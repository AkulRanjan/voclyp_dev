"""Security primitives used across the platform.

- API keys: random, prefixed, stored only as salted PBKDF2 hashes, verified in
  constant time, with scopes, expiry and revocation.
- Webhooks: per-endpoint HMAC secrets, timestamped SHA-256 signatures, and an
  SSRF guard that refuses URLs resolving to private/loopback/link-local space.
- Audit log: SHA-256 hash chaining so tampering with any historical entry is
  detectable.
- AudioVault: encryption at rest (Fernet/AES-128-CBC+HMAC) for raw audio during
  its short life before pipeline deletion, with best-effort secure overwrite.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit

API_KEY_PREFIX = "vclp"
PBKDF2_ITERATIONS = 100_000
VALID_SCOPES = ("ingest", "read", "admin")


class SecurityConfigError(Exception):
    pass


# -- API keys ----------------------------------------------------------------

def generate_api_key():
    """Return (full_key, key_id, secret). The full key is shown exactly once;
    only the salted hash of the secret is ever stored."""
    key_id = secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    return f"{API_KEY_PREFIX}_{key_id}_{secret}", key_id, secret


def parse_api_key(full_key: str):
    """Return (key_id, secret) or None if the key is malformed."""
    parts = (full_key or "").split("_", 2)
    if len(parts) != 3 or parts[0] != API_KEY_PREFIX or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def hash_secret(secret: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS
    ).hex()


def verify_secret(secret: str, salt_hex: str, expected_hash_hex: str) -> bool:
    computed = hash_secret(secret, bytes.fromhex(salt_hex))
    return hmac.compare_digest(computed, expected_hash_hex)


def new_salt() -> str:
    return os.urandom(16).hex()


# -- webhook signing ----------------------------------------------------------

def new_webhook_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def _webhook_mac(secret: str, timestamp: int, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + body, hashlib.sha256
    ).hexdigest()


def sign_webhook(secret: str, timestamp: int, body: bytes,
                 *extra_secrets: str) -> str:
    """Signature header value: ``t=<unix-ts>,v1=<hmac-sha256-hex>``.
    The timestamp is signed so receivers can reject replayed deliveries.
    During a secret rotation overlap window, additional ``v1=`` entries are
    appended (one per still-valid secret) so consumers verifying against
    either the old or the new secret keep working — zero-downtime rotation."""
    macs = [_webhook_mac(s, timestamp, body) for s in (secret, *extra_secrets)]
    return f"t={timestamp}," + ",".join(f"v1={m}" for m in macs)


def verify_webhook_signature(secret: str, header: str, body: bytes,
                             tolerance_s: int = 300) -> bool:
    """Reference verifier (what we document for partners). Accepts a header
    carrying multiple ``v1=`` signatures and matches any of them."""
    ts = None
    provided = []
    for part in header.split(","):
        key, sep, value = part.partition("=")
        if not sep:
            return False
        if key == "t":
            try:
                ts = int(value)
            except ValueError:
                return False
        elif key == "v1":
            provided.append(value)
    if ts is None or not provided:
        return False
    if abs(time.time() - ts) > tolerance_s:
        return False
    expected = _webhook_mac(secret, ts, body)
    return any(hmac.compare_digest(expected, p) for p in provided)


# -- SSRF guard ----------------------------------------------------------------

def check_webhook_url(url: str, allow_insecure: bool = False):
    """Return (ok, reason). Refuses anything that could be used to reach
    internal infrastructure (SSRF): non-https schemes, credentials in the URL,
    and hosts resolving to private/loopback/link-local/reserved addresses.
    The ``log://`` scheme is the no-network sink used by tests and connectors."""
    parts = urlsplit(url)
    if parts.scheme == "log":
        return True, "ok"
    allowed = ("https", "http") if allow_insecure else ("https",)
    if parts.scheme not in allowed:
        return False, f"scheme '{parts.scheme}' not allowed (https required)"
    if not parts.hostname:
        return False, "missing host"
    if parts.username or parts.password:
        return False, "credentials in URL not allowed"
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443,
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, "host does not resolve"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, f"host resolves to non-public address {ip}"
    return True, "ok"


# -- audit hash chain -----------------------------------------------------------

def chain_hash(prev_hash: str, *fields: str) -> str:
    h = hashlib.sha256(prev_hash.encode("utf-8"))
    for f in fields:
        h.update(b"\x1f")
        h.update((f or "").encode("utf-8"))
    return h.hexdigest()


# -- audio encryption at rest ----------------------------------------------------

class AudioVault:
    """Read/write/destroy raw audio. With a master key, content is encrypted at
    rest (Fernet) for the short window before the pipeline deletes it. Deletion
    overwrites the file with random bytes before unlinking (best-effort on
    modern filesystems; the real guarantee is the short retention window)."""

    def __init__(self, master_key: bytes = b""):
        self._fernet = None
        if master_key:
            try:
                from cryptography.fernet import Fernet
            except ImportError as exc:  # fail closed: key set but no crypto lib
                raise SecurityConfigError(
                    "VOCLYP_MASTER_KEY is set but the 'cryptography' package is "
                    "not installed; refusing to store audio unencrypted"
                ) from exc
            # Production: master_key should itself be a random KMS-managed key;
            # the KDF here only normalizes its length.
            derived = hashlib.pbkdf2_hmac(
                "sha256", master_key, b"voclyp-audio-vault-v1", 200_000
            )
            self._fernet = Fernet(base64.urlsafe_b64encode(derived))

    @property
    def encrypted(self) -> bool:
        return self._fernet is not None

    def write(self, path, data: bytes) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._fernet.encrypt(data) if self._fernet else data)

    def read(self, path) -> bytes:
        raw = Path(path).read_bytes()
        return self._fernet.decrypt(raw) if self._fernet else raw

    def delete(self, path) -> None:
        path = Path(path)
        if not path.exists():
            return
        try:
            size = path.stat().st_size
            with open(path, "r+b") as f:
                f.write(os.urandom(size))
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass  # overwrite is best-effort; unlink below is mandatory
        path.unlink()

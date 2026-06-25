"""Ephemeral raw-audio storage.

Production uses S3 in ap-south-1 (Mumbai). Each object is tagged with
``erase_after`` so the erasure worker (and an S3 lifecycle rule as a backstop)
can destroy it within the DPDP 2-hour window. Offline, a filesystem-backed
mock with the same surface lets the whole flow run with no AWS account.
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AudioObject:
    bucket: str
    key: str
    sha256: str
    size: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audio_key(tenant_id: str, conversation_id: str, suffix: str = ".wav") -> str:
    return f"{tenant_id}/{conversation_id}{suffix}"


class LocalAudioStore:
    """Filesystem stand-in for S3 used in offline dev and tests."""

    backend = "local"

    def __init__(self, root, bucket: str = "voclyp-local-audio"):
        self.root = Path(root)
        self.bucket = bucket
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key

    def put(self, key: str, data: bytes, erase_after: str = "",
            metadata: dict | None = None) -> AudioObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        # record the erase_after tag alongside the blob
        if erase_after:
            path.with_suffix(path.suffix + ".tag").write_text(
                erase_after, encoding="utf-8")
        return AudioObject(self.bucket, key, _sha256(data), len(data))

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        existed = path.exists()
        if existed:
            # best-effort overwrite before unlink (mirror AudioVault.delete)
            try:
                size = path.stat().st_size
                with open(path, "r+b") as fh:
                    import os
                    fh.write(os.urandom(size))
                    fh.flush()
            except OSError:
                pass
            path.unlink()
        tag = path.with_suffix(path.suffix + ".tag")
        if tag.exists():
            tag.unlink()
        return existed

    def ensure_lifecycle(self) -> None:
        """No-op locally; the erasure worker is the precise enforcer."""
        return None


class S3AudioStore:  # pragma: no cover - exercised only with real AWS creds
    """boto3-backed S3 store in ap-south-1."""

    backend = "s3"

    def __init__(self, settings):
        import boto3

        self.bucket = settings.s3_bucket
        kwargs = {"region_name": settings.aws_region}
        if settings._aws_creds_present():
            kwargs.update(
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            if settings.aws_session_token:
                kwargs["aws_session_token"] = settings.aws_session_token
        self._s3 = boto3.client("s3", **kwargs)

    def put(self, key: str, data: bytes, erase_after: str = "",
            metadata: dict | None = None) -> AudioObject:
        tagging = f"erase_after={erase_after}&ephemeral=true" if erase_after else "ephemeral=true"
        self._s3.put_object(
            Bucket=self.bucket, Key=key, Body=data,
            ContentType="audio/wav",
            Tagging=tagging,
            Metadata={k: str(v) for k, v in (metadata or {}).items()},
            ServerSideEncryption="aws:kms",
        )
        return AudioObject(self.bucket, key, _sha256(data), len(data))

    def get(self, key: str) -> bytes:
        resp = self._s3.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def delete(self, key: str) -> bool:
        self._s3.delete_object(Bucket=self.bucket, Key=key)
        return True

    def ensure_lifecycle(self) -> None:
        """Backstop lifecycle rule: expire ephemeral-tagged objects after 1 day
        (the erasure worker enforces the precise 2-hour deadline)."""
        self._s3.put_bucket_lifecycle_configuration(
            Bucket=self.bucket,
            LifecycleConfiguration={
                "Rules": [{
                    "ID": "voclyp-ephemeral-audio",
                    "Filter": {"Tag": {"Key": "ephemeral", "Value": "true"}},
                    "Status": "Enabled",
                    "Expiration": {"Days": 1},
                }],
            },
        )


def open_audio_store(settings):
    """S3 when a bucket + boto3 are available, else the filesystem mock."""
    if settings.has_aws():
        try:
            return S3AudioStore(settings)
        except Exception:
            pass
    return LocalAudioStore(settings.local_path / "s3")

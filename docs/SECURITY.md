# VoClyp — Security Model and Guardrails

VoClyp processes the most sensitive artifact a field business produces: raw
recordings of real customers. The design principle is **the platform should not
need to be trusted** — the dangerous material (audio, PII) is destroyed or
redacted by the machine itself, provably, before insight ever leaves the
pipeline. This document is the threat model, the controls implemented in code,
and the hardening required at deployment time.

## Assets and trust boundaries

| Asset | Sensitivity | Lifetime |
|---|---|---|
| Raw audio | Highest (voice, PII, biometrics) | Minutes–hours: destroyed by the pipeline |
| Customer PII (names, phones, Aadhaar, PAN, email) | High | Redacted before analysis; never stored |
| Insight documents | Medium (de-identified business signal) | Retained per tenant, delete-on-demand |
| API keys / webhook secrets | High | Hashed at rest / shown once |
| Audit + consent logs | High (integrity, not confidentiality) | Retained, tamper-evident |

Trust boundaries: (1) field device → gateway, (2) gateway → internal services,
(3) insight store → partner systems. Nothing crosses 1 or 3 except the public
contracts; nothing inside is reachable except through the gateway.

## Threat model → implemented controls

| Threat (STRIDE) | Control | Where |
|---|---|---|
| **S**poofed caller | API keys: random 256-bit secrets, salted PBKDF2-SHA256 (100k iters), constant-time compare, revocation + expiry; plaintext shown exactly once | `security.py`, `store.py` |
| Spoofed webhook payloads to partners | Per-endpoint HMAC-SHA256 signatures with signed timestamp (`X-Voclyp-Signature: t=...,v1=...`), replay window | `security.py`, `delivery.py` |
| **T**ampering with audit history | Per-tenant SHA-256 hash chain over every audit entry; `verify_audit_chain` detects any edit; exposed at `GET /v1/audit` | `store.py` |
| Tampering with uploads in transit | TLS (deployment, see checklist); idempotency keys prevent duplicate-processing tricks | gateway proxy, `ingestion.py` |
| **R**epudiation ("we never recorded / never deleted") | Consent log at submit time; audio deletion is itself an audited, hash-chained event | `ingestion.py`, `worker.py` |
| **I**nformation disclosure: cross-tenant reads | Structural isolation — no store method or SQL path exists without `tenant_id` | `store.py` |
| Disclosure: raw audio at rest | AudioVault encryption (Fernet: AES-128-CBC + HMAC) when `VOCLYP_MASTER_KEY` is set; fails closed if the key is set but crypto is unavailable; secure-overwrite on delete | `security.py` |
| Disclosure: PII in insights | Redaction (phone, email, Aadhaar, PAN, consented customer name) runs **before** analysis; audio destroyed before signal extraction; quotes in signals are post-redaction | `redaction.py`, pipeline order |
| Disclosure: SSRF via webhook URLs | https-only, no URL credentials, DNS-resolved addresses must be public (blocks 127.0.0.1, RFC-1918, link-local/cloud metadata 169.254.169.254); checked at registration **and** at every send | `security.py`, gateway, `delivery.py` |
| Disclosure: error leakage | Generic 500s; no stack traces, paths, or internals in responses | gateway |
| **D**enial of service | Per-key rate limiting (429 + Retry-After); Content-Length precheck + body size cap; metadata field length caps; durable queue absorbs bursts, retries capped, poison jobs dead-lettered | gateway, `ingestion.py`, `queueing.py` |
| **E**levation of privilege | Scopes per key (`ingest` / `read` / `admin`); field devices get ingest-only keys — a stolen device key cannot read a single insight or touch webhooks. Console users authenticate with a signed session token; the **role is a signed claim** mapped to scopes server-side (`manager`→read+admin, `sales`→ingest+read), so a user cannot escalate by editing client state, and self-signup as a manager is blocked by invite-gating | gateway, `security.py`, `store.py` |

Plus browser-grade response hygiene on every gateway response:
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Cache-Control: no-store`, `Referrer-Policy: no-referrer`, restrictive CSP.

## Console authentication (operator UI)

The web console (`web/`) and any first-party UI authenticate users with
email/password and a **signed session token**, distinct from machine API keys.

- **Passwords**: salted PBKDF2-SHA256 (same primitive as API keys), constant-time
  verify, 8–256 char policy; plaintext never stored or logged.
- **Session token**: compact HMAC-SHA256-signed claims (`sub`, `role`, `tenant`,
  `epoch`, `iat`, `exp`), 12h TTL. It is **not** a bearer-only trust: every
  request re-validates the token against live user state — the user must still
  exist, the `role` claim must match the current role, and the `epoch` must
  match the user's `session_epoch`. So role changes and logout take effect
  immediately.
- **Role → scope** is enforced at the gateway, server-side. The same `/v1`
  endpoints accept *either* a tenant API key *or* a session token; both resolve
  to a tenant + scope set. A `sales` user's token cannot call admin endpoints
  (webhooks, metrics, delete) — verified by tests.
- **Invite-gating**: the first account for a new organization becomes its
  manager/owner; everyone else must redeem a single-use, manager-issued invite
  that fixes their role. This closes self-elected-manager registration.
- **Server-side logout / revocation**: `POST /auth/logout` bumps the user's
  `session_epoch`, invalidating every outstanding token for that user. The same
  mechanism backs forced logout on role change or password reset.
- **Signing secret**: `VOCLYP_SESSION_SECRET`. If unset, it is derived from the
  master key via HMAC domain separation (never the raw audio key); in
  `VOCLYP_ENV=production` the gateway **fails closed** rather than fall back to
  an ephemeral secret.
- **Brute force**: per-(client, email) login throttle (10 / 5 min). Auth events
  (signup, login, logout, invite) are written to the tamper-evident audit log.

Residual notes: tokens live in browser `localStorage` (mitigated by a strict
same-origin CSP — no inline scripts, `script-src 'self'`); intra-tenant reads
are tenant-scoped, not yet per-agent (a `sales` user can read their tenant's
insights via the API though the UI does not surface it) — per-agent read
scoping is the next refinement.

## Key management

- `VOCLYP_MASTER_KEY` (audio at rest) must come from a KMS / secrets manager,
  never from code, config files, or human-chosen passphrases. Rotate by
  re-issuing; audio lives hours at most, so rotation has no migration cost.
- API keys: issue ingest-only keys to field deployments, read keys to partner
  integrations, admin keys to nobody by default. Set `expires_days` for
  anything handed to a device fleet. Revoke immediately on device loss
  (`revoke_api_key` — takes effect on the next request).
- Webhook signing secrets are per-endpoint; rotating one endpoint does not
  disturb others.
- `VOCLYP_SESSION_SECRET` (console token signing) must be a stable 32+ byte
  random value from the secrets manager in production — required (fail-closed)
  when `VOCLYP_ENV=production`. Rotating it logs every console user out.

## Deployment hardening checklist (not enforced by code)

- [ ] TLS 1.2+ terminated in front of the gateway (the app sets HSTS-adjacent
      headers but cannot provide transport security itself). No plaintext
      listener exposed.
- [ ] `VOCLYP_ENV=production` and `VOCLYP_SESSION_SECRET` set (the gateway
      refuses to start in production without a stable session secret).
- [ ] Rate limiting and the login throttle are per-process/in-memory; front
      with a shared limiter (or sticky sessions) when running more than one
      gateway instance.
- [ ] Gateway is the **only** ingress; workers, queue, and store live on a
      private network with no inbound routes.
- [ ] Database/disk encryption (TDE or encrypted volumes) for the insight
      store — insights are de-identified, but defense in depth applies.
- [ ] Secrets injected via KMS/secret manager; no secrets in env files in
      images; image scanning + pinned dependencies in CI.
- [ ] Per-tenant data residency honored at the storage layer (region field on
      tenants is the routing seed).
- [ ] Monitoring: alert on auth-failure spikes, rate-limit saturation,
      dead-letter growth, audit-chain verification failures (run
      `verify_audit_chain` on a schedule), and audio files older than the
      deletion SLA.
- [ ] Backups of the insight store must honor delete-on-demand (backup
      retention ≤ deletion SLA, or deletion replay on restore).
- [ ] Pen test before first enterprise tenant; re-test on major releases.

## Compliance mapping

- **India DPDP Act 2023**: consent at capture (consent log), purpose
  limitation (only de-identified insight retained), erasure on request
  (`DELETE /v1/conversations/{id}`, audited), data residency (`region` per
  tenant), breach accountability (tamper-evident audit trail).
- **GDPR-style rights**: erasure and auditability as above; raw-voice
  minimization by pipeline-enforced deletion.
- **SOC 2 (Security/Confidentiality)**: access control (scoped keys, RBAC
  seed), audit logging with integrity, encryption in transit (deployment) and
  at rest, change-controlled schema/taxonomy versioning recorded per insight.

## Reporting

Suspected vulnerabilities: open a private issue or contact the maintainers
directly. Do not include real customer data in reports.

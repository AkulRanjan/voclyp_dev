# VoClyp — Private Cloud Deployment on AWS

How to run the VoClyp backend as a **private, secure deployment in your own AWS
account** — a locked-down VPC (Virtual Private Cloud) with everything on private
subnets and the gateway as the only ingress. This is the topology
[docs/SECURITY.md](SECURITY.md) already assumes; the production hardening already
in the code (`VOCLYP_ENV=production` fail-closed, required `VOCLYP_SESSION_SECRET`)
is what makes the deploy safe.

> "Private cloud on AWS" = your AWS account + a VPC with no public ingress except
> a TLS-terminating load balancer in front of the gateway. It is not the same as
> an on-prem private cloud, but a hardened VPC is the AWS-native equivalent.

## The decision that drives everything: state

The backend today is **single-node by design**. The gateway and the worker run
from one image and share one `/data` volume holding **SQLite** (`voclyp.db`,
`queue.db`) and the **audio files**. That is ideal for the demo but does not
scale horizontally and is fragile on networked filesystems. Two paths:

| | **Path A — lift & shift** | **Path B — cloud-native (recommended)** |
|---|---|---|
| Effort | Runs the code **as-is** | Needs code changes (swap 3 backends) |
| State | One EBS volume (SQLite + audio) | **RDS Postgres** + **S3** + **SQS** |
| Scale | Vertical only, single node | Gateway & worker scale independently |
| Good for | Pilot / single tenant | A real product deployment |

`docs/BUILD-MAP.md` already lists Path B's pieces ("real object storage for
chunks; real broker behind `queueing.py`") as the remaining Phase-1 work, and the
code has clean seams for it (`store.py`, `security.AudioVault`, `queueing.py`).
**Recommendation: ship Path A to get something live, then migrate to Path B.**

## AWS service mapping

| VoClyp piece | AWS service |
|---|---|
| Gateway + worker container (the existing `Dockerfile`) | **ECS Fargate** (or EC2) in **private subnets** |
| Only ingress, TLS termination | **ALB** in public subnets + **ACM** certificate (+ optional **WAF**) |
| Insight / user / audit store (`store.py`) | **RDS PostgreSQL** (Path B) · EBS SQLite (Path A) |
| Audio at rest (`AudioVault`) | **S3** bucket — SSE-KMS, public access blocked |
| Job queue (`queueing.py`) | **SQS** (+ dead-letter queue) (Path B) |
| Secrets: `VOCLYP_MASTER_KEY`, `VOCLYP_SESSION_SECRET`, `SARVAM_API_KEY` | **Secrets Manager** + **KMS** customer-managed key |
| Container image registry | **ECR** |
| Frontend (`web/dist`) | **S3 + CloudFront**, or served by the gateway (same-origin) |
| Logs / alarms / threat detection | **CloudWatch**, **GuardDuty**, **CloudTrail** |
| Keep traffic off the public internet | **VPC endpoints** (S3, ECR, Secrets Manager, SQS) |

## Target architecture (Path B)

```
                Internet
                   │  HTTPS (ACM cert)
            ┌──────▼──────┐  public subnets
            │  ALB (+WAF) │
            └──────┬──────┘
   ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  VPC boundary
   private subnets │ (no public IPs below)
            ┌──────▼───────┐        ┌──────────────┐
            │ Gateway      │        │ Worker       │  (no ingress)
            │ (Fargate)    │        │ (Fargate ×N) │
            └───┬───┬───┬──┘        └──┬───┬───┬───┘
                │   │   │              │   │   │
        ┌───────▼┐ ┌▼────────┐ ┌───────▼┐ ┌▼──────┐ ┌▼───────────────┐
        │  RDS   │ │   SQS   │ │  S3    │ │ KMS   │ │ Secrets Manager │
        │Postgres│ │ (queue) │ │(audio) │ │       │ │                 │
        └────────┘ └─────────┘ └────────┘ └───────┘ └─────────────────┘
```

The ALB can reach **only** the gateway; the worker has no inbound rules at all;
RDS / SQS / S3 are reached over private subnets and VPC endpoints.

## Step-by-step

1. **Account & region.** Pick a region for data residency — e.g. `ap-south-1`
   (Mumbai) given Indian customers + the DPDP Act. Operate via an IAM role (not
   root); enable CloudTrail and GuardDuty.
2. **Network.** A VPC with 2 public + 2 private subnets across 2 AZs; one NAT
   gateway (or VPC endpoints to avoid NAT cost); security groups: ALB→gateway
   :8000 only, gateway→RDS/SQS, **nothing inbound to the worker**.
3. **Secrets.** Create a KMS CMK. Put `VOCLYP_MASTER_KEY`,
   `VOCLYP_SESSION_SECRET` (32+ random bytes), and `SARVAM_API_KEY` in Secrets
   Manager. Never bake them into the image.
4. **Image.** `docker build` and push to ECR. (The `Dockerfile` already runs as a
   non-root `voclyp` user.)
5. **Data stores.** RDS Postgres (encrypted at rest, private subnet, automated
   backups); an S3 bucket (block public access, SSE-KMS, lifecycle rule to expire
   any stray audio object); an SQS queue + dead-letter queue.
6. **Compute.** One ECS Fargate cluster, two services from the same image:
   - **gateway** — `uvicorn voclyp.gateway.app:app`, behind the ALB, with
     `VOCLYP_ENV=production` and secrets injected from Secrets Manager.
   - **worker** — `python -m voclyp.worker`, desired count ≥ 1, no load balancer.
   Give each task an IAM role scoped to exactly its S3 prefix / SQS queue /
   secret ARNs (least privilege).
7. **TLS & ingress.** ACM certificate on the ALB; HTTPS only (redirect 80→443);
   optional WAF with rate rules. The app already emits `X-Content-Type-Options`,
   `X-Frame-Options: DENY`, a restrictive CSP, and `Cache-Control: no-store`.
8. **Frontend.** `cd web && npm run build`, then host `dist/` on S3 + CloudFront
   (or have the gateway serve it so it is same-origin). Point it at the ALB
   domain; the app calls `/v1` and `/auth` with the session token.
9. **Observability.** Ship logs to CloudWatch; alarm on auth-failure spikes,
   5xx, SQS DLQ growth, and schedule `verify_audit_chain` (see the SECURITY.md
   checklist).

## What Path B costs in code (honest)

Path A runs as-is. Path B swaps three backends behind existing seams:

- `store.py` → a Postgres-backed `Store` (SQLite → `psycopg`; the tenant-scoped
  query shape is unchanged).
- `AudioVault` (`security.py`) → read/write/delete against **S3** instead of the
  local filesystem (keep encryption, or rely on S3 SSE-KMS).
- `queueing.py` → an **SQS** producer/consumer in place of the SQLite queue.

These are isolated, well-defined changes the architecture was built for, but they
are real work (a focused effort each) plus tests. Make each backend selectable by
env var so SQLite/local stays the default for dev and tests.

## Security mapping (AWS ⇄ controls)

| Control | AWS realization |
|---|---|
| Gateway is the only ingress | ALB → gateway SG only; worker SG has no inbound |
| Internal services private | RDS/SQS/S3 in private subnets; VPC endpoints; no public IPs |
| Secrets from a manager, not code | Secrets Manager + KMS CMK; injected into ECS tasks |
| Session token signing (fail-closed in prod) | `VOCLYP_ENV=production` + `VOCLYP_SESSION_SECRET` from Secrets Manager |
| Encryption at rest | RDS encrypted, EBS encrypted, S3 SSE-KMS |
| TLS in transit | ACM cert on ALB, HTTPS-only listener |
| Least privilege | Per-service IAM task roles scoped to specific ARNs |
| Audit integrity | Hash-chained audit log; ship to CloudWatch; scheduled `verify_audit_chain` |
| Data residency (DPDP) | Single-region deployment; `region` field per tenant |
| Threat detection / forensics | GuardDuty, CloudTrail, VPC Flow Logs |

## Rough cost

A small single-region private deployment is roughly **$100–200 / month**:
Fargate (~$30), ALB (~$18), RDS `t4g.micro` (~$15–30), and the usual gotcha —
**NAT Gateway (~$32 + data)**, which VPC endpoints can largely replace.
S3 / SQS / Secrets / KMS / CloudFront are a few dollars each.

## Next artifacts (not yet built)

1. **Infrastructure as code** — a Terraform (or AWS CDK) module for the whole
   Path-B stack (VPC, ECS, ALB+ACM, RDS, S3, SQS, Secrets, IAM).
2. **Backend swaps** — Postgres `Store`, S3 `AudioVault`, SQS queue, selectable
   by env var, with tests.
3. **Production pipeline** — split entrypoints + a GitHub Actions workflow:
   build → push to ECR → deploy to ECS.

Suggested order: **#2 then #1** — land the cloud-native backends behind their
seams, then the IaC to run them. No AWS account is touched until that exists and
you explicitly authorize a deploy.

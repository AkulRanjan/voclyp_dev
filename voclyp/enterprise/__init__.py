"""VoClyp enterprise cloud layer (additive, feature-flagged).

This package holds the cloud-native, event-driven build described in
docs/enterprise/ARCHITECTURE.md: DPDP-grade consent capture, S3 ephemeral
audio, Kafka eventing, Sarvam dual-transcript ASR, AWS Bedrock (Claude)
extraction, multi-channel routing, and 2-hour erasure.

Nothing in the existing pipeline imports this package. With
VOCLYP_ENTERPRISE_ENABLED unset (the default) the gateway behaves exactly as
before. Every external dependency (boto3, confluent-kafka, psycopg, twilio) is
optional: when the credential or library is missing the component degrades to
an in-process mock so the whole flow still runs end-to-end offline.
"""
from __future__ import annotations

from .config import EnterpriseSettings, load_enterprise_settings

__all__ = ["EnterpriseSettings", "load_enterprise_settings"]

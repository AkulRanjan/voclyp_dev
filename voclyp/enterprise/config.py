"""Enterprise configuration — environment-driven, safe defaults, all-off.

Like voclyp.config.Settings, every value here comes from the environment and
has a benign default. The platform stays in pure-offline/mock mode unless the
relevant credentials are present, so a developer can exercise the entire
event-driven flow with no cloud accounts.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _b(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _s(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class EnterpriseSettings:
    # master switch — when False the gateway never mounts enterprise routes
    enabled: bool = False

    # where local stores / mock sinks live (offline dev + tests)
    local_dir: str = "data/enterprise"

    # -- AWS (S3 Mumbai + Bedrock Claude) -------------------------------------
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""
    s3_bucket: str = ""
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"

    # -- Supabase / Postgres ---------------------------------------------------
    supabase_db_url: str = ""          # postgres connection string (psycopg)
    supabase_url: str = ""             # https://<project>.supabase.co (optional)
    supabase_service_key: str = ""     # service-role key (optional)

    # -- Kafka -----------------------------------------------------------------
    kafka_bootstrap: str = ""
    kafka_security_protocol: str = "SASL_SSL"
    kafka_sasl_mechanism: str = "PLAIN"
    kafka_sasl_username: str = ""
    kafka_sasl_password: str = ""
    kafka_group_id: str = "voclyp-enterprise"

    # -- Twilio WhatsApp -------------------------------------------------------
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""     # e.g. whatsapp:+1415...
    twilio_template_sid: str = ""      # approved content template (HX...)

    # -- Zoho CRM --------------------------------------------------------------
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_api_domain: str = "https://www.zohoapis.in"
    zoho_accounts_domain: str = "https://accounts.zoho.in"

    # -- Redis -----------------------------------------------------------------
    redis_url: str = ""

    # -- Sarvam (shared with the core pipeline) --------------------------------
    sarvam_api_key: str = ""

    # -- business rules --------------------------------------------------------
    # Below this overall confidence, OR whenever a numeric EMI commitment is
    # extracted, WhatsApp is held for 1-tap agent verification (Self-Correction 2).
    confidence_threshold: float = 0.55
    # Sarvam REST hard limit is 30s; longer audio routes to the Batch API.
    sarvam_rest_limit_s: float = 30.0
    # DPDP ephemeral-audio promise: destroy raw audio within this window.
    erase_after_seconds: int = 7200    # 2 hours

    # convenience flags
    def has_aws(self) -> bool:
        # boto3's default credential chain may still work without explicit keys,
        # but for the mock decision we require an explicit bucket.
        return bool(self.s3_bucket)

    def has_bedrock(self) -> bool:
        return bool(self.aws_region and self._aws_creds_present())

    def _aws_creds_present(self) -> bool:
        return bool(self.aws_access_key_id and self.aws_secret_access_key)

    def has_supabase(self) -> bool:
        return bool(self.supabase_db_url)

    def has_kafka(self) -> bool:
        return bool(self.kafka_bootstrap)

    def has_twilio(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token
                    and self.twilio_whatsapp_from)

    def has_zoho(self) -> bool:
        return bool(self.zoho_client_id and self.zoho_refresh_token)

    @property
    def local_path(self) -> Path:
        return Path(self.local_dir)


def load_enterprise_settings() -> EnterpriseSettings:
    return EnterpriseSettings(
        enabled=_b("VOCLYP_ENTERPRISE_ENABLED"),
        local_dir=_s("VOCLYP_ENTERPRISE_DIR", "data/enterprise"),
        aws_region=_s("AWS_REGION", "ap-south-1"),
        aws_access_key_id=_s("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_s("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=_s("AWS_SESSION_TOKEN"),
        s3_bucket=_s("VOCLYP_S3_BUCKET"),
        bedrock_model_id=_s("VOCLYP_BEDROCK_MODEL_ID",
                            "anthropic.claude-3-5-sonnet-20240620-v1:0"),
        supabase_db_url=_s("SUPABASE_DB_URL"),
        supabase_url=_s("SUPABASE_URL"),
        supabase_service_key=_s("SUPABASE_SERVICE_KEY"),
        kafka_bootstrap=_s("KAFKA_BOOTSTRAP_SERVERS"),
        kafka_security_protocol=_s("KAFKA_SECURITY_PROTOCOL", "SASL_SSL"),
        kafka_sasl_mechanism=_s("KAFKA_SASL_MECHANISM", "PLAIN"),
        kafka_sasl_username=_s("KAFKA_SASL_USERNAME"),
        kafka_sasl_password=_s("KAFKA_SASL_PASSWORD"),
        kafka_group_id=_s("KAFKA_GROUP_ID", "voclyp-enterprise"),
        twilio_account_sid=_s("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_s("TWILIO_AUTH_TOKEN"),
        twilio_whatsapp_from=_s("TWILIO_WHATSAPP_FROM"),
        twilio_template_sid=_s("TWILIO_TEMPLATE_SID"),
        zoho_client_id=_s("ZOHO_CLIENT_ID"),
        zoho_client_secret=_s("ZOHO_CLIENT_SECRET"),
        zoho_refresh_token=_s("ZOHO_REFRESH_TOKEN"),
        zoho_api_domain=_s("ZOHO_API_DOMAIN", "https://www.zohoapis.in"),
        zoho_accounts_domain=_s("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.in"),
        redis_url=_s("REDIS_URL"),
        sarvam_api_key=_s("SARVAM_API_KEY"),
        confidence_threshold=_f("VOCLYP_CONFIDENCE_THRESHOLD", 0.55),
        sarvam_rest_limit_s=_f("VOCLYP_SARVAM_REST_LIMIT_S", 30.0),
        erase_after_seconds=_i("VOCLYP_ERASE_AFTER_SECONDS", 7200),
    )

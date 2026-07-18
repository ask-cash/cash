"""
config.py — Central, environment-driven configuration for Cash.

Everything cloud-native reads from here so the same image runs locally
(SQLite + local disk) and in Kubernetes (Postgres + Redis + object storage)
purely by changing environment variables.
"""

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- Database -------------------------------------------------------
    # Postgres in prod (postgresql://...), empty falls back to local SQLite.
    database_url: str = ""
    sqlite_path: str = os.path.join("user_data", "cash.db")

    # --- Queue ----------------------------------------------------------
    # Redis URL for the gateway -> worker job queue. Empty = in-process
    # synchronous execution (handy for local single-process dev).
    redis_url: str = ""
    queue_name: str = "cash:jobs"

    # --- Object storage -------------------------------------------------
    # Native GCS, S3-compatible storage, or local disk for development.
    storage_backend: str = "local"           # "local" | "s3" | "gcs"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""                 # set for minio / non-AWS
    s3_region: str = "us-east-1"
    gcs_bucket: str = ""
    gcs_project: str = ""
    local_storage_dir: str = "user_data/uploads"

    # --- Secrets / per-tenant token vault -------------------------------
    secrets_backend: str = "db"               # "db" | "env"
    # Fernet key (32-byte url-safe base64) used to encrypt tenant tokens at
    # rest in Postgres. Supplied via a K8s Secret in prod.
    secrets_encryption_key: str = ""

    # --- Multi-tenancy --------------------------------------------------
    # Tenant used when no explicit tenant context is set (local dev /
    # single-tenant legacy main.py).
    default_tenant_id: str = "default"
    enforce_tenant: bool = False              # raise if tenant unset

    # --- Gateway --------------------------------------------------------
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8080
    public_base_url: str = ""                 # https://api.<domain>
    telegram_webhook_secret: str = ""         # X-Telegram-Bot-Api-Secret-Token

    # --- Discord connector ----------------------------------------------
    connector_shard_index: int = 0            # this pod's slice (StatefulSet ordinal)
    connector_shard_total: int = 1            # number of connector pods

    # --- Observability --------------------------------------------------
    metrics_enabled: bool = True
    log_level: str = "INFO"
    log_json: bool = False

    # --- Customer onboarding --------------------------------------------
    # When true, non-owner users who DM Cash on any platform are taken through
    # the in-chat onboarding flow (name/email/timezone/use case) and issued a
    # secure setup link. Owner messages are never onboarded.
    onboarding_enabled: bool = True
    # Secret used to sign onboarding links. Falls back to the Fernet key, then
    # to a dev default — set ONBOARDING_SIGNING_SECRET in prod.
    onboarding_signing_secret: str = ""
    onboarding_link_ttl_hours: int = 72


def load_settings() -> Settings:
    """Build Settings from the current environment."""
    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        sqlite_path=os.getenv("SQLITE_PATH", os.path.join("user_data", "cash.db")),
        redis_url=os.getenv("REDIS_URL", ""),
        queue_name=os.getenv("QUEUE_NAME", "cash:jobs"),
        storage_backend=os.getenv("STORAGE_BACKEND", "local"),
        s3_bucket=os.getenv("S3_BUCKET", ""),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", ""),
        s3_region=os.getenv("S3_REGION", "us-east-1"),
        gcs_bucket=os.getenv("GCS_BUCKET", ""),
        gcs_project=os.getenv("GCS_PROJECT", ""),
        local_storage_dir=os.getenv("LOCAL_STORAGE_DIR", "user_data/uploads"),
        secrets_backend=os.getenv("SECRETS_BACKEND", "db"),
        secrets_encryption_key=os.getenv("SECRETS_ENCRYPTION_KEY", ""),
        default_tenant_id=os.getenv("DEFAULT_TENANT_ID", "default"),
        enforce_tenant=_bool("ENFORCE_TENANT", False),
        gateway_host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        gateway_port=int(os.getenv("GATEWAY_PORT", "8080")),
        public_base_url=os.getenv("PUBLIC_BASE_URL", ""),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        connector_shard_index=_shard_index(),
        connector_shard_total=int(os.getenv("CONNECTOR_SHARD_TOTAL", "1")),
        metrics_enabled=_bool("METRICS_ENABLED", True),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_json=_bool("LOG_JSON", False),
        onboarding_enabled=_bool("CASH_ONBOARDING_ENABLED", True),
        onboarding_signing_secret=os.getenv("ONBOARDING_SIGNING_SECRET", ""),
        onboarding_link_ttl_hours=int(os.getenv("ONBOARDING_LINK_TTL_HOURS", "72")),
    )


def _shard_index() -> int:
    """Derive the connector shard ordinal.

    In a StatefulSet the pod name ends with the ordinal (e.g. cash-connector-2),
    so we parse POD_NAME when CONNECTOR_SHARD_INDEX is not explicitly set.
    """
    explicit = os.getenv("CONNECTOR_SHARD_INDEX")
    if explicit is not None:
        return int(explicit)
    pod_name = os.getenv("POD_NAME", "")
    if pod_name and "-" in pod_name:
        tail = pod_name.rsplit("-", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return 0


settings = load_settings()

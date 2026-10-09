"""Core configuration for the Cloud Fuel & Dispensing Platform.

Pydantic-settings based environment-driven configuration, loaded with
precedence: defaults < .env < exported env vars.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Runtime -----------------------------------------------------------
    ENVIRONMENT: Literal["dev", "test", "prod"] = "dev"
    DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    INGESTION_PORT: int = 8001

    # --- Security ----------------------------------------------------------
    SECRET_KEY: str = secrets.token_hex(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    PASSWORD_MIN_LENGTH: int = 8
    LOGIN_RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 900

    # --- Database ----------------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "fuel_monitoring"
    POSTGRES_USER: str = "fuel_user"
    POSTGRES_PASSWORD: str = "fuel_pass"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 20
    TESTING: bool = False

    # --- Redis -------------------------------------------------------------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # --- MQTT / EMQX -------------------------------------------------------
    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_TLS_PORT: int = 8883
    MQTT_CA_CERT: str | None = None
    MQTT_CLIENT_CERT: str | None = None
    MQTT_CLIENT_KEY: str | None = None
    #: Connect to the broker over TLS. Previously inferred from MQTT_CA_CERT being
    #: non-empty, which meant a deployment could look configured (a cert path was
    #: set) while still connecting in plaintext. Make it explicit instead.
    MQTT_USE_TLS: bool = False
    #: Refuse to start without TLS. A production deployment that silently falls
    #: back to plaintext would transmit device credentials in the clear.
    MQTT_REQUIRE_TLS: bool = False
    MQTT_QOS: int = 1
    MQTT_KEEPALIVE: int = 60
    #: Broker credentials for the platform's own ingestion service. The broker is
    #: deny-by-default (see infra/emqx/emqx.conf), so these are required for
    #: telemetry to flow at all (G-001).
    MQTT_SERVICE_USERNAME: str = ""
    MQTT_SERVICE_PASSWORD: str = ""
    #: EMQX 5 automation credential for the REST API (provisioning script).
    #: EMQX's REST API authenticates with an API key/secret, not with dashboard
    #: credentials; the key is bootstrapped from infra/emqx/secrets/api_keys.txt.
    EMQX_API_URL: str = "http://emqx:18083"
    EMQX_API_KEY: str = ""
    EMQX_API_SECRET: str = ""
    #: Per-gateway device password template. Provisioning derives each device
    #: password from this seed + the device MAC (see scripts/provision_mqtt_accounts).
    MQTT_DEVICE_PASSWORD_SEED: str = ""

    # --- Dispensing --------------------------------------------------------
    CODE_LENGTH_MIN: int = 6
    CODE_LENGTH_MAX: int = 8
    CODE_TTL_DAYS: int = 7
    CODE_MAX_ATTEMPTS: int = 5
    CODE_RATE_LIMIT_PER_MIN: int = 10
    DISPENSE_GRACE_LITERS: float = 0.5          # allowed overshoot tolerance
    PARTIAL_MIN_REMAINING_LITERS: float = 1.0   # below this, treat as fulfilled
    TOTALIZER_DISCREPANCY_TOLERANCE_LITERS: float = 1.0

    # --- Notifications -----------------------------------------------------
    DEFAULT_NOTIFICATION_CHANNEL: str = "sms"     # sms|whatsapp|email|webhook
    NOTIFY_MAX_RETRIES: int = 3
    NOTIFY_RETRY_BACKOFF: int = 5          # seconds; exponential per attempt

    # --- Alarm clearing -----------------------------------------------------
    #: A threshold alarm only auto-resolves once the measurement is this far back
    #: inside the safe band. Without it a value hovering on the threshold flaps
    #: the alarm on and off (an "alarm storm").
    ALARM_CLEAR_HYSTERESIS_METERS: float = 0.05
    ALARM_CLEAR_HYSTERESIS_LITERS: float = 25.0

    # --- Telemetry freshness ----------------------------------------------
    # A tank/gateway that stays silent longer than this is reported offline and
    # a communication_lost alarm is raised by the stale-connection sweeper.
    TANK_STALE_AFTER_SECONDS: int = 300
    GATEWAY_STALE_AFTER_SECONDS: int = 600
    STALE_SWEEP_INTERVAL_SECONDS: int = 60

    # --- Edge trust ----------------------------------------------------------
    # Shared secret protecting the standalone ingestion service's HTTP fallback
    # endpoints (/api/v1/ingest/*).  When empty those endpoints are DISABLED
    # (404) — MQTT remains the normal path.  Never expose :8001 without it.
    INGEST_API_KEY: str = ""

    # --- Gateway commands --------------------------------------------------
    COMMAND_QUEUE_OUTBOUND: str = "iot:commands:outbound"
    COMMAND_QUEUE_INFLIGHT: str = "iot:commands:inflight"
    COMMAND_BACKOFF_BASE_SECONDS: int = 60
    COMMAND_BACKOFF_MAX_SECONDS: int = 900
    COMMAND_MAX_ATTEMPTS: int = 3
    COMMAND_PENDING_TTL_SECONDS: int = 120

    # --- TimescaleDB lifecycle ---------------------------------------------
    TSDB_MEASUREMENTS_RETENTION_DAYS: int = 30
    TSDB_COMPRESSION_AFTER_DAYS: int = 7

    # --- Analytics ---------------------------------------------------------
    CONSUMPTION_DEFAULT_DAYS: int = 30
    CONSUMPTION_FORECAST_WINDOW_DAYS: int = 7
    CSV_EXPORT_BATCH_SIZE: int = 1000

    # --- Admin seed --------------------------------------------------------
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@fuelplatform.local"
    ADMIN_PASSWORD: str = ""
    ADMIN_FORCE_PASSWORD: bool = False

    # --- CORS --------------------------------------------------------------
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Production safety --------------------------------------------------
    @model_validator(mode="after")
    def _fail_closed_in_production(self) -> Settings:
        """Refuse to run a production deployment on insecure defaults.

        Every one of these was silently satisfied before: the platform would
        start happily with plaintext broker credentials, development secrets and
        debug logging, and the operator would only find out on the first audit.
        Failing at startup is the only moment the mistake is cheap to fix.
        """
        if self.ENVIRONMENT != "prod":
            return self
        problems = []
        if not self.MQTT_USE_TLS:
            problems.append(
                "MQTT_USE_TLS is false: device credentials would cross the network "
                "in plaintext. Run scripts/generate_certs.sh and set "
                "MQTT_USE_TLS=true with MQTT_CA_CERT."
            )
        if self.ENVIRONMENT == "prod" and self.DEBUG:
            problems.append("DEBUG is true in production")
        placeholder = {"change-me", "changeme", "dev-secret", "secret"}
        if self.SECRET_KEY.strip().lower() in placeholder:
            problems.append("SECRET_KEY is still a placeholder value")
        if not self.POSTGRES_PASSWORD:
            problems.append("POSTGRES_PASSWORD is empty")
        if problems:
            raise ValueError(
                "Refusing to start in production with insecure configuration:\n  - "
                + "\n  - ".join(problems)
            )
        return self

    # --- Property convenience ---------------------------------------------
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


#: Cached singleton; mirrors what every module gets via ``get_settings()``.
settings = get_settings()
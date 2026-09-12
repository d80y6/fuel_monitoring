"""Core configuration for the Cloud Fuel & Dispensing Platform.

Pydantic-settings based environment-driven configuration, loaded with
precedence: defaults < .env < exported env vars.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

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
    MQTT_QOS: int = 1
    MQTT_KEEPALIVE: int = 60

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
    DEFAULT_NOTIFICATION_CHANNEL: Literal["sms", "whatsapp"] = "sms"
    NOTIFY_MAX_RETRIES: int = 3
    NOTIFY_RETRY_BACKOFF: int = 5          # seconds; exponential per attempt

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
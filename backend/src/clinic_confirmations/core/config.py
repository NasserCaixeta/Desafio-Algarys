from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class Settings(BaseSettings):
    """Validated configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Clinic Confirmations"
    app_version: str = "1.0.0"
    app_env: str = "development"
    timezone: str = Field(
        default="America/Sao_Paulo",
        validation_alias=AliasChoices("APP_TIMEZONE", "timezone"),
    )
    log_level: str = "INFO"
    log_json: bool = True

    api_host: str = "0.0.0.0"
    api_port: PositiveInt = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    max_upload_bytes: PositiveInt = 5 * 1024 * 1024
    dependency_timeout_seconds: PositiveInt = 2

    database_url: str = (
        "postgresql+psycopg://clinic:clinic_local_password@localhost:5433/clinic_confirmations"
    )
    redis_url: str = "redis://localhost:6380/0"
    celery_queue: str = "confirmations"
    celery_visibility_timeout_seconds: PositiveInt = 3600
    reconciliation_interval_seconds: PositiveInt = 5
    reconciliation_batch_size: PositiveInt = 100

    max_message_attempts: PositiveInt = 3
    retry_backoff_base_seconds: PositiveInt = 5
    retry_backoff_max_seconds: PositiveInt = 300
    processing_lease_seconds: PositiveInt = 120
    simulated_failure_suffixes: str = "0000"
    simulated_failure_attempts: NonNegativeInt = 1
    simulated_latency_ms: NonNegativeInt = 250

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def failure_suffix_list(self) -> tuple[str, ...]:
        return tuple(
            suffix.strip()
            for suffix in self.simulated_failure_suffixes.split(",")
            if suffix.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # backend/.env wins over the repo-root .env when both exist.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    environment: Literal["development", "staging", "production"] = "development"

    # Runtime connection. Must be a role WITHOUT superuser/BYPASSRLS that does
    # not own the tables, otherwise Row-Level Security is silently skipped.
    database_url: str
    # Owner connection, used only by Alembic.
    migration_database_url: str
    redis_url: str = "redis://localhost:6379/0"

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0)

    # How far a webhook's timestamp may be from our clock before it is refused.
    webhook_timestamp_tolerance_seconds: int = Field(default=300, gt=0)

    # Local hour (0-23) after which a hotel's previous day is audited.
    night_audit_hour: int = Field(default=3, ge=0, le=23)

    # Outbound availability pushes to channel managers.
    channel_outbound_timeout_seconds: float = Field(default=10, gt=0, le=60)
    # Nights from today sent by a full "sync now".
    channel_outbound_sync_days: int = Field(default=90, ge=1, le=366)
    # Local development only: lets outbound URLs use http and point at
    # localhost or private addresses. Refused in production (see below).
    channel_outbound_allow_private_hosts: bool = False

    # Channex.io. "mock" answers every call locally with Channex-shaped success
    # responses and sends nothing; "live" calls channex_base_url with the key.
    channex_mode: Literal["mock", "live"] = "mock"
    channex_base_url: str = "https://staging.channex.io/api/v1"
    channex_api_key: SecretStr | None = None
    channex_timeout_seconds: float = Field(default=15, gt=0, le=60)

    @model_validator(mode="after")
    def _no_private_outbound_hosts_in_production(self) -> Self:
        if self.environment == "production" and self.channel_outbound_allow_private_hosts:
            raise ValueError("CHANNEL_OUTBOUND_ALLOW_PRIVATE_HOSTS cannot be enabled in production")
        return self

    @model_validator(mode="after")
    def _channex_live_is_configured(self) -> Self:
        if self.channex_mode == "live":
            if self.channex_api_key is None or not self.channex_api_key.get_secret_value():
                raise ValueError("CHANNEX_API_KEY is required when CHANNEX_MODE=live")
            if not self.channex_base_url.startswith("https://"):
                raise ValueError("CHANNEX_BASE_URL must be an https URL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

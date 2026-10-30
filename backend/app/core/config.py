from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_SECRET_KEY = "hei-local-development-key-not-for-production-2026"


class Settings(BaseSettings):
    app_name: str = "Home Energy Intelligence"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = DEVELOPMENT_SECRET_KEY
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    database_url: str = "sqlite:///./hei_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    email_verification_expire_hours: int = 24
    password_reset_expire_minutes: int = 30
    frontend_base_url: str = "http://localhost:3000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_starttls: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        key_length = len(self.secret_key.encode("utf-8"))
        if key_length < 32:
            raise ValueError("SECRET_KEY must contain at least 32 bytes")
        if self.app_env.casefold() == "production" and self.secret_key == DEVELOPMENT_SECRET_KEY:
            raise ValueError("A unique SECRET_KEY must be configured in production")
        if not 5 <= self.password_reset_expire_minutes <= 120:
            raise ValueError("PASSWORD_RESET_EXPIRE_MINUTES must be between 5 and 120")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

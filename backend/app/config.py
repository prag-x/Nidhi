from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Development only. At least 32 bytes, as HS256 (RFC 7518 §3.2) requires; production refuses to start with it.
DEFAULT_SECRET = "dev-only-secret-change-me-before-any-real-deployment"


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables prefixed with NIDHI_."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NIDHI_", extra="ignore")

    app_name: str = "Nidhi"
    environment: str = "development"  # development | production | test
    database_url: str = "sqlite:///./nidhi.db"
    secret_key: str = DEFAULT_SECRET
    access_token_minutes: int = 480
    bcrypt_rounds: int = 12
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    upload_dir: str = "./uploads"
    # base64 of 32 random bytes; files are encrypted with it at rest (derived from secret_key when empty)
    file_key: str = ""
    file_key_file: str = ""   # or a file holding that base64 key (used by the one-container demo image)
    model_dir: str = "./models"
    # Address printed in letters' verification QR codes.
    public_base_url: str = "http://localhost:5173"
    static_dir: str | None = None  # built web app to serve from the API (single-container deployments)
    max_upload_mb: int = 10
    max_media_mb: int = 50
    # Shows demo accounts on the login screen. Turn off for any real deployment.
    demo_mode: bool = True
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 300
    log_level: str = "INFO"
    # Business calendar for receipt dates, timelines and reports.
    timezone: str = "Asia/Kolkata"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and settings.secret_key in (DEFAULT_SECRET, "replace-with-a-long-random-string"):
        raise RuntimeError("NIDHI_SECRET_KEY must be set in production")
    if len(settings.secret_key.encode()) < 32:
        raise RuntimeError(
            "NIDHI_SECRET_KEY is too short: use at least 32 characters, e.g. "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    return settings

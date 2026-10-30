from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_SECRET = "dev-only-secret-change-me"


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
    if settings.is_production and settings.secret_key == DEFAULT_SECRET:
        raise RuntimeError("NIDHI_SECRET_KEY must be set in production")
    return settings

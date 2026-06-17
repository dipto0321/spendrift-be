from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # project root


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Security
    secret_key: str = Field(min_length=32, alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # Database (PostgreSQL; SQLite is used only by the test suite)
    database_url: str = Field(alias="DATABASE_URL")

    # API
    api_v1_str: str = Field(default="/api/v1", alias="API_V1_STR")
    debug: bool = Field(default=False, alias="DEBUG")

    # Public sign-up kill switch: set false in deployments where new
    # accounts should not be created by anyone who finds the API.
    allow_registration: bool = Field(default=True, alias="ALLOW_REGISTRATION")

    # CORS - comma-separated list of allowed origins (no wildcard:
    # credentials are allowed, so origins must be explicit)
    cors_origins: str = Field(
        default="http://localhost:3000", alias="CORS_ORIGINS"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Storage (S3-compatible: Cloudflare R2, MinIO, Floci, etc.)
    storage_endpoint_url: str = Field(alias="STORAGE_ENDPOINT_URL")
    storage_access_key_id: str = Field(alias="STORAGE_ACCESS_KEY_ID")
    storage_secret_access_key: str = Field(alias="STORAGE_SECRET_ACCESS_KEY")
    storage_bucket_name: str = Field(alias="STORAGE_BUCKET_NAME")
    storage_presign_expiry: int = Field(default=86400, alias="STORAGE_PRESIGN_EXPIRY")
    storage_env: str = Field(default="dev", alias="STORAGE_ENV")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        # .env also holds compose-only variables (POSTGRES_*); ignore
        # keys that aren't part of these settings instead of crashing.
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]

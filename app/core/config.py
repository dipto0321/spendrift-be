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

    # Database
    database_url: str = Field(default="sqlite:///./app.db", alias="DATABASE_URL")

    # API
    api_v1_str: str = Field(default="/api/v1", alias="API_V1_STR")
    debug: bool = Field(default=False, alias="DEBUG")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8"
    )


settings = Settings()  # type: ignore[call-arg]

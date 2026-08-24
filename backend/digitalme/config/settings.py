"""Typed settings loaded from environment variables and the local .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    DeepSeek is optional so archive and browsing features remain fully local.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    app_name: str = "DigitalMe Memory Engine"
    environment: str = Field(default="development", validation_alias="DIGITALME_ENVIRONMENT")
    database_url: str = Field(
        default="sqlite:///./data/digitalme.db",
        validation_alias="DIGITALME_DATABASE_URL",
    )
    api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("API_KEY", "DEEPSEEK_API_KEY"),
    )
    api_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("API_BASE_URL", "DEEPSEEK_API_BASE_URL"),
    )

    @property
    def deepseek_configured(self) -> bool:
        """Return whether both required DeepSeek settings are available."""

        return self.api_key is not None and self.api_base_url is not None

    def ensure_local_directories(self) -> None:
        """Create parent directories required by a file-backed SQLite database."""

        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return
        database_path = self.database_url.removeprefix(prefix)
        if database_path == ":memory:" or database_path.startswith("file:"):
            return
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""

    return Settings()

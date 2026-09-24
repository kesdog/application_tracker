from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_env: str = "development"
    followup_delay_days: int = Field(default=7, ge=0, le=3650)
    max_followup_suggestions: int = Field(default=2, ge=0, le=100)
    app_data_dir: Path = PROJECT_ROOT / "data"
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = "info"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.lower()

    @field_validator("app_data_dir", mode="after")
    @classmethod
    def resolve_data_dir(cls, value: Path) -> Path:
        value = value.expanduser()
        return (PROJECT_ROOT / value).resolve() if not value.is_absolute() else value.resolve()

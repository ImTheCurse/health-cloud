"""Environment configuration.

Every field is required, so a missing variable
fails loudly at import time with a pydantic ValidationError naming it, rather
than silently running on a fallback value.

Variables belonging to later build steps are added by those steps, so the app
always boots against the environment it actually needs today.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str
    log_level: str
    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()

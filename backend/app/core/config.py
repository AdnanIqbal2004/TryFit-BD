"""Environment-backed settings for the TryFit BD backend."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration; secrets and local paths belong in the environment."""

    model_config = SettingsConfigDict(
        env_prefix="TRYFIT_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    storage_dir: Path = Path("./data/private")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    min_image_width: int = Field(default=256, gt=0)
    min_image_height: int = Field(default=256, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    retention_minutes: int = Field(default=45, gt=0)
    cleanup_interval_seconds: int = Field(default=60, gt=0)
    max_pending_jobs: int = Field(default=10, gt=0)
    database_url: str = "sqlite:///./data/tryfit.db"
    model_name: str = "unselected"
    device: str = "auto"

    @property
    def resolved_storage_dir(self) -> Path:
        """Resolve relative storage paths against the repository root, not the shell cwd."""

        if self.storage_dir.is_absolute():
            return self.storage_dir
        return PROJECT_ROOT / self.storage_dir


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for the current process."""

    return Settings()

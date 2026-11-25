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
    platform_setup_token: str = ""
    app_base_url: str = "http://127.0.0.1:5173"
    session_days: int = Field(default=14, ge=1, le=90)
    verification_minutes: int = Field(default=30, ge=5, le=1440)
    password_reset_minutes: int = Field(default=30, ge=5, le=1440)
    invitation_days: int = Field(default=7, ge=1, le=30)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = "TryFit BD <no-reply@tryfitbd.local>"
    smtp_starttls: bool = True
    model_name: str = "unselected"
    device: str = "auto"
    catvton_source: Path | None = None
    catvton_width: int = Field(default=576, ge=256, le=768, multiple_of=8)
    catvton_height: int = Field(default=768, ge=256, le=1024, multiple_of=8)
    catvton_steps: int = Field(default=25, ge=1, le=50)

    @property
    def resolved_storage_dir(self) -> Path:
        """Resolve relative storage paths against the repository root, not the shell cwd."""

        if self.storage_dir.is_absolute():
            return self.storage_dir
        return PROJECT_ROOT / self.storage_dir

    @property
    def resolved_database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("This build currently supports sqlite:/// database URLs only.")
        path = Path(self.database_url[len(prefix):])
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for the current process."""

    return Settings()

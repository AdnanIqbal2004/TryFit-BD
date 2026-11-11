"""Private, temporary storage for user uploads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from app.core.config import Settings


class UploadNotFoundError(Exception):
    """Raised when an upload ID does not identify a stored upload."""


def ensure_private_root(settings: Settings) -> Path:
    root = settings.resolved_storage_dir
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        # Windows ACLs do not map cleanly to POSIX mode bits; keep the directory non-public.
        pass
    return root


def store_person_image(settings: Settings, image_bytes: bytes, extension: str) -> tuple[str, datetime]:
    """Create an unguessable upload directory and store a sanitized image under a fixed name."""

    root = ensure_private_root(settings)
    upload_id = str(uuid4())
    upload_dir = root / upload_id
    upload_dir.mkdir(mode=0o700)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(minutes=settings.retention_minutes)
    try:
        marker = upload_dir / ".created_at"
        marker.write_text(created_at.isoformat(), encoding="ascii")
        image_path = upload_dir / f"person{extension}"
        with image_path.open("xb") as image_file:
            image_file.write(image_bytes)
        try:
            os.chmod(marker, 0o600)
            os.chmod(image_path, 0o600)
        except OSError:
            pass
    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    return upload_id, expires_at


def store_job_inputs(
    settings: Settings,
    person_bytes: bytes,
    person_extension: str,
    garment_bytes: bytes,
    garment_extension: str,
) -> tuple[str, Path, datetime]:
    """Store both sanitized job images in one private, expiring UUID directory."""

    root = ensure_private_root(settings)
    job_id = str(uuid4())
    job_dir = root / job_id
    job_dir.mkdir(mode=0o700)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(minutes=settings.retention_minutes)
    try:
        marker = job_dir / ".created_at"
        marker.write_text(created_at.isoformat(), encoding="ascii")
        person_path = job_dir / f"person{person_extension}"
        garment_path = job_dir / f"garment{garment_extension}"
        for image_path, image_bytes in (
            (person_path, person_bytes),
            (garment_path, garment_bytes),
        ):
            with image_path.open("xb") as image_file:
                image_file.write(image_bytes)
            try:
                os.chmod(image_path, 0o600)
            except OSError:
                pass
        try:
            os.chmod(marker, 0o600)
        except OSError:
            pass
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return job_id, job_dir, expires_at


def _directory_for_id(settings: Settings, upload_id: str) -> Path:
    try:
        canonical_id = str(UUID(upload_id))
    except (ValueError, AttributeError) as exc:
        raise UploadNotFoundError from exc
    root = ensure_private_root(settings)
    upload_dir = root / canonical_id
    if upload_dir.is_symlink() or not upload_dir.is_dir():
        raise UploadNotFoundError
    return upload_dir


def delete_upload(settings: Settings, upload_id: str) -> None:
    upload_dir = _directory_for_id(settings, upload_id)
    shutil.rmtree(upload_dir)


def delete_expired_uploads(settings: Settings) -> int:
    """Remove expired upload directories using their immutable creation marker."""

    root = ensure_private_root(settings)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.retention_minutes)
    removed = 0
    for entry in root.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            continue
        try:
            canonical_id = str(UUID(entry.name))
            upload_dir = root / canonical_id
            marker = upload_dir / ".created_at"
            if marker.is_file() and not marker.is_symlink():
                created_at = datetime.fromisoformat(marker.read_text(encoding="ascii")).astimezone(timezone.utc)
            else:
                # Recover an orphaned directory left by an interruption during upload.
                created_at = datetime.fromtimestamp(upload_dir.stat().st_mtime, timezone.utc)
            if created_at <= cutoff:
                shutil.rmtree(upload_dir)
                removed += 1
        except (ValueError, OSError, UploadNotFoundError):
            # Ignore malformed or concurrently removed entries; never log user data.
            continue
    return removed

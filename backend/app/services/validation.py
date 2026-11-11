"""Validate and sanitize image uploads before any model processing."""

from __future__ import annotations

from io import BytesIO
import warnings

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings


class UploadValidationError(Exception):
    """An expected upload validation failure safe to show to the user."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


async def read_validated_image(upload: UploadFile, settings: Settings) -> tuple[bytes, str]:
    """Read within the configured limit, verify actual image content, and strip metadata."""

    if upload.size is not None and upload.size > settings.max_upload_bytes:
        raise UploadValidationError(
            f"Image is too large. Maximum size is {settings.max_upload_bytes // (1024 * 1024)} MB.",
            413,
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(64 * 1024, settings.max_upload_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise UploadValidationError(
                f"Image is too large. Maximum size is {settings.max_upload_bytes // (1024 * 1024)} MB.",
                413,
            )

    raw = b"".join(chunks)
    if not raw:
        raise UploadValidationError("The uploaded image is empty.", 400)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as probe:
                image_format = probe.format
                width, height = probe.size
                if image_format not in {"JPEG", "PNG"}:
                    raise UploadValidationError("Unsupported image content. Upload a JPG or PNG image.", 415)
                if width * height > settings.max_image_pixels:
                    raise UploadValidationError("Image dimensions are too large to process safely.", 413)
                if width < settings.min_image_width or height < settings.min_image_height:
                    raise UploadValidationError(
                        f"Image is too small. Minimum dimensions are {settings.min_image_width} x {settings.min_image_height} pixels.",
                        400,
                    )
                probe.verify()

            with Image.open(BytesIO(raw)) as source:
                clean = ImageOps.exif_transpose(source).convert("RGB")
                output = BytesIO()
                if image_format == "JPEG":
                    clean.save(output, format="JPEG", quality=95, optimize=True)
                    extension = ".jpg"
                else:
                    clean.save(output, format="PNG", optimize=True)
                    extension = ".png"
    except UploadValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UploadValidationError("The uploaded file is not a readable JPG or PNG image.", 415) from exc

    return output.getvalue(), extension

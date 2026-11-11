"""Ordinary image checks applied after model inference."""

from __future__ import annotations

from pathlib import Path
import warnings

from PIL import Image, ImageStat, UnidentifiedImageError


class OutputValidationError(Exception):
    """Raised when inference output is missing, unreadable, or blank."""


def validate_output_image(path: Path) -> None:
    """Require an actual readable, non-empty, non-uniform PNG or JPEG image."""

    if not path.is_file() or path.stat().st_size == 0:
        raise OutputValidationError("The model did not produce an image. Please try again.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as probe:
                if probe.format not in {"JPEG", "PNG"}:
                    raise OutputValidationError("The model returned an unsupported image format.")
                width, height = probe.size
                if width <= 0 or height <= 0:
                    raise OutputValidationError("The model returned an empty image.")
                probe.verify()
            with Image.open(path) as result:
                result.load()
                if max(ImageStat.Stat(result.convert("RGB")).stddev) < 1.0:
                    raise OutputValidationError("The generated image appears blank. Please try another input.")
    except OutputValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise OutputValidationError("The generated image could not be read. Please try again.") from exc

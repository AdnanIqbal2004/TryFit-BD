"""Shared fixtures for backend tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings


def make_image_bytes(size: tuple[int, int] = (512, 512), image_format: str = "JPEG") -> bytes:
    """Create a nonblank deterministic image for upload and output checks."""

    image = Image.new("RGB", size)
    pixels = image.load()
    width, height = size
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "private",
        max_upload_bytes=2 * 1024 * 1024,
        min_image_width=128,
        min_image_height=128,
        max_image_pixels=2_000_000,
        retention_minutes=45,
        cleanup_interval_seconds=1,
        max_pending_jobs=3,
    )


@pytest.fixture
def api_client(settings, monkeypatch):
    import app.api.uploads as uploads_api
    import app.main as main_module

    monkeypatch.setattr(uploads_api, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    with TestClient(main_module.app) as client:
        yield client

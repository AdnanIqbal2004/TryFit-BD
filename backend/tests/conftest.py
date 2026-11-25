"""Shared fixtures for backend tests."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import parse_qs, urlsplit

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
        database_url=f"sqlite:///{(tmp_path / 'tryfit.db').as_posix()}",
        catvton_source=None,
        env="development",
        smtp_host="",
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
    import app.api.auth as auth_api
    import app.api.uploads as uploads_api
    import app.main as main_module

    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(uploads_api, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    with TestClient(main_module.app) as client:
        yield client


def sign_in_account(client: TestClient, account_type: str = "merchant") -> dict:
    credentials = {"email": f"{account_type}@example.test", "password": "test-password-2026"}
    body = {**credentials, "full_name": "Test user", "account_type": account_type}
    if account_type == "merchant":
        body["business_name"] = "Test shop"
    registered = client.post("/api/auth/register", json=body)
    assert registered.status_code == 201, registered.text
    query = urlsplit(registered.json()["preview_url"]).fragment.partition("?")[2]
    verified = client.post("/api/auth/verify-email", json={"token": parse_qs(query)["token"][0]})
    assert verified.status_code == 200
    logged_in = client.post("/api/auth/login", json=credentials)
    assert logged_in.status_code == 200
    return logged_in.json()

"""HTTP-level tests for consent, image validation, private storage, and deletion."""

from __future__ import annotations

from io import BytesIO
import uuid

from PIL import Image

from app.services.storage import delete_expired_uploads, store_person_image
from tests.conftest import make_image_bytes


def test_health_endpoint(api_client):
    response = api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_requires_explicit_consent(api_client):
    response = api_client.post(
        "/api/uploads",
        files={"person_image": ("person.jpg", make_image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 400
    assert "Consent is required" in response.json()["detail"]


def test_upload_validates_real_format_and_sanitizes_filename(api_client, settings):
    response = api_client.post(
        "/api/uploads",
        data={"consent": "true"},
        files={"person_image": ("../../private-name.png", make_image_bytes(), "image/png")},
    )
    assert response.status_code == 201
    payload = response.json()
    upload_id = str(uuid.UUID(payload["upload_id"]))
    stored_dir = settings.resolved_storage_dir / upload_id
    assert stored_dir.is_dir()
    assert {path.name for path in stored_dir.iterdir()} == {".created_at", "person.jpg"}
    assert not (settings.resolved_storage_dir / "private-name.png").exists()
    assert payload["status"] == "uploaded"


def test_upload_rejects_unsupported_content(api_client):
    gif_buffer = BytesIO()
    Image.new("RGB", (256, 256), "red").save(gif_buffer, format="GIF")
    response = api_client.post(
        "/api/uploads",
        data={"consent": "true"},
        files={"person_image": ("looks-like-jpeg.jpg", gif_buffer.getvalue(), "image/jpeg")},
    )
    assert response.status_code == 415
    assert "JPG or PNG" in response.json()["detail"]


def test_upload_rejects_corrupt_image(api_client):
    response = api_client.post(
        "/api/uploads",
        data={"consent": "true"},
        files={"person_image": ("corrupt.jpg", b"not an image", "image/jpeg")},
    )
    assert response.status_code == 415


def test_upload_rejects_file_over_configured_size(api_client, settings):
    settings.max_upload_bytes = 1024
    response = api_client.post(
        "/api/uploads",
        data={"consent": "true"},
        files={"person_image": ("large.jpg", make_image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 413


def test_upload_rejects_tiny_image(api_client):
    response = api_client.post(
        "/api/uploads",
        data={"consent": "true"},
        files={"person_image": ("tiny.jpg", make_image_bytes((32, 32)), "image/jpeg")},
    )
    assert response.status_code == 400
    assert "Minimum dimensions" in response.json()["detail"]


def test_delete_upload_removes_private_files(api_client, settings):
    created = api_client.post(
        "/api/uploads",
        data={"consent": "true"},
        files={"person_image": ("person.jpg", make_image_bytes(), "image/jpeg")},
    )
    upload_id = created.json()["upload_id"]
    stored_dir = settings.resolved_storage_dir / upload_id
    assert stored_dir.exists()

    response = api_client.delete(f"/api/uploads/{upload_id}")
    assert response.status_code == 204
    assert not stored_dir.exists()


def test_delete_does_not_accept_path_traversal(api_client):
    response = api_client.delete("/api/uploads/..%2F..%2Foutside")
    assert response.status_code == 404


def test_expired_uploads_are_removed_by_retention_cleanup(settings):
    image_id, _expires_at = store_person_image(settings, make_image_bytes(), ".jpg")
    directory = settings.resolved_storage_dir / image_id
    marker = directory / ".created_at"
    from datetime import datetime, timedelta, timezone

    marker.write_text((datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), encoding="ascii")

    assert delete_expired_uploads(settings) == 1
    assert not directory.exists()

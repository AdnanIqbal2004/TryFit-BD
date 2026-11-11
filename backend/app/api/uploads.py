"""Consent-gated temporary upload and immediate deletion endpoints."""

import asyncio
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.storage import UploadNotFoundError, delete_upload, store_person_image
from app.services.validation import UploadValidationError, read_validated_image

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


class UploadCreated(BaseModel):
    upload_id: str
    status: str
    expires_at: datetime


@router.post("", response_model=UploadCreated, status_code=status.HTTP_201_CREATED)
async def create_upload(
    consent: bool = Form(default=False),
    person_image: UploadFile = File(...),
) -> UploadCreated:
    """Validate consent and image content before storing a temporary person photo."""

    if consent is not True:
        raise HTTPException(status_code=400, detail="Consent is required before the image can be processed.")

    settings = get_settings()
    try:
        clean_bytes, extension = await read_validated_image(person_image, settings)
        upload_id, expires_at = await asyncio.to_thread(
            store_person_image, settings, clean_bytes, extension
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        await person_image.close()

    return UploadCreated(upload_id=upload_id, status="uploaded", expires_at=expires_at)


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_upload(upload_id: str) -> Response:
    """Delete an upload immediately; the UUID is the only lookup key."""

    try:
        delete_upload(get_settings(), upload_id)
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Upload was not found or has already expired.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

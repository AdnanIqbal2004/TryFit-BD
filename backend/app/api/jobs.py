"""Consent-gated virtual try-on jobs and private result delivery."""

from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.job_manager import JobManager, JobNotFoundError, JobQueueFullError, JobSnapshot
from app.services.validation import UploadValidationError, read_validated_image
from app.core.security import CurrentActor, current_actor

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobCreated(BaseModel):
    job_id: str
    status: str
    expires_at: datetime


class JobStatus(BaseModel):
    job_id: str
    status: str
    error_message: str | None
    expires_at: datetime
    processing_seconds: float | None


def _manager(request: Request) -> JobManager:
    return request.app.state.job_manager

def _actor(request: Request) -> CurrentActor:
    return current_actor(request)


def _response(snapshot: JobSnapshot) -> JobStatus:
    return JobStatus(
        job_id=snapshot.job_id,
        status=snapshot.status,
        error_message=snapshot.error_message,
        expires_at=snapshot.expires_at,
        processing_seconds=snapshot.processing_seconds,
    )


@router.post("", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    request: Request,
    consent: bool = Form(default=False),
    category: str = Form(default="upper"),
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
) -> JobCreated:
    """Validate both images and enqueue one temporary try-on request."""
    if consent is not True:
        raise HTTPException(status_code=400, detail="Consent is required before images can be processed.")
    if category != "upper":
        raise HTTPException(status_code=400, detail="This demo supports upper-body garments only.")
    settings = get_settings()
    actor = _actor(request)
    try:
        person_bytes, person_ext = await read_validated_image(person_image, settings)
        garment_bytes, garment_ext = await read_validated_image(garment_image, settings)
        snapshot = await _manager(request).submit(
            person_bytes, person_ext, garment_bytes, garment_ext, category, actor.organization_id
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except JobQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    finally:
        await person_image.close()
        await garment_image.close()
    return JobCreated(job_id=snapshot.job_id, status=snapshot.status, expires_at=snapshot.expires_at)


@router.get("/history")
def job_history(request: Request):
    actor = _actor(request)
    return {"jobs": request.app.state.saas_store.list_jobs(actor.organization_id), "usage": request.app.state.saas_store.usage_summary(actor.organization_id)}

@router.get("/{job_id}", response_model=JobStatus)
def get_job(request: Request, job_id: str) -> JobStatus:
    try:
        return _response(_manager(request).get_status(job_id, _actor(request).organization_id))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job was not found or has expired.") from exc


@router.get("/{job_id}/result")
def get_result(request: Request, job_id: str) -> FileResponse:
    try:
        path = _manager(request).get_result_path(job_id, _actor(request).organization_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="A completed result is not available.") from exc
    return FileResponse(path, media_type="image/png", filename="tryfit-preview.png", headers={"Cache-Control": "no-store"})


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(request: Request, job_id: str) -> Response:
    try:
        await _manager(request).delete(job_id, _actor(request).organization_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job was not found or has expired.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

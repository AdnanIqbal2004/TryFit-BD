"""FIFO, single-worker job manager for memory-limited local inference."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
from typing import Literal

from app.ai.engine import ModelUnavailableError, TryOnEngine
from app.ai.output_check import OutputValidationError, validate_output_image
from app.core.config import Settings
from app.services.storage import store_job_inputs

logger = logging.getLogger(__name__)
JobState = Literal["waiting", "processing", "done", "failed"]


class JobQueueFullError(Exception):
    """Raised when the configured pending-job limit has been reached."""


class JobNotFoundError(Exception):
    """Raised when a job is unknown or its temporary data has expired."""


@dataclass(slots=True)
class JobRecord:
    job_id: str
    job_dir: Path
    person_path: Path
    garment_path: Path
    category: str
    created_at: datetime
    expires_at: datetime
    status: JobState = "waiting"
    error_message: str | None = None
    result_path: Path | None = None
    processing_seconds: float | None = None
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: str
    status: JobState
    error_message: str | None
    expires_at: datetime
    processing_seconds: float | None


class JobManager:
    """Run inference serially and keep only temporary in-memory job state."""

    def __init__(self, settings: Settings, engine: TryOnEngine) -> None:
        self._settings = settings
        self._engine = engine
        self._queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=settings.max_pending_jobs)
        self._jobs: dict[str, JobRecord] = {}
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker(), name="tryfit-inference-worker")

    async def shutdown(self) -> None:
        task = self._worker_task
        if task is None:
            return
        await self._queue.put(None)
        await task
        self._worker_task = None

    async def submit(
        self,
        person_bytes: bytes,
        person_extension: str,
        garment_bytes: bytes,
        garment_extension: str,
        category: str,
    ) -> JobSnapshot:
        if self._worker_task is None or self._worker_task.done():
            await self.start()
        if self._queue.full():
            raise JobQueueFullError("The try-on queue is full. Please try again shortly.")

        job_id, job_dir, expires_at = await asyncio.to_thread(
            store_job_inputs,
            self._settings,
            person_bytes,
            person_extension,
            garment_bytes,
            garment_extension,
        )
        person_path = next(job_dir.glob("person.*"))
        garment_path = next(job_dir.glob("garment.*"))
        record = JobRecord(
            job_id=job_id,
            job_dir=job_dir,
            person_path=person_path,
            garment_path=garment_path,
            category=category,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )
        self._jobs[job_id] = record
        try:
            self._queue.put_nowait(job_id)
        except asyncio.QueueFull as exc:
            self._jobs.pop(job_id, None)
            await asyncio.to_thread(shutil.rmtree, job_dir, True)
            raise JobQueueFullError("The try-on queue is full. Please try again shortly.") from exc
        return self._snapshot(record)

    def get_status(self, job_id: str) -> JobSnapshot:
        record = self._get_record(job_id)
        return self._snapshot(record)

    def get_result_path(self, job_id: str) -> Path:
        record = self._get_record(job_id)
        if record.status != "done" or record.result_path is None:
            raise JobNotFoundError("A completed result is not available for this job.")
        return record.result_path

    async def delete(self, job_id: str) -> None:
        record = self._get_record(job_id)
        record.deleted = True
        await asyncio.to_thread(shutil.rmtree, record.job_dir, True)
        if record.status == "waiting":
            self._jobs.pop(record.job_id, None)

    def _get_record(self, job_id: str) -> JobRecord:
        record = self._jobs.get(job_id)
        if record is None or record.deleted or not record.job_dir.is_dir():
            self._jobs.pop(job_id, None)
            raise JobNotFoundError("Job was not found or has expired.")
        if datetime.now(timezone.utc) >= record.expires_at:
            self._jobs.pop(job_id, None)
            raise JobNotFoundError("Job was not found or has expired.")
        return record

    @staticmethod
    def _snapshot(record: JobRecord) -> JobSnapshot:
        return JobSnapshot(
            job_id=record.job_id,
            status=record.status,
            error_message=record.error_message,
            expires_at=record.expires_at,
            processing_seconds=record.processing_seconds,
        )

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                if job_id is None:
                    return
                record = self._jobs.get(job_id)
                if record is None or record.deleted:
                    continue
                record.status = "processing"
                started = asyncio.get_running_loop().time()
                success = False
                try:
                    result_path = await asyncio.to_thread(
                        self._engine.generate,
                        record.person_path,
                        record.garment_path,
                        record.category,
                        record.job_dir / "result.png",
                    )
                    expected_dir = record.job_dir.resolve()
                    resolved_result = Path(result_path).resolve()
                    if expected_dir not in resolved_result.parents:
                        raise OutputValidationError("The model returned an invalid result location.")
                    validate_output_image(resolved_result)
                    if record.deleted:
                        continue
                    record.result_path = resolved_result
                    record.status = "done"
                    record.error_message = None
                    success = True
                except ModelUnavailableError as exc:
                    record.status = "failed"
                    record.error_message = str(exc)
                except OutputValidationError as exc:
                    record.status = "failed"
                    record.error_message = str(exc)
                    logger.warning("AI output rejected for job %s", record.job_id)
                except Exception as exc:
                    record.status = "failed"
                    if "out of memory" in str(exc).lower() or "outofmemory" in type(exc).__name__.lower():
                        record.error_message = "The GPU ran out of memory. Try again later with a supported image."
                    else:
                        record.error_message = "Try-on generation failed. Please try again later."
                    logger.exception("AI job failed (job_id=%s)", record.job_id)
                finally:
                    record.processing_seconds = asyncio.get_running_loop().time() - started
                    logger.info(
                        "AI job finished job_id=%s model=%s device=%s category=%s settings=%s success=%s duration_seconds=%.3f",
                        record.job_id,
                        self._engine.model_name,
                        self._engine.device,
                        record.category,
                        self._engine.run_settings,
                        success,
                        record.processing_seconds,
                    )
                    if record.deleted:
                        await asyncio.to_thread(shutil.rmtree, record.job_dir, True)
                        self._jobs.pop(record.job_id, None)
            finally:
                self._queue.task_done()

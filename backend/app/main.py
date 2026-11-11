"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.uploads import router as uploads_router
from app.ai.engine import UnconfiguredTryOnEngine
from app.core.config import get_settings
from app.services.job_manager import JobManager
from app.services.retention import retention_cleanup_loop
from app.services.storage import ensure_private_root


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await asyncio.to_thread(ensure_private_root, settings)
    job_manager = JobManager(settings, UnconfiguredTryOnEngine())
    await job_manager.start()
    app.state.job_manager = job_manager
    cleanup_task = asyncio.create_task(retention_cleanup_loop(settings))
    app.state.retention_cleanup_task = cleanup_task
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        await job_manager.shutdown()


app = FastAPI(title="TryFit BD", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(uploads_router)
app.include_router(jobs_router)

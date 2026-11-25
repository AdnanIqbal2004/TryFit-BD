"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.uploads import router as uploads_router
from app.api.auth import router as auth_router
from app.api.workspace import router as workspace_router
from app.api.platform import router as platform_router
from app.ai.catvton import CatVTONEngine
from app.ai.engine import UnconfiguredTryOnEngine
from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.services.job_manager import JobManager
from app.services.retention import retention_cleanup_loop
from app.services.storage import ensure_private_root
from app.services.saas_store import SaaSStore


def create_engine(settings: Settings) -> CatVTONEngine | UnconfiguredTryOnEngine:
    if settings.catvton_source is None:
        return UnconfiguredTryOnEngine()
    return CatVTONEngine(
        settings.catvton_source,
        settings.catvton_width,
        settings.catvton_height,
        settings.catvton_steps,
        settings.device,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await asyncio.to_thread(ensure_private_root, settings)
    app.state.saas_store = SaaSStore(settings.resolved_database_path)
    engine = create_engine(settings)
    app.state.tryon_engine = engine
    job_manager = JobManager(settings, engine, app.state.saas_store)
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
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(platform_router)


# Serve the production UI and API together when a frontend build is available.
frontend = PROJECT_ROOT / "frontend" / "dist"
if (frontend / "index.html").is_file():
    @app.get("/", include_in_schema=False)
    def serve_homepage():
        return FileResponse(frontend / "index.html")

    @app.get("/favicon.svg", include_in_schema=False)
    def serve_favicon():
        return FileResponse(frontend / "favicon.svg")

    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="frontend-assets")

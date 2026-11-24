"""Basic application liveness endpoint."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, str | bool]:
    engine = request.app.state.tryon_engine
    return {"status": "ok", "model_available": bool(getattr(engine, "model_available", False)), "model_name": str(getattr(engine, "model_name", "unselected")), "device": str(getattr(engine, "runtime", getattr(engine, "device", "unconfigured"))), "message": ""}

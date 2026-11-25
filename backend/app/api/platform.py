"""Read-only, platform-wide reporting for the configured owner."""

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.core.security import SESSION_COOKIE, token_digest
from app.services.saas_store import SaaSStore

router = APIRouter(prefix="/api/platform", tags=["platform owner"])


@router.get("/overview")
def overview(request: Request, response: Response, page: int = Query(default=1, ge=1, le=1_000_000)):
    store: SaaSStore = request.app.state.saas_store
    session = request.cookies.get(SESSION_COOKIE)
    user = store.get_session_user(token_digest(session)) if session else None
    if not user or not user["email_verified_at"]:
        raise HTTPException(401, "Sign in with a verified account to continue.")
    if not user["is_platform_owner"]:
        raise HTTPException(403, "This dashboard is only available to the platform owner.")
    response.headers["Cache-Control"] = "no-store"
    return store.platform_overview(page=page, page_size=20)

"""Workspace-scoped merchant dashboard and management actions."""
from datetime import datetime, timedelta, timezone
import re
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.security import CurrentActor, current_actor, new_token, require_manager, token_digest
from app.services.email import action_link, send_action_email
from app.services.saas_store import SaaSStore

router = APIRouter(prefix="/api/workspace", tags=["merchant workspace"])

class StoreBody(BaseModel):
    provider: str
    display_name: str = Field(min_length=2, max_length=100)
    store_domain: str = Field(min_length=3, max_length=253)
class ApiKeyBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
class InviteBody(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    role: str = "member"
def _store(request: Request) -> SaaSStore:
    return request.app.state.saas_store
def _actor(request: Request) -> CurrentActor:
    return current_actor(request)

@router.get("")
def dashboard(request: Request):
    actor, store = _actor(request), _store(request)
    return {"user": {"id": actor.user_id, "full_name": actor.full_name, "email": actor.email}, "workspace": {"id": actor.organization_id, "name": actor.organization_name, "slug": actor.organization_slug, "role": actor.role}, "workspaces": store.organizations_for_user(actor.user_id), "members": store.list_members(actor.organization_id), "invitations": store.list_invitations(actor.organization_id), "stores": store.list_stores(actor.organization_id), "api_keys": store.list_api_keys(actor.organization_id), "jobs": store.list_jobs(actor.organization_id), "usage": store.usage_summary(actor.organization_id)}

@router.post("/stores", status_code=201)
def add_store(body: StoreBody, request: Request):
    actor, store = _actor(request), _store(request)
    require_manager(actor)
    provider = body.provider.lower()
    domain = body.store_domain.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
    if provider not in {"shopify", "woocommerce", "custom"} or not re.fullmatch(r"[a-z0-9.-]+(?::\d{1,5})?", domain):
        raise HTTPException(422, "Choose a supported provider and enter a valid store domain.")
    try:
        return store.add_store(actor.organization_id, provider, body.display_name, domain)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(409, "This store is already listed in this workspace.") from exc
        raise

@router.delete("/stores/{store_id}", status_code=204)
def delete_store(store_id: str, request: Request):
    actor = _actor(request)
    require_manager(actor)
    if not _store(request).delete_store(actor.organization_id, store_id):
        raise HTTPException(404, "Store was not found.")

@router.post("/api-keys", status_code=201)
def create_api_key(body: ApiKeyBody, request: Request):
    actor, store = _actor(request), _store(request)
    require_manager(actor)
    raw = "tfbd_live_" + new_token()
    saved = store.create_api_key(actor.organization_id, actor.user_id, body.name, raw[:18] + "…", token_digest(raw))
    return {**saved, "secret": raw, "message": "Copy this key now. It will not be shown again."}

@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(key_id: str, request: Request):
    actor = _actor(request)
    require_manager(actor)
    if not _store(request).revoke_api_key(actor.organization_id, key_id):
        raise HTTPException(404, "API key was not found or already revoked.")

@router.post("/invitations", status_code=201)
def invite(body: InviteBody, request: Request):
    actor, store, settings = _actor(request), _store(request), get_settings()
    require_manager(actor)
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or body.role not in {"admin", "member"}:
        raise HTTPException(422, "Enter a valid email and choose admin or member access.")
    if body.role == "admin" and actor.role != "owner":
        raise HTTPException(403, "Only the workspace owner can invite an admin.")
    if any(m["email"].lower() == email for m in store.list_members(actor.organization_id)):
        raise HTTPException(409, "This person is already a workspace member.")
    raw = new_token()
    expires = datetime.now(timezone.utc) + timedelta(days=settings.invitation_days)
    store.create_invitation(actor.organization_id, email, body.role, token_digest(raw), expires.isoformat())
    link = action_link(settings, "accept-invite", raw)
    try:
        preview = send_action_email(settings, email, f"Join {actor.organization_name} on TryFit BD", link)
    except RuntimeError as exc:
        store.remove_invitation(actor.organization_id, email)
        raise HTTPException(503, str(exc)) from exc
    return {"message": "Invitation created.", "preview_url": preview, "email_sent": preview is None, "expires_at": expires.isoformat()}

@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: str, request: Request):
    actor, store = _actor(request), _store(request)
    require_manager(actor)
    target = next((m for m in store.list_members(actor.organization_id) if m["id"] == user_id), None)
    if not target:
        raise HTTPException(404, "Member was not found.")
    if target["role"] == "admin" and actor.role != "owner":
        raise HTTPException(403, "Only the owner can remove an admin.")
    if not store.revoke_member(actor.organization_id, user_id):
        raise HTTPException(403, "Workspace owners cannot be removed here.")

@router.delete("/invitations/{email}", status_code=204)
def cancel_invitation(email: str, request: Request):
    actor = _actor(request)
    require_manager(actor)
    if not _store(request).remove_invitation(actor.organization_id, email):
        raise HTTPException(404, "Invitation was not found.")

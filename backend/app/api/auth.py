"""Merchant registration, email verification, sessions, and recovery."""
from datetime import datetime, timedelta, timezone
import re

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import SESSION_COOKIE, current_actor, hash_password, new_token, token_digest, verify_password
from app.services.email import action_link, send_action_email
from app.services.saas_store import SaaSStore

router = APIRouter(prefix="/api/auth", tags=["merchant accounts"])

class RegisterBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    business_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)

class Credentials(BaseModel):
    email: str
    password: str

class EmailBody(BaseModel):
    email: str

class TokenBody(BaseModel):
    token: str

class PasswordBody(BaseModel):
    token: str
    password: str = Field(min_length=12, max_length=256)

class AcceptInviteBody(BaseModel):
    token: str
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    password: str | None = Field(default=None, min_length=12, max_length=256)

def _store(request: Request) -> SaaSStore:
    return request.app.state.saas_store

def _email(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise HTTPException(422, "Enter a valid email address.")
    return value

def _expiry(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()

def _session(request: Request, response: Response, user_id: str) -> None:
    settings = get_settings()
    raw = new_token()
    _store(request).create_session(token_digest(raw), user_id, (datetime.now(timezone.utc) + timedelta(days=settings.session_days)).isoformat())
    response.set_cookie(SESSION_COOKIE, raw, httponly=True, secure=settings.env.lower() != "development", samesite="lax", max_age=settings.session_days * 86400, path="/")

@router.post("/register", status_code=201)
def register(body: RegisterBody, request: Request):
    email, store, settings = _email(body.email), _store(request), get_settings()
    if store.get_user_by_email(email):
        raise HTTPException(409, "An account with this email already exists. Try signing in or resetting the password.")
    try:
        user, organization = store.create_account(full_name=body.full_name, business_name=body.business_name, email=email, password_hash=hash_password(body.password))
        raw = new_token()
        store.create_email_token(token_hash=token_digest(raw), purpose="verify", user_id=user["id"], email=email, expires_at=_expiry(settings.verification_minutes))
        preview = send_action_email(settings, email, "Verify your TryFit BD email", action_link(settings, "verify-email", raw))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"message": "Check your email for a verification link.", "preview_url": preview, "workspace": {"id": organization["id"], "name": organization["name"]}}

@router.post("/verify-email")
def verify_email(body: TokenBody, request: Request):
    token = _store(request).consume_email_token(token_hash=token_digest(body.token), purpose="verify")
    if not token:
        raise HTTPException(400, "This verification link is invalid or expired. Request another one.")
    _store(request).mark_email_verified(token["user_id"])
    return {"message": "Email verified. You can now sign in."}

@router.post("/resend-verification")
def resend_verification(body: EmailBody, request: Request):
    email, store, settings = _email(body.email), _store(request), get_settings()
    user, preview = store.get_user_by_email(email), None
    if user and not user["email_verified_at"]:
        raw = new_token()
        store.create_email_token(token_hash=token_digest(raw), purpose="verify", user_id=user["id"], email=email, expires_at=_expiry(settings.verification_minutes))
        try:
            preview = send_action_email(settings, email, "Verify your TryFit BD email", action_link(settings, "verify-email", raw))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
    return {"message": "If the account needs verification, a link has been sent.", "preview_url": preview}

@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    user = _store(request).get_user_by_email(_email(body.email))
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect.")
    if not user["email_verified_at"]:
        raise HTTPException(403, "Verify your email before signing in.")
    _session(request, response, user["id"])
    return {"user": {"id": user["id"], "full_name": user["full_name"], "email": user["email"]}, "workspaces": _store(request).organizations_for_user(user["id"])}

@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        _store(request).revoke_session(token_digest(raw))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=get_settings().env.lower() != "development", samesite="lax")
    response.status_code = 204
    return response

@router.get("/me")
def me(request: Request):
    actor = current_actor(request)
    return {"user": {"id": actor.user_id, "full_name": actor.full_name, "email": actor.email}, "workspaces": _store(request).organizations_for_user(actor.user_id)}

@router.post("/password-reset/request")
def request_password_reset(body: EmailBody, request: Request):
    email, store, settings = _email(body.email), _store(request), get_settings()
    user, preview = store.get_user_by_email(email), None
    if user and user["email_verified_at"]:
        raw = new_token()
        store.create_email_token(token_hash=token_digest(raw), purpose="reset", user_id=user["id"], email=email, expires_at=_expiry(settings.password_reset_minutes))
        try:
            preview = send_action_email(settings, email, "Reset your TryFit BD password", action_link(settings, "reset-password", raw))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
    return {"message": "If the account exists, a password reset link has been sent.", "preview_url": preview}

@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordBody, request: Request):
    token = _store(request).consume_email_token(token_hash=token_digest(body.token), purpose="reset")
    if not token:
        raise HTTPException(400, "This password reset link is invalid or expired.")
    _store(request).update_password(token["user_id"], hash_password(body.password))
    return {"message": "Password updated. Sign in with your new password."}

@router.post("/invitations/accept")
def accept_invitation(body: AcceptInviteBody, request: Request, response: Response):
    store, token_hash = _store(request), token_digest(body.token)
    actor = current_actor(request, required=False)
    if actor:
        org = store.accept_invitation(token_hash=token_hash, user_id=actor.user_id, email=actor.email)
        if not org:
            raise HTTPException(400, "This invitation is invalid, expired, or addressed to another account.")
        return {"message": "Invitation accepted.", "workspace": org}
    if not body.full_name or not body.password:
        raise HTTPException(422, "Enter your name and a password to accept this invitation.")
    accepted = store.accept_invitation_new_user(token_hash=token_hash, full_name=body.full_name, password_hash=hash_password(body.password))
    if not accepted:
        raise HTTPException(400, "This invitation is invalid, expired, or the email already has an account. Sign in first.")
    user, org = accepted
    _session(request, response, user["id"])
    return {"message": "Invitation accepted.", "workspace": org}

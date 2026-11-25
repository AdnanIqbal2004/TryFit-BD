"""Merchant registration, email verification, sessions, and recovery."""
from datetime import datetime, timedelta, timezone
import hmac
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import SESSION_COOKIE, current_actor, hash_password, new_token, token_digest, verify_password
from app.services.email import action_link, send_action_email
from app.services.saas_store import SaaSStore

router = APIRouter(prefix="/api/auth", tags=["merchant accounts"])
MIN_PASSWORD_LENGTH = 8

class RegisterBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    business_name: str | None = Field(default=None, max_length=120)
    account_type: Literal["merchant", "customer"] = "merchant"
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)

class Credentials(BaseModel):
    email: str
    password: str

class EmailBody(BaseModel):
    email: str

class TokenBody(BaseModel):
    token: str

class PasswordBody(BaseModel):
    token: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)

class PlatformSetupBody(PasswordBody):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)

class AcceptInviteBody(BaseModel):
    token: str
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=256)

def _store(request: Request) -> SaaSStore:
    return request.app.state.saas_store

def _session_payload(request: Request, user_id: str, full_name: str, email: str, *, platform_owner: bool = False) -> dict:
    return {
        "user": {"id": user_id, "full_name": full_name, "email": email},
        "workspaces": _store(request).organizations_for_user(user_id),
        "platform_owner": platform_owner,
    }

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
    name = body.full_name.strip()
    business_name = (body.business_name or "").strip()
    if len(name) < 2:
        raise HTTPException(422, "Enter your full name.")
    if body.account_type == "merchant" and len(business_name) < 2:
        raise HTTPException(422, "Enter your business name.")
    try:
        user, organization = store.create_account(
            full_name=name,
            business_name=business_name if body.account_type == "merchant" else "Personal fitting room",
            email=email,
            password_hash=hash_password(body.password),
            kind=body.account_type,
        )
        raw = new_token()
        store.create_email_token(token_hash=token_digest(raw), purpose="verify", user_id=user["id"], email=email, expires_at=_expiry(settings.verification_minutes))
        preview = send_action_email(settings, email, "Verify your TryFit BD email", action_link(settings, "verify-email", raw))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"message": "Check your email for a verification link.", "preview_url": preview, "workspace": {"id": organization["id"], "name": organization["name"], "kind": organization["kind"]}}

@router.post("/verify-email")
def verify_email(body: TokenBody, request: Request):
    token = _store(request).consume_email_token(token_hash=token_digest(body.token), purpose="verify")
    if not token:
        raise HTTPException(400, "This verification link is invalid or expired. Request another one.")
    _store(request).mark_email_verified(token["user_id"])
    return {"message": "Email verified. You can now sign in."}


@router.post("/platform-setup", status_code=201)
def setup_platform(body: PlatformSetupBody, request: Request):
    setup_token = get_settings().platform_setup_token
    if len(setup_token) < 32 or not hmac.compare_digest(body.token.encode(), setup_token.encode()):
        raise HTTPException(403, "The owner setup link is invalid or unavailable.")
    full_name = body.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(422, "Enter your full name.")
    store = _store(request)
    if not store.create_platform_owner(full_name, _email(body.email), hash_password(body.password)):
        raise HTTPException(409, "Owner setup is already complete or this email is already registered.")
    return {"message": "Owner account created. Sign in to open the dashboard."}

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

def _login(body: Credentials, request: Request, response: Response, *, platform_owner: bool):
    user = _store(request).get_user_by_email(_email(body.email))
    if not user or user["disabled_at"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect.")
    if not user["email_verified_at"]:
        raise HTTPException(403, "Verify your email before signing in.")
    if bool(user["is_platform_owner"]) != platform_owner:
        detail = "Sign in with your platform owner account." if platform_owner else "Use the owner sign-in page for this account."
        raise HTTPException(403, detail)
    _session(request, response, user["id"])
    return _session_payload(request, user["id"], user["full_name"], user["email"], platform_owner=platform_owner)


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    return _login(body, request, response, platform_owner=False)


@router.post("/platform-login")
def platform_login(body: Credentials, request: Request, response: Response):
    return _login(body, request, response, platform_owner=True)

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
    raw = request.cookies.get(SESSION_COOKIE)
    user = _store(request).get_session_user(token_digest(raw)) if raw else None
    if user and user["is_platform_owner"] and user["email_verified_at"]:
        return _session_payload(request, user["id"], user["full_name"], user["email"], platform_owner=True)
    actor = current_actor(request)
    return _session_payload(request, actor.user_id, actor.full_name, actor.email)

@router.post("/password-reset/request")
def request_password_reset(body: EmailBody, request: Request):
    email, store, settings = _email(body.email), _store(request), get_settings()
    user, preview = store.get_user_by_email(email), None
    if user and user["email_verified_at"] and (not user["is_platform_owner"] or settings.smtp_host):
        raw = new_token()
        store.create_email_token(token_hash=token_digest(raw), purpose="reset", user_id=user["id"], email=email, expires_at=_expiry(settings.password_reset_minutes))
        try:
            preview = send_action_email(settings, email, "Reset your TryFit BD password", action_link(settings, "reset-password", raw))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
    return {"message": "If the account exists, a password reset link has been sent.", "preview_url": preview}

@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordBody, request: Request):
    settings = get_settings()
    store = _store(request)
    token = store.consume_email_token(token_hash=token_digest(body.token), purpose="reset")
    user = store.get_user(token["user_id"]) if token else None
    if not user or (user["is_platform_owner"] and not settings.smtp_host):
        raise HTTPException(400, "This password reset link is invalid or expired.")
    store.update_password(user["id"], hash_password(body.password))
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

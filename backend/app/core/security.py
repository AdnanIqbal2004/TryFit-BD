"""Password, opaque token, session, and workspace authorization helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request, status

from app.services.saas_store import SaaSStore

PASSWORD_ITERATIONS = 600_000
SESSION_COOKIE = "tryfit_session"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(rounds_text)
        if rounds < 100_000 or rounds > 2_000_000:
            return False
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_text), rounds)
        return hmac.compare_digest(derived.hex(), digest_text)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True, slots=True)
class CurrentActor:
    user_id: str
    email: str
    full_name: str
    organization_id: str
    organization_name: str
    organization_slug: str
    role: str
    workspace_kind: str
    api_key_id: str | None = None

    @property
    def can_manage(self) -> bool:
        return self.workspace_kind == "merchant" and self.role in {"owner", "admin"}


def current_actor(request: Request, *, required: bool = True) -> CurrentActor | None:
    """Resolve a verified browser session or a private organization API key."""

    store: SaaSStore = request.app.state.saas_store
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        raw_key = authorization[7:].strip()
        api_key = store.get_api_key(token_digest(raw_key)) if raw_key else None
        if api_key:
            member = store.get_membership(api_key["created_by_user_id"], api_key["organization_id"])
            user = store.get_user(api_key["created_by_user_id"])
            if member and member["kind"] == "merchant" and user and user["email_verified_at"] and not user["disabled_at"]:
                store.touch_api_key(api_key["id"])
                return CurrentActor(
                    user_id=user["id"], email=user["email"], full_name=user["full_name"],
                    organization_id=member["organization_id"], organization_name=member["name"],
                    organization_slug=member["slug"], role=member["role"],
                    workspace_kind=member["kind"], api_key_id=api_key["id"],
                )

    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        user = store.get_session_user(token_digest(session_token))
        if user and user["email_verified_at"]:
            selected_org = request.headers.get("x-organization-id")
            member = store.get_membership(user["id"], selected_org)
            if member:
                return CurrentActor(
                    user_id=user["id"], email=user["email"], full_name=user["full_name"],
                    organization_id=member["organization_id"], organization_name=member["name"],
                    organization_slug=member["slug"], role=member["role"], workspace_kind=member["kind"],
                )
    if required:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in with a verified account to continue.")
    return None


def require_manager(actor: CurrentActor) -> None:
    if not actor.can_manage:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only workspace owners and admins can make this change.")

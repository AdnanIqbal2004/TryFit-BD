"""Persistent SQLite records for accounts, workspaces, integrations, and usage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterator
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SaaSStore:
    """Small transactional store for the local SaaS MVP; repositories can move to Postgres later."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level="DEFERRED")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    email_verified_at TEXT,
                    created_at TEXT NOT NULL,
                    disabled_at TEXT
                );
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'merchant' CHECK(kind IN ('merchant', 'customer'))
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('owner','admin','member')),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (organization_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS email_tokens (
                    token_hash TEXT PRIMARY KEY,
                    purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset','invite')),
                    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                    organization_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
                    email TEXT NOT NULL COLLATE NOCASE,
                    invited_role TEXT,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
                CREATE INDEX IF NOT EXISTS idx_email_tokens_email ON email_tokens(email, purpose);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    created_by_user_id TEXT NOT NULL REFERENCES users(id),
                    name TEXT NOT NULL,
                    prefix TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS store_connections (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL CHECK(provider IN ('shopify','woocommerce','custom')),
                    display_name TEXT NOT NULL,
                    store_domain TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'added' CHECK(status IN ('added','connected','disconnected')),
                    created_at TEXT NOT NULL,
                    UNIQUE(organization_id, store_domain)
                );
                CREATE TABLE IF NOT EXISTS tryon_jobs (
                    job_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    processing_seconds REAL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_org_created ON tryon_jobs(organization_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    job_id TEXT NOT NULL UNIQUE REFERENCES tryon_jobs(job_id) ON DELETE CASCADE,
                    units INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_usage_org_date ON usage_events(organization_id, created_at);
                """
            )
            # Existing local databases predate customer workspaces.
            db.execute("BEGIN IMMEDIATE")
            columns = {column["name"] for column in db.execute("PRAGMA table_info(organizations)")}
            if "kind" not in columns:
                db.execute(
                    "ALTER TABLE organizations ADD COLUMN kind TEXT NOT NULL DEFAULT 'merchant' "
                    "CHECK(kind IN ('merchant', 'customer'))"
                )
            user_columns = {column["name"] for column in db.execute("PRAGMA table_info(users)")}
            if "is_platform_owner" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN is_platform_owner INTEGER NOT NULL DEFAULT 0 CHECK(is_platform_owner IN (0, 1))")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_single_platform_owner ON users(is_platform_owner) WHERE is_platform_owner = 1")

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row is not None else None

    def create_account(self, *, full_name: str, business_name: str, email: str, password_hash: str, kind: str = "merchant") -> tuple[dict, dict]:
        user_id, organization_id = str(uuid.uuid4()), str(uuid.uuid4())
        now = utc_now()
        base_slug = "".join(c.lower() if c.isalnum() else "-" for c in business_name).strip("-")[:48] or "workspace"
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        with self._connection() as db:
            db.execute(
                "INSERT INTO users(id,full_name,email,password_hash,created_at) VALUES(?,?,?,?,?)",
                (user_id, full_name.strip(), email.lower().strip(), password_hash, now),
            )
            db.execute(
                "INSERT INTO organizations(id,name,slug,created_at,kind) VALUES(?,?,?,?,?)",
                (organization_id, business_name.strip(), slug, now, kind),
            )
            db.execute(
                "INSERT INTO memberships(organization_id,user_id,role,created_at) VALUES(?,?,?,?)",
                (organization_id, user_id, "owner", now),
            )
        return self.get_user(user_id), self.get_organization(organization_id)

    def get_user(self, user_id: str) -> dict | None:
        with self._connection() as db:
            return self._dict(db.execute("SELECT id,full_name,email,password_hash,email_verified_at,created_at,disabled_at,is_platform_owner FROM users WHERE id=?", (user_id,)).fetchone())

    def get_user_by_email(self, email: str) -> dict | None:
        with self._connection() as db:
            return self._dict(db.execute("SELECT id,full_name,email,password_hash,email_verified_at,created_at,disabled_at,is_platform_owner FROM users WHERE email=? COLLATE NOCASE", (email.lower().strip(),)).fetchone())

    def create_platform_owner(self, full_name: str, email: str, password_hash: str) -> bool:
        now = utc_now()
        try:
            with self._connection() as db:
                db.execute(
                    "INSERT INTO users(id,full_name,email,password_hash,email_verified_at,created_at,is_platform_owner) "
                    "VALUES(?,?,?,?,?,?,1)",
                    (str(uuid.uuid4()), full_name, email, password_hash, now, now),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def create_email_token(self, *, token_hash: str, purpose: str, email: str, expires_at: str, user_id: str | None = None, organization_id: str | None = None, invited_role: str | None = None) -> None:
        with self._connection() as db:
            if purpose == "invite":
                db.execute("UPDATE email_tokens SET consumed_at=? WHERE email=? COLLATE NOCASE AND purpose=? AND organization_id=? AND consumed_at IS NULL", (utc_now(), email.lower().strip(), purpose, organization_id))
            else:
                db.execute("UPDATE email_tokens SET consumed_at=? WHERE email=? COLLATE NOCASE AND purpose=? AND consumed_at IS NULL", (utc_now(), email.lower().strip(), purpose))
            db.execute(
                "INSERT INTO email_tokens(token_hash,purpose,user_id,organization_id,email,invited_role,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (token_hash, purpose, user_id, organization_id, email.lower().strip(), invited_role, expires_at, utc_now()),
            )

    def accept_invitation_new_user(self, *, token_hash: str, full_name: str, password_hash: str) -> tuple[dict, dict] | None:
        now = utc_now()
        with self._connection() as db:
            token = db.execute("SELECT * FROM email_tokens WHERE token_hash=? AND purpose='invite' AND consumed_at IS NULL AND expires_at>?", (token_hash, now)).fetchone()
            if token is None or db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (token['email'],)).fetchone():
                return None
            user_id = str(uuid.uuid4())
            db.execute("INSERT INTO users(id,full_name,email,password_hash,email_verified_at,created_at) VALUES(?,?,?,?,?,?)", (user_id, full_name.strip(), token['email'], password_hash, now, now))
            db.execute("INSERT INTO memberships(organization_id,user_id,role,created_at) VALUES(?,?,?,?)", (token['organization_id'], user_id, token['invited_role'], now))
            db.execute("UPDATE email_tokens SET consumed_at=? WHERE token_hash=?", (now, token_hash))
        return self.get_user(user_id), self.get_organization(token['organization_id'])

    def create_invitation(self, organization_id: str, email: str, role: str, token_hash: str, expires_at: str) -> None:
        self.create_email_token(token_hash=token_hash, purpose="invite", email=email, expires_at=expires_at, organization_id=organization_id, invited_role=role)

    def remove_invitation(self, organization_id: str, email: str) -> bool:
        with self._connection() as db:
            cur = db.execute("UPDATE email_tokens SET consumed_at=? WHERE organization_id=? AND email=? COLLATE NOCASE AND purpose='invite' AND consumed_at IS NULL", (utc_now(), organization_id, email))
            return cur.rowcount > 0

    def consume_email_token(self, *, token_hash: str, purpose: str) -> dict | None:
        now = utc_now()
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM email_tokens WHERE token_hash=? AND purpose=? AND consumed_at IS NULL AND expires_at>?",
                (token_hash, purpose, now),
            ).fetchone()
            if row is None:
                return None
            db.execute("UPDATE email_tokens SET consumed_at=? WHERE token_hash=?", (now, token_hash))
            return dict(row)

    def mark_email_verified(self, user_id: str) -> None:
        with self._connection() as db:
            db.execute("UPDATE users SET email_verified_at=COALESCE(email_verified_at, ?) WHERE id=?", (utc_now(), user_id))

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self._connection() as db:
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))

    def create_session(self, token_hash: str, user_id: str, expires_at: str) -> None:
        with self._connection() as db:
            db.execute("INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)", (token_hash, user_id, expires_at, utc_now()))

    def get_session_user(self, token_hash: str) -> dict | None:
        with self._connection() as db:
            row = db.execute(
                "SELECT u.id,u.full_name,u.email,u.email_verified_at,u.created_at,u.is_platform_owner,s.expires_at "
                "FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>? AND u.disabled_at IS NULL",
                (token_hash, utc_now()),
            ).fetchone()
            return self._dict(row)

    def revoke_session(self, token_hash: str) -> None:
        with self._connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def organizations_for_user(self, user_id: str) -> list[dict]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT o.id,o.name,o.slug,o.kind,m.role FROM organizations o JOIN memberships m ON m.organization_id=o.id "
                "WHERE m.user_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,o.name",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_organization(self, organization_id: str) -> dict | None:
        with self._connection() as db:
            return self._dict(db.execute("SELECT id,name,slug,created_at,kind FROM organizations WHERE id=?", (organization_id,)).fetchone())

    def platform_overview(self, *, page: int, page_size: int) -> dict:
        accounts = """
            WITH accounts AS (
                SELECT u.id, u.full_name, u.email, u.created_at,
                    u.email_verified_at IS NOT NULL AS verified,
                    CASE MIN(CASE o.kind WHEN 'customer' THEN 0 WHEN 'merchant' THEN 1 ELSE 2 END)
                        WHEN 0 THEN 'customer' WHEN 1 THEN 'merchant' ELSE 'unassigned'
                    END AS kind
                FROM users u
                LEFT JOIN memberships m ON m.user_id = u.id
                LEFT JOIN organizations o ON o.id = m.organization_id
                WHERE u.is_platform_owner = 0
                GROUP BY u.id
            )
        """
        with self._connection() as db:
            db.execute("BEGIN")
            counts = db.execute(accounts + """
                SELECT COUNT(*) AS total,
                    COUNT(CASE WHEN kind = 'customer' THEN 1 END) AS customers,
                    COUNT(CASE WHEN kind = 'merchant' THEN 1 END) AS merchants,
                    COUNT(CASE WHEN NOT verified THEN 1 END) AS unverified,
                    (SELECT COUNT(*) FROM organizations WHERE kind = 'merchant') AS merchant_workspaces,
                    (SELECT COUNT(*) FROM store_connections) AS stores,
                    (SELECT COUNT(*) FROM tryon_jobs) AS tryon_requests
                FROM accounts
            """).fetchone()
            rows = db.execute(accounts + """
                SELECT id, full_name, email, kind, verified, created_at FROM accounts
                ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?
            """, (page_size, (page - 1) * page_size)).fetchall()
        return {
            "counts": dict(counts),
            "accounts": [{**dict(row), "verified": bool(row["verified"])} for row in rows],
            "page": page,
            "page_size": page_size,
        }

    def get_membership(self, user_id: str, organization_id: str | None = None) -> dict | None:
        with self._connection() as db:
            if organization_id:
                row = db.execute(
                    "SELECT o.id AS organization_id,o.name,o.slug,o.kind,m.user_id,m.role FROM memberships m "
                    "JOIN organizations o ON o.id=m.organization_id WHERE m.user_id=? AND o.id=?",
                    (user_id, organization_id),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT o.id AS organization_id,o.name,o.slug,o.kind,m.user_id,m.role FROM memberships m "
                    "JOIN organizations o ON o.id=m.organization_id WHERE m.user_id=? "
                    "ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,o.name LIMIT 1",
                    (user_id,),
                ).fetchone()
            return self._dict(row)

    def list_members(self, organization_id: str) -> list[dict]:
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT u.id,u.full_name,u.email,m.role,m.created_at FROM memberships m JOIN users u ON u.id=m.user_id "
                "WHERE m.organization_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,u.full_name",
                (organization_id,),
            ).fetchall()]

    def list_invitations(self, organization_id: str) -> list[dict]:
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT email,invited_role AS role,expires_at,created_at FROM email_tokens "
                "WHERE organization_id=? AND purpose='invite' AND consumed_at IS NULL AND expires_at>? ORDER BY created_at DESC",
                (organization_id, utc_now()),
            ).fetchall()]

    def accept_invitation(self, *, token_hash: str, user_id: str, email: str) -> dict | None:
        now = utc_now()
        with self._connection() as db:
            token = db.execute(
                "SELECT * FROM email_tokens WHERE token_hash=? AND purpose='invite' AND consumed_at IS NULL AND expires_at>?",
                (token_hash, now),
            ).fetchone()
            if token is None or token["email"].lower() != email.lower():
                return None
            db.execute(
                "INSERT OR IGNORE INTO memberships(organization_id,user_id,role,created_at) VALUES(?,?,?,?)",
                (token["organization_id"], user_id, token["invited_role"], now),
            )
            db.execute("UPDATE email_tokens SET consumed_at=? WHERE token_hash=?", (now, token_hash))
            return dict(db.execute("SELECT id,name,slug,created_at,kind FROM organizations WHERE id=?", (token["organization_id"],)).fetchone())

    def revoke_member(self, organization_id: str, user_id: str) -> bool:
        with self._connection() as db:
            row = db.execute("SELECT role FROM memberships WHERE organization_id=? AND user_id=?", (organization_id, user_id)).fetchone()
            if row is None or row["role"] == "owner":
                return False
            db.execute("DELETE FROM memberships WHERE organization_id=? AND user_id=?", (organization_id, user_id))
            return True

    def add_store(self, organization_id: str, provider: str, display_name: str, store_domain: str) -> dict:
        store_id = str(uuid.uuid4())
        now = utc_now()
        with self._connection() as db:
            db.execute(
                "INSERT INTO store_connections(id,organization_id,provider,display_name,store_domain,status,created_at) VALUES(?,?,?,?,?,'added',?)",
                (store_id, organization_id, provider, display_name.strip(), store_domain.lower().strip(), now),
            )
            return dict(db.execute("SELECT id,provider,display_name,store_domain,status,created_at FROM store_connections WHERE id=?", (store_id,)).fetchone())

    def list_stores(self, organization_id: str) -> list[dict]:
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,provider,display_name,store_domain,status,created_at FROM store_connections WHERE organization_id=? ORDER BY created_at DESC",
                (organization_id,),
            ).fetchall()]

    def delete_store(self, organization_id: str, store_id: str) -> bool:
        with self._connection() as db:
            cur = db.execute("DELETE FROM store_connections WHERE organization_id=? AND id=?", (organization_id, store_id))
            return cur.rowcount > 0

    def create_api_key(self, organization_id: str, user_id: str, name: str, prefix: str, token_hash: str) -> dict:
        key_id = str(uuid.uuid4())
        with self._connection() as db:
            db.execute(
                "INSERT INTO api_keys(id,organization_id,created_by_user_id,name,prefix,token_hash,created_at) VALUES(?,?,?,?,?,?,?)",
                (key_id, organization_id, user_id, name.strip(), prefix, token_hash, utc_now()),
            )
            return dict(db.execute("SELECT id,name,prefix,created_at,last_used_at FROM api_keys WHERE id=?", (key_id,)).fetchone())

    def get_api_key(self, token_hash: str) -> dict | None:
        with self._connection() as db:
            row = db.execute(
                "SELECT id,organization_id,created_by_user_id,name,prefix FROM api_keys WHERE token_hash=? AND revoked_at IS NULL",
                (token_hash,),
            ).fetchone()
            return self._dict(row)

    def touch_api_key(self, key_id: str) -> None:
        with self._connection() as db:
            db.execute("UPDATE api_keys SET last_used_at=? WHERE id=? AND revoked_at IS NULL", (utc_now(), key_id))

    def list_api_keys(self, organization_id: str) -> list[dict]:
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,name,prefix,created_at,last_used_at FROM api_keys WHERE organization_id=? AND revoked_at IS NULL ORDER BY created_at DESC",
                (organization_id,),
            ).fetchall()]

    def revoke_api_key(self, organization_id: str, key_id: str) -> bool:
        with self._connection() as db:
            cur = db.execute("UPDATE api_keys SET revoked_at=? WHERE organization_id=? AND id=? AND revoked_at IS NULL", (utc_now(), organization_id, key_id))
            return cur.rowcount > 0

    def create_job(self, *, job_id: str, organization_id: str, category: str, status: str, expires_at: str) -> None:
        with self._connection() as db:
            db.execute(
                "INSERT INTO tryon_jobs(job_id,organization_id,category,status,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                (job_id, organization_id, category, status, utc_now(), expires_at),
            )

    def update_job(self, *, job_id: str, status: str, error_message: str | None = None, processing_seconds: float | None = None, record_usage: bool = False) -> None:
        with self._connection() as db:
            db.execute(
                "UPDATE tryon_jobs SET status=?,error_message=?,processing_seconds=COALESCE(?,processing_seconds) WHERE job_id=?",
                (status, error_message, processing_seconds, job_id),
            )
            if record_usage:
                row = db.execute("SELECT organization_id FROM tryon_jobs WHERE job_id=?", (job_id,)).fetchone()
                if row:
                    db.execute(
                        "INSERT OR IGNORE INTO usage_events(organization_id,job_id,units,created_at) VALUES(?,?,1,?)",
                        (row["organization_id"], job_id, utc_now()),
                    )

    def mark_job_deleted(self, job_id: str) -> None:
        with self._connection() as db:
            db.execute("UPDATE tryon_jobs SET deleted_at=? WHERE job_id=?", (utc_now(), job_id))

    def get_job(self, organization_id: str, job_id: str) -> dict | None:
        with self._connection() as db:
            return self._dict(db.execute(
                "SELECT job_id,organization_id,category,status,error_message,created_at,expires_at,processing_seconds "
                "FROM tryon_jobs WHERE organization_id=? AND job_id=? AND deleted_at IS NULL",
                (organization_id, job_id),
            ).fetchone())

    def list_jobs(self, organization_id: str, limit: int = 50) -> list[dict]:
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT job_id,category,status,error_message,created_at,expires_at,processing_seconds "
                "FROM tryon_jobs WHERE organization_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (organization_id, limit),
            ).fetchall()]

    def usage_summary(self, organization_id: str) -> dict:
        with self._connection() as db:
            month_start = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00+00:00")
            row = db.execute(
                "SELECT COUNT(*) AS this_month FROM usage_events WHERE organization_id=? AND created_at>=?",
                (organization_id, month_start),
            ).fetchone()
            total = db.execute("SELECT COUNT(*) AS total FROM usage_events WHERE organization_id=?", (organization_id,)).fetchone()
            return {"this_month": row["this_month"], "total": total["total"]}

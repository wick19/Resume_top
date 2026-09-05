from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from backend.db import cursor, init_db

TOKEN_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def register_user(email: str, password: str) -> dict:
    init_db()
    email = email.strip().lower()
    if "@" not in email or len(password) < 8:
        raise ValueError("Use a real email and a password of at least 8 characters.")
    with cursor() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise ValueError("That email is already registered.")
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, hash_password(password), _iso(_now())),
        )
        row = conn.execute(
            "SELECT id, email FROM users WHERE email = ?", (email,)
        ).fetchone()
    return {"id": row["id"], "email": row["email"]}


def login_user(email: str, password: str) -> tuple[dict, str]:
    init_db()
    email = email.strip().lower()
    with cursor() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise ValueError("Wrong email or password.")
        token = secrets.token_urlsafe(32)
        expires = _iso(_now() + timedelta(days=TOKEN_DAYS))
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, row["id"], expires),
        )
    return {"id": row["id"], "email": row["email"]}, token


def user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    init_db()
    with cursor() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.email, s.expires_at
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        return None
    if datetime.fromisoformat(row["expires_at"]) < _now():
        return None
    return {"id": row["id"], "email": row["email"]}


def logout_token(token: str | None) -> None:
    if not token:
        return
    with cursor() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_or_create_cli_user(email: str, password: str = "local-dev-password") -> dict:
    init_db()
    email = email.strip().lower()
    with cursor() as conn:
        row = conn.execute(
            "SELECT id, email FROM users WHERE email = ?", (email,)
        ).fetchone()
        if row:
            return {"id": row["id"], "email": row["email"]}
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, hash_password(password), _iso(_now())),
        )
        row = conn.execute(
            "SELECT id, email FROM users WHERE email = ?", (email,)
        ).fetchone()
    return {"id": row["id"], "email": row["email"]}


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:8]

"""Per-user fact bank storage.

Each user's uploaded resume is parsed into a fact bank and stored here. That
bank becomes the source of truth for every tailored resume we generate for
them. If a user has not uploaded anything yet, `effective_bank` falls back to
the bundled default (`data/fact_bank.json`) so the app still works.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.db import cursor, init_db
from backend.fact_bank import load_bank


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_user_bank(
    user_id: int,
    bank: dict[str, Any],
    source_name: str = "",
    mode: str = "heuristic",
) -> None:
    init_db()
    now = _now_iso()
    payload = json.dumps(bank)
    with cursor() as conn:
        conn.execute(
            """
            INSERT INTO fact_banks (user_id, data, source_name, mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                data = excluded.data,
                source_name = excluded.source_name,
                mode = excluded.mode,
                updated_at = excluded.updated_at
            """,
            (user_id, payload, source_name, mode, now, now),
        )


def load_user_bank(user_id: int | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    init_db()
    with cursor() as conn:
        row = conn.execute(
            "SELECT data FROM fact_banks WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["data"])
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    # Banks saved before a schema fix (e.g. missing "projects"/"roles" keys
    # from an older LLM extraction) must be healed on every read, not just
    # on the next upload, or every tailor attempt keeps hitting the same
    # incomplete record.
    from backend.resume_parser import normalize_bank

    return normalize_bank(data)


def user_bank_meta(user_id: int | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    init_db()
    with cursor() as conn:
        row = conn.execute(
            "SELECT source_name, mode, updated_at FROM fact_banks WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "source_name": row["source_name"],
        "mode": row["mode"],
        "updated_at": row["updated_at"],
    }


def effective_bank(user_id: int | None) -> dict[str, Any]:
    """The user's uploaded bank if present, otherwise the bundled default."""
    return load_user_bank(user_id) or load_bank()


def delete_user_bank(user_id: int) -> None:
    init_db()
    with cursor() as conn:
        conn.execute("DELETE FROM fact_banks WHERE user_id = ?", (user_id,))

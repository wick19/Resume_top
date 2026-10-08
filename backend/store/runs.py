"""One tailor at a time can outlive the browser tab that started it."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.store.db import cursor

_LOG_LIMIT = 80


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, default=str)


def _load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def abandon_running(reason: str) -> None:
    """A process restart kills the tailor thread. Do not leave those rows looking live."""
    with cursor() as conn:
        conn.execute(
            """
            UPDATE tailor_runs
            SET status = 'error', error = ?, updated_at = ?
            WHERE status = 'running'
            """,
            (reason, _now()),
        )


def stop_running(user_id: int, except_id: int | None = None) -> None:
    """Close every live tailor for this user. A stopped row is not an error and saves no PDF."""
    sql = """
        UPDATE tailor_runs
        SET status = 'stopped', message = 'Stopped', error = '', updated_at = ?
        WHERE user_id = ? AND status = 'running'
    """
    params: list[Any] = [_now(), user_id]
    if except_id is not None:
        sql += " AND id != ?"
        params.append(except_id)
    with cursor() as conn:
        conn.execute(sql, params)


def stop_run(user_id: int, run_id: int) -> bool:
    with cursor() as conn:
        cur = conn.execute(
            """
            UPDATE tailor_runs
            SET status = 'stopped', message = 'Stopped', error = '', updated_at = ?
            WHERE id = ? AND user_id = ? AND status = 'running'
            """,
            (_now(), run_id, user_id),
        )
        return cur.rowcount > 0


def is_running(run_id: int) -> bool:
    with cursor() as conn:
        row = conn.execute("SELECT status FROM tailor_runs WHERE id = ?", (run_id,)).fetchone()
    return bool(row and row["status"] == "running")


def create_run(user_id: int, company: str, role: str) -> int:
    stop_running(user_id)
    label = f"{company or 'Company'} — {role or 'Role'}"
    now = _now()
    with cursor() as conn:
        cur = conn.execute(
            """
            INSERT INTO tailor_runs (
                user_id, status, label, company, role, stage, message, pct, target,
                log_json, created_at, updated_at
            )
            VALUES (?, 'running', ?, ?, ?, 'parse', 'Starting…', 4, 97, '[]', ?, ?)
            """,
            (user_id, label, company or "", role or "", now, now),
        )
        return int(cur.lastrowid)


def record_event(run_id: int, event: dict[str, Any]) -> None:
    kind = event.get("type")
    if kind == "progress":
        _progress(run_id, event)
    elif kind == "result":
        _finish(run_id, event)
    elif kind == "error":
        _fail(run_id, str(event.get("detail") or "Tailor failed"))


def fail_run(run_id: int, detail: str) -> None:
    _fail(run_id, detail)


def _progress(run_id: int, event: dict[str, Any]) -> None:
    with cursor() as conn:
        row = conn.execute("SELECT log_json FROM tailor_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return
        log = _load(row["log_json"], [])
        message = str(event.get("message") or "")
        if message:
            log.append({"message": message, "stage": event.get("stage") or ""})
        log = log[-_LOG_LIMIT:]
        conn.execute(
            """
            UPDATE tailor_runs
            SET stage = ?, message = ?, pct = ?, score = ?, target = ?,
                log_json = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (
                event.get("stage") or "",
                message,
                int(event.get("pct") or 0),
                event.get("score"),
                event.get("target") or 97,
                _dump(log),
                _now(),
                run_id,
            ),
        )


def _finish(run_id: int, event: dict[str, Any]) -> None:
    audit = event.get("audit") or {}
    with cursor() as conn:
        conn.execute(
            """
            UPDATE tailor_runs
            SET status = 'done', stage = 'finalize', message = 'Ready', pct = 100,
                score = ?, target = ?, result_json = ?, error = '', updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (
                audit.get("ats_score"),
                audit.get("ats_target") or 97,
                _dump(event),
                _now(),
                run_id,
            ),
        )


def _fail(run_id: int, detail: str) -> None:
    with cursor() as conn:
        conn.execute(
            """
            UPDATE tailor_runs
            SET status = 'error', error = ?, message = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (detail, detail, _now(), run_id),
        )


def _public(row: Any) -> dict[str, Any]:
    result = _load(row["result_json"], None)
    return {
        "id": row["id"],
        "status": row["status"],
        "label": row["label"] or "",
        "company": row["company"] or "",
        "role": row["role"] or "",
        "stage": row["stage"] or "",
        "message": row["message"] or "",
        "pct": row["pct"] or 0,
        "score": row["score"],
        "target": row["target"] or 97,
        "log": _load(row["log_json"], []),
        "result": result,
        "error": row["error"] or "",
    }


def get_run(user_id: int, run_id: int) -> dict[str, Any] | None:
    with cursor() as conn:
        row = conn.execute(
            "SELECT * FROM tailor_runs WHERE id = ? AND user_id = ?",
            (run_id, user_id),
        ).fetchone()
    if not row:
        return None
    return _public(row)


def active_run(user_id: int) -> dict[str, Any] | None:
    with cursor() as conn:
        row = conn.execute(
            """
            SELECT * FROM tailor_runs
            WHERE user_id = ? AND status = 'running'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return _public(row)

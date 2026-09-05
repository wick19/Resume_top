from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.config import DB_PATH, OUTPUT_DIR, RETENTION_DAYS
from backend.logbook import LOG_PATH

STATUSES = ("pending", "kept", "deleted")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    dest = path or DB_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dest))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            url TEXT DEFAULT '',
            extractor TEXT DEFAULT 'paste',
            pdf_path TEXT NOT NULL,
            cover_letter_path TEXT DEFAULT '',
            output_dir TEXT NOT NULL,
            created_at TEXT NOT NULL,
            notify_after TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            decided_at TEXT,
            extra TEXT DEFAULT '{}'
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_apps_company ON applications(company, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_apps_notify ON applications(status, notify_after)"
    )
    conn.commit()
    return conn


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    try:
        item["extra"] = json.loads(item.get("extra") or "{}")
    except json.JSONDecodeError:
        item["extra"] = {}
    created = _parse(item["created_at"])
    item["age_days"] = (_now() - created).days
    item["due"] = item["status"] == "pending" and _now() >= _parse(item["notify_after"])
    return item


def save_application(entry: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    created = _now()
    notify = created + timedelta(days=RETENTION_DAYS)
    extra = {
        k: entry.get(k)
        for k in ("mode", "cover_mode", "interview", "gaps")
        if k in entry
    }
    with connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO applications (
                company, role, url, extractor, pdf_path, cover_letter_path,
                output_dir, created_at, notify_after, status, extra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                entry.get("company") or "company",
                entry.get("role") or "role",
                entry.get("url") or "",
                entry.get("extractor") or "paste",
                entry["pdf_path"],
                entry.get("cover_letter_path") or "",
                entry["output_dir"],
                _iso(created),
                _iso(notify),
                json.dumps(extra),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row(row)  # type: ignore[return-value]


def get_application(app_id: int, path: Path | None = None) -> dict[str, Any] | None:
    with connect(path) as conn:
        return _row(conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone())


def list_applications(
    company: str | None = None,
    status: str | None = None,
    limit: int = 100,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM applications WHERE 1=1"
    args: list[Any] = []
    if company:
        sql += " AND lower(company) = lower(?)"
        args.append(company)
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with connect(path) as conn:
        return [_row(r) for r in conn.execute(sql, args)]  # type: ignore[misc]


def due_notifications(path: Path | None = None) -> list[dict[str, Any]]:
    with connect(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM applications
            WHERE status = 'pending' AND notify_after <= ?
            ORDER BY notify_after ASC
            """,
            (_iso(_now()),),
        ).fetchall()
    return [_row(r) for r in rows]  # type: ignore[misc]


def keep_application(app_id: int, path: Path | None = None) -> dict[str, Any]:
    return _set_status(app_id, "kept", path=path)


def snooze_application(app_id: int, days: int | None = None, path: Path | None = None) -> dict[str, Any]:
    days = days if days is not None else RETENTION_DAYS
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            raise KeyError(f"application {app_id} not found")
        if row["status"] == "deleted":
            raise ValueError("cannot snooze a deleted resume")
        notify = _now() + timedelta(days=days)
        conn.execute(
            """
            UPDATE applications
            SET status = 'pending', notify_after = ?, decided_at = NULL
            WHERE id = ?
            """,
            (_iso(notify), app_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    return _row(updated)  # type: ignore[return-value]


def delete_application(app_id: int, path: Path | None = None) -> dict[str, Any]:
    item = get_application(app_id, path=path)
    if item is None:
        raise KeyError(f"application {app_id} not found")
    _remove_files(item.get("output_dir") or "")
    return _set_status(app_id, "deleted", path=path)


def _set_status(app_id: int, status: str, path: Path | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(status)
    with connect(path) as conn:
        row = conn.execute("SELECT id FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            raise KeyError(f"application {app_id} not found")
        conn.execute(
            "UPDATE applications SET status = ?, decided_at = ? WHERE id = ?",
            (status, _iso(_now()), app_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    return _row(updated)  # type: ignore[return-value]


def _remove_files(output_dir: str) -> None:
    if not output_dir:
        return
    folder = Path(output_dir).resolve()
    root = OUTPUT_DIR.resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        return
    if folder.exists() and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


def migrate_jsonl(path: Path | None = None) -> int:
    """One-time import of the old jsonl log if the sqlite store is empty."""
    jsonl = LOG_PATH
    if not jsonl.exists():
        return 0
    with connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        if count:
            return 0
    imported = 0
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not row.get("pdf_path") or not row.get("output_dir"):
            continue
        ts = row.get("ts")
        try:
            created = _parse(ts) if ts else _now()
        except ValueError:
            created = _now()
        notify = created + timedelta(days=RETENTION_DAYS)
        with connect(path) as conn:
            conn.execute(
                """
                INSERT INTO applications (
                    company, role, url, extractor, pdf_path, cover_letter_path,
                    output_dir, created_at, notify_after, status, extra
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    row.get("company") or "company",
                    row.get("role") or "role",
                    row.get("url") or "",
                    row.get("extractor") or "paste",
                    row["pdf_path"],
                    row.get("cover_letter_path") or "",
                    row["output_dir"],
                    _iso(created),
                    _iso(notify),
                    json.dumps(
                        {
                            k: row.get(k)
                            for k in ("mode", "cover_mode", "interview", "gaps")
                            if k in row
                        }
                    ),
                ),
            )
            conn.commit()
        imported += 1
    return imported

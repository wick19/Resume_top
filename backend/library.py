from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import REVIEW_DAYS
from backend.db import cursor, init_db


def _library_dir() -> Path:
    from backend import config

    return config.LIBRARY_DIR


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value or "item").strip("_")
    return (text[:60] or "item")


def _row(row) -> dict:
    created = datetime.fromisoformat(row["created_at"])
    next_review = datetime.fromisoformat(row["next_review_at"])
    now = _now()
    days_old = max(0, (now - created).days)
    due = row["status"] == "active" and next_review <= now
    days_until = (next_review - now).days
    match = re.search(r"_v(\d+)(?:_|$|\.)", row["pdf_path"] or "")
    version = int(match.group(1)) if match else 1
    return {
        "id": row["id"],
        "company": row["company"],
        "role": row["role"],
        "url": row["url"] or "",
        "status": row["status"],
        "created_at": row["created_at"],
        "next_review_at": row["next_review_at"],
        "last_reviewed_at": row["last_reviewed_at"],
        "days_old": days_old,
        "due": due,
        "days_until_review": days_until,
        "version": version,
        "label": f"{row['company']} — {row['role']} — v{version} — {days_old} days old",
        "prompt": (
            f"{row['company']} — {row['role']} — v{version} — {days_old} days old. Keep or delete?"
            if due
            else None
        ),
        "has_pdf": bool(row["pdf_path"]),
        "has_cover": bool(row["cover_path"]),
    }


def ingest_files(
    user_id: int,
    company: str,
    role: str,
    url: str,
    pdf_path: str,
    cover_path: str = "",
    jd_path: str = "",
    revision: int = 1,
) -> dict:
    init_db()
    now = _now()
    stamp = now.strftime("%Y-%m-%d")
    dest_dir = _library_dir() / str(user_id) / _slug(company)
    dest_dir.mkdir(parents=True, exist_ok=True)
    pdf_src = Path(pdf_path)
    stem = f"{stamp}_{_slug(role)}_v{revision}"
    pdf_dest = dest_dir / f"{stem}.pdf"
    shutil.copy2(pdf_src, pdf_dest)
    cover_dest = ""
    if cover_path and Path(cover_path).exists():
        cover_file = dest_dir / f"{stem}_cover.txt"
        shutil.copy2(cover_path, cover_file)
        cover_dest = str(cover_file)
    jd_dest = ""
    if jd_path and Path(jd_path).exists():
        jd_file = dest_dir / f"{stem}_jd.txt"
        shutil.copy2(jd_path, jd_file)
        jd_dest = str(jd_file)
    next_review = now + timedelta(days=REVIEW_DAYS)
    with cursor() as conn:
        cur = conn.execute(
            """
            INSERT INTO resumes (
                user_id, company, role, url, status, created_at, next_review_at,
                pdf_path, cover_path, jd_path
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                company,
                role,
                url or "",
                _iso(now),
                _iso(next_review),
                str(pdf_dest),
                cover_dest,
                jd_dest,
            ),
        )
        resume_id = cur.lastrowid
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    return _row(row)


def list_resumes(user_id: int, include_deleted: bool = False) -> list[dict]:
    init_db()
    sql = "SELECT * FROM resumes WHERE user_id = ?"
    args: list = [user_id]
    if not include_deleted:
        sql += " AND status != 'deleted'"
    sql += " ORDER BY company COLLATE NOCASE, created_at DESC"
    with cursor() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row(r) for r in rows]


def due_resumes(user_id: int) -> list[dict]:
    init_db()
    now = _iso(_now())
    with cursor() as conn:
        rows = conn.execute(
            """
            SELECT * FROM resumes
            WHERE user_id = ? AND status = 'active' AND next_review_at <= ?
            ORDER BY next_review_at ASC
            """,
            (user_id, now),
        ).fetchall()
    return [_row(r) for r in rows]


def get_resume(user_id: int, resume_id: int):
    init_db()
    with cursor() as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        ).fetchone()
    return row


def keep_resume(user_id: int, resume_id: int) -> dict:
    row = get_resume(user_id, resume_id)
    if not row or row["status"] == "deleted":
        raise KeyError("Resume not found")
    now = _now()
    nxt = now + timedelta(days=REVIEW_DAYS)
    with cursor() as conn:
        conn.execute(
            """
            UPDATE resumes
            SET last_reviewed_at = ?, next_review_at = ?, status = 'active'
            WHERE id = ? AND user_id = ?
            """,
            (_iso(now), _iso(nxt), resume_id, user_id),
        )
        updated = conn.execute(
            "SELECT * FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
    return _row(updated)


def delete_resume(user_id: int, resume_id: int) -> dict:
    row = get_resume(user_id, resume_id)
    if not row:
        raise KeyError("Resume not found")
    for key in ("pdf_path", "cover_path", "jd_path"):
        path = Path(row[key] or "")
        if path.exists() and path.is_file():
            path.unlink()
    now = _now()
    with cursor() as conn:
        conn.execute(
            """
            UPDATE resumes
            SET status = 'deleted', last_reviewed_at = ?, pdf_path = '', cover_path = '', jd_path = ''
            WHERE id = ? AND user_id = ?
            """,
            (_iso(now), resume_id, user_id),
        )
    return {
        "id": resume_id,
        "status": "deleted",
        "linkedin_hint": "If you uploaded this on LinkedIn Easy Apply, delete it from your resume list there too.",
    }


def file_for_download(user_id: int, resume_id: int, kind: str) -> Path:
    row = get_resume(user_id, resume_id)
    if not row or row["status"] == "deleted":
        raise KeyError("Resume not found")
    path = Path(row["pdf_path"] if kind != "cover" else row["cover_path"] or "")
    if not path.exists():
        raise FileNotFoundError("File is not on this server")
    return path

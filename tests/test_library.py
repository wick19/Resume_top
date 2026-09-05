from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.auth import get_or_create_cli_user
from backend.db import cursor, init_db
from backend.library import (
    delete_resume,
    due_resumes,
    ingest_files,
    keep_resume,
    list_resumes,
)


def _pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.7 test")
    return path


def test_keep_starts_a_new_7_day_cycle(tmp_path):
    init_db()
    user = get_or_create_cli_user("cycle@test.local")
    pdf = _pdf(tmp_path / "a.pdf")
    record = ingest_files(user["id"], "Acme", "AI Engineer", "", str(pdf))
    assert record["due"] is False
    past = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with cursor() as conn:
        conn.execute(
            "UPDATE resumes SET next_review_at = ? WHERE id = ?",
            (past, record["id"]),
        )
    due = due_resumes(user["id"])
    assert len(due) == 1
    assert "Keep or delete" in (due[0]["prompt"] or "")
    kept = keep_resume(user["id"], record["id"])
    assert kept["due"] is False
    assert due_resumes(user["id"]) == []


def test_delete_removes_file(tmp_path):
    init_db()
    user = get_or_create_cli_user("del@test.local")
    pdf = _pdf(tmp_path / "b.pdf")
    record = ingest_files(user["id"], "Infosys", "Backend", "", str(pdf))
    from backend.library import get_resume

    row = get_resume(user["id"], record["id"])
    stored_pdf = Path(row["pdf_path"])
    assert stored_pdf.exists()
    delete_resume(user["id"], record["id"])
    assert not stored_pdf.exists()
    assert list_resumes(user["id"]) == []

from __future__ import annotations

import json
from typing import Any

from backend.aligner import tailor
from backend.compiler import (
    cleanup_older_output,
    compile_resume,
    next_revision,
    output_folder,
    safe_pdf_name,
)
from backend.cover_letter import generate_cover_letter
from backend.logbook import append_application
from backend.schemas import Audit


def run_application(
    jd: str,
    target_role: str = "",
    company: str = "",
    url: str = "",
    extractor: str = "paste",
    rewrite: bool = True,
    cover_letter: bool = True,
    user_id: int | None = None,
) -> dict[str, Any]:
    doc, audit_raw = tailor(
        jd,
        target_role=target_role,
        company=company,
        rewrite=rewrite,
    )
    firm = (company or "company").strip()
    role = (target_role or "role").strip()
    revision = next_revision(firm, role)
    dest = output_folder(firm, role, revision)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "job_description.txt").write_text(jd, encoding="utf-8")
    (dest / "capture.json").write_text(
        json.dumps(
            {"url": url, "extractor": extractor, "company": firm, "role": role},
            indent=2,
        ),
        encoding="utf-8",
    )
    (dest / "audit.json").write_text(
        Audit(**audit_raw).model_dump_json(indent=2), encoding="utf-8"
    )
    filename = safe_pdf_name(firm, role, revision)
    pdf = compile_resume(doc, dest, filename)
    cleanup_older_output(firm, role, dest)

    cover_path = ""
    cover_mode = ""
    if cover_letter:
        letter, cover_mode = generate_cover_letter(
            jd, role, firm, doc, rewrite=rewrite
        )
        cover_file = dest / "cover_letter.txt"
        cover_file.write_text(letter.strip() + "\n", encoding="utf-8")
        cover_path = str(cover_file)

    log_path = append_application(
        {
            "company": firm,
            "role": role,
            "url": url,
            "extractor": extractor,
            "pdf_path": str(pdf),
            "cover_letter_path": cover_path,
            "output_dir": str(dest),
            "mode": audit_raw.get("mode"),
            "cover_mode": cover_mode,
            "interview": audit_raw.get("interview"),
            "gaps": audit_raw.get("gaps") or [],
        }
    )
    resume_id = None
    if user_id is not None:
        from backend.library import ingest_files

        record = ingest_files(
            user_id,
            firm,
            role,
            url,
            str(pdf),
            cover_path,
            str(dest / "job_description.txt"),
            revision=revision,
        )
        resume_id = record["id"]
    return {
        "status": "success",
        "output_dir": str(dest),
        "pdf_path": str(pdf),
        "cover_letter_path": cover_path,
        "log_path": str(log_path),
        "company": firm,
        "role": role,
        "url": url,
        "extractor": extractor,
        "audit": audit_raw,
        "resume_id": resume_id,
    }

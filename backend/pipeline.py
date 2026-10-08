from __future__ import annotations

import json
from typing import Any, Iterator

from backend.match.aligner import tailor, tailor_stream
from backend.match.ats import TARGET
from backend.resume.compiler import (
    cleanup_older_output,
    compile_resume,
    next_revision,
    output_folder,
    safe_pdf_name,
)
from backend.cover_letter import generate_cover_letter
from backend.store.logbook import append_application
from backend.schemas import Audit


def _finalize(
    doc: dict[str, Any],
    audit_raw: dict[str, Any],
    jd: str,
    target_role: str,
    company: str,
    url: str,
    extractor: str,
    cover_letter: bool,
    user_id: int | None,
    bank: dict[str, Any],
) -> dict[str, Any]:
    """Compile the PDF, write the cover letter + log, and store in the library.

    Shared by the blocking and streaming run paths so they cannot drift.
    """
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
            jd, role, firm, doc, rewrite=audit_raw.get("mode") == "rewrite", bank=bank
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
            "ats_score": audit_raw.get("ats_score"),
            "gaps": audit_raw.get("gaps") or [],
        }
    )

    resume_id = None
    if user_id is not None:
        from backend.store.library import ingest_files

        record = ingest_files(
            user_id, firm, role, url, str(pdf), cover_path,
            str(dest / "job_description.txt"), revision=revision,
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


def run_application(
    jd: str,
    target_role: str = "",
    company: str = "",
    url: str = "",
    extractor: str = "paste",
    rewrite: bool = True,
    cover_letter: bool = True,
    user_id: int | None = None,
    llm_provider: str = "",
) -> dict[str, Any]:
    from backend.llm.llm import using_provider
    from backend.resume.userbank import effective_bank

    chosen = (llm_provider or "").strip().lower()
    if chosen == "select":
        rewrite = False
        chosen = ""
    bank = effective_bank(user_id)
    with using_provider(chosen):
        doc, audit_raw = tailor(
            jd, target_role=target_role, company=company, rewrite=rewrite, bank=bank
        )
        return _finalize(
            doc, audit_raw, jd, target_role, company, url, extractor,
            cover_letter, user_id, bank,
        )


def run_application_stream(
    jd: str,
    target_role: str = "",
    company: str = "",
    url: str = "",
    extractor: str = "paste",
    rewrite: bool = True,
    cover_letter: bool = True,
    user_id: int | None = None,
    llm_provider: str = "",
    halted=None,
) -> Iterator[dict[str, Any]]:
    """Yield progress events during tailoring, then a final 'result' event with
    the compiled PDF path, resume id, and audit (including the ATS score)."""
    from backend.llm.llm import using_provider
    from backend.resume.userbank import effective_bank

    chosen = (llm_provider or "").strip().lower()
    if chosen == "select":
        rewrite = False
        chosen = ""
    bank = effective_bank(user_id)
    doc: dict[str, Any] = {}
    audit_raw: dict[str, Any] = {}
    with using_provider(chosen):
        for event in tailor_stream(
            jd, target_role=target_role, company=company, rewrite=rewrite, bank=bank, halted=halted
        ):
            if halted and halted():
                return
            if event.get("type") == "done":
                doc, audit_raw = event["doc"], event["audit"]
            else:
                yield event

        if halted and halted():
            return
        if not doc:
            return
        yield {
            "type": "progress",
            "stage": "finalize",
            "message": "Compiling the PDF and a short cover letter from the same facts.",
            "pct": 96,
            "score": audit_raw.get("ats_score"),
            "target": TARGET,
        }
        result = _finalize(
            doc, audit_raw, jd, target_role, company, url, extractor,
            cover_letter, user_id, bank,
        )
    yield {"type": "result", **result}

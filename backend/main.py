from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from backend.auth import (
    change_password,
    get_or_create_cli_user,
    login_user,
    logout_token,
    register_user,
    user_from_token,
)
from backend.resume.compiler import compile_resume, output_folder
from backend.config import CLI_USER_EMAIL, DATA_DIR, FRONTEND_DIR, HOST, PORT, ROOT
from backend.store.db import init_db
from backend.store.runs import (
    abandon_running,
    active_run,
    create_run,
    fail_run,
    get_run,
    is_running,
    record_event,
    stop_run,
)
from backend.resume.fact_bank import default_document, load_bank
from backend.jobs.jobs import search_jobs
from backend.store.library import (
    delete_resume,
    due_resumes,
    file_for_download,
    keep_resume,
    list_resumes,
)
from backend.store.logbook import read_applications
from backend.pipeline import run_application, run_application_stream
from backend.resume.resume_parser import bank_summary, build_fact_bank, extract_text
from backend.schemas import Audit, TailorRequest, TailorResponse
from backend.resume.userbank import (
    delete_user_bank,
    effective_bank,
    load_user_bank,
    save_user_bank,
    user_bank_meta,
)
from backend.resume.validator import ValidationError, validate_document

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB is plenty for a resume
ALLOWED_RESUME_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    abandon_running("The tailor stopped because the server restarted.")
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Resume Tailor", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthBody(BaseModel):
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_long_enough(cls, value: str) -> str:
        if len(value or "") < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return authorization.strip()


def current_user(authorization: str | None = Header(default=None)) -> dict:
    user = user_from_token(_bearer(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Log in first.")
    return user


def optional_or_cli_user(authorization: str | None = Header(default=None)) -> dict:
    user = user_from_token(_bearer(authorization))
    if user:
        return user
    return get_or_create_cli_user(CLI_USER_EMAIL)


_DEVTOOLS_UUID = DATA_DIR / "chrome-devtools-uuid"
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _chrome_devtools_uuid() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = _DEVTOOLS_UUID.read_text().strip() if _DEVTOOLS_UUID.exists() else ""
    if len(current) == 36:
        return current
    generated = str(uuid.uuid4())
    _DEVTOOLS_UUID.write_text(generated)
    return generated


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools(request: Request):
    """Chrome asks for this whenever DevTools is open. Local only."""
    host = request.client.host if request.client else ""
    if host not in _LOOPBACK:
        raise HTTPException(status_code=404)
    return {"workspace": {"root": str(ROOT), "uuid": _chrome_devtools_uuid()}}


@app.get("/health")
def health():
    from backend.llm.llm import status as llm_status

    bank = load_bank()
    return {
        "ok": True,
        "roles": len(bank["roles"]),
        "projects": len(bank["projects"]),
        "facts": sum(len(r["bullets"]) for r in bank["roles"])
        + sum(len(p["bullets"]) for p in bank["projects"]),
        "llm": llm_status(),
    }


@app.post("/v1/auth/register")
def auth_register(body: AuthBody):
    try:
        user = register_user(body.email, body.password)
        user, token = login_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "token": token}


@app.post("/v1/auth/login")
def auth_login(body: AuthBody):
    try:
        user, token = login_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"user": user, "token": token}


@app.post("/v1/auth/password")
def auth_password(body: AuthBody):
    try:
        change_password(body.email, body.password)
        user, token = login_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "token": token}


@app.post("/v1/auth/logout")
def auth_logout(authorization: str | None = Header(default=None)):
    logout_token(_bearer(authorization))
    return {"ok": True}


@app.get("/v1/auth/me")
def auth_me(user: dict = Depends(current_user)):
    return {"user": user}


@app.get("/v1/resume")
def resume_status(user: dict = Depends(current_user)):
    """Whether this user has uploaded a source-of-truth resume yet."""
    meta = user_bank_meta(user["id"])
    bank = effective_bank(user["id"])
    summary = bank_summary(bank)
    return {
        "uploaded": meta is not None,
        "meta": meta,
        "summary": summary,
        "suggested_titles": summary.get("suggested_titles") or [],
    }


@app.post("/v1/resume/upload")
async def resume_upload(
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    """Parse an uploaded resume into this user's fact bank (source of truth)."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_RESUME_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Upload a PDF, DOCX, or TXT resume.",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Resume is larger than 5 MB.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(raw)
        tmp.flush()
        try:
            text = extract_text(tmp.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if len((text or "").strip()) < 80:
        raise HTTPException(
            status_code=422,
            detail="Could not read enough text from that file. If it is a scanned "
            "image PDF, paste the text as .txt instead.",
        )

    bank, mode = build_fact_bank(text)
    save_user_bank(user["id"], bank, source_name=file.filename or "", mode=mode)
    summary = bank_summary(bank)
    warnings = []
    if summary["roles"] == 0:
        warnings.append("No work experience detected — check the file formatting.")
    if not bank["profile"].get("email"):
        warnings.append("No email detected in the resume header.")
    return {
        "ok": True,
        "mode": mode,  # 'llm' or 'heuristic'
        "summary": summary,
        "warnings": warnings,
    }


@app.delete("/v1/resume")
def resume_delete(user: dict = Depends(current_user)):
    delete_user_bank(user["id"])
    return {"ok": True}


@app.post("/v1/tailor/stream")
async def tailor_stream_endpoint(
    payload: TailorRequest, user: dict = Depends(optional_or_cli_user)
):
    """Server-sent events: a live explanation of each step, then the PDF."""
    _require_llm_provider(payload.llm_provider)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    run_id = create_run(user["id"], payload.company, payload.target_role)

    def offer(item: dict | None) -> None:
        try:
            asyncio.run_coroutine_threadsafe(queue.put(item), loop).result(timeout=2)
        except Exception:
            # The browser can leave. The tailor keeps writing the run row.
            return

    def produce() -> None:
        try:
            for event in run_application_stream(
                payload.job_description,
                target_role=payload.target_role,
                company=payload.company,
                url=payload.url,
                extractor=payload.extractor,
                rewrite=payload.rewrite,
                cover_letter=payload.cover_letter,
                user_id=user["id"],
                llm_provider=payload.llm_provider,
                halted=lambda: not is_running(run_id),
            ):
                if not is_running(run_id):
                    break
                record_event(run_id, event)
                offer(event)
            offer(None)
        except Exception as exc:
            fail_run(run_id, str(exc))
            offer({"type": "error", "detail": str(exc)})
            offer(None)

    threading.Thread(target=produce, daemon=True).start()

    async def gen():
        pad = ":" + (" " * 1024) + "\n\n"
        yield f"data: {json.dumps({'type': 'run', 'id': run_id})}\n\n{pad}"
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n{pad}"
            await asyncio.sleep(0)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/runs/active")
def run_active(user: dict = Depends(current_user)):
    return {"run": active_run(user["id"])}


@app.get("/v1/runs/{run_id}")
def run_status(run_id: int, user: dict = Depends(current_user)):
    row = get_run(user["id"], run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


@app.post("/v1/runs/{run_id}/stop")
def run_stop(run_id: int, user: dict = Depends(current_user)):
    row = get_run(user["id"], run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    stop_run(user["id"], run_id)
    return get_run(user["id"], run_id)


@app.get("/v1/jobs/search")
def jobs_search(
    q: str,
    page: int = 1,
    page_size: int = 10,
    limit: int | None = None,
    user: dict = Depends(current_user),
):
    try:
        meta = user_bank_meta(user["id"])
        return search_jobs(
            q,
            limit=limit,
            page=page,
            page_size=page_size if limit is None else None,
            bank=load_user_bank(user["id"]),
            cache_key=f"{user['id']}:{(meta or {}).get('updated_at') or 'none'}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/library")
def library_list(user: dict = Depends(current_user)):
    return {
        "resumes": list_resumes(user["id"]),
        "due": due_resumes(user["id"]),
        "review_days": 7,
    }


@app.post("/v1/library/{resume_id}/keep")
def library_keep(resume_id: int, user: dict = Depends(current_user)):
    try:
        return keep_resume(user["id"], resume_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Resume not found") from exc


@app.post("/v1/library/{resume_id}/delete")
def library_delete(resume_id: int, user: dict = Depends(current_user)):
    try:
        return delete_resume(user["id"], resume_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Resume not found") from exc


@app.get("/v1/library/{resume_id}/download")
def library_download(
    resume_id: int,
    kind: str = "resume",
    user: dict = Depends(current_user),
):
    try:
        path = file_for_download(user["id"], resume_id, kind)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    filename = path.name
    media = "application/pdf" if path.suffix == ".pdf" else "text/plain"
    return FileResponse(path, media_type=media, filename=filename)


@app.get("/v1/log")
def application_log(limit: int = 50, user: dict = Depends(optional_or_cli_user)):
    due = due_resumes(user["id"])
    return {
        "applications": read_applications(limit=limit),
        "due": due,
        "user": user["email"],
    }


@app.post("/v1/render")
def render_master():
    doc = default_document()
    validate_document(doc)
    dest = output_folder("master", "resume")
    pdf = compile_resume(doc, dest, "Ritwik_Resume.pdf")
    return {"status": "success", "pdf_path": str(pdf), "output_dir": str(dest)}


def _require_llm_provider(name: str) -> None:
    from backend.llm.llm import assert_provider

    try:
        assert_provider(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_tailor(
    payload: TailorRequest, user: dict = Depends(optional_or_cli_user)
) -> TailorResponse:
    _require_llm_provider(payload.llm_provider)
    try:
        result = run_application(
            payload.job_description,
            target_role=payload.target_role,
            company=payload.company,
            url=payload.url,
            extractor=payload.extractor,
            rewrite=payload.rewrite,
            cover_letter=payload.cover_letter,
            user_id=user["id"],
            llm_provider=payload.llm_provider,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TailorResponse(
        status=result["status"],
        output_dir=result["output_dir"],
        pdf_path=result["pdf_path"],
        cover_letter_path=result["cover_letter_path"],
        company=result["company"],
        role=result["role"],
        url=result["url"],
        extractor=result["extractor"],
        resume_id=result.get("resume_id"),
        audit=Audit(**result["audit"]),
    )


@app.post("/v1/tailor", response_model=TailorResponse)
def tailor_endpoint(
    payload: TailorRequest, user: dict = Depends(optional_or_cli_user)
):
    return _run_tailor(payload, user)


@app.post("/v1/ingest", response_model=TailorResponse)
def ingest_endpoint(
    payload: TailorRequest, user: dict = Depends(optional_or_cli_user)
):
    return _run_tailor(payload, user)


DIST_DIR = FRONTEND_DIR / "dist"


def _frontend_file(path: str) -> FileResponse:
    index = DIST_DIR / "index.html"
    if path:
        candidate = (DIST_DIR / path).resolve()
        root = DIST_DIR.resolve()
        if candidate.is_file() and (candidate == root or root in candidate.parents):
            return FileResponse(candidate)
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend missing")


@app.get("/")
def home():
    return _frontend_file("")


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path == "health" or full_path.startswith(("v1/", ".well-known/")):
        raise HTTPException(status_code=404)
    return _frontend_file(full_path)


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    run()

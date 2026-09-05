from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.auth import (
    get_or_create_cli_user,
    login_user,
    logout_token,
    register_user,
    user_from_token,
)
from backend.compiler import compile_resume, output_folder
from backend.config import CLI_USER_EMAIL, FRONTEND_DIR, HOST, PORT
from backend.db import init_db
from backend.fact_bank import default_document, load_bank
from backend.jobs import search_jobs
from backend.library import (
    delete_resume,
    due_resumes,
    file_for_download,
    keep_resume,
    list_resumes,
)
from backend.logbook import read_applications
from backend.pipeline import run_application
from backend.schemas import Audit, TailorRequest, TailorResponse
from backend.validator import ValidationError, validate_document


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
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
    password: str = Field(min_length=8)


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


@app.get("/health")
def health():
    bank = load_bank()
    return {
        "ok": True,
        "roles": len(bank["roles"]),
        "projects": len(bank["projects"]),
        "facts": sum(len(r["bullets"]) for r in bank["roles"])
        + sum(len(p["bullets"]) for p in bank["projects"]),
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


@app.post("/v1/auth/logout")
def auth_logout(authorization: str | None = Header(default=None)):
    logout_token(_bearer(authorization))
    return {"ok": True}


@app.get("/v1/auth/me")
def auth_me(user: dict = Depends(current_user)):
    return {"user": user}


@app.get("/v1/jobs/search")
def jobs_search(q: str, limit: int = 20, user: dict = Depends(current_user)):
    try:
        return search_jobs(q, limit=min(max(limit, 1), 40))
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


def _run_tailor(
    payload: TailorRequest, user: dict = Depends(optional_or_cli_user)
) -> TailorResponse:
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


@app.get("/")
def home():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Frontend missing")
    return FileResponse(index)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    run()

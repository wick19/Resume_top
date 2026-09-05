from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

SAMPLE = (
    "We are hiring an AI Engineer for production FastAPI microservices, "
    "LLM orchestration, Redis, PostgreSQL, Docker, and Kubernetes. "
    "REST APIs and OAuth2 required."
)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["facts"] >= 20


def test_tailor_select_only(tmp_path, monkeypatch):
    import backend.compiler as compiler
    import backend.logbook as logbook
    import backend.pipeline as pipeline

    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "output_folder", lambda company, role, revision=1: tmp_path / "api_run")
    monkeypatch.setattr(logbook, "LOG_PATH", tmp_path / "applications.jsonl")
    monkeypatch.setattr(pipeline, "append_application", logbook.append_application)

    res = client.post(
        "/v1/tailor",
        json={
            "job_description": SAMPLE,
            "target_role": "AI Engineer",
            "company": "Acme",
            "extractor": "paste",
            "rewrite": False,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pdf_path"].endswith(".pdf")
    assert body["cover_letter_path"].endswith("cover_letter.txt")
    assert body["audit"]["mode"] == "select"


def test_jobs_search_requires_login():
    res = client.get("/v1/jobs/search", params={"q": "AI"})
    assert res.status_code == 401


def test_jobs_search_returns_public_results(monkeypatch):
    from backend.auth import register_user, login_user
    import backend.main as main

    register_user("jobs@test.local", "password1")
    _user, token = login_user("jobs@test.local", "password1")

    monkeypatch.setattr(
        main,
        "search_jobs",
        lambda q, limit=20: {
            "query": q,
            "jobs": [
                {
                    "id": "remotive:1",
                    "source": "remotive",
                    "title": "AI Engineer",
                    "company": "Acme",
                    "description": "FastAPI",
                    "url": "https://remotive.com/1",
                }
            ],
            "errors": [],
            "note": "ok",
        },
    )
    res = client.get(
        "/v1/jobs/search",
        params={"q": "AI Engineer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["jobs"][0]["company"] == "Acme"

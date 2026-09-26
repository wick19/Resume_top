from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

SAMPLE = (
    "We are hiring an AI Engineer for production FastAPI microservices, "
    "LLM orchestration, Redis, PostgreSQL, Docker, and Kubernetes. "
    "REST APIs and OAuth2 required."
)


def test_login_short_password_is_readable():
    res = client.post(
        "/v1/auth/login",
        json={"email": "v@gmail.com", "password": "short"},
    )
    assert res.status_code == 422
    msgs = " ".join(item.get("msg", "") for item in res.json()["detail"])
    assert "8 characters" in msgs


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["facts"] >= 20
    assert "quota" in body["llm"]
    assert "groq" in body["llm"]["signup"]
    assert "quotas" in body["llm"]
    assert {row["provider"] for row in body["llm"]["quotas"]} >= {"groq", "gemini", "cerebras"}
    assert {c["id"] for c in body["llm"]["choices"]} >= {"auto", "groq", "select"}


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


def test_tailor_llm_provider_select_skips_rewrite(tmp_path, monkeypatch):
    import backend.compiler as compiler
    import backend.logbook as logbook
    import backend.pipeline as pipeline

    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "output_folder", lambda company, role, revision=1: tmp_path / "api_select")
    monkeypatch.setattr(logbook, "LOG_PATH", tmp_path / "applications.jsonl")
    monkeypatch.setattr(pipeline, "append_application", logbook.append_application)

    called = {"chat": False}

    def boom(*_args, **_kwargs):
        called["chat"] = True
        raise AssertionError("select must not call the LLM")

    monkeypatch.setattr("backend.aligner.chat", boom)
    monkeypatch.setattr("backend.cover_letter.chat", boom)

    res = client.post(
        "/v1/tailor",
        json={
            "job_description": SAMPLE,
            "target_role": "AI Engineer",
            "company": "Acme",
            "extractor": "paste",
            "rewrite": True,
            "llm_provider": "select",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["audit"]["mode"] == "select"
    assert called["chat"] is False


def test_tailor_unknown_llm_provider():
    res = client.post(
        "/v1/tailor",
        json={
            "job_description": SAMPLE,
            "target_role": "AI Engineer",
            "company": "Acme",
            "extractor": "paste",
            "llm_provider": "madeup",
        },
    )
    assert res.status_code == 400
    assert "Unknown" in res.json()["detail"]


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
        lambda q, limit=None, bank=None, page=1, page_size=10, cache_key="": {
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

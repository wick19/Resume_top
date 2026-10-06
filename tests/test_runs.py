from fastapi.testclient import TestClient

from backend.auth import login_user, register_user
from backend.main import app
from backend.pipeline import run_application_stream
from backend.store.runs import create_run, get_run, record_event

client = TestClient(app)

JD = (
    "AI Engineer: Python, FastAPI, Redis, PostgreSQL, "
    "Docker, Kubernetes, LLMs, REST APIs."
)


def _user():
    register_user("stop@test.local", "password1")
    user, token = login_user("stop@test.local", "password1")
    return user, {"Authorization": f"Bearer {token}"}


def test_new_run_closes_the_previous_without_a_pdf():
    user, _headers = _user()
    first = create_run(user["id"], "Acme", "AI Engineer")
    second = create_run(user["id"], "Beta", "Backend Engineer")
    assert get_run(user["id"], first)["status"] == "stopped"
    assert get_run(user["id"], first)["result"] is None
    assert get_run(user["id"], second)["status"] == "running"
    record_event(
        first,
        {
            "type": "result",
            "company": "Acme",
            "role": "AI Engineer",
            "resume_id": 9,
            "audit": {"ats_score": 90, "ats_target": 97},
        },
    )
    closed = get_run(user["id"], first)
    assert closed["status"] == "stopped"
    assert closed["result"] is None


def test_stop_endpoint_drops_the_active_run():
    user, headers = _user()
    run_id = create_run(user["id"], "Acme", "AI Engineer")
    res = client.post(f"/v1/runs/{run_id}/stop", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "stopped"
    assert client.get("/v1/runs/active", headers=headers).json()["run"] is None


def test_halted_stream_does_not_compile(tmp_path, monkeypatch):
    import backend.pipeline as pipeline
    import backend.resume.compiler as compiler
    import backend.store.logbook as logbook

    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "output_folder", lambda company, role, revision=1: tmp_path / "halted")
    monkeypatch.setattr(logbook, "LOG_PATH", tmp_path / "applications.jsonl")
    monkeypatch.setattr(pipeline, "append_application", logbook.append_application)

    seen = []

    def halted():
        return len(seen) >= 1

    for event in run_application_stream(
        JD,
        target_role="AI Engineer",
        company="Acme",
        rewrite=False,
        halted=halted,
    ):
        seen.append(event)

    assert seen
    assert not any(event.get("type") == "result" for event in seen)
    assert not (tmp_path / "halted").exists()

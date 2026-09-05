from backend.aligner import tailor
from backend.cover_letter import generate_cover_letter, template_cover_letter, validate_cover_letter, word_count
from backend.fact_bank import default_document, load_bank
from backend.logbook import append_application, read_applications
from backend.pipeline import run_application
from backend.validator import ValidationError


SAMPLE = """
We are hiring an AI Engineer to own production FastAPI microservices and LLM-powered workflows.
Requirements: Python, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, REST APIs, OAuth2.
Kafka is required. Experience with RAG is a plus.
"""


def test_template_cover_letter_is_short_and_valid():
    bank = load_bank()
    doc = default_document()
    letter = template_cover_letter(SAMPLE, "AI Engineer", "Acme", doc, bank)
    assert 40 < word_count(letter) <= 250
    validate_cover_letter(letter, bank, "Acme")


def test_cover_letter_rejects_too_long():
    bank = load_bank()
    try:
        validate_cover_letter("word " * 251, bank)
        raised = False
    except ValidationError:
        raised = True
    assert raised


def test_select_only_pipeline_writes_pdf_and_letter(tmp_path, monkeypatch):
    import backend.compiler as compiler
    import backend.logbook as logbook
    import backend.pipeline as pipeline

    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "output_folder", lambda company, role, revision=1: tmp_path / "run")
    monkeypatch.setattr(logbook, "LOG_PATH", tmp_path / "applications.jsonl")
    monkeypatch.setattr(pipeline, "append_application", logbook.append_application)

    result = run_application(
        SAMPLE,
        target_role="AI Engineer",
        company="Acme",
        rewrite=False,
        cover_letter=True,
    )
    assert result["status"] == "success"
    from pathlib import Path

    assert Path(result["pdf_path"]).exists()
    assert Path(result["pdf_path"]).stat().st_size > 1000
    assert Path(result["cover_letter_path"]).exists()
    rows = read_applications(path=tmp_path / "applications.jsonl")
    assert rows and rows[0]["company"] == "Acme"


def test_tailor_select_only_keeps_sprouts():
    doc, audit = tailor(SAMPLE, target_role="AI Engineer", company="Acme", rewrite=False)
    assert doc["roles"][0]["id"] == "role.sprouts"
    assert audit["mode"] == "select"
    assert any("kafka" in g.lower() for g in audit["gaps"])

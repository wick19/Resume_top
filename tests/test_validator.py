from backend.fact_bank import default_document, load_bank
from backend.validator import ValidationError, validate_document


def test_master_document_validates():
    validate_document(default_document())


def test_every_resume_bullet_has_an_id():
    bank = load_bank()
    ids = []
    for role in bank["roles"]:
        assert role["id"]
        for bullet in role["bullets"]:
            assert bullet["id"].startswith(role["id"])
            ids.append(bullet["id"])
    for project in bank["projects"]:
        for bullet in project["bullets"]:
            assert bullet["id"].startswith(project["id"])
            ids.append(bullet["id"])
    assert len(ids) == len(set(ids))
    assert len(ids) >= 20


def test_rejects_invented_metric():
    doc = default_document()
    doc["roles"][1]["bullets"][1]["text"] += " increasing revenue by 90%."
    try:
        validate_document(doc)
        raised = False
    except ValidationError as exc:
        raised = True
        assert "90%" in str(exc)
    assert raised


def test_rejects_kafka_on_sprouts_bullet():
    doc = default_document()
    doc["roles"][0]["bullets"][0]["text"] += " using Kafka."
    try:
        validate_document(doc, jd="Kafka is required.")
        raised = False
    except ValidationError:
        raised = True
    assert raised


def test_rejects_keyword_stuffing_of_grounded_stack():
    """Even skills that live on the role stack cannot all be dumped into one bullet."""
    doc = default_document()
    # Sprouts stack includes FastAPI, Redis, Docker, Kubernetes, JWT, OAuth2.
    # The first bullet does not originally list those.
    doc["roles"][0]["bullets"][0]["text"] += (
        " using FastAPI, Redis, Docker, Kubernetes, JWT, and OAuth2."
    )
    try:
        validate_document(doc)
        raised = False
        message = ""
    except ValidationError as exc:
        raised = True
        message = str(exc)
    assert raised
    assert "keyword-stuffs" in message or "keyword dump" in message


def test_rejects_profile_mutation():
    doc = default_document()
    doc["profile"]["email"] = "other@example.com"
    try:
        validate_document(doc)
        raised = False
    except ValidationError as exc:
        raised = True
        assert "email" in str(exc)
    assert raised


def test_allows_years_already_in_fact_bank_summary():
    bank = load_bank()
    bank = {**bank, "default_summary": "HR professional with 5+ years of experience in hiring."}
    doc = default_document()
    doc["summary"] = "HR professional with 5+ years of experience in talent acquisition."
    validate_document(doc, bank)


def test_rejects_years_invented_in_summary():
    doc = default_document()
    doc["summary"] = (doc.get("summary") or "") + " with 12 years of experience."
    try:
        validate_document(doc)
        raised = False
    except ValidationError as exc:
        raised = True
        assert "years of experience" in str(exc)
    assert raised


def test_neighbor_rephrase_is_allowed_and_unrelated_tool_is_not():
    from backend.neighbors import along_the_lines

    assert along_the_lines("sql", {"postgresql"})
    assert not along_the_lines("sqlalchemy", {"postgresql"})
    assert not along_the_lines("kubernetes", {"docker"})
    assert not along_the_lines("kafka", {"postgresql", "docker"})

    bank = {
        "profile": {
            "name": "A", "phone": "", "email": "", "linkedin": "",
            "github": "", "portfolio": "",
        },
        "default_summary": "Builds data services.",
        "synonyms": {},
        "education": [],
        "projects": [],
        "skill_groups": [{
            "id": "skills.1",
            "label": "Skills",
            "items": ["PostgreSQL", "MySQL", "Python"],
        }],
        "roles": [{
            "id": "role.1",
            "company": "Acme",
            "title": "Engineer",
            "start": "2024",
            "end": "2025",
            "location": "",
            "stack": ["PostgreSQL"],
            "bullets": [{
                "id": "role.1.b1",
                "text": "Designed PostgreSQL schemas for reporting.",
                "skills": ["PostgreSQL"],
                "locked_numbers": [],
            }],
        }],
    }
    role = {
        "id": "role.1",
        "company": "Acme",
        "title": "Engineer",
        "start": "2024",
        "end": "2025",
        "location": "",
        "bullets": [{
            "id": "role.1.b1",
            "text": "Designed PostgreSQL schemas and SQL reporting tables for the finance team.",
        }],
    }
    doc = {
        "profile": dict(bank["profile"]),
        "summary": "Engineer building SQL reporting services.",
        "roles": [role],
        "projects": [],
        "education": [],
        "skill_groups": bank["skill_groups"],
    }
    validate_document(doc, bank)

    doc["summary"] = "Engineer building Workday pipelines."
    doc["roles"][0]["bullets"][0]["text"] = (
        "Designed PostgreSQL schemas for reporting using Workday."
    )
    try:
        validate_document(doc, bank, jd="Experience with Workday is required.")
        raised = False
    except ValidationError as exc:
        raised = True
        assert "workday" in str(exc).lower()
    assert raised


def test_overlay_strips_invented_years_from_summary():
    from backend.aligner import overlay_rewrite

    selected = default_document()
    out = overlay_rewrite(
        selected,
        {"summary": "Engineer with 9 years of experience building APIs."},
    )
    assert "9" not in out["summary"]
    assert "years" not in out["summary"].lower()

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
        validate_document(doc)
        raised = False
    except ValidationError:
        raised = True
    assert raised


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

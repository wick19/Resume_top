from backend.match.ats import CAP, score_resume
from backend.resume.fact_bank import default_document, load_bank
from backend.match.jd_parser import detect_seniority, parse_jd
from backend.match.semantic import backend_name, similarity


def test_parse_jd_splits_must_and_nice():
    jd = """
    Senior AI Engineer

    Requirements:
    - Strong Python and FastAPI experience
    - Production experience with PostgreSQL and Redis

    Nice to have:
    - Exposure to Kubernetes and Kafka
    """
    parsed = parse_jd(jd, target_role="AI Engineer")
    assert parsed["seniority"] == "senior"
    assert parsed["title"] == "AI Engineer"
    assert "FastAPI" in parsed["must_have_skills"]
    assert "Python" in parsed["must_have_skills"]
    # Kafka is not in the fact bank -> flagged as an external ask, not a skill.
    assert "Kafka" in parsed["nice_to_have_external"] or "Kafka" in parsed["must_have_external"]


def test_requirements_come_from_the_job_not_a_profession_list():
    from backend.match.jd_parser import phrase_supported

    bank = load_bank()
    hr = parse_jd(
        "Requirements: experience with Workday and employee relations.\n"
        "Nice to have: Gainsight.",
        target_role="Customer Success Manager",
        bank=bank,
    )
    external = hr["must_have_external"] + hr["nice_to_have_external"]
    assert any(p.lower() == "workday" for p in external)
    assert any(p.lower() == "gainsight" for p in external)
    assert phrase_supported("sql", {"roles": [{
        "bullets": [{"text": "Designed PostgreSQL schemas.", "skills": ["PostgreSQL"]}],
        "stack": ["PostgreSQL"],
    }], "skill_groups": [{"items": ["PostgreSQL"]}], "default_summary": "", "synonyms": {}, "projects": []})
    assert not phrase_supported("SQLAlchemy", {"roles": [{
        "bullets": [{"text": "Designed PostgreSQL schemas.", "skills": ["PostgreSQL"]}],
        "stack": ["PostgreSQL"],
    }], "skill_groups": [{"items": ["PostgreSQL"]}], "default_summary": "", "synonyms": {}, "projects": []})


def test_boilerplate_around_a_known_skill_is_not_a_gap():
    """Wrappers are not skills. A different product or duty still is a gap.
    The same rule applies outside engineering."""
    from backend.match.jd_parser import phrase_supported

    bank = load_bank()
    jd = """
    Requirements:
    - A customer-facing role such as sales engineer, solutions engineer
    - Proficiency in Python, Typescript
    - Knowledge of LLM
    - Agentic frameworks such as OpenAI Agents SDK, DSPy
    - Understanding of GenAI concepts
    """
    external = [p.lower() for p in parse_jd(jd, bank=bank)["must_have_external"]]
    assert phrase_supported("Proficiency in Python", bank)
    assert phrase_supported("Knowledge of LLM", bank)
    assert phrase_supported("Understanding of GenAI concepts", bank)
    assert "python" not in external
    assert "typescript" not in external
    assert not any("llm" in p and "dspy" in p for p in external)
    assert any("sales engineer" in p for p in external)
    assert any("solutions engineer" in p for p in external)
    assert any("dspy" in p for p in external)
    assert any("openai agents sdk" in p for p in external)
    assert "agents" not in external

    nurse = {
        "default_summary": "Nurse with bedside patient assessment.",
        "synonyms": {},
        "projects": [],
        "roles": [{
            "title": "Registered Nurse",
            "stack": [],
            "bullets": [{
                "text": "Completed patient assessment and wound care each shift.",
                "skills": ["patient assessment", "wound care"],
            }],
        }],
        "skill_groups": [{"items": ["patient assessment", "wound care"]}],
    }
    clinical = parse_jd(
        "Requirements:\n- Proficiency in patient assessment\n- Knowledge of Epic EHR",
        target_role="Registered Nurse",
        bank=nurse,
    )
    clinical_gaps = [p.lower() for p in clinical["must_have_external"]]
    assert not any("patient assessment" in p for p in clinical_gaps)
    assert any("epic ehr" in p for p in clinical_gaps)


def test_detect_seniority_variants():
    assert detect_seniority("We want a Junior developer") == "junior"
    assert detect_seniority("Principal / Staff Engineer") == "staff"
    assert detect_seniority("A backend engineer") == "unspecified"


def test_ats_score_rewards_coverage_and_caps():
    jd = """
    AI Engineer. Requirements: Python, FastAPI, PostgreSQL, Redis, Docker,
    Kubernetes, REST APIs, LLMs, semantic search.
    """
    parsed = parse_jd(jd, target_role="AI Engineer")
    doc = default_document(load_bank())
    result = score_resume(doc, parsed)
    assert 0 <= result["score"] <= CAP
    # The master resume already covers most of these, so it should score well.
    assert result["score"] >= 60
    assert result["target"] == 97
    assert CAP == 98


def test_ats_missing_in_bank_is_actionable():
    # A JD skill the bank supports but a stripped resume does not surface.
    jd = "Requirements: Python, FastAPI, Elasticsearch, semantic retrieval."
    parsed = parse_jd(jd, target_role="AI Engineer")
    doc = default_document(load_bank())
    # Drop the bullet that carries "semantic retrieval" so it is not surfaced
    # anywhere (it is not a Skills-section item, only bullet phrasing).
    for role in doc["roles"]:
        role["bullets"] = [
            b for b in role["bullets"] if "semantic retrieval" not in b["text"].lower()
        ]
    result = score_resume(doc, parsed)
    assert "semantic retrieval" in result["missing_in_bank"]
    # Elasticsearch lives in the Skills section, so it stays covered.
    assert "Elasticsearch" in result["must_covered"]


def test_semantic_similarity_lexical_fallback_is_ordered():
    # Without a key we use the lexical fallback; identical text should win.
    assert backend_name() in ("embeddings", "lexical")
    sims = similarity("python fastapi backend", [
        "python fastapi backend service",
        "graphic design and illustration",
    ])
    assert sims[0] > sims[1]

from backend.match.scoring import order_recent_bullets, select_for_jd


JD = """
We are hiring a Senior AI Engineer / Backend Engineer.
You will design FastAPI microservices, LLM provider orchestration, Redis caching,
asynchronous pipelines, PostgreSQL, Docker, and Kubernetes.
Experience with RAG and LangChain is a plus. Kafka is required.
"""


def test_select_keeps_recent_sprouts_role_first():
    doc = select_for_jd(JD, target_role="AI Engineer")
    assert doc["roles"][0]["id"] == "role.sprouts"
    used = {b["id"] for r in doc["roles"] for b in r["bullets"]}
    assert "role.sprouts.b1" in used
    assert "role.sprouts.b4" in used or "role.sprouts.b5" in used


def test_recent_role_leads_with_the_matching_metric():
    bank = {
        "default_summary": "Backend engineer.",
        "synonyms": {},
        "projects": [],
        "education": [],
        "profile": {},
        "skill_groups": [{
            "id": "skills.lang",
            "label": "Languages",
            "items": ["Go", "FastAPI", "PostgreSQL"],
        }],
        "roles": [
            {
                "id": "role.now",
                "company": "Now",
                "title": "Engineer",
                "start": "2024",
                "end": "Present",
                "location": "",
                "include_by_default": True,
                "recency_rank": 1,
                "stack": ["Python"],
                "bullets": [
                    {"id": "b1", "text": "Wrote internal notes for the team.", "skills": []},
                    {"id": "b2", "text": "Kept the PostgreSQL schemas healthy.", "skills": ["PostgreSQL"]},
                    {"id": "b3", "text": "Built FastAPI services and cut latency by 20%.", "skills": ["FastAPI"]},
                ],
            },
            {
                "id": "role.old",
                "company": "Old",
                "title": "Developer",
                "start": "2020",
                "end": "2022",
                "location": "",
                "include_by_default": True,
                "recency_rank": 2,
                "stack": [],
                "bullets": [
                    {"id": "old1", "text": "First original bullet about PostgreSQL.", "skills": ["PostgreSQL"]},
                    {"id": "old2", "text": "Second original bullet about FastAPI latency by 15%.", "skills": ["FastAPI"]},
                ],
            },
        ],
    }
    doc = select_for_jd(
        "Backend engineer. FastAPI and PostgreSQL required.",
        target_role="Backend Engineer",
        bank=bank,
    )
    recent = doc["roles"][0]
    assert recent["id"] == "role.now"
    assert recent["bullets"][0]["id"] == "b2"
    assert recent["bullets"][1]["id"] == "b3"
    older = next(role for role in doc["roles"] if role["id"] == "role.old")
    assert [bullet["id"] for bullet in older["bullets"]] == ["old1", "old2"]
    assert doc["skill_groups"][0]["items"] == ["FastAPI", "PostgreSQL", "Go"]


def test_metric_bullet_moves_into_the_first_two_lines():
    ordered = order_recent_bullets(
        [
            {"id": "a", "text": "Built FastAPI services for the product.", "skills": ["FastAPI"]},
            {"id": "b", "text": "Ran PostgreSQL backups for the product.", "skills": ["PostgreSQL"]},
            {"id": "c", "text": "Cut API latency by 20% on Redis.", "skills": ["Redis"]},
        ],
        {"fastapi", "postgresql", "redis"},
    )
    assert [bullet["id"] for bullet in ordered] == ["a", "c", "b"]

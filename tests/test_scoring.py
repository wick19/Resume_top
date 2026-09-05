from backend.scoring import select_for_jd


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

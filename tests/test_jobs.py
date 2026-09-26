from urllib.parse import unquote_plus

import httpx

from backend.jobs import google_jobs_url, google_location, host_blocked, html_to_text, search_jobs


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_html_to_text_strips_tags():
    assert "FastAPI" in html_to_text("<p>Build <b>FastAPI</b> services</p>")


def test_linkedin_is_blocked():
    assert host_blocked("https://www.linkedin.com/jobs/view/123")
    assert host_blocked("https://www.naukri.com/job-listings-x")
    assert not host_blocked("https://remotive.com/api/remote-jobs")


def test_google_jobs_url_is_title_and_city_not_resume_stack():
    url = google_jobs_url(
        "AI Engineer",
        location="Bengaluru",
        keywords=["Python", "Alembic", "API"],
    )
    q = unquote_plus(url)
    assert "udm=8" in url
    assert "AI Engineer" in q
    assert "Bengaluru" in q
    assert "Alembic" not in q
    assert "API" not in q.split("q=")[-1]
    assert q.lower().count("jobs") == 0


def test_google_location_uses_current_role_city():
    city = google_location(
        {
            "profile": {"location": ""},
            "roles": [
                {
                    "title": "AI Engineer",
                    "company": "Sprouts.ai Bengaluru",
                    "location": "Karnataka, India",
                    "recency_rank": 1,
                }
            ],
        }
    )
    assert city == "Bengaluru"


def test_search_merges_public_apis(monkeypatch):
    def fake_get(url, params=None, **_kwargs):
        if "remotive.com" in url:
            return _Resp(
                {
                    "jobs": [
                        {
                            "id": 1,
                            "title": "AI Engineer",
                            "company_name": "Acme",
                            "candidate_required_location": "Remote",
                            "url": "https://remotive.com/remote-jobs/1",
                            "description": "<p>FastAPI and LLM orchestration</p>",
                            "tags": ["python"],
                        }
                    ]
                }
            )
        if "remoteok.com" in url:
            return _Resp(
                [
                    {"legal": "credit Remote OK"},
                    {
                        "id": 9,
                        "position": "Backend Engineer",
                        "company": "Other",
                        "location": "Remote",
                        "url": "https://remoteok.com/remote-jobs/9",
                        "description": "Java only enterprise role",
                        "tags": ["java"],
                    },
                ]
            )
        if "arbeitnow.com" in url:
            return _Resp({"data": []})
        if "jobicy.com" in url:
            return _Resp({"jobs": []})
        if "himalayas.app" in url:
            return _Resp({"jobs": []})
        if "themuse.com" in url:
            return _Resp({"results": []})
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "get", fake_get)
    result = search_jobs("AI Engineer FastAPI", limit=10)
    titles = {j["title"] for j in result["jobs"]}
    assert "AI Engineer" in titles
    assert "Backend Engineer" not in titles
    assert result["jobs"][0]["source"] == "remotive"
    assert "FastAPI" in result["jobs"][0]["description"]
    assert "not scraped" in result["note"]
    assert len(result["sources"]) >= 7
    assert "google.com/search" in result["google_jobs_url"]
    assert "Alembic" not in result["google_jobs_url"]
    assert "udm=8" in result["google_jobs_url"]


def test_keywords_for_title_stay_in_that_role():
    from backend.jobs import keywords_for_title

    bank = {
        "roles": [
            {
                "title": "AI Engineer",
                "recency_rank": 1,
                "stack": ["Python"],
                "bullets": [
                    {"text": "FastAPI LLMs", "skills": ["FastAPI", "LLMs", "Elasticsearch"]},
                    {"text": "React dashboards", "skills": ["React"]},
                ],
            },
            {
                "title": "Python Full Stack Developer",
                "recency_rank": 2,
                "stack": [],
                "bullets": [
                    {"text": "Django app", "skills": ["Django", "Flask", "PostgreSQL"]},
                ],
            },
        ]
    }
    role, kws = keywords_for_title("AI Engineer", bank)
    assert role == "AI Engineer"
    assert "FastAPI" in kws and "LLMs" in kws
    assert "Django" not in kws

    role2, kws2 = keywords_for_title("Python Full Stack Developer", bank)
    assert role2 == "Python Full Stack Developer"
    assert "Django" in kws2 and "Flask" in kws2
    assert "Elasticsearch" not in kws2

    role3, kws3 = keywords_for_title("AI Engineer, LangGraph", bank)
    assert role3 == "AI Engineer"
    assert "LangGraph" in kws3


def test_score_job_title_family_then_keywords():
    from backend.jobs import score_job

    keywords = ["FastAPI", "LLMs", "Python"]
    ai = score_job(
        {"title": "ML Engineer", "description": "PyTorch and research papers"},
        "AI Engineer",
        keywords,
    )
    assert ai is not None and ai[0] >= 2

    backend = score_job(
        {
            "title": "Backend Engineer",
            "description": "FastAPI microservices and LLMs on Python",
        },
        "AI Engineer",
        keywords,
    )
    assert backend is not None and backend[0] == 1
    assert "FastAPI" in backend[2] and "LLMs" in backend[2]

    java = score_job(
        {"title": "Backend Engineer", "description": "Java only enterprise role"},
        "AI Engineer",
        keywords,
    )
    assert java is None

    random = score_job(
        {"title": "Office Manager", "description": "We use AI tools in the office"},
        "AI Engineer",
        keywords,
    )
    assert random is None


def test_search_uses_resume_keywords_to_rank(monkeypatch):
    def fake_get(url, params=None, **_kwargs):
        if "remotive.com" in url:
            return _Resp(
                {
                    "jobs": [
                        {
                            "id": 1,
                            "title": "AI Engineer",
                            "company_name": "Acme",
                            "candidate_required_location": "Remote",
                            "url": "https://remotive.com/remote-jobs/1",
                            "description": "<p>FastAPI and LLM orchestration</p>",
                            "tags": ["python"],
                        },
                        {
                            "id": 2,
                            "title": "Office Manager",
                            "company_name": "Other",
                            "candidate_required_location": "Remote",
                            "url": "https://remotive.com/remote-jobs/2",
                            "description": "<p>Friendly office, some AI tools</p>",
                            "tags": [],
                        },
                    ]
                }
            )
        if "remoteok.com" in url:
            return _Resp([{"legal": "credit Remote OK"}])
        if "arbeitnow.com" in url:
            return _Resp({"data": []})
        if "jobicy.com" in url:
            return _Resp({"jobs": []})
        if "himalayas.app" in url:
            return _Resp({"jobs": []})
        if "themuse.com" in url:
            return _Resp({"results": []})
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "get", fake_get)
    bank = {
        "roles": [
            {
                "title": "AI Engineer",
                "recency_rank": 1,
                "bullets": [{"text": "x", "skills": ["FastAPI", "LLMs"]}],
            }
        ]
    }
    result = search_jobs("AI Engineer", limit=10, bank=bank)
    titles = [j["title"] for j in result["jobs"]]
    assert titles == ["AI Engineer"]
    assert result["matched_role"] == "AI Engineer"
    assert "FastAPI" in result["keywords"]
    assert "FastAPI" in result["jobs"][0]["matched_keywords"]
    google_q = unquote_plus(result["google_jobs_url"])
    assert "AI Engineer" in google_q
    assert "FastAPI" not in google_q


def test_search_paginates_and_reuses_cache(monkeypatch):
    remotive_hits = {"n": 0}

    def fake_get(url, params=None, **_kwargs):
        if "remotive.com" in url:
            remotive_hits["n"] += 1
            return _Resp(
                {
                    "jobs": [
                        {
                            "id": i,
                            "title": f"AI Engineer {i}",
                            "company_name": f"Co{i}",
                            "candidate_required_location": "Remote",
                            "url": f"https://remotive.com/{i}",
                            "description": "<p>FastAPI and LLM orchestration</p>",
                            "tags": ["python"],
                        }
                        for i in range(1, 4)
                    ]
                }
            )
        if "remoteok.com" in url:
            return _Resp([{"legal": "credit Remote OK"}])
        if "arbeitnow.com" in url:
            return _Resp({"data": []})
        if "jobicy.com" in url:
            return _Resp({"jobs": []})
        if "himalayas.app" in url:
            return _Resp({"jobs": []})
        if "themuse.com" in url:
            return _Resp({"results": []})
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "get", fake_get)
    first = search_jobs(
        "AI Engineer FastAPI",
        page=1,
        page_size=2,
        cache_key="pager-test",
    )
    assert first["total"] == 3
    assert first["pages"] == 2
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert len(first["jobs"]) == 2
    second = search_jobs(
        "AI Engineer FastAPI",
        page=2,
        page_size=2,
        cache_key="pager-test",
    )
    assert second["page"] == 2
    assert len(second["jobs"]) == 1
    assert second["jobs"][0]["title"] not in {j["title"] for j in first["jobs"]}
    assert remotive_hits["n"] == 1


def test_suggested_titles_are_two_most_recent():
    from backend.resume_parser import suggested_titles

    bank = {
        "roles": [
            {"title": "AI Engineer", "recency_rank": 1},
            {"title": "Python Full Stack Developer", "recency_rank": 2},
            {"title": "Intern", "recency_rank": 3},
        ]
    }
    assert suggested_titles(bank) == ["AI Engineer", "Python Full Stack Developer"]

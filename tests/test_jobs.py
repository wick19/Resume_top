import httpx

from backend.jobs import host_blocked, html_to_text, search_jobs


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
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "get", fake_get)
    result = search_jobs("AI Engineer FastAPI", limit=10)
    titles = {j["title"] for j in result["jobs"]}
    assert "AI Engineer" in titles
    assert "Backend Engineer" not in titles
    assert result["jobs"][0]["source"] == "remotive"
    assert "FastAPI" in result["jobs"][0]["description"]
    assert "not scraped" in result["note"]

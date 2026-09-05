from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

UA = "ResumeTailor/0.2 (personal job search; +https://localhost)"
TIMEOUT = 12.0

# Login-walled boards. Do not fetch these — use the extension or paste.
BLOCKED_HOSTS = (
    "linkedin.com",
    "naukri.com",
    "indeed.com",
    "glassdoor.com",
    "foundit.in",
    "monster.com",
    "cutshort.io",
)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data and data.strip():
            self.parts.append(data)


def html_to_text(value: str) -> str:
    if not value:
        return ""
    parser = _HTMLText()
    try:
        parser.feed(value)
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(query: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9+#]+", query.lower()) if len(t) >= 2]


_STOP = {
    "engineer",
    "developer",
    "remote",
    "job",
    "senior",
    "junior",
    "intern",
    "role",
    "and",
    "the",
    "for",
}


def _has_token(token: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9+#]){re.escape(token)}(?![a-z0-9+#])", text) is not None


def _matches(job: dict, tokens: list[str]) -> bool:
    if not tokens:
        return True
    distinctive = [t for t in tokens if t not in _STOP] or tokens
    blob = " ".join(
        [
            job.get("title") or "",
            job.get("company") or "",
            job.get("location") or "",
            " ".join(job.get("tags") or []),
            job.get("description") or "",
        ]
    ).lower()
    return any(_has_token(tok, blob) for tok in distinctive)


def _card(
    source: str,
    source_id: str,
    title: str,
    company: str,
    location: str,
    url: str,
    description: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    text = html_to_text(description)
    return {
        "id": f"{source}:{source_id}",
        "source": source,
        "source_id": str(source_id),
        "title": (title or "Role").strip(),
        "company": (company or "Company").strip(),
        "location": (location or "").strip(),
        "url": (url or "").strip(),
        "description": text,
        "snippet": text[:280],
        "tags": tags or [],
    }


def host_blocked(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_HOSTS)


def _get(url: str, params: dict | None = None) -> Any:
    if host_blocked(url):
        raise ValueError("That site is not fetched here. Paste the JD or use the extension.")
    response = httpx.get(
        url,
        params=params,
        timeout=TIMEOUT,
        headers={"User-Agent": UA, "Accept": "application/json"},
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.json()


def _from_remotive(query: str, limit: int) -> list[dict]:
    data = _get(
        "https://remotive.com/api/remote-jobs",
        {"search": query, "limit": max(limit, 5)},
    )
    out = []
    for row in data.get("jobs") or []:
        out.append(
            _card(
                "remotive",
                row.get("id") or row.get("url") or "",
                row.get("title") or "",
                row.get("company_name") or "",
                row.get("candidate_required_location") or "Remote",
                row.get("url") or "",
                row.get("description") or "",
                list(row.get("tags") or []),
            )
        )
    return out


def _from_remoteok(query: str) -> list[dict]:
    data = _get("https://remoteok.com/api")
    if not isinstance(data, list):
        return []
    out = []
    for row in data:
        if not isinstance(row, dict) or "legal" in row:
            continue
        title = row.get("position") or row.get("title") or ""
        out.append(
            _card(
                "remoteok",
                row.get("id") or row.get("slug") or title,
                title,
                row.get("company") or "",
                row.get("location") or "Remote",
                row.get("url") or row.get("apply_url") or "",
                row.get("description") or "",
                [str(t) for t in (row.get("tags") or [])],
            )
        )
    return out


def _from_arbeitnow(query: str) -> list[dict]:
    data = _get("https://www.arbeitnow.com/api/job-board-api", {"page": 1})
    rows = data.get("data") if isinstance(data, dict) else data
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        out.append(
            _card(
                "arbeitnow",
                row.get("slug") or row.get("url") or "",
                row.get("title") or "",
                row.get("company_name") or "",
                row.get("location") or ("Remote" if row.get("remote") else ""),
                row.get("url") or "",
                row.get("description") or "",
                [str(t) for t in (row.get("tags") or [])],
            )
        )
    return out


def search_jobs(query: str, limit: int = 20) -> dict[str, Any]:
    q = (query or "").strip()
    if len(q) < 2:
        raise ValueError("Type at least 2 characters to search.")
    tokens = _tokens(q)
    errors: list[str] = []
    found: list[dict] = []
    fetchers = (
        ("Remotive", lambda: _from_remotive(q, limit)),
        ("Remote OK", lambda: _from_remoteok(q)),
        ("Arbeitnow", lambda: _from_arbeitnow(q)),
    )
    for name, fetch in fetchers:
        try:
            found.extend(fetch())
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    matched = [job for job in found if job["description"] and _matches(job, tokens)]
    seen: set[str] = set()
    unique: list[dict] = []
    for job in matched:
        key = (job["company"].lower(), job["title"].lower(), job["source"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    unique.sort(key=lambda j: (0 if tokens and tokens[0] in j["title"].lower() else 1, j["title"]))
    return {
        "query": q,
        "jobs": unique[:limit],
        "sources": [
            {"name": "Remotive", "url": "https://remotive.com"},
            {"name": "Remote OK", "url": "https://remoteok.com"},
            {"name": "Arbeitnow", "url": "https://www.arbeitnow.com"},
        ],
        "errors": errors,
        "note": (
            "Public job-board APIs only (free, no login). "
            "LinkedIn / Naukri / Indeed are not scraped — use the extension or paste those JDs."
        ),
    }

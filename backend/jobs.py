from __future__ import annotations

import html
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from backend.textutil import skill_in_text

UA = "ResumeTailor/0.2 (personal job search; +https://localhost)"
TIMEOUT = 12.0
PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 25
POOL_MAX = 100
_CACHE_TTL = 180.0
_CACHE: dict[str, tuple[float, list[dict[str, Any]], dict[str, Any]]] = {}

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
    "with",
    "staff",
    "principal",
}

# Words that mean "this is a software job title", not a skill.
_ROLE_WORDS = {
    "engineer",
    "developer",
    "scientist",
    "architect",
    "analyst",
    "specialist",
    "programmer",
}

# Map a searched title token onto other title words in the same family.
# "AI Engineer" should still match "ML Engineer" / "LLM Engineer".
_TITLE_FAMILY: dict[str, tuple[str, ...]] = {
    "ai": ("ai", "ml", "llm", "nlp", "genai", "generative"),
    "ml": ("ml", "ai", "llm", "nlp"),
    "llm": ("llm", "ai", "generative", "nlp", "genai"),
    "nlp": ("nlp", "ai", "llm", "generative"),
    "python": ("python", "django", "flask", "fastapi"),
    "full": ("fullstack",),
    "stack": ("fullstack",),
    "fullstack": ("fullstack", "full-stack"),
    "backend": ("backend", "back-end", "api"),
    "frontend": ("frontend", "front-end", "react"),
}

_FAMILY_PHRASES = (
    "machine learning",
    "artificial intelligence",
    "deep learning",
    "generative ai",
    "full stack",
    "full-stack",
)

_SKIP_SKILLS = {
    "agile",
    "git",
    "github",
    "linux",
    "communication",
    "testing",
    "ci/cd",
}


def _has_token(token: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9+#]){re.escape(token)}(?![a-z0-9+#])", text) is not None


def _job_blob(job: dict) -> str:
    return " ".join(
        [
            job.get("title") or "",
            job.get("company") or "",
            job.get("location") or "",
            " ".join(job.get("tags") or []),
            job.get("description") or "",
        ]
    )


def parse_title_query(query: str) -> tuple[str, list[str]]:
    """Split 'AI Engineer, FastAPI, LLM' into a title plus extra keywords."""
    parts = [p.strip() for p in re.split(r"[,|/]+", (query or "").strip()) if p.strip()]
    if not parts:
        return "", []
    if len(parts) == 1:
        return parts[0], []
    return parts[0], parts[1:]


def _title_similarity(query: str, role_title: str) -> float:
    a = set(_tokens(query))
    b = set(_tokens(role_title))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def keywords_for_title(
    query: str,
    bank: dict[str, Any] | None = None,
    limit: int = 10,
) -> tuple[str, list[str]]:
    """Skills from the resume role that matches this search title.

    Clicking "AI Engineer" should use FastAPI / LLMs from that role, not
    Django from a different job. Typed extras after a comma are always kept.
    """
    title, extras = parse_title_query(query)
    found: list[str] = []
    seen: set[str] = set()

    def add(skill: str, weight: int = 1) -> None:
        key = (skill or "").strip()
        if len(key) < 2 or key.lower() in _SKIP_SKILLS or key.lower() in seen:
            return
        seen.add(key.lower())
        found.append(key)

    matched_role = ""
    roles = list((bank or {}).get("roles") or [])
    if title and roles:
        ranked = sorted(
            ((_title_similarity(title, r.get("title") or ""), r) for r in roles),
            key=lambda pair: (
                -pair[0],
                int(pair[1].get("recency_rank") or 99),
            ),
        )
        best = ranked[0][0]
        chosen = [r for score, r in ranked if score >= 0.34 and score >= best - 0.15]
        if not chosen and best > 0:
            chosen = [ranked[0][1]]
        if chosen:
            matched_role = (chosen[0].get("title") or "").strip()
        counts: dict[str, int] = {}
        for role in chosen:
            recency = int(role.get("recency_rank") or 9)
            boost = max(1, 5 - recency)
            for item in role.get("stack") or []:
                counts[item] = counts.get(item, 0) + boost
            for bullet in role.get("bullets") or []:
                for skill in bullet.get("skills") or []:
                    counts[skill] = counts.get(skill, 0) + boost * 2
        for skill, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
            add(skill)

    for extra in extras:
        add(extra)
    return matched_role, found[:limit]


def _family_needles(title_query: str) -> list[str]:
    needles: list[str] = []
    seen: set[str] = set()
    for tok in _tokens(title_query):
        if tok in _STOP or tok in _ROLE_WORDS:
            continue
        for alias in _TITLE_FAMILY.get(tok, (tok,)):
            if alias not in seen and alias not in {"full", "stack"}:
                seen.add(alias)
                needles.append(alias)
    return needles


def _fold_title(value: str) -> str:
    text = (value or "").lower()
    text = text.replace("full-stack", "full stack").replace("fullstack", "full stack")
    text = text.replace("back-end", "backend").replace("front-end", "frontend")
    return text


def _title_family_hit(job_title: str, title_query: str) -> bool:
    """True when the posting's title is in the same family as the search title."""
    title = _fold_title(job_title)
    query = _fold_title(title_query)
    if not title or not query:
        return False
    if query in title:
        return True
    for phrase in _FAMILY_PHRASES:
        if phrase in query and phrase in title:
            return True
    needles = _family_needles(title_query)
    return any(_has_token(n, title) for n in needles)


def _matched_keywords(job: dict, keywords: list[str]) -> list[str]:
    blob = _job_blob(job)
    hits: list[str] = []
    seen: set[str] = set()
    for skill in keywords:
        key = skill.lower()
        if key in seen:
            continue
        if skill_in_text(skill, blob):
            seen.add(key)
            hits.append(skill)
    return hits


def score_job(
    job: dict,
    title_query: str,
    keywords: list[str],
) -> tuple[int, int, list[str]] | None:
    """Return (title_score, keyword_hits, matched_keywords) or None to drop.

    1. Title family first: "AI Engineer" keeps ML/LLM Engineer, drops
       "Office Manager" even if the JD mentions AI once.
    2. Resume keywords next: a Backend Engineer posting still ranks if it
       asks for several skills from that resume role (FastAPI + LLMs).
    """
    job_title = job.get("title") or ""
    hits = _matched_keywords(job, keywords)
    family = _title_family_hit(job_title, title_query)
    role_in_job = any(_has_token(w, job_title.lower()) for w in _ROLE_WORDS)
    if family:
        title_score = 3 if role_in_job else 2
    elif role_in_job and len(hits) >= 2:
        title_score = 1
    elif len(hits) >= 3:
        title_score = 1
    else:
        return None
    return title_score, len(hits), hits


def _matches(job: dict, tokens: list[str]) -> bool:
    if not tokens:
        return True
    distinctive = [t for t in tokens if t not in _STOP] or tokens
    blob = _job_blob(job).lower()
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


def google_jobs_url(
    title: str,
    location: str = "",
    extras: list[str] | None = None,
    keywords: list[str] | None = None,
) -> str:
    """Open Google's Jobs tab for the searched title — not a stuffed skill list.

    Resume keywords (Alembic, JWT, API) belong to *our* ranking. Google Jobs
    matches recruiter-style queries: "AI Engineer in Bengaluru". The word
    "jobs" is omitted because udm=8 is already the Jobs vertical.
    """
    del keywords  # callers used to pass resume stack; that emptied the Jobs tab
    title = re.sub(r"\s+", " ", (title or "").strip()) or "software engineer"
    parts = [title]
    for extra in extras or []:
        extra = re.sub(r"\s+", " ", extra.strip())
        if extra and extra.lower() not in title.lower():
            parts.append(extra)
            if len(parts) >= 2:  # title + at most one typed extra
                break
    loc = re.sub(r"\s+", " ", (location or "").strip())
    if loc and loc.lower() not in " ".join(parts).lower():
        parts.append(f"in {loc}")
    q = " ".join(parts)
    params = f"udm=8&q={quote_plus(q)}&hl=en"
    if loc and loc.lower() in _INDIA_PLACES:
        params += "&gl=in"
    return f"https://www.google.com/search?{params}"


_INDIA_PLACES = {
    "bengaluru", "bangalore", "chennai", "hyderabad", "mumbai", "pune",
    "delhi", "new delhi", "noida", "gurgaon", "gurugram", "kolkata",
    "ahmedabad", "kochi", "india", "karnataka", "tamil nadu", "maharashtra",
}

# Metro names Google Jobs actually has inventory for (not a neighbourhood).
_METROS: list[tuple[str, str]] = [
    ("bengaluru", "Bengaluru"),
    ("bangalore", "Bengaluru"),
    ("chennai", "Chennai"),
    ("hyderabad", "Hyderabad"),
    ("mumbai", "Mumbai"),
    ("pune", "Pune"),
    ("gurugram", "Gurugram"),
    ("gurgaon", "Gurugram"),
    ("noida", "Noida"),
    ("delhi", "Delhi"),
    ("hattiesburg", "Hattiesburg, MS"),
    ("frisco", "Dallas, TX"),
    ("austin", "Austin, TX"),
    ("seattle", "Seattle"),
    ("san francisco", "San Francisco"),
    ("new york", "New York"),
    ("london", "London"),
    ("berlin", "Berlin"),
    ("toronto", "Toronto"),
]


def google_location(bank: dict[str, Any] | None) -> str:
    """City-level location from the resume, never a GPS neighbourhood."""
    if not bank:
        return ""
    roles = sorted(
        bank.get("roles") or [],
        key=lambda r: int(r.get("recency_rank") or 99),
    )
    blobs: list[str] = []
    for role in roles[:2]:
        blobs.append(f"{role.get('location') or ''} {role.get('company') or ''}")
    profile = bank.get("profile") or {}
    blobs.append(profile.get("location") or "")
    for blob in blobs:
        low = blob.lower()
        for needle, city in _METROS:
            if needle in low:
                return city
    return ""


def _from_jobicy(query: str, limit: int) -> list[dict]:
    tag = re.sub(r"\s+", " ", query).strip()[:50]
    if len(tag) < 3:
        tag = "software"
    data = _get(
        "https://jobicy.com/api/v2/remote-jobs",
        {"count": min(max(limit, 5), 100), "tag": tag},
    )
    out = []
    for row in data.get("jobs") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            _card(
                "jobicy",
                row.get("id") or row.get("jobSlug") or "",
                row.get("jobTitle") or "",
                row.get("companyName") or "",
                row.get("jobGeo") or "Remote",
                row.get("url") or "",
                row.get("jobDescription") or row.get("jobExcerpt") or "",
                [str(t) for t in (row.get("jobIndustry") or [])],
            )
        )
    return out


def _from_himalayas(query: str) -> list[dict]:
    data = _get(
        "https://himalayas.app/jobs/api/search",
        {"q": query, "page": 1, "sort": "relevant"},
    )
    rows = data.get("jobs") if isinstance(data, dict) else data
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        company = ""
        if isinstance(row.get("company"), dict):
            company = row["company"].get("name") or ""
        company = company or row.get("companyName") or row.get("company") or ""
        url = (
            row.get("applicationLink")
            or row.get("url")
            or row.get("guid")
            or ""
        )
        out.append(
            _card(
                "himalayas",
                row.get("id") or url or row.get("title") or "",
                row.get("title") or row.get("jobTitle") or "",
                str(company),
                row.get("location") or row.get("excerpt") or "Remote",
                str(url),
                row.get("description") or row.get("excerpt") or "",
                [str(t) for t in (row.get("parentCategories") or row.get("categories") or [])],
            )
        )
    return out


def _from_themuse(query: str) -> list[dict]:
    data = _get(
        "https://www.themuse.com/api/public/jobs",
        {"page": 0, "descending": "true"},
    )
    rows = data.get("results") if isinstance(data, dict) else []
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        company = ""
        if isinstance(row.get("company"), dict):
            company = row["company"].get("name") or ""
        locs = row.get("locations") or []
        location = ""
        if locs and isinstance(locs[0], dict):
            location = locs[0].get("name") or ""
        refs = row.get("refs") if isinstance(row.get("refs"), dict) else {}
        url = refs.get("landing_page") or ""
        out.append(
            _card(
                "themuse",
                row.get("id") or url or "",
                row.get("name") or "",
                company,
                location,
                url,
                row.get("contents") or "",
                [c.get("name") for c in (row.get("categories") or []) if isinstance(c, dict)],
            )
        )
    return out


PUBLIC_SOURCES = [
    {"name": "Remotive", "url": "https://remotive.com", "kind": "api"},
    {"name": "Remote OK", "url": "https://remoteok.com", "kind": "api"},
    {"name": "Arbeitnow", "url": "https://www.arbeitnow.com", "kind": "api"},
    {"name": "Jobicy", "url": "https://jobicy.com", "kind": "api"},
    {"name": "Himalayas", "url": "https://himalayas.app", "kind": "api"},
    {"name": "The Muse", "url": "https://www.themuse.com", "kind": "api"},
    {"name": "Google Jobs", "url": "https://www.google.com/search?ibp=htl;jobs", "kind": "link"},
]


def search_jobs(
    query: str,
    limit: int | None = None,
    bank: dict[str, Any] | None = None,
    page: int = 1,
    page_size: int | None = None,
    cache_key: str = "",
) -> dict[str, Any]:
    q = (query or "").strip()
    if len(q) < 2:
        raise ValueError("Type at least 2 characters to search.")
    page = max(1, int(page or 1))
    # `limit` used to mean "how many cards to return". Keep that as page size
    # when the caller does not pass page_size. The ranked pool is larger so
    # later pages have real jobs instead of a hard 15-cut.
    size = page_size if page_size is not None else (limit if limit is not None else PAGE_SIZE_DEFAULT)
    size = min(max(int(size), 1), PAGE_SIZE_MAX)
    pool = min(POOL_MAX, max(limit or POOL_MAX, page * size))

    title_query, extras = parse_title_query(q)
    matched_role, keywords = keywords_for_title(q, bank)
    for extra in extras:
        if extra.lower() not in {k.lower() for k in keywords}:
            keywords.append(extra)

    meta = {
        "query": q,
        "title": title_query or q,
        "matched_role": matched_role,
        "keywords": keywords[:10],
        "google_jobs_url": google_jobs_url(
            title_query or q,
            location=google_location(bank),
            extras=extras,
        ),
        "sources": PUBLIC_SOURCES,
        "note": (
            "Six free public job APIs (no key). Google Jobs is opened in a new tab — "
            "Google does not offer a free whole-internet scrape API. "
            "LinkedIn / Naukri / Indeed are not scraped — use the extension or paste those JDs."
        ),
    }
    unique, errors = _ranked_jobs(
        q,
        title_query,
        keywords,
        pool=pool,
        cache_key=cache_key,
    )
    total = len(unique)
    pages = max(1, math.ceil(total / size)) if total else 1
    if page > pages:
        page = pages
    start = (page - 1) * size
    return {
        **meta,
        "jobs": unique[start : start + size],
        "total": total,
        "page": page,
        "page_size": size,
        "pages": pages,
        "errors": errors,
    }


def _ranked_jobs(
    q: str,
    title_query: str,
    keywords: list[str],
    pool: int,
    cache_key: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    key = f"{cache_key}::{q.lower()}" if cache_key else ""
    now = time.monotonic()
    if key:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1], hit[2].get("errors") or []
        stale = [k for k, (ts, *_rest) in _CACHE.items() if now - ts >= _CACHE_TTL]
        for old in stale:
            _CACHE.pop(old, None)

    tokens = _tokens(q)
    errors: list[str] = []
    found: list[dict] = []
    fetchers = (
        ("Remotive", lambda: _from_remotive(title_query or q, pool)),
        ("Remote OK", lambda: _from_remoteok(q)),
        ("Arbeitnow", lambda: _from_arbeitnow(q)),
        ("Jobicy", lambda: _from_jobicy(title_query or q, pool)),
        ("Himalayas", lambda: _from_himalayas(title_query or q)),
        ("The Muse", lambda: _from_themuse(q)),
    )
    with ThreadPoolExecutor(max_workers=6) as pool_exec:
        futs = {pool_exec.submit(fn): name for name, fn in fetchers}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                found.extend(fut.result())
            except Exception as exc:
                errors.append(f"{name}: {exc}")
    ranked: list[tuple[int, int, dict]] = []
    for job in found:
        if not job.get("description"):
            continue
        scored = score_job(job, title_query or q, keywords)
        if scored is None:
            if keywords or not _matches(job, tokens):
                continue
            scored = (1, 0, [])
        title_score, kw_count, hits = scored
        job = dict(job)
        job["matched_keywords"] = hits
        job["title_match"] = title_score >= 2
        ranked.append((title_score, kw_count, job))
    seen: set[str] = set()
    unique: list[dict] = []
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]["title"]))
    for _title_score, _kw, job in ranked:
        job_key = (job["company"].lower(), job["title"].lower(), job["source"])
        if job_key in seen:
            continue
        seen.add(job_key)
        unique.append(job)
        if len(unique) >= pool:
            break
    if key:
        _CACHE[key] = (now, unique, {"errors": errors})
        if len(_CACHE) > 32:
            oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
            _CACHE.pop(oldest, None)
    return unique, errors

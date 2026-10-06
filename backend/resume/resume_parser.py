"""Turn an uploaded resume (PDF / DOCX / TXT) into a fact bank.

The fact bank is this app's source of truth: the aligner may only select,
reorder, and rephrase what is in it — it can never invent a new employer,
degree, or metric. So when a user uploads their resume, we parse it into the
same schema `data/fact_bank.json` uses.

Two paths:
  * LLM path (when an OpenAI-compatible key is set): the model extracts the
    structure, and we still normalise + validate the shape.
  * Heuristic path (always available, used in tests and offline): section and
    bullet detection with regexes.

Nothing here fabricates content. Percentages found in a bullet are locked so
later rewrites cannot drop or invent numbers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.textutil import percents, skill_in_text

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
URL_RE = re.compile(r"https?://[^\s|)]+", re.I)
DATE_RANGE_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"|\d{1,2}/\d{4}|\d{4})\s*[–\-—to]+\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"|\d{1,2}/\d{4}|\d{4}|Present|Current)",
    re.I,
)
BULLET_RE = re.compile(r"^\s*[•●▪‣∙\-\*\u2013\u2022]\s*(.*)")

SECTION_HEADS = {
    "summary": re.compile(r"^\s*(professional\s+)?(summary|profile|objective|about)\s*$", re.I),
    "experience": re.compile(r"^\s*(professional\s+|work\s+)?(experience|employment|work history)\s*$", re.I),
    "projects": re.compile(
        r"^\s*(selected\s+)?(engineering\s+)?(personal\s+)?(academic\s+)?projects?\s*$",
        re.I,
    ),
    "education": re.compile(r"^\s*education\s*$", re.I),
    "skills": re.compile(
        r"^\s*(?:core|key|technical|professional|areas?\s+of)?\s*"
        r"(?:skills|expertise|competenc(?:y|ies)|technologies|technology|tech\s+stack|"
        r"tools(?:\s*(?:&|and)\s+(?:technologies|platforms))?)\s*$",
        re.I,
    ),
    "achievements": re.compile(r"^\s*(key\s+)?achievements?\s*$", re.I),
}

TITLE_HINT = re.compile(
    r"\b(engineer|developer|intern|ambassador|manager|analyst|scientist|"
    r"architect|specialist|consultant|lead|programmer|designer|"
    r"administrator|officer|associate|director|founder|researcher|"
    r"executive|recruiter|coordinator|generalist|partner|"
    r"human resources|talent acquisition)\b",
    re.I,
)
LOCATION_TAIL_RE = re.compile(
    r"\s+("
    r"Bengaluru|Bangalore|Chennai|Pune|Hyderabad|Mumbai|Delhi|New Delhi|"
    r"Noida|Gurgaon|Gurugram|Kolkata|Ahmedabad|Jaipur|Frisco|"
    r"Remote|India|USA|UK|United States"
    r")\b.*$",
    re.I,
)
BULLET_VERB_RE = re.compile(
    r"^(Managing|Driving|Ensuring|Supporting|Collaborating|Developed|Building|"
    r"Built|Led|Successfully|Coordinated|Reviewed|Conducted|Utilized|Guided|"
    r"Evaluated|Extended|Maintained|Generated|Determined|Sourced|Planned|"
    r"Addressing|Overseeing|Tracking|Drafting|Serving|Joined|Designed|"
    r"Contributed|Created|Implemented|Worked)\b",
    re.I,
)
SCHOOL_RE = re.compile(
    r"\b(university|institute|college|school|academy|polytechnic)\b",
    re.I,
)
MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"

# A small built-in vocabulary so bullets on an unknown resume still get tagged
# with recognisable skills (used to ground what a rewrite may say).
COMMON_TECH = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
    "Ruby", "PHP", "Scala", "Kotlin", "Swift", "SQL", "R",
    "FastAPI", "Django", "Flask", "Spring", "Node.js", "Express", "React",
    "Next.js", "Angular", "Vue.js", "Tailwind CSS", "HTML5", "CSS3",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
    "DynamoDB", "Oracle", "SQLAlchemy", "Alembic",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Helm",
    "Jenkins", "GitHub Actions", "CI/CD", "Linux", "Kafka", "Spark", "Airflow",
    "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy", "LLMs",
    "Generative AI", "NLP", "RAG", "LangChain", "REST APIs", "GraphQL", "gRPC",
    "Microservices", "OAuth2", "JWT", "Celery", "Pydantic",
]


def extract_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return _normalize_pdf_text(
            "\n".join((page.extract_text() or "") for page in reader.pages)
        )
    if suffix == ".docx":
        import docx

        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported resume format: {suffix or 'unknown'} (use PDF, DOCX, or TXT)")


def _clean(line: str) -> str:
    return line.strip(" \t•-*\u2013").strip()


def _normalize_pdf_text(text: str) -> str:
    """Undo common pypdf artefacts: split letters and dates glued to titles."""
    text = (text or "").replace("\u00ad", "")
    # "•Managing" (glyph, no space) and "F ull" / "V oice".
    text = re.sub(r"([•●▪‣∙\u2022])(\S)", r"\1 \2", text)
    text = re.sub(r"\b([B-HJ-Z]) ([a-z]{2,})", r"\1\2", text)
    # "UA V" all-caps acronym split; "SUMMAR Y" / "EDUCA TION".
    text = re.sub(r"\b([A-Z]{2}) ([A-Z])\b", r"\1\2", text)
    text = re.sub(r"\b([A-Z]{4,}) ([A-Z])\b", r"\1\2", text)
    text = re.sub(r"\b(PLA) (TFORMS)\b", r"\1\2", text)
    text = re.sub(r"\b(EDUCA) (TION)\b", r"\1\2", text)
    # "DeveloperFeb 2024" / "InternJun 2019"
    text = re.sub(rf"([A-Za-z])({MONTH_RE}\.?\s*\d{{4}})", r"\1 \2", text)
    return text


def _looks_like_sentence(line: str) -> bool:
    """Bullets and wrap lines, not a job title / employer heading."""
    clean = _clean(line)
    if not clean:
        return False
    if clean.endswith(".") or clean.endswith(";"):
        return True
    if len(clean) > 90 and not DATE_RANGE_RE.search(clean):
        return True
    if BULLET_VERB_RE.match(clean):
        return True
    if clean[0].islower():
        return True
    return False


def _is_page_number(line: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}", _clean(line)))


def _is_entry_header(line: str) -> bool:
    """True for a job/project/school heading, not a wrapped bullet fragment."""
    raw = (line or "").strip()
    if not raw or _is_page_number(raw) or BULLET_RE.match(raw):
        return False
    clean = _clean(raw)
    if not clean or len(clean) > 140:
        return False
    if _looks_like_sentence(clean):
        return False
    if DATE_RANGE_RE.search(clean):
        return True
    if "|" in clean:
        return True
    if clean[0].isupper() and TITLE_HINT.search(clean) and len(clean) < 80:
        return True
    if clean[0].isupper() and SCHOOL_RE.search(clean) and len(clean) < 80:
        return True
    return False


def _header_has_dates(entry: dict[str, Any]) -> bool:
    return bool(DATE_RANGE_RE.search(" ".join(entry.get("header") or [])))


def _parse_profile(lines: list[str]) -> dict[str, Any]:
    text = "\n".join(lines)
    email = (EMAIL_RE.search(text) or [""])[0] if EMAIL_RE.search(text) else ""
    urls = URL_RE.findall(text)
    linkedin = next((u for u in urls if "linkedin" in u.lower()), "")
    github = next((u for u in urls if "github" in u.lower()), "")
    portfolio = next((u for u in urls if u not in (linkedin, github)), "")
    phone = ""
    for match in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", match)
        if 8 <= len(digits) <= 15:
            phone = match.strip()
            break
    name = ""
    for line in lines[:6]:
        clean = _clean(line)
        if not clean or "@" in clean or clean.lower().startswith("http"):
            continue
        if any(ch.isdigit() for ch in clean):
            continue
        if 2 <= len(clean) <= 60:
            name = clean
            break
    return {
        "name": name or "Your Name",
        "phone": phone,
        "email": email,
        "linkedin": linkedin,
        "linkedin_label": "LinkedIn",
        "github": github,
        "github_label": "GitHub",
        "portfolio": portfolio,
        "portfolio_label": "Portfolio",
        "location": "",
    }


def _sectionize(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {k: [] for k in SECTION_HEADS}
    sections["_header"] = []
    current = "_header"
    for line in lines:
        matched = None
        for name, pattern in SECTION_HEADS.items():
            if pattern.match(line):
                matched = name
                break
        if matched:
            current = matched
            continue
        sections[current].append(line)
    return sections


def _split_entries(lines: list[str]) -> list[dict[str, Any]]:
    """Group lines into entries.

    PDF extractors wrap bullets onto their own lines without a leading bullet.
    Those continuations must join the previous bullet — they are not new jobs.
    A new entry starts only on a real heading (dates, title words, school, or
    `name | stack`), or a second dated/school line when the current header
    already has dates (two education rows with no bullets).
    """
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        if not line.strip() or _is_page_number(line):
            continue
        bullet = BULLET_RE.match(line)
        if bullet:
            if current is None:
                current = {"header": [], "bullets": []}
            text = bullet.group(1).strip()
            if text:
                current["bullets"].append(text)
            continue
        clean = _clean(line)
        if not clean:
            continue
        if _is_entry_header(clean):
            if current is None:
                current = {"header": [clean], "bullets": []}
            elif current["bullets"]:
                entries.append(current)
                current = {"header": [clean], "bullets": []}
            elif _header_has_dates(current) and DATE_RANGE_RE.search(clean):
                entries.append(current)
                current = {"header": [clean], "bullets": []}
            elif (
                _header_has_dates(current)
                and SCHOOL_RE.search(clean)
                and not TITLE_HINT.search(clean)
                and not any(TITLE_HINT.search(h) for h in current["header"])
            ):
                entries.append(current)
                current = {"header": [clean], "bullets": []}
            else:
                current["header"].append(clean)
        elif current and current["bullets"]:
            current["bullets"][-1] = f"{current['bullets'][-1]} {clean}".strip()
        elif current:
            current["header"].append(clean)
        else:
            current = {"header": [clean], "bullets": []}
    if current and (current["header"] or current["bullets"]):
        entries.append(current)
    return entries


def _split_title_company(text: str) -> tuple[str, str]:
    text = DATE_RANGE_RE.sub("", text).strip(" ,–-|")
    parts = [p.strip() for p in re.split(r"\s{2,}|\s+\|\s+", text) if p.strip()]
    if len(parts) >= 2:
        return re.sub(r"\s+", " ", parts[0]).strip(), re.sub(r"\s+", " ", parts[1]).strip()
    return re.sub(r"\s+", " ", text).strip(), ""


def _peel_location(text: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", text or "").strip(" ,–-|")
    if not text:
        return "", ""
    m = LOCATION_TAIL_RE.search(text)
    if m:
        return text[: m.start()].strip(" ,"), text[m.start() :].strip(" ,")
    if "," in text:
        left, _, right = text.partition(",")
        if TITLE_HINT.search(left) or len(left.split()) <= 6:
            return left.strip(), right.strip()
    return text, ""


def _title_company_location(header_lines: list[str]) -> tuple[str, str, str, str, str]:
    heading = [h for h in header_lines if not _looks_like_sentence(h) and not _is_page_number(h)]
    if not heading:
        heading = list(header_lines)
    blob = " ".join(heading)
    start, end = _dates_from(blob)
    dated = next((h for h in heading if DATE_RANGE_RE.search(h)), "")
    titled = next(
        (
            h
            for h in heading
            if TITLE_HINT.search(h) and DATE_RANGE_RE.search(h)
        ),
        None,
    ) or next(
        (
            h
            for h in heading
            if TITLE_HINT.search(h) and not _looks_like_sentence(h)
        ),
        None,
    ) or dated or (heading[0] if heading else "")
    title, company = _split_title_company(titled)
    title, title_loc = _peel_location(title)
    others = [h for h in heading if h != titled]
    company_blob = DATE_RANGE_RE.sub("", " ".join(others)).strip(" ,–-|")
    if not company and company_blob:
        company, location = _peel_location(company_blob)
        if not location:
            parts = [p.strip() for p in company_blob.split(",") if p.strip()]
            company = re.sub(r"\s+", " ", parts[0]).strip() if parts else company
            location = ", ".join(parts[1:])
    else:
        _, location = _peel_location(company_blob) if company_blob else ("", "")
        if company:
            company, loc2 = _peel_location(company)
            location = loc2 or location
    location = title_loc or location
    return title, company, location, start, end


def _entry_bullets(entry: dict[str, Any]) -> list[str]:
    """Move sentence-like header leftovers into bullets and join wrap fragments."""
    bullets = [b.strip() for b in entry.get("bullets") or [] if b.strip()]
    keep: list[str] = []
    for h in entry.get("header") or []:
        if _is_page_number(h):
            continue
        if _looks_like_sentence(h) or (
            len(h) > 85 and not DATE_RANGE_RE.search(h) and not TITLE_HINT.search(h[:40])
        ):
            bullets.append(h.strip())
        else:
            keep.append(h)
    entry["header"] = keep
    joined: list[str] = []
    for text in bullets:
        if joined and text and text[0].islower():
            joined[-1] = f"{joined[-1]} {text}".strip()
        else:
            joined.append(text)
    return joined


def _dates_from(text: str) -> tuple[str, str]:
    m = DATE_RANGE_RE.search(text)
    if not m:
        return "", ""
    return m.group(1).strip(), m.group(2).strip()


def _skills_for(text: str, vocab: list[str]) -> list[str]:
    return [term for term in vocab if skill_in_text(term, text)]


def _bullet_nodes(prefix: str, bullets: list[str], vocab: list[str]) -> list[dict[str, Any]]:
    nodes = []
    for i, text in enumerate(bullets, 1):
        text = text.strip()
        if not text:
            continue
        nodes.append({
            "id": f"{prefix}.b{i}",
            "text": text,
            "skills": _skills_for(text, vocab),
            "locked_numbers": sorted(percents(text)),
        })
    return nodes


def _build_skill_groups(skill_lines: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    groups: list[dict[str, Any]] = []
    vocab: list[str] = []
    idx = 0
    loose: list[str] = []
    for line in skill_lines:
        clean = _clean(line)
        if not clean:
            continue
        if ":" in clean:
            label, _, rest = clean.partition(":")
            items = [x.strip() for x in re.split(r"[,;|]", rest) if x.strip()]
            if items:
                groups.append({"id": f"skills.{idx}", "label": label.strip(), "items": items})
                idx += 1
                vocab.extend(items)
        else:
            loose.extend(x.strip() for x in re.split(r"[,;|]", clean) if x.strip())
    if loose:
        groups.append({"id": f"skills.{idx}", "label": "Skills", "items": loose})
        vocab.extend(loose)
    return groups, vocab


def _attach_achievements(
    roles: list[dict[str, Any]], lines: list[str], vocab: list[str]
) -> None:
    if not lines or not roles:
        return
    texts: list[str] = []
    for entry in _split_entries(lines):
        texts.extend(_entry_bullets(entry))
    for text in texts:
        target = None
        low = text.lower()
        for role in roles:
            company = (role.get("company") or "").split(",")[0].strip()
            token = company.split()[0].rstrip(".,") if company else ""
            if token and len(token) >= 4 and token.lower() in low:
                target = role
                break
        if target is None:
            target = roles[0]
        extra = _bullet_nodes(target["id"], [text], vocab)
        target.setdefault("bullets", []).extend(extra)


def build_fact_bank_heuristic(text: str) -> dict[str, Any]:
    lines = [ln for ln in _normalize_pdf_text(text or "").splitlines()]
    sections = _sectionize(lines)
    profile = _parse_profile(sections["_header"] + lines[:8])

    skill_groups, skill_vocab = _build_skill_groups(sections["skills"])
    vocab = list(dict.fromkeys(skill_vocab + COMMON_TECH))

    # Roles
    roles: list[dict[str, Any]] = []
    for i, entry in enumerate(_split_entries(sections["experience"])):
        bullets = _entry_bullets(entry)
        header_lines = entry["header"]
        if not header_lines and not bullets:
            continue
        title, company, location, start, end = _title_company_location(header_lines)
        if not title and not bullets:
            continue
        if _looks_like_sentence(title):
            continue
        roles.append({
            "id": f"role.{i}",
            "company": company,
            "title": title,
            "start": start,
            "end": end,
            "location": location,
            "include_by_default": True,
            "recency_rank": i + 1,
            "domains": [],
            "stack": [],
            "bullets": _bullet_nodes(f"role.{i}", bullets, vocab),
        })
    _attach_achievements(roles, sections.get("achievements") or [], vocab)

    # Projects
    projects: list[dict[str, Any]] = []
    for i, entry in enumerate(_split_entries(sections["projects"])):
        bullets = _entry_bullets(entry)
        header = " ".join(entry["header"]).strip()
        if not header and not bullets:
            continue
        name, _, stack_str = header.partition("|")
        stack = [s.strip() for s in re.split(r"[,;]", stack_str) if s.strip()]
        projects.append({
            "id": f"project.{i}",
            "name": name.strip() or f"Project {i + 1}",
            "include_by_default": True,
            "domains": [],
            "stack": stack,
            "bullets": _bullet_nodes(f"project.{i}", bullets, vocab),
        })

    # Education
    education: list[dict[str, Any]] = []
    for i, entry in enumerate(_split_entries(sections["education"])):
        header_lines = entry["header"] + entry["bullets"]
        blob = " ".join(header_lines).strip()
        if not blob:
            continue
        start, end = _dates_from(blob)
        blob_wo = DATE_RANGE_RE.sub("", blob).strip(" ,–-|")
        parts = [p.strip() for p in re.split(r"\s{2,}|\||,", blob_wo) if p.strip()]
        education.append({
            "id": f"edu.{i}",
            "school": parts[0] if parts else blob_wo,
            "location": parts[-1] if len(parts) > 2 else "",
            "credential": parts[1] if len(parts) > 1 else "",
            "start": start,
            "end": end,
        })

    summary = " ".join(_clean(l) for l in sections["summary"] if l.strip()).strip()

    bank = {
        "profile": profile,
        "default_summary": summary,
        "roles": roles,
        "projects": projects,
        "education": education,
        "skill_groups": skill_groups,
        "synonyms": {},
    }
    return normalize_bank(bank)


def normalize_bank(bank: dict[str, Any]) -> dict[str, Any]:
    """Guarantee required keys, ids, and locked numbers so the rest of the
    pipeline (scoring, validator, compiler) can consume it safely."""
    bank.setdefault("profile", {})
    profile = bank["profile"]
    for key, default in (
        ("name", "Your Name"), ("phone", ""), ("email", ""),
        ("linkedin", ""), ("linkedin_label", "LinkedIn"),
        ("github", ""), ("github_label", "GitHub"),
        ("portfolio", ""), ("portfolio_label", "Portfolio"), ("location", ""),
    ):
        profile.setdefault(key, default)

    bank.setdefault("default_summary", "")
    bank.setdefault("synonyms", {})
    bank.setdefault("roles", [])
    bank.setdefault("projects", [])
    bank.setdefault("education", [])
    bank.setdefault("skill_groups", [])

    vocab = list(dict.fromkeys(
        [item for g in bank.get("skill_groups", []) for item in g.get("items", [])]
        + COMMON_TECH
    ))

    for ri, role in enumerate(bank.get("roles", [])):
        role.setdefault("id", f"role.{ri}")
        role.setdefault("company", "")
        role.setdefault("title", "")
        role.setdefault("start", "")
        role.setdefault("end", "")
        role.setdefault("location", "")
        role.setdefault("include_by_default", True)
        role.setdefault("recency_rank", ri + 1)
        role.setdefault("domains", [])
        role.setdefault("stack", [])
        for bi, bullet in enumerate(role.get("bullets", []), 1):
            bullet.setdefault("id", f"{role['id']}.b{bi}")
            bullet.setdefault("text", "")
            bullet.setdefault("skills", _skills_for(bullet.get("text", ""), vocab))
            bullet["locked_numbers"] = sorted(percents(bullet.get("text", "")))

    for pi, project in enumerate(bank.get("projects", [])):
        project.setdefault("id", f"project.{pi}")
        project.setdefault("name", f"Project {pi + 1}")
        project.setdefault("include_by_default", True)
        project.setdefault("domains", [])
        project.setdefault("stack", [])
        for bi, bullet in enumerate(project.get("bullets", []), 1):
            bullet.setdefault("id", f"{project['id']}.b{bi}")
            bullet.setdefault("text", "")
            bullet.setdefault("skills", _skills_for(bullet.get("text", ""), vocab))
            bullet["locked_numbers"] = sorted(percents(bullet.get("text", "")))

    for ei, edu in enumerate(bank.get("education", [])):
        edu.setdefault("id", f"edu.{ei}")
        for key in ("school", "location", "credential", "start", "end"):
            edu.setdefault(key, "")

    for gi, group in enumerate(bank.get("skill_groups", [])):
        group.setdefault("id", f"skills.{gi}")
        group.setdefault("label", "Skills")
        group.setdefault("items", [])

    fill_skill_groups(bank)
    return bank


def fill_skill_groups(bank: dict[str, Any]) -> dict[str, Any]:
    """Keep a skills section whenever the resume already names tools.

    Uploads sometimes store those tools on jobs only. The PDF prints
    skill_groups, so an empty list would leave Technical Expertise blank.
    Nothing is added that is not already on a role, project, or skills line.
    """
    kept = [group for group in bank.get("skill_groups") or [] if group.get("items")]
    if kept:
        bank["skill_groups"] = kept
        return bank

    items: list[str] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        text = re.sub(r"\s+", " ", str(raw or "").strip(" ,;|"))
        if len(text) < 2 or len(text) > 60:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        items.append(text)

    for role in bank.get("roles") or []:
        for item in role.get("stack") or []:
            add(item)
        for bullet in role.get("bullets") or []:
            for item in bullet.get("skills") or []:
                add(item)
    for project in bank.get("projects") or []:
        for item in project.get("stack") or []:
            add(item)
        for bullet in project.get("bullets") or []:
            for item in bullet.get("skills") or []:
                add(item)
    if items:
        bank["skill_groups"] = [
            {"id": "skills.0", "label": "Technical Skills", "items": items}
        ]
    else:
        bank["skill_groups"] = []
    return bank


def bank_summary(bank: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": bank.get("profile", {}).get("name", ""),
        "roles": len(bank.get("roles", [])),
        "projects": len(bank.get("projects", [])),
        "education": len(bank.get("education", [])),
        "skill_groups": len(bank.get("skill_groups", [])),
        "bullets": sum(len(r.get("bullets", [])) for r in bank.get("roles", []))
        + sum(len(p.get("bullets", [])) for p in bank.get("projects", [])),
        "suggested_titles": suggested_titles(bank),
    }


def suggested_titles(bank: dict[str, Any], n: int = 2) -> list[str]:
    """Most recent unique job titles from the fact bank (search chips)."""
    roles = list(bank.get("roles") or [])
    roles.sort(key=lambda r: int(r.get("recency_rank") or 99))
    out: list[str] = []
    seen: set[str] = set()
    for role in roles:
        title = re.sub(r"\s+", " ", (role.get("title") or "").strip())
        if len(title) < 3 or not TITLE_HINT.search(title):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
        if len(out) >= n:
            break
    return out


def _llm_fact_bank(text: str) -> dict[str, Any] | None:
    from backend.llm.llm import chat, llm_available

    if not llm_available():
        return None
    try:
        system = (
            "You extract a resume into strict JSON. Do NOT invent anything. "
            "Only use content present in the resume text. Keep exact numbers. "
            "skill_groups must list every tool the resume already names. "
            "Read them from any layout: a section titled Skills, Technical Skills, "
            "Technical Expertise, Core Competencies, Areas of Expertise, Technologies, "
            "Tools, or Tech Stack; a 'Label: a, b, c' line; a comma or pipe list; a sidebar. "
            "Keep the resume's own category labels. If there is no skills section, put the "
            "tools named in roles and projects into one group labeled Technical Skills. "
            "Do not leave skill_groups empty when those tools are written on the resume. "
            "Schema: {profile:{name,phone,email,linkedin,github,portfolio,location},"
            "default_summary, roles:[{company,title,start,end,location,stack:[],"
            "bullets:[{text}]}], projects:[{name,stack:[],bullets:[{text}]}], "
            "education:[{school,location,credential,start,end}], "
            "skill_groups:[{label,items:[]}]}. Return JSON only."
        )
        raw = chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": text[:12000]},
            ],
            temperature=0.0,
        )
        data = json.loads(raw)
        if not data.get("roles") and not data.get("education"):
            return None
        return normalize_bank(data)
    except Exception:
        return None


def build_fact_bank(text: str, prefer_llm: bool = True) -> tuple[dict[str, Any], str]:
    """Return (bank, mode) where mode is 'llm' or 'heuristic'."""
    if prefer_llm:
        llm = _llm_fact_bank(text)
        if llm is not None:
            return llm, "llm"
    return build_fact_bank_heuristic(text), "heuristic"

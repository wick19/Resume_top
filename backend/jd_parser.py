"""Structured JD parsing.

Turns raw job-description text into a structured object:
    title, seniority, must-have skills, nice-to-have skills, domains, keywords.

This is deterministic. Requirement phrases are read from the job text itself,
then compared with the fact bank. Nothing here is a list of tools for one career.
"""

from __future__ import annotations

import re
from typing import Any

from backend.fact_bank import all_skills, load_bank
from backend.neighbors import along_the_lines
from backend.textutil import skill_in_text

SENIORITY_PATTERNS = [
    ("intern", r"\bintern(ship)?\b"),
    ("junior", r"\b(junior|jr\.?|entry[- ]level|graduate|associate)\b"),
    ("staff", r"\b(staff|principal|distinguished)\b"),
    ("lead", r"\b(lead|head of|manager|director)\b"),
    ("senior", r"\b(senior|sr\.?|experienced)\b"),
    ("mid", r"\b(mid[- ]level|mid)\b"),
]

# Headings that separate hard requirements from nice-to-haves.
_MUST_HEAD = re.compile(
    r"(requirements|qualifications|must[- ]?have|what you.ll need|"
    r"what we.re looking for|you have|minimum qualifications|basic qualifications|"
    r"responsibilities|who you are)",
    re.I,
)
_NICE_HEAD = re.compile(
    r"(nice[- ]?to[- ]?have|preferred|bonus|plus|good to have|"
    r"nice if|desirable|preferred qualifications|it.s a plus)",
    re.I,
)

_TITLE_WORDS = (
    "engineer", "developer", "scientist", "architect", "manager", "analyst",
    "designer", "consultant", "administrator", "specialist", "lead", "intern",
    "programmer", "researcher",
)

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./_-]{1,}", re.I)
_STOP = {
    "the", "and", "for", "with", "you", "our", "are", "will", "have", "who",
    "this", "that", "your", "from", "all", "can", "not", "but", "any", "was",
    "job", "role", "team", "work", "years", "experience", "including", "such",
    "about", "into", "using", "help", "make", "more", "than", "them", "they",
    "what", "when", "where", "which", "while", "their", "there", "these",
    "those", "would", "should", "could", "must", "week", "day", "days",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def detect_seniority(jd: str) -> str:
    blob = f" {jd.lower()} "
    for label, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, blob):
            return label
    return "unspecified"


def detect_title(jd: str, target_role: str = "") -> str:
    if target_role.strip():
        return target_role.strip()
    # Look at the first few non-empty lines for a title-like phrase.
    for line in (jd or "").splitlines():
        clean = line.strip(" -\t:•").strip()
        if not clean or len(clean) > 80:
            continue
        low = clean.lower()
        if any(word in low for word in _TITLE_WORDS):
            return clean
    return ""


def _split_sections(jd: str) -> tuple[str, str]:
    """Return (must_text, nice_text). Anything before a nice-to-have heading is
    treated as must; everything after it as nice-to-have."""
    lines = (jd or "").splitlines()
    must: list[str] = []
    nice: list[str] = []
    bucket = must
    for line in lines:
        if _NICE_HEAD.search(line):
            bucket = nice
        elif _MUST_HEAD.search(line):
            bucket = must
        bucket.append(line)
    return "\n".join(must), "\n".join(nice)


def _skills_in(text: str, bank: dict[str, Any]) -> list[str]:
    """Fact-bank skills (and their synonyms) that appear in text, returned as
    canonical bank skill names."""
    found: dict[str, None] = {}
    skills = all_skills(bank)
    for skill in skills:
        if skill_in_text(skill, text):
            found[skill] = None
    # Synonyms map back to a canonical skill the resume can actually support.
    for canonical, alts in (bank.get("synonyms") or {}).items():
        for needle in (canonical, *alts):
            if skill_in_text(needle, text):
                # Only add canonical if it is a real bank skill.
                for s in skills:
                    if s.lower() == canonical.lower():
                        found[s] = None
    return list(found.keys())


# Ordinary requirement English. Not a list of products or careers.
_GENERIC = _STOP | {
    "experience", "experienced", "year", "plus", "strong", "excellent", "ability",
    "able", "skills", "skill", "required", "requirement", "requirements",
    "preferred", "qualification", "qualifications", "exposure", "include",
    "including", "knowledge", "familiar", "proficient", "expertise", "background",
    "minimum", "basic", "good", "solid", "hands", "hand", "degree", "bachelor",
    "master", "equivalent", "related", "field", "working", "environment",
    "communication", "highly", "well", "proven", "looking", "seeking", "join",
    "responsibilities", "responsibility", "overview", "about", "candidate",
    "candidates", "successful", "success", "ideal", "opportunity", "position",
}

_LEAD_RE = re.compile(
    r"(?:experience|proficien\w*|familiar\w*|knowledge|expertise|background|"
    r"skilled|exposure)\s+(?:with|in|to|using)\s+([^.;\n]+)",
    re.I,
)
_REQUIRED_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9+#./_-]{2,})\s+is\s+required\b",
    re.I,
)
_TOOLISH_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9+#]*(?:[./+-][A-Za-z0-9+#]+)+|"
    r"[A-Z][a-z0-9]{2,}(?:\s+[A-Z][a-z0-9]{2,}){0,2})\b"
)
_PREFIX_RE = re.compile(
    r"^(?:exposure to|experience with|experience in|knowledge of|proficient in|"
    r"familiar with|skilled in|background in)\s+",
    re.I,
)
_SPLIT_RE = re.compile(r"\s*(?:,|/|;|\band\b|\bor\b)\s*", re.I)


def bank_support_text(bank: dict[str, Any]) -> str:
    parts: list[str] = [bank.get("default_summary") or ""]
    parts.extend(all_skills(bank))
    for key in ("roles", "projects"):
        for node in bank.get(key) or []:
            parts.extend([
                node.get("title") or "",
                node.get("name") or "",
                node.get("company") or "",
                " ".join(node.get("stack") or []),
            ])
            for bullet in node.get("bullets") or []:
                parts.append(bullet.get("text") or "")
                parts.extend(bullet.get("skills") or [])
    return "\n".join(parts)


def _anchors(bank: dict[str, Any]) -> set[str]:
    anchors = {s.lower() for s in all_skills(bank)}
    for canon, alts in (bank.get("synonyms") or {}).items():
        anchors.add(canon.lower())
        anchors.update(a.lower() for a in alts)
    for token in TOKEN_RE.findall(bank_support_text(bank).lower()):
        if len(token) >= 3:
            anchors.add(token)
    return anchors


def phrase_supported(phrase: str, bank: dict[str, Any]) -> bool:
    """True when the job phrase is already written, or is a close rephrase of it."""
    if skill_in_text(phrase, bank_support_text(bank)):
        return True
    return along_the_lines(phrase, _anchors(bank))


def _keep_phrase(phrase: str) -> bool:
    clean = _PREFIX_RE.sub("", (phrase or "").strip(" .:-•*|"))
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) < 3 or len(clean) > 60:
        return False
    tokens = [t.lower() for t in TOKEN_RE.findall(clean)]
    content = [t for t in tokens if t not in _GENERIC and len(t) >= 3 and not t.isdigit()]
    if not content:
        return False
    if len(tokens) > 8:
        return False
    return True


def _clean_phrase(phrase: str) -> str:
    clean = _PREFIX_RE.sub("", (phrase or "").strip(" .:-•*|"))
    return re.sub(r"\s+", " ", clean).strip()


def requirement_phrases(text: str) -> list[str]:
    """Skill-like phrases as this job wrote them. No career dictionary."""
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        clean = _clean_phrase(raw)
        key = clean.lower()
        if key in seen or not _keep_phrase(clean):
            return
        seen.add(key)
        found.append(clean)

    for match in _LEAD_RE.finditer(text or ""):
        for part in _SPLIT_RE.split(match.group(1)):
            add(part)
    for match in _REQUIRED_RE.finditer(text or ""):
        add(match.group(1))
    for line in (text or "").splitlines():
        stripped = line.strip(" -\t•*")
        if not stripped:
            continue
        words = stripped.split()
        if "," in stripped or "/" in stripped or len(words) <= 6:
            for part in _SPLIT_RE.split(stripped):
                add(part)
    for match in _TOOLISH_RE.finditer(text or ""):
        add(match.group(1))
    return found


def _external_in(text: str, bank: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for phrase in requirement_phrases(text):
        if phrase_supported(phrase, bank):
            continue
        out.append(phrase)
    return out


def _keywords(text: str, limit: int = 25) -> list[str]:
    counts: dict[str, int] = {}
    for tok in TOKEN_RE.findall(text.lower()):
        if len(tok) < 3 or tok in _STOP or tok.isdigit():
            continue
        counts[tok] = counts.get(tok, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [tok for tok, _ in ranked[:limit]]


def _domains(text: str, bank: dict[str, Any]) -> list[str]:
    known: set[str] = set()
    for role in bank.get("roles", []):
        known.update(role.get("domains") or [])
    for proj in bank.get("projects", []):
        known.update(proj.get("domains") or [])
    hints = {
        "ai": ["ai", "machine learning", "ml", "llm", "generative", "nlp", "genai"],
        "backend": ["backend", "api", "microservice", "server-side", "distributed"],
        "frontend": ["frontend", "react", "ui", "ux", "web app"],
        "fullstack": ["full stack", "full-stack", "fullstack"],
        "data": ["data pipeline", "etl", "data engineering", "warehouse", "analytics"],
        "ml": ["model", "training", "inference", "pytorch", "tensorflow"],
        "platform": ["platform", "infrastructure", "devops", "kubernetes", "cloud-native"],
        "fintech": ["finance", "fintech", "payment", "trading", "banking"],
        "gtm": ["go-to-market", "gtm", "sales", "growth", "community"],
    }
    blob = _norm(text)
    out: list[str] = []
    for domain, needles in hints.items():
        if domain in known and any(n in blob for n in needles):
            out.append(domain)
    return out


def parse_jd(
    jd: str,
    target_role: str = "",
    bank: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bank = bank or load_bank()
    must_text, nice_text = _split_sections(jd)

    must_skills = _skills_in(must_text, bank)
    nice_skills = [s for s in _skills_in(nice_text, bank) if s not in must_skills]
    # If the JD had no clear headings, treat everything as must-have.
    if not must_skills and nice_skills:
        must_skills, nice_skills = nice_skills, []

    external_must = _external_in(must_text, bank)
    external_nice = [
        s for s in _external_in(nice_text, bank) if s not in external_must
    ]

    return {
        "title": detect_title(jd, target_role),
        "seniority": detect_seniority(jd),
        "must_have_skills": must_skills,
        "nice_to_have_skills": nice_skills,
        "must_have_external": external_must,   # asked for, not in the fact bank
        "nice_to_have_external": external_nice,
        "domains": _domains(jd, bank),
        "keywords": _keywords(jd),
    }

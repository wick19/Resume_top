"""Deterministic ATS-style score for a tailored resume against a parsed JD.

This is not a real ATS. It is a transparent, repeatable proxy that rewards the
things published ATS/recruiter research actually rewards:

    - must-have skill coverage (the biggest lever)
    - nice-to-have coverage
    - title alignment in the summary + most recent role
    - recency: JD-critical skills appearing in the most recent role's bullets
    - clean, parseable format (our compiler always emits single-column text)

The tailor loop uses `score_resume` after each rewrite pass and feeds
`missing_in_bank` back to the model to push coverage up toward the target.

Scores are capped at CAP so we never show a dishonest 100.
"""

from __future__ import annotations

from typing import Any

from backend.textutil import skill_in_text

TARGET = 97          # loop keeps going until it reaches this (or runs out of passes)
CAP = 98             # never report above this

WEIGHTS = {
    "must": 55.0,
    "nice": 8.0,
    "title": 15.0,
    "recency": 12.0,
    "format": 10.0,
}


def _resume_text(doc: dict[str, Any]) -> str:
    parts: list[str] = [doc.get("summary") or ""]
    for role in doc.get("roles") or []:
        parts.append(role.get("title") or "")
        parts.extend(b.get("text") or "" for b in role.get("bullets") or [])
    for proj in doc.get("projects") or []:
        parts.append(proj.get("name") or "")
        parts.extend(proj.get("stack") or [])
        parts.extend(b.get("text") or "" for b in proj.get("bullets") or [])
    for group in doc.get("skill_groups") or []:
        parts.extend(group.get("items") or [])
    return "\n".join(parts)


def _recent_role_text(doc: dict[str, Any]) -> str:
    roles = doc.get("roles") or []
    if not roles:
        return ""
    role = roles[0]
    parts = [role.get("title") or ""]
    parts.extend(b.get("text") or "" for b in role.get("bullets") or [])
    return "\n".join(parts)


def _coverage(skills: list[str], text: str) -> tuple[list[str], list[str]]:
    covered, missing = [], []
    for skill in skills:
        (covered if skill_in_text(skill, text) else missing).append(skill)
    return covered, missing


def score_resume(doc: dict[str, Any], parsed_jd: dict[str, Any]) -> dict[str, Any]:
    text = _resume_text(doc)
    recent = _recent_role_text(doc)

    must = parsed_jd.get("must_have_skills") or []
    nice = parsed_jd.get("nice_to_have_skills") or []

    must_cov, must_missing = _coverage(must, text)
    nice_cov, _ = _coverage(nice, text)

    must_ratio = (len(must_cov) / len(must)) if must else 1.0
    nice_ratio = (len(nice_cov) / len(nice)) if nice else 1.0

    # Title alignment: how many title tokens land in summary + recent role.
    title_tokens = [
        t for t in (parsed_jd.get("title") or "").lower().split()
        if len(t) > 2
    ]
    head_text = ((doc.get("summary") or "") + "\n" + recent).lower()
    title_ratio = (
        sum(1 for t in title_tokens if t in head_text) / len(title_tokens)
        if title_tokens else 1.0
    )

    # Recency: must-have skills that appear in the most recent role.
    recent_cov, _ = _coverage(must, recent)
    recency_ratio = (len(recent_cov) / len(must)) if must else 1.0

    # Format: our compiler always emits single-column, standard-heading text.
    format_ratio = 1.0

    raw = (
        WEIGHTS["must"] * must_ratio
        + WEIGHTS["nice"] * nice_ratio
        + WEIGHTS["title"] * title_ratio
        + WEIGHTS["recency"] * recency_ratio
        + WEIGHTS["format"] * format_ratio
    )
    score = min(CAP, round(raw))

    return {
        "score": int(score),
        "target": TARGET,
        "must_total": len(must),
        "must_covered": must_cov,
        "missing_in_bank": must_missing,
        "nice_covered": nice_cov,
        "title_ratio": round(title_ratio, 2),
        "recency_ratio": round(recency_ratio, 2),
        "breakdown": {
            "must": round(WEIGHTS["must"] * must_ratio, 1),
            "nice": round(WEIGHTS["nice"] * nice_ratio, 1),
            "title": round(WEIGHTS["title"] * title_ratio, 1),
            "recency": round(WEIGHTS["recency"] * recency_ratio, 1),
            "format": round(WEIGHTS["format"] * format_ratio, 1),
        },
    }


def adjacent_openings(
    doc: dict[str, Any],
    parsed_jd: dict[str, Any],
    bank: dict[str, Any],
) -> list[str]:
    """JD tools that are not in the bank verbatim, but sit next to a bank skill
    and are not yet written on the resume. The rewrite may phrase these."""
    from backend.fact_bank import all_skills
    from backend.neighbors import along_the_lines

    anchors = {s.lower() for s in all_skills(bank)}
    text = _resume_text(doc)
    asked: list[str] = []
    asked.extend(parsed_jd.get("must_have_external") or [])
    asked.extend(parsed_jd.get("nice_to_have_external") or [])
    out: list[str] = []
    seen: set[str] = set()
    for tool in asked:
        key = tool.lower()
        if key in seen or skill_in_text(tool, text):
            continue
        if along_the_lines(tool, anchors):
            seen.add(key)
            out.append(tool)
    return out

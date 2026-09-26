from __future__ import annotations

import re

PCT_RE = re.compile(r"\d+(?:\.\d+)?%")
YEARS_RE = re.compile(r"\b(\d+\+?)\s*(?:years?|yrs)\b", re.I)
YEAR_PHRASE_RE = re.compile(
    r"(?:(?:,\s*)?(?:\bwith|\bover|\bmore than)\s+)?"
    r"(\d+\+?)\s*(?:years?|yrs)(?:['’]s)?(?:\s+of\s+experience)?",
    re.I,
)


def year_claims(text: str) -> set[str]:
    return {m.group(1).lower() for m in YEARS_RE.finditer(text or "")}


def strip_invented_years(text: str, allowed_source: str) -> str:
    """Drop 'N years of experience' claims that are not already in the source."""
    allowed = year_claims(allowed_source)

    def repl(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1).lower() in allowed else ""

    out = YEAR_PHRASE_RE.sub(repl, text or "")
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;])", r"\1", out)
    return out.strip(" ,;")


def skill_in_text(skill: str, text: str) -> bool:
    if not skill or not text:
        return False
    pattern = rf"(?<![a-z0-9+#]){re.escape(skill.lower())}(?![a-z0-9+#])"
    return re.search(pattern, text.lower()) is not None


def percents(text: str) -> set[str]:
    return {m.lower() for m in PCT_RE.findall(text or "")}

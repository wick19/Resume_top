from __future__ import annotations

import re

PCT_RE = re.compile(r"\d+(?:\.\d+)?%")
YEARS_RE = re.compile(r"\b\d+\+?\s*(?:years?|yrs)\b", re.I)


def skill_in_text(skill: str, text: str) -> bool:
    if not skill or not text:
        return False
    pattern = rf"(?<![a-z0-9+#]){re.escape(skill.lower())}(?![a-z0-9+#])"
    return re.search(pattern, text.lower()) is not None


def percents(text: str) -> set[str]:
    return {m.lower() for m in PCT_RE.findall(text or "")}

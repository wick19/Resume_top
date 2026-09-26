"""Compare a job's years ask with the dates already on the fact bank.

This only feeds the audit gap list. It does not change the ATS score and it
does not write a tenure onto the resume.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_ASK_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs)\b", re.I)
_PRESENT_RE = re.compile(r"\b(?:present|current|now|ongoing)\b", re.I)
_MONTH_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s+((?:19|20)\d{2})\b",
    re.I,
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def years_asked(jd: str) -> list[int]:
    """Distinct experience asks in the posting, highest first. Ignores 0 and 40+."""
    found: set[int] = set()
    for raw in _ASK_RE.findall(jd or ""):
        number = int(raw)
        if 1 <= number <= 30:
            found.add(number)
    return sorted(found, reverse=True)


def _point(text: str, *, is_end: bool, today: date) -> date | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if _PRESENT_RE.search(raw):
        return today
    month = _MONTH_RE.search(raw)
    if month:
        key = month.group(1).lower()[:3]
        return date(int(month.group(2)), _MONTHS[key], 1)
    year = _YEAR_RE.search(raw)
    if year:
        value = int(year.group(1))
        return date(value, 12, 1) if is_end else date(value, 1, 1)
    return None


def covered_years(roles: list[dict[str, Any]] | None, today: date | None = None) -> float | None:
    """Merged length of role date ranges, in years. Overlaps count once."""
    today = today or date.today()
    spans: list[tuple[int, int]] = []
    for role in roles or []:
        start = _point(str(role.get("start") or ""), is_end=False, today=today)
        end = _point(str(role.get("end") or ""), is_end=True, today=today)
        if start is None and end is None:
            continue
        if start is None:
            start = end
        if end is None:
            end = today
        if end < start:
            start, end = end, start
        spans.append((start.toordinal(), end.toordinal()))
    if not spans:
        return None
    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    days = sum(end - start for start, end in merged)
    return days / 365.25


def _fmt_years(years: float) -> str:
    if years < 0.75:
        return "under 1 year"
    half = round(years * 2) / 2
    if half == int(half):
        count = int(half)
        return "1 year" if count == 1 else f"{count} years"
    return f"{half:.1f} years"


def tenure_gap(jd: str, bank: dict[str, Any] | None, today: date | None = None) -> str | None:
    """A gap sentence when the posting asks for more years than the dates cover."""
    asks = years_asked(jd)
    if not asks or not bank:
        return None
    covered = covered_years(bank.get("roles") or [], today=today)
    if covered is None:
        return None
    unmet = [n for n in asks if covered + 0.05 < n]
    if not unmet:
        return None
    shown = _fmt_years(covered)
    if len(unmet) == 1:
        return (
            f"JD asks for {unmet[0]}+ years of experience; "
            f"dated roles cover about {shown}."
        )
    listed = " and ".join(f"{n}+" for n in unmet)
    return (
        f"JD asks for {listed} years of experience; "
        f"dated roles cover about {shown}."
    )

"""Close rephrase of something already written in the fact bank.

This is not a profession list. A job phrase is allowed when it is already
in the bank text, or when it is a shorter form of a skill already written
there ("sql" inside "postgresql"). A different product is not a rephrase.
"""

from __future__ import annotations


def _norm(term: str) -> str:
    return " ".join((term or "").lower().split())


def along_the_lines(term: str, anchors: set[str]) -> bool:
    """True when `term` is already written in `anchors`, or is contained in one."""
    needle = _norm(term)
    if not needle or not anchors:
        return False
    base = {_norm(a) for a in anchors if a}
    if needle in base:
        return True
    for anchor in base:
        if len(needle) >= 3 and len(anchor) > len(needle) and needle in anchor:
            return True
        words = [w for w in needle.split() if len(w) >= 4]
        if words and all(w in anchor for w in words):
            return True
    return False

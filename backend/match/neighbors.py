"""Close rephrase of something already written in the fact bank.

This is not a profession list. A job phrase is allowed when it is already
in the bank text, or when it is a shorter form of a skill already written
there ("sql" inside "postgresql"). A different product is not a rephrase.
"""

from __future__ import annotations


def _norm(term: str) -> str:
    return " ".join((term or "").lower().split())


def _compact_same_skill(needle: str, anchor: str) -> bool:
    """True when one token is a compact form of a multi-word skill.

    "genai" is the start of "generative" plus "ai". "llm" is the initials of
    "large language models". This is the same test for every kind of work.
    """
    if " " in needle or " " not in anchor or len(needle) < 3:
        return False
    words = [word for word in anchor.split() if word]
    if len(words) < 2:
        return False
    if len(words) >= 3 and needle == "".join(word[0] for word in words):
        return True
    for index, later in enumerate(words):
        if index == 0 or len(needle) <= len(later) or not needle.endswith(later):
            continue
        head = needle[: -len(later)]
        if len(head) >= 3 and any(word.startswith(head) for word in words[:index]):
            return True
    return False


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
        if _compact_same_skill(needle, anchor):
            return True
        words = [w for w in needle.split() if len(w) >= 4]
        if words and all(w in anchor for w in words):
            return True
    return False

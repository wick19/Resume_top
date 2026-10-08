from __future__ import annotations

from typing import Any

from backend.resume.fact_bank import all_skills, allowed_skills_for_bullet, index_facts, load_bank
from backend.match.neighbors import along_the_lines
from backend.textutil import percents, skill_in_text, year_claims

# A rewrite may add at most this many bank skills that were not already in the
# original bullet. Stops a JD-clone dump even when every extra skill is
# technically grounded in the parent role's stack.
MAX_NEW_SKILLS_PER_BULLET = 2
# If new skills were added, reject a keyword-pile sentence (skills / words).
MAX_ADDED_SKILL_DENSITY = 0.22

class ValidationError(ValueError):
    pass


def _unsupported_in(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if skill_in_text(phrase, text)]


def validate_document(
    doc: dict[str, Any],
    bank: dict[str, Any] | None = None,
    jd: str = "",
) -> None:
    bank = bank or load_bank()
    idx = index_facts(bank)
    errors: list[str] = []

    profile = bank["profile"]
    doc_profile = doc.get("profile") or {}
    for key in ("name", "phone", "email", "linkedin", "github", "portfolio"):
        if doc_profile.get(key) != profile.get(key):
            errors.append(f"profile.{key} is locked and cannot change")

    summary = doc.get("summary") or ""
    original_summary = bank.get("default_summary") or ""
    invented_years = year_claims(summary) - year_claims(original_summary)
    if invented_years:
        errors.append("summary must not invent years of experience")
    unsupported: list[str] = []
    if jd:
        from backend.match.scoring import gap_skills

        unsupported = gap_skills(jd, bank)
    named = _unsupported_in(summary, unsupported)
    if named:
        errors.append(
            "summary names requirements with no base in the fact bank: " + ", ".join(named)
        )

    for role in doc.get("roles") or []:
        rid = role.get("id")
        entry = idx.get(rid)
        if not entry or entry["kind"] != "role":
            errors.append(f"unknown role id: {rid}")
            continue
        src = entry["node"]
        for field in ("company", "title", "start", "end", "location"):
            if role.get(field) != src.get(field):
                errors.append(f"{rid}.{field} is locked ({src.get(field)!r})")
        if not role.get("bullets"):
            errors.append(f"{rid} has no bullets")
        for bullet in role.get("bullets") or []:
            bid = bullet.get("id")
            bentry = idx.get(bid)
            if not bentry or bentry["kind"] != "role_bullet":
                errors.append(f"unknown bullet id: {bid}")
                continue
            if bentry["parent"]["id"] != rid:
                errors.append(f"{bid} does not belong to {rid}")
            errors.extend(_check_bullet(bullet, bentry, bank, unsupported))

    for project in doc.get("projects") or []:
        pid = project.get("id")
        entry = idx.get(pid)
        if not entry or entry["kind"] != "project":
            errors.append(f"unknown project id: {pid}")
            continue
        src = entry["node"]
        if project.get("name") != src.get("name"):
            errors.append(f"{pid}.name is locked")
        src_stack = {s.lower() for s in (src.get("stack") or [])}
        for item in project.get("stack") or []:
            if item.lower() not in src_stack:
                errors.append(f"{pid} stack item not in fact bank: {item}")
        for bullet in project.get("bullets") or []:
            bid = bullet.get("id")
            bentry = idx.get(bid)
            if not bentry or bentry["kind"] != "project_bullet":
                errors.append(f"unknown project bullet id: {bid}")
                continue
            if bentry["parent"]["id"] != pid:
                errors.append(f"{bid} does not belong to {pid}")
            errors.extend(_check_bullet(bullet, bentry, bank, unsupported))

    src_edu = {e["id"]: e for e in bank["education"]}
    for edu in doc.get("education") or []:
        eid = edu.get("id")
        if eid not in src_edu:
            errors.append(f"unknown education id: {eid}")
            continue
        for field in ("school", "location", "credential", "start", "end"):
            if edu.get(field) != src_edu[eid].get(field):
                errors.append(f"{eid}.{field} is locked")

    allowed_skill = {s.lower() for s in all_skills(bank)}
    for group in doc.get("skill_groups") or []:
        gid = group.get("id")
        gentry = idx.get(gid)
        if not gentry or gentry["kind"] != "skill_group":
            errors.append(f"unknown skill group: {gid}")
            continue
        src_items = {s.lower() for s in gentry["node"]["items"]}
        if group.get("label") != gentry["node"]["label"]:
            errors.append(f"{gid}.label is locked")
        for item in group.get("items") or []:
            if item.lower() not in src_items or item.lower() not in allowed_skill:
                errors.append(f"{gid} contains skill not in bank: {item}")

    if errors:
        raise ValidationError("; ".join(errors))


def _check_bullet(
    bullet: dict[str, Any],
    entry: dict[str, Any],
    bank: dict[str, Any] | None = None,
    unsupported: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    text = (bullet.get("text") or "").strip()
    if not text:
        errors.append(f"{bullet.get('id')} is empty")
        return errors
    original = entry["node"]["text"]
    if year_claims(text) - year_claims(original):
        errors.append(f"{bullet.get('id')} invents years of experience")

    locked = set(entry["node"].get("locked_numbers") or [])
    allowed_pct = percents(original) | {p.lower() for p in locked if "%" in p}
    extra = percents(text) - allowed_pct
    if extra:
        errors.append(f"{bullet.get('id')} invented metrics: {sorted(extra)}")
    for pct in percents(original):
        if pct not in percents(text):
            errors.append(f"{bullet.get('id')} dropped locked metric {pct}")

    allowed = allowed_skills_for_bullet(entry, bank)
    bank_skills = {s.lower() for s in all_skills(bank)}
    present: list[str] = []
    for skill in sorted(bank_skills, key=len, reverse=True):
        if len(skill) < 4:
            continue
        if not skill_in_text(skill, text):
            continue
        present.append(skill)
        if skill not in allowed and not along_the_lines(skill, allowed):
            errors.append(
                f"{bullet.get('id')} introduces skill {skill!r} not grounded in this fact"
            )

    original_skills = {
        s.lower()
        for s in bank_skills
        if len(s) >= 4 and skill_in_text(s, original)
    }
    added = [s for s in present if s not in original_skills]
    if len(added) > MAX_NEW_SKILLS_PER_BULLET:
        errors.append(
            f"{bullet.get('id')} keyword-stuffs {len(added)} new skills "
            f"(cap {MAX_NEW_SKILLS_PER_BULLET}): {added[:6]}"
        )
    words = max(1, len(text.split()))
    if added and (len(present) / words) > MAX_ADDED_SKILL_DENSITY:
        errors.append(
            f"{bullet.get('id')} is a keyword dump ({len(present)} skills / {words} words)"
        )

    invented = [
        phrase for phrase in (unsupported or [])
        if skill_in_text(phrase, text) and not skill_in_text(phrase, original)
        and not along_the_lines(phrase, allowed)
    ]
    if invented:
        errors.append(
            f"{bullet.get('id')} adds requirements with no base in this fact: "
            + ", ".join(invented)
        )

    return errors

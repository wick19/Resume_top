from __future__ import annotations

from typing import Any

from backend.fact_bank import all_skills, allowed_skills_for_bullet, index_facts, load_bank
from backend.textutil import YEARS_RE, percents, skill_in_text

KNOWN_TECH_HINTS = [
    "kafka",
    "spark",
    "airflow",
    "snowflake",
    "bigquery",
    "golang",
    "ruby on rails",
    "hadoop",
    "sagemaker",
    "graphql",
    "grpc",
    "ansible",
    "pulumi",
    "flink",
    "databricks",
    "looker",
    "tableau",
    "salesforce",
]


class ValidationError(ValueError):
    pass


def validate_document(doc: dict[str, Any], bank: dict[str, Any] | None = None) -> None:
    bank = bank or load_bank()
    idx = index_facts(bank)
    errors: list[str] = []

    profile = bank["profile"]
    doc_profile = doc.get("profile") or {}
    for key in ("name", "phone", "email", "linkedin", "github", "portfolio"):
        if doc_profile.get(key) != profile.get(key):
            errors.append(f"profile.{key} is locked and cannot change")

    summary = doc.get("summary") or ""
    if YEARS_RE.search(summary):
        errors.append("summary must not invent years of experience")

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
            errors.extend(_check_bullet(bullet, bentry))

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
            errors.extend(_check_bullet(bullet, bentry))

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


def _check_bullet(bullet: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    text = (bullet.get("text") or "").strip()
    if not text:
        errors.append(f"{bullet.get('id')} is empty")
        return errors
    if YEARS_RE.search(text):
        errors.append(f"{bullet.get('id')} invents years of experience")

    original = entry["node"]["text"]
    locked = set(entry["node"].get("locked_numbers") or [])
    allowed_pct = percents(original) | {p.lower() for p in locked if "%" in p}
    extra = percents(text) - allowed_pct
    if extra:
        errors.append(f"{bullet.get('id')} invented metrics: {sorted(extra)}")
    for pct in percents(original):
        if pct not in percents(text):
            errors.append(f"{bullet.get('id')} dropped locked metric {pct}")

    allowed = allowed_skills_for_bullet(entry)
    bank_skills = {s.lower() for s in all_skills()}
    for skill in sorted(bank_skills, key=len, reverse=True):
        if len(skill) < 4:
            continue
        if skill_in_text(skill, text) and skill not in allowed:
            errors.append(
                f"{bullet.get('id')} introduces skill {skill!r} not grounded in this fact"
            )

    blob = text.lower()
    known = {s.lower() for s in all_skills()}
    for hint in KNOWN_TECH_HINTS:
        if hint in blob and hint not in known and hint not in original.lower():
            errors.append(f"{bullet.get('id')} introduces ungrounded tool {hint!r}")

    return errors

from __future__ import annotations

import copy
import json
from functools import lru_cache
from typing import Any

from backend.config import FACT_BANK_PATH
from backend.textutil import skill_in_text


@lru_cache(maxsize=1)
def load_bank() -> dict[str, Any]:
    with FACT_BANK_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def all_skills(bank: dict[str, Any] | None = None) -> list[str]:
    bank = bank or load_bank()
    items: list[str] = []
    for group in bank["skill_groups"]:
        items.extend(group["items"])
    for role in bank["roles"]:
        items.extend(role.get("stack") or [])
        for b in role["bullets"]:
            items.extend(b.get("skills") or [])
    for project in bank["projects"]:
        items.extend(project.get("stack") or [])
        for b in project["bullets"]:
            items.extend(b.get("skills") or [])
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def index_facts(bank: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    bank = bank or load_bank()
    idx: dict[str, dict[str, Any]] = {}
    for role in bank["roles"]:
        idx[role["id"]] = {"kind": "role", "node": role}
        for bullet in role["bullets"]:
            idx[bullet["id"]] = {
                "kind": "role_bullet",
                "node": bullet,
                "parent": role,
            }
    for project in bank["projects"]:
        idx[project["id"]] = {"kind": "project", "node": project}
        for bullet in project["bullets"]:
            idx[bullet["id"]] = {
                "kind": "project_bullet",
                "node": bullet,
                "parent": project,
            }
    for edu in bank["education"]:
        idx[edu["id"]] = {"kind": "education", "node": edu}
    for group in bank["skill_groups"]:
        idx[group["id"]] = {"kind": "skill_group", "node": group}
    return idx


def allowed_skills_for_bullet(entry: dict[str, Any]) -> set[str]:
    bullet = entry["node"]
    parent = entry["parent"]
    allowed = {s.lower() for s in (bullet.get("skills") or [])}
    allowed.update(s.lower() for s in (parent.get("stack") or []))
    original = bullet["text"]
    for skill in all_skills():
        if skill_in_text(skill, original):
            allowed.add(skill.lower())
    return allowed


def default_document(bank: dict[str, Any] | None = None) -> dict[str, Any]:
    """Master resume: original wording, default includes, no LLM."""
    bank = bank or load_bank()
    roles = []
    for role in bank["roles"]:
        roles.append(
            {
                "id": role["id"],
                "company": role["company"],
                "title": role["title"],
                "start": role["start"],
                "end": role["end"],
                "location": role["location"],
                "bullets": [
                    {"id": b["id"], "text": b["text"]} for b in role["bullets"]
                ],
            }
        )
    projects = []
    for project in bank["projects"]:
        if not project.get("include_by_default", True):
            continue
        projects.append(
            {
                "id": project["id"],
                "name": project["name"],
                "stack": list(project.get("stack") or []),
                "bullets": [
                    {"id": b["id"], "text": b["text"]} for b in project["bullets"]
                ],
            }
        )
    return {
        "profile": copy.deepcopy(bank["profile"]),
        "summary": bank["default_summary"],
        "roles": roles,
        "projects": projects,
        "education": copy.deepcopy(bank["education"]),
        "skill_groups": copy.deepcopy(bank["skill_groups"]),
    }

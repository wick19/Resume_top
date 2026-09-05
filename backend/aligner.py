from __future__ import annotations

import copy
import json
from typing import Any

from backend.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from backend.fact_bank import load_bank
from backend.prompts import SYSTEM_PROMPT, user_prompt
from backend.scoring import gap_skills, select_for_jd
from backend.validator import ValidationError, validate_document


def _client():
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": OPENAI_API_KEY}
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return OpenAI(**kwargs)


def overlay_rewrite(selected: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(selected)
    if isinstance(llm.get("summary"), str) and llm["summary"].strip():
        out["summary"] = llm["summary"].strip()

    role_map = {r.get("id"): r for r in llm.get("roles") or [] if r.get("id")}
    for role in out["roles"]:
        src = role_map.get(role["id"])
        if not src:
            continue
        bmap = {
            b["id"]: b["text"].strip()
            for b in src.get("bullets") or []
            if b.get("id") and isinstance(b.get("text"), str)
        }
        for bullet in role["bullets"]:
            if bullet["id"] in bmap and bmap[bullet["id"]]:
                bullet["text"] = bmap[bullet["id"]]

    proj_map = {p.get("id"): p for p in llm.get("projects") or [] if p.get("id")}
    for project in out["projects"]:
        src = proj_map.get(project["id"])
        if not src:
            continue
        bmap = {
            b["id"]: b["text"].strip()
            for b in src.get("bullets") or []
            if b.get("id") and isinstance(b.get("text"), str)
        }
        for bullet in project["bullets"]:
            if bullet["id"] in bmap and bmap[bullet["id"]]:
                bullet["text"] = bmap[bullet["id"]]

    group_map = {g.get("id"): g for g in llm.get("skill_groups") or [] if g.get("id")}
    for group in out["skill_groups"]:
        src = group_map.get(group["id"])
        if not src or not isinstance(src.get("items"), list):
            continue
        allowed = {i.lower(): i for i in group["items"]}
        reordered = []
        seen = set()
        for item in src["items"]:
            if not isinstance(item, str):
                continue
            key = item.lower()
            if key in allowed and key not in seen:
                reordered.append(allowed[key])
                seen.add(key)
        for item in group["items"]:
            if item.lower() not in seen:
                reordered.append(item)
        group["items"] = reordered
    return out


def _facts_used(doc: dict[str, Any]) -> list[str]:
    ids = []
    for role in doc.get("roles") or []:
        ids.append(role["id"])
        ids.extend(b["id"] for b in role.get("bullets") or [])
    for project in doc.get("projects") or []:
        ids.append(project["id"])
        ids.extend(b["id"] for b in project.get("bullets") or [])
    return ids


def _call_llm(jd: str, target_role: str, company: str, selected: dict[str, Any]) -> dict[str, Any]:
    client = _client()
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(jd, target_role, company, selected)},
        ],
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def tailor(
    jd: str,
    target_role: str = "",
    company: str = "",
    rewrite: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bank = load_bank()
    selected = select_for_jd(jd, target_role=target_role, bank=bank)
    # Attach stacks for the model; strip later before PDF if needed.
    stacks = {r["id"]: r.get("stack") for r in bank["roles"]}
    for role in selected["roles"]:
        role["stack"] = stacks.get(role["id"]) or []

    audit = {
        "interview": "Unknown",
        "reject_reasons": [],
        "gaps": gap_skills(jd, bank),
        "facts_used": _facts_used(selected),
        "mode": "select",
        "notes": [],
    }

    doc = selected
    if rewrite and OPENAI_API_KEY:
        last_error = None
        payload = None
        for attempt in range(2):
            try:
                payload = _call_llm(jd, target_role, company, doc if attempt == 0 else selected)
                candidate = overlay_rewrite(selected, payload)
                validate_document(candidate, bank)
                doc = candidate
                last_error = None
                break
            except (ValidationError, json.JSONDecodeError, KeyError) as exc:
                last_error = str(exc)
                audit["notes"].append(f"rewrite attempt {attempt + 1} rejected: {exc}")
        if last_error:
            audit["notes"].append("fell back to original wording after failed rewrite")
            doc = selected
            validate_document(doc, bank)
        else:
            audit["mode"] = "rewrite"
            if isinstance(payload, dict) and isinstance(payload.get("audit"), dict):
                src = payload["audit"]
                if src.get("interview") in ("Yes", "No"):
                    audit["interview"] = src["interview"]
                if isinstance(src.get("reject_reasons"), list):
                    audit["reject_reasons"] = [str(x) for x in src["reject_reasons"][:3]]
                if isinstance(src.get("gaps"), list):
                    extra = [str(x) for x in src["gaps"] if x]
                    audit["gaps"] = list(dict.fromkeys(audit["gaps"] + extra))
    else:
        if rewrite and not OPENAI_API_KEY:
            audit["notes"].append("OPENAI_API_KEY missing; selected original bullets only")
        validate_document(doc, bank)

    audit["facts_used"] = _facts_used(doc)
    # Drop helper fields from the printable document.
    for role in doc["roles"]:
        role.pop("score", None)
        role.pop("stack", None)
    for project in doc["projects"]:
        project.pop("score", None)
    doc.pop("query_terms", None)
    return doc, audit

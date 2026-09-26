from __future__ import annotations

import copy
import re
from typing import Any

from backend.fact_bank import all_skills, load_bank
from backend.semantic import similarity as semantic_similarity

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./_-]{1,}", re.I)

# How much semantic similarity can nudge a node's score. Kept small so strong
# literal keyword overlap still dominates; this only breaks ties and surfaces
# related work the lexical pass would miss.
SEMANTIC_WEIGHT = 3.0


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def expand_query(jd: str, bank: dict[str, Any] | None = None) -> set[str]:
    bank = bank or load_bank()
    blob = _norm(jd)
    terms: set[str] = set(TOKEN_RE.findall(blob))
    for canonical, alts in (bank.get("synonyms") or {}).items():
        needles = [canonical, *alts]
        if any(_norm(n) in blob for n in needles):
            terms.add(_norm(canonical))
            terms.update(_norm(a) for a in alts)
    for skill in all_skills(bank):
        if _norm(skill) in blob:
            terms.add(_norm(skill))
    return terms


def _node_text(node: dict[str, Any]) -> str:
    parts = [node.get("name") or "", node.get("company") or "", node.get("title") or ""]
    parts.extend(node.get("stack") or [])
    parts.extend(node.get("domains") or [])
    for b in node.get("bullets") or []:
        parts.append(b.get("text") or "")
        parts.extend(b.get("skills") or [])
    return _norm(" ".join(parts))


def score_node(node: dict[str, Any], query: set[str]) -> float:
    text = _node_text(node)
    if not query:
        return 0.0
    hits = 0
    for term in query:
        if len(term) < 3:
            continue
        if term in text:
            hits += 1
    recency = float(node.get("recency_rank") or 9)
    recency_boost = max(0.0, 4.0 - recency) * 0.15
    return hits + recency_boost


def score_bullet(bullet: dict[str, Any], parent: dict[str, Any], query: set[str]) -> float:
    blob = _norm(
        " ".join(
            [
                bullet.get("text") or "",
                " ".join(bullet.get("skills") or []),
                " ".join(parent.get("stack") or []),
            ]
        )
    )
    hits = sum(1 for t in query if len(t) >= 3 and t in blob)
    return float(hits)


def select_for_jd(
    jd: str,
    target_role: str = "",
    bank: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage A: pick roles, bullets, projects, skill order. Original wording."""
    bank = bank or load_bank()
    query = expand_query(f"{target_role}\n{jd}", bank)
    jd_query = f"{target_role}\n{jd}"

    role_nodes = bank.get("roles") or []
    role_sims = semantic_similarity(jd_query, [_node_text(r) for r in role_nodes])
    role_scores = [
        (score_node(r, query) + SEMANTIC_WEIGHT * sim, r)
        for r, sim in zip(role_nodes, role_sims)
    ]
    role_scores.sort(key=lambda x: -x[0])

    selected_roles: list[dict[str, Any]] = []
    for score, role in role_scores:
        default = role.get("include_by_default", True)
        if not default and score < 8:
            continue
        ranked = sorted(
            role["bullets"],
            key=lambda b: -score_bullet(b, role, query),
        )
        keep_n = 6 if role.get("recency_rank", 9) <= 2 else 5
        if not default:
            keep_n = min(2, len(ranked))
        keep_ids = {b["id"] for b in ranked[: min(keep_n, len(ranked))]}
        picked = [b for b in role["bullets"] if b["id"] in keep_ids]
        selected_roles.append(
            {
                "id": role["id"],
                "company": role["company"],
                "title": role["title"],
                "start": role["start"],
                "end": role["end"],
                "location": role["location"],
                "score": round(score, 2),
                "bullets": [{"id": b["id"], "text": b["text"]} for b in picked],
            }
        )

    # Keep chronological / recency order on the page, not score order.
    order = {r["id"]: i for i, r in enumerate(bank.get("roles") or [])}
    selected_roles.sort(key=lambda r: order.get(r["id"], 99))

    project_nodes = bank.get("projects") or []
    project_rank = {p["id"]: i for i, p in enumerate(project_nodes)}
    project_sims = semantic_similarity(
        jd_query, [_node_text(p) for p in project_nodes]
    )
    project_scores = [
        (score_node(p, query) + SEMANTIC_WEIGHT * sim, p)
        for p, sim in zip(project_nodes, project_sims)
    ]
    project_scores.sort(key=lambda x: -x[0])
    selected_projects = []
    for score, project in project_scores[:3]:
        if score < 1 and not project.get("include_by_default", True):
            continue
        selected_projects.append(
            {
                "id": project["id"],
                "name": project["name"],
                "stack": list(project.get("stack") or [])[:6],
                "score": round(score, 2),
                "bullets": [{"id": b["id"], "text": b["text"]} for b in project["bullets"]],
            }
        )
    selected_projects.sort(key=lambda p: project_rank.get(p["id"], 99))

    groups = [
        {"id": group["id"], "label": group["label"], "items": list(group["items"])}
        for group in bank.get("skill_groups") or []
    ]

    return {
        "profile": copy.deepcopy(bank.get("profile") or {}),
        "summary": bank.get("default_summary", ""),
        "roles": selected_roles,
        "projects": selected_projects,
        "education": copy.deepcopy(bank.get("education") or []),
        "skill_groups": groups,
        "query_terms": sorted(query)[:80],
    }


def gap_skills(jd: str, bank: dict[str, Any] | None = None) -> list[str]:
    """Phrases this job asks for that the fact bank does not already support."""
    from backend.jd_parser import parse_jd

    bank = bank or load_bank()
    parsed = parse_jd(jd, bank=bank)
    gaps = list(parsed.get("must_have_external") or [])
    seen = {g.lower() for g in gaps}
    for phrase in parsed.get("nice_to_have_external") or []:
        if phrase.lower() not in seen:
            seen.add(phrase.lower())
            gaps.append(phrase)
    return gaps

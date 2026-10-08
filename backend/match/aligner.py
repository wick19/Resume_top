from __future__ import annotations

import copy
import json
from typing import Any, Iterator

from backend.match.ats import TARGET, adjacent_openings, score_resume
from backend.resume.fact_bank import load_bank
from backend.match.jd_parser import parse_jd, unsupported_clauses
from backend.llm.llm import (
    BudgetExceeded,
    ProviderFailed,
    chat,
    clear_skipped,
    is_pinned,
    llm_available,
    resolve as llm_resolve,
    skip_provider,
)
from backend.llm.prompts import SYSTEM_PROMPT, user_prompt
from backend.match.scoring import gap_skills, order_skill_groups, select_for_jd
from backend.resume.tenure import tenure_gap
from backend.textutil import strip_invented_years
from backend.resume.validator import ValidationError, validate_document

MAX_PASSES = 4


def overlay_rewrite(selected: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(selected)
    if isinstance(llm.get("summary"), str) and llm["summary"].strip():
        out["summary"] = strip_invented_years(
            llm["summary"].strip(), out.get("summary") or ""
        )

    role_map = {r.get("id"): r for r in llm.get("roles") or [] if isinstance(r, dict) and r.get("id")}
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
                bullet["text"] = strip_invented_years(
                    bmap[bullet["id"]], bullet.get("text") or ""
                )

    proj_map = {p.get("id"): p for p in llm.get("projects") or [] if isinstance(p, dict) and p.get("id")}
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
                bullet["text"] = strip_invented_years(
                    bmap[bullet["id"]], bullet.get("text") or ""
                )

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


def _call_llm(
    jd: str,
    target_role: str,
    company: str,
    selected: dict[str, Any],
    missing: list[str] | None,
    ats_score: int | None,
) -> dict[str, Any]:
    from backend.llm.llm import parse_json_object

    content = chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_prompt(
                    jd, target_role, company, selected,
                    missing_skills=missing,
                    ats_score=ats_score,
                    ats_target=TARGET,
                ),
            },
        ],
        temperature=0.3,
    )
    return parse_json_object(content)


def _csv(items: list[Any] | None, n: int = 5) -> str:
    vals = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not vals:
        return "none named"
    extra = len(vals) - n
    head = ", ".join(vals[:n])
    return f"{head} (+{extra} more)" if extra > 0 else head


def _progress(stage: str, message: str, pct: int, score: int | None = None) -> dict[str, Any]:
    return {
        "type": "progress",
        "stage": stage,
        "message": message,
        "pct": pct,
        "score": score,
        "target": TARGET,
    }


def _strip(doc: dict[str, Any]) -> None:
    for role in doc.get("roles", []):
        role.pop("score", None)
        role.pop("stack", None)
    for project in doc.get("projects", []):
        project.pop("score", None)
    doc.pop("query_terms", None)


def _halted(halted) -> bool:
    return bool(halted and halted())


def tailor_stream(
    jd: str,
    target_role: str = "",
    company: str = "",
    rewrite: bool = True,
    bank: dict[str, Any] | None = None,
    halted=None,
) -> Iterator[dict[str, Any]]:
    """Yield progress events, then a final {'type': 'done', 'doc', 'audit'}.

    The ATS score climbs across rewrite passes until it reaches the target or
    the passes run out. Each pass tells the model which in-bank JD skills are
    still under-surfaced, so coverage goes up without inventing anything.
    """
    bank = bank or load_bank()
    clear_skipped()
    role_name = (target_role or "").strip() or "this role"
    co = f" at {company.strip()}" if (company or "").strip() else ""

    yield _progress(
        "parse",
        f"Reading the job description for {role_name}{co}. Pulling title, seniority, and skills we can actually support from your uploaded resume.",
        8,
    )
    parsed = parse_jd(jd, target_role=target_role, bank=bank)
    jd_title = parsed.get("title") or role_name
    yield _progress(
        "parse",
        f"This posting looks like {jd_title} ({parsed.get('seniority') or 'unspecified'} seniority). "
        f"Skills from your fact bank that the JD mentions: {_csv(parsed.get('must_have_skills'))}.",
        14,
    )
    if parsed.get("must_have_external"):
        yield _progress(
            "parse",
            f"The JD also asks for {_csv(parsed.get('must_have_external'))}, which are not in your fact bank. "
            "Those stay listed as gaps — we will not invent them.",
            16,
        )

    yield _progress(
        "select",
        "Selecting which of your roles and bullets match this JD. Wording stays original until a rewrite pass.",
        22,
    )
    selected = select_for_jd(jd, target_role=target_role, bank=bank)
    stacks = {r["id"]: r.get("stack") for r in (bank.get("roles") or [])}
    for role in selected["roles"]:
        role["stack"] = stacks.get(role["id"]) or []
    kept = []
    for role in selected.get("roles") or []:
        n = len(role.get("bullets") or [])
        title = role.get("title") or "Role"
        firm = role.get("company") or "your company"
        kept.append(f"{title} at {firm} ({n} bullet{'s' if n != 1 else ''})")
    yield _progress(
        "select",
        ("Keeping " + "; ".join(kept[:3]) + ".") if kept else "No matching roles found in the fact bank.",
        30,
    )

    tool_gaps = list(gap_skills(jd, bank))
    gaps = list(tool_gaps)
    years = tenure_gap(jd, bank)
    if years:
        gaps.append(years)
        yield _progress(
            "parse",
            years + " That stays a gap. The resume will not gain a new tenure, and the score is unchanged.",
            18,
        )

    base = score_resume(selected, parsed)
    audit: dict[str, Any] = {
        "interview": "Unknown",
        "reject_reasons": [],
        "gaps": gaps,
        "facts_used": _facts_used(selected),
        "mode": "select",
        "ats_score": base["score"],
        "ats_target": TARGET,
        "notes": [],
    }
    yield _progress(
        "score",
        f"Baseline ATS match is {base['score']}% (target {TARGET}%). "
        f"Under-surfaced skills still in your bank: {_csv(base.get('missing_in_bank'))}.",
        38,
        base["score"],
    )

    doc = selected
    if rewrite and llm_available():
        best = copy.deepcopy(selected)
        best_score = base
        final_payload: dict[str, Any] | None = None
        provider_stop: ProviderFailed | None = None
        for attempt in range(MAX_PASSES):
            if _halted(halted):
                return
            spec = llm_resolve()
            if spec is None:
                provider_stop = provider_stop or ProviderFailed(
                    "", "No free model is available for this rewrite."
                )
                break
            model_label = f"{spec['name']} ({spec['model']})"
            pct = 45 + int(40 * (attempt + 1) / MAX_PASSES)
            missing = list(best_score.get("missing_in_bank") or [])
            openings = adjacent_openings(best, parsed, bank)
            focus = missing + [item for item in openings if item not in missing]
            yield _progress(
                "rewrite",
                f"Rewrite pass {attempt + 1} of {MAX_PASSES} on {model_label}: same facts, JD wording. "
                "This wait is the model thinking — not a freeze.",
                pct,
                best_score["score"],
            )
            prev = best_score["score"]
            try:
                payload = _call_llm(
                    jd, target_role, company, selected, focus, best_score["score"]
                )
                candidate = overlay_rewrite(selected, payload)
                order_skill_groups(candidate.get("skill_groups") or [], jd)
                validate_document(candidate, bank, jd)
            except BudgetExceeded as exc:
                audit["notes"].append(str(exc))
                yield _progress("rewrite", str(exc), pct, best_score["score"])
                break
            except ProviderFailed as exc:
                provider_stop = exc
                audit["notes"].append(str(exc))
                if is_pinned():
                    yield _progress("rewrite", str(exc), pct, best_score["score"])
                    break
                skip_provider(exc.provider)
                nxt = llm_resolve()
                if nxt is None:
                    yield _progress(
                        "rewrite",
                        f"{exc.provider} did not finish. No other model is available.",
                        pct,
                        best_score["score"],
                    )
                    break
                yield _progress(
                    "rewrite",
                    f"{exc.provider} did not finish. Continuing this resume on {nxt['name']}.",
                    pct,
                    best_score["score"],
                )
                continue
            except RuntimeError as exc:
                audit["notes"].append(str(exc))
                yield _progress("rewrite", str(exc), pct, best_score["score"])
                break
            except (ValidationError, json.JSONDecodeError, KeyError, ValueError) as exc:
                audit["notes"].append(f"rewrite attempt {attempt + 1} rejected: {exc}")
                yield _progress(
                    "rewrite",
                    f"Pass {attempt + 1} was rejected by the fact-bank validator ({exc}). "
                    "Retrying without invented claims.",
                    pct,
                    best_score["score"],
                )
                continue
            cand = score_resume(candidate, parsed)
            openings = adjacent_openings(candidate, parsed, bank)
            if cand["score"] >= best_score["score"]:
                best, best_score, final_payload = candidate, cand, payload
            delta = cand["score"] - prev
            if delta > 0:
                move = f"up {delta} points"
            elif delta < 0:
                move = f"down {abs(delta)} points (kept the better draft)"
            else:
                move = "unchanged"
            room = list(cand.get("missing_in_bank") or []) + openings
            hit = cand["score"] >= TARGET
            yield _progress(
                "score",
                f"Pass {attempt + 1} finished. ATS {prev}% → {cand['score']}% ({move}). "
                + (
                    "Target reached."
                    if hit
                    else f"Still room to phrase from the fact bank: {_csv(room)}."
                ),
                pct + 2,
                cand["score"],
            )
            if best_score["score"] >= TARGET:
                break
            if not room and cand["score"] <= prev:
                yield _progress(
                    "rewrite",
                    "Stopping extra passes — the job's remaining tools have no neighbor in the fact bank.",
                    pct + 2,
                    cand["score"],
                )
                break

        if final_payload is not None:
            doc = best
            audit["mode"] = "rewrite"
            audit["ats_score"] = best_score["score"]
            spec = llm_resolve()
            if spec:
                audit["notes"].append(f"Rewritten with {spec['name']} ({spec['model']})")
            src = final_payload.get("audit") if isinstance(final_payload, dict) else None
            if isinstance(src, dict):
                if src.get("interview") in ("Yes", "No"):
                    audit["interview"] = src["interview"]
                if isinstance(src.get("reject_reasons"), list):
                    audit["reject_reasons"] = [str(x) for x in src["reject_reasons"][:3]]
                if isinstance(src.get("gaps"), list):
                    extra: list[str] = []
                    for raw in src["gaps"]:
                        extra.extend(unsupported_clauses(str(raw), bank))
                    audit["gaps"] = list(dict.fromkeys(list(audit["gaps"]) + extra))
        else:
            audit["notes"].append("kept original wording after failed rewrite passes")
            doc = selected
            try:
                validate_document(doc, bank, jd)
            except ValidationError as exc:
                audit["notes"].append(f"source resume warning: {exc}")
            if provider_stop is not None and is_pinned():
                kept = f"{provider_stop} Kept your original bullets."
            elif provider_stop is not None:
                kept = "No rewrite finished. Kept your original bullets."
            else:
                kept = "Kept your original bullets. Rewrite passes did not produce a valid improvement."
            yield _progress(
                "rewrite",
                kept,
                88,
                base["score"],
            )
    else:
        if rewrite and not llm_available():
            from backend.llm.llm import status as llm_status

            st = llm_status()
            note = st.get("note") or "No free LLM backend; selected original bullets only"
            audit["notes"].append(note)
            yield _progress("rewrite", note, 70, base["score"])
        validate_document(doc, bank, jd)

    if tool_gaps or years:
        audit["interview"] = "No"
        reasons: list[str] = []
        if years:
            reasons.append(years)
        if tool_gaps:
            reasons.append(
                "The job asks for "
                + ", ".join(tool_gaps[:6])
                + ", which the fact bank does not support."
            )
        audit["reject_reasons"] = (reasons + list(audit.get("reject_reasons") or []))[:3]

    final_score = score_resume(doc, parsed)
    audit["ats_score"] = final_score["score"]
    audit["facts_used"] = _facts_used(doc)
    audit["missing_skills"] = final_score["missing_in_bank"]
    _strip(doc)
    if _halted(halted):
        return
    yield _progress(
        "finalize",
        f"Done matching. Final ATS {final_score['score']}%. Compiling the PDF and cover letter next.",
        92,
        final_score["score"],
    )
    yield {"type": "done", "doc": doc, "audit": audit}


def tailor(
    jd: str,
    target_role: str = "",
    company: str = "",
    rewrite: bool = True,
    bank: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Non-streaming convenience wrapper around tailor_stream."""
    doc: dict[str, Any] = {}
    audit: dict[str, Any] = {}
    for event in tailor_stream(jd, target_role, company, rewrite, bank):
        if event.get("type") == "done":
            doc, audit = event["doc"], event["audit"]
    return doc, audit

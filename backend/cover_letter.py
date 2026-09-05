from __future__ import annotations

import json
import re
from typing import Any

from backend.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from backend.fact_bank import load_bank
from backend.textutil import YEARS_RE, percents
from backend.validator import KNOWN_TECH_HINTS, ValidationError

MAX_WORDS = 250

COVER_SYSTEM = """You write a short job application cover letter.

Pain-point method:
- Identify the primary business/engineering problem in the job description.
- Explain how the candidate's EXISTING experience addresses it.
- Do not summarize the whole resume.

Hard rules:
- 250 words or fewer.
- Do not invent employers, tools, metrics, or years of experience.
- Only mention companies and percentages that appear in the provided resume JSON.
- No 'AI generated', no ATS talk, no begging.
- First person, professional, specific.

Return JSON: {"pain_point": "...", "cover_letter": "..."}
"""


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def validate_cover_letter(
    text: str,
    bank: dict[str, Any] | None = None,
    company: str = "",
) -> None:
    bank = bank or load_bank()
    errors: list[str] = []
    body = (text or "").strip()
    if not body:
        errors.append("cover letter is empty")
    if word_count(body) > MAX_WORDS:
        errors.append(f"cover letter exceeds {MAX_WORDS} words")
    if YEARS_RE.search(body):
        errors.append("cover letter invents years of experience")
    locked = {m["value"].lower() for m in bank.get("metrics_lock") or []}
    extra = percents(body) - locked
    if extra:
        errors.append(f"cover letter invented metrics: {sorted(extra)}")
    known = {s.lower() for g in bank["skill_groups"] for s in g["items"]}
    blob = body.lower()
    for hint in KNOWN_TECH_HINTS:
        if hint in blob and hint not in known:
            errors.append(f"cover letter introduces ungrounded tool {hint!r}")
    if errors:
        raise ValidationError("; ".join(errors))


def template_cover_letter(
    jd: str,
    target_role: str,
    company: str,
    doc: dict[str, Any],
    bank: dict[str, Any] | None = None,
) -> str:
    bank = bank or load_bank()
    role = target_role or "this role"
    firm = company or "your team"
    recent = (doc.get("roles") or [{}])[0]
    bullets = [b["text"] for b in (recent.get("bullets") or [])[:2]]
    proof = " ".join(bullets) if bullets else bank["default_summary"]
    # Keep one tight paragraph plus a close.
    text = (
        f"I am writing for the {role} opening at {firm}. "
        f"The posting calls for production backend and AI systems that stay reliable under load, "
        f"which is the work I have been doing as {recent.get('title', 'an engineer')} at {recent.get('company', 'Sprouts.ai')}. "
        f"{proof} "
        f"I would like to bring that same mix of FastAPI services, provider orchestration, and cost-aware LLM workflows to {firm}."
    )
    # Trim if a long proof blob pushes over the cap.
    words = text.split()
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS])
    validate_cover_letter(text, bank, company)
    return text


def _client():
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": OPENAI_API_KEY}
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
    return OpenAI(**kwargs)


def generate_cover_letter(
    jd: str,
    target_role: str,
    company: str,
    doc: dict[str, Any],
    rewrite: bool = True,
) -> tuple[str, str]:
    """Returns (letter, mode) where mode is rewrite|template."""
    bank = load_bank()
    if rewrite and OPENAI_API_KEY:
        client = _client()
        slim = {
            "summary": doc.get("summary"),
            "roles": [
                {
                    "company": r["company"],
                    "title": r["title"],
                    "bullets": [b["text"] for b in r.get("bullets") or []][:3],
                }
                for r in (doc.get("roles") or [])[:3]
            ],
        }
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            temperature=0.3,
            messages=[
                {"role": "system", "content": COVER_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"TARGET ROLE: {target_role}\nCOMPANY: {company}\n\n"
                        f"JOB DESCRIPTION:\n{jd}\n\nRESUME JSON:\n{json.dumps(slim)}"
                    ),
                },
            ],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        letter = str(payload.get("cover_letter") or "").strip()
        try:
            validate_cover_letter(letter, bank, company)
            return letter, "rewrite"
        except (ValidationError, json.JSONDecodeError):
            pass
    return template_cover_letter(jd, target_role, company, doc, bank), "template"

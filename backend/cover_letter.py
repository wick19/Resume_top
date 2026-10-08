from __future__ import annotations

import json
import re
from typing import Any

from backend.llm.llm import ProviderFailed, chat, is_pinned, llm_available, resolve, skip_provider
from backend.resume.fact_bank import load_bank
from backend.textutil import YEARS_RE, percents
from backend.resume.validator import ValidationError

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
    jd: str = "",
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
    # Percentages are grounded if they appear anywhere in the fact bank: the
    # explicit metrics_lock (default bank) or any bullet's text / locked_numbers
    # (uploaded banks). Anything else is invented.
    locked = {m["value"].lower() for m in bank.get("metrics_lock") or []}
    for section in ("roles", "projects"):
        for node in bank.get(section) or []:
            for bullet in node.get("bullets") or []:
                locked |= percents(bullet.get("text") or "")
                locked |= {p.lower() for p in bullet.get("locked_numbers") or []}
    extra = percents(body) - locked
    if extra:
        errors.append(f"cover letter invented metrics: {sorted(extra)}")
    if jd:
        from backend.match.scoring import gap_skills
        from backend.textutil import skill_in_text

        invented = [phrase for phrase in gap_skills(jd, bank) if skill_in_text(phrase, body)]
        if invented:
            errors.append(
                "cover letter names requirements with no base in the fact bank: "
                + ", ".join(invented)
            )
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
    title = recent.get("title") or "an engineer"
    at_company = f" at {recent['company']}" if recent.get("company") else ""
    bullets = [b["text"] for b in (recent.get("bullets") or [])[:2]]
    proof = " ".join(bullets) if bullets else (bank.get("default_summary") or "")
    # One tight paragraph, no invented tools — only content already on the resume.
    text = (
        f"I am writing to apply for the {role} opening at {firm}. "
        f"The role maps closely to my work as {title}{at_company}. "
        f"{proof} "
        f"I would welcome the chance to bring that same experience to {firm}."
    )
    words = text.split()
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS])
    validate_cover_letter(text, bank, company)
    return text


def generate_cover_letter(
    jd: str,
    target_role: str,
    company: str,
    doc: dict[str, Any],
    rewrite: bool = True,
    bank: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Returns (letter, mode) where mode is rewrite|template."""
    bank = bank or load_bank()
    if rewrite and llm_available():
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
        while True:
            try:
                raw = chat(
                    [
                        {"role": "system", "content": COVER_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"TARGET ROLE: {target_role}\nCOMPANY: {company}\n\n"
                                f"JOB DESCRIPTION:\n{jd}\n\nRESUME JSON:\n{json.dumps(slim)}"
                            ),
                        },
                    ],
                    temperature=0.3,
                )
                payload = json.loads(raw)
                letter = str(payload.get("cover_letter") or "").strip()
                validate_cover_letter(letter, bank, company)
                return letter, "rewrite"
            except ProviderFailed as exc:
                if is_pinned() or resolve() is None:
                    break
                skip_provider(exc.provider)
                if resolve() is None:
                    break
            except Exception:
                break
    return template_cover_letter(jd, target_role, company, doc, bank), "template"

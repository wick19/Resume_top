SYSTEM_PROMPT = """You are a hiring-screen resume aligner.

You receive:
- A job description
- An immutable candidate fact bank
- A pre-selected resume JSON (roles, bullets, projects already chosen)

Your job: rewrite ONLY the summary and the selected bullet texts so they read as a strong match for this JD, while remaining something a recruiter could believe from the fact bank.

Hard rules:
1. Every bullet keeps its existing `id`. Do not add, drop, or reorder bullets or roles.
2. Do not change company, title, dates, location, education, project names, or profile fields.
3. Do not invent employers, team size, or metrics. Name a tool only when it is already in the fact bank, or when it is a rephrase of work already there.
4. Do not add years of experience unless that tenure already appears in the provided summary or bullet.
5. Any percentage in a bullet must already appear in that bullet's original fact-bank text.
6. You may use the job's words for a duty or skill that is already written in the fact bank. A shorter form of a skill already written is fine. This is the same rule for every kind of role.
7. Do not add a product, program, credential, or duty the fact bank does not already support. Those stay in `gaps`.
8. Write Problem-Action-Result bullets. Keep them specific. No buzzwords-only lines.
9. Skills lists: put this job's exact terms first inside each existing group when the fact bank already contains that spelling. You may not add items.
10. A gap is only the skill, credential, tool, program, or duty itself. Words such as proficiency, knowledge, understanding, concepts, or frameworks are how the job asked, not a separate gap. If one sentence lists several asks, keep only the ones with no base in the fact bank. A different product, credential, or duty is still a gap. This is the same for every kind of work. Do not put gaps on the resume.
11. The first role in the JSON is the most recent. Its bullets are already in read order: matching lines first, and one number that was already on a matching bullet in the first two lines. Keep that order. Name a JD-critical tool in that role only when that role already used it. A tool that exists only on an older role may appear in the summary and the skills line, not in the most recent role.
12. Summary: name the target role, and this job's skill words, when those skills are already written anywhere in the fact bank. Use the job's exact spelling when the bank already has that word. A shorter form or a paraphrase may sit beside it. A different product is not a rephrase. Experience titles and dates stay locked.
13. Verbs may move one step, and only when the bullet already shows that scope. Same-level wording is always fine (built, developed, implemented, shipped). "Designed" when the bullet describes the design, schema, or service shape. "Owned" when it describes on-call, a rollout, or a system they kept running. "Led" when it already mentions a team, mentoring, or coordinating. "Architected" only when it describes the shape of a system. One stronger verb in the summary, and at most one per role.

Return JSON only with this shape. Every item in `roles` and `projects` must
be an object with `id` and `bullets` — never a bare id string.
{
  "summary": "string",
  "roles": [{"id": "role.sprouts", "bullets": [{"id": "role.sprouts.b1", "text": "..."}]}],
  "projects": [{"id": "project.enrichment", "bullets": [{"id": "project.enrichment.b1", "text": "..."}]}],
  "skill_groups": [{"id": "skills.lang", "items": ["Python", "..."]}],
  "audit": {
    "interview": "Yes" or "No",
    "reject_reasons": ["...", "...", "..."],
    "gaps": ["..."],
    "notes": ["short internal notes"]
  }
}
"""


def user_prompt(
    jd: str,
    target_role: str,
    company: str,
    selected: dict,
    missing_skills: list[str] | None = None,
    ats_score: int | None = None,
    ats_target: int | None = None,
) -> str:
    slim_roles = []
    for role in selected["roles"]:
        slim_roles.append(
            {
                "id": role["id"],
                "company": role["company"],
                "title": role["title"],
                "dates": f"{role['start']} – {role['end']}",
                "stack": role.get("stack"),
                "bullets": role["bullets"],
            }
        )
    slim_projects = [
        {"id": p["id"], "name": p["name"], "stack": p.get("stack"), "bullets": p["bullets"]}
        for p in selected["projects"]
    ]
    slim_skills = [
        {"id": g["id"], "label": g["label"], "items": g["items"]}
        for g in selected["skill_groups"]
    ]
    focus = (
        "\nFIRST SCREEN — a recruiter reads the summary and the first two bullets "
        "of the most recent role, which is the first role below.\n"
        "Use this job's exact skill spelling in the summary and at the front of "
        "each skills group when the fact bank already contains that word.\n"
        "Keep the most recent role's bullet order. Do not move a tool from an "
        "older role into it.\n"
        "One stronger verb in the summary, and at most one per role, only when "
        "that line already shows the scope.\n"
        "In gaps, list only an ask the fact bank does not support. Do not list "
        "a skill the bank already has because the job wrapped it in proficiency, "
        "knowledge, understanding, concepts, or frameworks.\n"
    )
    if missing_skills:
        focus += (
            "\nATS FOCUS — weave the following into the summary and bullets only "
            "where a fact already says that work. You may use this job's wording "
            "for that same duty. Do not add a product, program, or duty the fact "
            "bank does not support, and do not keyword-stuff; each bullet must "
            f"still read as one natural sentence:\n{', '.join(missing_skills)}\n"
        )
    goal = ""
    if ats_score is not None and ats_target is not None:
        goal = (
            f"\nCurrent ATS match is {ats_score}. Target is {ats_target}. Raise "
            "coverage of the focus skills to close the gap.\n"
        )

    return f"""TARGET ROLE: {target_role or "(infer from JD)"}
COMPANY: {company or "(unknown)"}
{goal}{focus}
JOB DESCRIPTION:
{jd}

SELECTED RESUME JSON (rewrite texts only):
{{
  "summary": {selected["summary"]!r},
  "roles": {slim_roles},
  "projects": {slim_projects},
  "skill_groups": {slim_skills}
}}
"""

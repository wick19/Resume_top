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
7. Do not add a product, program, or duty the fact bank does not already support. Those stay in `gaps`.
8. Write Problem-Action-Result bullets. Keep them specific. No buzzwords-only lines.
9. Skills lists: you may reorder items inside an existing group; you may not add items.
10. If the JD asks for something with no base in the fact bank, list it in `gaps`. Do not put it on the resume.
11. Recency: put JD-critical tools in the most recent role's wording when those tools already exist on that role, or when they are only a rephrase of work already there.

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
    focus = ""
    if missing_skills:
        focus = (
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

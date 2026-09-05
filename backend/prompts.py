SYSTEM_PROMPT = """You are a hiring-screen resume aligner.

You receive:
- A job description
- An immutable candidate fact bank
- A pre-selected resume JSON (roles, bullets, projects already chosen)

Your job: rewrite ONLY the summary and the selected bullet texts so they read as a strong match for this JD, while remaining something a recruiter could believe from the fact bank.

Hard rules:
1. Every bullet keeps its existing `id`. Do not add, drop, or reorder bullets or roles.
2. Do not change company, title, dates, location, education, project names, or profile fields.
3. Do not invent employers, tools, products, team size, or metrics.
4. Any percentage in a bullet must already appear in that bullet's original fact-bank text.
5. Use the job's nouns and verbs when they describe work already in that fact (FastAPI, REST APIs, provider orchestration, caching, CI/CD, etc.).
6. Write Problem-Action-Result bullets. Keep them specific. No buzzwords-only lines.
7. Skills lists: you may reorder items inside an existing group; you may not add items.
8. If the JD asks for something with no base in the fact bank, list it in `gaps`. Do not put it on the resume.
9. Recency: put JD-critical tools in the most recent role's wording when those tools already exist on that role.

Return JSON only with this shape:
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


def user_prompt(jd: str, target_role: str, company: str, selected: dict) -> str:
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
    return f"""TARGET ROLE: {target_role or "(infer from JD)"}
COMPANY: {company or "(unknown)"}

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

import json

from fastapi.testclient import TestClient

from backend.main import app
from backend.resume.resume_parser import build_fact_bank_heuristic, extract_text

client = TestClient(app)

SAMPLE_RESUME = """Jane Doe
jane.doe@example.com | +1 415 555 0100 | https://linkedin.com/in/janedoe | https://github.com/janedoe

SUMMARY
Backend engineer focused on Python APIs and data platforms.

EXPERIENCE
Senior Backend Engineer   Acme Corp   Jan 2022 - Present
- Built FastAPI services handling heavy traffic with Redis caching.
- Designed PostgreSQL schemas and REST APIs for billing, improving latency by 30%.

Software Engineer   Beta LLC   Jun 2019 - Dec 2021
- Developed Django applications and CI/CD pipelines using Docker and Jenkins.

PROJECTS
Realtime Analytics Dashboard | Python, React, Kafka
- Built streaming ingestion and dashboards for event analytics.

EDUCATION
State University   B.S. in Computer Science   2015 - 2019

SKILLS
Languages: Python, JavaScript, SQL
Backend: FastAPI, Django, REST APIs, PostgreSQL, Redis
Cloud: Docker, Kubernetes, AWS, CI/CD
"""


def _auth():
    from backend.auth import login_user, register_user

    register_user("upload@test.local", "password1")
    _user, token = login_user("upload@test.local", "password1")
    return {"Authorization": f"Bearer {token}"}


def test_heuristic_parser_extracts_structure():
    bank = build_fact_bank_heuristic(SAMPLE_RESUME)
    assert bank["profile"]["name"] == "Jane Doe"
    assert bank["profile"]["email"] == "jane.doe@example.com"
    assert len(bank["roles"]) == 2
    assert bank["roles"][0]["title"].startswith("Senior Backend Engineer")
    assert bank["roles"][0]["company"] == "Acme Corp"
    # Locked metric survives parsing.
    joined = " ".join(b["text"] for b in bank["roles"][0]["bullets"])
    assert "30%" in joined
    assert any("30%" in (b["locked_numbers"] or []) for b in bank["roles"][0]["bullets"])
    assert len(bank["projects"]) == 1
    assert len(bank["education"]) == 1
    assert bank["skill_groups"]


# Mimics pypdf output: wrapped bullets without a leading •, glued dates, split letters.
PDF_WRAP_RESUME = """Ritwik
ritwik@example.com

Professional Experience
AI Engineer Sep 2025 – Present
Sprouts.ai Bengaluru, Karnataka, India
• Designed production Generative AI and NLP pipelines for enterprise contact enrichment using LLM reasoning,
semantic retrieval, entity resolution, and Elasticsearch to support reliable enrichment and search outcomes.
• Built production AI inference and retrieval services using Azure OpenAI, Hugging Face Transformers, TensorFlow,
and PyTorch for LLM-powered chat, embeddings, batch processing, ranking, and semantic search.
Python F ull Stack DeveloperFeb 2024 – Jan 2025
TekGigz LLC Frisco, Texas, USA
• Developed a finance-focused web application using Python, Flask, Django, and PostgreSQL to streamline
transaction processing, vendor management, and real-time financial reporting.
Software Development InternJun 2019 – Aug 2019
PTC Onshape Inc. Pune, Maharashtra, India
• Contributed to a cloud-based engineering design platform.
Adidas May 2020 – Mar 2021
Campus Ambassador Chennai, Tamil Nadu, India
• Led campus outreach initiatives.
Selected Engineering Projects
Portfolio Concierge — Multilingual V oice AI | JavaScript, React, LLM
• Built and deployed a multilingual Voice AI assistant.
Distributed Hotel Management Platform | Python, Django, PostgreSQL
• Designed a scalable distributed database platform.
Education
University of Southern Mississippi Hattiesburg, MS
Master of Science in Computer and Information Science Jan 2022 – Dec 2023
SRM Institute of Science And Technology Chennai, Tamil Nadu
Bachelor of Technology in Computer Science Jun 2017 – Jun 2021
Technical Expertise
Languages: Python, JavaScript, SQL
"""


def test_heuristic_parser_joins_pdf_wrap_lines_and_real_titles():
    from backend.resume.resume_parser import suggested_titles

    bank = build_fact_bank_heuristic(PDF_WRAP_RESUME)
    titles = [r["title"] for r in bank["roles"]]
    assert titles[0] == "AI Engineer"
    assert titles[1] == "Python Full Stack Developer"
    assert "semantic retrieval" not in titles
    assert len(bank["roles"]) == 4
    first_bullets = " ".join(b["text"] for b in bank["roles"][0]["bullets"])
    assert "semantic retrieval" in first_bullets
    assert suggested_titles(bank) == ["AI Engineer", "Python Full Stack Developer"]
    assert bank["roles"][0]["company"].startswith("Sprouts.ai")
    assert bank["roles"][1]["company"].startswith("TekGigz")
    assert any(r["title"] == "Campus Ambassador" for r in bank["roles"])
    assert len(bank["projects"]) >= 2
    assert len(bank["education"]) == 2


# pypdf artefacts from an HR resume: glued bullets, split headings, Key Achievements.
HR_PDF_RESUME = """Vaishnavi Sharma
vaishnavi@example.com
PROFESSIONAL SUMMAR Y
Results-driven Human Resources and Talent Acquisition professional with 5+ years of experience.
CORE SKILLS
Talent Acquisition:End-to-End Recruitment, Tech Hiring, Campus Hiring
TOOLS & PLA TFORMS
LinkedIn Recruiter, Naukri, Microsoft Excel
PROFESSIONAL EXPERIENCE
Associate Human Resources October 2024 – Present
Sprouts.ai Bengaluru
•Managing the complete hiring lifecycle, including bulk campus hiring, sourcing, screening, interviewing, and
onboarding candidates while aligning hiring efforts with business requirements.
•Driving seamless onboarding experiences, conducting exit interviews, managing exit documentation, and
ensuring smooth offboarding processes.
Talent Acquisition Executive February 2023 – October 2024
Thimblerr Bengaluru
•Collaborated with hiring managers to understand hiring requirements and role responsibilities.
•Utilized job portals, LinkedIn, social media, and professional networks to source potential candidates.
Talent Acquisition Executive November 2021 – February 2023
Newton School Bengaluru
•Coordinated with hiring managers to identify staffing requirements.
•Sourced candidates through online platforms, job portals, social media, and professional networks.
KEY ACHIEVEMENTS
•Successfully onboarded 40+ employees while ensuring a seamless joining experience at Sprouts.ai.
•Successfully hired leadership talent, including a Vice President of Product and an Associate Director – Program
Management.
•Successfully filled 11+ sales positions within one month at Newton School.
EDUCA TION
Dr. K. N. Modi Institute of Engineering and T echnology Modinagar, Uttar Pradesh
Bachelor of Computer Applications 2018 – 2021
"""


def test_heuristic_parser_hr_titles_not_achievement_lines():
    from backend.resume.resume_parser import suggested_titles

    bank = build_fact_bank_heuristic(HR_PDF_RESUME)
    titles = [r["title"] for r in bank["roles"]]
    assert titles[0] == "Associate Human Resources"
    assert titles[1] == "Talent Acquisition Executive"
    assert titles[2] == "Talent Acquisition Executive"
    assert len(bank["roles"]) == 3
    assert all("Successfully hired" not in (r["title"] or "") for r in bank["roles"])
    assert bank["roles"][0]["company"].startswith("Sprouts.ai")
    assert bank["roles"][1]["company"].startswith("Thimblerr")
    assert bank["roles"][2]["company"].startswith("Newton")
    assert len(bank["roles"][0]["bullets"]) >= 2
    assert "hiring lifecycle" in bank["roles"][0]["bullets"][0]["text"]
    chips = suggested_titles(bank)
    assert chips[0] == "Associate Human Resources"
    assert chips[1] == "Talent Acquisition Executive"
    assert not any("Vice President" in t or "Successfully" in t for t in chips)
    assert bank["education"]
    assert bank["skill_groups"]


def test_skill_headings_and_jobs_only_skills_still_fill_the_section():
    from backend.resume.resume_parser import normalize_bank

    competencies = SAMPLE_RESUME.replace("SKILLS", "Core Competencies")
    bank = build_fact_bank_heuristic(competencies)
    labels = [group["label"].lower() for group in bank["skill_groups"]]
    assert any("language" in label for label in labels)
    assert any("Python" in group["items"] for group in bank["skill_groups"])

    tools = SAMPLE_RESUME.replace("SKILLS", "Tools & Technologies")
    assert build_fact_bank_heuristic(tools)["skill_groups"]

    jobs_only = normalize_bank({
        "profile": {"name": "Jane Doe"},
        "default_summary": "",
        "roles": [{
            "company": "Acme",
            "title": "Engineer",
            "stack": ["Python", "Kubernetes"],
            "bullets": [{"text": "Built services.", "skills": ["FastAPI"]}],
        }],
        "projects": [{"name": "Demo", "stack": ["PostgreSQL"], "bullets": []}],
        "skill_groups": [],
    })
    items = [item.lower() for item in jobs_only["skill_groups"][0]["items"]]
    assert jobs_only["skill_groups"][0]["label"] == "Technical Skills"
    assert {"python", "kubernetes", "fastapi", "postgresql"} <= set(items)


def test_extract_text_txt(tmp_path):
    p = tmp_path / "resume.txt"
    p.write_text(SAMPLE_RESUME, encoding="utf-8")
    assert "Jane Doe" in extract_text(p)


def test_upload_sets_source_of_truth_and_tailor_uses_it(tmp_path, monkeypatch):
    import backend.resume.compiler as compiler
    import backend.store.logbook as logbook
    import backend.pipeline as pipeline

    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline, "output_folder", lambda company, role, revision=1: tmp_path / "run"
    )
    monkeypatch.setattr(logbook, "LOG_PATH", tmp_path / "applications.jsonl")
    monkeypatch.setattr(pipeline, "append_application", logbook.append_application)

    headers = _auth()
    up = client.post(
        "/v1/resume/upload",
        headers=headers,
        files={"file": ("resume.txt", SAMPLE_RESUME, "text/plain")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["summary"]["roles"] == 2

    status = client.get("/v1/resume", headers=headers)
    assert status.json()["uploaded"] is True

    res = client.post(
        "/v1/tailor",
        headers=headers,
        json={
            "job_description": "Hiring a Python backend engineer with FastAPI, "
            "PostgreSQL, Redis, Docker, and REST APIs. Django a plus.",
            "target_role": "Backend Engineer",
            "company": "Umbrella",
            "extractor": "paste",
            "rewrite": False,
        },
    )
    assert res.status_code == 200, res.text
    # The compiled resume must be built from Jane's uploaded bank, not Ritwik's.
    produced = json.loads((tmp_path / "run" / "resume.json").read_text())
    assert produced["profile"]["name"] == "Jane Doe"
    assert res.json()["audit"]["ats_target"] == 97


def test_tailor_stream_emits_progress_and_result(tmp_path, monkeypatch):
    import backend.resume.compiler as compiler
    import backend.store.logbook as logbook
    import backend.pipeline as pipeline

    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline, "output_folder", lambda company, role, revision=1: tmp_path / "run2"
    )
    monkeypatch.setattr(logbook, "LOG_PATH", tmp_path / "applications.jsonl")
    monkeypatch.setattr(pipeline, "append_application", logbook.append_application)

    events = []
    with client.stream(
        "POST",
        "/v1/tailor/stream",
        json={
            "job_description": "AI Engineer: Python, FastAPI, Redis, PostgreSQL, "
            "Docker, Kubernetes, LLMs, REST APIs.",
            "target_role": "AI Engineer",
            "company": "Acme",
            "extractor": "paste",
            "rewrite": False,
        },
    ) as res:
        assert res.status_code == 200
        for line in res.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    stages = [e.get("stage") for e in events if e.get("type") == "progress"]
    assert "parse" in stages and "finalize" in stages
    result = [e for e in events if e.get("type") == "result"]
    assert result and result[0]["pdf_path"].endswith(".pdf")
    assert result[0]["audit"]["ats_target"] == 97
    assert any(e.get("type") == "run" and e.get("id") for e in events)


def test_run_stays_readable_after_the_stream_closes(tmp_path, monkeypatch):
    import backend.resume.compiler as compiler
    import backend.store.logbook as logbook
    import backend.pipeline as pipeline

    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline, "output_folder", lambda company, role, revision=1: tmp_path / "run3"
    )
    monkeypatch.setattr(logbook, "LOG_PATH", tmp_path / "applications.jsonl")
    monkeypatch.setattr(pipeline, "append_application", logbook.append_application)

    headers = _auth()
    events = []
    with client.stream(
        "POST",
        "/v1/tailor/stream",
        headers=headers,
        json={
            "job_description": "AI Engineer: Python, FastAPI, Redis, PostgreSQL, "
            "Docker, Kubernetes, LLMs, REST APIs.",
            "target_role": "AI Engineer",
            "company": "Acme",
            "extractor": "paste",
            "rewrite": False,
        },
    ) as res:
        assert res.status_code == 200
        for line in res.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    run_id = next(event["id"] for event in events if event.get("type") == "run")
    saved = client.get(f"/v1/runs/{run_id}", headers=headers)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["status"] == "done"
    assert body["label"] == "Acme — AI Engineer"
    assert body["result"]["resume_id"]
    assert body["result"]["audit"]["ats_score"] >= 0
    assert body["log"]
    assert client.get("/v1/runs/active", headers=headers).json()["run"] is None

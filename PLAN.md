# Resume Tailor — Plan

Personal pipeline: open a job on any board, generate a JD-aligned resume PDF from a locked fact bank, apply.

This is not a ChatGPT prompt pack. It is a local tool whose job is to increase interview callbacks by making every application look like the same engineer the screener is searching for — without inventing a career.

---

## 1. Why this exists

Manual flow (paste resume + JD + “hiring manager” prompt into ChatGPT for every Naukri / Cutshort / Foundit / Monster / career-page listing) is slower than applying. Generic AI resumes also read as fluff, which recruiters discard in a few seconds.

What actually sits between you and a recruiter:

1. **Parser** — ATS / career portal turns the PDF into fields (name, titles, dates, skills, bullets). If it cannot parse a line, that line does not exist.
2. **Match / rank** — the posting’s required titles, skills, and qualifications are compared to those fields. Modern systems use **keywords plus meaning**, not a single magic “ATS %”.
3. **Human skim** — often under 10 seconds. First screen: title, last company, stack in recent bullets, one or two proof numbers.

The product compresses steps 2–3 into one click: capture JD → map it onto *your* work → emit a clean PDF.

**Success metric:** more recruiter replies and interview loops per week of applying.  
**Not a product claim:** “this guarantees interviews.” Fit, volume of *relevant* applications, LinkedIn profile, and referrals still matter. The tool only removes the slow, inconsistent tailoring step.

---

## 2. What we are building

A **user-triggered** tailor loop:

```
[Job page you already opened]
        │  one click, or paste JD
        ▼
[JD extractor]  →  structured job: company, title, requirements, stack
        ▼
[Fact bank]     →  your real roles, projects, skills, metrics (immutable)
        ▼
[Aligner]       →  which bullets/projects to surface, how to phrase them
        ▼
[Compiler]      →  ATS-readable PDF (page count follows content, not a 1-page rule)
        ▼
[You apply]     →  upload that PDF on the same site
```

Operator: **Ritwik**. Source resume: `RitwikRN.pdf` (LaTeX, 2 pages, Aug 2026).

### In scope (v1)

- Locked JSON fact bank derived from the current resume
- Capture JD from the **current tab** (LinkedIn, Naukri, Cutshort, Foundit, Monster, generic career pages) with a **paste-JD fallback** when the DOM is unknown
- Recruiter-style audit **in the app UI only** (yes/no skim, gaps, weak bullets) — never printed on the PDF
- Tailored resume PDF + optional cover letter
- Local FastAPI service + Typst/LaTeX template (same family as the current resume)
- Per-application output folder: company, role, date, PDF, JD snapshot

### Out of scope (v1)

- Mass scraping of LinkedIn / Naukri behind the scenes
- Auto-submit to 1,000 jobs
- Fake ATS scores labeled as “LinkedIn’s score”
- Editing `RitwikRN.pdf` in place (PDFs are a bad source of truth; the fact bank is)

---

## 3. Screening baseline (what we optimize for)

We do **not** have LinkedIn Hiring Assistant’s model weights. We use what LinkedIn and ATS vendors have actually published, plus parser reality.

### LinkedIn Recruiter / Hiring Assistant (public)

From [LinkedIn Engineering — Recruiter search](https://www.linkedin.com/blog/engineering/recommendations/ai-behind-linkedin-recruiter-search-and-recommendation-systems) and [Hiring Assistant retrieval](https://www.linkedin.com/blog/engineering/ai/semantic-search-for-ai-agents-at-scale-retrieval-and-ranking-for-linkedins-hiring-assistant):

| Signal | What it means for the resume |
| --- | --- |
| Canonical **title** + **skills** | Use the job’s title family and the exact skill names they search (FastAPI, not only “Python APIs”) |
| Work-experience similarity | Skills must show up **inside recent bullets**, not only a Skills dump |
| Query → qualifications list | Mirror required qualifications in summary + last 1–2 roles |
| Semantic retrieval (embeddings) | Related phrasing can match (FastAPI ↔ REST APIs, Redis + async ↔ pipelines) **if the work is real** |
| Location / seniority | Keep dates, location, and level consistent with the fact bank |
| LLM “does this person fit the brief?” | Bullets should read like evidence, not a keyword list pasted from the JD |

LinkedIn Recruiter also ranks on **response likelihood** and other engagement features we cannot control from a PDF. We only control **qualification fit** and **parseability**.

### ATS / career portals (Naukri, Foundit, Monster, Workday, Lever, Greenhouse)

Public, repeatable rules (Jobscan and similar ATS research; parser behavior is the same class of problem):

- Single column, standard headings: Experience, Projects, Education, Skills
- Real selectable text (the current resume already is: pdfTeX / LaTeX)
- No text boxes, no skill bars, no white-on-white keyword stuffing
- Exact JD terms **only where the fact bank supports them**
- Recency: last 1–2 roles carry most of the match
- Skills listed first in the Skills section should be the ones this JD cares about
- Metrics beat adjectives

### Dual audience

Every generated resume must pass **both**:

1. Machine: titles, skills, tools, recency  
2. Human: Problem → Action → Result, believable for this career

---

## 4. Source of truth: fact bank

The model is not allowed to invent a biography. It may only **select, reorder, and rephrase** nodes from `data/fact_bank.json`.

Locked fields (never invented, never mutated by the LLM):

- Identity: name, phone, email, LinkedIn, GitHub, portfolio
- Employers, titles, locations, date ranges
- Education (USM MS CIS; SRM B.Tech CSE)
- Numeric metrics already on the resume (20% API time, 25% query, 10% support, 15% deploy issues, 30% release cycle, ~20% UI responsiveness)
- Project names that exist in the bank

### Current career nodes (from `RitwikRN.pdf`)

| Node | Use when JD wants |
| --- | --- |
| Sprouts.ai — AI Engineer (Sep 2025–Present) | Production FastAPI, LLM workflows, provider orchestration, Redis, auth, K8s, GTM/intel product |
| TekGigz — Python Full Stack (Feb 2024–Jan 2025) | Flask/Django, PostgreSQL, REST, reporting UIs, Jenkins, Heroku |
| PTC Onshape intern (2019) | React/Angular, data structures, CI — only if relevant; keep short |
| Adidas campus ambassador | Only for GTM / community / campaign roles |
| Project: Contact enrichment platform | Microservices, multi-provider, async, caching, Docker/K8s |
| Project: Distributed hotel platform | Django, PostgreSQL, Azure SQL, multi-user systems |
| Project: UAV path-loss ML | Sklearn/TF/PyTorch, feature engineering — ML/DS JDs |
| Skills lists | Reordered per JD; items not in the bank stay out |

Adjacent phrasing is allowed **only** when a node already implies the capability (example: async + Redis + enrichment pipelines → “resilient job processing / rate-limited provider I/O”). If there is no base (example: “HFT matching engine”, “FPGA”, “10 years Java”), that requirement is a **gap in the UI**, not a new bullet on the PDF.

The PDF never says “tailored”, “ATS score”, “gap”, or “AI generated”.

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Browser extension (Manifest V3)                        │
│  Site adapters + generic fallback + “use selection”     │
└──────────────────────────┬──────────────────────────────┘
                           │ POST /v1/ingest
                           ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI (localhost)                                    │
│  1. Normalize JD JSON                                   │
│  2. Extract required skills / title / seniority         │
│  3. Score fact-bank nodes vs JD (deterministic overlap  │
│     + LLM mapping constrained by bank IDs)              │
│  4. Emit resume.json (schema-validated)                 │
│  5. Compile PDF via Typst or pdfLaTeX                   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
              output/<company>_<role>_<date>/resume.pdf
```

### Why this split

| Piece | Why |
| --- | --- |
| Extension, not a crawler | You are already on the page. Avoids login-wall scrapers and ToS mass-harvesting. Public job APIs (Remotive / Remote OK / Arbeitnow) are the only bulk search. |
| Site adapters + fallback | Naukri / Cutshort / Foundit / Monster / LinkedIn DOMs differ. Unknown career sites → selected text or paste. |
| Fact bank, not “here is my PDF, rewrite everything” | Stops new employers, new degrees, new percentages. |
| Compiler, not LLM-written DOCX | Current resume is LaTeX; Typst/LaTeX keep layout stable and ATS-parseable. |
| JSON schema on LLM output | If a bullet cites a company/metric not in the bank, reject and retry. |

### Suggested layout

```
Resume_top/
  PLAN.md
  RitwikRN.pdf                 # original, do not overwrite
  data/fact_bank.json
  backend/                     # FastAPI
  templates/resume.typ         # or .tex
  extension/                   # Chrome MV3
  output/                      # generated applications
```

---

## 6. Cross-site JD capture

**Principle:** extract from the page the user is looking at. Do not log into LinkedIn/Naukri as a bot.

| Source | Strategy |
| --- | --- |
| LinkedIn | Known job-description containers; if logged-out wall, user pastes |
| Naukri | Job detail selectors; fallback to article/main text |
| Cutshort | Job body selectors; fallback |
| Foundit / Monster | Shared “jobDesc”-style blocks; fallback |
| Company career sites (Greenhouse, Lever, Workday, custom) | JSON-LD `JobPosting` if present; then `[class*="job-description"]`; then selected text |
| Anything else | “Copy JD” in the popup, or highlight + send selection |

Each ingest stores `url`, `captured_at`, `extractor` (`adapter` \| `jsonld` \| `selection` \| `paste`), and raw text so a bad extract is debuggable.

---

## 7. Aligner (the actual product)

Two stages. Stage A can be mostly deterministic. Stage B is the LLM, tightly boxed.

### Stage A — what to include

- Parse JD into: title, seniority, must-have skills, nice-to-haves, domain (fintech, GTM, ML, platform, …)
- Score each fact-bank role/project by token + synonym overlap
- Pick 3–6 bullets per recent role; drop intern/ambassador unless the JD needs them
- Reorder Skills so JD tools are first
- Choose 1–3 projects that match; omit the rest rather than shrinking font to force one page

### Stage B — how to phrase

System rules (enforced in prompt **and** in a validator):

1. Every bullet maps to a `fact_id`. No orphan sentences.
2. Keep locked metrics exactly (`25%` stays `25%`).
3. Prefer the job’s nouns/verbs when they describe work already in that fact.
4. PAR/STAR: context → what you built → result (metric if the bank has one).
5. Summary is 3–4 lines for *this* role family, not a new identity.
6. No buzzword-only lines (“passionate team player”).

UI after each run (not in the PDF):

- 10-second recruiter call: Interview? Yes/No  
- Top 3 likely rejection reasons  
- Skills in JD with no fact-bank support  
- Diff of which facts were used  

That is the viral “hiring manager” prompt, turned into an API, with the resume already in context.

---

## 8. PDF output

- **No page cap.** Current master is 2 pages; tailored versions may be 1–3 depending on the JD. Do not pad.
- US Letter, single column, standard headings, 10pt-class body (match current look)
- Filename: `Ritwik_<Company>_<Role>.pdf`
- Keep hyperlinks (email, LinkedIn, GitHub, portfolio) — already in the source PDF

---

## 9. What to study (verified, not cloned)

Use these as architecture references. Do not copy their page limits or auto-apply.

| Repo | Stars (approx.) | Steal this | Ignore this |
| --- | --- | --- | --- |
| [srbhr/Resume-Matcher](https://github.com/srbhr/Resume-Matcher) | ~28k | JD vs resume structuring, local LLM harness, keyword/entity split | Building a public SaaS; their UX is not our UX |
| [JaimeYeung/Resume-Tailor-AI](https://github.com/JaimeYeung/Resume-Tailor-AI) | ~36 | Fact extraction, keyword report (hard skill / domain / title), “don’t fabricate” | **One-page trim** — we are not doing that |
| [a-essam23/resume-tailor-ai](https://github.com/a-essam23/resume-tailor-ai) | ~5 | Extension → server → PDF shape | LinkedIn-only; Puppeteer HTML PDFs are weaker for ATS than Typst/LaTeX |
| [Pickle-Pixel/ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) | ~1k | `resume_facts` preserved; tailor ≠ invent | Stage 6 auto-submit and board-wide scraping — out of scope for us |

Prompts worth encoding (assessment style, not copy-paste theatre):

- Recruiter skim: 10s yes/no + reject reasons + missing keywords + weak bullets  
- Then rewrite **only** selected fact-bank bullets into PAR using JD language  
- JSON-only response, validated against schema  

---

## 10. Build order

| Phase | Deliverable | Done when |
| --- | --- | --- |
| 0 | `data/fact_bank.json` from `RitwikRN.pdf` | Every bullet on the PDF has an id; metrics listed once |
| 1 | Typst/LaTeX template that can render the bank with **zero** LLM | Output PDF looks like the current resume |
| 2 | FastAPI `POST /v1/tailor` with pasted JD | Validated `resume.json` + PDF in `output/` |
| 3 | Extension: LinkedIn + Naukri adapters + paste fallback | One click from a real job page |
| 4 | Cutshort, Foundit, Monster, JSON-LD career pages | Fallback still works when adapter misses |
| 5 | Cover letter (pain-point, ≤250 words) + application log | Same ingest, second artifact |

Do not start the extension before the fact bank and compiler work. A pretty button on a hallucinated PDF is worse than copy-paste.

---

## 11. Risks (stated plainly)

| Risk | Mitigation |
| --- | --- |
| Model invents Kafka / years / % | Schema + fact_id validator; reject output |
| JD extract grabs nav/sidebar | Adapters + user “use selection”; store raw capture |
| Keyword stuffing looks like JD clone | Cap overlap; require PAR and real metrics |
| Site HTML changes | Fallback path is first-class, not an afterthought |
| Confusing Cursor PDF view | Cursor shows PDF *source*; open in Preview. Pipeline never depends on Cursor’s renderer |

---

## 12. Decision log

| Decision | Choice |
| --- | --- |
| Page limit | None |
| Apply automation | Human submits |
| Source of truth | JSON fact bank, not the PDF |
| Layout | Typst or LaTeX, ATS-safe single column |
| Sites | All boards via current-tab extract + paste |
| Screening model | Public LinkedIn/ATS signals above, not a fake score formula |
| Interview promise | Optimize for callbacks; do not market a guarantee |

## Implementation status

| Phase | Status |
| --- | --- |
| 0 Fact bank | Done (`data/fact_bank.json`) |
| 1 Compiler | Done (Typst, fpdf2 fallback) |
| 2 Tailor API / CLI | Done (`/v1/tailor`, `python -m backend tailor`) |
| 3–4 Extension adapters | Done (LinkedIn, Naukri, Cutshort, Foundit/Monster, JSON-LD, paste) |
| 5 Cover letter + log | Done (`cover_letter.txt`, `output/applications.jsonl`) |
| Library + 7-day keep/delete | Done (SQLite, `/` UI, per-user login, Docker) |
| Job search | Done via public APIs only (Remotive, Remote OK, Arbeitnow). No LinkedIn/Naukri scrape. |

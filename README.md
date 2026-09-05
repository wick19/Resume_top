# Resume Tailor

Local pipeline: paste a job description (or click the extension on a job page), get a JD-aligned PDF and a short cover letter from a locked fact bank. You apply. The tool does not submit applications.

Phases 0–5 from `PLAN.md` are in place: fact bank, compiler, tailor API, host adapters, cover letter, application log.

## Setup

```bash
cd ~/Desktop/Resume_top
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# create a local .env (not committed) and add OPENAI_API_KEY for rewritten bullets
```

Cursor shows PDFs as raw `%PDF` source. Open generated files in Preview or Chrome.

## Commands

Compile the master resume from the fact bank (no LLM):

```bash
python -m backend render
```

Tailor to a pasted JD. Without an API key this selects/reorders original bullets. With a key it rewrites phrasing, then a validator rejects invented metrics, employers, and tools:

```bash
python -m backend tailor --jd-file data/sample_jd.txt --role "AI Engineer" --company Sprouts
python -m backend tailor --jd-file data/sample_jd.txt --role "AI Engineer" --company Acme --select-only
```

API:

```bash
python -m backend.main
# POST http://127.0.0.1:8000/v1/tailor
# GET  http://127.0.0.1:8000/health
```

```bash
curl -s http://127.0.0.1:8000/v1/tailor \
  -H 'Content-Type: application/json' \
  -d @- <<'EOF'
{
  "job_description": "PASTE JD HERE (at least 40 characters)",
  "target_role": "AI Engineer",
  "company": "Acme",
  "extractor": "paste"
}
EOF
```

Each run writes `output/<company>_<role>_<timestamp>/`:

- `Ritwik_<Company>_<Role>.pdf` — upload this
- `cover_letter.txt` — pain-point letter, 250 words or fewer
- `resume.json` — structured content
- `audit.json` — interview skim, gaps, facts used (not printed on the PDF)
- `job_description.txt` / `capture.json` — what was ingested

A running log of applications is appended to `output/applications.jsonl`. Show it with `python -m backend log`.

## Rules the PDF must follow

- Identity, employers, titles, dates, education, and existing percentages are locked
- New tools/metrics that are not in `data/fact_bank.json` are dropped or rejected
- No page cap
- The PDF never says it was tailored or scored

## Tests

```bash
python -m pytest -q
```

## Library + 7-day cycle

Open http://127.0.0.1:8000 after starting the API. Register, then:

- **Needs a decision** — due on the 7-day cycle. Keep = ask again in 7 days. Delete = remove the file here.
- **Download resume / cover letter** from the same page.

PDFs are ~50KB each. Twenty of them will not fill your RAM. They live in `library/` (disk), grouped by your account and company.

This app cannot delete files from LinkedIn. If you uploaded a PDF there, remove it in LinkedIn’s resume list too.

```bash
python -m backend review
python -m backend jobs -q "AI Engineer"

```

## Find jobs (public APIs, not scraping)

The UI at `/` and `python -m backend jobs -q "AI Engineer"` search **Remotive**, **Remote OK**, and **Arbeitnow**. Those boards publish a free JSON feed. No API key.

This is **not** a LinkedIn / Naukri / Indeed crawler. Those sites block bots and ban accounts. For those, stay on the job page and use the extension, or paste the JD.

## Docker

```bash
docker compose up --build
```

Then open http://localhost:8000 and register. Data stays in a Docker volume, not scattered across your Desktop.

## Cloud / other people logging in

There is **no honest $0 “Dropbox for everyone’s resumes”** that is also private. Free hosts still store the files somewhere.

What this code already does: **each person registers**, and they only see **their** resumes.

To put it on the internet you’d still need a host (Fly.io, Render, a cheap VPS) plus HTTPS. Do not put this on a public URL without `SECRET_KEY` set. I would not use a random free disk for PDFs that have your phone number unless you trust that host.

Local or Docker on your machine is the sane default. Cloud is optional later.

1. Start the API: `python -m backend.main`
2. Chrome → Extensions → Load unpacked → `extension/`
3. Open a job page, click the extension, **Read page**, then **Tailor resume**.

If the site DOM is unknown, paste the JD into the popup. The PDF lands in `output/` and a copy is stored in your library.

## License

MIT. See [LICENSE](LICENSE).

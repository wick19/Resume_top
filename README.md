# Resume Tailor

Local pipeline: register, **upload your resume** (that file becomes the source of truth), paste a job description or click **Tailor** on the job page, get a JD-aligned PDF and a short cover letter. You apply. The tool does not submit applications.

After login the UI streams rewrite passes and shows a climbing ATS match toward **97–98**. That number is our own coverage score of skills already in the uploaded resume, not LinkedIn’s. A requirement the resume does not support stays on the gap list and does not lower that number. If any such gap is present, including a years ask the role dates do not cover, the 10-second skim is “likely no.”

You can leave the run page. The tailor keeps going on this machine. The header shows **Tailoring…** while it runs, then **Result ready**. **Stop** on the run page closes that attempt: no PDF is saved, and it does not block the next tailor. Starting another job does the same to the one already running. The result page has the match, the skim, the gaps, and the PDF and cover-letter downloads. Restarting the API stops a tailor that was still in progress.

Requirement phrases are read from the job itself, for any kind of role. A close rephrase of a duty or skill already written may go on the PDF. A product, program, or duty that is not in the fact bank stays off it. There is no profession list and no role mode.

Rewrite uses a free backend when one is available: Gemini, then Cerebras, Groq, and NVIDIA. Ollama is used only when none of those keys has quota left. There is no paid model path.

## Setup

```bash
cd ~/Desktop/Resume_top
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional .env — free keys only, see .env.example
```

## Cost (stays $0)

Nothing you need bills you. Do **not** add a paid model key. Do **not** deploy Fly/Render.

The app picks a backend in this order: **Gemini → Cerebras → Groq → NVIDIA → Cloudflare → Ollama (local) → offline select-only**. After login, **Rewrite with** lets you pin one of those (or original bullets only) instead of Auto. Daily app caps: Gemini 120 calls, Cerebras 150, Groq 80, NVIDIA 80. Those are call counters so a free key cannot roll into a bill.

| Path | Cost | Quality for this app | How |
| --- | --- | --- | --- |
| **Ollama on this Mac** | $0, private, unlimited | Best long-term. 8B–70B locally. | Install [Ollama](https://ollama.com), then `ollama pull llama3.1` and `ollama pull nomic-embed-text`. Restart the API. `/health` should say `provider: ollama`. |
| **Groq free key** | $0, rate-limited | Fast rewrite (`qwen/qwen3.8-27b`, instruct mode). | [console.groq.com](https://console.groq.com) — no card. Put `GROQ_API_KEY=gsk_...` in `.env`. |
| **Gemini 3.8 Flash** | $0 on the free tier | Best writer on a key you already have. Pro is not used. | [aistudio.google.com](https://aistudio.google.com/apikey) — `GEMINI_API_KEY=...`. Leave billing off. |
| **Cerebras free key** | $0 trial | `gpt-oss-120b`, still the fast large backup. | [cloud.cerebras.ai](https://cloud.cerebras.ai) — `CEREBRAS_API_KEY=...`. Do not buy credits. |
| **NVIDIA Build trial** | $0, no card | `deepseek-ai/deepseek-v4.1-flash`, the free endpoint NVIDIA still serves. | [build.nvidia.com/settings](https://build.nvidia.com/settings) — `NVIDIA_API_KEY=nvapi-...`. |
| Offline (no LLM) | $0 | Select/reorder + local ATS. No rewritten wording. | Default if none of the above is running. |

Stack two free keys if you want failover later. One is enough.

**Not used (and we will not add):** LinkedIn/Naukri scrapers, paid OpenAI embeddings, paid hosts. Those burn money or accounts.

`GET /health` → `llm` tells you which backend is live.

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
python -m backend tailor --jd-file data/sample_jd.txt --role "AI Engineer" --company Acme --llm gemini
```

API:

```bash
python -m backend.main
# POST http://127.0.0.1:8000/v1/tailor
# POST http://127.0.0.1:8000/v1/tailor/stream   (SSE: run id, progress, then result)
# GET  http://127.0.0.1:8000/v1/runs/active     (the tailor still running for this user)
# GET  http://127.0.0.1:8000/v1/runs/{id}       (score, skim, gaps, library id when done)
# POST http://127.0.0.1:8000/v1/resume/upload   (multipart file — source of truth)
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

- **Upload your source resume** (PDF / DOCX / TXT). Later tailors only use that fact bank.
- **Paste a JD or search public boards**, then tailor. `/run` shows parse → select → rewrite with the match climbing toward 97–98. Leaving that page does not cancel the work. When it finishes, `/result` shows the skim, the gaps, the under-surfaced skills, and the downloads.
- **Needs a decision** — due on the 7-day cycle. Keep = ask again in 7 days. Delete = remove the file here. The header badge and a browser notification (if you allow it) are the reminders. There is no OS popup daemon. CLI: `python -m backend review`.
- **Download resume / cover letter** from the same page.

PDFs are ~50KB each. Twenty of them will not fill your RAM. They live in `library/` (disk), grouped by your account and company.

This app cannot delete files from LinkedIn. If you uploaded a PDF there, remove it in LinkedIn’s resume list too.

```bash
python -m backend review
python -m backend jobs -q "AI Engineer"

```

## Find jobs (public APIs, not scraping)

The UI at `/` and `python -m backend jobs -q "AI Engineer"` search **six free APIs**: Remotive, Remote OK, Arbeitnow, Jobicy, Himalayas, The Muse. After you upload a resume, the two most recent job titles appear as search chips.

**Google Jobs** is a new-tab link from search, not a scrape. Google does not offer a free “whole internet jobs” API (SerpAPI and similar are paid). On a Google Jobs panel, the extension’s Tailor button reads the posting that is already open.

This is **not** a LinkedIn / Naukri / Indeed crawler. Those sites block bots and ban accounts. Stay on the job page and click Tailor there, or paste the JD. The extension does not log into those sites.

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

Checked-in templates (you still have to create the app and set secrets yourself):

```bash
# Fly.io — after `fly launch` / volume create
fly secrets set SECRET_KEY=...
fly deploy

# Render — uses render.yaml; set the free provider keys in the dashboard
```

## Extension

The extension adds one **Tailor** button on the job you already have open. It reads that page and sends the text to the local API as the account you signed in with. It does not click Apply, and it does not call LinkedIn, Naukri, Indeed, or the other boards.

1. Start the API: `python -m backend.main`
2. Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → `extension/`
3. Open the extension and sign in with the same email as the app. The resume has to be uploaded in the app first.
4. Open a job on LinkedIn, Naukri, Indeed, Glassdoor, Foundit, Monster, Cutshort, Workday, Greenhouse, Lever, or a Google Jobs panel. Click **Tailor** on that page.

The panel on that page shows the climbing match, the skim, the gaps, and the PDF and cover-letter downloads. That click is the same kind of run as the app: the header in the app can say **Tailoring…** or **Result ready** for it.

On any other tab, the extension popup has **Tailor this tab**. If the description is not on the page, paste it in the app. Reload the extension in `chrome://extensions` after pulling these files.

## License

MIT. See [LICENSE](LICENSE).

from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
FACT_BANK_PATH = DATA_DIR / "fact_bank.json"
OUTPUT_DIR = ROOT / "output"
LIBRARY_DIR = Path(os.getenv("LIBRARY_DIR") or ROOT / "library")
LIBRARY_DB = Path(os.getenv("LIBRARY_DB") or DATA_DIR / "library.db")
TEMPLATES_DIR = ROOT / "templates"
FRONTEND_DIR = ROOT / "frontend"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
# Free backends. Leave empty and we auto-pick: Ollama → Groq → Gemini → Cerebras → NVIDIA.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Groq shut down llama-3.1-8b-instant for free/dev tiers on 2026-08-16.
# Qwen 3.8 instruct mode. GPT-OSS 20B stays available if GROQ_MODEL is set back.
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Pinned free Flash. gemini-3.1-pro is paid, so it is not a default.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
# NVIDIA Build trial host only (integrate.api.nvidia.com). No paid deploy URL.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-pro")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
# App-side caps, well below vendor free tiers. Paid OpenAI stays off unless
# LLM_ALLOW_PAID=1 is set on purpose.
# Call caps, not dollars. Groq stays at 80 because its free plan is 200k tokens/day.
# Gemini 120 and Cerebras 150 stay under those providers' free walls.
LLM_DAILY_CAP_GROQ = int(os.getenv("LLM_DAILY_CAP_GROQ", "80"))
LLM_DAILY_CAP_GEMINI = int(os.getenv("LLM_DAILY_CAP_GEMINI", "120"))
LLM_DAILY_CAP_CEREBRAS = int(os.getenv("LLM_DAILY_CAP_CEREBRAS", "150"))
LLM_DAILY_CAP_NVIDIA = int(os.getenv("LLM_DAILY_CAP_NVIDIA", "80"))
LLM_DAILY_CAP_CLOUDFLARE = int(os.getenv("LLM_DAILY_CAP_CLOUDFLARE", "40"))
LLM_ALLOW_PAID = os.getenv("LLM_ALLOW_PAID", "").strip().lower() in {"1", "true", "yes"}
# Worst-case API calls for one tailor (4 rewrite passes + cover letter).
LLM_CALLS_PER_TAILOR = int(os.getenv("LLM_CALLS_PER_TAILOR", "5"))
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
REVIEW_DAYS = int(os.getenv("REVIEW_DAYS", "7"))
CLI_USER_EMAIL = os.getenv("CLI_USER_EMAIL", "local@resume-tailor.local")

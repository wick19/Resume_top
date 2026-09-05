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
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
REVIEW_DAYS = int(os.getenv("REVIEW_DAYS", "7"))
CLI_USER_EMAIL = os.getenv("CLI_USER_EMAIL", "local@resume-tailor.local")

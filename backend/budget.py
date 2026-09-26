"""App-side free-tier kill switch.

Vendor free quotas can still roll into a paid plan if you keep calling after
429s or after they change limits. We stop first, on a UTC daily counter that
is well below published free caps, and never call OpenAI unless LLM_ALLOW_PAID=1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend import config
from backend.db import cursor, init_db

SIGNUP = {
    "groq": "https://console.groq.com/keys",
    "gemini": "https://aistudio.google.com/apikey",
    "cerebras": "https://cloud.cerebras.ai",
    "nvidia": "https://build.nvidia.com/settings",
    "cloudflare": "https://dash.cloudflare.com/?to=/:account/workers/models",
}

LABELS = {
    "groq": "Groq Qwen 3.8",
    "gemini": "Gemini 3.8 Flash",
    "cerebras": "Cerebras GPT-OSS 120B",
    "nvidia": "NVIDIA DeepSeek V4 Pro",
    "cloudflare": "Cloudflare Workers AI",
    "ollama": "Ollama (local)",
}


def _openai_cap() -> int:
    import os

    return int(os.getenv("LLM_DAILY_CAP_OPENAI", "20"))


def _cap(provider: str) -> int | None:
    if provider == "ollama":
        return None
    if provider == "openai":
        return 0 if not config.LLM_ALLOW_PAID else _openai_cap()
    mapping = {
        "groq": config.LLM_DAILY_CAP_GROQ,
        "gemini": config.LLM_DAILY_CAP_GEMINI,
        "cerebras": config.LLM_DAILY_CAP_CEREBRAS,
        "nvidia": config.LLM_DAILY_CAP_NVIDIA,
        "cloudflare": config.LLM_DAILY_CAP_CLOUDFLARE,
    }
    if provider not in mapping:
        return 0
    return mapping[provider]


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def reset_at_iso() -> str:
    now = datetime.now(timezone.utc)
    nxt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    if now >= nxt:
        nxt = nxt + timedelta(days=1)
    return nxt.isoformat().replace("+00:00", "Z")


def used_today(provider: str) -> int:
    init_db()
    with cursor() as conn:
        row = conn.execute(
            "SELECT calls FROM llm_usage WHERE day = ? AND provider = ?",
            (utc_day(), provider),
        ).fetchone()
    return int(row["calls"]) if row else 0


def remaining_calls(provider: str) -> int | None:
    cap = _cap(provider)
    if cap is None:
        return None
    return max(0, cap - used_today(provider))


def allow(provider: str, n: int = 1) -> bool:
    left = remaining_calls(provider)
    if left is None:
        return True
    return left >= n


def record(provider: str, n: int = 1) -> None:
    if _cap(provider) is None:
        return
    init_db()
    day = utc_day()
    with cursor() as conn:
        conn.execute(
            """
            INSERT INTO llm_usage (day, provider, calls)
            VALUES (?, ?, ?)
            ON CONFLICT(day, provider) DO UPDATE SET
                calls = llm_usage.calls + excluded.calls
            """,
            (day, provider, max(1, n)),
        )


def remaining_tailors(provider: str) -> int | None:
    left = remaining_calls(provider)
    if left is None:
        return None
    per = max(1, config.LLM_CALLS_PER_TAILOR)
    return left // per


def snapshot(provider: str | None) -> dict[str, Any]:
    """Numbers the UI shows: calls left, estimated tailors left, kill switch."""
    if not provider:
        return {
            "provider": None,
            "unlimited": False,
            "kill_switch": True,
            "cap": 0,
            "used": 0,
            "remaining_calls": 0,
            "remaining_tailors": 0,
            "calls_per_tailor": config.LLM_CALLS_PER_TAILOR,
            "resets_at": reset_at_iso(),
            "signup": SIGNUP,
        }
    cap = _cap(provider)
    used = 0 if cap is None else used_today(provider)
    left = remaining_calls(provider)
    tailors = remaining_tailors(provider)
    killed = cap is not None and (left or 0) < 1
    return {
        "provider": provider,
        "unlimited": cap is None,
        "kill_switch": killed,
        "cap": cap,
        "used": used,
        "remaining_calls": left,
        "remaining_tailors": tailors,
        "calls_per_tailor": config.LLM_CALLS_PER_TAILOR,
        "resets_at": reset_at_iso(),
        "signup": SIGNUP,
    }


def board(rows: list[tuple[str, str, bool]]) -> list[dict[str, Any]]:
    """One quota line per provider: configured or not, remaining tailors."""
    out: list[dict[str, Any]] = []
    for name, model, configured in rows:
        snap = snapshot(name)
        snap["label"] = LABELS.get(name, name)
        snap["model"] = model
        snap["configured"] = bool(configured)
        if not configured:
            snap["remaining_tailors"] = 0
            snap["remaining_calls"] = 0
            snap["kill_switch"] = False
        out.append(snap)
    return out

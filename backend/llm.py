"""Pick a $0 (or already-configured) OpenAI-compatible backend.

Order, unless LLM_PROVIDER is set:

  1. Ollama on localhost     — truly free, private, unlimited (optional)
  2. Groq Qwen 3.8 27B       — free tier, no card
  3. Gemini 3.8 Flash        — free AI Studio key
  4. Cerebras GPT-OSS 120B   — free trial
  5. NVIDIA DeepSeek V4 Pro  — free Build trial, no card
  6. OPENAI_API_KEY          — blocked unless LLM_ALLOW_PAID=1

Groq is called over HTTPS. Local Llama is only used if Ollama is running.

Embeddings never call a paid OpenAI embedding model. They use Ollama
`nomic-embed-text` when Ollama is up, otherwise the lexical fallback.
"""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from threading import local
from typing import Any

from backend import budget, config

_tls = local()


class BudgetExceeded(RuntimeError):
    """Raised when the app kill switch stops a cloud LLM call."""


def _providers() -> dict[str, dict[str, Any]]:
    host = (config.OLLAMA_HOST or "http://127.0.0.1:11434").rstrip("/")
    return {
        "ollama": {
            "base_url": f"{host}/v1",
            "api_key": "ollama",
            "model": config.OLLAMA_MODEL,
            "embed_model": "nomic-embed-text",
            "cost": "free-local",
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": config.GROQ_API_KEY,
            "model": config.GROQ_MODEL,
            "embed_model": None,
            "cost": "free-tier",
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key": config.GEMINI_API_KEY,
            "model": config.GEMINI_MODEL,
            "embed_model": None,
            "cost": "free-tier",
        },
        "cerebras": {
            "base_url": "https://api.cerebras.ai/v1",
            "api_key": config.CEREBRAS_API_KEY,
            "model": "gpt-oss-120b",
            "embed_model": None,
            "cost": "free-tier",
        },
        "nvidia": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": config.NVIDIA_API_KEY,
            "model": config.NVIDIA_MODEL,
            "embed_model": None,
            "cost": "free-tier",
        },
        "cloudflare": {
            "base_url": (
                f"https://api.cloudflare.com/client/v4/accounts/"
                f"{config.CLOUDFLARE_ACCOUNT_ID}/ai/v1"
            ),
            "api_key": (
                config.CLOUDFLARE_API_TOKEN
                if config.CLOUDFLARE_ACCOUNT_ID and config.CLOUDFLARE_API_TOKEN
                else ""
            ),
            "model": "@cf/meta/llama-3.1-8b-instruct",
            "embed_model": None,
            "cost": "free-tier",
        },
        "openai": {
            "base_url": config.OPENAI_BASE_URL,
            "api_key": config.OPENAI_API_KEY,
            "model": config.OPENAI_MODEL,
            "embed_model": None,
            "cost": "paid-if-openai",
        },
    }


def ollama_running() -> bool:
    try:
        import httpx

        host = (config.OLLAMA_HOST or "http://127.0.0.1:11434").rstrip("/")
        resp = httpx.get(f"{host}/api/tags", timeout=0.4)
        return resp.status_code == 200
    except Exception:
        return False


def _wanted() -> str:
    return (getattr(_tls, "name", "") or config.LLM_PROVIDER or "").strip().lower()


@contextmanager
def using_provider(name: str):
    """Pin this request to one backend (UI picker). Empty name = auto order."""
    prev = getattr(_tls, "name", "")
    _tls.name = (name or "").strip().lower()
    try:
        yield
    finally:
        _tls.name = prev


def resolve() -> dict[str, Any] | None:
    """Return the active provider dict, or None if rewrite stays offline."""
    catalog = _providers()
    forced = _wanted()
    if forced in {"auto", "select"}:
        forced = ""
    if forced:
        if forced == "openai" and not config.LLM_ALLOW_PAID:
            return None
        if forced == "ollama" and not ollama_running():
            return None
        spec = catalog.get(forced)
        if not spec:
            return None
        if forced != "ollama" and not spec.get("api_key"):
            return None
        return {"name": forced, **spec}

    if ollama_running():
        return {"name": "ollama", **catalog["ollama"]}
    for name in ("groq", "gemini", "cerebras", "nvidia", "cloudflare"):
        spec = catalog[name]
        if spec.get("api_key") and budget.allow(name):
            return {"name": name, **spec}
    if config.LLM_ALLOW_PAID and catalog["openai"].get("api_key"):
        return {"name": "openai", **catalog["openai"]}
    return None


resolve.cache_clear = lambda: None  # tests; override is per-request via contextvar


def assert_provider(name: str) -> None:
    """Raise ValueError if the UI/CLI picked a backend we cannot use."""
    chosen = (name or "").strip().lower()
    if chosen in {"", "auto", "select"}:
        return
    catalog = _providers()
    spec = catalog.get(chosen)
    if not spec:
        raise ValueError(f"Unknown rewrite model '{name}'.")
    if chosen == "openai" and not config.LLM_ALLOW_PAID:
        raise ValueError("Paid OpenAI is disabled.")
    if chosen == "ollama" and not ollama_running():
        raise ValueError("Ollama is not running on this machine.")
    if chosen != "ollama" and not spec.get("api_key"):
        raise ValueError(f"{chosen} is not configured in .env.")
    if chosen != "ollama" and not budget.allow(chosen):
        raise ValueError(
            f"{chosen} daily free cap is used. Pick another model, or wait until 00:00 UTC."
        )


def llm_available() -> bool:
    spec = resolve()
    if spec is None:
        return False
    return budget.allow(spec["name"])


def client_and_model() -> tuple[Any, str]:
    spec = resolve()
    if spec is None:
        raise RuntimeError("No free or configured LLM backend is available.")
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": spec["api_key"] or "local", "timeout": 90.0, "max_retries": 1}
    if spec.get("base_url"):
        kwargs["base_url"] = spec["base_url"]
    return OpenAI(**kwargs), spec["model"]


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    json_object: bool = True,
) -> str:
    """One counted cloud call. Local Ollama is not counted. Cap hit → BudgetExceeded."""
    spec = resolve()
    if spec is None:
        raise RuntimeError("No free or configured LLM backend is available.")
    name = spec["name"]
    if not budget.allow(name):
        raise BudgetExceeded(
            f"Free {name} cap for today is used. No paid calls will be made. "
            "Rewrites reset at 00:00 UTC."
        )
    client, model = client_and_model()
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    if json_object:
        kwargs["response_format"] = {"type": "json_object"}
    # Qwen 3.8 thinks by default and would burn Groq's free token cap.
    # GPT-OSS defaults to medium/high reasoning and can sit silent for minutes.
    if name == "groq" and "qwen" in model:
        kwargs["extra_body"] = {"reasoning_effort": "none"}
    elif name in {"groq", "cerebras"} and "gpt-oss" in model:
        kwargs["extra_body"] = {"reasoning_effort": "low"}
    def _call(k: dict[str, Any]):
        return client.chat.completions.create(**k)

    try:
        response = _call(kwargs)
    except Exception as exc:
        text = str(exc)
        salvaged = _salvage_failed_generation(exc)
        if salvaged is not None:
            budget.record(name)
            return salvaged
        if json_object and (
            "response_format" in text.lower() or "json_validate_failed" in text.lower()
        ):
            kwargs.pop("response_format", None)
            try:
                response = _call(kwargs)
            except Exception as exc2:
                salvaged = _salvage_failed_generation(exc2)
                if salvaged is not None:
                    budget.record(name)
                    return salvaged
                raise RuntimeError(_friendly_chat_error(name, model, exc2)) from exc2
        elif "503" in text or "overloaded" in text.lower() or "high demand" in text.lower():
            # Free-tier models occasionally bounce a 503 for a second or two.
            # One quick retry clears most of these without bothering the user.
            time.sleep(2.0)
            try:
                response = _call(kwargs)
            except Exception as exc2:
                raise RuntimeError(_friendly_chat_error(name, model, exc2)) from exc2
        elif "429" in text or "rate limit" in text.lower():
            time.sleep(_retry_after_seconds(text))
            try:
                response = _call(kwargs)
            except Exception as exc2:
                raise RuntimeError(_friendly_chat_error(name, model, exc2)) from exc2
        else:
            raise RuntimeError(_friendly_chat_error(name, model, exc)) from exc
    budget.record(name)
    return response.choices[0].message.content or "{}"


def _friendly_chat_error(provider: str, model: str, exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if (
        "model_not_found" in low
        or "does not exist" in low
        or "not_found" in low
        or "no longer available" in low
        or " 404" in low
        or low.startswith("404")
    ):
        alt = "Cerebras or Groq" if provider == "gemini" else "Gemini or Cerebras"
        return (
            f"{provider} no longer serves `{model}`. "
            f"Pick {alt} in Rewrite with, or set "
            f"{'GEMINI_MODEL' if provider == 'gemini' else 'GROQ_MODEL' if provider == 'groq' else provider.upper() + '_MODEL'} in .env."
        )
    if "timeout" in low or "timed out" in low:
        return (
            f"{provider} took too long ({model}). "
            "Try a different model in Rewrite with, or wait and tailor again."
        )
    if "503" in low or "overloaded" in low or "high demand" in low:
        return (
            f"{provider} is overloaded right now (free tier). "
            "Try again in a few seconds, or pick another model in Rewrite with."
        )
    if "429" in low or "rate limit" in low:
        return (
            f"{provider} per-minute free-tier limit hit — this is Groq's speed cap, "
            "not today's rewrite budget. Wait about a minute, or pick another model."
        )
    if "json_validate_failed" in low or "failed to generate json" in low:
        return (
            f"{provider} returned broken JSON for this rewrite. "
            "Try again, or pick another model in Rewrite with."
        )
    return text


def _retry_after_seconds(text: str, default: float = 8.0) -> float:
    """Groq 429s often say 'Please try again in 6.52s'. Cap the wait."""
    match = re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*s", (text or "").lower())
    if match:
        return min(20.0, max(2.0, round(float(match.group(1)) + 0.4, 2)))
    return default


_ROLE_GAP_RE = re.compile(
    r'\},\s*"(role\.[^"]+|project\.[^"]+)"\s*,\s*"bullets"\s*:'
)


def _slice_balanced_object(text: str, start: int) -> str | None:
    """Return the `{...}` starting at `start`, respecting JSON strings."""
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_failed_generation(exc: Exception) -> str | None:
    """Pull Groq's `failed_generation` blob out of an OpenAI-compat 400."""
    body = getattr(exc, "body", None)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = None
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict) and err.get("failed_generation"):
            return str(err["failed_generation"])
    text = str(exc)
    idx = text.find("failed_generation")
    if idx < 0:
        return None
    brace = text.find("{", idx)
    return _slice_balanced_object(text, brace)


def repair_json_text(text: str) -> str:
    """Fix the common Groq JSON-mode mistakes we actually see."""
    out = (text or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```(?:json)?\s*", "", out)
        out = re.sub(r"\s*```$", "", out).strip()
    # `},"role.1","bullets":` → `},{"id":"role.1","bullets":`
    out = _ROLE_GAP_RE.sub(r'}, {"id": "\1", "bullets":', out)
    out = re.sub(r",\s*([}\]])", r"\1", out)
    return out


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse model output into a dict, repairing Groq JSON-mode glitches."""
    raw = repair_json_text(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sliced = _slice_balanced_object(raw, raw.find("{"))
        if not sliced:
            raise
        data = json.loads(repair_json_text(sliced))
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object.")
    return data


def _salvage_failed_generation(exc: Exception) -> str | None:
    raw = extract_failed_generation(exc)
    if not raw:
        return None
    try:
        return json.dumps(parse_json_object(raw))
    except (json.JSONDecodeError, ValueError):
        return None


def embed_spec() -> dict[str, Any] | None:
    """Only Ollama embeddings are used — they are local and free."""
    spec = resolve()
    if spec and spec["name"] == "ollama" and spec.get("embed_model"):
        return spec
    if ollama_running():
        return {"name": "ollama", **_providers()["ollama"]}
    return None


def status() -> dict[str, Any]:
    resolve.cache_clear()
    spec = resolve()
    catalog = _providers()
    quota_specs = [
        ("groq", catalog["groq"]["model"], bool(catalog["groq"].get("api_key"))),
        ("gemini", catalog["gemini"]["model"], bool(catalog["gemini"].get("api_key"))),
        ("cerebras", catalog["cerebras"]["model"], bool(catalog["cerebras"].get("api_key"))),
        ("nvidia", catalog["nvidia"]["model"], bool(catalog["nvidia"].get("api_key"))),
    ]
    if catalog["cloudflare"].get("api_key"):
        quota_specs.append(
            ("cloudflare", catalog["cloudflare"]["model"], True)
        )
    quota_rows = budget.board(quota_specs)
    quota = budget.snapshot(spec["name"] if spec else None)
    if spec:
        quota["active"] = True
    if not spec:
        return {
            "rewrite": False,
            "provider": None,
            "cost": "free-offline",
            "note": (
                "No LLM. Select/reorder only. Add a free Groq key "
                f"({budget.SIGNUP['groq']}), or Gemini / Cerebras."
            ),
            "quota": quota,
            "quotas": quota_rows,
            "choices": choices(),
            "signup": budget.SIGNUP,
        }
    rewrite_on = budget.allow(spec["name"])
    parts = []
    for row in quota_rows:
        if not row["configured"]:
            continue
        n = row["remaining_tailors"]
        tag = "using now" if spec["name"] == row["provider"] else "standby"
        parts.append(f"{row['label']}: {n} rewrite{'s' if n != 1 else ''} left ({tag})")
    note = " → ".join(parts) if parts else (
        f"{spec['name']} is local — no daily cap."
        if spec["name"] == "ollama"
        else ""
    )
    return {
        "rewrite": rewrite_on,
        "provider": spec["name"],
        "model": spec["model"],
        "cost": spec["cost"],
        "embeddings": spec["name"] == "ollama",
        "quota": quota,
        "quotas": quota_rows,
        "choices": choices(),
        "signup": budget.SIGNUP,
        "note": note,
    }


def choices() -> list[dict[str, Any]]:
    """Backends the UI can put in the rewrite picker."""
    catalog = _providers()
    rows: list[dict[str, Any]] = [
        {
            "id": "auto",
            "label": "Auto (first with remaining quota)",
            "model": "",
            "configured": True,
        }
    ]
    for name in ("groq", "gemini", "cerebras", "nvidia"):
        spec = catalog[name]
        configured = bool(spec.get("api_key"))
        rows.append(
            {
                "id": name,
                "label": budget.LABELS.get(name, name),
                "model": spec["model"],
                "configured": configured,
                "remaining_tailors": budget.remaining_tailors(name) if configured else 0,
            }
        )
    if catalog["cloudflare"].get("api_key"):
        spec = catalog["cloudflare"]
        rows.append(
            {
                "id": "cloudflare",
                "label": budget.LABELS["cloudflare"],
                "model": spec["model"],
                "configured": True,
                "remaining_tailors": budget.remaining_tailors("cloudflare"),
            }
        )
    if ollama_running():
        rows.append(
            {
                "id": "ollama",
                "label": "Ollama (local, unlimited)",
                "model": catalog["ollama"]["model"],
                "configured": True,
            }
        )
    rows.append(
        {
            "id": "select",
            "label": "Original bullets only (no rewrite)",
            "model": "",
            "configured": True,
        }
    )
    return rows

"""Pick a $0 (or already-configured) OpenAI-compatible backend.

Order, unless LLM_PROVIDER is set. Best free writer first. A few minutes
is fine. Ollama is last, and only when no cloud key has quota left.

  1. Gemini 3.8 Flash           — free AI Studio key
  2. Cerebras GPT-OSS 120B      — free trial
  3. Groq Qwen 3.8 27B          — free tier, no card
  4. NVIDIA DeepSeek V4.1 Flash — free Build trial, no card
  5. Ollama on localhost        — optional, if nothing above is available

There is no paid model path. Groq, Gemini, Cerebras, and NVIDIA are called
with the OpenAI client library only because those hosts speak that protocol.

Embeddings use local Ollama `nomic-embed-text` when Ollama is up, otherwise
the lexical fallback.
"""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from threading import local
from typing import Any

from backend import config
from backend.llm import budget

_tls = local()


class BudgetExceeded(RuntimeError):
    """Raised when the app kill switch stops a cloud LLM call."""


class ProviderFailed(RuntimeError):
    """The chosen model timed out, was overloaded, or hit a per-minute limit."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(message)


# One rewrite call may think. Three minutes is the wait the product allows.
CALL_TIMEOUT = 180.0


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


def is_pinned() -> bool:
    """True when this request asked for one named model, not Auto."""
    name = _wanted()
    return bool(name) and name not in {"auto", "select"}


def _skipped() -> set[str]:
    skipped = getattr(_tls, "skipped", None)
    if skipped is None:
        skipped = set()
        _tls.skipped = skipped
    return skipped


def skip_provider(name: str) -> None:
    """Drop a model for the rest of this tailor. Auto then uses the next one."""
    if name:
        _skipped().add(name)


def clear_skipped() -> None:
    _tls.skipped = set()


@contextmanager
def using_provider(name: str):
    """Pin this request to one backend (UI picker). Empty name = auto order."""
    prev = getattr(_tls, "name", "")
    prev_skipped = set(_skipped())
    _tls.name = (name or "").strip().lower()
    _tls.skipped = set()
    try:
        yield
    finally:
        _tls.name = prev
        _tls.skipped = prev_skipped


def resolve() -> dict[str, Any] | None:
    """Return the active provider dict, or None if rewrite stays offline."""
    catalog = _providers()
    forced = _wanted()
    if forced in {"auto", "select"}:
        forced = ""
    if forced:
        if forced == "ollama" and not ollama_running():
            return None
        spec = catalog.get(forced)
        if not spec:
            return None
        if forced != "ollama" and not spec.get("api_key"):
            return None
        return {"name": forced, **spec}

    skipped = _skipped()
    for name in ("gemini", "cerebras", "groq", "nvidia", "cloudflare"):
        if name in skipped:
            continue
        spec = catalog[name]
        if spec.get("api_key") and budget.allow(name):
            return {"name": name, **spec}
    if ollama_running():
        return {"name": "ollama", **catalog["ollama"]}
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

    kwargs: dict[str, Any] = {
        "api_key": spec["api_key"] or "local",
        "timeout": CALL_TIMEOUT,
        "max_retries": 0,
    }
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
    effort = _reasoning_effort(name, model)
    if effort:
        kwargs["extra_body"] = {"reasoning_effort": effort}
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
                raise _failed(name, model, exc2) from exc2
        elif _failure_kind(text) == "overloaded":
            time.sleep(2.0)
            try:
                response = _call(kwargs)
            except Exception as exc2:
                raise _failed(name, model, exc2) from exc2
        elif _failure_kind(text) == "rate":
            time.sleep(_retry_after_seconds(text))
            try:
                response = _call(kwargs)
            except Exception as exc2:
                raise _failed(name, model, exc2) from exc2
        else:
            raise _failed(name, model, exc) from exc
    budget.record(name)
    return response.choices[0].message.content or "{}"


def _reasoning_effort(provider: str, model: str) -> str | None:
    """Gemini stays at medium. Groq and Cerebras use low so a spare still writes."""
    if provider == "gemini":
        return "medium"
    if provider == "groq" and "qwen" in model:
        return "low"
    if provider in {"groq", "cerebras"} and "gpt-oss" in model:
        return "low"
    return None


def _failure_kind(text: str) -> str | None:
    low = (text or "").lower()
    if "timeout" in low or "timed out" in low:
        return "timeout"
    if "503" in low or "overloaded" in low or "high demand" in low:
        return "overloaded"
    if "429" in low or "rate limit" in low:
        return "rate"
    return None


def _failed(provider: str, model: str, exc: Exception) -> Exception:
    kind = _failure_kind(str(exc))
    if kind == "timeout":
        return ProviderFailed(provider, f"{provider} did not finish this rewrite ({model}).")
    if kind == "overloaded":
        return ProviderFailed(provider, f"{provider} is overloaded and did not finish this rewrite.")
    if kind == "rate":
        return ProviderFailed(
            provider,
            f"{provider} hit its per-minute limit and did not finish this rewrite.",
        )
    return RuntimeError(_friendly_chat_error(provider, model, exc))


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
        ("gemini", catalog["gemini"]["model"], bool(catalog["gemini"].get("api_key"))),
        ("cerebras", catalog["cerebras"]["model"], bool(catalog["cerebras"].get("api_key"))),
        ("groq", catalog["groq"]["model"], bool(catalog["groq"].get("api_key"))),
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
                "No LLM. Select/reorder only. Add a free Gemini key "
                f"({budget.SIGNUP['gemini']}), or Cerebras / Groq."
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
            "label": "Auto (best free model with quota left)",
            "model": "",
            "configured": True,
        }
    ]
    for name in ("gemini", "cerebras", "groq", "nvidia"):
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

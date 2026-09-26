"""Semantic similarity with a graceful fallback.

If an OpenAI-compatible key is configured we use a real embedding model.
Otherwise we fall back to a deterministic lexical cosine over token bags, so
the pipeline still runs (and tests stay hermetic) without a network call.

Callers should treat the result as a 0..1 similarity and use it only as a
*boost* on top of the deterministic lexical overlap in `scoring.py` — never as
the sole signal.
"""

from __future__ import annotations

import math
import re
from typing import Any

from backend.llm import embed_spec

EMBED_MODEL = "nomic-embed-text"
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./_-]{1,}", re.I)


def embeddings_available() -> bool:
    return embed_spec() is not None


def _bag(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for tok in _TOKEN_RE.findall((text or "").lower()):
        if len(tok) < 2:
            continue
        counts[tok] = counts.get(tok, 0.0) + 1.0
    return counts


def _cosine_bags(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _cosine_vec(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed(texts: list[str]) -> list[list[float]] | None:
    spec = embed_spec()
    if not spec:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=spec["api_key"] or "ollama",
            base_url=spec["base_url"],
            timeout=8.0,
            max_retries=0,
        )
        resp = client.embeddings.create(
            model=spec.get("embed_model") or EMBED_MODEL, input=texts
        )
        return [item.embedding for item in resp.data]
    except Exception:
        # Any failure (network, quota, model name) → lexical fallback.
        return None


def similarity(query: str, candidates: list[str]) -> list[float]:
    """Return a similarity in [0, 1] for the query against each candidate."""
    if not candidates:
        return []
    vectors = _embed([query, *candidates])
    if vectors is not None and len(vectors) == len(candidates) + 1:
        q = vectors[0]
        return [max(0.0, _cosine_vec(q, v)) for v in vectors[1:]]
    # Lexical fallback.
    qbag = _bag(query)
    return [_cosine_bags(qbag, _bag(c)) for c in candidates]


def backend_name() -> str:
    return "embeddings" if embeddings_available() else "lexical"

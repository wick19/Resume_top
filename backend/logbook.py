from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import OUTPUT_DIR

LOG_PATH = OUTPUT_DIR / "applications.jsonl"


def append_application(entry: dict[str, Any], path: Path | None = None) -> Path:
    dest = path or LOG_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    with dest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return dest


def read_applications(limit: int = 50, path: Path | None = None) -> list[dict[str, Any]]:
    dest = path or LOG_PATH
    if not dest.exists():
        return []
    lines = dest.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))

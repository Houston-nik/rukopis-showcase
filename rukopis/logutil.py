"""Журнал шагов. Текст конспекта сюда не пишется."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REDACTED_KEYS = {
    "text",
    "body",
    "content",
    "conspect",
    "note",
    "material",
    "prompt",
    "sentence",
    "line",
    "paragraph",
}

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "logs" / "rukopis.log"


def log_step(step: str, log_path: Path | None = None, **fields: object) -> None:
    path = log_path or DEFAULT_LOG
    clean: dict[str, object] = {}
    for key, value in fields.items():
        if key.lower() in REDACTED_KEYS:
            continue
        if isinstance(value, str):
            value = value.replace("\n", " ")[:180]
        clean[key] = value
    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": str(step)[:80],
        **clean,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

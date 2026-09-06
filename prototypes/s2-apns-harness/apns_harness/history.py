"""Append-only send history so S4 can correlate what was sent vs. what arrived.

One JSON object per line in `logs/send-history.jsonl` (gitignored — it contains
device tokens and is captured data, not code). Each record is self-contained:
timestamp, push type, environment, headers actually sent, a redacted device
token, the payload, and the APNs response (status, apns-id, reason).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import paths

LOG_DIR = paths.logs_dir()
HISTORY_PATH = LOG_DIR / "send-history.jsonl"


def redact_token(token: str) -> str:
    if len(token) <= 12:
        return "…"
    return f"{token[:6]}…{token[-4:]} (len {len(token)})"


def record(entry: dict, *, path: Path | None = None) -> Path:
    path = path or HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"logged_at": time.time(), "logged_at_iso": _iso(), **entry}
    with path.open("a") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    return path


def _iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def tail(n: int = 10, *, path: Path | None = None) -> list[dict]:
    path = path or HISTORY_PATH
    if not path.is_file():
        return []
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines[-n:]]

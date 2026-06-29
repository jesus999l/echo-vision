#!/usr/bin/env python3
"""
Echo Observer — The Memory Spine
Tails /tmp/echo_events.jsonl and decides what to remember.

Responsibilities:
  1. Read new events from the bus (tail, no re-reads)
  2. Filter noise (high-frequency cursor moves, etc.)
  3. Persist meaningful events to cognition/memory/events.jsonl
  4. Update /tmp/echo_bubble.txt with narration when relevant

Does NOT:
  - Call any AI model
  - Touch memory.db (that is the old stack)
  - Write outside /tmp/ and cognition/memory/
  - Slow down the tool_router

Run: ~/vision_env/bin/python3 echo_observer.py
"""

import json
import os
import tempfile
import time
from pathlib import Path

BUS_FILE      = Path("/tmp/echo_events.jsonl")
MEMORY_FILE   = Path(__file__).parent / "memory" / "events.jsonl"
BUBBLE_FILE   = Path("/tmp/echo_bubble.txt")
POLL_INTERVAL = 0.2   # seconds

# ── Importance filter ──────────────────────────────────────────────────────────
# These event types are too noisy to persist every occurrence.
# Still narrated, but only saved every N seconds per type.
_RATE_LIMITS = {
    "cursor_moved": 5.0,     # save at most once per 5s
    "browser_seen": 2.0,     # save at most once per 2s per URL
}
_last_saved: dict = {}


def _should_persist(event: dict) -> bool:
    etype = event.get("type", "")
    limit = _RATE_LIMITS.get(etype)
    if limit is None:
        return True  # all other types: always persist

    key = f"{etype}:{event.get('url', event.get('tool', ''))}"
    now = time.monotonic()
    last = _last_saved.get(key, 0.0)
    if now - last >= limit:
        _last_saved[key] = now
        return True
    return False


def _persist(event: dict) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MEMORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _atomic_write(path: Path, data: str):
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, delete=False, suffix=".tmp"
    ) as f:
        f.write(data)
        tmp = f.name
    os.replace(tmp, path)

def _narrate(event: dict) -> None:
    summary = event.get("summary", "").strip()
    if summary:
        try:
            _atomic_write(BUBBLE_FILE, summary)
        except OSError:
            pass


def _process(event: dict) -> None:
    _narrate(event)
    if _should_persist(event):
        _persist(event)


def run() -> None:
    print("[observer] Echo Observer online — tailing event bus.")

    # Seek to end of existing file so we don't replay old events on restart
    offset = 0
    if BUS_FILE.exists():
        offset = BUS_FILE.stat().st_size

    while True:
        try:
            if BUS_FILE.exists():
                current_size = BUS_FILE.stat().st_size
                if current_size > offset:
                    with BUS_FILE.open("r", encoding="utf-8") as f:
                        f.seek(offset)
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    event = json.loads(line)
                                    _process(event)
                                except json.JSONDecodeError:
                                    pass
                    offset = current_size

                elif current_size < offset:
                    # File was truncated/rotated
                    offset = 0

        except OSError:
            pass

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()

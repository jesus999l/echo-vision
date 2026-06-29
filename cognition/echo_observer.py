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


_last_signatures = []

def _is_duplicate(event: dict) -> bool:
    # Exclude timestamp for duplicate comparison
    event_copy = {k: v for k, v in event.items() if k != "timestamp"}
    sig = json.dumps(event_copy, sort_keys=True)
    if sig in _last_signatures:
        return True
    _last_signatures.append(sig)
    if len(_last_signatures) > 20:
        _last_signatures.pop(0)
    return False


def _persist(event: dict) -> None:
    try:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with MEMORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
    except OSError:
        pass  # Never crash the observer daemon over write failure


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
    if _is_duplicate(event):
        return
    _narrate(event)
    if _should_persist(event):
        _persist(event)


def run() -> None:
    print("[observer] Echo Observer online — tailing event bus.")

    # Seek to end of existing file so we don't replay old events on restart
    offset = 0
    if BUS_FILE.exists():
        try:
            offset = BUS_FILE.stat().st_size
        except OSError:
            pass

    while True:
        try:
            if BUS_FILE.exists():
                current_size = BUS_FILE.stat().st_size
                if current_size > offset:
                    with BUS_FILE.open("r", encoding="utf-8") as f:
                        f.seek(offset)
                        while True:
                            line = f.readline()
                            if not line:
                                break
                            if not line.endswith("\n"):
                                # Partial line — stop and wait for writer to complete
                                break

                            offset += len(line.encode("utf-8"))
                            line_str = line.strip()
                            if line_str:
                                try:
                                    event = json.loads(line_str)
                                    _process(event)
                                except json.JSONDecodeError:
                                    pass

                elif current_size < offset:
                    # File was truncated/rotated
                    offset = 0

        except OSError:
            pass

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()

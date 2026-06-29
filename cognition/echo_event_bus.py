#!/usr/bin/env python3
"""
Echo Event Bus
Writes events to /tmp/echo_events.jsonl (tmpfs — RAM-only, no SSD).
echo_observer.py tails this file and decides what to persist.

WHY NOT in-process listener list:
  tool_router, observer, browser_bridge are separate processes.
  A shared file is the correct IPC primitive for this pattern.
  It matches the existing /tmp/echo_pos.json, /tmp/echo_bubble.txt style.

SOURCES that can emit:
  - tool_router.py (tool executions, permission blocks)
  - echo_browser_bridge.py (page seen, tab changed)
  - voice pipeline (commands heard)
  - DriftWM (zone changed, window focused) — future
"""

import json
import os
import tempfile
import time
from pathlib import Path

BUS_FILE = Path("/tmp/echo_events.jsonl")


def emit(event: dict) -> None:
    """
    Append one event to the bus file atomically.
    Caller should include: type, source, and optionally summary.
    timestamp is added automatically.
    """
    event = {
        "timestamp": time.time(),
        **event,
    }

    line = json.dumps(event, ensure_ascii=False) + "\n"

    # Atomic append via temp file in same dir (tmpfs)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir="/tmp",
            delete=False,
            suffix=".evt",
            encoding="utf-8",
        ) as f:
            f.write(line)
            tmp_path = f.name

        # Open bus in append mode and write atomically
        with open(BUS_FILE, "a", encoding="utf-8") as bus:
            with open(tmp_path, "r", encoding="utf-8") as src:
                bus.write(src.read())

    except OSError:
        pass  # Never crash the caller over observation
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


async def emit_async(event: dict) -> None:
    """Async wrapper for use in tool_router.py action_worker."""
    emit(event)


if __name__ == "__main__":
    emit({
        "type":    "bus_test",
        "source":  "echo_event_bus",
        "summary": "Event bus online.",
    })
    print(f"Wrote test event to {BUS_FILE}")
    print(f"Content: {BUS_FILE.read_text().strip()}")

#!/usr/bin/env python3
"""
echo_heartbeat.py — shared ping/pong listener for Echo subsystems.

Import this in any live Echo module to make it discoverable.
Uses the existing event bus (/tmp/echo_events.jsonl) — no new IPC paths.

Usage in any subsystem (e.g. wake_word.py, tool_router.py):

    from cognition.echo_heartbeat import start_heartbeat
    start_heartbeat("wake_word")   # call once, near the top of the file

That's it. The listener runs in a background thread, watches for "ping"
events on the bus, and writes a "pong" event back with this subsystem's
name and a timestamp. Zero impact on the subsystem's own logic.
"""

import json
import threading
import time
from pathlib import Path

BUS_FILE = Path("/tmp/echo_events.jsonl")
POLL_INTERVAL = 0.5  # seconds


def _emit_pong(name: str, ping_id: str):
    """Write a pong event to the bus, tagged with this subsystem's name."""
    event = {
        "type":     "pong",
        "source":   name,
        "ping_id":  ping_id,
        "timestamp": time.time(),
    }
    try:
        with open(BUS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
    except OSError:
        pass  # never crash the host subsystem over a missed pong


def _listen_loop(name: str, stop_event: threading.Event):
    """
    Tail the event bus from the moment this starts (not from offset 0 —
    we don't want to replay old pings). Respond to any 'ping' event seen
    after this point with a 'pong' tagged as `name`.
    """
    # seek to end of file on start — only react to NEW pings
    offset = 0
    if BUS_FILE.exists():
        offset = BUS_FILE.stat().st_size

    seen_ping_ids = set()

    while not stop_event.is_set():
        try:
            if not BUS_FILE.exists():
                time.sleep(POLL_INTERVAL)
                continue

            with open(BUS_FILE, "r", encoding="utf-8") as f:
                f.seek(offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if event.get("type") == "ping":
                        ping_id = event.get("ping_id", "")
                        if ping_id and ping_id not in seen_ping_ids:
                            seen_ping_ids.add(ping_id)
                            _emit_pong(name, ping_id)

                offset = f.tell()
        except OSError:
            pass

        time.sleep(POLL_INTERVAL)


def start_heartbeat(name: str) -> threading.Event:
    """
    Start a background thread that makes this subsystem respond to pings.
    Call once per subsystem, near the top of the file, after imports.

    Returns a threading.Event — call .set() on it if you ever need to
    stop the heartbeat (rarely needed; daemon thread dies with the process).
    """
    stop_event = threading.Event()
    t = threading.Thread(
        target=_listen_loop,
        args=(name, stop_event),
        daemon=True,
        name=f"echo_heartbeat_{name}",
    )
    t.start()
    return stop_event

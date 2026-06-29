#!/usr/bin/env python3
"""
Echo Shadow Cursor Daemon
Polls /tmp/echo_live_ui.json and pushes cursor targets into /tmp/echo_pos.json.
DriftWM reads echo_pos.json for the sprite orbit position.

Run: ~/vision_env/bin/python3 echo_shadow_cursor.py
"""

import json
import time
from pathlib import Path

LIVE_UI  = Path("/tmp/echo_live_ui.json")
ECHO_POS = Path("/tmp/echo_pos.json")
POLL     = 0.1   # seconds

_last = None

def run():
    global _last
    print("[shadow_cursor] online — polling /tmp/echo_live_ui.json")

    while True:
        try:
            if LIVE_UI.exists():
                raw = LIVE_UI.read_text().strip()
                if raw:
                    payload = json.loads(raw)
                    if payload != _last and payload.get("type") == "cursor_target":
                        _last = payload
                        x, y = payload.get("x"), payload.get("y")
                        if x is not None and y is not None:
                            ECHO_POS.write_text(json.dumps({
                                "x": x, "y": y, "source": "gemini_live"
                            }))
                            print(f"[shadow_cursor] → ({x}, {y})")
        except (json.JSONDecodeError, OSError):
            pass

        time.sleep(POLL)

if __name__ == "__main__":
    run()

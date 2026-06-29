#!/usr/bin/env python3
"""
DriftWM Bridge — Compositor IPC stub.
Flesh out once DriftWM has a socket or inotify-watched command file.
Currently: tool_router writes /tmp/echo_focus_target.json.
DriftWM polls that file (same pattern as zones.json hot-reload).
"""

import json
from pathlib import Path

def focus_window(app_id: str) -> dict:
    Path("/tmp/echo_focus_target.json").write_text(
        json.dumps({"window": app_id, "source": "driftwm_bridge"})
    )
    return {"ok": True, "window": app_id}

def send_zone_command(cmd: str, zone_name: str, **kwargs) -> dict:
    payload = {"cmd": cmd, "zone": zone_name, **kwargs}
    Path("/tmp/echo_zone_cmd.json").write_text(json.dumps(payload))
    return {"ok": True, "payload": payload}

if __name__ == "__main__":
    print("[driftwm_bridge] stub — no action taken")

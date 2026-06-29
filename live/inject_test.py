#!/usr/bin/env python3
"""
Local test injector — sends fake Gemini tool calls via Unix socket.
live_socket.py must be running first.

Usage: ~/vision_env/bin/python3 inject_test.py
"""

import json
import socket
import time

SOCKET_PATH = "/tmp/echo_live.sock"

def send(tool: str, args: dict):
    payload = json.dumps({"tool": tool, "args": args}).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(SOCKET_PATH)
        s.sendall(payload)
        resp = s.recv(4096)
    result = json.loads(resp.decode())
    mark = "✓" if result.get("ok") else "✗"
    print(f"  {mark} {tool}({args}) → {result}")
    time.sleep(0.3)

if __name__ == "__main__":
    print("=== inject_test: firing fake Gemini tool calls ===")
    print()

    # 1. Speech bubble
    send("show_notification", {"message": "Gemini Live bridge test successful."})

    # 2. Shadow cursor movement
    send("move_shadow_cursor", {"x": 400, "y": 300})
    time.sleep(0.5)
    send("move_shadow_cursor", {"x": 800, "y": 400})
    time.sleep(0.5)
    send("move_shadow_cursor", {"x": 960, "y": 540})

    # 3. Zone navigation
    send("navigate_zone", {"zone": "work"})

    # 4. Blocked calls — should return ok: False
    send("run_shell",    {"cmd": "id"})
    send("close_window", {"window": "firefox"})

    print()
    print("Check:")
    print("  cat /tmp/echo_bubble.txt")
    print("  cat /tmp/echo_pos.json")
    print("  cat /tmp/echo_nav.json")

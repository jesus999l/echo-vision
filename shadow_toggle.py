#!/usr/bin/env python3
"""Toggle shadow cursor modes: off → follow → active-only → off"""
import socket, json, os

STATE_FILE = "/tmp/echo_shadow_mode"
MODES = ["off", "follow", "active"]

def get_mode():
    try:
        return open(STATE_FILE).read().strip()
    except:
        return "off"

def set_mode(mode):
    open(STATE_FILE, 'w').write(mode)

def send(cmd):
    try:
        s = socket.socket()
        s.connect(("127.0.0.1", 59998))
        s.sendall(json.dumps(cmd).encode())
        s.close()
    except:
        pass

current = get_mode()
idx = MODES.index(current) if current in MODES else 0
next_mode = MODES[(idx + 1) % len(MODES)]
set_mode(next_mode)

if next_mode == "off":
    send({"action": "follow", "enabled": False})
    send({"action": "hide"})
    import subprocess
    subprocess.Popen(["notify-send", "Echo Shadow", "● OFF", "-t", "1500"])
elif next_mode == "follow":
    send({"action": "follow", "enabled": True})
    import subprocess
    subprocess.Popen(["notify-send", "Echo Shadow", "◈ FOLLOW MODE", "-t", "1500"])
elif next_mode == "active":
    send({"action": "follow", "enabled": False})
    send({"action": "hide"})
    import subprocess
    subprocess.Popen(["notify-send", "Echo Shadow", "◎ ACTIVE ONLY", "-t", "1500"])

print(f"shadow mode: {current} → {next_mode}")

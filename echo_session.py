#!/usr/bin/env python3
"""
echo_session.py — Echo speech bubble + voice
Commands:
  save    — snapshot current windows to ~/.echo/session.json
  speak TEXT — send text to Echo bubble + TTS
  daemon  — watch driftwm process
"""
import json
import os
import sys
import subprocess
import time
import threading

SESSION_FILE = os.path.expanduser("~/.echo/session.json")
STATE_FILE   = f"{os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000')}/driftwm/state"
BUBBLE_FILE  = "/tmp/echo_bubble.txt"
VA           = os.path.expanduser("~/vision_assistant")
VENV         = os.path.expanduser("~/vision_env/bin/python3")


def read_state():
    try:
        content = open(STATE_FILE).read()
        for line in content.splitlines():
            if line.startswith("windows="):
                return json.loads(line[8:])
    except Exception as e:
        print(f"[session] state read error: {e}")
    return []

def save():
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    windows = read_state()
    if not windows:
        print("[session] no windows to save")
        return
    data = {"saved_at": time.time(), "windows": windows}
    json.dump(data, open(SESSION_FILE, 'w'), indent=2)
    print(f"[session] saved {len(windows)} windows to {SESSION_FILE}")
    for w in windows:
        print(f"  {w['app_id']}: {w['title'][:60]}")


def echo_speak(text: str):
    """
    Write bubble text and speak via TTS.
    Sequence (order matters):
      1. Kill any pending bubble-clear timers from previous speak
      2. Write new text to bubble
      3. Speak via Piper+sox
      4. Arm a new auto-clear timer tied to this exact text
    """
    # 1. Kill stale auto-clear timers before doing anything else
    try:
        subprocess.run(
            ["pkill", "-f", "sleep 15 && "],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

    # 2. Write bubble
    try:
        open(BUBBLE_FILE, 'w').write(text)
    except Exception:
        pass

    print(f"[Echo] {text}")

    # 3. Speak — non-blocking so daemon/session use doesn't stall
    try:
        sys.path.insert(0, '/home/jesus999l/vision_assistant')
        from voice import speak as piper_speak
        piper_speak(text, blocking=False)
    except Exception as e:
        print(f'[session] TTS error: {e}')

    # 4. Arm auto-clear tied to first 15 chars of this text (safe shell escaping)
    anchor = text[:15].replace("'", "'\\''")
    clear_cmd = (
        f"sleep 15 && "
        f"content=$(cat /tmp/echo_bubble.txt 2>/dev/null); "
        f"[[ \"$content\" == *'{anchor}'* ]] && echo -n '' > /tmp/echo_bubble.txt"
    )
    subprocess.Popen(
        ['bash', '-c', clear_cmd],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def daemon_mode():
    """Watch driftwm process; auto-save every 30s."""
    print("[session] daemon started — watching driftwm")
    last_save  = 0
    was_running = True
    while True:
        now = time.time()
        driftwm_running = subprocess.run(
            ["pgrep", "-x", "driftwm"], capture_output=True
        ).returncode == 0

        if driftwm_running:
            was_running = True
            if now - last_save > 30:
                windows = read_state()
                if windows:
                    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
                    json.dump(
                        {"saved_at": now, "windows": windows},
                        open(SESSION_FILE, 'w'), indent=2
                    )
                    last_save = now
        else:
            if was_running:
                print("[session] driftwm crashed — waiting for restart...")
                was_running = False
            time.sleep(2)
            driftwm_back = subprocess.run(
                ["pgrep", "-x", "driftwm"], capture_output=True
            ).returncode == 0
            if driftwm_back and not was_running:
                print("[session] driftwm restarted — restoring session in 3s")
                time.sleep(3)
                was_running = True

        time.sleep(2)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "save":
        save()
    elif cmd == "speak":
        echo_speak(" ".join(sys.argv[2:]))
    elif cmd == "daemon":
        daemon_mode()
    else:
        print("Usage: echo_session.py [save|speak TEXT|daemon]")

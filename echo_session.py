#!/usr/bin/env python3
"""
echo_session.py — DriftWM session save/restore + Echo speech bubble + voice
Commands:
  save    — snapshot current windows to ~/.echo/session.json
  restore — relaunch saved windows
  speak TEXT — send text to Echo bubble + TTS
  daemon  — watch for crashes and auto-restore
"""
import json, os, sys, subprocess, time, socket, threading

SESSION_FILE = os.path.expanduser("~/.echo/session.json")
STATE_FILE   = f"{os.environ.get('XDG_RUNTIME_DIR', '/run/user/1000')}/driftwm/state"
BUBBLE_FILE  = "/tmp/echo_bubble.txt"   # compositor reads this for speech bubble
VA           = os.path.expanduser("~/vision_assistant")
VENV         = os.path.expanduser("~/vision_env/bin/python3")

# ── App launch commands ───────────────────────────────────────────────────────
LAUNCH_MAP = {
    "firefox":              "firefox",
    "gnome-terminal-server":"gnome-terminal",
    "discord":              "discord",
    "cursor":               "cursor --no-sandbox",
    "obsidian":             "obsidian",
    "steam":                "steam",
    "thunar":               "thunar",
}

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
    data = {
        "saved_at": time.time(),
        "windows": windows
    }
    json.dump(data, open(SESSION_FILE, 'w'), indent=2)
    print(f"[session] saved {len(windows)} windows to {SESSION_FILE}")
    for w in windows:
        print(f"  {w['app_id']}: {w['title'][:60]}")

def restore():
    if not os.path.exists(SESSION_FILE):
        print("[session] no session file found")
        return
    data = json.load(open(SESSION_FILE))
    windows = data.get("windows", [])
    print(f"[session] restoring {len(windows)} windows...")
    launched = set()
    for w in windows:
        app_id = w.get("app_id", "")
        cmd    = LAUNCH_MAP.get(app_id)
        if not cmd:
            print(f"  [skip] no launch command for {app_id}")
            continue
        if app_id in launched:
            continue
        launched.add(app_id)
        print(f"  launching {app_id}: {cmd}")
        subprocess.Popen(cmd.split(), env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.4)
    echo_speak(f"Session restored. {len(launched)} apps relaunched.")

def echo_speak(text):
    """Write bubble text and speak via TTS."""
    # Write to bubble file for compositor overlay
    try:
        open(BUBBLE_FILE, 'w').write(text)
    except Exception:
        pass
    # TTS via espeak-ng
    try:
        subprocess.Popen(
            ["espeak-ng", "-v", "en-us", "-s", "145", "-p", "60", text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[session] TTS error: {e}")
    print(f"[Echo] {text}")
    # Auto-clear bubble after 5s via background process (survives parent exit)
    subprocess.Popen(
        ['bash', '-c', 'sleep 5 && echo -n > /tmp/echo_bubble.txt'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def daemon_mode():
    """Watch driftwm process; auto-save every 30s, auto-restore on crash."""
    print("[session] daemon started — watching driftwm")
    last_save = 0
    was_running = True
    while True:
        now = time.time()
        driftwm_running = subprocess.run(
            ["pgrep", "-x", "driftwm"], capture_output=True
        ).returncode == 0

        if driftwm_running:
            was_running = True
            # Auto-save every 30 seconds
            if now - last_save > 30:
                windows = read_state()
                if windows:
                    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
                    json.dump({"saved_at": now, "windows": windows},
                              open(SESSION_FILE, 'w'), indent=2)
                    last_save = now
        else:
            if was_running:
                print("[session] driftwm crashed — waiting for restart...")
                was_running = False
            # Wait for driftwm to come back up
            time.sleep(2)
            driftwm_back = subprocess.run(
                ["pgrep", "-x", "driftwm"], capture_output=True
            ).returncode == 0
            if driftwm_back and not was_running:
                print("[session] driftwm restarted — restoring session in 3s")
                time.sleep(3)
                restore()
                was_running = True

        time.sleep(2)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "save":
        save()
    elif cmd == "restore":
        restore()
    elif cmd == "speak":
        echo_speak(" ".join(sys.argv[2:]))
    elif cmd == "daemon":
        daemon_mode()
    else:
        print("Usage: echo_session.py [save|restore|speak TEXT|daemon]")

def run_hourly_sync():
    """Automated cyclical environment mapping stub"""
    import time
    while True:
        try:
            save_session()
            print("[session] Cyclical hourly checkpoint written successfully.")
        except Exception as e:
            print(f"[session] Backup loop non-fatal fault: {e}")
        time.sleep(3600)

#!/usr/bin/env python3
"""
echo_game_mode.py — Compositor profile switcher for game sessions.

Uses a MASTER config (written once, never touched by game mode) as the
restore point. Game mode patches a LIVE copy. No backup confusion.

On game focus:   patch live config → remove conflicting bindings → reload
On game unfocus: restore from master → reload

Add new games to GAME_PROFILES. No other changes needed.

Start:  nohup ~/vision_env/bin/python3 ~/vision_assistant/echo_game_mode.py </dev/null >> /tmp/echo_game_mode.log 2>&1 &
Stop:   pkill -f echo_game_mode.py
"""

import os, re, signal, subprocess, sys, time
from datetime import datetime
from pathlib import Path

# ── PATHS ─────────────────────────────────────────────────────────────────────
CONFIG_PATH  = Path.home() / ".config/driftwm/config.toml"
MASTER_PATH  = Path.home() / ".config/driftwm/config.master.toml"
POLL_SECS    = 2.0

# ── GAME REGISTRY ─────────────────────────────────────────────────────────────
GAME_PROFILES = {
    "steam_app_230410": {
        "name": "Warframe",
        "process": "Warframe",
        "suppress_mouse_anywhere": ["middle"],
        "suppress_mouse_on_window": [],
    },
}

# ── LOGGING ───────────────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [game_mode] [{level}] {msg}", flush=True)

# ── MASTER CONFIG ─────────────────────────────────────────────────────────────
def ensure_master():
    if MASTER_PATH.exists():
        return
    if not CONFIG_PATH.exists():
        log("config.toml not found!", "ERROR")
        return
    MASTER_PATH.write_text(CONFIG_PATH.read_text())
    log(f"Master config saved: {MASTER_PATH}")

def reset_master():
    if MASTER_PATH.exists():
        MASTER_PATH.unlink()
    ensure_master()
    log("Master config reset from current live config.")

# ── CONFIG PATCHING ───────────────────────────────────────────────────────────
def _remove_mouse_binding(text, section, button):
    pattern = rf'(?m)^[ \t]*"{re.escape(button)}"[ \t]*=[ \t]*"[^"]*"[ \t]*\n?'
    section_re = rf'(\[{re.escape(section)}\][^\[]*)'
    def scrub(m):
        return re.sub(pattern, '', m.group(1))
    return re.sub(section_re, scrub, text, flags=re.DOTALL)

def apply_game_profile(app_id):
    profile = GAME_PROFILES[app_id]
    ensure_master()
    text = MASTER_PATH.read_text()
    changed = False
    for btn in profile.get("suppress_mouse_anywhere", []):
        patched = _remove_mouse_binding(text, "mouse.anywhere", btn)
        if patched != text:
            text = patched
            changed = True
            log(f"  Suppressed [mouse.anywhere] '{btn}'")
    for btn in profile.get("suppress_mouse_on_window", []):
        patched = _remove_mouse_binding(text, "mouse.on_window", btn)
        if patched != text:
            text = patched
            changed = True
            log(f"  Suppressed [mouse.on_window] '{btn}'")
    CONFIG_PATH.write_text(text)
    if changed:
        reload_compositor()
    else:
        log("  No bindings needed suppression")

def restore_normal():
    if not MASTER_PATH.exists():
        log("No master config — cannot restore. Run: echo_game_mode.py reset-master", "WARN")
        return
    CONFIG_PATH.write_text(MASTER_PATH.read_text())
    log("Config restored from master.")
    reload_compositor()

# ── COMPOSITOR RELOAD ─────────────────────────────────────────────────────────
def reload_compositor():
    try:
        subprocess.run(
            ["xdotool", "key", "super+r"],
            capture_output=True, timeout=3,
            env={**os.environ, "DISPLAY": ":0"}
        )
        log("DriftWM reloaded.")
    except Exception as e:
        log(f"Reload failed: {e} — press mod+r manually", "WARN")

# ── DETECTION ─────────────────────────────────────────────────────────────────
def _process_running(name):
    return subprocess.run(["pgrep", "-f", name], capture_output=True).returncode == 0

def _focused_app_id():
    try:
        r = subprocess.run(["wlrctl", "window", "list"],
            capture_output=True, text=True, timeout=3)
        for line in r.stdout.splitlines():
            if "activated" in line or "focused" in line:
                return line.split(None, 1)[0].strip()
    except Exception:
        pass
    return None

def _focused_window_title():
    try:
        r = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=2,
            env={**os.environ, "DISPLAY": ":0"}
        )
        return r.stdout.strip().lower()
    except Exception:
        return ""

def focused_game():
    """Return app_id only when game is BOTH running AND focused."""
    wlr_focused = _focused_app_id()
    title = _focused_window_title()
    for app_id, profile in GAME_PROFILES.items():
        if not _process_running(profile["process"]):
            continue
        if wlr_focused == app_id:
            return app_id
        if profile["name"].lower() in title:
            return app_id
    return None

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
_running = True
_game_active = False
_active_id = None

def _shutdown(sig, frame):
    global _running
    log("Shutting down — restoring config...")
    _running = False
    if _game_active:
        restore_normal()
    sys.exit(0)

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

def run():
    global _game_active, _active_id

    # Wait for DriftWM to settle before doing anything
    time.sleep(3)
    ensure_master()

    log("Game mode manager ready.")
    log(f"Watching: {[p['name'] for p in GAME_PROFILES.values()]}")
    log(f"Master: {MASTER_PATH}")

    while _running:
        try:
            game = focused_game()
            if game and not _game_active:
                _game_active = True
                _active_id = game
                log(f"GAME MODE ON → {GAME_PROFILES[game]['name']}")
                apply_game_profile(game)
            elif not game and _game_active:
                name = GAME_PROFILES.get(_active_id, {}).get("name", "?")
                log(f"GAME MODE OFF ← {name}")
                _game_active = False
                _active_id = None
                restore_normal()
        except Exception as e:
            log(f"Error: {e}", "WARN")
        time.sleep(POLL_SECS)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reset-master":
        reset_master()
        print(f"Master saved to {MASTER_PATH}")
        sys.exit(0)
    run()

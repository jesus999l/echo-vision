"""
Browser and media control.
Uses playerctl for music, xdotool/xdg-open for browser actions.
"""
import subprocess, urllib.parse, time, os, json

_ACTION_LOG_PATH = os.path.expanduser("~/vision_assistant/browser_action_log.json")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def _log_action(action, detail=""):
    try:
        log = []
        if os.path.exists(_ACTION_LOG_PATH):
            with open(_ACTION_LOG_PATH) as f:
                log = json.load(f)
        log.append({"time": time.strftime("%H:%M"), "action": action, "detail": detail})
        with open(_ACTION_LOG_PATH, "w") as f:
            json.dump(log[-10:], f)
    except: pass

def get_action_log():
    try:
        if os.path.exists(_ACTION_LOG_PATH):
            with open(_ACTION_LOG_PATH) as f:
                return json.load(f)
    except: pass
    return []

_player_cache = {"name": None, "ts": 0.0}

def _get_firefox_player():
    """Return current Firefox playerctl instance name (cached 20s)."""
    if time.time() - _player_cache["ts"] < 20 and _player_cache["name"]:
        return _player_cache["name"]
    for line in _run("playerctl -l").stdout.strip().splitlines():
        if "firefox" in line.lower():
            _player_cache["name"] = line.strip()
            _player_cache["ts"]   = time.time()
            return _player_cache["name"]
    _player_cache["name"] = None
    return None

def _player(cmd):
    """Run playerctl on Firefox player, fallback to all players."""
    p = _get_firefox_player()
    if p:
        _run(f"playerctl -p {p} {cmd}")
    else:
        _run(f"playerctl -a {cmd}")

def _get_firefox_wid():
    """Return the largest (main) Firefox window ID."""
    r = _run("xdotool search --class firefox")
    wids = r.stdout.strip().splitlines()
    best, best_area = None, 0
    for wid in wids:
        geo = _run(f"xdotool getwindowgeometry {wid}").stdout
        try:
            import re
            m = re.search(r'Geometry: (\d+)x(\d+)', geo)
            if m:
                area = int(m.group(1)) * int(m.group(2))
                if area > best_area:
                    best_area = area
                    best = wid
        except: pass
    return best

def _minimize_vision():
    for name in [".*Vision Assistant.*", ".*ChatOverlay.*"]:
        r = _run(f"xdotool search --name '{name}'")
        wid = r.stdout.strip().split()[0] if r.stdout.strip() else None
        if wid:
            _run(f"xdotool windowminimize {wid}")
            time.sleep(0.3)
            return wid
    return None

def _restore_vision(wid):
    if wid:
        time.sleep(0.2)
        _run(f"xdotool windowactivate {wid}")

# ── MUSIC ─────────────────────────────────────────────────────────────────────
def play_liked():
    """Resume or open YouTube Music liked songs."""
    import threading
    _log_action("play_liked")
    def _bg():
        # Try resume first (fast path)
        result = _run("playerctl -a status")
        if "Paused" in result.stdout:
            _run("playerctl -a play"); return
        if "Playing" in result.stdout:
            return
        # Nothing playing — open YT Music
        _player_cache["name"] = None  # invalidate cache
        _run("xdg-open 'https://music.youtube.com/library/liked_songs'")
        time.sleep(6.0)
        _player_cache["ts"] = 0  # force rescan
        p = _get_firefox_player()
        if p: _run(f"playerctl -p {p} play")
    threading.Thread(target=_bg, daemon=True).start()
    return "Playing your liked music..."

def play_music(query=None):
    """Search and play a song on YouTube Music."""
    if not query:
        return play_liked()
    import threading
    _log_action("play_song", query)
    def _bg():
        va_wid = _minimize_vision()
        try:
            ff_wid = _get_firefox_wid()
            if not ff_wid:
                _run(f"xdg-open 'https://music.youtube.com/search?q={urllib.parse.quote(query)}'")
                time.sleep(5.0)
                ff_wid = _get_firefox_wid()
                if not ff_wid: return
            _run(f"xdotool windowactivate --sync {ff_wid}")
            time.sleep(0.5)
            url = f"https://music.youtube.com/search?q={urllib.parse.quote(query)}"
            _run("xdotool key ctrl+l")
            time.sleep(0.3)
            _run(f"echo -n '{url}' | xclip -selection clipboard")
            time.sleep(0.1)
            _run("xdotool key ctrl+a ctrl+v Return")
            time.sleep(4.0)
            for _ in range(4):
                _run("xdotool key Tab")
                time.sleep(0.1)
            _run("xdotool key Return")
        finally:
            _restore_vision(va_wid)
    threading.Thread(target=_bg, daemon=True).start()
    return f"Searching for {query}..."

def media_pause():
    _player("play-pause"); return "Toggled play/pause."

def media_next():
    _player("next"); return "Next track."

def media_prev():
    _player("previous"); return "Previous track."

# ── VOLUME ────────────────────────────────────────────────────────────────────
def volume_up():
    _run("xdotool key XF86AudioRaiseVolume XF86AudioRaiseVolume XF86AudioRaiseVolume")
    _log_action("volume_up")
    return "Volume up."

def volume_down():
    _run("xdotool key XF86AudioLowerVolume XF86AudioLowerVolume XF86AudioLowerVolume")
    _log_action("volume_down")
    return "Volume down."

def volume_mute():
    _run("xdotool key XF86AudioMute")
    _log_action("volume_mute")
    return "Toggled mute."

# ── WEB ───────────────────────────────────────────────────────────────────────
def web_search(query):
    _run(f"xdg-open 'https://www.google.com/search?q={urllib.parse.quote(query)}'")
    return f"Searching: {query}"

def youtube_search(query):
    _run(f"xdg-open 'https://www.youtube.com/results?search_query={urllib.parse.quote(query)}'")
    return f"YouTube: {query}"


# ── VLC / LOCAL MEDIA ─────────────────────────────────────────────────────────
import glob as _glob

def _detect_usb():
    """Return the first mounted USB media path under /media/<user>/."""
    user = os.environ.get("USER", "jesus999l")
    mounts = _glob.glob(f"/media/{user}/*/")
    # Prefer drive with video files
    for m in mounts:
        for root, dirs, files in os.walk(m):
            for f in files:
                if f.lower().endswith((".mp4", ".mkv", ".avi", ".webm")):
                    return m
    return mounts[0] if mounts else None

def play_usb(path=None):
    """Launch scan_and_play.py with USB drive or given path."""
    import threading
    target = path or _detect_usb()
    if not target:
        return "No USB drive detected."
    _log_action("play_usb", target)
    def _bg():
        import subprocess as _sp
        _sp.Popen(
            ["python3", os.path.expanduser("~/scan_and_play.py"), target],
            env={**os.environ, "GTK_THEME": "Mint-Y-Dark",
                 "QT_STYLE_OVERRIDE": "gtk2", "QT_QPA_PLATFORMTHEME": "gtk2"},
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    threading.Thread(target=_bg, daemon=True).start()
    return f"Playing media from {os.path.basename(target.rstrip('/'))}..."

def vlc_pause():
    """Pause/resume VLC via playerctl."""
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} play-pause")
            return "VLC toggled."
    # Fallback — all players
    _run("playerctl -a play-pause")
    return "Toggled playback."

def vlc_next():
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} next")
            return "Next."
    _run("playerctl -a next")
    return "Next."

def vlc_prev():
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} previous")
            return "Previous."
    _run("playerctl -a previous")
    return "Previous."

def vlc_stop():
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} stop")
            return "VLC stopped."
    _run("playerctl -a stop")
    return "Stopped."

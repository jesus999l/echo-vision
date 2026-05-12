"""
echo_game_recorder.py — Passive input recorder for Echo game learning.

- Monitors for Warframe window focus
- Records all keyboard + mouse inputs with timestamps only when Warframe is focused
- Saves sessions to ~/echo_game_sessions/
- Analyzes patterns: combos, timing, habits, rotations
- Echo can query session data to understand playstyle

Auto-starts when Warframe process detected.
Can be imported by wake_word.py or run standalone.
"""
import os, sys, json, time, threading, subprocess
from datetime import datetime

SESSION_DIR = os.path.expanduser("~/echo_game_sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

WARFRAME_TITLES = ["warframe", "warframe.x64"]
POLL_INTERVAL   = 0.5   # seconds between focus checks

# ── SESSION ───────────────────────────────────────────────────────────────────
class GameSession:
    def __init__(self):
        self.start_time = time.time()
        self.events     = []          # {t, type, key/btn, x, y, action}
        self.focused_time = 0.0
        self._focus_start = None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(SESSION_DIR, f"session_{ts}.json")
        self.metadata = {
            "start":    datetime.now().isoformat(),
            "end":      None,
            "duration": 0,
            "game":     "Warframe",
            "events":   0,
        }
        print(f"[recorder] Session started → {self.path}")

    def log(self, event_type, key=None, button=None, x=None, y=None, action=None):
        self.events.append({
            "t":      round(time.time() - self.start_time, 3),
            "type":   event_type,   # "key" | "mouse_click" | "mouse_move" | "mouse_scroll"
            "key":    key,
            "btn":    button,
            "x":      x,
            "y":      y,
            "action": action,       # "press" | "release" | "scroll_up" | "scroll_down"
        })

    def on_focus(self):
        self._focus_start = time.time()

    def on_unfocus(self):
        if self._focus_start:
            self.focused_time += time.time() - self._focus_start
            self._focus_start = None

    def save(self):
        self.on_unfocus()
        self.metadata["end"]      = datetime.now().isoformat()
        self.metadata["duration"] = round(time.time() - self.start_time, 1)
        self.metadata["focused"]  = round(self.focused_time, 1)
        self.metadata["events"]   = len(self.events)
        data = {
            "metadata": self.metadata,
            "events":   self.events,
            "analysis": analyze_session(self.events),
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[recorder] Session saved — {len(self.events)} events, "
              f"{self.metadata['focused']}s focused → {self.path}")
        return self.path

# ── ANALYSIS ──────────────────────────────────────────────────────────────────
def analyze_session(events):
    """Extract patterns from raw events for Echo to understand playstyle."""
    if not events:
        return {}

    key_counts   = {}
    mouse_clicks = {}
    combos       = []
    burst_windows = []  # periods of high activity

    last_keys    = []
    last_t       = 0
    burst_start  = None
    burst_count  = 0
    BURST_GAP    = 0.5   # seconds gap = new burst
    COMBO_WINDOW = 0.8   # seconds = combo window

    for ev in events:
        t = ev["t"]

        # Key counts
        if ev["type"] == "key" and ev["action"] == "press" and ev["key"]:
            k = ev["key"]
            key_counts[k] = key_counts.get(k, 0) + 1

            # Combo detection
            if t - last_t < COMBO_WINDOW:
                last_keys.append(k)
            else:
                if len(last_keys) >= 3:
                    combos.append(last_keys[:])
                last_keys = [k]
            last_t = t

        # Mouse button counts
        if ev["type"] == "mouse_click" and ev["btn"]:
            b = ev["btn"]
            mouse_clicks[b] = mouse_clicks.get(b, 0) + 1

        # Burst detection (rapid input)
        if ev["type"] in ("key", "mouse_click"):
            if burst_start is None or t - last_t > BURST_GAP:
                if burst_count >= 5:
                    burst_windows.append({
                        "start": round(burst_start, 1),
                        "count": burst_count
                    })
                burst_start = t
                burst_count = 1
            else:
                burst_count += 1

    # Top keys
    top_keys = sorted(key_counts.items(), key=lambda x: x[1], reverse=True)[:15]

    # Most common combos
    combo_strs = ["+".join(c) for c in combos]
    combo_counts = {}
    for c in combo_strs:
        combo_counts[c] = combo_counts.get(c, 0) + 1
    top_combos = sorted(combo_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "top_keys":    top_keys,
        "mouse_clicks": sorted(mouse_clicks.items(), key=lambda x: x[1], reverse=True),
        "top_combos":  top_combos,
        "burst_windows": burst_windows[:20],
        "total_keystrokes": sum(key_counts.values()),
        "total_clicks": sum(mouse_clicks.values()),
    }

# ── FOCUS WATCHER ─────────────────────────────────────────────────────────────
def _get_active_window_title():
    try:
        r = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=1
        )
        return r.stdout.strip().lower()
    except:
        return ""

def _warframe_focused():
    title = _get_active_window_title()
    return any(wf in title for wf in WARFRAME_TITLES)

def _warframe_running():
    r = subprocess.run(["pgrep", "-f", "Warframe.x64.exe"], capture_output=True)
    return r.returncode == 0

# ── INPUT LISTENER ────────────────────────────────────────────────────────────
_session     = None
_focused     = False
_listener_kb = None
_listener_ms = None
_recording   = False

def _start_listeners(session):
    global _listener_kb, _listener_ms
    try:
        from pynput import keyboard, mouse

        def on_key_press(key):
            if not _focused: return
            try:
                k = key.char if hasattr(key, 'char') and key.char else str(key).replace('Key.', '')
                session.log("key", key=k, action="press")
            except: pass

        def on_key_release(key):
            if not _focused: return
            try:
                k = key.char if hasattr(key, 'char') and key.char else str(key).replace('Key.', '')
                session.log("key", key=k, action="release")
            except: pass

        def on_click(x, y, button, pressed):
            if not _focused: return
            session.log("mouse_click", button=str(button).replace('Button.', ''),
                       x=x, y=y, action="press" if pressed else "release")

        def on_scroll(x, y, dx, dy):
            if not _focused: return
            session.log("mouse_scroll", x=x, y=y,
                       action="scroll_up" if dy > 0 else "scroll_down")

        def on_move(x, y):
            if not _focused: return
            # Only log every 10th move to avoid flooding
            if len(session.events) % 10 == 0:
                session.log("mouse_move", x=x, y=y)

        _listener_kb = keyboard.Listener(
            on_press=on_key_press, on_release=on_key_release)
        _listener_ms = mouse.Listener(
            on_click=on_click, on_scroll=on_scroll, on_move=on_move)

        _listener_kb.daemon = True
        _listener_ms.daemon = True
        _listener_kb.start()
        _listener_ms.start()
        print("[recorder] Input listeners active.")
    except Exception as e:
        print(f"[recorder] Listener error: {e}")

def _stop_listeners():
    global _listener_kb, _listener_ms
    try:
        if _listener_kb: _listener_kb.stop()
        if _listener_ms: _listener_ms.stop()
    except: pass
    _listener_kb = _listener_ms = None

# ── MAIN MONITOR LOOP ─────────────────────────────────────────────────────────
def _monitor_loop():
    global _session, _focused, _recording

    print("[recorder] Waiting for Warframe...")
    while True:
        running = _warframe_running()

        if running and not _recording:
            # Warframe just launched
            _recording = True
            _session = GameSession()
            _start_listeners(_session)
            # Save loadout to session metadata
            try:
                sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
                from warframe_loadout import read_loadout_from_log, get_loadout_summary
                loadout = read_loadout_from_log()
                if loadout:
                    _session.metadata["loadout"] = loadout
                    _session.metadata["loadout_summary"] = get_loadout_summary()
                    print(f"[recorder] Loadout: {get_loadout_summary()}")
            except Exception as e:
                print(f"[recorder] Loadout read failed: {e}")
            print("[recorder] Warframe detected — recording started.")
            # Move Warframe to game space (workspace 1)
            import subprocess as _sp
            _sp.Popen(["bash", os.path.expanduser("~/warframe-workspace.sh")])
            try:
                from briefing import send_notification
                send_notification("Echo", "Game recording started.", urgency="low")
            except: pass

        elif not running and _recording:
            # Warframe closed
            _recording = False
            _focused = False
            _stop_listeners()
            if _session:
                path = _session.save()
                _session = None
                print("[recorder] Warframe closed — session saved.")
                try:
                    from briefing import send_notification
                    send_notification("Echo", "Game session saved.", urgency="low")
                except: pass

        if _recording and _session:
            # Update focus state
            now_focused = _warframe_focused()
            if now_focused and not _focused:
                _focused = True
                _session.on_focus()
            elif not now_focused and _focused:
                _focused = False
                _session.on_unfocus()

        time.sleep(POLL_INTERVAL)

def start_game_recorder():
    """Start the game recorder as a background daemon thread."""
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
    print("[recorder] Game recorder running — will auto-start on Warframe launch.")
    return t

# ── QUERY INTERFACE FOR ECHO ─────────────────────────────────────────────────
def get_recent_sessions(n=5):
    """Return metadata from the last N sessions."""
    files = sorted(
        [f for f in os.listdir(SESSION_DIR) if f.endswith(".json")],
        reverse=True
    )[:n]
    sessions = []
    for f in files:
        try:
            data = json.load(open(os.path.join(SESSION_DIR, f)))
            sessions.append(data.get("metadata", {}))
        except: pass
    return sessions

def get_session_analysis(session_file=None):
    """Return analysis from latest session or specified file."""
    if not session_file:
        files = sorted(
            [f for f in os.listdir(SESSION_DIR) if f.endswith(".json")],
            reverse=True
        )
        if not files: return None
        session_file = os.path.join(SESSION_DIR, files[0])
    try:
        data = json.load(open(session_file))
        return data.get("analysis", {})
    except: return None

def summarize_playstyle():
    """Generate a natural language summary of playstyle for Echo."""
    files = sorted(
        [f for f in os.listdir(SESSION_DIR) if f.endswith(".json")],
        reverse=True
    )[:10]
    if not files:
        return "No game sessions recorded yet."

    all_keys = {}
    all_combos = {}
    total_sessions = len(files)
    total_time = 0

    for f in files:
        try:
            data = json.load(open(os.path.join(SESSION_DIR, f)))
            meta = data.get("metadata", {})
            analysis = data.get("analysis", {})
            total_time += meta.get("focused", 0)
            for k, v in analysis.get("top_keys", []):
                all_keys[k] = all_keys.get(k, 0) + v
            for c, v in analysis.get("top_combos", []):
                all_combos[c] = all_combos.get(c, 0) + v
        except: pass

    top_keys   = sorted(all_keys.items(),   key=lambda x: x[1], reverse=True)[:8]
    top_combos = sorted(all_combos.items(), key=lambda x: x[1], reverse=True)[:5]

    hours = total_time / 3600
    summary = f"Based on {total_sessions} Warframe sessions ({hours:.1f}h total):\n"
    summary += f"Most used keys: {', '.join(k for k, _ in top_keys)}\n"
    if top_combos:
        summary += f"Common combos: {', '.join(c for c, _ in top_combos)}\n"
    return summary

if __name__ == "__main__":
    start_game_recorder()
    print("Press Ctrl+C to stop.")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        if _session: _session.save()
        print("Stopped.")

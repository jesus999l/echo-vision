#!/usr/bin/env python3
import subprocess, json, sys

APP_ICONS = {
    "firefox": "🦊", "discord": "💬", "cursor": "✦",
    "obsidian": "🔮", "steam": "🎮", "nemo": "📁",
    "thunar": "📁", "code": "⌨", "chromium": "🌐",
    "vlc": "▶", "kitty": "🖥", "alacritty": "🖥",
    "tilix": "🖥", "warframe": "⚔", "easyeffects": "🎛",
    "blueman": "🔵", "pavucontrol": "🔊", "default": "◆",
}
STATE_FILE = "/tmp/echo_taskbar_state.json"
IGNORE = ["sticky.py", "drift_panel", "echo_taskbar"]

def wlr_list():
    try:
        out = subprocess.check_output(["wlrctl","toplevel","list"], text=True, stderr=subprocess.DEVNULL)
        wins = []
        for line in out.strip().splitlines():
            p = line.split(None, 2)
            if len(p) >= 2:
                wins.append({"id": p[0], "app_id": p[1].lower().rstrip(":"), "title": p[2] if len(p) > 2 else p[1]})
        return wins
    except:
        return []

def get_icon(app_id):
    for k, v in APP_ICONS.items():
        if k in app_id:
            return v
    return APP_ICONS["default"]

def load_state():
    try: return json.load(open(STATE_FILE))
    except: return {}

def save_state(s):
    try: json.dump(s, open(STATE_FILE, "w"))
    except: pass

def build():
    wins = wlr_list()
    if not wins:
        print(json.dumps({"text": "", "tooltip": "No windows"}))
        sys.stdout.flush()
        return
    groups = {}
    for w in wins:
        if any(x in w["app_id"] for x in IGNORE):
            continue
        groups.setdefault(w["app_id"], []).append(w)
    parts, tips = [], []
    for aid, ws in groups.items():
        icon = get_icon(aid)
        count = len(ws)
        badge = f"<sup>{count}</sup>" if count > 1 else ""
        parts.append(f"{icon}{badge}")
        tips.append(f"{icon} {aid}  [{count}]")
        for w in ws:
            tips.append(f"  └ {w['title'][:50]}")
    print(json.dumps({"text": "  ".join(parts), "tooltip": "\n".join(tips)}))
    sys.stdout.flush()

if len(sys.argv) > 1 and sys.argv[1] == "click":
    wins = wlr_list()
    if not wins: sys.exit(0)
    groups = {}
    for w in wins:
        if not any(x in w["app_id"] for x in IGNORE):
            groups.setdefault(w["app_id"], []).append(w)
    all_wins = [w for ws in groups.values() for w in ws]
    s = load_state()
    idx = s.get("idx", 0) % len(all_wins)
    subprocess.run(["wlrctl", "toplevel", "focus", "id:" + all_wins[idx]["id"]], capture_output=True)
    s["idx"] = (idx + 1) % len(all_wins)
    save_state(s)
    sys.exit(0)

build()
sys.exit(0)

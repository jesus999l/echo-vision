#!/usr/bin/env python3
"""
echo_sticky_bar.py — Waybar module for Sticky notes app
Shows one 📝 icon with count, hover lists all note titles
Click focuses the Sticky app window
"""
import subprocess, json, sys

def get_sticky_windows():
    try:
        out = subprocess.check_output(["wlrctl", "toplevel", "list"], text=True, stderr=subprocess.DEVNULL)
        windows = []
        for line in out.strip().splitlines():
            if "sticky.py" in line:
                parts = line.split(None, 2)
                wid = parts[0] if parts else ""
                title = parts[2] if len(parts) > 2 else "Note"
                if title == "sticky.py":
                    title = "Untitled Note"
                windows.append({"id": wid, "title": title})
        return windows
    except:
        return []

def focus_sticky(windows):
    # Focus the main Sticky window (titled "Notes") or first one
    target = next((w for w in windows if w["title"] == "Notes"), None)
    if not target and windows:
        target = windows[0]
    if target:
        subprocess.run(["wlrctl", "toplevel", "focus", f"title:Notes"], capture_output=True)
    else:
        # Launch sticky if not running
        subprocess.Popen(["sticky"], start_new_session=True)

if len(sys.argv) > 1 and sys.argv[1] == "click":
    windows = get_sticky_windows()
    focus_sticky(windows)
    sys.exit(0)

windows = get_sticky_windows()
count = len(windows)

if count == 0:
    print(json.dumps({"text": "", "tooltip": "No sticky notes"}))
else:
    titles = [w["title"] for w in windows]
    unique = list(dict.fromkeys(titles))  # dedupe preserving order
    tooltip_lines = [f"📝 Sticky Notes ({count})"] + [f"  • {t}" for t in unique]
    badge = f"<sup>{count}</sup>" if count > 1 else ""
    print(json.dumps({
        "text": f"📝{badge}",
        "tooltip": "\n".join(tooltip_lines)
    }))

sys.exit(0)

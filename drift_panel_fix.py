#!/usr/bin/env python3
"""Patch wlr_focus and wlr_close in drift_panel.py"""

path = "/home/claude/drift_panel_patch.py"

NEW_FUNCTIONS = '''
XWAYLAND_APPS = {"firefox", "discord", "steam", "chromium", "chrome"}

def wlr_focus(win):
    title  = win.get("title", "")[:60]
    app_id = win.get("app_id", "").lower()
    try:
        if any(x in app_id for x in XWAYLAND_APPS):
            ids = subprocess.check_output(
                ["xdotool", "search", "--name", title],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip().splitlines()
            if ids:
                subprocess.Popen(["xdotool", "windowactivate", "--sync", ids[0]],
                                 stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(
                ["wlrctl", "toplevel", "focus", f"title:{title}"],
                stderr=subprocess.DEVNULL
            )
    except Exception:
        pass


def wlr_close(win):
    title  = win.get("title", "")[:60]
    app_id = win.get("app_id", "").lower()
    try:
        if any(x in app_id for x in XWAYLAND_APPS):
            ids = subprocess.check_output(
                ["xdotool", "search", "--name", title],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip().splitlines()
            if ids:
                subprocess.Popen(["xdotool", "windowclose", ids[0]],
                                 stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(
                ["wlrctl", "toplevel", "close", f"title:{title}"],
                stderr=subprocess.DEVNULL
            )
    except Exception:
        pass

'''

with open("/home/jesus999l/vision_assistant/drift_panel.py") as f:
    src = f.read()

# Replace old wlr_focus and wlr_close functions
import re
src = re.sub(
    r'\ndef wlr_focus\(win\):.*?\n\ndef wlr_close\(win\):.*?\n\n',
    NEW_FUNCTIONS,
    src,
    flags=re.DOTALL
)

with open("/home/jesus999l/vision_assistant/drift_panel.py", "w") as f:
    f.write(src)

import ast
ast.parse(src)
print("patched and syntax ok")

"""
Patch: Autostart + skip briefing on boot.
1. Creates ~/.config/autostart/echo-desktop.desktop
2. Patches main.py to support --no-briefing flag and settings.json skip_briefing key
   - Reminder daemon always starts (notifications/reminders still work)
   - Briefing notification + speech are skipped when flag/setting active

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_autostart_briefing.py
"""
import os, subprocess

MAIN    = os.path.expanduser("~/vision_assistant/main.py")
AUTODIR = os.path.expanduser("~/.config/autostart")
DESKTOP = os.path.join(AUTODIR, "echo-desktop.desktop")

# ── 1. AUTOSTART ──────────────────────────────────────────────────────────────
os.makedirs(AUTODIR, exist_ok=True)

desktop_content = """\
[Desktop Entry]
Type=Application
Name=Echo Desktop
Comment=Echo AI Assistant
Exec=/home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/main.py
Path=/home/jesus999l/vision_assistant
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
"""

with open(DESKTOP, "w") as f:
    f.write(desktop_content)
os.chmod(DESKTOP, 0o755)
print(f"OK: autostart entry written → {DESKTOP}")

# ── 2. MAIN.PY — skip briefing flag ──────────────────────────────────────────
src = open(MAIN).read()

old_briefing = '''    try:
        from briefing import get_morning_briefing, show_morning_briefing_notification, speak_morning_briefing, start_reminder_daemon
        b = get_morning_briefing()
        show_morning_briefing_notification(b)
        start_reminder_daemon()
        # Speak briefing on startup if enabled
        try:
            import json as _j, os as _o
            _cfg = _j.load(open(_o.path.expanduser("~/vision_assistant/settings.json")))
            if _cfg.get("speak_briefing", False):
                import threading as _th
                _th.Thread(target=speak_morning_briefing, args=(b,), daemon=True).start()
        except: pass
        print("[main] Briefing + reminder daemon started.")
    except Exception as e:
        print(f"[main] Briefing skipped: {e}")'''

new_briefing = '''    try:
        from briefing import get_morning_briefing, show_morning_briefing_notification, speak_morning_briefing, start_reminder_daemon

        # Check skip flags: --no-briefing arg OR settings.json skip_briefing=true
        _skip_briefing = "--no-briefing" in sys.argv
        if not _skip_briefing:
            try:
                import json as _j, os as _o
                _cfg = _j.load(open(_o.path.expanduser("~/vision_assistant/settings.json")))
                _skip_briefing = bool(_cfg.get("skip_briefing", False))
            except: pass

        # Reminder daemon always runs regardless of skip
        start_reminder_daemon()

        if not _skip_briefing:
            b = get_morning_briefing()
            show_morning_briefing_notification(b)
            # Speak briefing if enabled
            try:
                import json as _j, os as _o
                _cfg = _j.load(open(_o.path.expanduser("~/vision_assistant/settings.json")))
                if _cfg.get("speak_briefing", False):
                    import threading as _th
                    _th.Thread(target=speak_morning_briefing, args=(b,), daemon=True).start()
            except: pass
            print("[main] Briefing + reminder daemon started.")
        else:
            print("[main] Briefing skipped (--no-briefing or settings). Reminder daemon running.")
    except Exception as e:
        print(f"[main] Briefing skipped: {e}")'''

if old_briefing in src:
    src = src.replace(old_briefing, new_briefing)
    open(MAIN, "w").write(src)
    print("OK: main.py briefing block patched")
else:
    print("FAIL: briefing block not found in main.py — may already be patched")

# ── 3. SYNTAX CHECK ───────────────────────────────────────────────────────────
r = subprocess.run(
    ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", MAIN],
    capture_output=True, text=True
)
print(f"{'OK' if r.returncode == 0 else 'ERR'}: main.py syntax")
if r.returncode != 0:
    print(r.stderr)

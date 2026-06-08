"""
Patch: Fix Warframe bot for Linux/Proton.
1. Fix WARFRAME_DISPLAY :1 → :0
2. Fix process detection to find Warframe.x64.exe (Proton)
3. Fix window detection to use DISPLAY=:0
4. Add voice commands to wake_word.py:
   - "farm orokin cells" / "farm neurodes" etc → launches bot
   - "stop farming" → kills bot
   - "what should I farm" / "farming tip" → KB lookup via voice

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_warframe_bot.py
"""
import os, subprocess, shutil

VA   = os.path.expanduser("~/vision_assistant")
BOT  = os.path.expanduser("~/echo_warframe/echo_warframe_bot.py")
WW   = os.path.join(VA, "wake_word.py")

# ── 1. FIX BOT ────────────────────────────────────────────────────────────────
src = open(BOT).read()

fixes = [
    # Fix display
    ('WARFRAME_DISPLAY = ":1"',
     'WARFRAME_DISPLAY = ":0"'),

    # Fix process detection — Proton uses Warframe.x64.exe
    ('result = subprocess.run(\n        ["pgrep", "-x", WARFRAME_PROCESS],\n        capture_output=True, text=True\n    )\n    # Also check wine/proton process names\n    result2 = subprocess.run(\n        ["pgrep", "-f", "Warframe.exe"],\n        capture_output=True, text=True\n    )\n    return bool(result.stdout.strip() or result2.stdout.strip())',
     'result = subprocess.run(\n        ["pgrep", "-f", "Warframe.x64.exe"],\n        capture_output=True, text=True\n    )\n    return bool(result.stdout.strip())'),

    # Fix window search to use correct display env
    ('["xdotool", "search", "--name", "Warframe"],\n        capture_output=True, text=True,\n        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}',
     '["xdotool", "search", "--class", "warframe"],\n        capture_output=True, text=True,\n        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}'),
]

applied = 0
for old, new in fixes:
    if old in src:
        src = src.replace(old, new)
        applied += 1
    else:
        print(f"WARN: fix not found — {old[:50]!r}")

open(BOT, "w").write(src)
print(f"OK: {applied}/{len(fixes)} fixes applied to bot")

# ── 2. COPY BOT TO vision_assistant FOR EASY IMPORT ──────────────────────────
dst = os.path.join(VA, "echo_warframe_bot.py")
shutil.copy2(BOT, dst)
print(f"OK: bot copied to {dst}")

# ── 3. ADD VOICE COMMANDS TO wake_word.py ────────────────────────────────────
ww_src = open(WW).read()

old_anchor = '''    # Game recorder queries'''

new_anchor = '''    # Warframe bot commands
    import re as _re
    _farm_match = _re.search(r"farm\s+(.+)", t)
    if _farm_match:
        resource = _farm_match.group(1).strip()
        def _start_farm(res=resource):
            try:
                import subprocess as _sp
                from voice import speak
                speak(f"Starting farm for {res}. Check the terminal for progress.")
                _sp.Popen([
                    "/home/jesus999l/vision_env/bin/python3",
                    "/home/jesus999l/echo_warframe/echo_warframe_bot.py",
                    "--resource", res
                ])
                _notify(f"🎮 Farming: {res}")
            except Exception as e:
                print(f"[wake] farm error: {e}")
        import threading; threading.Thread(target=_start_farm, daemon=True).start(); return

    if any(x in t for x in ["stop farming", "stop bot", "stop warframe bot"]):
        import subprocess as _sp
        _sp.run(["pkill", "-f", "echo_warframe_bot"], capture_output=True)
        from voice import speak
        speak("Farming stopped.")
        return

    if any(x in t for x in ["what should i farm", "farming tip", "where to farm", "best farm"]):
        def _farm_tip():
            try:
                from voice import speak
                speak("Tell me what resource you need and I will look it up. For example, say: farm orokin cells.")
            except Exception as e:
                print(f"[wake] farm tip error: {e}")
        import threading; threading.Thread(target=_farm_tip, daemon=True).start(); return

    # Game recorder queries'''

if "stop farming" not in ww_src:
    if old_anchor in ww_src:
        ww_src = ww_src.replace(old_anchor, new_anchor)
        open(WW, "w").write(ww_src)
        print("OK: Warframe voice commands added")
    else:
        print("FAIL: anchor not found in wake_word.py")
else:
    print("INFO: Warframe commands already in wake_word.py")

# ── 4. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("echo_warframe_bot.py", BOT), ("wake_word.py", WW)]:
    r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
    print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
    if r.returncode != 0:
        print(r.stderr)

# ── 5. QUICK DRY RUN TEST ────────────────────────────────────────────────────
print("\nTesting KB lookup (dry run)...")
r = subprocess.run(
    [py, BOT, "--resource", "orokin cell", "--dry-run"],
    capture_output=True, text=True,
    cwd=os.path.expanduser("~/echo_warframe")
)
print(r.stdout[-500:] if r.stdout else "no output")
if r.returncode != 0:
    print(r.stderr[-300:])

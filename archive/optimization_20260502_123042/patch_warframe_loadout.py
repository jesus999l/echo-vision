"""
Patch: Wire warframe_loadout.py into bot and game recorder.
1. Copies warframe_loadout.py to ~/echo_warframe/ and ~/vision_assistant/
2. Bot logs loadout at session start
3. Game recorder saves loadout to session JSON when Warframe detected
4. Voice: "what's my loadout" / "current loadout" → Echo speaks it

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_warframe_loadout.py
"""
import os, subprocess, shutil

VA      = os.path.expanduser("~/vision_assistant")
WF      = os.path.expanduser("~/echo_warframe")
BOT     = os.path.join(WF, "echo_warframe_bot.py")
REC     = os.path.join(VA, "echo_game_recorder.py")
WW      = os.path.join(VA, "wake_word.py")
LD_SRC  = os.path.join(os.path.dirname(__file__), "warframe_loadout.py")

# ── 1. COPY LOADOUT MODULE ────────────────────────────────────────────────────
if not os.path.exists(LD_SRC):
    LD_SRC = os.path.expanduser("~/Downloads/warframe_loadout.py")

for dest_dir in [WF, VA]:
    dst = os.path.join(dest_dir, "warframe_loadout.py")
    if os.path.exists(LD_SRC) and LD_SRC != dst:
        shutil.copy2(LD_SRC, dst)
print("OK: warframe_loadout.py copied")

# ── 2. WIRE INTO BOT — log loadout at start ───────────────────────────────────
bot_src = open(BOT).read()

old_bot_start = '''    log(f"Echo Warframe Bot starting - Target: {resource_name}")

    # 1. Load KB and look up resource'''

new_bot_start = '''    log(f"Echo Warframe Bot starting - Target: {resource_name}")

    # Log current loadout
    try:
        sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from warframe_loadout import get_loadout_summary
        loadout = get_loadout_summary()
        log(f"Loadout: {loadout}")
    except Exception as e:
        log(f"Loadout read failed: {e}", "WARN")

    # 1. Load KB and look up resource'''

if old_bot_start in bot_src:
    bot_src = bot_src.replace(old_bot_start, new_bot_start)
    open(BOT, "w").write(bot_src)
    shutil.copy2(BOT, os.path.join(VA, "echo_warframe_bot.py"))
    print("OK: loadout logging added to bot")
else:
    print("FAIL: bot start block not found")

# ── 3. WIRE INTO GAME RECORDER — save loadout when session starts ─────────────
rec_src = open(REC).read()

old_rec_start = '''        if running and not _recording:
            # Warframe just launched
            _recording = True
            _session = GameSession()
            _start_listeners(_session)
            print("[recorder] Warframe detected — recording started.")
            try:
                from briefing import send_notification
                send_notification("Echo", "Game recording started.", urgency="low")
            except: pass'''

new_rec_start = '''        if running and not _recording:
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
            try:
                from briefing import send_notification
                send_notification("Echo", "Game recording started.", urgency="low")
            except: pass'''

if old_rec_start in rec_src:
    rec_src = rec_src.replace(old_rec_start, new_rec_start)
    open(REC, "w").write(rec_src)
    print("OK: loadout detection wired into game recorder")
else:
    print("FAIL: recorder start block not found")

# ── 4. ADD VOICE COMMAND TO wake_word.py ─────────────────────────────────────
ww_src = open(WW).read()

old_farm_stop = '''    if any(x in t for x in ["stop farming", "stop bot", "stop warframe bot"]):'''

new_loadout_voice = '''    if any(x in t for x in ["what's my loadout", "current loadout", "my loadout", "what am i using"]):
        def _speak_loadout():
            try:
                from warframe_loadout import get_loadout_summary
                from voice import speak
                summary = get_loadout_summary()
                speak(f"Current loadout: {summary}")
                _notify(summary)
            except Exception as e:
                print(f"[wake] loadout error: {e}")
        import threading; threading.Thread(target=_speak_loadout, daemon=True).start(); return

    if any(x in t for x in ["stop farming", "stop bot", "stop warframe bot"]):'''

if "what's my loadout" not in ww_src:
    if old_farm_stop in ww_src:
        ww_src = ww_src.replace(old_farm_stop, new_loadout_voice)
        open(WW, "w").write(ww_src)
        print("OK: loadout voice command added")
    else:
        print("FAIL: anchor not found in wake_word.py")
else:
    print("INFO: loadout voice already present")

# ── 5. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [
    ("warframe_loadout.py", os.path.join(VA, "warframe_loadout.py")),
    ("echo_warframe_bot.py", BOT),
    ("echo_game_recorder.py", REC),
    ("wake_word.py", WW),
]:
    if os.path.exists(path):
        r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
        print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
        if r.returncode != 0:
            print(r.stderr)

# ── 6. QUICK TEST ─────────────────────────────────────────────────────────────
print("\nTesting loadout detection...")
r = subprocess.run(
    [py, os.path.join(VA, "warframe_loadout.py")],
    capture_output=True, text=True
)
print(r.stdout.strip() or r.stderr.strip())

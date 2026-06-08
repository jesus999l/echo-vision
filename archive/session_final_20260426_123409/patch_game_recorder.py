"""
Patch: Wire echo_game_recorder.py into Echo.
1. Copies echo_game_recorder.py to ~/vision_assistant/
2. Starts recorder in main.py on boot
3. Adds voice commands to wake_word.py:
   - "how do I play" / "my playstyle" / "game summary" → Echo summarizes sessions
   - "game stats" / "last session" → Echo reports last session stats

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_game_recorder.py
"""
import os, subprocess, shutil

VA      = os.path.expanduser("~/vision_assistant")
MAIN    = os.path.join(VA, "main.py")
WW      = os.path.join(VA, "wake_word.py")
REC_SRC = os.path.join(os.path.dirname(__file__), "echo_game_recorder.py")
REC_DST = os.path.join(VA, "echo_game_recorder.py")

# ── 1. COPY RECORDER ─────────────────────────────────────────────────────────
if not os.path.exists(REC_SRC):
    REC_SRC = os.path.expanduser("~/Downloads/echo_game_recorder.py")

if os.path.exists(REC_SRC) and REC_SRC != REC_DST:
    shutil.copy2(REC_SRC, REC_DST)
    print(f"OK: echo_game_recorder.py copied")
elif os.path.exists(REC_DST):
    print("OK: echo_game_recorder.py already in vision_assistant/")
else:
    print("WARN: echo_game_recorder.py not found — copy manually")

# ── 2. WIRE INTO main.py ─────────────────────────────────────────────────────
main_src = open(MAIN).read()

old_anchor = '''    # Push-to-talk
    try:
        from ptt import start_ptt
        start_ptt()
    except Exception as e:
        print(f"[main] PTT skipped: {e}")'''

new_anchor = '''    # Push-to-talk
    try:
        from ptt import start_ptt
        start_ptt()
    except Exception as e:
        print(f"[main] PTT skipped: {e}")

    # Game input recorder — auto-starts when Warframe launches
    try:
        from echo_game_recorder import start_game_recorder
        start_game_recorder()
    except Exception as e:
        print(f"[main] Game recorder skipped: {e}")'''

if "start_game_recorder" not in main_src:
    if old_anchor in main_src:
        main_src = main_src.replace(old_anchor, new_anchor)
        open(MAIN, "w").write(main_src)
        print("OK: game recorder wired into main.py")
    else:
        print("FAIL: anchor not found in main.py")
else:
    print("INFO: game recorder already in main.py")

# ── 3. ADD VOICE COMMANDS TO wake_word.py ────────────────────────────────────
ww_src = open(WW).read()

old_system = '''    # System status + cleanup
    if any(x in t for x in ["system status","how\'s the system","check system","cpu usage","ram usage","memory usage"]):'''

new_system = '''    # Game recorder queries
    if any(x in t for x in ["how do i play","my playstyle","game summary","how i play","warframe summary"]):
        def _playstyle():
            try:
                from echo_game_recorder import summarize_playstyle
                from voice import speak
                summary = summarize_playstyle()
                speak(summary)
                _notify(summary[:200])
            except Exception as e:
                print(f"[wake] playstyle error: {e}")
        import threading; threading.Thread(target=_playstyle, daemon=True).start(); return

    if any(x in t for x in ["game stats","last session","last game","session stats"]):
        def _game_stats():
            try:
                from echo_game_recorder import get_recent_sessions
                from voice import speak
                sessions = get_recent_sessions(1)
                if not sessions:
                    speak("No game sessions recorded yet.")
                    return
                s = sessions[0]
                msg = (f"Last session: {s.get('duration', 0):.0f} seconds, "
                       f"{s.get('events', 0)} inputs recorded, "
                       f"{s.get('focused', 0):.0f} seconds in focus.")
                speak(msg)
                _notify(msg)
            except Exception as e:
                print(f"[wake] game stats error: {e}")
        import threading; threading.Thread(target=_game_stats, daemon=True).start(); return

    # System status + cleanup
    if any(x in t for x in ["system status","how\'s the system","check system","cpu usage","ram usage","memory usage"]):'''

if "how do i play" not in ww_src:
    if old_system in ww_src:
        ww_src = ww_src.replace(old_system, new_system)
        open(WW, "w").write(ww_src)
        print("OK: game voice commands added to wake_word.py")
    else:
        print("FAIL: system status block not found in wake_word.py")
else:
    print("INFO: game voice commands already in wake_word.py")

# ── 4. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("echo_game_recorder.py", REC_DST), ("main.py", MAIN), ("wake_word.py", WW)]:
    if os.path.exists(path):
        r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
        print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
        if r.returncode != 0:
            print(r.stderr)

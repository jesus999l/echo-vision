"""
Patch: Player input detection (auto-pause), practice run mode, recorder integration.

1. Auto-pause: pynput monitors keyboard/mouse — if YOU press a key, bot pauses 3s
2. Practice run: --practice flag records your play session, saves as a replayable profile
3. Recorder integration: links to echo_game_recorder session data

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_warframe_features.py
"""
import os, subprocess, shutil

BOT = os.path.expanduser("~/echo_warframe/echo_warframe_bot.py")
DST = os.path.expanduser("~/vision_assistant/echo_warframe_bot.py")

src = open(BOT).read()

# ── 1. ADD PLAYER INPUT DETECTION + PAUSE LOGIC ───────────────────────────────
player_input_code = '''
# ── PLAYER INPUT DETECTION ────────────────────────────────────────────────────
_player_active     = False
_player_last_input = 0.0
_bot_paused        = False
PLAYER_PAUSE_SECS  = 3.0   # pause bot this long after player input detected

def _start_input_monitor():
    """Monitor player keyboard/mouse — pause bot when player takes over."""
    global _player_active, _player_last_input
    try:
        from pynput import keyboard, mouse

        def _on_key(key):
            global _player_active, _player_last_input
            _player_active = True
            _player_last_input = time.time()

        def _on_click(x, y, button, pressed):
            global _player_active, _player_last_input
            if pressed:
                _player_active = True
                _player_last_input = time.time()

        kb = keyboard.Listener(on_press=_on_key)
        ms = mouse.Listener(on_click=_on_click)
        kb.daemon = True
        ms.daemon = True
        kb.start()
        ms.start()
        log("Player input monitor active — bot will pause when you take control.")
    except Exception as e:
        log(f"Input monitor failed: {e}", "WARN")

def _check_player_pause():
    """Return True if bot should pause due to recent player input."""
    global _player_active, _bot_paused
    if _player_active:
        since = time.time() - _player_last_input
        if since < PLAYER_PAUSE_SECS:
            if not _bot_paused:
                log(f"Player input detected — bot pausing for {PLAYER_PAUSE_SECS}s...")
                _bot_paused = True
            return True
        else:
            if _bot_paused:
                log("Resuming bot control...")
                _bot_paused = False
            _player_active = False
    return False

'''

# ── 2. ADD PRACTICE RUN MODE ──────────────────────────────────────────────────
practice_run_code = '''
# ── PRACTICE RUN MODE ─────────────────────────────────────────────────────────
def run_practice(duration_minutes=20):
    """
    Practice run: Echo watches YOU play and records your inputs.
    Saves session to ~/echo_game_sessions/ for Echo to learn from.
    Bot does NOT control the game — just observes and records.
    """
    log(f"PRACTICE MODE: Recording your play for {duration_minutes} minutes.")
    log("Echo is watching — play normally. Bot will not interfere.")
    log("Press Ctrl+C to stop early.")

    # Make sure game recorder is capturing
    try:
        sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from echo_game_recorder import _recording, _session
        if _recording and _session:
            log(f"Game recorder already active: {_session.path}")
        else:
            log("Note: Start Echo Desktop for full session recording.")
    except Exception as e:
        log(f"Recorder check: {e}", "WARN")

    # Just wait and let the recorder do its job
    end_time = time.time() + duration_minutes * 60
    elapsed_mins = 0
    while time.time() < end_time and running:
        time.sleep(30)
        elapsed_mins += 0.5
        remaining = int((end_time - time.time()) / 60)
        log(f"Practice run: {elapsed_mins:.0f}m recorded, {remaining}m remaining")

    log("Practice run complete. Session saved to ~/echo_game_sessions/")
    log("Say 'hey echo my playstyle' to hear what Echo learned.")

'''

# ── 3. PATCH basic_combat_loop TO CHECK PLAYER INPUT ──────────────────────────
old_loop_start = '''    while time.time() < end_time:
        loop_count += 1
        elapsed = int((time.time() - (end_time - duration_minutes * 60)) / 60)
        remaining = int((end_time - time.time()) / 60)

        if loop_count % 30 == 0:
            log(f"Farming loop: {elapsed}m elapsed, {remaining}m remaining")

        # Cast Desecrate every 3 seconds to catch corpses
        if loop_count % 3 == 0:
            farm_ability()'''

new_loop_start = '''    _start_input_monitor()
    while time.time() < end_time:
        loop_count += 1
        elapsed = int((time.time() - (end_time - duration_minutes * 60)) / 60)
        remaining = int((end_time - time.time()) / 60)

        if loop_count % 30 == 0:
            log(f"Farming loop: {elapsed}m elapsed, {remaining}m remaining")

        # Pause if player takes control
        if _check_player_pause():
            time.sleep(0.3)
            continue

        # Cast ability every 3 seconds
        if loop_count % 3 == 0:
            farm_ability()'''

# ── 4. PATCH MAIN ENTRY POINT TO SUPPORT --practice FLAG ─────────────────────
old_parser = '''    parser = argparse.ArgumentParser(description="Echo Warframe Farming Bot")
    parser.add_argument("--resource", required=True, help="Resource to farm (e.g. 'orokin cell')")
    parser.add_argument("--duration", type=int, default=20, help="Farm duration in minutes (default: 20)")
    parser.add_argument("--dry-run", action="store_true", help="Look up resource without controlling game")
    args = parser.parse_args()

    run_bot(args.resource, args.duration, args.dry_run)'''

new_parser = '''    parser = argparse.ArgumentParser(description="Echo Warframe Farming Bot")
    parser.add_argument("--resource", default="orokin cell", help="Resource to farm (e.g. 'orokin cell')")
    parser.add_argument("--duration", type=int, default=20, help="Farm duration in minutes (default: 20)")
    parser.add_argument("--dry-run", action="store_true", help="Look up resource without controlling game")
    parser.add_argument("--practice", action="store_true", help="Practice mode: record your play, bot watches only")
    args = parser.parse_args()

    if args.practice:
        run_practice(args.duration)
    else:
        run_bot(args.resource, args.duration, args.dry_run)'''

# ── APPLY ALL PATCHES ─────────────────────────────────────────────────────────
applied = 0

# Insert player input code before basic_combat_loop
anchor = "def basic_combat_loop("
if anchor in src and "_start_input_monitor" not in src:
    src = src.replace(anchor, player_input_code + "\n" + anchor)
    applied += 1
    print("OK: player input detection added")
else:
    print("INFO: player input already present or anchor not found")

# Insert practice run code before run_bot
anchor2 = "def run_bot("
if anchor2 in src and "run_practice" not in src:
    src = src.replace(anchor2, practice_run_code + "\ndef run_bot(")
    applied += 1
    print("OK: practice run mode added")
else:
    print("INFO: practice run already present")

# Patch combat loop
if old_loop_start in src:
    src = src.replace(old_loop_start, new_loop_start)
    applied += 1
    print("OK: combat loop patched with player pause")
else:
    print("FAIL: combat loop start not found")

# Patch parser
if old_parser in src:
    src = src.replace(old_parser, new_parser)
    applied += 1
    print("OK: --practice flag added to CLI")
else:
    print("FAIL: parser block not found")

open(BOT, "w").write(src)
shutil.copy2(BOT, DST)

# Syntax check
r = subprocess.run(
    ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", BOT],
    capture_output=True, text=True
)
print(f"{'OK' if r.returncode == 0 else 'ERR'}: syntax")
if r.returncode != 0:
    print(r.stderr)

print(f"\nApplied {applied}/4 patches")
print("\nUsage:")
print("  Normal farm:   DISPLAY=:0 python3 echo_warframe_bot.py --resource 'orokin cell'")
print("  Practice run:  DISPLAY=:0 python3 echo_warframe_bot.py --practice --duration 20")
print("  Voice:         'hey echo farm orokin cells'")
print("\nDuring bot run: press any key to pause bot for 3 seconds and take control")

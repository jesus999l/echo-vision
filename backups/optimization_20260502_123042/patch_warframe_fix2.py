"""
Patch: Fix bot self-pause + ability timing + state detection + desktop launcher.

1. Bot inputs no longer trigger player-pause (only YOUR inputs pause it)
2. Tentacle Swarm cast by real time, not loop count
3. State detection improved — orbiter check requires text confirmation
4. Creates ~/warframe-bot.sh desktop launcher so you don't need terminal

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_warframe_fix2.py
"""
import os, subprocess, shutil

BOT  = os.path.expanduser("~/echo_warframe/echo_warframe_bot.py")
DST  = os.path.expanduser("~/vision_assistant/echo_warframe_bot.py")

src = open(BOT).read()
applied = 0

# ── 1. FIX PLAYER INPUT DETECTION — ignore bot's own keypresses ──────────────
old_monitor = '''def _start_input_monitor():
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
                _player_last_input = time.time()'''

new_monitor = '''_bot_typing = False   # set True while bot is sending inputs

def _start_input_monitor():
    """Monitor player keyboard/mouse — pause bot when player takes over.
    Ignores inputs while _bot_typing is True (bot's own keypresses)."""
    global _player_active, _player_last_input
    try:
        from pynput import keyboard, mouse

        def _on_key(key):
            global _player_active, _player_last_input
            if _bot_typing:
                return  # ignore bot's own inputs
            _player_active = True
            _player_last_input = time.time()

        def _on_click(x, y, button, pressed):
            global _player_active, _player_last_input
            if _bot_typing:
                return
            if pressed:
                _player_active = True
                _player_last_input = time.time()'''

if old_monitor in src:
    src = src.replace(old_monitor, new_monitor)
    applied += 1
    print("OK: player input monitor fixed — ignores bot keypresses")
else:
    print("FAIL: monitor block not found")

# ── 2. WRAP ALL BOT INPUT FUNCTIONS WITH _bot_typing FLAG ────────────────────
old_key = '''def key(k, delay=0.1):
    """Press a key in Warframe window"""
    wid = get_warframe_window_id()
    if wid:
        subprocess.run(
            ["xdotool", "key", "--window", wid, k],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
        )
        time.sleep(delay)'''

new_key = '''def key(k, delay=0.1):
    """Press a key in Warframe window"""
    global _bot_typing
    wid = get_warframe_window_id()
    if wid:
        _bot_typing = True
        subprocess.run(
            ["xdotool", "key", "--window", wid, k],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
        )
        time.sleep(delay)
        _bot_typing = False'''

if old_key in src:
    src = src.replace(old_key, new_key)
    applied += 1
    print("OK: key() wrapped with _bot_typing flag")
else:
    print("FAIL: key() not found")

# ── 3. FIX COMBAT LOOP — use real time for ability, not loop count ────────────
old_ability_line = '''        # ── YOUR PLAY STYLE (learned from practice sessions) ──────────────
        # Tentacle Swarm every 30-35 seconds
        if loop_count % 110 == 0:   # ~33s at 0.3s per tick
            farm_ability()
            log("Cast Tentacle Swarm")'''

new_ability_line = '''        # ── YOUR PLAY STYLE (learned from practice sessions) ──────────────
        # Tentacle Swarm every 32 seconds (real time, not loop count)
        if time.time() - _last_ability_cast >= 32:
            farm_ability()
            _last_ability_cast = time.time()
            log("Cast Tentacle Swarm")'''

if old_ability_line in src:
    src = src.replace(old_ability_line, new_ability_line)
    applied += 1
    print("OK: Tentacle Swarm now uses real-time 32s interval")
else:
    print("FAIL: ability line not found")

# Add _last_ability_cast init before the while loop
old_loop_init = '''    _start_input_monitor()
    while time.time() < end_time:'''
new_loop_init = '''    _start_input_monitor()
    _last_ability_cast = time.time() - 30  # cast immediately on first tick
    while time.time() < end_time:'''

if old_loop_init in src:
    src = src.replace(old_loop_init, new_loop_init)
    applied += 1
    print("OK: ability timer initialized")
else:
    print("FAIL: loop init not found")

# ── 4. FIX STATE DETECTION — orbiter needs text confirmation ─────────────────
old_state_orbiter = '''            wt = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True,
                env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}).stdout.lower()
            state = "in_mission" if "warframe" not in wt else "orbiter"
        else:
            state = "orbiter"'''

new_state_orbiter = '''            # Default to in_mission when text is empty — orbiter always has some UI text
            state = "in_mission"
        else:
            # Has some text but not clear keywords — assume orbiter
            state = "orbiter"'''

if old_state_orbiter in src:
    src = src.replace(old_state_orbiter, new_state_orbiter)
    applied += 1
    print("OK: state detection fixed — empty OCR = in_mission")
else:
    print("FAIL: state detection block not found")

# ── 5. WRAP keydown/keyup WITH _bot_typing FLAG ───────────────────────────────
# Find all keydown/keyup subprocess calls and wrap them
old_keydown_block = '''        subprocess.run(
            ["xdotool", "keydown", "w"],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
            capture_output=True
        )
        time.sleep(0.6)
        subprocess.run(
            ["xdotool", "keyup", "w"],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
            capture_output=True
        )'''

new_keydown_block = '''        global _bot_typing
        _bot_typing = True
        subprocess.run(
            ["xdotool", "keydown", "w"],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
            capture_output=True
        )
        time.sleep(0.6)
        subprocess.run(
            ["xdotool", "keyup", "w"],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
            capture_output=True
        )
        _bot_typing = False'''

if old_keydown_block in src:
    src = src.replace(old_keydown_block, new_keydown_block)
    applied += 1
    print("OK: keydown/keyup wrapped with _bot_typing flag")
else:
    print("FAIL: keydown block not found")

open(BOT, "w").write(src)
shutil.copy2(BOT, DST)

# ── 6. CREATE DESKTOP LAUNCHER ────────────────────────────────────────────────
launcher_sh = """\
#!/usr/bin/env bash
# Warframe Bot Launcher — run without terminal
RESOURCE="${1:-orokin cell}"
DURATION="${2:-20}"
DISPLAY=:0 /home/jesus999l/vision_env/bin/python3 /home/jesus999l/echo_warframe/echo_warframe_bot.py \\
    --resource "$RESOURCE" --duration "$DURATION" &
notify-send "Echo Warframe Bot" "Farming $RESOURCE for ${DURATION}m" -i applications-games
"""
launcher_path = os.path.expanduser("~/warframe-bot.sh")
open(launcher_path, "w").write(launcher_sh)
os.chmod(launcher_path, 0o755)
print(f"OK: {launcher_path} created")

# Desktop .desktop file
desktop_content = """\
[Desktop Entry]
Type=Application
Name=Farm Orokin Cells
Comment=Run Warframe farming bot
Exec=bash /home/jesus999l/warframe-bot.sh "orokin cell" 20
Icon=applications-games
Terminal=false
Categories=Game;
"""
desktop_path = os.path.expanduser("~/Desktop/Farm Orokin Cells.desktop")
open(desktop_path, "w").write(desktop_content)
os.chmod(desktop_path, 0o755)
subprocess.run(["gio", "set", desktop_path, "metadata::trusted", "true"], capture_output=True)
print(f"OK: Desktop launcher created")

# Syntax check
r = subprocess.run(
    ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", BOT],
    capture_output=True, text=True
)
print(f"{'OK' if r.returncode == 0 else 'ERR'}: syntax")
if r.returncode != 0: print(r.stderr)
print(f"\nApplied {applied}/6 patches")
print("\nNow:")
print("  - Bot won't pause itself from its own keypresses")
print("  - Tentacle Swarm cast every 32 seconds (real time)")
print("  - Empty OCR = in_mission (no more false orbiter detection)")
print("  - Desktop icon: 'Farm Orokin Cells' — no terminal needed")
print("  - Voice: 'hey echo farm orokin cells'")

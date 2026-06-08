#!/usr/bin/env python3
"""
Echo Warframe Bot - Resource Farming Core
Handles: launching Warframe, detecting game state, navigating to missions,
and farming resources using vision + xdotool input automation.

Usage:
    python3 echo_warframe_bot.py --resource "orokin cell"
    python3 echo_warframe_bot.py --resource "neurodes" --duration 20
"""

import subprocess
import time
import json
import os
import sys
import argparse
import signal
from datetime import datetime

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
KB_FILE = os.path.expanduser("~/echo_warframe/warframe_parsed_kb.json")
LOG_FILE = os.path.expanduser("~/echo_warframe/bot_log.txt")
SCREENSHOT_DIR = os.path.expanduser("~/echo_warframe/screenshots")
WARFRAME_DISPLAY = ":0"       # Desktop 2 (your gaming desktop)
WARFRAME_PROCESS = "Warframe"
STEAM_CMD = "steam steam://rungameid/230410"  # Warframe Steam ID
OLLAMA_MODEL = "moondream:latest"   # vision model for screen reading
DEFAULT_FARM_NODE = "Gabii"  # Best Orokin Cell farm — Dark Sector Survival, Ceres
OLLAMA_URL = "http://localhost:11434/api/generate"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ── ESCAPE MENU COORDINATES (1920x1080) ──────────────────────────────────────
# These are the clickable menu items in the Escape/pause menu
MENU_NAVIGATION   = (275, 263)
MENU_EQUIPMENT    = (275, 381)
MENU_OPERATOR     = (270, 420)
MENU_MARKET       = (230, 461)
MENU_COMMUNICATION= (315, 499)
MENU_QUESTS       = (255, 539)
MENU_RAILJACK     = (270, 578)
MENU_PROFILE      = (260, 617)
MENU_OPTIONS      = (265, 656)
MENU_EXIT_GAME    = (310, 695)


# ── ESCAPE MENU COORDINATES (1920x1080) ──────────────────────────────────────
# These are the clickable menu items in the Escape/pause menu
MENU_NAVIGATION   = (275, 263)
MENU_EQUIPMENT    = (275, 381)
MENU_OPERATOR     = (270, 420)
MENU_MARKET       = (230, 461)
MENU_COMMUNICATION= (315, 499)
MENU_QUESTS       = (255, 539)
MENU_RAILJACK     = (270, 578)
MENU_PROFILE      = (260, 617)
MENU_OPTIONS      = (265, 656)
MENU_EXIT_GAME    = (310, 695)


# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────
def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ─────────────────────────────────────────
# KNOWLEDGE BASE
# ─────────────────────────────────────────
def load_kb():
    if not os.path.exists(KB_FILE):
        log("KB file not found. Run warframe_parser.py first.", "ERROR")
        sys.exit(1)
    with open(KB_FILE) as f:
        return json.load(f)

def lookup_resource(kb, resource_name):
    """Find best farm location for a resource"""
    query_index = kb.get("echo_query_index", {})
    aliases = query_index.get("aliases", {})
    best_farms = query_index.get("best_farms", {})

    # Normalize input
    name = resource_name.lower().strip()

    # Check aliases
    if name in aliases:
        name = aliases[name]

    # Check hardcoded best farms first (most accurate)
    if name in best_farms:
        farm = best_farms[name]
        log(f"Resource: {name}")
        log(f"Best mission: {farm['mission']}")
        log(f"Faction: {farm['faction']}")
        log(f"Tip: {farm['tip']}")
        return farm

    # Fall back to parsed drop data
    resource_locs = kb.get("resource_locations", {})
    if name in resource_locs:
        top = resource_locs[name][:3]
        log(f"Resource: {name} - top drop locations:")
        for loc in top:
            log(f"  {loc['planet']} - {loc['node']} ({loc['mission_type']}) {loc['chance']:.1f}%")
        return {"mission": f"{top[0]['node']}, {top[0]['planet']}", "tip": "From drop data"}

    log(f"Resource '{resource_name}' not found in KB.", "WARN")
    return None

# ─────────────────────────────────────────
# PROCESS / WINDOW MANAGEMENT
# ─────────────────────────────────────────
def is_warframe_running():
    result = subprocess.run(
        ["pgrep", "-f", "Warframe.x64.exe"],
        capture_output=True, text=True
    )
    return bool(result.stdout.strip())

def launch_warframe():
    log("Warframe not running. Launching via Steam...")
    subprocess.Popen(
        STEAM_CMD.split(),
        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
    )
    log("Waiting for Warframe to launch (up to 8 minutes)...")
    # Poll every 10s for up to 8 minutes
    for i in range(48):
        time.sleep(10)
        if is_warframe_running():
            log(f"Warframe process detected after {(i+1)*10}s.")
            log("Waiting 60s for game to fully load...")
            time.sleep(60)
            return True
        if i % 6 == 0 and i > 0:
            log(f"Still waiting... ({i*10}s elapsed)")
    log("Warframe failed to launch in time.", "ERROR")
    return False

def get_warframe_window_id():
    result = subprocess.run(
        ["xdotool", "search", "--name", "Warframe"],
        capture_output=True, text=True,
        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
    )
    ids = result.stdout.strip().split()
    if ids:
        return ids[-1]  # last match is usually the game window
    return None

def focus_warframe():
    wid = get_warframe_window_id()
    if wid:
        subprocess.run(
            ["xdotool", "windowfocus", "--sync", wid],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
        )
        time.sleep(0.5)
        return True
    log("Could not find Warframe window.", "WARN")
    return False

# ─────────────────────────────────────────
# INPUT AUTOMATION
# ─────────────────────────────────────────
def key(k, delay=0.1):
    """Press a key in Warframe window"""
    wid = get_warframe_window_id()
    if wid:
        subprocess.run(
            ["xdotool", "key", "--window", wid, k],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
        )
        time.sleep(delay)

def click(x, y, delay=0.3):
    """Click at screen coordinates in Warframe window"""
    wid = get_warframe_window_id()
    if wid:
        subprocess.run(
            ["xdotool", "mousemove", "--window", wid, str(x), str(y)],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
        )
        time.sleep(0.1)
        subprocess.run(
            ["xdotool", "click", "--window", wid, "1"],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
        )
        time.sleep(delay)

def type_text(text, delay=0.05):
    """Type text into Warframe"""
    wid = get_warframe_window_id()
    if wid:
        subprocess.run(
            ["xdotool", "type", "--window", wid, "--delay", str(int(delay*1000)), text],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}
        )

# ─────────────────────────────────────────
# SCREEN CAPTURE + VISION
# ─────────────────────────────────────────
def screenshot(name="screen"):
    path = os.path.join(SCREENSHOT_DIR, f"{name}_{int(time.time())}.png")
    subprocess.run(
        ["scrot", "-D", WARFRAME_DISPLAY, path],
        capture_output=True
    )
    return path

def ask_vision(image_path, question):
    """Ask moondream what's on screen — resizes image first for speed."""
    import base64, urllib.request
    if not os.path.exists(image_path):
        return "no image"
    # Resize to 640x360 before sending — moondream is much faster on small images
    resized = image_path + "_small.jpg"
    try:
        subprocess.run(["convert", image_path, "-resize", "640x360", resized],
                       capture_output=True, timeout=5)
        src_path = resized if os.path.exists(resized) else image_path
    except:
        src_path = image_path
    with open(src_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    try:
        if os.path.exists(resized): os.unlink(resized)
    except: pass
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": question,
        "images": [img_b64],
        "stream": False
    }).encode()
    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("response", "").strip()
    except Exception as e:
        log(f"Vision query failed: {e}", "WARN")
        return "error"

def detect_game_state():
    """Detect game state via OCR on Warframe window — fast and reliable."""
    import tempfile
    env = {**os.environ, "DISPLAY": WARFRAME_DISPLAY}
    # Get window ID
    r = subprocess.run(["xdotool", "search", "--name", "Warframe"],
        capture_output=True, text=True, env=env)
    wid = r.stdout.strip().split()[-1] if r.stdout.strip() else None
    if not wid:
        log("Warframe window not found for state detection", "WARN")
        return "unknown"
    tmp = tempfile.mktemp(suffix=".png")
    crop = tempfile.mktemp(suffix=".png")
    try:
        subprocess.run(["import", "-window", wid, tmp],
            capture_output=True, env=env)
        subprocess.run(["convert", tmp, "-crop", "800x200+560+0", "+repage", crop],
            capture_output=True)
        try:
            import pytesseract
            sys.path.insert(0, os.path.expanduser("~/vision_env/lib/python3.12/site-packages"))
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(crop)).lower().strip()
        except Exception as e:
            log(f"OCR failed: {e}", "WARN")
            text = ""
        if any(x in text for x in ["navigation", "star chart", "solar system", "select mission"]):
            state = "navigation"
        elif any(x in text for x in ["mission complete", "mission failed", "extract now"]):
            state = "mission_complete"
        elif any(x in text for x in ["loading", "please wait"]):
            state = "loading"
        elif any(x in text for x in ["login", "username", "password", "sign in"]):
            state = "login_screen"
        elif any(x in text for x in ["orbiter", "navigation console", "arsenal"]):
            state = "orbiter"
        elif len(text.strip()) < 10:
            # Take second screenshot to confirm — orbiter has 3D elements
            # If Warframe window exists but no HUD text, could be either
            # Use window title as tiebreaker
            wt = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True,
                env={**os.environ, "DISPLAY": WARFRAME_DISPLAY}).stdout.lower()
            state = "in_mission" if "warframe" not in wt else "orbiter"
        else:
            state = "orbiter"
        log(f"Detected game state: {state} (ocr: {repr(text[:60])})")
        return state
    finally:
        for f in [tmp, crop]:
            try: os.unlink(f)
            except: pass

# ─────────────────────────────────────────
# GAME NAVIGATION
# ─────────────────────────────────────────

def open_escape_menu():
    """Open the Escape menu."""
    key("Escape")
    time.sleep(0.8)

def close_escape_menu():
    """Close the Escape menu."""
    key("Escape")
    time.sleep(0.5)

def menu_click(coords, label=""):
    """Click an Escape menu item by coordinates."""
    wid = get_warframe_window_id()
    if not wid:
        log("Cannot click menu — Warframe window not found", "WARN")
        return False
    env = {**os.environ, "DISPLAY": WARFRAME_DISPLAY}
    # Get window position to calculate absolute coords
    geo = subprocess.run(
        ["xdotool", "getwindowgeometry", wid],
        capture_output=True, text=True, env=env
    ).stdout
    # Parse position
    import re
    pos_match = re.search(r"Position: (\d+),(\d+)", geo)
    if pos_match:
        win_x = int(pos_match.group(1))
        win_y = int(pos_match.group(2))
    else:
        win_x = win_y = 0
    abs_x = win_x + coords[0]
    abs_y = win_y + coords[1]
    subprocess.run(["xdotool", "mousemove", str(abs_x), str(abs_y)],
                   env=env, capture_output=True)
    time.sleep(0.2)
    subprocess.run(["xdotool", "click", "1"], env=env, capture_output=True)
    if label:
        log(f"Clicked menu: {label}")
    time.sleep(0.5)
    return True

def navigate_via_menu():
    """Open fast travel radial menu (Q) and click Navigation."""
    log("Opening fast travel menu (Q) → Navigation...")
    key("q")
    time.sleep(0.8)
    menu_click(MENU_NAVIGATION, "Navigation")
    time.sleep(2.0)

def open_equipment_via_menu():
    """Open Escape menu and click Equipment/Arsenal."""
    log("Opening Escape menu → Equipment...")
    open_escape_menu()
    time.sleep(0.5)
    menu_click(MENU_EQUIPMENT, "Equipment")
    time.sleep(2.0)

def search_node_in_navigation(node_name):
    """Type node name in navigation search box."""
    log(f"Searching for: {node_name}")
    # Ctrl+F opens search in star chart
    key("ctrl+f")
    time.sleep(0.5)
    type_text(node_name)
    time.sleep(1.5)
    key("Return")
    time.sleep(1.0)

def navigate_to_star_chart():
    """Open navigation via Escape menu — reliable from any state."""
    navigate_via_menu()

def search_mission_node(node_name):
    """Search for mission node in navigation."""
    search_node_in_navigation(node_name)

def start_mission_solo():
    """Click solo play and start mission"""
    log("Starting mission solo...")
    key("Return")  # confirm mission
    time.sleep(1)
    # Solo button - position varies by resolution, using keyboard nav
    key("Tab")
    time.sleep(0.3)
    key("Return")
    time.sleep(3)

# ─────────────────────────────────────────
# IN-MISSION BEHAVIOR (Nekros)
# ─────────────────────────────────────────

# Key bindings (adjust to match your setup)
ABILITY_3 = "3"       # Ability 3 (kept for compatibility)
ABILITY_4 = "4"       # Hydroid Tentacle Swarm / Nekros Terrify
SPRINT = "shift"
JUMP = "space"
MELEE = "e"
FIRE = "mouse1"
RELOAD = "r"
LOOT = "x"
ROLL = "v"            # dodge/roll

def nekros_desecrate():
    """Cast Desecrate to loot corpses (Nekros)"""
    key(ABILITY_3, delay=0.2)

def hydroid_pilfering_swarm():
    """Cast Tentacle Swarm with Pilfering augment (Hydroid)"""
    key(ABILITY_4, delay=0.2)

def nekros_terrify():
    """Cast Terrify to reduce armor"""
    key(ABILITY_4, delay=0.2)

# Primary farming ability — switch based on frame
def farm_ability():
    hydroid_pilfering_swarm()

def pickup_loot():
    """Press loot key"""
    key(LOOT, delay=0.1)


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


def basic_combat_loop(duration_minutes=20):
    """
    Basic farming loop for Nekros:
    - Move around
    - Kill enemies
    - Cast Desecrate on corpses
    - Collect loot
    - Repeat
    """
    log(f"Starting Nekros farming loop ({duration_minutes} min)...")
    end_time = time.time() + (duration_minutes * 60)
    loop_count = 0

    _start_input_monitor()
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
            farm_ability()

        # Move around to find enemies (basic WASD pattern)
        # Move forward
        subprocess.run(
            ["xdotool", "keydown", "w"],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
            capture_output=True
        )
        time.sleep(0.8)
        subprocess.run(
            ["xdotool", "keyup", "w"],
            env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
            capture_output=True
        )

        # Randomly strafe
        if loop_count % 5 == 0:
            direction = "a" if loop_count % 10 < 5 else "d"
            subprocess.run(
                ["xdotool", "keydown", direction],
                env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
                capture_output=True
            )
            time.sleep(0.4)
            subprocess.run(
                ["xdotool", "keyup", direction],
                env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
                capture_output=True
            )

        # Melee attack nearby enemies
        if loop_count % 2 == 0:
            key(MELEE, delay=0.1)

        # Pickup loot
        pickup_loot()

        time.sleep(0.3)

        # Every 60 seconds, take a screenshot and check state
        if loop_count % 200 == 0:
            state = detect_game_state()
            if state in ["mission_complete", "orbiter", "main_menu"]:
                log(f"Mission ended or state changed: {state}")
                break
            if state == "in_mission":
                log("Still in mission, continuing...")

    log("Farming loop ended.")

# ─────────────────────────────────────────
# EXTRACTION
# ─────────────────────────────────────────
def extract_from_mission():
    """Navigate to extraction point"""
    log("Heading to extraction...")
    # Press M to open minimap/waypoint, or use waypoint key
    key("m")
    time.sleep(0.5)
    # Sprint toward extraction
    subprocess.run(
        ["xdotool", "keydown", "shift"],
        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
        capture_output=True
    )
    subprocess.run(
        ["xdotool", "keydown", "w"],
        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
        capture_output=True
    )
    time.sleep(5)
    subprocess.run(
        ["xdotool", "keyup", "w"],
        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
        capture_output=True
    )
    subprocess.run(
        ["xdotool", "keyup", "shift"],
        env={**os.environ, "DISPLAY": WARFRAME_DISPLAY},
        capture_output=True
    )

# ─────────────────────────────────────────
# SAFETY STOP
# ─────────────────────────────────────────
running = True

def signal_handler(sig, frame):
    global running
    log("Stop signal received. Halting bot safely...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ─────────────────────────────────────────
# MAIN BOT FLOW
# ─────────────────────────────────────────

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


def run_bot(resource_name, duration_minutes=20, dry_run=False):
    log(f"Echo Warframe Bot starting - Target: {resource_name}")

    # 1. Load KB and look up resource
    kb = load_kb()
    farm_info = lookup_resource(kb, resource_name)
    if not farm_info:
        log(f"Could not find farm location for: {resource_name}", "ERROR")
        return

    log(f"Farm plan: {farm_info.get('mission', 'Unknown')}")
    log(f"Tip: {farm_info.get('tip', '')}")

    if dry_run:
        log("[DRY RUN] Would navigate to mission and farm. Exiting.")
        return

    # 2. Check if Warframe is running
    if not is_warframe_running():
        success = launch_warframe()
        if not success:
            log("Could not launch Warframe.", "ERROR")
            return
    else:
        log("Warframe is already running.")

    # 3. Focus the window
    if not focus_warframe():
        log("Could not focus Warframe window.", "ERROR")
        return

    time.sleep(1)

    # 4. Detect current state
    state = detect_game_state()

    # 5. Navigate based on state
    if state in ["orbiter", "main_menu"]:
        navigate_to_star_chart()
        time.sleep(2)
        mission = farm_info.get("mission", "")
        if mission:
            # Extract just the node name
            node = mission.split(",")[0].strip()
            search_mission_node(node)
            time.sleep(1)

    elif state == "in_mission":
        log("Already in a mission. Starting farm loop...")

    elif state == "login_screen":
        log("Warframe is at login screen. Manual login required.", "WARN")
        return

    else:
        log(f"Unexpected state: {state}. Attempting to navigate anyway...")
        navigate_to_star_chart()
        time.sleep(2)

    # 6. Farm loop
    if not running:
        return

    log(f"Starting farm for {resource_name} - {duration_minutes} minutes")
    basic_combat_loop(duration_minutes)

    # 7. Extract
    extract_from_mission()
    time.sleep(10)

    log(f"Farming session complete. Check your inventory for {resource_name}.")

# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Echo Warframe Farming Bot")
    parser.add_argument("--resource", default="orokin cell", help="Resource to farm (e.g. 'orokin cell')")
    parser.add_argument("--duration", type=int, default=20, help="Farm duration in minutes (default: 20)")
    parser.add_argument("--dry-run", action="store_true", help="Look up resource without controlling game")
    parser.add_argument("--practice", action="store_true", help="Practice mode: record your play, bot watches only")
    args = parser.parse_args()

    if args.practice:
        run_practice(args.duration)
    else:
        run_bot(args.resource, args.duration, args.dry_run)

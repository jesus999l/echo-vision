"""
Patch: Replace physical orbiter navigation with Escape menu clicks.
Uses the Escape menu (always accessible) to navigate to Navigation, Equipment, etc.
Coordinates mapped from 1920x1080 screenshot.

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_warframe_menu.py
"""
import os, subprocess, shutil

BOT = os.path.expanduser("~/echo_warframe/echo_warframe_bot.py")
DST = os.path.expanduser("~/vision_assistant/echo_warframe_bot.py")

src = open(BOT).read()

# ── MENU COORDINATES (1920x1080) ──────────────────────────────────────────────
# Mapped from screenshot — Escape menu left side
MENU_COORDS = """
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
"""

# ── NEW NAVIGATION FUNCTIONS ──────────────────────────────────────────────────
new_nav_functions = '''
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
    pos_match = re.search(r"Position: (\\d+),(\\d+)", geo)
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
    """Open Escape menu and click Navigation."""
    log("Opening Escape menu → Navigation...")
    open_escape_menu()
    time.sleep(0.5)
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
'''

# ── REPLACE OLD navigate_to_star_chart ────────────────────────────────────────
old_nav = '''def navigate_to_star_chart():
    """From orbiter, open the navigation/star chart"""
    log("Opening navigation...")
    key("Escape")  # close any open menus
    time.sleep(0.5)
    # Navigation is usually bound to 'M' or clicking the nav console
    key("m")
    time.sleep(2)

def search_mission_node(node_name):
    """Search for a specific mission node in navigation"""
    log(f"Searching for mission node: {node_name}")
    # Most Warframe UI has a search bar in navigation
    # Use Ctrl+F or just type to search
    type_text(node_name)
    time.sleep(1)'''

new_nav = '''def navigate_to_star_chart():
    """Open navigation via Escape menu — reliable from any state."""
    navigate_via_menu()

def search_mission_node(node_name):
    """Search for mission node in navigation."""
    search_node_in_navigation(node_name)'''

# ── APPLY PATCHES ─────────────────────────────────────────────────────────────
applied = 0

# Add menu coords after CONFIG section
old_config_end = 'os.makedirs(SCREENSHOT_DIR, exist_ok=True)'
new_config_end = f'os.makedirs(SCREENSHOT_DIR, exist_ok=True)\n{MENU_COORDS}'
if old_config_end in src:
    src = src.replace(old_config_end, new_config_end)
    applied += 1
    print("OK: menu coordinates added")
else:
    print("FAIL: config end not found")

# Add new navigation functions before old ones
if old_nav in src:
    src = src.replace(old_nav, new_nav_functions + "\n" + new_nav)
    applied += 1
    print("OK: menu navigation functions added")
else:
    print("FAIL: old navigation block not found")

open(BOT, "w").write(src)
shutil.copy2(BOT, DST)

# Syntax check
py = "/home/jesus999l/vision_env/bin/python3"
r = subprocess.run([py, "-m", "py_compile", BOT], capture_output=True, text=True)
print(f"{'OK' if r.returncode == 0 else 'ERR'}: syntax check")
if r.returncode != 0:
    print(r.stderr)

print(f"\nApplied {applied}/2 patches")
print("Bot now uses Escape menu for navigation instead of physical movement")
print("Test: DISPLAY=:0 python3 ~/echo_warframe/echo_warframe_bot.py --resource 'orokin cell' --dry-run")

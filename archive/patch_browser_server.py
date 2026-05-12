"""
Patch: Wire echo_browser_server.py into Echo Desktop main.py.
Also installs lz4 for Firefox session reading.

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_browser_server.py
"""
import os, subprocess, shutil

VA   = os.path.expanduser("~/vision_assistant")
MAIN = os.path.join(VA, "main.py")
SRV  = os.path.join(VA, "echo_browser_server.py")
SRC  = os.path.join(os.path.dirname(__file__), "echo_browser_server.py")

# ── 1. COPY SERVER ────────────────────────────────────────────────────────────
if not os.path.exists(SRC):
    SRC = os.path.expanduser("~/Downloads/echo_browser_server.py")
if os.path.exists(SRC) and SRC != SRV:
    shutil.copy2(SRC, SRV)
    print("OK: echo_browser_server.py copied")
elif os.path.exists(SRV):
    print("OK: echo_browser_server.py already in vision_assistant/")

# ── 2. INSTALL lz4 FOR FIREFOX SESSION READING ───────────────────────────────
r = subprocess.run(
    ["/home/jesus999l/vision_env/bin/python3", "-c", "import lz4"],
    capture_output=True
)
if r.returncode != 0:
    print("INFO: installing lz4...")
    subprocess.run(
        ["/home/jesus999l/vision_env/bin/pip", "install", "lz4", "--quiet"],
        check=False
    )
    print("OK: lz4 installed")
else:
    print("OK: lz4 available")

# ── 3. WIRE INTO main.py ──────────────────────────────────────────────────────
main_src = open(MAIN).read()

old_anchor = '''    # Game input recorder — auto-starts when Warframe launches
    try:
        from echo_game_recorder import start_game_recorder
        start_game_recorder()
    except Exception as e:
        print(f"[main] Game recorder skipped: {e}")'''

new_anchor = '''    # Game input recorder — auto-starts when Warframe launches
    try:
        from echo_game_recorder import start_game_recorder
        start_game_recorder()
    except Exception as e:
        print(f"[main] Game recorder skipped: {e}")

    # Browser server — Echo Firefox sidebar
    try:
        from echo_browser_server import start_browser_server
        start_browser_server()
    except Exception as e:
        print(f"[main] Browser server skipped: {e}")'''

if "start_browser_server" not in main_src:
    if old_anchor in main_src:
        main_src = main_src.replace(old_anchor, new_anchor)
        open(MAIN, "w").write(main_src)
        print("OK: browser server wired into main.py")
    else:
        print("FAIL: anchor not found in main.py")
else:
    print("INFO: browser server already in main.py")

# ── 4. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("echo_browser_server.py", SRV), ("main.py", MAIN)]:
    r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
    print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
    if r.returncode != 0:
        print(r.stderr)

# ── 5. QUICK TEST ─────────────────────────────────────────────────────────────
print("\nTesting Firefox data access...")
r = subprocess.run([py, "-c", """
import sys
sys.path.insert(0, '/home/jesus999l/vision_assistant')
from echo_browser_server import get_recent_bookmarks, get_interests
bm = get_recent_bookmarks(3)
print(f"Bookmarks found: {len(bm)}")
if bm: print(f"  Latest: {bm[0].get('title','?')[:50]}")
p = get_interests()
print(f"Top topics: {[t[0] for t in p.get('top_topics',[])[:5]]}")
"""], capture_output=True, text=True)
print(r.stdout.strip())
if r.returncode != 0:
    print(r.stderr[:300])

print("""
Done. Next steps:
1. Copy echo_sidebar.user.js to your machine
2. Open Tampermonkey dashboard in Firefox
3. Click 'Create new script'
4. Paste the contents of echo_sidebar.user.js
5. Save (Ctrl+S)
6. Restart Echo Desktop
7. Look for 'ECHO' tab on the right side of every page
""")

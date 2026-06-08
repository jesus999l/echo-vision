"""
Patch: Wire text_selector.py into xbindkeys hotkey + wake_word.py voice command.
- Hotkey: Ctrl+Alt+T → launches text selector
- Voice: "select text" / "read screen" / "copy text" → launches text selector

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_text_selector.py
"""
import os, subprocess, shutil

VA      = os.path.expanduser("~/vision_assistant")
WW      = os.path.join(VA, "wake_word.py")
XBKEYS  = os.path.expanduser("~/.xbindkeysrc")
SEL_SRC = os.path.join(VA, "text_selector.py")

# ── 1. COPY text_selector.py INTO vision_assistant ───────────────────────────
src = os.path.join(os.path.dirname(__file__), "text_selector.py")
if not os.path.exists(src):
    src = os.path.expanduser("~/Downloads/text_selector.py")

if os.path.exists(src) and src != SEL_SRC:
    shutil.copy2(src, SEL_SRC)
    print(f"OK: text_selector.py copied to {SEL_SRC}")
elif os.path.exists(SEL_SRC):
    print("OK: text_selector.py already in vision_assistant/")
else:
    print("WARN: text_selector.py not found — copy it manually to ~/vision_assistant/")

# ── 2. CHECK scrot is installed ───────────────────────────────────────────────
r = subprocess.run(["which", "scrot"], capture_output=True)
if r.returncode != 0:
    print("INFO: scrot not found — installing...")
    subprocess.run(["sudo", "apt-get", "install", "-y", "scrot"], check=False)
else:
    print("OK: scrot available")

# ── 3. ADD HOTKEY TO ~/.xbindkeysrc ──────────────────────────────────────────
hotkey_entry = '''
# Echo text selector (Ctrl+Alt+T)
"/home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/text_selector.py"
  control+alt+t
'''

if os.path.exists(XBKEYS):
    content = open(XBKEYS).read()
    if "text_selector" in content:
        print("INFO: text_selector hotkey already in .xbindkeysrc")
    else:
        with open(XBKEYS, "a") as f:
            f.write(hotkey_entry)
        print("OK: Ctrl+Alt+T hotkey added to .xbindkeysrc")
        # Reload xbindkeys
        subprocess.run(["pkill", "xbindkeys"], capture_output=True)
        subprocess.Popen(["xbindkeys"])
        print("OK: xbindkeys reloaded")
else:
    with open(XBKEYS, "w") as f:
        f.write(hotkey_entry.strip() + "\n")
    print(f"OK: .xbindkeysrc created with hotkey")
    subprocess.Popen(["xbindkeys"])

# ── 4. ADD VOICE TRIGGER TO wake_word.py ────────────────────────────────────
ww_src = open(WW).read()

old_usb_trigger = '    if any(x in t for x in ["play usb"'

new_text_sel = '''\
    # Text selector
    if any(x in t for x in ["select text","read screen","copy text","text selector","scan text","read text"]):
        import threading, subprocess as _sp
        threading.Thread(target=lambda: _sp.Popen([
            "/home/jesus999l/vision_env/bin/python3",
            "/home/jesus999l/vision_assistant/text_selector.py"
        ]), daemon=True).start(); return

    if any(x in t for x in ["play usb"'''

if "select text" not in ww_src:
    if old_usb_trigger in ww_src:
        ww_src = ww_src.replace(old_usb_trigger, new_text_sel)
        open(WW, "w").write(ww_src)
        print("OK: voice trigger added to wake_word.py")
    else:
        print("FAIL: insertion point not found in wake_word.py")
else:
    print("INFO: voice trigger already in wake_word.py")

# ── 5. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("text_selector.py", SEL_SRC), ("wake_word.py", WW)]:
    if os.path.exists(path):
        r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
        print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
        if r.returncode != 0:
            print(r.stderr)

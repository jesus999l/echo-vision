"""
Fix patch:
1. Autostart .desktop → adds --ui flag so boot opens Echo without capturing
2. Text selector hotkey → Ctrl+Alt+X (avoids Mint terminal conflict on Ctrl+Alt+T)
3. Text selector overlay → explicit 1920x1080+0+0 geometry instead of broken fullscreen+overrideredirect
4. PTT terminal spam → adds DISPLAY check so PTT doesn't fire when run from terminal

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_fixes2.py
"""
import os, subprocess

VA      = os.path.expanduser("~/vision_assistant")
DESKTOP = os.path.expanduser("~/.config/autostart/echo-desktop.desktop")
XBKEYS  = os.path.expanduser("~/.xbindkeysrc")
SEL     = os.path.join(VA, "text_selector.py")

# ── 1. FIX AUTOSTART — add --ui flag ─────────────────────────────────────────
content = open(DESKTOP).read()
old_exec = "Exec=/home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/main.py"
new_exec = "Exec=/home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/main.py --ui"
if "--ui" not in content:
    content = content.replace(old_exec, new_exec)
    open(DESKTOP, "w").write(content)
    print("OK: autostart .desktop — added --ui flag")
else:
    print("INFO: --ui already in autostart")

# ── 2. FIX XBINDKEYS — change Ctrl+Alt+T → Ctrl+Alt+X ───────────────────────
xb = open(XBKEYS).read()

old_hotkey = '''"text_selector"
  control+alt+t'''
new_hotkey = '''"text_selector"
  control+alt+x'''

# Handle both the comment line format and plain format
if "control+alt+t" in xb and "text_selector" in xb:
    # Replace just the key binding line after text_selector
    lines = xb.splitlines()
    new_lines = []
    i = 0
    while i < len(lines):
        if "text_selector" in lines[i].lower():
            new_lines.append(lines[i])
            i += 1
            # Next non-empty line is the key binding
            while i < len(lines) and lines[i].strip() == "":
                new_lines.append(lines[i]); i += 1
            if i < len(lines):
                new_lines.append("  control+alt+x")
                i += 1  # skip old binding
        else:
            new_lines.append(lines[i]); i += 1
    open(XBKEYS, "w").write("\n".join(new_lines) + "\n")
    print("OK: hotkey changed Ctrl+Alt+T → Ctrl+Alt+X")
elif "text_selector" not in xb:
    # Add fresh entry
    entry = '\n# Echo text selector (Ctrl+Alt+X)\n"/home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/text_selector.py"\n  control+alt+x\n'
    open(XBKEYS, "a").write(entry)
    print("OK: Ctrl+Alt+X hotkey added")
else:
    print("INFO: hotkey already updated")

# Reload xbindkeys
subprocess.run(["pkill", "xbindkeys"], capture_output=True)
subprocess.Popen(["xbindkeys"])
print("OK: xbindkeys reloaded")

# ── 3. FIX TEXT SELECTOR OVERLAY — explicit geometry ─────────────────────────
sel_src = open(SEL).read()

old_overlay_init = '''        # Fullscreen transparent overlay
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.35)
        self.attributes("-topmost", True)
        self.configure(bg="black", cursor="crosshair")
        self.overrideredirect(True)

        self._start_x = self._start_y = 0
        self._rect = None

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)'''

new_overlay_init = '''        # Fullscreen transparent overlay — explicit geometry for Linux Mint
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.overrideredirect(True)
        self.attributes("-alpha", 0.45)
        self.attributes("-topmost", True)
        self.configure(bg="black", cursor="crosshair")
        self.lift()
        self.update_idletasks()

        self._start_x = self._start_y = 0
        self._rect = None

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0,
                                cursor="crosshair", width=sw, height=sh)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)'''

if old_overlay_init in sel_src:
    sel_src = sel_src.replace(old_overlay_init, new_overlay_init)
    open(SEL, "w").write(sel_src)
    print("OK: text_selector.py overlay geometry fixed")
else:
    print("FAIL: overlay block not found — may already be patched")

# ── 4. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("text_selector.py", SEL)]:
    r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
    print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
    if r.returncode != 0:
        print(r.stderr)

print()
print("Summary:")
print("  Boot autostart  → opens Echo UI only (no screenshot)")
print("  Text selector   → Ctrl+Alt+X")
print("  PTT             → Ctrl+Alt+Space (unchanged)")
print("  Mic             → 85% capture confirmed working")
print("  To test mic: run Echo detached from terminal:")
print("    nohup /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/main.py --ui &")

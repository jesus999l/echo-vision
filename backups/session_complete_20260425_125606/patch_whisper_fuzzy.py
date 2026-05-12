"""
Patch: Whisper base.en upgrade + fuzzy command matching.
1. Downloads faster-whisper base.en model (~150MB)
2. Switches wake_word.py to use base.en
3. Adds fuzzy matching to route_command() so mis-transcriptions still route correctly
   e.g. "fause" → "pause", "nex song" → "next song", "hey acko" → handled

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_whisper_fuzzy.py
"""
import os, subprocess

VA = os.path.expanduser("~/vision_assistant")
WW = os.path.join(VA, "wake_word.py")

# ── 1. DOWNLOAD base.en ───────────────────────────────────────────────────────
print("[1/3] Downloading faster-whisper base.en (~150MB)...")
r = subprocess.run(
    ["/home/jesus999l/vision_env/bin/python3", "-c",
     "from faster_whisper import WhisperModel; "
     "print('Downloading...'); "
     "m = WhisperModel('base.en', device='cpu', compute_type='int8'); "
     "print('OK: base.en ready')"],
    capture_output=False
)
if r.returncode != 0:
    print("WARN: Download may have failed — check above output")
else:
    print("OK: base.en downloaded")

# ── 2. SWITCH MODEL IN wake_word.py ──────────────────────────────────────────
print("[2/3] Switching wake_word.py to base.en...")
ww_src = open(WW).read()

old_model = '"tiny.en", device="cpu", compute_type="int8",'
new_model = '"base.en", device="cpu", compute_type="int8",'

if old_model in ww_src:
    ww_src = ww_src.replace(old_model, new_model)
    print("OK: Model switched tiny.en → base.en")
elif "base.en" in ww_src:
    print("INFO: Already using base.en")
else:
    print("FAIL: Model line not found")

# ── 3. ADD FUZZY MATCHING TO route_command() ─────────────────────────────────
print("[3/3] Adding fuzzy matching to route_command()...")

old_route_start = '''def route_command(text):
    t = text.lower().strip()
    for wp in WAKE_PHRASES:
        t = t.replace(wp, "").strip()
    if not t:
        return
    print(f"[wake] routing: {t}")'''

new_route_start = '''def _fuzzy_correct(t):
    """Fix common Whisper mis-transcriptions before routing."""
    replacements = {
        # Pause variants
        "fause": "pause", "paus ": "pause ", "pausing": "pause",
        "paul's": "pause", "poses": "pause",
        # Play variants
        "plea": "play", "plane": "play", "playa": "play",
        # Next/previous
        "nex ": "next ", "neck song": "next song",
        "next on": "next song", "text song": "next song",
        "previous on": "previous song", "prefix song": "previous song",
        # Volume
        "louder please": "volume up", "turn up": "volume up",
        "quieter": "volume down", "turn down": "volume down",
        # System
        "system stasis": "system status", "system stats": "system status",
        "clean system please": "clean system",
        # Music
        "my music please": "my music", "play music please": "play music",
        # USB
        "play use b": "play usb", "play you as b": "play usb",
        # Common word errors
        "acko": "echo", "eko": "echo", "ecco": "echo",
    }
    result = t
    for wrong, right in replacements.items():
        result = result.replace(wrong, right)
    return result

def route_command(text):
    t = text.lower().strip()
    for wp in WAKE_PHRASES:
        t = t.replace(wp, "").strip()
    if not t:
        return
    # Apply fuzzy correction before routing
    corrected = _fuzzy_correct(t)
    if corrected != t:
        print(f"[wake] fuzzy: {t!r} → {corrected!r}")
        t = corrected
    print(f"[wake] routing: {t}")'''

if old_route_start in ww_src:
    ww_src = ww_src.replace(old_route_start, new_route_start)
    print("OK: fuzzy matching added to route_command()")
elif "_fuzzy_correct" in ww_src:
    print("INFO: fuzzy matching already present")
else:
    print("FAIL: route_command() not found")

open(WW, "w").write(ww_src)

# ── 4. SYNTAX CHECK ───────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
r = subprocess.run([py, "-m", "py_compile", WW], capture_output=True, text=True)
print(f"{'OK' if r.returncode == 0 else 'ERR'}: wake_word.py")
if r.returncode != 0:
    print(r.stderr)

print()
print("Done. Restart Echo to use base.en + fuzzy matching:")
print("  pkill -f 'main.py'; sleep 1")
print("  ALSA_LOG_LEVEL=0 PYTHONUNBUFFERED=1 /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/main.py --ui > /tmp/echo.log 2>/tmp/echo_err.log &")

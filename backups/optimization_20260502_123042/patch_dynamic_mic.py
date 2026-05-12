"""
Patch: Dynamic MIC_DEVICE detection.
Instead of hardcoding a device index (breaks when audio devices change),
Echo now finds the pulse/pipewire device at runtime every startup.

Priority order:
1. 'pulse' device (PipeWire-pulse, most compatible)
2. 'pipewire' device
3. 'default' device
4. First device with input channels (last resort)

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_dynamic_mic.py
"""
import os, subprocess

VA  = os.path.expanduser("~/vision_assistant")
WW  = os.path.join(VA, "wake_word.py")
PTT = os.path.join(VA, "ptt.py")

# ── 1. ADD get_mic_device() TO wake_word.py ───────────────────────────────────
ww_src = open(WW).read()

old_mic = "MIC_DEVICE      = 3"

new_mic = '''def get_mic_device():
    """Dynamically find the best input device index at runtime."""
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            try:
                d = p.get_device_info_by_index(i)
                if d["maxInputChannels"] > 0:
                    devices.append((i, d["name"].lower()))
            except: pass
        p.terminate()
        # Priority: pulse > pipewire > default > sysdefault > first available
        for priority in ["pulse", "pipewire", "default", "sysdefault"]:
            for idx, name in devices:
                if priority in name:
                    print(f"[mic] Using device {idx}: {name}")
                    return idx
        if devices:
            print(f"[mic] Fallback device {devices[0][0]}: {devices[0][1]}")
            return devices[0][0]
    except Exception as e:
        print(f"[mic] Device detection failed: {e}")
    return None

MIC_DEVICE = get_mic_device()'''

if old_mic in ww_src:
    ww_src = ww_src.replace(old_mic, new_mic)
    open(WW, "w").write(ww_src)
    print("OK: wake_word.py — dynamic MIC_DEVICE")
elif "def get_mic_device" in ww_src:
    print("INFO: dynamic MIC_DEVICE already in wake_word.py")
else:
    print("FAIL: MIC_DEVICE line not found in wake_word.py")
    print("Current MIC_DEVICE line:")
    for line in open(WW):
        if "MIC_DEVICE" in line and "def" not in line and "input_device" not in line:
            print(f"  {repr(line.rstrip())}")

# ── 2. PATCH ptt.py ───────────────────────────────────────────────────────────
ptt_src = open(PTT).read()

old_ptt_mic = "MIC_DEVICE    = None   # None = default, or set to int (e.g. 11)"

new_ptt_mic = '''def _get_mic_device():
    """Find pulse/pipewire input device dynamically."""
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            try:
                d = p.get_device_info_by_index(i)
                if d["maxInputChannels"] > 0:
                    devices.append((i, d["name"].lower()))
            except: pass
        p.terminate()
        for priority in ["pulse", "pipewire", "default", "sysdefault"]:
            for idx, name in devices:
                if priority in name:
                    return idx
        return devices[0][0] if devices else None
    except: return None

MIC_DEVICE = _get_mic_device()'''

if old_ptt_mic in ptt_src:
    ptt_src = ptt_src.replace(old_ptt_mic, new_ptt_mic)
    open(PTT, "w").write(ptt_src)
    print("OK: ptt.py — dynamic MIC_DEVICE")
elif "_get_mic_device" in ptt_src:
    print("INFO: dynamic MIC_DEVICE already in ptt.py")
else:
    print("FAIL: MIC_DEVICE line not found in ptt.py")
    for line in open(PTT):
        if "MIC_DEVICE" in line and "def" not in line and "input_device" not in line:
            print(f"  {repr(line.rstrip())}")

# ── 3. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("wake_word.py", WW), ("ptt.py", PTT)]:
    r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
    print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
    if r.returncode != 0:
        print(r.stderr)

# ── 4. QUICK TEST ─────────────────────────────────────────────────────────────
print("\nTesting device detection now:")
r = subprocess.run([py, "-c", """
import sys
sys.path.insert(0, '/home/jesus999l/vision_assistant')
from wake_word import get_mic_device, MIC_DEVICE
print(f"Detected MIC_DEVICE = {MIC_DEVICE}")
"""], capture_output=True, text=True)
out = [l for l in r.stdout.splitlines() if "ALSA" not in l and "jack" not in l and "Cannot" not in l and "LOG" not in l]
print("\n".join(out))
if r.returncode != 0:
    print(r.stderr[:300])

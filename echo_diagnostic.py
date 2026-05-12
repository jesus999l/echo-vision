#!/usr/bin/env python3
"""
Echo Desktop — Full System Diagnostic
Checks all components and reports status.
Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/echo_diagnostic.py
"""
import os, sys, subprocess, socket, json, time, shutil

sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

VA = os.path.expanduser("~/vision_assistant")

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "
INFO = "ℹ️ "

results = []

def check(label, ok, detail="", warn=False):
    icon = WARN if warn else (PASS if ok else FAIL)
    results.append((icon, label, detail))
    print(f"  {icon}  {label:<40} {detail}")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

print("\n" + "═"*60)
print("  Echo Desktop — System Diagnostic")
print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("═"*60 + "\n")

# ── 1. CORE PROCESSES ─────────────────────────────────────────────────────────
print("[ Core Processes ]")
r = run("pgrep -f 'vision_assistant/main.py'")
check("Echo Desktop running", bool(r.stdout.strip()),
      f"PID {r.stdout.strip()[:8]}" if r.stdout.strip() else "not running")

r = run("pgrep -f 'ollama'")
check("Ollama running", bool(r.stdout.strip()))

r = run("curl -s http://localhost:11434/api/tags --max-time 3")
if r.returncode == 0:
    try:
        models = [m['name'] for m in json.loads(r.stdout).get('models', [])]
        check("Ollama API", True, f"{len(models)} models: {', '.join(models[:3])}")
    except:
        check("Ollama API", False, "bad response")
else:
    check("Ollama API", False, "not responding")

r = run("curl -s http://127.0.0.1:59996/status --max-time 3")
try:
    d = json.loads(r.stdout)
    check("Browser server (port 59996)", True, f"model: {d.get('model','?')}")
except:
    check("Browser server (port 59996)", False, "not responding")

# ── 2. AUDIO & MIC ────────────────────────────────────────────────────────────
print("\n[ Audio & Microphone ]")
r = run("pactl info | grep 'Default Sink'")
sink = r.stdout.strip().replace("Default Sink: ", "")
check("Default audio sink", bool(sink), sink[:50])

r = run("pactl info | grep 'Default Source'")
source = r.stdout.strip().replace("Default Source: ", "")
check("Default mic source", bool(source), source[:50])

r = run("pactl list cards | grep -A15 'bluez_card' | grep 'Active Profile'")
profile = r.stdout.strip().replace("Active Profile:", "").strip()
check("Crusher ANC 2 profile", bool(profile), profile if profile else "not connected")

r = run("amixer sget Capture 2>/dev/null | grep -o '[0-9]*%' | head -1")
vol = r.stdout.strip()
check("Mic capture volume", bool(vol), vol)

r = run("pgrep -f easyeffects")
check("EasyEffects running", bool(r.stdout.strip()))

# ── 3. WAKE WORD & VOICE ──────────────────────────────────────────────────────
print("\n[ Wake Word & Voice ]")
vosk = os.path.exists(os.path.expanduser("~/vosk-model-small-en-us-0.15/am/final.mdl"))
check("Vosk model", vosk)

r = run("ls ~/.cache/huggingface/hub/ 2>/dev/null | grep 'faster-whisper-base'")
check("Whisper base.en model", bool(r.stdout.strip()))

piper = os.path.exists(os.path.expanduser("~/piper/piper"))
check("Piper TTS binary", piper)

r = run("grep 'MIC_DEVICE' ~/vision_assistant/wake_word.py | head -1")
mic_dev = r.stdout.strip()
check("Dynamic MIC_DEVICE", "get_mic_device" in open(os.path.join(VA, "wake_word.py")).read(),
      mic_dev)

# ── 4. NEW MODULES ────────────────────────────────────────────────────────────
print("\n[ Echo Modules ]")
modules = [
    ("ptt.py", "Push to Talk"),
    ("self_adjust.py", "Self-Adjustment Monitor"),
    ("system_clean.py", "System Cleaner"),
    ("text_selector.py", "Text Selector"),
    ("echo_game_recorder.py", "Game Recorder"),
    ("echo_warframe_bot.py", "Warframe Bot"),
    ("warframe_loadout.py", "Loadout Detector"),
    ("echo_browser_server.py", "Browser Server"),
]
for fname, label in modules:
    path = os.path.join(VA, fname)
    check(label, os.path.exists(path), fname)

# ── 5. HOTKEYS ────────────────────────────────────────────────────────────────
print("\n[ Hotkeys ]")
xbkeys = open(os.path.expanduser("~/.xbindkeysrc")).read()
hotkeys = [
    ("control+alt+x", "Text Selector (Ctrl+Alt+X)"),
    ("control+alt+g", "Gaming Mode (Ctrl+Alt+G)"),
    ("control+alt+s", "Open Echo (Ctrl+Alt+S)"),
]
for key, label in hotkeys:
    check(label, key in xbkeys.lower())

r = run("pgrep xbindkeys")
check("xbindkeys running", bool(r.stdout.strip()))

# ── 6. AUTOSTART ──────────────────────────────────────────────────────────────
print("\n[ Autostart ]")
autostart = os.path.expanduser("~/.config/autostart/echo-desktop.desktop")
if os.path.exists(autostart):
    content = open(autostart).read()
    check("Echo autostart", True, "--ui" in content and "OK" or "missing --ui flag",
          warn="--ui" not in content)
else:
    check("Echo autostart", False, "file missing")

r = run("systemctl is-enabled docker 2>/dev/null")
check("Docker autostart disabled", "disabled" in r.stdout, r.stdout.strip())

r = run("systemctl is-enabled boinc-client 2>/dev/null")
check("BOINC autostart disabled", "disabled" in r.stdout or r.returncode != 0,
      r.stdout.strip() or "not found")

# ── 7. DISK & SYSTEM ──────────────────────────────────────────────────────────
print("\n[ System Resources ]")
disk = shutil.disk_usage("/")
free_gb = disk.free / 1024**3
used_pct = disk.used / disk.total * 100
check("Disk space", free_gb > 5, f"{free_gb:.1f}GB free ({used_pct:.0f}% used)",
      warn=free_gb < 10)

r = run("free -b")
parts = r.stdout.splitlines()[1].split()
ram_used = int(parts[2]) / 1024**3
ram_total = int(parts[1]) / 1024**3
ram_pct = int(parts[2]) / int(parts[1]) * 100
check("RAM usage", ram_pct < 85, f"{ram_used:.1f}/{ram_total:.1f}GB ({ram_pct:.0f}%)",
      warn=ram_pct > 70)

r = run("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'")
cpu = float(r.stdout.strip() or "0")
check("CPU usage", cpu < 80, f"{cpu:.0f}%", warn=cpu > 50)

# ── 8. GAME SESSIONS ──────────────────────────────────────────────────────────
print("\n[ Warframe & Gaming ]")
sessions_dir = os.path.expanduser("~/echo_game_sessions")
if os.path.exists(sessions_dir):
    sessions = sorted(os.listdir(sessions_dir))
    big = [s for s in sessions if os.path.getsize(os.path.join(sessions_dir, s)) > 10000]
    check("Game sessions recorded", len(big) > 0, f"{len(big)} sessions with data")
else:
    check("Game sessions directory", False, "missing")

kb = os.path.expanduser("~/echo_warframe/warframe_parsed_kb.json")
check("Warframe KB", os.path.exists(kb), "1.4MB KB found" if os.path.exists(kb) else "missing")

# ── 9. SCHEDULED TASKS ───────────────────────────────────────────────────────
print("\n[ Scheduled Tasks ]")
r = run("crontab -l 2>/dev/null")
cron = r.stdout
check("Weekly system clean", "system_clean" in cron or "echo_cleanup" in cron)
check("BOINC schedule", "boinc-schedule" in cron)

maintenance_stamp = os.path.expanduser("~/vision_assistant/.last_maintenance")
if os.path.exists(maintenance_stamp):
    last = float(open(maintenance_stamp).read().strip())
    days = (time.time() - last) / 86400
    check("Monthly maintenance", days < 30, f"last run {days:.0f} days ago",
          warn=days > 25)
else:
    check("Monthly maintenance", False, "never run — will run on next Echo start", warn=True)

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print("\n" + "═"*60)
passed = sum(1 for r in results if r[0] == PASS)
warned = sum(1 for r in results if r[0] == WARN)
failed = sum(1 for r in results if r[0] == FAIL)
total  = len(results)
print(f"  Results: {passed} passed  {warned} warnings  {failed} failed  ({total} total)")

if failed > 0:
    print(f"\n  Failed checks:")
    for icon, label, detail in results:
        if icon == FAIL:
            print(f"    {FAIL} {label}: {detail}")

if warned > 0:
    print(f"\n  Warnings:")
    for icon, label, detail in results:
        if icon == WARN:
            print(f"    {WARN} {label}: {detail}")

print("═"*60 + "\n")

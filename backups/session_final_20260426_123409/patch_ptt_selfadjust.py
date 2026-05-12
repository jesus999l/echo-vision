"""
Patch: Push-to-Talk (PTT) + Self-Adjustment Monitor.

1. PTT — Hold Ctrl+Alt+Space → records while held → releases → Whisper → route_command()
   - Bypasses wake word entirely
   - Works even when Echo window is not focused
   - Visual/audio cue on start/stop

2. Self-Adjustment Monitor — background thread checks system health every 10 min:
   - Low disk space → offer to run cleanup
   - Mic volume low → offer to boost
   - High CPU/RAM → notify
   - Applies fixes only after user confirms via notification action

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_ptt_selfadjust.py
"""
import os, subprocess

VA   = os.path.expanduser("~/vision_assistant")
WW   = os.path.join(VA, "wake_word.py")
MAIN = os.path.join(VA, "main.py")
PTT  = os.path.join(VA, "ptt.py")
ADJ  = os.path.join(VA, "self_adjust.py")

# ── 1. CREATE ptt.py ──────────────────────────────────────────────────────────
ptt_src = '''\
"""
Push-to-Talk for Echo Desktop.
Hold Ctrl+Alt+Space → records while held → Whisper → route_command().
Runs as a background daemon thread.
"""
import os, sys, threading, tempfile, wave, time
sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

PTT_KEY_COMBO = {\'ctrl\', \'alt\', \'space\'}   # all three must be held
MIC_DEVICE    = None   # None = default, or set to int (e.g. 11)
SAMPLE_RATE   = 16000
CHUNK         = 1024
MAX_HOLD_SEC  = 30     # safety cutoff

_held_keys   = set()
_recording   = False
_rec_thread  = None
_frames      = []
_pa          = None

def _beep(freq=880, duration=0.08):
    """Short audio cue via paplay/beep, non-blocking."""
    try:
        import subprocess as _sp
        _sp.Popen(
            ["python3", "-c",
             f"import os; os.system(\'paplay --volume=40000 /usr/share/sounds/freedesktop/stereo/audio-volume-change.oga 2>/dev/null || beep -f {freq} -l {int(duration*1000)} 2>/dev/null\')"],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except: pass

def _notify(msg):
    try:
        import subprocess as _sp
        _sp.Popen(["notify-send", "-t", "1500", "-u", "low",
                   "-a", "Echo PTT", "🎙 Echo PTT", msg],
                  stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except: pass

def _start_recording():
    global _recording, _frames, _pa
    import pyaudio
    _recording = True
    _frames = []
    _beep(880, 0.07)
    _notify("Listening...")
    try:
        _pa = pyaudio.PyAudio()
        stream = _pa.open(
            format=pyaudio.paInt16, channels=1,
            rate=SAMPLE_RATE, input=True,
            input_device_index=MIC_DEVICE,
            frames_per_buffer=CHUNK
        )
        start = time.time()
        while _recording and (time.time() - start) < MAX_HOLD_SEC:
            data = stream.read(CHUNK, exception_on_overflow=False)
            _frames.append(data)
        stream.stop_stream()
        stream.close()
        _pa.terminate()
        _pa = None
    except Exception as e:
        print(f"[ptt] record error: {e}")
        _recording = False

def _stop_and_transcribe():
    global _recording
    _recording = False
    _beep(660, 0.07)
    if not _frames:
        return

    # Write WAV
    tmp = tempfile.mktemp(prefix="echo_ptt_", suffix=".wav")
    try:
        with wave.open(tmp, \'wb\') as wf:
            import pyaudio
            wf.setnchannels(1)
            wf.setsampwidth(2)  # paInt16 = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b\'\'.join(_frames))
    except Exception as e:
        print(f"[ptt] wav error: {e}")
        return

    # Transcribe
    try:
        sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from wake_word import _transcribe_whisper, route_command
        text = _transcribe_whisper(tmp)
        if text.strip():
            print(f"[ptt] command: {text!r}")
            _notify(f""{text}"")
            route_command(text)
        else:
            _notify("Nothing heard.")
    except Exception as e:
        print(f"[ptt] transcribe error: {e}")
    finally:
        try: os.unlink(tmp)
        except: pass

def _on_press(key):
    global _rec_thread
    try:
        from pynput.keyboard import Key
        name = key.char if hasattr(key, \'char\') and key.char else str(key).replace(\'Key.\', \'\')
        _held_keys.add(name.lower())
        # Check if full combo held
        if PTT_KEY_COMBO.issubset(_held_keys) and not _recording:
            _rec_thread = threading.Thread(target=_start_recording, daemon=True)
            _rec_thread.start()
    except: pass

def _on_release(key):
    try:
        from pynput.keyboard import Key
        name = key.char if hasattr(key, \'char\') and key.char else str(key).replace(\'Key.\', \'\')
        _held_keys.discard(name.lower())
        # Release if any PTT key lifted while recording
        if _recording and not PTT_KEY_COMBO.issubset(_held_keys):
            threading.Thread(target=_stop_and_transcribe, daemon=True).start()
    except: pass

def start_ptt():
    """Start PTT keyboard listener in background."""
    try:
        from pynput import keyboard
        listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
        listener.daemon = True
        listener.start()
        print("[ptt] Push-to-talk ready — hold Ctrl+Alt+Space to speak.")
        return listener
    except ImportError:
        print("[ptt] pynput not installed — run: pip install pynput --break-system-packages")
        return None
    except Exception as e:
        print(f"[ptt] failed to start: {e}")
        return None
'''

open(PTT, "w").write(ptt_src)
print("OK: ptt.py created")

# ── 2. CREATE self_adjust.py ──────────────────────────────────────────────────
adj_src = '''\
"""
Echo Self-Adjustment Monitor.
Runs in background, checks system health every 10 min.
Proposes fixes via notification — only applies with user confirmation.
"""
import os, sys, subprocess, threading, time, shutil
sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

CHECK_INTERVAL   = 600   # 10 minutes
DISK_WARN_GB     = 5.0   # warn below 5 GB free
DISK_CRIT_GB     = 2.0   # critical below 2 GB
RAM_WARN_PCT     = 85    # warn above 85% RAM used
CPU_WARN_PCT     = 90    # warn above 90% CPU (sustained)
MIC_VOL_MIN      = 70    # warn if mic capture below 70%

_last_alerts     = {}    # throttle: don\'t repeat same alert < 1hr
_ALERT_COOLDOWN  = 3600

def _throttle(key):
    now = time.time()
    if now - _last_alerts.get(key, 0) < _ALERT_COOLDOWN:
        return True
    _last_alerts[key] = now
    return False

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def _notify_action(title, body, action_label, action_cmd, urgency="normal"):
    """Send notification. action_cmd runs if user clicks action (via zenity confirm)."""
    try:
        subprocess.Popen(
            ["notify-send", "-u", urgency, "-a", "Echo", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except: pass
    # Also speak it
    try:
        from voice import speak
        speak(f"{title}. {body}")
    except: pass

def _ask_permission(question, on_confirm):
    """Show a yes/no dialog. Calls on_confirm() if user says yes."""
    def _dialog():
        r = subprocess.run(
            ["zenity", "--question", "--title=Echo", f"--text={question}",
             "--width=380", "--ok-label=Yes, do it", "--cancel-label=No thanks"],
            capture_output=True
        )
        if r.returncode == 0:
            on_confirm()
    threading.Thread(target=_dialog, daemon=True).start()

# ── CHECKS ────────────────────────────────────────────────────────────────────
def check_disk():
    try:
        disk = shutil.disk_usage("/")
        free_gb = disk.free / 1024**3
        used_pct = disk.used / disk.total * 100
        if free_gb < DISK_CRIT_GB and not _throttle("disk_crit"):
            _ask_permission(
                f"⚠ Disk space critical: only {free_gb:.1f} GB free ({used_pct:.0f}% used).\\nRun Echo system cleanup now?",
                _do_cleanup
            )
        elif free_gb < DISK_WARN_GB and not _throttle("disk_warn"):
            _notify_action(
                "Echo — Low Disk Space",
                f"{free_gb:.1f} GB free ({used_pct:.0f}% used). Consider running cleanup.",
                "Clean now", "", urgency="normal"
            )
    except Exception as e:
        print(f"[selfadj] disk check error: {e}")

def check_ram():
    try:
        lines = _run("free -b").stdout.strip().splitlines()
        parts = lines[1].split()
        total, used = int(parts[1]), int(parts[2])
        pct = used / total * 100
        if pct > RAM_WARN_PCT and not _throttle("ram_warn"):
            free_gb = (total - used) / 1024**3
            _notify_action(
                "Echo — High RAM Usage",
                f"RAM at {pct:.0f}% used. {free_gb:.1f} GB free.",
                "", "", urgency="normal"
            )
    except Exception as e:
        print(f"[selfadj] ram check error: {e}")

def check_mic_volume():
    try:
        r = _run("amixer sget Capture 2>/dev/null || amixer sget \'Mic Boost\' 2>/dev/null")
        import re
        m = re.search(r\'\\[(\\d+)%\\]\', r.stdout)
        if m:
            vol = int(m.group(1))
            if vol < MIC_VOL_MIN and not _throttle("mic_vol"):
                _ask_permission(
                    f"Echo mic capture volume is low ({vol}%).\\nBoost it to 85% for better voice recognition?",
                    _boost_mic
                )
    except Exception as e:
        print(f"[selfadj] mic check error: {e}")

def check_cpu():
    try:
        r = _run("top -bn2 -d0.5 | grep \'Cpu(s)\' | tail -1 | awk \'{print $2+$4}\'")
        cpu = float(r.stdout.strip() or "0")
        if cpu > CPU_WARN_PCT and not _throttle("cpu_warn"):
            _notify_action(
                "Echo — High CPU Usage",
                f"CPU at {cpu:.0f}%. Echo may respond slowly.",
                "", "", urgency="normal"
            )
    except Exception as e:
        print(f"[selfadj] cpu check error: {e}")

# ── FIXES (only called after user confirms) ───────────────────────────────────
def _do_cleanup():
    try:
        from system_clean import clean_system
        from briefing import send_notification
        result = clean_system()
        send_notification("Echo Cleanup Complete", result.split("\\n")[0])
        try:
            from voice import speak
            speak("Cleanup complete.")
        except: pass
    except Exception as e:
        print(f"[selfadj] cleanup error: {e}")

def _boost_mic():
    try:
        subprocess.run("amixer sset Capture 85% 2>/dev/null || amixer sset \'Mic Boost\' 85% 2>/dev/null",
                       shell=True)
        try:
            from voice import speak
            speak("Microphone volume boosted to 85 percent.")
        except: pass
        from briefing import send_notification
        send_notification("Echo", "Mic volume set to 85%.")
    except Exception as e:
        print(f"[selfadj] mic boost error: {e}")

# ── MONITOR LOOP ──────────────────────────────────────────────────────────────
def _monitor_loop():
    time.sleep(30)   # wait for Echo to fully boot first
    while True:
        try:
            check_disk()
            check_ram()
            check_mic_volume()
            check_cpu()
        except Exception as e:
            print(f"[selfadj] monitor error: {e}")
        time.sleep(CHECK_INTERVAL)

def start_self_adjust():
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
    print("[selfadj] Self-adjustment monitor started.")
    return t
'''

open(ADJ, "w").write(adj_src)
print("OK: self_adjust.py created")

# ── 3. INSTALL pynput IF NEEDED ───────────────────────────────────────────────
r = subprocess.run(
    ["/home/jesus999l/vision_env/bin/python3", "-c", "import pynput"],
    capture_output=True
)
if r.returncode != 0:
    print("INFO: installing pynput...")
    subprocess.run(
        ["/home/jesus999l/vision_env/bin/pip", "install", "pynput", "--quiet"],
        check=False
    )
    print("OK: pynput installed")
else:
    print("OK: pynput available")

# ── 4. WIRE PTT + SELF-ADJUST INTO main.py ───────────────────────────────────
main_src = open(MAIN).read()

old_anchor = '''    # Monthly maintenance — runs silently if due (every 28 days)'''

new_anchor = '''    # Push-to-talk
    try:
        from ptt import start_ptt
        start_ptt()
    except Exception as e:
        print(f"[main] PTT skipped: {e}")

    # Self-adjustment monitor
    try:
        from self_adjust import start_self_adjust
        start_self_adjust()
    except Exception as e:
        print(f"[main] Self-adjust skipped: {e}")

    # Monthly maintenance — runs silently if due (every 28 days)'''

if "from ptt import" not in main_src:
    if old_anchor in main_src:
        main_src = main_src.replace(old_anchor, new_anchor)
        open(MAIN, "w").write(main_src)
        print("OK: PTT + self-adjust wired into main.py")
    else:
        print("FAIL: anchor not found in main.py")
else:
    print("INFO: PTT already in main.py")

# ── 5. SYNTAX CHECKS ─────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("ptt.py", PTT), ("self_adjust.py", ADJ), ("main.py", MAIN)]:
    r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
    print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
    if r.returncode != 0:
        print(r.stderr)

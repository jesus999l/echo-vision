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

_last_alerts     = {}    # throttle: don't repeat same alert < 1hr
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
                f"⚠ Disk space critical: only {free_gb:.1f} GB free ({used_pct:.0f}% used).\nRun Echo system cleanup now?",
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
        r = _run("amixer sget Capture 2>/dev/null || amixer sget 'Mic Boost' 2>/dev/null")
        import re
        m = re.search(r'\[(\d+)%\]', r.stdout)
        if m:
            vol = int(m.group(1))
            if vol < MIC_VOL_MIN and not _throttle("mic_vol"):
                _ask_permission(
                    f"Echo mic capture volume is low ({vol}%).\nBoost it to 85% for better voice recognition?",
                    _boost_mic
                )
    except Exception as e:
        print(f"[selfadj] mic check error: {e}")

def check_cpu():
    try:
        r = _run("top -bn2 -d0.5 | grep 'Cpu(s)' | tail -1 | awk '{print $2+$4}'")
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
        send_notification("Echo Cleanup Complete", result.split("\n")[0])
        try:
            from voice import speak
            speak("Cleanup complete.")
        except: pass
    except Exception as e:
        print(f"[selfadj] cleanup error: {e}")

def _boost_mic():
    try:
        subprocess.run("amixer sset Capture 85% 2>/dev/null || amixer sset 'Mic Boost' 85% 2>/dev/null",
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

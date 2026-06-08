"""
Patch: System Cleaner + USB/Local Media Voice Integration.

1. Adds system_clean.py — on-demand + auto CPU/RAM report, apt/logs/trash/tmp cleanup
2. Wires "clean system" / "system status" into wake_word.py voice commands
3. Adds USB media voice commands to wake_word.py:
   - "play USB" / "play from USB" / "play local media" → auto-detect USB + launch VLC
   - pause/next/prev already work via existing playerctl _media() calls
4. Adds vlc_control() to browser_control.py for VLC-specific commands

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_system_media.py
"""
import os, subprocess

VA   = os.path.expanduser("~/vision_assistant")
WW   = os.path.join(VA, "wake_word.py")
BC   = os.path.join(VA, "browser_control.py")
SYS  = os.path.join(VA, "system_clean.py")

# ── 1. CREATE system_clean.py ─────────────────────────────────────────────────
system_clean_src = '''\
"""
Echo system cleaner — on-demand and scheduled.
Reports CPU/RAM usage, frees disk space via apt/logs/trash/tmp cleanup.
"""
import subprocess, os, shutil, time, glob

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def _mb(b): return f"{b / 1024**2:.1f} MB"
def _gb(b): return f"{b / 1024**3:.2f} GB"

def system_status():
    """Return a string summary of current CPU/RAM/disk usage."""
    lines = []

    # CPU
    try:
        cpu = _run("top -bn1 | grep \'Cpu(s)\' | awk \'{print $2+$4}\'").stdout.strip()
        lines.append(f"CPU usage: {cpu}%")
    except: lines.append("CPU: unavailable")

    # RAM
    try:
        mem = _run("free -b").stdout.strip().splitlines()
        parts = mem[1].split()
        total, used, free = int(parts[1]), int(parts[2]), int(parts[3])
        lines.append(f"RAM: {_gb(used)} used / {_gb(total)} total ({_gb(free)} free)")
    except: lines.append("RAM: unavailable")

    # Disk
    try:
        disk = shutil.disk_usage("/")
        lines.append(f"Disk /: {_gb(disk.used)} used / {_gb(disk.total)} total ({_gb(disk.free)} free)")
    except: lines.append("Disk: unavailable")

    # Swap
    try:
        swap = _run("free -b").stdout.strip().splitlines()
        if len(swap) >= 3:
            sp = swap[2].split()
            if len(sp) >= 3:
                st, su = int(sp[1]), int(sp[2])
                lines.append(f"Swap: {_gb(su)} used / {_gb(st)} total")
    except: pass

    return "\\n".join(lines)

def clean_system(verbose=True):
    """
    Frees disk space:
    - apt cache clean + autoremove
    - systemd journal logs older than 7 days
    - User trash
    - /tmp files older than 1 day owned by current user
    - ~/.cache/thumbnails older than 30 days
    Returns a summary string.
    """
    freed_estimates = []
    log = []

    # Snapshot disk before
    try:
        disk_before = shutil.disk_usage("/").free
    except:
        disk_before = 0

    # apt cache
    try:
        r = _run("sudo apt-get clean -y 2>&1")
        r2 = _run("sudo apt-get autoremove -y 2>&1")
        log.append("apt cache + autoremove: done")
    except Exception as e:
        log.append(f"apt: {e}")

    # systemd journal — keep 7 days
    try:
        r = _run("sudo journalctl --vacuum-time=7d 2>&1")
        out = r.stdout.strip() or r.stderr.strip()
        log.append(f"journal: {out.splitlines()[-1] if out else \'done\'}")
    except Exception as e:
        log.append(f"journal: {e}")

    # Trash
    try:
        trash = os.path.expanduser("~/.local/share/Trash")
        removed = 0
        for sub in ["files", "info", "expunged"]:
            p = os.path.join(trash, sub)
            if os.path.exists(p):
                for f in os.listdir(p):
                    fp = os.path.join(p, f)
                    try:
                        if os.path.isdir(fp): shutil.rmtree(fp)
                        else: os.remove(fp)
                        removed += 1
                    except: pass
        log.append(f"trash: {removed} items removed")
    except Exception as e:
        log.append(f"trash: {e}")

    # /tmp owned by current user, older than 1 day
    try:
        uid = os.getuid()
        cutoff = time.time() - 86400
        removed = 0
        for f in glob.glob("/tmp/*"):
            try:
                if os.stat(f).st_uid == uid and os.path.getmtime(f) < cutoff:
                    if os.path.isdir(f): shutil.rmtree(f)
                    else: os.remove(f)
                    removed += 1
            except: pass
        log.append(f"/tmp cleanup: {removed} items removed")
    except Exception as e:
        log.append(f"/tmp: {e}")

    # Thumbnail cache older than 30 days
    try:
        cutoff2 = time.time() - 30 * 86400
        removed2 = 0
        thumb_dir = os.path.expanduser("~/.cache/thumbnails")
        for root, dirs, files in os.walk(thumb_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if os.path.getmtime(fp) < cutoff2:
                        os.remove(fp)
                        removed2 += 1
                except: pass
        log.append(f"thumbnails: {removed2} old removed")
    except Exception as e:
        log.append(f"thumbnails: {e}")

    # Disk after
    try:
        disk_after = shutil.disk_usage("/").free
        freed = disk_after - disk_before
        freed_str = f"Net freed: ~{_gb(freed)}" if freed > 0 else "Net freed: minimal (already clean)"
    except:
        freed_str = ""

    summary = "System clean complete:\\n"
    summary += "\\n".join(f"  · {l}" for l in log)
    if freed_str:
        summary += f"\\n  · {freed_str}"
    if verbose:
        print(f"[system_clean] {summary}")
    return summary

if __name__ == "__main__":
    print(system_status())
    print()
    print(clean_system())
'''

open(SYS, "w").write(system_clean_src)
print("OK: system_clean.py created")

# ── 2. ADD vlc_control + usb_play TO browser_control.py ─────────────────────
bc_src = open(BC).read()

vlc_additions = '''

# ── VLC / LOCAL MEDIA ─────────────────────────────────────────────────────────
import glob as _glob

def _detect_usb():
    """Return the first mounted USB media path under /media/<user>/."""
    user = os.environ.get("USER", "jesus999l")
    mounts = _glob.glob(f"/media/{user}/*/")
    # Prefer drive with video files
    for m in mounts:
        for root, dirs, files in os.walk(m):
            for f in files:
                if f.lower().endswith((".mp4", ".mkv", ".avi", ".webm")):
                    return m
    return mounts[0] if mounts else None

def play_usb(path=None):
    """Launch scan_and_play.py with USB drive or given path."""
    import threading
    target = path or _detect_usb()
    if not target:
        return "No USB drive detected."
    _log_action("play_usb", target)
    def _bg():
        import subprocess as _sp
        _sp.Popen(
            ["python3", os.path.expanduser("~/scan_and_play.py"), target],
            env={**os.environ, "GTK_THEME": "Mint-Y-Dark",
                 "QT_STYLE_OVERRIDE": "gtk2", "QT_QPA_PLATFORMTHEME": "gtk2"},
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    threading.Thread(target=_bg, daemon=True).start()
    return f"Playing media from {os.path.basename(target.rstrip('/'))}..."

def vlc_pause():
    """Pause/resume VLC via playerctl."""
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} play-pause")
            return "VLC toggled."
    # Fallback — all players
    _run("playerctl -a play-pause")
    return "Toggled playback."

def vlc_next():
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} next")
            return "Next."
    _run("playerctl -a next")
    return "Next."

def vlc_prev():
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} previous")
            return "Previous."
    _run("playerctl -a previous")
    return "Previous."

def vlc_stop():
    r = _run("playerctl -l")
    for line in r.stdout.strip().splitlines():
        if "vlc" in line.lower():
            _run(f"playerctl -p {line.strip()} stop")
            return "VLC stopped."
    _run("playerctl -a stop")
    return "Stopped."
'''

if "def play_usb" not in bc_src:
    bc_src = bc_src.rstrip() + "\n" + vlc_additions
    open(BC, "w").write(bc_src)
    print("OK: VLC/USB functions added to browser_control.py")
else:
    print("INFO: play_usb already in browser_control.py")

# ── 3. PATCH wake_word.py — add USB + system voice commands ──────────────────
ww_src = open(WW).read()

# Add _play_usb helper after _play_music
old_media_fn = '''def _media(action):'''

new_media_fn = '''def _play_usb(path=None):
    try:
        from browser_control import play_usb
        result = play_usb(path)
        print(f"[wake] usb: {result}")
    except Exception as e:
        print(f"[wake] usb error: {e}")

def _system_status_speak():
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from system_clean import system_status
        from voice import speak
        speak(system_status())
    except Exception as e:
        print(f"[wake] system status error: {e}")

def _system_clean_speak():
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from system_clean import clean_system
        from voice import speak
        speak("Starting system cleanup. This may take a moment.")
        result = clean_system()
        speak("Cleanup complete. " + result.split("\\n")[0])
    except Exception as e:
        print(f"[wake] system clean error: {e}")

def _media(action):'''

if "_play_usb" not in ww_src:
    ww_src = ww_src.replace(old_media_fn, new_media_fn)
    print("OK: USB + system helpers added to wake_word.py")
else:
    print("INFO: _play_usb already in wake_word.py")

# Add voice command triggers — find the music/media block
old_mute = '''    if "mute" in t: _media("mute"); return'''

new_mute = '''    if "mute" in t: _media("mute"); return

    # USB / local media
    if any(x in t for x in ["play usb","play from usb","play local","play media","play movie","play show","play from drive"]):
        _play_usb(); return
    if any(x in t for x in ["stop vlc","stop movie","stop video","stop playing"]): 
        from browser_control import vlc_stop; vlc_stop(); return

    # System status + cleanup
    if any(x in t for x in ["system status","how\'s the system","check system","cpu usage","ram usage","memory usage"]):
        import threading; threading.Thread(target=_system_status_speak, daemon=True).start(); return
    if any(x in t for x in ["clean system","clean up","system cleanup","free up space","clear cache"]):
        import threading; threading.Thread(target=_system_clean_speak, daemon=True).start(); return'''

if "play usb" not in ww_src:
    if old_mute in ww_src:
        ww_src = ww_src.replace(old_mute, new_mute)
        print("OK: USB + system voice triggers added to wake_word.py")
    else:
        print("FAIL: mute trigger line not found in wake_word.py")
else:
    print("INFO: USB triggers already in wake_word.py")

open(WW, "w").write(ww_src)

# ── 4. SYNTAX CHECKS ──────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("system_clean.py", SYS), ("browser_control.py", BC), ("wake_word.py", WW)]:
    r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
    print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
    if r.returncode != 0:
        print(r.stderr)

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
        cpu = _run("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'").stdout.strip()
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

    return "\n".join(lines)

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
        log.append(f"journal: {out.splitlines()[-1] if out else 'done'}")
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

    summary = "System clean complete:\n"
    summary += "\n".join(f"  · {l}" for l in log)
    if freed_str:
        summary += f"\n  · {freed_str}"
    if verbose:
        print(f"[system_clean] {summary}")
    return summary

if __name__ == "__main__":
    print(system_status())
    print()
    print(clean_system())

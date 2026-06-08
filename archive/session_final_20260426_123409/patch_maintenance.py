"""
Patch: Fix purge_old_habits + add monthly maintenance scheduler.
1. Fixes purge cutoff from 1 day → 90 days (preserves 28-day habit graph)
2. Removes duplicate purge_old_habits() at bottom of ui.py
3. Adds monthly_maintenance() to memory.py: DB vacuum, backup rotation, log cleanup
4. Wires monthly maintenance into main.py startup (runs if >28 days since last run)

Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_maintenance.py
"""
import os, subprocess

MAIN   = os.path.expanduser("~/vision_assistant/main.py")
UI     = os.path.expanduser("~/vision_assistant/ui.py")
MEM    = os.path.expanduser("~/vision_assistant/memory.py")

# ── 1. FIX purge_old_habits CUTOFF in ui.py (first definition, line ~166) ────
ui_src = open(UI).read()

old_purge = '''def purge_old_habits():
    import sqlite3
    from config import DB_PATH
    cutoff=time.time()-86400
    conn=sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM habit_completions WHERE timestamp < ?",(cutoff,))
    conn.commit(); conn.close()
class EventDialog'''

new_purge = '''def purge_old_habits():
    import sqlite3
    from config import DB_PATH
    # Keep 90 days of completions — needed for graphs and history
    cutoff = time.time() - 90 * 86400
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM habit_completions WHERE timestamp < ?", (cutoff,))
    conn.commit(); conn.close()
class EventDialog'''

if old_purge in ui_src:
    ui_src = ui_src.replace(old_purge, new_purge)
    print("OK: purge_old_habits cutoff fixed → 90 days")
else:
    print("FAIL: first purge_old_habits block not found")

# ── 2. REMOVE duplicate purge_old_habits at bottom of ui.py ──────────────────
old_dup = '''def purge_old_habits():
    import sqlite3
    from config import DB_PATH
    cutoff=time.time()-86400
    conn=sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM habit_completions WHERE timestamp < ?",(cutoff,))
    conn.commit(); conn.close()'''

# Only remove if it still exists (the first replacement above changed one copy)
if old_dup in ui_src:
    ui_src = ui_src.replace(old_dup, "# purge_old_habits defined at module top", 1)
    print("OK: duplicate purge_old_habits removed")
else:
    print("INFO: duplicate already gone or not found (may be fine)")

open(UI, "w").write(ui_src)

# ── 3. ADD monthly_maintenance() to memory.py ─────────────────────────────────
mem_src = open(MEM).read()

maintenance_fn = '''

# ── MONTHLY MAINTENANCE ───────────────────────────────────────────────────────
import glob as _glob, shutil as _shutil, time as _time

MAINTENANCE_STAMP = os.path.expanduser("~/vision_assistant/.last_maintenance")

def monthly_maintenance(force=False):
    """
    Runs at most once every 28 days (or forced).
    - Vacuums the SQLite DB
    - Prunes habit_completions older than 90 days
    - Prunes journal entries older than 2 years
    - Keeps only last 10 backups
    - Removes stale /tmp/vision_* files older than 1 day
    Returns a summary string.
    """
    # Check if due
    if not force:
        try:
            last = float(open(MAINTENANCE_STAMP).read().strip())
            if _time.time() - last < 28 * 86400:
                return None  # Not due yet
        except (FileNotFoundError, ValueError):
            pass  # First run

    log = []
    conn = get_db()

    # Vacuum
    try:
        conn.execute("VACUUM")
        conn.commit()
        log.append("DB vacuumed")
    except Exception as e:
        log.append(f"Vacuum failed: {e}")

    # Prune habit completions > 90 days
    try:
        cutoff = _time.time() - 90 * 86400
        n = conn.execute("SELECT COUNT(*) FROM habit_completions WHERE timestamp < ?",
                         (cutoff,)).fetchone()[0]
        conn.execute("DELETE FROM habit_completions WHERE timestamp < ?", (cutoff,))
        conn.commit()
        log.append(f"Habit completions pruned: {n} old records removed")
    except Exception as e:
        log.append(f"Habit prune failed: {e}")

    # Prune journal entries > 2 years
    try:
        cutoff2 = _time.time() - 730 * 86400
        n2 = conn.execute("SELECT COUNT(*) FROM journal WHERE timestamp < ?",
                          (cutoff2,)).fetchone()[0]
        conn.execute("DELETE FROM journal WHERE timestamp < ?", (cutoff2,))
        conn.commit()
        log.append(f"Journal pruned: {n2} entries older than 2 years removed")
    except Exception as e:
        log.append(f"Journal prune failed: {e}")

    conn.close()

    # Keep last 10 backups
    try:
        backup_dir = os.path.expanduser("~/vision_assistant/backups")
        backups = sorted(_glob.glob(os.path.join(backup_dir, "*")))
        to_remove = backups[:-10]
        for b in to_remove:
            _shutil.rmtree(b, ignore_errors=True)
        if to_remove:
            log.append(f"Backups pruned: kept last 10, removed {len(to_remove)}")
        else:
            log.append("Backups OK: within limit")
    except Exception as e:
        log.append(f"Backup prune failed: {e}")

    # Clean stale /tmp/vision_* files
    try:
        stale_cutoff = _time.time() - 86400
        removed = 0
        for f in _glob.glob("/tmp/vision_*"):
            try:
                if os.path.getmtime(f) < stale_cutoff:
                    os.remove(f)
                    removed += 1
            except: pass
        log.append(f"Temp files cleaned: {removed} removed")
    except Exception as e:
        log.append(f"Temp cleanup failed: {e}")

    # Write timestamp
    try:
        open(MAINTENANCE_STAMP, "w").write(str(_time.time()))
    except: pass

    summary = "Monthly maintenance complete:\\n" + "\\n".join(f"  · {l}" for l in log)
    print(f"[maintenance] {summary}")
    return summary
'''

# Insert before the last line or after imports — find a safe anchor
anchor = "\n# ── MONTHLY MAINTENANCE"
if anchor not in mem_src:
    # Append before end of file
    mem_src = mem_src.rstrip() + "\n" + maintenance_fn
    open(MEM, "w").write(mem_src)
    print("OK: monthly_maintenance() added to memory.py")
else:
    print("INFO: monthly_maintenance already in memory.py")

# ── 4. WIRE INTO main.py ──────────────────────────────────────────────────────
main_src = open(MAIN).read()

old_wake = '''    try:
        from wake_word import start_in_background
        start_in_background()
        print("[main] Wake word detector started.")
    except Exception as e:
        print(f"[main] Wake word skipped: {e}")'''

new_wake = '''    try:
        from wake_word import start_in_background
        start_in_background()
        print("[main] Wake word detector started.")
    except Exception as e:
        print(f"[main] Wake word skipped: {e}")

    # Monthly maintenance — runs silently if due (every 28 days)
    try:
        from memory import monthly_maintenance
        import threading as _mth
        def _run_maintenance():
            result = monthly_maintenance()
            if result:
                try:
                    from briefing import send_notification
                    send_notification("Echo Maintenance", "Monthly cleanup completed.", urgency="low")
                except: pass
        _mth.Thread(target=_run_maintenance, daemon=True).start()
    except Exception as e:
        print(f"[main] Maintenance skipped: {e}")'''

if old_wake in main_src:
    main_src = main_src.replace(old_wake, new_wake)
    open(MAIN, "w").write(main_src)
    print("OK: monthly maintenance wired into main.py")
else:
    print("FAIL: wake word block not found in main.py")

# ── 5. SYNTAX CHECKS ──────────────────────────────────────────────────────────
py = "/home/jesus999l/vision_env/bin/python3"
for label, path in [("ui.py", UI), ("memory.py", MEM), ("main.py", MAIN)]:
    r = subprocess.run([py, "-m", "py_compile", path], capture_output=True, text=True)
    print(f"{'OK' if r.returncode == 0 else 'ERR'}: {label}")
    if r.returncode != 0:
        print(r.stderr)

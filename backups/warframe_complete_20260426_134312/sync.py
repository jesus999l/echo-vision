"""
Sync module - serializes state to JSON for Android/Echo portability.
Designed to work offline-first with optional cloud sync.
"""
import os
import json
import time
import sqlite3
import hashlib
import datetime
from config import DB_PATH

SYNC_DIR  = os.path.expanduser("~/vision_assistant/sync")
SYNC_FILE = os.path.join(SYNC_DIR, "state.json")
os.makedirs(SYNC_DIR, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def export_state():
    """Export full app state to JSON for Android sync."""
    conn = get_db()
    state = {
        "exported_at": time.time(),
        "exported_at_str": datetime.datetime.now().isoformat(),
        "goals": [dict(r) for r in conn.execute("SELECT * FROM goals").fetchall()],
        "habits": [dict(r) for r in conn.execute("SELECT * FROM habits WHERE active=1").fetchall()],
        "journal": [dict(r) for r in conn.execute(
            "SELECT * FROM journal ORDER BY timestamp DESC LIMIT 100").fetchall()],
        "calendar_events": [dict(r) for r in conn.execute(
            "SELECT * FROM calendar_events ORDER BY start_time DESC LIMIT 200").fetchall()],
        "habit_completions": [dict(r) for r in conn.execute(
            "SELECT * FROM habit_completions ORDER BY timestamp DESC LIMIT 500").fetchall()],
    }
    conn.close()
    with open(SYNC_FILE, "w") as f:
        json.dump(state, f, indent=2)
    checksum = hashlib.md5(json.dumps(state).encode()).hexdigest()
    return SYNC_FILE, checksum

def import_state(json_path, merge=True):
    """Import state from JSON (from Android). merge=True keeps existing data."""
    with open(json_path) as f:
        state = json.load(f)
    conn = get_db()
    imported = {"goals":0,"habits":0,"journal":0,"events":0}
    if not merge:
        # Full replace - careful!
        conn.execute("DELETE FROM goals")
        conn.execute("DELETE FROM habits")

    for g in state.get("goals",[]):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO goals (id,title,description,category,target_date,progress,created_at,completed,status) VALUES (?,?,?,?,?,?,?,?,?)",
                (g["id"],g["title"],g.get("description",""),g.get("category","personal"),
                 g.get("target_date"),g.get("progress",0),g.get("created_at",time.time()),
                 g.get("completed",0),g.get("status","later"))
            )
            imported["goals"] += 1
        except: pass

    for h in state.get("habits",[]):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO habits (id,name,description,frequency,created_at,active,target,period) VALUES (?,?,?,?,?,?,?,?)",
                (h["id"],h["name"],h.get("description",""),h.get("frequency","daily"),
                 h.get("created_at",time.time()),1,h.get("target",1),h.get("period","daily"))
            )
            imported["habits"] += 1
        except: pass

    for j in state.get("journal",[]):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO journal (id,timestamp,title,content,mood,tags) VALUES (?,?,?,?,?,?)",
                (j["id"],j["timestamp"],j.get("title",""),j["content"],j.get("mood",3),j.get("tags","[]"))
            )
            imported["journal"] += 1
        except: pass

    for ev in state.get("calendar_events",[]):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO calendar_events (id,title,description,start_time,end_time,all_day,color) VALUES (?,?,?,?,?,?,?)",
                (ev["id"],ev["title"],ev.get("description",""),ev["start_time"],
                 ev.get("end_time",ev["start_time"]+3600),ev.get("all_day",0),ev.get("color","#7c6af7"))
            )
            imported["events"] += 1
        except: pass

    conn.commit()
    conn.close()
    return imported

def get_sync_status():
    """Check last sync time and file size."""
    if not os.path.exists(SYNC_FILE):
        return {"synced": False, "last_sync": None, "size": 0}
    stat = os.stat(SYNC_FILE)
    return {
        "synced": True,
        "last_sync": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%b %d %H:%M"),
        "size_kb": round(stat.st_size / 1024, 1),
        "path": SYNC_FILE
    }

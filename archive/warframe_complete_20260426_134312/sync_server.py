"""
Echo WiFi Sync Server — serves data to Android Echo Sync app.
"""
import json, socket, threading, time, sqlite3, datetime
from config import DB_PATH

SYNC_PORT = 59997  # different from IPC port

_server_thread = None
_running = False

def _get_sync_data():
    """Bundle all Echo data for the Android app."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        goals   = [dict(r) for r in conn.execute("SELECT * FROM goals WHERE completed=0 ORDER BY created_at DESC").fetchall()]
        habits  = [dict(r) for r in conn.execute("SELECT * FROM habits WHERE active=1").fetchall()]
        events  = [dict(r) for r in conn.execute(
            "SELECT * FROM calendar_events WHERE start_time>=? ORDER BY start_time LIMIT 50",
            (time.time() - 86400,)).fetchall()]
        journal = [dict(r) for r in conn.execute(
            "SELECT * FROM journal ORDER BY timestamp DESC LIMIT 50").fetchall()]
        notes   = [dict(r) for r in conn.execute(
            "SELECT * FROM quick_notes ORDER BY updated_at DESC LIMIT 50").fetchall()]
        # Add today's completion count to each habit
        today = datetime.date.today().isoformat()
        for h in habits:
            count = conn.execute(
                "SELECT COUNT(*) FROM habit_completions WHERE habit_id=? AND date_str=?",
                (h["id"], today)).fetchone()[0]
            h["today_count"] = count
    finally:
        conn.close()
    return {
        "goals": goals, "habits": habits, "events": events,
        "journal": journal, "notes": notes, "quick_notes": notes,
        "sync_time": time.time()
    }

def _handle_push(data):
    """Handle actions pushed from Android app."""
    action = data.get("action")
    payload = data.get("data", {})
    try:
        conn = sqlite3.connect(DB_PATH)
        if action == "log_habit":
            hid = payload.get("id")
            today = datetime.date.today().isoformat()
            conn.execute(
                "INSERT INTO habit_completions (habit_id,date_str,timestamp) VALUES (?,?,?)",
                (hid, today, time.time()))
        elif action == "add_journal":
            conn.execute(
                "INSERT INTO journal (content,mood,timestamp) VALUES (?,?,?)",
                (payload.get("content",""), payload.get("mood",3), payload.get("timestamp",time.time())))
        elif action == "add_task":
            conn.execute(
                "INSERT INTO goals (title,description,category,created_at,priority) VALUES (?,?,?,?,?)",
                (payload.get("title",""), "", payload.get("category","personal"),
                 time.time(), payload.get("priority","normal")))
        conn.commit()
        conn.close()
        # Signal UI refresh
        import os
        open(os.path.expanduser("~/vision_assistant/.ui_refresh"), "w").close()
    except Exception as e:
        print(f"[sync] push error: {e}")

def _handle_client(conn, addr):
    try:
        data = b""
        conn.settimeout(5)
        while True:
            chunk = conn.recv(1024)
            if not chunk: break
            data += chunk
            if b"\n" in data: break
        msg = data.decode("utf-8").strip()
        if msg == "ECHO_SYNC_REQUEST":
            payload = json.dumps(_get_sync_data())
            conn.sendall(payload.encode("utf-8"))
        elif msg.startswith("ECHO_SYNC_PUSH:"):
            push_data = json.loads(msg[15:])
            _handle_push(push_data)
            conn.sendall(b"OK")
    except Exception as e:
        print(f"[sync] client error: {e}")
    finally:
        conn.close()

def start_sync_server():
    global _server_thread, _running
    if _running: return
    _running = True
    def _serve():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", SYNC_PORT))
        srv.listen(5)
        srv.settimeout(1)
        print(f"[sync] Server running on port {SYNC_PORT}")
        while _running:
            try:
                conn, addr = srv.accept()
                threading.Thread(target=_handle_client, args=(conn,addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[sync] server error: {e}")
                break
        srv.close()
    _server_thread = threading.Thread(target=_serve, daemon=True)
    _server_thread.start()
    return SYNC_PORT

def stop_sync_server():
    global _running
    _running = False

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "unknown"

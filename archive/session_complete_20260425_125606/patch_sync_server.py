"""
Patch: add WiFi sync server to Echo desktop so the Android app can connect.
Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_sync_server.py
"""
import subprocess

MAIN = "/home/jesus999l/vision_assistant/main.py"
UI   = "/home/jesus999l/vision_assistant/ui.py"

# ── sync_server.py ────────────────────────────────────────────────────────────
SYNC_SERVER = '''"""
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
            if b"\\n" in data: break
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
'''

with open("/home/jesus999l/vision_assistant/sync_server.py", "w") as f:
    f.write(SYNC_SERVER)
print("OK: sync_server.py created")

# ── ui.py: add sync section to settings ──────────────────────────────────────
ui_src = open(UI).read()

old = '''        section("SYNC / ANDROID",ACCENT3)
        s_frame=tk.Frame(inner,bg=BG3,padx=14,pady=12); s_frame.pack(fill="x",padx=10,pady=(0,6))
        try:
            from sync import get_sync_status
            status=get_sync_status()
            if status["synced"]:
                tk.Label(s_frame,text=f"Last sync: {status['last_sync']}  ({status['size_kb']} KB)",
                         bg=BG3,fg=ACCENT3,font=FONT_TINY).pack(anchor="w",pady=(0,6))
            else:
                tk.Label(s_frame,text="Never synced",bg=BG3,fg=TEXT3,font=FONT_TINY).pack(anchor="w",pady=(0,6))
        except: pass
        def do_sync():
            try:
                from sync import export_state
                path,checksum=export_state()
                self.append_chat("system",f"✓ Synced to {path}")
                self.open_page("settings")
            except Exception as e:
                self.append_chat("system",f"Sync error: {e}")
        sbtn(s_frame,"Export State (for Android)",do_sync,bg=ACCENT3,fg=BG,px=10,py=4).pack(anchor="w")
        tk.Label(s_frame,text="Saves to ~/vision_assistant/sync/state.json",
                 bg=BG3,fg=TEXT3,font=FONT_TINY).pack(anchor="w",pady=(4,0))'''

new = '''        section("SYNC / ANDROID",ACCENT3)
        s_frame=tk.Frame(inner,bg=BG3,padx=14,pady=12); s_frame.pack(fill="x",padx=10,pady=(0,6))
        # Sync server status
        _sync_status={"running":False,"port":None}
        def _refresh_sync_status():
            try:
                from sync_server import _running, SYNC_PORT, get_local_ip
                if _running:
                    ip=get_local_ip()
                    sync_lbl.config(text=f"✓ Server running  ·  {ip}:{SYNC_PORT}",fg=ACCENT3)
                    start_btn.config(text="Stop Sync Server",bg=DANGER)
                else:
                    sync_lbl.config(text="Server stopped",fg=TEXT3)
                    start_btn.config(text="Start Sync Server",bg=ACCENT3)
            except: pass
        sync_lbl=tk.Label(s_frame,text="Server stopped",bg=BG3,fg=TEXT3,font=FONT_TINY)
        sync_lbl.pack(anchor="w",pady=(0,4))
        def toggle_sync():
            try:
                from sync_server import start_sync_server, stop_sync_server, _running, get_local_ip, SYNC_PORT
                if _running:
                    stop_sync_server()
                else:
                    port=start_sync_server()
                    ip=get_local_ip()
                    self.show_toast(f"Sync server started — {ip}:{port}",color=ACCENT3)
                inner.after(500,_refresh_sync_status)
            except Exception as e:
                self.show_toast(f"Sync error: {e}",color=DANGER)
        start_btn=sbtn(s_frame,"Start Sync Server",toggle_sync,bg=ACCENT3,fg=BG,px=10,py=4)
        start_btn.pack(anchor="w",pady=(0,4))
        tk.Label(s_frame,text="Open Echo Sync on Android → Settings → enter this IP",
                 bg=BG3,fg=TEXT3,font=FONT_TINY,wraplength=260).pack(anchor="w")
        inner.after(500,_refresh_sync_status)'''

if old in ui_src:
    ui_src = ui_src.replace(old, new)
    print("OK: sync section in settings")
else:
    print("FAIL: sync section not found")

open(UI, "w").write(ui_src)

# Syntax check
for label, path in [("ui.py", UI), ("sync_server.py", "/home/jesus999l/vision_assistant/sync_server.py")]:
    r = subprocess.run(
        ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", path],
        capture_output=True, text=True
    )
    print(f"{'OK' if r.returncode==0 else 'ERR'}: {label}")
    if r.returncode != 0: print(r.stderr)

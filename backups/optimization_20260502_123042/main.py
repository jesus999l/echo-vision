"""
Vision Assistant — entry point.
"""
import tkinter as tk
import threading, socket, json, sys, os, shutil, glob, time

sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
from config import IPC_HOST, IPC_PORT, IPC_MAGIC

VA_DIR     = os.path.expanduser("~/vision_assistant")
BACKUP_DIR = os.path.join(VA_DIR, "backups")
CRITICAL_FILES = [
    "ui.py", "ai.py", "main.py", "memory.py", "config.py",
    "voice.py", "personality.py", "browser_control.py",
    "wake_word.py", "briefing.py",
]

# ── BACKUP / RECOVERY ─────────────────────────────────────────────────────────
def auto_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest  = os.path.join(BACKUP_DIR, stamp)
    os.makedirs(dest, exist_ok=True)
    backed = []
    for fname in CRITICAL_FILES:
        src = os.path.join(VA_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, fname))
            backed.append(fname)
    # Keep last 5 backups
    for old in sorted(glob.glob(os.path.join(BACKUP_DIR, "*")))[:-5]:
        shutil.rmtree(old, ignore_errors=True)
    print(f"[backup] {stamp} — {len(backed)} files")

def _last_good_backup():
    for b in sorted(glob.glob(os.path.join(BACKUP_DIR, "*")), reverse=True):
        ui = os.path.join(b, "ui.py")
        if os.path.exists(ui) and os.path.getsize(ui) > 10000:
            return b
    return None

def safe_import_ui():
    try:
        from ui import ChatOverlay
        return ChatOverlay
    except Exception as e:
        print(f"[ui] Import failed: {e} — attempting recovery...")
        backup = _last_good_backup()
        if backup:
            for fname in CRITICAL_FILES:
                src = os.path.join(backup, fname)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(VA_DIR, fname))
            try:
                import importlib, ui as _ui
                importlib.reload(_ui)
                return _ui.ChatOverlay
            except Exception as e2:
                print(f"[ui] Recovery failed: {e2}")
    return None

# ── IPC ───────────────────────────────────────────────────────────────────────
def send_to_running_instance(screenshot_path, ocr_text):
    try:
        payload = json.dumps({
            "magic": IPC_MAGIC,
            "screenshot": screenshot_path,
            "ocr": ocr_text,
        }).encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((IPC_HOST, IPC_PORT))
        s.sendall(payload)
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False

def start_ipc_server(app):
    def _listen():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((IPC_HOST, IPC_PORT))
        srv.listen(5)
        srv.settimeout(1)
        while True:
            try:
                conn, _ = srv.accept()
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk: break
                    data += chunk
                conn.close()
                msg = json.loads(data.decode())
                if msg.get("magic") == IPC_MAGIC:
                    app.root.after(0, lambda m=msg: app.handle_capture(m["screenshot"], m["ocr"]))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[ipc] {e}")
    threading.Thread(target=_listen, daemon=True).start()

# ── APP ───────────────────────────────────────────────────────────────────────
class VisionApp:
    def __init__(self, ChatOverlay):
        self.ChatOverlay  = ChatOverlay
        self.root         = tk.Tk()
        self.root.withdraw()
        self.chat_window  = None

    def _get_or_create_window(self):
        if self.chat_window is None or not self.chat_window.winfo_exists():
            self.chat_window = self.ChatOverlay(self.root)
        self.chat_window.lift()
        self.chat_window.focus_force()
        return self.chat_window

    def handle_capture(self, screenshot_path, ocr_text):
        threading.Thread(target=self._do_capture,
                         args=(screenshot_path, ocr_text), daemon=True).start()

    def _do_capture(self, screenshot_path, ocr_text):
        from search import reverse_image_search
        reverse_image_search(screenshot_path, ocr_text)
        self.root.after(0, lambda: self._show_window(screenshot_path, ocr_text))

    def _show_window(self, screenshot_path, ocr_text):
        win = self._get_or_create_window()
        win.set_capture(screenshot_path, ocr_text)
        self.root.after(500, win.append_divider)
        win.display_image(screenshot_path)
        if ocr_text.strip():
            win.append_chat("OCR", ocr_text.strip())
        else:
            win.append_chat("System", "No text detected.")

    def run(self, ui_only=False):
        from capture import capture_area, ocr_image, cleanup_stale_processes
        cleanup_stale_processes()

        if ui_only:
            if send_to_running_instance("", ""):
                print("[main] Sent to existing instance.")
                return
            start_ipc_server(self)
            self.root.after(100, self._get_or_create_window)
            self.root.mainloop()
            return

        screenshot_path = capture_area()
        if not screenshot_path:
            print("[main] Screenshot cancelled.")
            return
        ocr_text = ocr_image(screenshot_path)
        if send_to_running_instance(screenshot_path, ocr_text):
            print("[main] Sent to existing instance.")
            return
        start_ipc_server(self)
        self.handle_capture(screenshot_path, ocr_text)
        self.root.mainloop()

# ── ENTRY ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    auto_backup()

    try:
        from briefing import get_morning_briefing, show_morning_briefing_notification, speak_morning_briefing, start_reminder_daemon

        # Check skip flags: --no-briefing arg OR settings.json skip_briefing=true
        _skip_briefing = "--no-briefing" in sys.argv
        if not _skip_briefing:
            try:
                import json as _j, os as _o
                _cfg = _j.load(open(_o.path.expanduser("~/vision_assistant/settings.json")))
                _skip_briefing = bool(_cfg.get("skip_briefing", False))
            except: pass

        # Reminder daemon always runs regardless of skip
        start_reminder_daemon()

        if not _skip_briefing:
            b = get_morning_briefing()
            show_morning_briefing_notification(b)
            # Speak briefing if enabled
            try:
                import json as _j, os as _o
                _cfg = _j.load(open(_o.path.expanduser("~/vision_assistant/settings.json")))
                if _cfg.get("speak_briefing", False):
                    import threading as _th
                    _th.Thread(target=speak_morning_briefing, args=(b,), daemon=True).start()
            except: pass
            print("[main] Briefing + reminder daemon started.")
        else:
            print("[main] Briefing skipped (--no-briefing or settings). Reminder daemon running.")
    except Exception as e:
        print(f"[main] Briefing skipped: {e}")

    try:
        from wake_word import start_in_background
        start_in_background()
        print("[main] Wake word detector started.")
    except Exception as e:
        print(f"[main] Wake word skipped: {e}")

    # Push-to-talk
    try:
        from ptt import start_ptt
        start_ptt()
    except Exception as e:
        print(f"[main] PTT skipped: {e}")

    # Game input recorder — auto-starts when Warframe launches
    try:
        from echo_game_recorder import start_game_recorder
        start_game_recorder()
    except Exception as e:
        print(f"[main] Game recorder skipped: {e}")

    # Browser server — Echo Firefox sidebar
    try:
        from echo_browser_server import start_browser_server
        start_browser_server()
    except Exception as e:
        print(f"[main] Browser server skipped: {e}")

    # Self-adjustment monitor
    try:
        from self_adjust import start_self_adjust
        start_self_adjust()
    except Exception as e:
        print(f"[main] Self-adjust skipped: {e}")

    # BOINC schedule — suspend during active hours
    try:
        import subprocess as _bc
        _bc.Popen(["bash", "/home/jesus999l/boinc-schedule.sh"],
                  stdout=_bc.DEVNULL, stderr=_bc.DEVNULL)
        print("[main] BOINC schedule applied.")
    except Exception as e:
        print(f"[main] BOINC skipped: {e}")

    # Bluetooth smart switch — auto HFP when Discord runs
    try:
        import subprocess as _bts
        _bts.Popen(["bash", "/home/jesus999l/bt-discord-switch.sh"],
                   stdout=_bts.DEVNULL, stderr=_bts.DEVNULL)
        print("[main] Bluetooth auto-switch started.")
    except Exception as e:
        print(f"[main] BT switch skipped: {e}")

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
        print(f"[main] Maintenance skipped: {e}")

    ChatOverlay = safe_import_ui()
    if ChatOverlay is None:
        print("FATAL: Could not load UI.")
        sys.exit(1)

    app = VisionApp(ChatOverlay)
    app.run(ui_only="--ui" in sys.argv)

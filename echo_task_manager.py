#!/usr/bin/env python3
"""
echo_task_manager.py — Hermes → Echo Loop Bridge
Watches ~/queue/ for task JSON files. Dispatches to echo_research_loop.
Writes results back to ~/queue/results/.

Task file format (~/queue/YYYYMMDD_HHMMSS_slug.json):
{
  "objective": "fix ChromaDB wiring",
  "constraints": ["do not modify memory.db", "use nomic-embed-text only"],
  "priority": "high",
  "mode": "semi",           // optional override
  "source": "hermes",       // who sent it
  "max_retries": 3
}

Result file written to ~/queue/results/YYYYMMDD_HHMMSS_slug_result.json:
{
  "task": {...original task...},
  "status": "success|partial|failed",
  "steps_run": 4,
  "steps_ok": 3,
  "summary": "str",
  "learnings": ["str"],
  "timestamp": "ISO"
}

Usage:
  python3 echo_task_manager.py          # run daemon
  python3 echo_task_manager.py --once   # process queue once, exit
  python3 echo_task_manager.py --kill   # send kill signal to running loop

Kill switch (HTTP):
  POST http://127.0.0.1:7799/kill       {"reason": "string"}
  GET  http://127.0.0.1:7799/status
"""

import os, sys, json, time, signal, logging, threading, subprocess
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ── CONFIG ────────────────────────────────────────────────────────────

HOME         = Path.home()
QUEUE_DIR    = HOME / "queue"
RESULTS_DIR  = QUEUE_DIR / "results"
PROCESSED    = QUEUE_DIR / "processed"
LOOP_SCRIPT  = HOME / "vision_assistant/echo_research_loop.py"
LOG_FILE     = HOME / "vision_assistant/logs/echo_task_manager.log"
KILL_FILE    = HOME / ".echo_kill"
PORT         = 7799
POLL_SECS    = 5

# ── LOGGING ───────────────────────────────────────────────────────────

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("echo_tasks")

# ── GLOBALS ───────────────────────────────────────────────────────────

_current_proc = None   # running loop subprocess
_running = True
_status = {"state": "idle", "current_task": None, "tasks_run": 0, "last_result": None}

# ── QUEUE UTILS ───────────────────────────────────────────────────────

def setup_dirs():
    for d in [QUEUE_DIR, RESULTS_DIR, PROCESSED]:
        d.mkdir(parents=True, exist_ok=True)

def read_task(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
        task = json.loads(raw)
        # Validate required fields
        if not task.get("objective"):
            log.warning(f"Task {path.name} missing 'objective', skipping")
            return None
        task["_file"] = str(path)
        task["_id"] = path.stem
        return task
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in {path.name}: {e}")
        return None
    except Exception as e:
        log.error(f"Could not read {path.name}: {e}")
        return None

def get_pending_tasks() -> list:
    """Return sorted list of pending task files (oldest first)."""
    files = sorted(QUEUE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime)
    tasks = []
    for f in files:
        t = read_task(f)
        if t:
            tasks.append(t)
    return tasks

def write_result(task: dict, status: str, summary: str, learnings: list, steps_run=0, steps_ok=0):
    ts = datetime.now().isoformat(timespec="seconds")
    result = {
        "task_id": task.get("_id"),
        "objective": task.get("objective"),
        "source": task.get("source", "unknown"),
        "status": status,
        "steps_run": steps_run,
        "steps_ok": steps_ok,
        "summary": summary,
        "learnings": learnings,
        "timestamp": ts
    }
    out_name = f"{task['_id']}_result.json"
    out_path = RESULTS_DIR / out_name
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info(f"Result written: {out_path.name}")
    return out_path

def archive_task(task_path: str):
    src = Path(task_path)
    if src.exists():
        dst = PROCESSED / src.name
        src.rename(dst)

# ── KILL SWITCH ───────────────────────────────────────────────────────

def kill_loop(reason="kill signal received"):
    global _current_proc
    log.warning(f"KILL: {reason}")
    KILL_FILE.write_text(reason)
    if _current_proc and _current_proc.poll() is None:
        _current_proc.terminate()
        try:
            _current_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _current_proc.kill()
        log.warning("Loop process terminated.")
    _current_proc = None
    _status["state"] = "killed"
    _status["current_task"] = None

def check_kill():
    """Return True and consume kill file if kill was requested."""
    if KILL_FILE.exists():
        reason = KILL_FILE.read_text()
        KILL_FILE.unlink()
        return True, reason
    return False, None

# ── DISPATCH ──────────────────────────────────────────────────────────

def dispatch_task(task: dict) -> dict:
    """
    Run echo_research_loop.py for this task as a subprocess.
    Returns result dict.
    """
    global _current_proc

    objective = task["objective"]
    mode = task.get("mode")  # optional override
    constraints = task.get("constraints", [])

    log.info(f"Dispatching: {objective}")
    log.info(f"  mode: {mode or 'auto'} | priority: {task.get('priority','medium')}")

    # Build objective string with constraints embedded
    full_objective = objective
    if constraints:
        full_objective += " [constraints: " + "; ".join(constraints) + "]"

    cmd = [sys.executable, str(LOOP_SCRIPT), full_objective]
    if mode:
        cmd += ["--mode", mode]

    _status["state"] = "running"
    _status["current_task"] = objective

    try:
        _current_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(HOME / "vision_assistant")
        )

        lines = []
        for line in _current_proc.stdout:
            line = line.rstrip()
            log.info(f"  [loop] {line}")
            lines.append(line)

            # Check kill mid-run
            killed, reason = check_kill()
            if killed:
                kill_loop(reason)
                return {
                    "status": "killed",
                    "summary": f"Killed mid-run: {reason}",
                    "learnings": [],
                    "steps_run": 0,
                    "steps_ok": 0
                }

        try:
            _current_proc.wait()
            rc = _current_proc.returncode
        except AttributeError:
            rc = 1  # process was killed mid-run

    except Exception as e:
        log.error(f"Dispatch error: {e}")
        return {
            "status": "failed",
            "summary": f"Dispatch error: {e}",
            "learnings": [],
            "steps_run": 0,
            "steps_ok": 0
        }
    finally:
        _current_proc = None
        _status["state"] = "idle"
        _status["current_task"] = None

    # Parse result from loop output
    status = "success" if rc == 0 else "failed"
    summary = next((l for l in reversed(lines) if "Loop complete" in l or "Aborted" in l or "Halted" in l), "")
    learnings = [l for l in lines if "✓" in l or "✗" in l or "Learned" in l][:10]

    return {
        "status": status,
        "summary": summary or f"Exit code {rc}",
        "learnings": learnings,
        "steps_run": sum(1 for l in lines if "Step " in l and "Exec" in l),
        "steps_ok": sum(1 for l in lines if "✓ Success" in l),
    }

# ── HTTP CONTROL SERVER ───────────────────────────────────────────────

class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # silence access log

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/status":
            self._json({**_status, "tasks_queued": len(list(QUEUE_DIR.glob("*.json")))})
        elif p == "/results":
            results = []
            for f in sorted(RESULTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
                try:
                    results.append(json.loads(f.read_text()))
                except:
                    pass
            self._json(results)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        ln = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(ln)) if ln else {}

        if p == "/kill":
            reason = body.get("reason", "HTTP kill request")
            kill_loop(reason)
            self._json({"ok": True, "reason": reason})

        elif p == "/task":
            # Enqueue a task directly via HTTP (Hermes webhook)
            if not body.get("objective"):
                self._json({"error": "missing objective"}, 400)
                return
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            slug = re.sub(r"[^\w]", "-", body["objective"][:30].lower())
            path = QUEUE_DIR / f"{ts}_{slug}.json"
            path.write_text(json.dumps(body, indent=2))
            log.info(f"Task enqueued via HTTP: {path.name}")
            self._json({"ok": True, "queued": path.name})

        else:
            self._json({"error": "not found"}, 404)

import re  # needed for /task slug

def start_control_server():
    server = HTTPServer(("127.0.0.1", PORT), ControlHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info(f"Control server on port {PORT} (kill: POST /kill, status: GET /status)")
    return server

# ── MAIN LOOP ─────────────────────────────────────────────────────────

def run_daemon():
    global _running

    setup_dirs()
    log.info("=" * 50)
    log.info("Echo Task Manager")
    log.info(f"Queue : {QUEUE_DIR}")
    log.info(f"Loop  : {LOOP_SCRIPT}")
    log.info(f"Port  : {PORT}")
    log.info("=" * 50)

    if not LOOP_SCRIPT.exists():
        log.error(f"Loop script not found: {LOOP_SCRIPT}")
        sys.exit(1)

    start_control_server()

    def shutdown(sig, frame):
        global _running
        _running = False
        log.info("Shutting down task manager...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    log.info(f"Watching {QUEUE_DIR} for tasks (poll every {POLL_SECS}s)...")

    while _running:
        tasks = get_pending_tasks()
        if tasks:
            task = tasks[0]  # process one at a time
            log.info(f"\nFound task: {task['_id']} ({task.get('priority','medium')} priority)")

            result = dispatch_task(task)

            write_result(
                task,
                status=result["status"],
                summary=result["summary"],
                learnings=result["learnings"],
                steps_run=result["steps_run"],
                steps_ok=result["steps_ok"]
            )

            archive_task(task["_file"])

            _status["tasks_run"] += 1
            _status["last_result"] = result["status"]

        time.sleep(POLL_SECS)

def run_once():
    setup_dirs()
    tasks = get_pending_tasks()
    if not tasks:
        log.info("No pending tasks.")
        return
    for task in tasks:
        log.info(f"Processing: {task['_id']}")
        result = dispatch_task(task)
        write_result(task, **result)
        archive_task(task["_file"])

# ── ENTRY POINT ───────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--kill" in args:
        # Send kill to running manager
        import urllib.request
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{PORT}/kill",
                data=json.dumps({"reason": "CLI kill"}).encode(),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=3)
            print("Kill signal sent.")
        except:
            # Fallback: write kill file
            KILL_FILE.write_text("CLI kill")
            print("Kill file written.")
        sys.exit(0)

    if "--status" in args:
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/status", timeout=3)
            print(json.dumps(json.loads(resp.read()), indent=2))
        except:
            print("Task manager not running.")
        sys.exit(0)

    if "--once" in args:
        run_once()
    else:
        run_daemon()

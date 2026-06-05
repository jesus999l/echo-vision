#!/usr/bin/env python3
"""
echo_deploy_package.py
Run once — deploys 3 things:
  1. Calendar importer (Google ICS → memory.db)
  2. Scribe pipeline (Google Chat/Drive → Obsidian Subconscious)
  3. Echo REST endpoint (FastAPI, port 8765)
"""
import os, sys, subprocess

BASE   = "/home/jesus999l/vision_assistant"
VAULT  = "/home/jesus999l/Documents/ObsidianVault/Echo"
TAKEOUT= "/home/jesus999l/Documents/Google_Takeout/Takeout"
VENV   = "/home/jesus999l/vision_env/bin/python3"

# ── 1. CALENDAR IMPORT ────────────────────────────────────────────────────────
def import_calendar():
    import re, sqlite3, datetime
    ics  = f"{TAKEOUT}/Calendar/jesuslopez8234@gmail.com.ics"
    db   = f"{BASE}/memory.db"
    if not os.path.exists(ics):
        print("[calendar] ICS not found, skipping")
        return
    with open(ics, encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', raw, re.DOTALL)
    conn = sqlite3.connect(db)
    imported = skipped = 0
    for e in events:
        def get(field):
            m = re.search(rf'{field}[^:]*:(.*)', e)
            return m.group(1).strip().replace("\\n", " ").replace("\\,", ",") if m else ""
        title   = get("SUMMARY")
        dtstart = get("DTSTART")
        dtend   = get("DTEND")
        desc    = get("DESCRIPTION")
        if not title or not dtstart:
            skipped += 1
            continue
        try:
            ds = dtstart.replace("Z","")[:15]
            fmt = "%Y%m%dT%H%M%S" if "T" in ds else "%Y%m%d"
            dt  = datetime.datetime.strptime(ds[:15] if "T" in ds else ds[:8], fmt)
            ts  = dt.timestamp()
            de  = dtend.replace("Z","")[:15] if dtend else ""
            if de:
                fmt2 = "%Y%m%dT%H%M%S" if "T" in de else "%Y%m%d"
                te = datetime.datetime.strptime(de[:15] if "T" in de else de[:8], fmt2).timestamp()
            else:
                te = ts + 3600
            all_day = 0 if "T" in dtstart else 1
            conn.execute(
                "INSERT OR IGNORE INTO calendar_events (title,description,start_time,end_time,all_day) VALUES (?,?,?,?,?)",
                (title, desc[:300], ts, te, all_day)
            )
            imported += 1
        except Exception as ex:
            skipped += 1
    conn.commit()
    conn.close()
    print(f"[calendar] imported {imported}, skipped {skipped}")

# ── 2. SCRIBE PIPELINE ────────────────────────────────────────────────────────
def run_scribe():
    import json, glob, shutil, datetime
    sub = f"{VAULT}/Subconscious"
    os.makedirs(sub, exist_ok=True)
    count = 0

    # Google Chat messages
    chat_jsons = glob.glob(f"{TAKEOUT}/Google Chat/Users/*/messages*.json") + \
                 glob.glob(f"{TAKEOUT}/Google Chat/Users/*/*.json")
    for jf in chat_jsons:
        try:
            with open(jf) as f:
                data = json.load(f)
            msgs = data.get("messages", [])
            if not msgs:
                continue
            lines = [f"# Google Chat Import\nsource: {os.path.basename(jf)}\n"]
            for m in msgs[:200]:
                sender = m.get("creator",{}).get("name","?")
                text   = m.get("text","").strip()
                ts     = m.get("created_date","")
                if text:
                    lines.append(f"[{ts}] {sender}: {text}")
            if len(lines) > 2:
                out = f"{sub}/gchat-import-{count}.md"
                with open(out,"w") as f:
                    f.write("\n".join(lines))
                count += 1
        except Exception:
            pass

    # Drive docs — copy text-based ones
    drive_root = f"{TAKEOUT}/Drive"
    for root, dirs, files in os.walk(drive_root):
        for fn in files:
            if fn.endswith((".txt",".md",".rst")):
                src = os.path.join(root, fn)
                dst = f"{sub}/drive-{fn}"
                shutil.copy2(src, dst)
                count += 1

    print(f"[scribe] wrote {count} files to Subconscious/")

# ── 3. ECHO REST ENDPOINT ─────────────────────────────────────────────────────
REST_CODE = '''#!/usr/bin/env python3
"""
echo_rest.py — Echo REST endpoint
Lets any device on the network talk to Echo via HTTP.
Port 8765. Run: python3 echo_rest.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn, datetime

app = FastAPI(title="Echo REST API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    message: str
    model: str = None

class TaskRequest(BaseModel):
    title: str
    description: str = ""

@app.get("/")
def root():
    return {"status": "echo online", "time": str(datetime.datetime.now())}

@app.get("/ping")
def ping():
    return {"pong": True}

@app.post("/chat")
def chat(req: ChatRequest):
    try:
        from ai import ask
        response = ask(req.message, model=req.model)
        return {"response": response, "model": req.model or "default"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
def status():
    try:
        import requests as _r
        ollama_ok = _r.get("http://localhost:11434", timeout=2).status_code == 200
    except Exception:
        ollama_ok = False
    try:
        import requests as _r
        proxima_ok = _r.get("http://localhost:3210", timeout=1).status_code < 500
    except Exception:
        proxima_ok = False
    return {
        "ollama": ollama_ok,
        "proxima": proxima_ok,
        "searxng": _check_port(8081),
        "panel": _check_port(7799),
    }

def _check_port(port):
    import socket
    try:
        s = socket.create_connection(("localhost", port), timeout=1)
        s.close(); return True
    except Exception:
        return False

@app.get("/tasks")
def get_tasks():
    from memory import get_goals
    return {"tasks": get_goals()}

@app.post("/tasks")
def add_task(req: TaskRequest):
    from memory import add_goal
    add_goal(req.title, req.description)
    return {"ok": True, "title": req.title}

@app.get("/briefing")
def briefing():
    try:
        from briefing import build_briefing_text
        return {"briefing": build_briefing_text()}
    except Exception as e:
        return {"briefing": f"unavailable: {e}"}

@app.get("/kb")
def kb_search(q: str = ""):
    try:
        from echo_kb_context import get_kb_context
        return {"results": get_kb_context(q)}
    except Exception as e:
        return {"results": "", "error": str(e)}

if __name__ == "__main__":
    print("[echo-rest] starting on http://0.0.0.0:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")
'''

def write_rest():
    path = f"{BASE}/echo_rest.py"
    with open(path, "w") as f:
        f.write(REST_CODE)
    os.chmod(path, 0o755)
    print(f"[rest] wrote {path}")

    # Check uvicorn installed
    try:
        import uvicorn
        print("[rest] uvicorn ok")
    except ImportError:
        print("[rest] installing uvicorn...")
        subprocess.run([VENV, "-m", "pip", "install", "uvicorn", "fastapi",
                        "--break-system-packages", "-q"])

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Echo Deploy Package ===")
    import_calendar()
    run_scribe()
    write_rest()
    print("\n=== Done ===")
    print("Start REST endpoint:")
    print(f"  nohup {VENV} {BASE}/echo_rest.py </dev/null >> /tmp/echo_rest.log 2>&1 & disown")
    print("\nTest it:")
    print("  curl http://localhost:8765/ping")
    print("  curl http://localhost:8765/status")

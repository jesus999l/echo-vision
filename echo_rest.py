#!/usr/bin/env python3
"""
echo_rest.py — Echo REST endpoint
Lets any device on the network talk to Echo via HTTP.
Port 8765. Run: python3 echo_rest.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
try:
    from cognition.echo_heartbeat import start_heartbeat
    start_heartbeat("echo_rest")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Header
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
class RunRequest(BaseModel):
    message: str
    source: str = "api"
ECHO_TOKEN = os.environ.get("ECHO_RUN_TOKEN", "")

@app.post("/run")
def run_command(req: RunRequest,
                authorization: str | None = Header(default=None),
                x_echo_token: str | None = Header(default=None)):
    token = x_echo_token or (authorization or "").removeprefix("Bearer ").strip()
    if ECHO_TOKEN and token != ECHO_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        import ai, uuid, json as _json
        from pathlib import Path as _Path
        parsed = ai.parse_task(req.message)
        task_id = str(uuid.uuid4())[:8]
        queue = _Path.home() / "queue"
        queue.mkdir(exist_ok=True)
        (_Path(queue) / f"task_{task_id}.json").write_text(
            _json.dumps({"id": task_id, "source": req.source,
                         "message": req.message, "parsed": parsed}))
        return {"ok": True, "task_id": task_id, "parsed": parsed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        from config import DEFAULT_MODEL
        model = req.model or DEFAULT_MODEL
        response = ask(req.message, model=model)
        return {"response": response, "model": model}
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

# ── OpenAI-compatible endpoints for Odysseus ──────────────────────────────
@app.get("/v1/models")
def v1_models():
    return {"object": "list", "data": [{"id": "qwen2.5:0.5b", "object": "model"}, {"id": "gemma3n-local", "object": "model"}]}

@app.post("/v1/chat/completions")
def v1_chat(req: dict):
    import ai
    msgs = req.get("messages", [])
    prompt = msgs[-1]["content"] if msgs else ""
    response = ai.ask(prompt=prompt)
    return {"id": "echo-1", "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": response}, "finish_reason": "stop"}], "model": req.get("model", "qwen2.5:0.5b")}

if __name__ == "__main__":
    print("[echo-rest] starting on http://0.0.0.0:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")

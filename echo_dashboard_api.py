"""
echo_dashboard_api.py — Vision Assistant v2 backend.

Serves real system metrics + Echo service heartbeat status to the v2
dashboard frontend. Does NOT touch main.py/ui.py (v1) or the core
pipeline logic in ai.py/memory.py — this is a read-mostly client that
sits alongside echo_rest.py.

Run standalone for now:
    ~/vision_env/bin/python3 ~/vision_assistant/echo_dashboard_api.py

Later this gets added to start-echo.sh as its own section, same
pattern as echo_rest.py.
"""
import json
import os
import sys
import time
import subprocess
import threading
from pathlib import Path

import psutil
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

app = FastAPI(title="Echo Dashboard API")

# Dashboard is a local file:// or localhost client — CORS wide open is fine,
# this never leaves the Tailscale mesh / localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEARTBEAT_FILE = Path("/tmp/echo_events.jsonl")

# Known Echo processes -> (display name, pgrep pattern, port or None)
SERVICES = [
    ("echo_rest",           "echo_rest.py",              8765),
    ("echo_vault_watcher",  "echo_vault_watcher",        None),
    ("echo_task_manager",   "echo_task_manager",         7799),
    ("echo_proxima_native", "echo_proxima_native",       3210),
    ("wake_word",           "wake_word.py",              None),
    ("vision_assistant_ui", "vision_assistant/main.py",  None),
    ("echo_browser_server", "echo_browser_server",       59996),
    ("echo_group_chat",     "echo_group_chat_server",    8484),
    ("wayvnc",              "wayvnc",                    5900),
    ("hermes_server",       "hermes_server",              None),
    ("echo_game_mode",      "echo_game_mode.py",          None),
    ("drift_panel",         "drift_panel.py",             None),
    ("shadow_cursor",       "echo_shadow_cursor.py",      None),
    ("odysseus_api",        "uvicorn app:app",            7000),
]


def _is_running(pattern: str) -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False


def _read_heartbeats(max_age_seconds: int = 30) -> dict:
    """Read /tmp/echo_events.jsonl and return {source: last_seen_ts}.

    Real schema confirmed from live file:
        {"type": "pong", "source": "echo_rest", "ping_id": "...", "timestamp": 1783042576.58}
    """
    beats = {}
    if not HEARTBEAT_FILE.exists():
        return beats
    try:
        with HEARTBEAT_FILE.open("r") as f:
            lines = f.readlines()[-200:]
        for line in lines:
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("type") != "pong":
                continue
            src = evt.get("source")
            ts = evt.get("timestamp")
            if src and ts:
                beats[src] = max(beats.get(src, 0), ts)
    except Exception:
        pass
    return beats


@app.get("/api/metrics")
def metrics():
    cpu = psutil.cpu_percent(interval=0.2)
    per_core = psutil.cpu_percent(interval=0, percpu=True)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    battery_info = None
    try:
        batt = psutil.sensors_battery()
        if batt:
            battery_info = {
                "percent": batt.percent,
                "charging": batt.power_plugged,
            }
    except Exception:
        pass

    temps = {}
    try:
        raw_temps = psutil.sensors_temperatures()
        if raw_temps:
            # Just grab the first sensor group's first reading as headline temp
            first_group = next(iter(raw_temps.values()))
            if first_group:
                temps["cpu"] = first_group[0].current
    except Exception:
        pass

    return {
        "timestamp": time.time(),
        "cpu": {"percent": cpu, "per_core": per_core},
        "ram": {
            "percent": vm.percent,
            "used_gb": round(vm.used / 1e9, 1),
            "total_gb": round(vm.total / 1e9, 1),
        },
        "disk": {
            "percent": disk.percent,
            "used_gb": round(disk.used / 1e9, 1),
            "total_gb": round(disk.total / 1e9, 1),
        },
        "net": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
        "battery": battery_info,
        "temps": temps,
    }


@app.get("/api/services")
def services():
    beats = _read_heartbeats()
    now = time.time()
    out = []
    running_count = 0
    for name, pattern, port in SERVICES:
        running = _is_running(pattern)
        last_beat = beats.get(name)
        stale = last_beat is not None and (now - last_beat) > 30

        if running and not stale:
            status = "green"
        elif running and stale:
            status = "yellow"  # process alive but heartbeat old
        else:
            status = "red"

        if running:
            running_count += 1

        out.append({
            "name": name,
            "status": status,
            "port": port,
            "last_heartbeat": last_beat,
        })

    return {
        "services": out,
        "running": running_count,
        "total": len(SERVICES),
    }


@app.get("/api/health")
def health():
    return JSONResponse({"ok": True, "ts": time.time()})


# ── Pipeline state (coarse, for now) ─────────────────────────────────────────
# NOTE: this only reflects requests made THROUGH this dashboard's /api/chat.
# It does not see voice/wake_word triggered requests, because ai.py has no
# stage instrumentation yet. Real per-stage state (memory_recall, routing,
# executing) requires adding write_pipeline_stage() calls inside ai.py's
# ask()/_ask_text()/execute_task() — that's a core-file change, do it as a
# separate deliberate step, not bundled into this dashboard patch.
_pipeline_lock = threading.Lock()
_pipeline_state = {
    "state": "idle",       # idle | thinking
    "last_prompt": None,
    "last_latency_ms": None,
    "last_updated": time.time(),
}


def _set_pipeline_state(**kwargs):
    with _pipeline_lock:
        _pipeline_state.update(kwargs)
        _pipeline_state["last_updated"] = time.time()


@app.get("/api/pipeline")
def pipeline():
    with _pipeline_lock:
        snapshot = dict(_pipeline_state)

    # Real, checkable service status — same logic as /api/services, just
    # the subset relevant to the AI pipeline specifically.
    snapshot["services"] = {
        "ollama": _is_running("ollama serve") or _is_running("ollama"),
        "proxima": _is_running("echo_proxima_native") or _is_running("electron"),
        "memory": Path(os.path.expanduser(
            "~/vision_assistant/chroma_db"
        )).exists(),
    }
    return snapshot


@app.post("/api/chat")
def api_chat(data: dict = Body(...)):
    prompt = (data.get("message") or "").strip()
    if not prompt:
        return JSONResponse({"error": "empty message"}, status_code=400)

    _set_pipeline_state(state="thinking", last_prompt=prompt)
    start = time.time()
    try:
        # Same pipeline every other Echo client uses — no reimplementation.
        from ai import chat as echo_chat
        reply = echo_chat(prompt)
    except Exception as e:
        _set_pipeline_state(state="idle", last_latency_ms=None)
        return JSONResponse({"error": str(e)}, status_code=500)

    latency_ms = round((time.time() - start) * 1000)
    _set_pipeline_state(state="idle", last_latency_ms=latency_ms)

    return {"reply": reply, "latency_ms": latency_ms}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8766)

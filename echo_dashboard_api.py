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
import time
import subprocess
from pathlib import Path

import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    """Read /tmp/echo_events.jsonl and return {service: last_seen_ts}."""
    beats = {}
    if not HEARTBEAT_FILE.exists():
        return beats
    try:
        # Tail the file — it can grow, so just read last ~200 lines
        with HEARTBEAT_FILE.open("r") as f:
            lines = f.readlines()[-200:]
        for line in lines:
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            svc = evt.get("service") or evt.get("name")
            ts = evt.get("ts") or evt.get("timestamp")
            if svc and ts:
                beats[svc] = max(beats.get(svc, 0), ts)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8766)

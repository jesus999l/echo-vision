#!/usr/bin/env python3
"""
Echo Health Check
Diagnoses the state of all Echo services, event streams, and dependencies.
Outputs a human-readable terminal report and saves a JSON status file to /tmp/echo_health.json.
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

VA_DIR = Path(__file__).parent.parent
STATUS_JSON_PATH = Path("/tmp/echo_health.json")


def check_event_bus() -> dict:
    bus_file = Path("/tmp/echo_events.jsonl")
    status = {"exists": bus_file.exists(), "writable": False, "error": None}
    try:
        if status["exists"]:
            with bus_file.open("a"):
                pass
            status["writable"] = True
        else:
            # Test directory writability
            test_file = Path("/tmp/.echo_bus_test")
            test_file.write_text("test")
            test_file.unlink()
            status["writable"] = True
    except OSError as e:
        status["error"] = str(e)
    return status


def check_observer() -> dict:
    status = {"alive": False, "pids": []}
    try:
        # Run pgrep -f to search for echo_observer.py process
        # Exclude this script itself (pgrep -f checks the full command line)
        res = subprocess.run(
            ["pgrep", "-f", "echo_observer.py"],
            capture_output=True,
            text=True,
        )
        pids = [p.strip() for p in res.stdout.splitlines() if p.strip()]
        # Verify it's not our own PID if someone named this script similarly
        my_pid = str(os.getpid())
        pids = [p for p in pids if p != my_pid]
        status["pids"] = pids
        status["alive"] = len(pids) > 0
    except Exception as e:
        status["error"] = str(e)
    return status


def check_tool_router() -> dict:
    status = {"importable": False, "error": None}
    try:
        sys.path.insert(0, str(VA_DIR))
        # Remove any existing cached modules if loaded to force dynamic import check
        if "live.tool_router" in sys.modules:
            del sys.modules["live.tool_router"]
        import importlib
        importlib.import_module("live.tool_router")
        status["importable"] = True
    except Exception as e:
        status["error"] = str(e)
    return status


def check_http_service(url: str) -> dict:
    status = {"reachable": False, "status_code": None, "error": None}
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as response:
            status["reachable"] = True
            status["status_code"] = response.status
    except Exception as e:
        status["error"] = str(e)
    return status


def check_piper() -> dict:
    piper_bin = Path("~/Echo/AI/Voices/piper/piper").expanduser()
    piper_model = Path("~/Echo/AI/Voices/piper/models/en_US-lessac-medium.onnx").expanduser()
    status = {
        "bin_exists": piper_bin.exists(),
        "model_exists": piper_model.exists(),
        "available": piper_bin.exists() and piper_model.exists(),
    }
    return status


def check_vosk() -> dict:
    vosk_path = Path("~/vosk-model-small-en-us-0.15").expanduser()
    model_file = vosk_path / "am" / "final.mdl"
    status = {
        "path_exists": vosk_path.exists(),
        "model_file_exists": model_file.exists(),
        "available": model_file.exists(),
    }
    return status


def main():
    print("🏥 Running Echo Self-Diagnostics...")
    print("=" * 45)

    diagnostics = {
        "event_bus": check_event_bus(),
        "observer": check_observer(),
        "tool_router": check_tool_router(),
        "proxima": check_http_service("http://localhost:3210/"),
        "ollama": check_http_service("http://localhost:11434/"),
        "piper": check_piper(),
        "vosk": check_vosk(),
    }

    # Format Human Report
    all_ok = True

    # 1. Event Bus
    bus = diagnostics["event_bus"]
    bus_mark = "✓" if bus["writable"] else "✗"
    print(f"[{bus_mark}] Event Bus (/tmp/echo_events.jsonl):")
    print(f"    - Writable: {bus['writable']}")
    if bus["error"]:
        print(f"    - Error: {bus['error']}")
        all_ok = False

    # 2. Observer
    obs = diagnostics["observer"]
    obs_mark = "✓" if obs["alive"] else "✗"
    print(f"[{obs_mark}] Observer Process (echo_observer.py):")
    print(f"    - Running: {obs['alive']} (PIDs: {', '.join(obs['pids']) if obs['pids'] else 'None'})")
    if not obs["alive"]:
        all_ok = False

    # 3. Tool Router
    tr = diagnostics["tool_router"]
    tr_mark = "✓" if tr["importable"] else "✗"
    print(f"[{tr_mark}] Tool Router (live.tool_router):")
    print(f"    - Importable: {tr['importable']}")
    if tr["error"]:
        print(f"    - Error: {tr['error']}")
        all_ok = False

    # 4. Proxima
    prox = diagnostics["proxima"]
    prox_mark = "✓" if prox["reachable"] else "✗"
    print(f"[{prox_mark}] Proxima Native Router (:3210):")
    print(f"    - Reachable: {prox['reachable']}")
    if prox["error"]:
        print(f"    - Error: {prox['error']}")
        all_ok = False

    # 5. Ollama
    oll = diagnostics["ollama"]
    oll_mark = "✓" if oll["reachable"] else "✗"
    print(f"[{oll_mark}] Ollama Local Runtime (:11434):")
    print(f"    - Reachable: {oll['reachable']}")
    if oll["error"]:
        print(f"    - Error: {oll['error']}")
        all_ok = False

    # 6. Piper TTS
    pip = diagnostics["piper"]
    pip_mark = "✓" if pip["available"] else "✗"
    print(f"[{pip_mark}] Piper Speech Synthesis (TTS):")
    print(f"    - Available: {pip['available']}")
    print(f"    - Binary: {'Found' if pip['bin_exists'] else 'Missing'}")
    print(f"    - Model: {'Found' if pip['model_exists'] else 'Missing'}")
    if not pip["available"]:
        all_ok = False

    # 7. Vosk STT
    vsk = diagnostics["vosk"]
    vsk_mark = "✓" if vsk["available"] else "✗"
    print(f"[{vsk_mark}] Vosk Speech Recognition (STT):")
    print(f"    - Available: {vsk['available']}")
    print(f"    - Model File: {'Found' if vsk['model_file_exists'] else 'Missing'}")
    if not vsk["available"]:
        all_ok = False

    print("=" * 45)
    if all_ok:
        print("🟢 Echo Stack Health Status: HEALTHY")
    else:
        print("🔴 Echo Stack Health Status: DEGRADED (Check warnings above)")
    print("=" * 45)

    # Save to JSON status file
    try:
        STATUS_JSON_PATH.write_text(json.dumps(diagnostics, indent=2))
        print(f"Saved JSON report to {STATUS_JSON_PATH}")
    except OSError as e:
        print(f"Failed to write JSON report to {STATUS_JSON_PATH}: {e}")

    # Exit with code 0 if healthy, 1 if degraded
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

# Echo Stack Startup & Reliability Audit

**Date:** 2026-06-29  
**Target File:** `~/vision_assistant/start-echo.sh`

---

## Executive Summary
This audit evaluates the initialization chain of the Echo AI Operating System stack launched via `start-echo.sh`. The system comprises 10 distinct microservices and background daemons spanning local AI routing, HTTP REST endpoints, Obsidian vault watchers, web interfaces, and Wayland compositor overlays.

The stack demonstrates good process isolation, but several race conditions, missing health verifications, and directory-leak flaws in the startup script impact reboot reliability.

---

## 1. Service Inventory

| # | Service Name | Command / Script | Port | Log File |
|---|---|---|---|---|
| 1 | **Proxima Native** | `echo_proxima_native.py --port 3210` | 3210 | `/tmp/echo_proxima.log` |
| 2 | **Browser Server** | `echo_browser_server.py` | 59996 | `/tmp/echo_browser.log` |
| 3 | **Group Chat Server** | `echo_group_chat_server.py` | 8484 | `/tmp/echo_groupchat.log` |
| 4 | **Hermes Gateway** | `hermes gateway run --replace` | Dynamic | `/tmp/echo_hermes.log` |
| 5 | **Echo Vision UI** | `main.py --ui` | GUI | `/tmp/echo_main.log` |
| 6 | **Echo REST API** | `echo_rest.py` | 8765 | `/tmp/echo_rest.log` |
| 7 | **Vault Watcher** | `echo_vault_watcher.py` | None | `/tmp/echo_vault.log` |
| 8 | **Task Manager** | `echo_task_manager.py` | 7799 | `/tmp/echo_tasks.log` |
| 9 | **Odysseus Web Workspace** | `uvicorn app:app --port 7000` | 7000 | `/tmp/odysseus.log` |
| 10 | **Echo Shadow Cursor** | `echo_shadow_cursor.py` | 59998 | `/tmp/echo_shadow.log` |

---

## 2. Key Findings & Vulnerabilities

### ⚠️ Race Conditions (Startup Sequencing)
1. **Proxima Native Fixed Sleep Timeout:**  
   `start-echo.sh` initiates `echo_proxima_native.py` and executes a hardcoded `sleep 3` before checking HTTP availability on port `3210`. `echo_proxima_native.py` loads Whisper model weights (`whisper.load_model("base")`) inside FastAPI's `lifespan` handler on startup. On CPU-only hardware (Intel i7-10610U), loading model weights frequently exceeds 3 seconds, leading to false-negative failure warnings in the startup log while downstream services attempt connections prematurely.
2. **REST API & Odysseus Startup Order:**  
   `echo_rest.py` (Port 8765) and Odysseus (Port 7000) are launched sequentially without waiting for port binding verification. Devices or UI frontend sessions connecting immediately upon script completion encounter connection errors until sockets bind.

### 🔍 Missing Health Checks
1. **Process-Only Verification (`pgrep` vs. HTTP ping):**  
   Services 2 (Browser Server), 3 (Group Chat Server), 6 (REST API), 8 (Task Manager), and 9 (Odysseus) are checked solely via process presence (`pgrep -f`). If a process experiences a deadlock, socket bind failure, or crash loop on port bind, `pgrep` reports it as healthy.
2. **Hermes Gateway Readiness:**  
   Hermes gateway is launched via `nohup` without verifying binary existence or return code, logging successful launch even if `hermes` is missing from `$PATH`.

### 💥 Single Points of Failure & Side Effects
1. **Working Directory Leak in Main Shell (Odysseus Launch):**  
   Line 107 of `start-echo.sh` executes `cd ~/odysseus && nohup ...`. Because this `cd` runs directly in the parent bash script environment without subshell containment, any subsequent commands execute with `~/odysseus` as `PWD` instead of `~/vision_assistant`.
2. **Missing Guard on Odysseus Daemon:**  
   Unlike all other services in `start-echo.sh`, Odysseus lacks a `pgrep` or port-check guard. Running `start-echo.sh` multiple times spawns multiple conflicting `uvicorn` instances.

---

## 3. Cognition & Live Stack Startup Safety Audit

| Subsystem | File | Startup Safety Status | Analysis |
|---|---|---|---|
| **Event Bus** | `cognition/echo_event_bus.py` | **SAFE** | Uses atomic append operations (`tempfile.NamedTemporaryFile` in `/tmp` $\rightarrow$ atomic stream write). Gracefully catches `OSError` so event logging failures never crash host callers. |
| **Tool Router** | `live/tool_router.py` | **SAFE** | RAM-only queue initialized at import. Hot-reloads `capabilities.json` safely. Atomically updates IPC files in `/tmp`. |
| **Observer Spine** | `cognition/echo_observer.py` | **SAFE** | On boot, seeks directly to `st_size` of `/tmp/echo_events.jsonl` to prevent replaying stale events from previous boots. Uses atomic file replacement for bubble narration updates. |

---

## 4. Recommended Direct Fixes

1. **Subshell Containment & Process Guard for Odysseus:** Wrap Odysseus startup in `(cd "$HOME/odysseus" && ...)` and add a `pgrep -f "uvicorn app:app"` check.
2. **Dynamic Polling for Proxima Native:** Replace hardcoded `sleep 3` with a 10-second polling retry loop checking `http://localhost:3210/`.
3. **HTTP Readiness Verification for REST API:** Verify `http://localhost:8765/ping` returns HTTP 200 before proceeding to downstream UI services.

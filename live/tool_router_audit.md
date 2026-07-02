# Echo Tool Router Audit
*Generated: 2026-06-30T01:00:14Z — READ ONLY, no files modified.*

---

## 1. File Inventory

| File | Status | Lines |
|------|--------|-------|
| `/home/jesus999l/vision_assistant/live/tool_router.py` | ✅ found | 350 |
| `/home/jesus999l/vision_assistant/capabilities.json` | ❌ NOT FOUND | — |
| `/tmp/echo_live_ui.json` | ❌ NOT FOUND | — |
| `/home/jesus999l/vision_assistant/cognition/echo_event_bus.py` | ✅ found | 62 |
| `/home/jesus999l/vision_assistant/live/echo_live.py` | ✅ found | 106 |
| `live/capabilities.json` | ✅ found (extra) | 51 |
| `live/driftwm_bridge.py` | ✅ found (extra) | 24 |
| `live/echo_shadow_cursor.py` | ✅ found (extra) | 44 |
| `live/inject_test.py` | ✅ found (extra) | 51 |
| `live/live_socket.py` | ✅ found (extra) | 55 |
| `live/secrets_loader.py` | ✅ found (extra) | 75 |

## 2. Current Tool Flow

**Dispatch handlers found:** (none detected — may use if/elif or dict lookup)

**Tool name strings detected:** requires_confirmation, move_shadow_cursor, show_notification, navigate_zone, launch_application, open_url, search_web, permission_block, tool_router, tool_execution, gemini_live, cursor_target, run_shell, close_window

**Head (first 50 lines):**
```python
#!/usr/bin/env python3
"""
Echo Live — Tool Router
Validates, dispatches, and narrates tool calls from Gemini Live.

Architecture:
    Gemini Live → echo_live.py → submit_tool_call() → ACTION_QUEUE → action_worker()
                                                                           |
                                                            DriftWM IPC / echo_actions.py

Design rules:
    - RAM-only queue (asyncio.Queue)
    - Atomic IPC writes (os.replace) — compositor reads cannot catch partial writes
    - Capabilities loaded from capabilities.json at import
    - Action narration: Echo describes what she just did, in first person
    - No logging, no database, no SSD writes outside /tmp (tmpfs)
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent / 'cognition'))
try:
    from echo_event_bus import emit_async as _emit
except ImportError:
    async def _emit(e): pass  # graceful degradation

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
CAPS_FILE = _HERE / "capabilities.json"

DRIFT_IPC = {
    "cursor": "/tmp/echo_pos.json",
    "nav":    "/tmp/echo_nav.json",
    "bubble": "/tmp/echo_bubble.txt",
    "live":   "/tmp/echo_live_ui.json",
}

SOCKET_PATH = "/tmp/echo_live.sock"
SEARXNG_URL = "http://localhost:8765"

# ── Capabilities ───────────────────────────────────────────────────────────────
def _load_caps():
    try:
```

**Other files in `live/`:**

### `capabilities.json`
```python
{
  "move_shadow_cursor": {
    "enabled": true,
    "requires_confirmation": false,
    "description": "Move Echo's sprite to a screen position"
  },
  "show_notification": {
    "enabled": true,
    "requires_confirmation": false,
    "description": "Write a message to Echo's speech bubble"
  },
  "navigate_zone": {
    "enabled": true,
    "requires_confirmation": false,
    "description": "Navigate to a named workspace zone"
  },
  "launch_application": {
    "enabled": true,
    "requires_confirmation": true,
    "description": "Launch a Linux application by executable name"
  },
  "open_url": {
    "enabled": true,
    "requires_confirmation": false,
    "description": "Open a URL in the default browser"
  },
  "search_web": {
    "enabled": true,
    "requires_confirmation": false,
    "description": "Search the web via local SearXNG"
```

### `driftwm_bridge.py`
```python
#!/usr/bin/env python3
"""
DriftWM Bridge — Compositor IPC stub.
Flesh out once DriftWM has a socket or inotify-watched command file.
Currently: tool_router writes /tmp/echo_focus_target.json.
DriftWM polls that file (same pattern as zones.json hot-reload).
"""

import json
from pathlib import Path

def focus_window(app_id: str) -> dict:
    Path("/tmp/echo_focus_target.json").write_text(
        json.dumps({"window": app_id, "source": "driftwm_bridge"})
    )
    return {"ok": True, "window": app_id}

def send_zone_command(cmd: str, zone_name: str, **kwargs) -> dict:
    payload = {"cmd": cmd, "zone": zone_name, **kwargs}
    Path("/tmp/echo_zone_cmd.json").write_text(json.dumps(payload))
    return {"ok": True, "payload": payload}

if __name__ == "__main__":
    print("[driftwm_bridge] stub — no action taken")
```

### `echo_shadow_cursor.py`
```python
#!/usr/bin/env python3
"""
Echo Shadow Cursor Daemon
Polls /tmp/echo_live_ui.json and pushes cursor targets into /tmp/echo_pos.json.
DriftWM reads echo_pos.json for the sprite orbit position.

Run: ~/vision_env/bin/python3 echo_shadow_cursor.py
"""

import json
import time
from pathlib import Path

LIVE_UI  = Path("/tmp/echo_live_ui.json")
ECHO_POS = Path("/tmp/echo_pos.json")
POLL     = 0.1   # seconds

_last = None

def run():
    global _last
    print("[shadow_cursor] online — polling /tmp/echo_live_ui.json")

    while True:
        try:
            if LIVE_UI.exists():
                raw = LIVE_UI.read_text().strip()
                if raw:
                    payload = json.loads(raw)
                    if payload != _last and payload.get("type") == "cursor_target":
```

### `inject_test.py`
```python
#!/usr/bin/env python3
"""
Local test injector — sends fake Gemini tool calls via Unix socket.
live_socket.py must be running first.

Usage: ~/vision_env/bin/python3 inject_test.py
"""

import json
import socket
import time

SOCKET_PATH = "/tmp/echo_live.sock"

def send(tool: str, args: dict):
    payload = json.dumps({"tool": tool, "args": args}).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(SOCKET_PATH)
        s.sendall(payload)
        resp = s.recv(4096)
    result = json.loads(resp.decode())
    mark = "✓" if result.get("ok") else "✗"
    print(f"  {mark} {tool}({args}) → {result}")
    time.sleep(0.3)

if __name__ == "__main__":
    print("=== inject_test: firing fake Gemini tool calls ===")
    print()

    # 1. Speech bubble
```

### `live_socket.py`
```python
#!/usr/bin/env python3
"""
Echo Live — Unix Socket Server
Receives tool call JSON over /tmp/echo_live.sock and dispatches via tool_router.
This replaces the Gemini websocket for local testing.

Usage:
  Terminal 1: ~/vision_env/bin/python3 live_socket.py
  Terminal 2: ~/vision_env/bin/python3 inject_test.py
           or: echo '{"tool":"show_notification","args":{"message":"test"}}' | nc -U /tmp/echo_live.sock
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tool_router import submit_tool_call, action_worker, SOCKET_PATH

async def handle_client(reader, writer):
    data = await reader.read(4096)
    try:
        msg    = json.loads(data.decode())
        tool   = msg.get("tool", "")
        args   = msg.get("args", {})
        result = await submit_tool_call(tool, args)
        writer.write(json.dumps(result).encode())
        await writer.drain()
```

### `secrets_loader.py`
```python
#!/usr/bin/env python3
"""
Echo Live — Secrets Loader
Validates GEMINI_API_KEY on startup. Rejects if missing, too short, or placeholder.
"""

import os
import sys
from pathlib import Path

SECRETS_FILE = Path.home() / ".config" / "echo" / "secrets.env"

PLACEHOLDER_STRINGS = [
    "your_key",
    "your_api_key",
    "paste",
    "placeholder",
    "changeme",
    "xxxx",
]


def load_secrets() -> str:
    """Load GEMINI_API_KEY into os.environ if present in ~/.config/echo/secrets.env."""
    if SECRETS_FILE.exists() and not os.environ.get("GEMINI_API_KEY"):
        try:
            for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
```

## 3. Existing Permissions

⚠️ `capabilities.json` NOT FOUND.

No permission layer detected. This means the router (if it exists) currently executes tool calls without a whitelist — **high risk** for Gemini Live integration.

**Permission-related lines in `tool_router.py`:**
```python
- Capabilities loaded from capabilities.json at import
CAPS_FILE = _HERE / "capabilities.json"
CAPABILITIES = _load_caps()
def reload_capabilities():
"""Hot-reload capabilities.json at runtime."""
global CAPABILITIES
def is_allowed(tool_name: str) -> bool:
cap = CAPABILITIES.get(tool_name)
cap = CAPABILITIES.get(tool_name, {})
Validates against capabilities.json, queues if allowed.
if not is_allowed(tool_name):
f"I don't have permission to do that: {tool_name}."
"type":    "permission_block",
"summary": f"I don't have permission to do that: {tool_name}.",
print(f"Capabilities loaded: {list(CAPABILITIES.keys())}")
("open_url",           {"url": "file:///etc/passwd"}),   # blocked silently
("run_shell",          {"cmd": "id"}),                   # not in caps → blocked
("close_window",       {"window": "firefox"}),           # disabled in caps → blocked
```

## 4. IPC Format

⚠️ `/tmp/echo_live_ui.json` not present (Echo not running, or IPC path not yet created).

**Expected format based on architecture docs:**
```json
{
  "bubble": "Opening browser...",
  "tool": "open_url",
  "status": "success",
  "timestamp": "2026-06-29T18:45:00Z"
}
```

No IPC write calls detected in `tool_router.py`.

**`echo_event_bus.py`** — 62 lines

```python
#!/usr/bin/env python3
"""
Echo Event Bus
Writes events to /tmp/echo_events.jsonl (tmpfs — RAM-only, no SSD).
echo_observer.py tails this file and decides what to persist.

WHY NOT in-process listener list:
  tool_router, observer, browser_bridge are separate processes.
  A shared file is the correct IPC primitive for this pattern.
  It matches the existing /tmp/echo_pos.json, /tmp/echo_bubble.txt style.

SOURCES that can emit:
  - tool_router.py (tool executions, permission blocks)
  - echo_browser_bridge.py (page seen, tab changed)
  - voice pipeline (commands heard)
  - DriftWM (zone changed, window focused) — future
"""

import json
import os
import tempfile
import time
from pathlib import Path

BUS_FILE = Path("/tmp/echo_events.jsonl")


def emit(event: dict) -> None:
    """
    Append one event to the bus file atomically.
    Caller should include: type, source, and optionally summary.
    timestamp is added automatically.
    """
    event = {
        "timestamp": time.time(),
        **event,
    }

    line = json.dumps(event, ensure_ascii=False) + "\n"

    try:
        # Direct atomic append via O_APPEND mode on tmpfs
        with open(BUS_FILE, "a", encoding="utf-8") as bus:
            bus.write(line)
            bus.flush()
    except OSError:
        pass  # Never crash the caller over observation


async def emit_async(event: dict) -> None:
```

## 5. Missing Safety Checks

- 🔴 **Direct shell execution detected** in `tool_router.py`:
```python
subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```
This is the exact `model → shell` path that must be gated.

- 🔴 **`capabilities.json` missing** — no static allowlist exists. Must be created before Gemini Live is connected.

- 🔴 **Path traversal / `file://` patterns found** in router source — must be sanitised before Gemini Live can pass arbitrary args.

## 6. Minimal Changes Required for Gemini Live Compatibility

Ordered by dependency (do not skip steps):

### Step 1 — Create `capabilities.json` (if absent)
```json
{
  "allowed_tools": [
    "open_url",
    "focus_window",
    "speak",
    "screenshot",
    "type_text",
    "search_web",
    "move_cursor",
    "scroll"
  ],
  "blocked_tools": [
    "run_command",
    "shell",
    "eval",
    "write_file",
    "delete_file",
    "execute"
  ],
  "url_schemes_allowed": ["https", "http"],
  "url_schemes_blocked": ["file", "javascript", "data"]
}
```

### Step 2 — Add permission gate to `tool_router.py`
Insert at the top of the dispatch function, before any execution:
```python
def _check_permission(tool_name: str, args: dict) -> tuple[bool, str]:
    caps = json.loads(Path("~/vision_assistant/capabilities.json").expanduser().read_text())
    if tool_name in caps.get("blocked_tools", []):
        return False, f"tool '{tool_name}' is blocked"
    if tool_name not in caps.get("allowed_tools", []):
        return False, f"tool '{tool_name}' not in allowlist"
    # URL scheme check
    url = args.get("url", "")
    if url:
        scheme = url.split("://")[0].lower() if "://" in url else ""
        if scheme in caps.get("url_schemes_blocked", []):
            return False, f"url scheme '{scheme}' is blocked"
    return True, "ok"
```

### Step 3 — Standardise IPC output format
Every tool call result must write to `/tmp/echo_live_ui.json`:
```python
ui_event = {
    "tool":      tool_name,
    "status":    "success" | "blocked" | "error",
    "bubble":    human_readable_string,
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "args":      args,   # sanitised — strip sensitive fields
}
Path("/tmp/echo_live_ui.json").write_text(json.dumps(ui_event))
```

### Step 4 — Emit to event bus after each tool call
```python
# after execution:
emit_event("tool_call", source="tool_router", message=tool_name,
           extra={"status": status, "args": args})
```

### Step 5 — Create `live/tools/` registry (pre-empts 3,000-line monster)
```
live/tools/
    __init__.py
    browser.py     # open_url, search_web
    system.py      # focus_window, screenshot, type_text, scroll
    voice.py       # speak
    vision.py      # screenshot + describe (Phase 3)
    memory.py      # emit_user_remember (Phase 4)
```
`tool_router.py` imports from these; never contains execution logic itself.

---

### What NOT to build yet
- Do not connect `echo_live.py` to Gemini Live until Steps 1–3 pass synthetic tests.
- Do not add memory writes to the router (memory engine is a future subscriber).
- Do not add LLM reasoning to the router — it stays dumb.

## 7. Synthetic Test Plan (before Gemini Live)

Run these manually after Step 1–4 changes:

```bash
ROUTER=~/vision_assistant/live/tool_router.py
PY=~/vision_env/bin/python3

# Legitimate call
$PY $ROUTER '{"tool":"open_url","args":{"url":"https://example.com"}}'
# Expect: /tmp/echo_live_ui.json updated, bubble set, no crash

# Blocked tool
$PY $ROUTER '{"tool":"run_command","args":{"cmd":"ls"}}'
# Expect: silent reject, status=blocked, no execution

# URL scheme attack
$PY $ROUTER '{"tool":"open_url","args":{"url":"file:///etc/passwd"}}'
# Expect: silent reject, status=blocked

# Unknown tool
$PY $ROUTER '{"tool":"nonexistent_tool","args":{}}'
# Expect: status=blocked (not in allowlist), no crash

# Malformed JSON
$PY $ROUTER 'not_json'
# Expect: error logged, no crash, /tmp/echo_live_ui.json unchanged
```

All five must pass before Phase 3 (Gemini Live connection).


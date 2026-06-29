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
        return json.loads(CAPS_FILE.read_text())
    except Exception:
        return {}

CAPABILITIES = _load_caps()

def reload_capabilities():
    """Hot-reload capabilities.json at runtime."""
    global CAPABILITIES
    CAPABILITIES = _load_caps()

def is_allowed(tool_name: str) -> bool:
    cap = CAPABILITIES.get(tool_name)
    return bool(cap and cap.get("enabled", False))

def requires_confirmation(tool_name: str) -> bool:
    cap = CAPABILITIES.get(tool_name, {})
    return bool(cap.get("requires_confirmation", True))

# ── Atomic IPC write ───────────────────────────────────────────────────────────
def atomic_write(path: str, data: str):
    """
    Write data atomically via temp file + os.replace.
    /tmp is tmpfs so this is RAM-only — no SSD writes.
    Prevents compositor from reading a partial write.
    """
    p = Path(path)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=p.parent, delete=False, suffix=".tmp"
    ) as f:
        f.write(data)
        tmp = f.name
    os.replace(tmp, path)

# ── Action narration ───────────────────────────────────────────────────────────
# Echo describes what she just did. Written to bubble AFTER execution.
# These are her observations about her own actions — not AI calls.
_NARRATIONS = {
    "move_shadow_cursor":  lambda a: f"Moving to ({a['x']}, {a['y']}).",
    "show_notification":   lambda a: f"{a['message']}",
    "navigate_zone":       lambda a: f"Navigating to zone: {a['zone']}.",
    "launch_application":  lambda a: f"Launching {a['application']}.",
    "open_url":            lambda a: f"Opening {a['url']}.",
    "search_web":          lambda a: f"Searching for: {a['query']}.",
}

def _narrate(tool: str, args: dict):
    """Write Echo's self-description to the speech bubble after action executes."""
    fn = _NARRATIONS.get(tool)
    if fn:
        try:
            atomic_write(DRIFT_IPC["bubble"], fn(args))
        except Exception:
            pass

# ── RAM queue ──────────────────────────────────────────────────────────────────
ACTION_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=32)

# ── Submit (called by echo_live.py) ───────────────────────────────────────────
async def submit_tool_call(tool_name: str, arguments: dict) -> dict:
    """
    Entry point from echo_live.py.
    Validates against capabilities.json, queues if allowed.
    Returns immediately — worker handles execution async.
    """
    if not isinstance(arguments, dict):
        return {"ok": False, "error": "args must be a dict"}

    if not is_allowed(tool_name):
        # Echo narrates the block too
        atomic_write(
            DRIFT_IPC["bubble"],
            f"I don't have permission to do that: {tool_name}."
        )
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_emit({
                    "type":    "permission_block",
                    "source":  "tool_router",
                    "tool":    tool_name,
                    "summary": f"I don't have permission to do that: {tool_name}.",
                }))
        except Exception:
            pass
        return {"ok": False, "error": f"Tool not enabled: {tool_name}"}

    # Confirmation-required tools: queue but mark pending (future UI hook)
    if requires_confirmation(tool_name):
        # For now: proceed but log intent. Future: pause and ask user.
        atomic_write(
            DRIFT_IPC["bubble"],
            f"Running {tool_name} — this requires confirmation. Proceeding."
        )

    try:
        ACTION_QUEUE.put_nowait({
            "tool": tool_name,
            "args": arguments,
            "time": time.monotonic(),
        })
        return {"ok": True, "queued": tool_name}

    except asyncio.QueueFull:
        return {"ok": False, "error": "Action queue full"}


# ── Worker ─────────────────────────────────────────────────────────────────────
async def action_worker():
    """Background task. Start with: asyncio.create_task(action_worker())"""
    while True:
        action = await ACTION_QUEUE.get()
        tool = action["tool"]
        args = action["args"]

        try:
            executed = True
            if   tool == "show_notification":  _show_notification(args)
            elif tool == "move_shadow_cursor":  _move_cursor(args)
            elif tool == "navigate_zone":       _navigate_zone(args)
            elif tool == "launch_application":  executed = bool(_launch_application(args))
            elif tool == "open_url":            executed = bool(_open_url(args))
            elif tool == "search_web":          executed = bool(_search_web(args))

            if executed:
                # Narrate AFTER successful execution
                # (show_notification skips — it IS the narration)
                if tool != "show_notification":
                    _narrate(tool, args)

                # Emit observation event
                narration_fn = _NARRATIONS.get(tool)
                summary = narration_fn(args) if narration_fn else f"{tool} executed."
                await _emit({
                    "type":    "tool_execution",
                    "source":  "gemini_live",
                    "tool":    tool,
                    "success": True,
                    "summary": summary,
                })

        except Exception:
            pass  # silent — no SSD log writes

        ACTION_QUEUE.task_done()


# ── DriftWM IPC ────────────────────────────────────────────────────────────────
def _move_cursor(args: dict):
    atomic_write(DRIFT_IPC["cursor"], json.dumps({
        "x":      int(args["x"]),
        "y":      int(args["y"]),
        "source": "gemini_live",
    }))
    # Also write to live UI file so echo_shadow_cursor.py picks it up
    atomic_write(DRIFT_IPC["live"], json.dumps({
        "type":   "cursor_target",
        "x":      int(args["x"]),
        "y":      int(args["y"]),
        "source": "gemini_live",
    }))

def _navigate_zone(args: dict):
    """Internal IPC — Gemini passes zone name, we map to /tmp/echo_nav.json."""
    atomic_write(DRIFT_IPC["nav"], json.dumps({
        "zone":   args["zone"],
        "source": "gemini_live",
    }))

def _show_notification(args: dict):
    atomic_write(DRIFT_IPC["bubble"], str(args["message"]))


# ── System actions ─────────────────────────────────────────────────────────────
def _launch_application(args: dict) -> bool:
    app = args.get("application", "").strip()
    if not app:
        return False
    subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

def _open_url(args: dict) -> bool:
    url = args.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        return False  # silently drop non-http
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

def _search_web(args: dict) -> bool:
    query = args.get("query", "").strip()
    if not query:
        return False
    url = f"{SEARXNG_URL}/search?q={urllib.parse.quote(query)}"
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


# ── Gemini tool declarations (import into echo_live.py) ───────────────────────
TOOL_DECLARATIONS = [
    {
        "name": "launch_application",
        "description": "Launch a Linux application by executable name",
        "parameters": {
            "type": "object",
            "properties": {
                "application": {"type": "string"},
            },
            "required": ["application"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a URL in the default browser",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "search_web",
        "description": "Search the web for a query",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "move_shadow_cursor",
        "description": "Move Echo to a screen position",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "navigate_zone",
        "description": "Navigate Echo to a named workspace zone",
        "parameters": {
            "type": "object",
            "properties": {"zone": {"type": "string"}},
            "required": ["zone"],
        },
    },
    {
        "name": "show_notification",
        "description": "Display a message in Echo's speech bubble",
        "parameters": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
]


# ── Self-test ──────────────────────────────────────────────────────────────────
async def _selftest():
    print("=== tool_router self-test ===")
    print(f"Capabilities loaded: {list(CAPABILITIES.keys())}")
    print()

    worker = asyncio.create_task(action_worker())

    tests = [
        ("show_notification",  {"message": "Echo Live bridge online."}),
        ("move_shadow_cursor", {"x": 960, "y": 540}),
        ("navigate_zone",      {"zone": "work"}),
        ("launch_application", {"application": "echo"}),
        ("open_url",           {"url": "https://example.com"}),
        ("open_url",           {"url": "file:///etc/passwd"}),   # blocked silently
        ("run_shell",          {"cmd": "id"}),                   # not in caps → blocked
        ("close_window",       {"window": "firefox"}),           # disabled in caps → blocked
    ]

    for name, args in tests:
        r = await submit_tool_call(name, args)
        mark = "✓" if r.get("ok") else "✗"
        print(f"  {mark} {name}: {r}")

    await ACTION_QUEUE.join()
    worker.cancel()

    print()
    print("IPC check:")
    for label, path in DRIFT_IPC.items():
        p = Path(path)
        if p.exists():
            print(f"  ✓ /tmp/{p.name}: {p.read_text()[:60]}")
        else:
            print(f"  - /tmp/{p.name}: not written")

if __name__ == "__main__":
    asyncio.run(_selftest())

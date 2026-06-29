#!/usr/bin/env bash
# start-echo.sh — boot the full Echo stack
set -e

VA="$HOME/vision_assistant"
VENV="$HOME/vision_env/bin"
ECHO_VENV="$HOME/.echo/venv/bin"
COOKIE_DIR="$HOME/.echo/cookies"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║         Echo Stack Launcher          ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Echo Proxima Native (:3210) — OpenAI-compatible router, no Electron ───
if curl -sf http://localhost:3210/ -o /dev/null 2>/dev/null; then
    echo "  ✓ Proxima native already running on :3210"
elif pgrep -f "echo_proxima_native" > /dev/null; then
    echo "  ✓ Proxima native process running (port may still be starting)"
else
    echo "  → Starting Proxima native on :3210..."
    nohup "$VENV/python3" "$VA/echo_proxima_native.py" --port 3210 \
        </dev/null >> /tmp/echo_proxima.log 2>&1 &
    disown 2>/dev/null || true
    READY=0
    for i in {1..10}; do
        if curl -sf http://localhost:3210/ -o /dev/null 2>/dev/null; then
            READY=1
            break
        fi
        sleep 1
    done
    if [ $READY -eq 1 ]; then
        echo "  ✓ Proxima native running"
    else
        echo "  ⚠ Proxima native starting slowly or failed — check /tmp/echo_proxima.log"
        echo "    (Electron Proxima: DISPLAY=:0 cd ~/Proxima && npm start &)"
    fi
fi

# ── 2. Echo Browser Server (:59996) ─────────────────────────────────────────
if pgrep -f "echo_browser_server" > /dev/null; then
    echo "  ✓ Browser server already running"
else
    echo "  → Starting Browser Server (:59996)..."
    nohup "$VENV/python3" "$VA/echo_browser_server.py" > /tmp/echo_browser.log 2>&1 &
    echo "  ✓ Browser server started"
fi

# ── 3. Echo Group Chat Server (:8484) ────────────────────────────────────────
if pgrep -f "echo_group_chat" > /dev/null; then
    echo "  ✓ Group chat server already running"
else
    echo "  → Starting Group Chat Server (:8484)..."
    nohup "$VENV/python3" "$VA/echo_group_chat_server.py" > /tmp/echo_groupchat.log 2>&1 &
    echo "  ✓ Group chat server started"
fi

# ── 4. Hermes Gateway ────────────────────────────────────────────────────────
if pgrep -f "hermes_cli.main" > /dev/null; then
    echo "  ✓ Hermes gateway already running"
else
    echo "  → Starting Hermes gateway..."
    nohup hermes gateway run --replace > /tmp/echo_hermes.log 2>&1 &
    echo "  ✓ Hermes gateway started"
fi

# ── 5. Echo Vision Assistant (main UI) ──────────────────────────────────────
if pgrep -f "vision_assistant/main.py" > /dev/null; then
    echo "  ✓ Echo Vision already running"
else
    echo "  → Starting Echo Vision Assistant..."
    nohup "$VENV/python3" "$VA/main.py" --ui > /tmp/echo_main.log 2>&1 &
    echo "  ✓ Echo Vision started"
fi

echo ""
echo "  Stack status:"
echo "    Proxima Native : http://localhost:3210/status"
echo "    Browser Server : http://localhost:59996"  
echo "    Group Chat     : http://localhost:8484"
echo "    Open WebUI     : http://localhost:8080"
echo ""
echo "  Logs:"
echo "    tail -f /tmp/echo_proxima.log"
echo "    tail -f /tmp/echo_browser.log"
echo ""
# ── 6. Echo REST API (:8765) ─────────────────────────────────────────────────
if pgrep -f "echo_rest.py" > /dev/null; then
    echo "  ✓ REST API already running"
else
    echo "  → Starting REST API (:8765)..."
    nohup "$VENV/python3" "$VA/echo_rest.py" </dev/null >> /tmp/echo_rest.log 2>&1 &
    disown 2>/dev/null || true
    echo "  ✓ REST API started"
fi

# ── 7. Vault watcher + task manager ─────────────────────────────────────────
if pgrep -f "echo_vault_watcher" > /dev/null; then
    echo "  ✓ Vault watcher already running"
else
    nohup "$VENV/python3" "$VA/echo_vault_watcher.py" </dev/null >> /tmp/echo_vault.log 2>&1 &
    disown 2>/dev/null || true
    echo "  ✓ Vault watcher started"
fi
if pgrep -f "echo_task_manager" > /dev/null; then
    echo "  ✓ Task manager already running"
else
    nohup "$VENV/python3" "$VA/echo_task_manager.py" </dev/null >> /tmp/echo_tasks.log 2>&1 &
    disown 2>/dev/null || true
    echo "  ✓ Task manager started"
fi
if pgrep -f "uvicorn app:app" > /dev/null; then
    echo "  ✓ Odysseus already running"
else
    (cd "$HOME/odysseus" && nohup "$HOME/odysseus/venv/bin/python" -m uvicorn app:app --host 0.0.0.0 --port 7000 </dev/null >> /tmp/odysseus.log 2>&1 &)
    echo "  ✓ Odysseus started"
fi

# ── Echo Shadow Cursor ────────────────────────────────────────────────────────
if pgrep -f "echo_shadow_cursor" > /dev/null; then
    echo "  ✓ Shadow cursor already running"
else
    echo "  → Starting Echo Shadow Cursor..."
    nohup "$VENV/python3" "$VA/echo_shadow_cursor.py" </dev/null >> /tmp/echo_shadow.log 2>&1 &
    disown 2>/dev/null || true
    echo "  ✓ Shadow cursor started"
fi

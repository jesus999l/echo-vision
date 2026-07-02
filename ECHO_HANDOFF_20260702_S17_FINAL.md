# Echo Project Handoff — 2026-07-02 S17-FINAL
*Session ended at ~93% token usage. Load this before next session.*

## ONE-PARAGRAPH CONTEXT
Echo is a local-first AI OS on ThinkPad T14s Gen 1 (Linux Mint 22.3, jesus999l,
Tailscale 100.120.238.106). Python stack at ~/vision_assistant/, Rust compositor
at ~/driftwm/. This session: fixed memory recall (768-dim), wired vault into
conversations, heartbeat 5/5, added /run remote command endpoint, discovered
dual-brain architecture (Proxima=chat, Ollama=tasks), switched task model to
qwen2.5:0.5b. Session ended mid-fix on parse_task() cleanup.

## IMMEDIATE NEXT ACTION (start here)
parse_task() has accumulated multiple patch layers and still returns Extra data.
The current function body is at lines 288-323 of ~/vision_assistant/ai.py.
Replace the entire try: block content with this clean version:

    r = requests.post(
        TASK_LLM_URL,
        json={
            "model": TASK_MODEL,
            "messages": [
                {"role": "system", "content": _TASK_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 80},
        },
        timeout=30,
    )
    resp = r.json()
    content = resp["message"]["content"].strip()
    if "</think>" in content:
        content = content.split("</think>", 1)[1].strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].lstrip()
    return json.loads(content)

CONFIRMED WORKING: raw response from Ollama is valid.
Ollama returns: resp["message"]["content"] = clean JSON string.
qwen2.5:0.5b responds in ~200-500ms, no timeout.
The Extra data error is from leftover brace-slicing logic applied AFTER
a clean content string — json.loads() runs twice on already-parsed text.

## VERIFY AFTER FIX
cd ~/vision_assistant && ~/vision_env/bin/python3 -c "
from ai import parse_task
print(parse_task('open Firefox'))
"
Expected: {'action': 'open_app', 'params': {'name': 'firefox'}, 'explanation': '...'}

## THEN: end-to-end /run test
export ECHO_RUN_TOKEN=echo-secret-01
pkill -f echo_rest.py; sleep 1
cd ~/vision_assistant && ECHO_RUN_TOKEN=echo-secret-01 ~/vision_env/bin/python3 echo_rest.py &
sleep 2
curl -s -X POST http://localhost:8765/run \
  -H "Content-Type: application/json" \
  -H "X-Echo-Token: echo-secret-01" \
  -d '{"message":"open Firefox"}' | python3 -m json.tool
Expected: ok:true, task_id, parsed.action=open_app

## DUAL-BRAIN ARCHITECTURE (confirmed this session)
Proxima Electron :3211 = conversational brain (ChatGPT/Claude/Gemini)
  - LLM_URL in config.py points here
  - PROBLEM: injects its own system prompt, ignores callers system prompt
  - USE FOR: chat, conversation, creative tasks only
Ollama :11434 = deterministic brain (task parsing, embeddings)
  - TASK_LLM_URL = http://127.0.0.1:11434/api/chat
  - TASK_MODEL = qwen2.5:0.5b (switched from qwen3:4b this session)
  - EMBED_MODEL = nomic-embed-text (768-dim)
  - USE FOR: parse_task(), embeddings only
echo_proxima_native :3210 = Whisper/OpenAI speech server (NOT a chat router)
  - was incorrectly documented as LLM router in previous handoffs
  - do not route chat or tasks here

## PORTS
:3210 echo_proxima_native (Whisper speech server)
:3211 Proxima Electron (ChatGPT/Claude/Gemini)
:8765 echo_rest (REST API, POST /run endpoint lives here)
:7799 echo_task_manager
:11434 Ollama
:59996 echo_browser_server
:8484 echo_group_chat
:5900 wayvnc

## MEMORY ARCHITECTURE (FULLY WORKING, do not revisit)
Layer 1: memory.py SQLite — chat history, goals, habits, calendar
Layer 2: ~/vision_assistant/chroma_db — 25327 entries, 768-dim nomic-embed-text
echo_memory.py _embed() uses http://127.0.0.1:11434/api/embed
ai.py build_context() injects vault recall on every _ask_text() call
main.py unchanged — PersistentClient needs no lifecycle

## HEARTBEAT (FULLY WORKING)
All 5 daemons: echo_rest, echo_vault_watcher, echo_task_manager,
echo_proxima_native, wake_word — all patched with start_heartbeat()
echo_ping.py returns 5/5
Test: ~/vision_env/bin/python3 ~/echo_ping.py

## /run ENDPOINT (working except parse_task output)
POST http://100.120.238.106:8765/run
Header: X-Echo-Token: echo-secret-01
Body: {"message": "open Firefox"}
Auth works, queue writes to ~/queue/, task_id returns
Only remaining issue: parse_task() returns fallback instead of real action

## ECHO_RUN_TOKEN (not yet persisted)
Currently set only via export ECHO_RUN_TOKEN=echo-secret-01
TODO: add to ~/.config/echo/secrets.env
TODO: add "source ~/.config/echo/secrets.env" to start-echo.sh

## FILES MODIFIED THIS SESSION
~/vision_assistant/echo_memory.py — _embed() uses Ollama nomic-embed-text
~/vision_assistant/ai.py — vault recall wired, parse_task() uses Ollama (partially broken, fix above)
~/vision_assistant/echo_rest.py — heartbeat + POST /run + Header auth
~/vision_assistant/echo_vault_watcher.py — heartbeat
~/vision_assistant/echo_task_manager.py — heartbeat
~/vision_assistant/echo_proxima_native.py — heartbeat
~/vision_assistant/wake_word.py — heartbeat
~/vision_assistant/browser_control.py — _safe_open() scheme validation
~/vision_assistant/config.py — TASK_LLM_URL, TASK_MODEL added
~/start-echo.sh — Ollama section 0 added

## DO NOT RUN
apply_memory.py — stale, all anchors failed, integration done manually
tool_router.py — does not exist, removed from backlog

## PRIORITY QUEUE (next session)
1. Fix parse_task() — clean rewrite above, 5 min
2. Test /run end-to-end from phone over Tailscale
3. Persist ECHO_RUN_TOKEN to secrets.env
4. Source secrets.env in start-echo.sh
5. Fix Proxima routing: code -> claude (not chatgpt)
6. Perplexity re-login in Electron session

## HARDWARE
SSD: 7/100 health — CRITICAL, avoid large writes
Bluetooth: pactl set-default-source bluez_input.98_67_2E_E3_7F_5D.0
Emergency SSH: ssh jesus999l@100.120.238.106 from Termux

## COMPLETION
Infrastructure: 88%
Integration/wiring: 78% (parse_task fix = 80%)
Memory intelligence: 85%
Remote pipeline: 85% (one fix away from end-to-end)

## THE RULE
Before building anything new:
~/vision_env/bin/python3 ~/echo_scan.py
Echo is reconnecting organs, not building new ones.

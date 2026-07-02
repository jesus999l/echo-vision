# Echo Project Handoff — 2026-07-01 S17
*Written at ~75% token usage. All confirmed state from this session.*

## Project in one paragraph (read this first)
Echo is a local-first AI OS running on a ThinkPad T14s Gen 1 (Linux Mint 22.3,
username jesus999l, Tailscale IP 100.120.238.106). It has a Python AI stack at
~/vision_assistant/ and a Rust/Smithay Wayland compositor at ~/driftwm/.
The goal is a compositor-level AI companion that listens for voice, routes
intelligence through a multi-provider pipeline, and takes real system actions.
This session focused on: fixing semantic memory recall, wiring vault context
into conversations, wiring heartbeat into all 5 daemons, adding Ollama to boot,
and building a remote command pipeline (phone -> ThinkPad via Tailscale).

## Architecture (current, confirmed)

### AI routing (dual-brain — NEW this session)
- Proxima Electron :3211 — conversational brain (ChatGPT/Claude/Gemini via browser)
- Ollama :11434 — deterministic brain (task parsing, embeddings)
- echo_proxima_native.py :3210 — actually a Whisper/OpenAI speech server (NOT a chat router)
- LLM_URL in config.py = http://127.0.0.1:3211/v1/chat/completions (chat)
- TASK_LLM_URL in config.py = http://127.0.0.1:11434/api/chat (task parsing)
- TASK_MODEL = qwen3:4b
- EMBED_MODEL = nomic-embed-text (768-dim)

### Memory (FULLY WORKING — do not revisit)
- Layer 1: memory.py SQLite — chat history, goals, habits, calendar
- Layer 2: ~/vision_assistant/chroma_db — 25,327 entries, 768-dim nomic-embed-text
- echo_memory.py _embed() uses OLLAMA_EMBED = http://127.0.0.1:11434/api/embed
- ai.py build_context() injects vault recall on every _ask_text() call
- main.py unchanged — PersistentClient needs no lifecycle

### Remote command pipeline (NEW this session — partially working)
- POST /run on echo_rest.py :8765
- Auth: X-Echo-Token header (env var ECHO_RUN_TOKEN)
- Flow: /run -> parse_task() -> ~/queue/task_{uuid}.json -> echo_task_manager
- parse_task() now routes to Ollama (not Proxima) for reliable JSON output
- BLOCKER: Ollama /api/chat timing out on qwen3:4b — fix in progress at session end
- Token for testing: echo-secret-01 (set via export ECHO_RUN_TOKEN=echo-secret-01)
- The token needs to be added to ~/.config/echo/secrets.env permanently

### Heartbeat (FULLY WORKING)
All 5 daemons patched with start_heartbeat() call:
echo_rest.py, echo_vault_watcher.py, echo_task_manager.py,
echo_proxima_native.py, wake_word.py
echo_ping.py returns 5/5. Run: ~/vision_env/bin/python3 ~/echo_ping.py

### Boot sequence (start-echo.sh)
Section 0: Ollama (NEW)
Section 1: echo_proxima_native :3210 (Whisper server)
Section 2: echo_browser_server :59996
Section 3: echo_group_chat :8484
Section 5: main.py --ui
Section 6: echo_rest :8765
Section 7: echo_vault_watcher + echo_task_manager
Then: Proxima Electron :3211 (waits up to 48s for ready)
Then: waybar, drift_panel, echo_game_mode, wayvnc :5900

## Key ports
:3210 echo_proxima_native (Whisper/OpenAI speech, NOT chat router)
:3211 Proxima Electron (ChatGPT/Claude/Gemini browser sessions)
:8765 echo_rest (REST API — main external interface)
:7799 echo_task_manager
:11434 Ollama (embeddings + task parsing)
:59996 echo_browser_server
:8484 echo_group_chat
:5900 wayvnc

## Key files modified this session
~/vision_assistant/echo_memory.py — _embed() uses Ollama nomic-embed-text
~/vision_assistant/ai.py — vault recall in build_context(), parse_task() uses Ollama
~/vision_assistant/echo_rest.py — heartbeat + POST /run endpoint
~/vision_assistant/echo_vault_watcher.py — heartbeat
~/vision_assistant/echo_task_manager.py — heartbeat
~/vision_assistant/echo_proxima_native.py — heartbeat
~/vision_assistant/wake_word.py — heartbeat
~/vision_assistant/browser_control.py — _safe_open() with scheme validation
~/vision_assistant/config.py — TASK_LLM_URL, TASK_MODEL added
~/start-echo.sh — Ollama section 0 added

## What does NOT exist (cleared from queue)
- tool_router.py — does not exist, was a ghost queue item, removed from backlog
- apply_memory.py — stale, all 4 anchors failed, integration done manually, do not run

## Next session priority (in order)
1. FINISH parse_task() fix: confirm /api/chat response parsing works, test end-to-end
   - Warmup qwen3:4b before first call
   - Response shape: r.json()["message"]["content"] (not choices[0])
   - Test: cd ~/vision_assistant && python3 -c "from ai import parse_task; print(parse_task('open Firefox'))"
   - Expected: {"action": "open_app", "params": {"name": "firefox"}, "explanation": "..."}

2. End-to-end /run test from phone (Termux on S24 Ultra 100.113.49.116):
   curl -s -X POST http://100.120.238.106:8765/run
     -H "Content-Type: application/json"
     -H "X-Echo-Token: echo-secret-01"
     -d '{"message":"open Firefox"}'
   Expected: ok:true + Firefox opens on ThinkPad

3. Persist ECHO_RUN_TOKEN to ~/.config/echo/secrets.env
   Add to start-echo.sh: source ~/.config/echo/secrets.env

4. Fix Proxima routing: code -> claude (not chatgpt)

5. Perplexity re-login in Electron session

6. Gemini Live unblock: enable API at console.cloud.google.com project 912434533280

## Known hardware issues
- SSD health: 7/100 Media_Wearout_Indicator — CRITICAL, avoid large writes
- Bluetooth headset: Skullcandy Crusher ANC 2, MAC 98:67:2E:E3:7F:5D
  pactl set-default-source bluez_input.98_67_2E_E3_7F_5D.0

## Emergency recovery
- SSH from S24: ssh jesus999l@100.120.238.106 (Tailscale from Termux)
- Never force driftwm into lightdm.conf — use TTY or greeter picker only
- GRUB timeout must stay >0

## Completion estimates
Infrastructure: 88%
Integration/wiring: 75% (remote pipeline 90% done, needs parse_task fix)
Memory intelligence: 85%
Media/device ecosystem: 15%

## The rule (read before every session)
Before building anything new:
~/vision_env/bin/python3 ~/echo_scan.py
Echo is reconnecting organs, not building new ones.

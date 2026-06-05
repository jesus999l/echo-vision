# Echo + DriftWM — Master Handoff Document
generated: 2026-06-04 (end of session)
author: jesus999l + Claude + Cursor + Gemini + ChatGPT
purpose: Complete system state for any AI picking this up cold

---

## The Human

- **Name**: jesus999l (J999l)
- **Machine**: ThinkPad T14s Gen 1, i7-10610U, 16GB RAM, CPU-only, Linux Mint 22.3, zsh
- **IP**: 192.168.4.46 (LAN) — Tailscale also active
- **Python env**: /home/jesus999l/vision_env — ALWAYS use this, never system python
- **Shell rule**: NEVER mix prose and commands in same block. User pastes entire responses into zsh.
- **Communication style**: Casual, direct. Build complete working files. Minimal abstract explanation.

---

## Project 1: Echo — Local AI Operating System

### What It Is
Echo is a local-first AI OS. Not a chatbot. A persistent system that runs on your hardware, remembers everything across sessions, and routes queries through multiple AI providers with full personal context injected.

### The Pipeline (How a message flows)
```
User speaks/types
    ↓
ask() in ai.py
    ↓
_enrich_prompt() — builds context from:
    • build_context()      — SQLite memory + recent messages
    • search_local()       — tasks, habits, journal, calendar
    • search_if_needed()   — SearXNG web search (if query needs it)
    • build_system_prompt()— personality + goals + upcoming events
    ↓
Proxima :3210 (tries ChatGPT → Gemini → Perplexity → Grok)
    ↓ if all fail →
Ollama :11434 (qwen2.5:0.5b default, gemma3n-local for heavy tasks)
    ↓
parse_and_execute_actions() — handles <action> blocks that modify data
    ↓
save_message() → memory.db
```

### Services — All start via ~/start-echo.sh
| Service | Port | Log | Notes |
|---|---|---|---|
| Ollama | 11434 | - | Local LLM runtime |
| echo_proxima_native.py | 3210 | /tmp/echo_proxima.log | Multi-AI router, needs --port 3210 |
| SearXNG (Docker) | 8081 | - | Private web search |
| echo_rest.py | 8765 | /tmp/echo_rest.log | REST API for any device |
| echo_vault_watcher.py | - | /tmp/echo_vault.log | Watches Subconscious/ → KB |
| echo_task_manager.py | 7799 | /tmp/echo_tasks.log | Task queue + HTTP control |
| echo_browser_server.py | 59996 | /tmp/echo_tv.log | TV/web XMB interface |
| Odysseus | 7000 | /tmp/odysseus.log | Web workspace UI (must cd ~/odysseus first) |

### Ollama Models
| Model | Size | Role |
|---|---|---|
| qwen2.5:0.5b | 397MB | Fast default for all queries |
| gemma3n-local | 4.2GB | Heavy reasoning, from GGUF at ~/Echo/AI/Models/ |

### REST API (port 8765) — Talk to Echo from anywhere
```
GET  /ping              → health check
GET  /status            → all service status
POST /chat              → {"message":"...", "model":"..."} → AI response with full context
GET  /tasks             → list goals/tasks
POST /tasks             → {"title":"...", "description":"..."} → add task
GET  /briefing          → morning briefing
GET  /kb?q=query        → knowledge base search
```
Test: `curl -X POST http://192.168.4.46:8765/chat -H "Content-Type: application/json" -d '{"message":"what tasks do i have"}'`

### Vault System
```
~/Documents/ObsidianVault/Echo/
├── Subconscious/    ← DROP FILES HERE — watcher distills to KB automatically
├── Knowledge_Base/  ← NEVER write here directly — watcher output only
├── Cognition/       ← plans, architecture
├── Archive/         ← processed originals
└── INDEX.md         ← auto-rebuilt
```
698 Google Drive/Chat files are in Subconscious/ waiting for distillation. Vault watcher is running but backlog is large — manual distillation pass needed.

### What Was Built/Fixed This Session
1. `_enrich_prompt()` — unified context injection for both Proxima AND Ollama paths
2. `echo_rest.py` — full FastAPI REST endpoint, all services accessible remotely
3. `search_local()` + `search_if_needed()` wired into `_ask_text()`
4. 142 Google Calendar events imported into memory.db
5. 698 Google files dropped in Subconscious/
6. Chroma synced (10 entries, nomic-embed-text)
7. `gemma3n-local` created in Ollama from GGUF
8. `qwen2.5:0.5b` pulled as fast default
9. All `gemma3:latest` hardcoded references replaced
10. `guidelines` bug fixed in `build_system_prompt()`
11. `multi_model.py` updated to use available models
12. Odysseus installed at ~/odysseus (web workspace, port 7000, admin/admin123)
13. Google Takeout (7GB) deleted after import — 24GB free now

### Known Issues / Remaining Wires
| Item | Status | Notes |
|---|---|---|
| Odysseus ↔ Echo bridge | PENDING | Settings → Models → http://192.168.4.46:8765/v1, model qwen2.5:0.5b |
| Subconscious distillation | PENDING | 698 files waiting, run manual pass |
| Shadow cursor | PENDING | echo_shadow.py exists, needs keybind |
| Hermes OpenRouter key | PENDING | Fix 30min Discord response time |
| Jules activation | PENDING | File one GitHub issue → autonomous overnight coding |
| ChromaDB expansion | PENDING | Only 10 entries, needs more distillation |
| Proxima Electron | MANUAL | Start manually for ChatGPT/Gemini browser sessions: cd ~/Proxima && npm start |

---

## Project 2: DriftWM — Infinite Canvas Compositor

### What It Is
driftwm is a custom Wayland compositor where windows float freely on an infinite 2D canvas. No workspaces. Camera pans and zooms. You navigate the canvas instead of switching desktops.

### Install State
- Binary: /usr/local/bin/driftwm 0.8.1 (PATCHED — button8/9 Rust source patched, binary installed)
- Source: ~/driftwm/ (Rust, smithay backend)
- Config: ~/.config/driftwm/config.toml
- Start script: ~/.config/driftwm/start.sh
- Session log: ~/driftwm-session.log
- Desktop entry: /usr/share/wayland-sessions/driftwm.desktop

### Switching Environments
- **Cinnamon → driftwm**: `Super+F12`
- **driftwm → Cinnamon**: `mod+F12` (actually `mod+XF86Favorites` — ThinkPad F12 sends XF86Favorites)
- Toggle script: ~/.local/bin/toggle-driftwm.sh

### Working Keybindings (mod = Super key)
| Binding | Action |
|---|---|
| mod+space | fuzzel launcher |
| mod+o | zoom-to-fit (overview — see ALL windows) |
| mod+h | home-toggle (snap back to origin) |
| mod+c | focus-center |
| mod+tab | cycle windows forward |
| mod+shift+tab | cycle windows backward ✅ |
| mod+equal | zoom in |
| mod+minus | zoom out |
| mod+shift+arrows | pan viewport (move camera) |
| mod+arrows | nudge focused window |
| mod+f | toggle fullscreen |
| mod+m | fit window to screen |
| mod+w | close window |
| mod+r | reload config (live, no restart needed) |
| mod+t | btop++ in terminal |
| mod+b | Firefox |
| mod+shift+d | Discord |
| mod+shift+q | quit driftwm |
| mod+XF86Favorites | quit driftwm (actual F12 key) |

### Config Features
- `window_placement = "auto"` — new windows open adjacent to focused, not overlapping
- Warframe window rule: 1280×720 at position [100, 50]
- Autostart: drift_panel.py + xbindkeys

### Known Issues
| Issue | Status | Notes |
|---|---|---|
| Mouse side buttons | NOT WORKING | button8/button9 patch in Rust source, binary installed, but libinput not passing BT mouse side buttons to compositor. User not in `input` group yet: `sudo usermod -aG input jesus999l` then relogin |
| F-keys (F1-F12) | NOT WORKING | ThinkPad sends XF86 media keys, no Fn lock on this model. Use mod+letter bindings instead |
| drift_panel close/focus | PARTIAL | wlrctl segfaults on plain focus. Patched to use `title:` syntax + xdotool for XWayland. Needs testing |
| Bluetooth popup | ANNOYING | blueman-applet can't be closed in Wayland — no fix yet |
| LightDM recovery | BUG | Sometimes needs reboot after driftwm exit |

### ThinkPad F-Key Map (actual keysyms sent)
| Physical Key | XF86 Name | Suggested driftwm binding |
|---|---|---|
| F7 | XF86Display | mod+XF86Display = "exec something" |
| F8 | XF86WLAN | WiFi toggle |
| F9 | XF86Messenger | Could bind to Discord |
| F10 | XF86Go | Free to use |
| F11 | Cancel | Free to use |
| F12 | XF86Favorites | mod+XF86Favorites = "quit" ← already set |

### Rust Patch Applied to driftwm Source
File: ~/driftwm/src/config/parse.rs line 59-60
```rust
"back" | "button8" => MouseTrigger::Button(0x116),
"forward" | "button9" => MouseTrigger::Button(0x117),
```
Config at ~/.config/driftwm/config.toml:
```toml
[mouse.anywhere]
"button9" = "zoom-in"
"button8" = "zoom-out"
```
Issue: libinput doesn't pass BT mouse side buttons without user being in `input` group.

---

## Odysseus — Web Workspace UI

### What It Is
Self-hosted AI workspace with chat, deep research, documents, email, calendar, notes, memory, image generation. Runs alongside Echo, uses same Ollama/SearXNG stack.

### State
- Location: ~/odysseus
- Port: 7000
- Credentials: admin / admin123
- MCP servers registered: Email, RAG, Image Generation, Browser (Playwright, 29 tools)
- Start: `cd ~/odysseus && nohup ~/odysseus/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 7000 </dev/null >> /tmp/odysseus.log 2>&1 & disown`
- Access: http://192.168.4.46:7000

### NEXT STEP: Wire to Echo
In Odysseus UI: Settings → Models → Add provider:
- Type: OpenAI Compatible
- URL: http://192.168.4.46:8765/v1
- Model: qwen2.5:0.5b

This gives Odysseus full Echo context (calendar, tasks, vault, web search) in every chat.

---

## Hardware / Infrastructure

### Devices
| Device | IP | Role |
|---|---|---|
| ThinkPad T14s | 192.168.4.46 | Primary hub |
| Samsung S24 Ultra | 100.113.49.116 | Mobile (Tailscale) |
| Onn 4K Google TV | 100.80.207.10 | TV (ADB) |

### Audio
- Headphones: Crusher ANC 2 (MAC: 98:67:2E:E3:7F:5D)
- Trusted and auto-connects on boot
- Default sink: Crusher (A2DP stereo)
- Default source: laptop mic (A2DP has no mic support)
- If profile shows "off": `pactl set-card-profile bluez_card.98_67_2E_E3_7F_5D a2dp-sink`
- EasyEffects sink is the correct path for Discord audio

### Disk
- 468GB total, ~24GB free (95%) — still tight
- Remaining large items: ~/Documents/Games (16G), ~/Echo/Projects (6.7G), ~/Echo/AI (4.9G)
- vision_env (8.1G) — needed, don't touch

---

## Priority Queue — What To Do Next

### Immediate (next session)
1. `sudo usermod -aG input jesus999l` + relogin → test side buttons
2. Wire Odysseus → Echo REST (Settings → Models → http://192.168.4.46:8765/v1)
3. Test drift_panel close/focus with patched wlrctl syntax
4. Manual Subconscious distillation pass (698 files)

### High Value
5. Hermes OpenRouter key → fix 30min Discord response
6. Shadow cursor (echo_shadow.py + keybind)
7. Jules: file one GitHub issue → autonomous coding starts
8. Planner layer in Echo (goal → tasks → execution)

### Architecture
9. Spine consolidation (Cursor is working on this)
10. driftwm hardware accel (XWayland glamor fix)

---

## Rules for Any AI Working on This System

1. **Commands in fenced blocks only** — user pastes entire responses into zsh
2. **vision_env** — always `~/vision_env/bin/python3`, never system python
3. **Claude is last resort** — exhaust Proxima providers first
4. **Vault writes** → Subconscious/ only, never Knowledge_Base/ directly
5. **No while True** unless proper daemon with SIGTERM handler
6. **Server pattern**: `nohup ... </dev/null >> logfile 2>&1 & disown`
7. **wlrctl syntax**: `wlrctl toplevel focus title:TITLE` — plain args segfault
8. **driftwm F-keys don't work** — use mod+letter or mod+XF86KeyName
9. **Odysseus** must be started from `cd ~/odysseus` — uses relative DB path
10. **button8/9 mouse**: patch in source, binary installed, blocked by libinput/input group

---

## Boot Sequence
```zsh
# Start Echo stack
~/start-echo.sh

# Start Odysseus (if not in start-echo.sh yet)
cd ~/odysseus && nohup ~/odysseus/venv/bin/python -m uvicorn app:app \
  --host 0.0.0.0 --port 7000 </dev/null >> /tmp/odysseus.log 2>&1 & disown

# Open Cursor
cursor --no-sandbox ~/vision_assistant &

# Switch to driftwm
Super+F12
```

## Health Check
```zsh
curl -s http://localhost:8765/status | python3 -m json.tool
# Should show: ollama, proxima, searxng, panel all true
```

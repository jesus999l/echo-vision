# Echo + DriftWM — Master Handoff Document
generated: 2026-06-06 (end of session)
repo: https://github.com/jesus999l/echo-vision (latest: c016b0a)
author: jesus999l

---

## The Machine
- ThinkPad T14s Gen 1, i7-10610U, 16GB RAM, CPU-only, Linux Mint 22.3, zsh
- User: jesus999l, home: /home/jesus999l, IP: 192.168.4.46
- Tailscale: ThinkPad 100.120.238.106, S24 Ultra 100.113.49.116, Onn TV 100.80.207.10
- Python env: /home/jesus999l/vision_env — ALWAYS use this
- Shell rule: NEVER mix prose and commands. User pastes entire responses into zsh.
- Disk: 468GB total, ~14GB free (97%) — still tight, ROMs (16GB) are next target

---

## Echo Pipeline
```
Voice/Type → ask() in ai.py → _enrich_prompt()
    → build_context() + search_local() + search_if_needed() + build_system_prompt()
    → Proxima :3210 (ChatGPT → Gemini → Perplexity → Grok)
    → fallback: Ollama :11434 (qwen2.5:0.5b / gemma3n-local)
    → parse_and_execute_actions() → save_message() → memory.db
```

## Services
| Service | Port | Log | Status |
|---|---|---|---|
| Ollama | 11434 | - | ✅ |
| echo_proxima_native.py | 3210 | /tmp/echo_proxima.log | ✅ |
| SearXNG (Docker) | 8081 | - | ✅ |
| echo_rest.py | 8765 | /tmp/echo_rest.log | ✅ |
| echo_vault_watcher.py | - | /tmp/echo_vault.log | ✅ |
| echo_task_manager.py | 7799 | /tmp/echo_tasks.log | ✅ |
| echo_browser_server.py | 59996 | /tmp/echo_tv.log | ✅ |
| Odysseus | 7000 | /tmp/odysseus.log | ✅ |
| main.py (voice/wake/IPC) | 59999 | /tmp/echo_main.log | ✅ |

Start all: `~/start-echo.sh`
Health: `curl -s http://localhost:8765/status | python3 -m json.tool`

## REST API (port 8765)
```
GET  /ping, /status
POST /chat                    {"message":"...", "model":"..."}
GET  /tasks, /briefing, /kb?q=query
POST /tasks                   {"title":"...", "description":"..."}
GET  /v1/models               OpenAI-compatible
POST /v1/chat/completions     OpenAI-compatible (Odysseus bridge)
```

## Odysseus
- URL: http://192.168.4.46:7000 | Login: admin / echo1234
- Models: http://192.168.4.46:8765/v1 (Echo REST, full context)
- Auth: ~/odysseus/data/auth.json (bcrypt hash)
- Must start from cd ~/odysseus (relative DB path — in start-echo.sh)

## Ollama Models
| Model | Size | Role |
|---|---|---|
| qwen2.5:0.5b | 397MB | Fast default |
| gemma3n-local | 4.2GB | Heavy reasoning |
| mxbai-embed-large | - | Embeddings |

---

## DriftWM State
- Binary: /usr/local/bin/driftwm 0.8.1
- Source: ~/driftwm/ — cargo clean done (rebuild takes ~2min)
- Config: ~/.config/driftwm/config.toml — ALWAYS validate before switching
- Validate: `python3 -c "import tomllib; tomllib.load(open('/home/jesus999l/.config/driftwm/config.toml','rb'))"`
- Toggle: Super+F12 (Cinnamon→driftwm) | mod+XF86Favorites (quit driftwm)

## Keybindings
| Binding | Action |
|---|---|
| mod+space | fuzzel launcher |
| mod+o | zoom-to-fit |
| mod+h | home-toggle |
| mod+tab / mod+shift+tab | cycle windows |
| mod+equal / mod+minus | zoom in/out (keyboard) |
| mod+shift+arrows | pan viewport |
| mod+f | fullscreen |
| mod+w | close window |
| mod+r | reload config (NO RESTART) |
| mod+b | Firefox |
| mod+shift+d | Discord |
| mod+shift+v | vision_clicker (AI screen click) |
| mod+shift+a | text_selector (area OCR → Echo) |
| Print | screenshot → ~/Pictures/ |
| shift+Print | region screenshot |
| button9 | zoom-in (1 step) |
| button8 | zoom-out (1 step) |
| scroll wheel | smooth zoom |

## Autostart (fires on driftwm boot)
- drift_panel.py
- xbindkeys
- xdg-desktop-portal-wlr
- waybar

## Waybar
- Config: ~/.config/waybar/config.jsonc
- Style: ~/.config/waybar/style.css
- Position: bottom, always visible (auto-hide CSS doesn't work in driftwm)
- Pinned apps: Firefox, Discord, Terminal, Cursor, Obsidian, Odysseus, Steam
- To add app: add custom/myapp block + add to modules-left in config.jsonc
- Restart: `pkill waybar && waybar &`

## drift_panel
- Location: ~/vision_assistant/drift_panel.py
- Features: window roster, 5-click kill escalation, Echo chat widget at bottom
- Echo chat: POST to http://localhost:8765/chat, mic button (arecord hw:0,0, 4s)
- Keyboard: ON_DEMAND mode set — typing works only with EXCLUSIVE (steals all focus)
- Bottom margin: 32px to clear waybar

## Rust Patches Applied
1. keyboard.rs — fixed chained comparison panic on held key release
2. config/types.rs — ZoomIn/ZoomOut removed from is_repeatable() (no more zoom runaway)
3. config/parse.rs — button8/button9 recognized as BTN_0x113/0x114

## Build & Install (must be in Cinnamon, driftwm NOT running)
```zsh
cd ~/driftwm && cargo build --release 2>&1 | tail -3
sudo rm /usr/local/bin/driftwm
sudo cp ~/driftwm/target/release/driftwm /usr/local/bin/driftwm
```

---

## Vision System (NEW THIS SESSION)
### vision_clicker.py
- Takes grim screenshot → sends to Gemini Vision via Proxima :3210
- Falls back to Ollama llava if Proxima fails
- Gets click coordinates from AI → xdotool click
- Trigger: mod+shift+v OR import and call vision_action("description")
- Status: WIRED, needs testing with real Gemini Vision response

### text_selector.py
- Drag overlay to select screen region → OCR via pytesseract
- "Ask Echo" button → sends screenshot + OCR text to main.py via IPC :59999
- main.py must be running for search to work
- Trigger: mod+shift+a
- Status: OVERLAY WORKS, search works when main.py is running

### echo_shadow.py
- Idle research agent (NOT a visual cursor)
- Triggers after 600s idle → auto-searches → saves to ~/Documents/ObsidianVault/Echo/Research/
- Not yet added to start-echo.sh
- Status: EXISTS, NOT WIRED

### Shadow Cursor (CONCEPT — NOT YET BUILT)
- Ghost cursor overlay that AI controls to guide user
- Architecture: voice trigger → grim screenshot → Gemini Vision → coordinates → GTK overlay cursor
- Building blocks exist: vision_clicker + text_selector + grim + Proxima
- Next step: build GTK transparent overlay window that renders ghost cursor

---

## What Was Built/Fixed This Session
1. Port 3211 → 3210 fixed in config.py (was breaking all voice commands)
2. main.py restored from pre_memory backup
3. echo_rest.py — /v1/models + /v1/chat/completions added
4. Odysseus → Echo bridge wired
5. Odysseus password reset (auth.json)
6. Whisper base.en → small.en upgrade
7. MAX_SILENCE 8 → 20 (better transcription)
8. EchoChatWidget added to drift_panel
9. Echo added to fuzzel launcher
10. Waybar installed + configured (bottom bar, pinned apps)
11. drift_panel bottom margin (32px for waybar)
12. xdg-desktop-portal-wlr installed (Discord screen share)
13. Screenshots: Print + shift+Print wired
14. ZoomIn/ZoomOut removed from repeatable (zoom no longer runaway)
15. New driftwm binary installed
16. vision_clicker.py: grim + Proxima Vision + xdotool + mod+shift+v
17. text_selector.py: grim swap + mod+shift+a
18. wtype + xdotool installed
19. Disk cleanup: freed ~12GB (.buildozer x2, llama.cpp, old downloads)
20. All code pushed to GitHub (c016b0a)

---

## Remaining Wires / Known Issues
| Item | Priority | Notes |
|---|---|---|
| set_obsidian_bridge missing | HIGH | ai.py missing attribute, startup error |
| set_web_searcher missing | HIGH | ai.py missing attribute, startup error |
| Subconscious distillation | HIGH | 698 files waiting in Subconscious/ |
| Shadow cursor build | HIGH | GTK overlay + Gemini Vision coordinates |
| SMS remote commands | MED | Twilio webhook → Echo REST, control PC from phone via SMS |
| Session restore driftwm | MED | Reopen windows on compositor restart |
| mod+e Echo terminal | MED | Removed (TOML quote issues), needs clean impl |
| drift_panel typing | MED | Layer-shell keyboard — EXCLUSIVE works but steals focus |
| Hermes OpenRouter key | MED | Fix 30min Discord response lag |
| Scribe pipeline | MED | Conversation history → Obsidian |
| .gitignore cleanup | LOW | Add chroma_db/, *.bak, *.pre_* |
| Build own Proxima | LOW | Fold echo_proxima_native.py into ai.py |
| Disk space | URGENT | 97% full, ROMs (16GB) need moving to external |
| waybar auto-hide | LOW | CSS trick doesn't work in driftwm |
| ChromaDB expansion | LOW | Only 10 entries |

---

## Feature Roadmap
### Next Session
1. Build shadow cursor overlay (GTK transparent window + ghost cursor rendering)
2. Fix set_obsidian_bridge + set_web_searcher in ai.py
3. Test vision_clicker end-to-end with Gemini Vision
4. SMS gateway (Twilio → Echo REST)
5. Move ROMs to external drive (free ~16GB)

### Architecture
6. Session restore for driftwm
7. Echo → driftwm IPC (voice window control)
8. Proxima watchdog
9. Planner layer (goal → tasks → execution)
10. driftwm hardware accel

---

## Rules for Any AI on This System
1. Commands in fenced blocks only — user pastes into zsh
2. vision_env always — ~/vision_env/bin/python3
3. Claude is last resort — Proxima first (ChatGPT/Gemini/Perplexity/Grok)
4. Proxima port is :3210 — any doc saying :3211 is WRONG
5. ALWAYS validate TOML before switching to driftwm
6. wlrctl: `wlrctl toplevel focus title:TITLE` — plain args segfault
7. Odysseus: cd ~/odysseus before starting
8. driftwm binary: sudo rm first, then sudo cp
9. No while True without SIGTERM handler
10. Server: nohup ... </dev/null >> logfile 2>&1 & disown
11. git push after every significant session
12. Disk at 97% — avoid large downloads without clearing space first

## Boot Sequence
```zsh
~/start-echo.sh
cursor --no-sandbox ~/vision_assistant &
Super+F12
```

## Health Check
```zsh
curl -s http://localhost:8765/status | python3 -m json.tool
curl -s http://localhost:3210/status | python3 -m json.tool
df -h / | tail -1
```

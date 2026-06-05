# Echo + DriftWM — Master Handoff Document
generated: 2026-06-05 (end of session)
repo: https://github.com/jesus999l/echo-vision (commit 48abe37 + zoom fix)
author: jesus999l

---

## The Human

- **Name**: jesus999l (J999l)
- **Machine**: ThinkPad T14s Gen 1, i7-10610U, 16GB RAM, CPU-only, Linux Mint 22.3, zsh
- **IP**: 192.168.4.46 (LAN) — Tailscale also active
- **Python env**: /home/jesus999l/vision_env — ALWAYS use this, never system python
- **Shell rule**: NEVER mix prose and commands in same block. User pastes entire responses into zsh.
- **Style**: Casual, direct. Build complete working files. Minimal abstract explanation.

---

## Project 1: Echo — Local AI OS

### Pipeline
```
User speaks/types
    ↓
ask() in ai.py
    ↓
_enrich_prompt() — builds context from:
    • build_context()       — SQLite memory + recent messages
    • search_local()        — tasks, habits, journal, calendar
    • search_if_needed()    — SearXNG web search
    • build_system_prompt() — personality + goals + upcoming events
    ↓
Proxima :3210 (ChatGPT → Gemini → Perplexity → Grok)
    ↓ if all fail →
Ollama :11434 (qwen2.5:0.5b default, gemma3n-local for heavy)
    ↓
parse_and_execute_actions() → save_message() → memory.db
```

### Services
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
| main.py (voice/wake) | IPC | /tmp/echo_main.log | ✅ |

Start all: `~/start-echo.sh`
Health: `curl -s http://localhost:8765/status | python3 -m json.tool`

### REST API (port 8765)
```
GET  /ping, /status
POST /chat              {"message":"...", "model":"..."}
GET  /tasks, /briefing, /kb?q=query
POST /tasks             {"title":"...", "description":"..."}
GET  /v1/models         OpenAI-compatible (for Odysseus)
POST /v1/chat/completions OpenAI-compatible (for Odysseus)
```

### Odysseus
- URL: http://192.168.4.46:7000
- Login: admin / echo1234
- Models: points to http://192.168.4.46:8765/v1
- Must start from `cd ~/odysseus` (relative DB path — already in start-echo.sh)
- Password stored in ~/odysseus/data/auth.json (bcrypt hash)

### Ollama Models
| Model | Size | Role |
|---|---|---|
| qwen2.5:0.5b | 397MB | Fast default |
| gemma3n-local | 4.2GB | Heavy reasoning |

### What Was Fixed This Session
1. Port 3211 → 3210 bug fixed in config.py (architectural handoff doc had wrong port)
2. main.py restored from pre_memory backup (stub had overwritten real entry point)
3. echo_rest.py — added /v1/models + /v1/chat/completions endpoints
4. Odysseus → Echo bridge wired
5. Odysseus password reset (auth.json bcrypt)
6. Whisper upgraded base.en → small.en
7. MAX_SILENCE 8 → 20 (stops cutting off mid-sentence)
8. Wake word routing fixed (:3211 → :3210)
9. EchoChatWidget added to drift_panel (text input + mic + response)
10. Echo added to fuzzel launcher (.local/share/applications/echo.desktop)

### Known Issues / Remaining Wires
| Item | Notes |
|---|---|
| set_obsidian_bridge missing | ai.py missing attribute, Obsidian bridge fails on startup |
| set_web_searcher missing | ai.py missing attribute, web search fails on startup |
| Subconscious distillation | 698 files in ~/Documents/ObsidianVault/Echo/Subconscious/ waiting |
| Shadow cursor | echo_shadow.py exists, needs keybind |
| Hermes OpenRouter key | Fix 30min Discord response time |
| drift_panel typing | Layer-shell keyboard — EXCLUSIVE works but steals focus, ON_DEMAND doesn't work in driftwm |
| drift_panel mic | Uses arecord hw:0,0 — test without stealing EasyEffects |
| mod+e Echo terminal | Removed (TOML quote issues) — needs clean reimplementation |
| Session restore | Feature requested — reopen windows on driftwm restart |
| .gitignore | Add chroma_db/, *.bak, *.pre_* |
| Build own Proxima | Fold echo_proxima_native.py into ai.py routing |
| Scribe pipeline | Conversation history → Obsidian |

---

## Project 2: DriftWM — Infinite Canvas Compositor

### Install State
- Binary: /usr/local/bin/driftwm 0.8.1 (patched: button8/9 + zoom non-repeatable)
- Source: ~/driftwm/ (Rust, smithay backend)
- Config: ~/.config/driftwm/config.toml — ALWAYS validate before switching
- Validate: `python3 -c "import tomllib; tomllib.load(open('/home/jesus999l/.config/driftwm/config.toml','rb'))"`
- Toggle: Super+F12 (Cinnamon→driftwm) | mod+XF86Favorites (driftwm→quit)

### Working Keybindings
| Binding | Action |
|---|---|
| mod+space | fuzzel launcher |
| mod+o | zoom-to-fit (overview) |
| mod+h | home-toggle |
| mod+c | focus-center |
| mod+tab / mod+shift+tab | cycle windows |
| mod+equal / mod+minus | zoom in/out |
| mod+shift+arrows | pan viewport |
| mod+arrows | nudge window |
| mod+f | toggle fullscreen |
| mod+m | fit window |
| mod+w | close window |
| mod+r | reload config |
| mod+t | btop++ |
| mod+b | Firefox |
| mod+shift+d | Discord |
| Print | screenshot → ~/Pictures/ |
| shift+Print | region screenshot |
| button9 | zoom-in (1 step) |
| button8 | zoom-out (1 step) |
| scroll wheel | smooth zoom |

### Autostart
- drift_panel.py
- xbindkeys
- xdg-desktop-portal-wlr
- waybar

### Waybar
- Config: ~/.config/waybar/config.jsonc
- Style: ~/.config/waybar/style.css
- Position: bottom, always visible (auto-hide CSS doesn't work in driftwm)
- Pinned: Firefox, Discord, Terminal, Cursor, Obsidian, Odysseus, Steam
- To add app: add custom/myapp block to config.jsonc, add to modules-left
- Battery error on start is harmless

### drift_panel
- Location: ~/vision_assistant/drift_panel.py
- Features: window roster grouped by app, kill buttons (5-click escalating), Echo chat widget
- Echo chat: sends to http://localhost:8765/chat, mic button records 4s via arecord
- Keyboard focus: set to ON_DEMAND (typing broken in driftwm), EXCLUSIVE works but steals all focus
- Bottom margin: 32px to clear waybar

### Known Issues
| Issue | Notes |
|---|---|
| Waybar auto-hide | CSS margin trick doesn't work in driftwm — bar always visible |
| shift+Print | slurp quoting fragile in TOML — may need testing |
| Session restore | REQUESTED — reopen windows on restart, not yet implemented |
| Bluetooth popup | blueman-applet can't be closed in Wayland |
| button8/9 hold-zoom | Rust feature needed — ContinuousAction for held buttons not implemented |

### Rust Changes Made This Session
1. keyboard.rs — fixed chained comparison panic (held key release)
2. config/types.rs — removed ZoomIn/ZoomOut from is_repeatable() — zoom no longer repeats on hold
3. config/parse.rs — button8/button9 recognized as BTN triggers

### Build & Install (must be in Cinnamon, driftwm not running)
```zsh
cd ~/driftwm && cargo build --release 2>&1 | tail -3
sudo rm /usr/local/bin/driftwm
sudo cp ~/driftwm/target/release/driftwm /usr/local/bin/driftwm
```

---

## Feature Roadmap (prioritized)

### Next Session
1. Fix set_obsidian_bridge + set_web_searcher in ai.py
2. Session restore for driftwm (save/restore window positions on restart)
3. Subconscious distillation pass (698 files)
4. .gitignore cleanup
5. mod+e Echo terminal (clean TOML-safe implementation)

### High Value
6. Shadow cursor (echo_shadow.py + keybind)
7. Hermes OpenRouter key (fix 30min Discord lag)
8. Scribe pipeline (conversation history → Obsidian)
9. Proxima watchdog (notify if Proxima dies)
10. Echo → driftwm IPC (voice control windows)

### Architecture
11. Build own Proxima into Echo (fold echo_proxima_native.py into ai.py)
12. Planner layer (goal → tasks → execution)
13. driftwm hardware accel (XWayland glamor)
14. button8 hold + scroll = smooth zoom (Rust feature)
15. ChromaDB expansion (only 10 entries, needs more distillation)

---

## Rules for Any AI Working on This System
1. Commands in fenced blocks only — user pastes into zsh
2. vision_env always — ~/vision_env/bin/python3, never system python
3. Claude is last resort — exhaust Proxima (ChatGPT/Gemini/Perplexity) first
4. Vault writes → Subconscious/ only, never Knowledge_Base/ directly
5. Proxima port is :3210 — any doc saying :3211 is WRONG
6. ALWAYS validate TOML before switching to driftwm
7. wlrctl syntax: `wlrctl toplevel focus title:TITLE` — plain args segfault
8. Odysseus must cd ~/odysseus before starting
9. No while True without SIGTERM handler
10. Server pattern: nohup ... </dev/null >> logfile 2>&1 & disown
11. driftwm binary: sudo rm first, then sudo cp (Text file busy otherwise)
12. git push after every significant session

## Boot Sequence
```zsh
~/start-echo.sh
cursor --no-sandbox ~/vision_assistant &
Super+F12  # switch to driftwm
```

## Health Check
```zsh
curl -s http://localhost:8765/status | python3 -m json.tool
# Expected: ollama, proxima, searxng, panel all true
curl -s http://localhost:3210/status
# Expected: all providers ready with cookies
```

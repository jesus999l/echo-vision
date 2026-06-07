# Echo + DriftWM — Master Handoff Document
generated: 2026-06-06 (end of session, ~30hr total)
repo: https://github.com/jesus999l/echo-vision (latest: 5757f6d)
author: jesus999l

---

## The Machine
- ThinkPad T14s Gen 1, i7-10610U, 16GB RAM, CPU-only, Linux Mint 22.3, zsh
- User: jesus999l, IP: 192.168.4.46, Tailscale: 100.120.238.106
- Python env: ~/vision_env — ALWAYS use this
- Disk: 468GB, ~15GB free (97%) — ROMs (16GB in ~/Documents/Games) are next target
- Shell rule: commands in fenced blocks only, user pastes into zsh

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
| echo_shadow_cursor.py | 59998 | /tmp/echo_shadow.log | ✅ |

Start all: `~/start-echo.sh`
Health: `curl -s http://localhost:8765/status | python3 -m json.tool`

## Odysseus
- URL: http://192.168.4.46:7000 | Login: admin / echo1234
- Models: http://192.168.4.46:8765/v1 (Echo REST, full context)
- Must cd ~/odysseus before starting (in start-echo.sh)

---

## DriftWM State
- Binary: /usr/local/bin/driftwm 0.8.1 (patched)
- Config: ~/.config/driftwm/config.toml — ALWAYS validate before switching
- Validate: `python3 -c "import tomllib; tomllib.load(open('/home/jesus999l/.config/driftwm/config.toml','rb'))"`
- Toggle: Super+F12 (Cinnamon→driftwm) | mod+XF86Favorites (quit)
- Build: `cd ~/driftwm && cargo build --release` then `sudo rm /usr/local/bin/driftwm && sudo cp ~/driftwm/target/release/driftwm /usr/local/bin/driftwm`

## Keybindings
| Binding | Action |
|---|---|
| mod+space | fuzzel launcher |
| mod+o | zoom-to-fit (see all windows) |
| mod+h | home-toggle |
| mod+tab / mod+shift+tab | cycle windows |
| mod+equal / mod+minus | zoom in/out |
| mod+r | reload config (NO RESTART) |
| mod+b | Firefox |
| mod+shift+d | Discord |
| mod+shift+v | vision_clicker (AI screen click) |
| mod+shift+a | text_selector (area OCR → Echo) |
| mod+shift+f | shadow cursor toggle (off→follow→active) |
| Print | screenshot → ~/Pictures/ |
| shift+Print | region screenshot |
| button9 | zoom-in (1 step, 5%) |
| button8 | zoom-out (1 step, 5%) |
| scroll wheel | smooth zoom |

## Autostart
- drift_panel.py, xbindkeys, xdg-desktop-portal-wlr, waybar
- echo_shadow_cursor.py (adds shadow cursor on boot)

## Waybar
- Config: ~/.config/waybar/config.jsonc
- Style: ~/.config/waybar/style.css
- Position: bottom, semi-transparent (0.35 opacity) when not hovered
- Pinned: Firefox, Discord, Terminal, Cursor, Obsidian, Odysseus, Steam
- Restart: `pkill waybar && waybar &`
- To add app: add custom/myapp block + add to modules-left

## drift_panel
- Location: ~/vision_assistant/drift_panel.py
- Kill buttons: 5-click escalating, uses `wlrctl toplevel close title:TITLE`
- Focus: uses `wlrctl toplevel focus title:TITLE`
- Echo chat: POST to :8765/chat, mic button (4s arecord)
- Keyboard: ON_DEMAND mode (typing limited in driftwm layer-shell)

## Rust Patches Applied
1. keyboard.rs — fixed chained comparison panic on held key release
2. config/types.rs — ZoomIn/ZoomOut removed from is_repeatable()
3. config/parse.rs — button8/button9 as BTN triggers

---

## Echo Shadow System

### echo_shadow_cursor.py
- **What it is**: GTK TOPLEVEL XWayland window, transparent 1920x1080, always on top
- **Skin**: Winged diamond angel — amber wings (flapping), purple diamond eye, glowing halo, bobbing tail dragonlet. Based on pet from player1who.neocities.org
- **Socket**: :59998, accepts JSON commands
- **Commands**:
  - `{"action":"move","x":960,"y":540,"label":"text"}` — move to position
  - `{"action":"follow","enabled":true}` — follow mouse cursor
  - `{"action":"follow","enabled":false}` — stop following
  - `{"action":"hide"}` — hide
  - `{"action":"click","x":100,"y":200}` — move + click
  - `{"action":"ai","instruction":"click settings"}` — AI vision mode
- **Toggle hotkey**: mod+shift+f (cycles: off → follow → active-only → off)
- **State file**: /tmp/echo_shadow_mode
- **Current limitation**: Window is placed on driftwm canvas at [900,500]. Follow mode works but cursor coordinates don't perfectly map to canvas coordinates. Echo is visible, animated, socket works.
- **Next step for true freedom**: Implement Echo rendering directly in driftwm Rust render pipeline (compositor-level overlay, no window needed)

### shadow_toggle.py
- Cycles shadow modes, sends to daemon via socket
- Shows notify-send on mode change

### vision_clicker.py
- Screenshot via grim → Gemini Vision via Proxima :3210 → coordinates → xdotool click
- Falls back to Ollama llava
- Trigger: mod+shift+v

### text_selector.py
- Drag overlay to select screen region → OCR → sends to main.py IPC :59999
- main.py must be running for search to work
- Trigger: mod+shift+a
- Uses grim for screenshot

### echo_shadow.py (different from shadow cursor)
- Idle research agent — triggers after 600s idle
- Auto-searches and saves to ~/Documents/ObsidianVault/Echo/Research/
- NOT yet added to start-echo.sh

---

## Echo Shadow — Phase Roadmap
| Phase | Goal | Status |
|---|---|---|
| 1 | Ghost cursor overlay, animated, socket controlled | ✅ DONE |
| 2 | Vision assisted guidance (screenshot → Gemini → coordinates) | ✅ WIRED |
| 3 | Multi-step navigation (AI generates step sequence) | PENDING |
| 4 | Workflow learning from input observation | PENDING |
| 5 | Compositor-level rendering (true full-canvas freedom) | FUTURE |

---

## Known Issues / Remaining Wires
| Item | Priority | Notes |
|---|---|---|
| set_obsidian_bridge missing | HIGH | ai.py missing attribute, startup error |
| set_web_searcher missing | HIGH | ai.py missing attribute, startup error |
| Subconscious distillation | HIGH | 698 files in Subconscious/ waiting |
| Echo shadow canvas coords | HIGH | Follow mode coords don't map to canvas. Fix: Rust compositor layer |
| Disk space | HIGH | 97% full, move ROMs (16GB) to external drive |
| Session restore driftwm | MED | Reopen windows on compositor restart |
| SMS remote commands | MED | Twilio webhook → Echo REST |
| Hermes OpenRouter key | MED | Fix 30min Discord lag |
| Scribe pipeline | MED | Conversation history → Obsidian |
| mod+e Echo terminal | MED | Removed (TOML issues), needs clean impl |
| Waybar auto-hide slide | LOW | CSS trick doesn't work in driftwm |
| .gitignore | LOW | Add chroma_db/, *.bak, *.pre_* |
| ChromaDB expansion | LOW | Only 10 entries |
| driftwm hardware accel | LOW | XWayland glamor fix |

---

## Rules
1. Commands in fenced blocks only — user pastes into zsh
2. vision_env always — ~/vision_env/bin/python3
3. Claude is last resort — Proxima first (ChatGPT/Gemini/Perplexity/Grok)
4. Proxima port is :3210 — any doc saying :3211 is WRONG
5. ALWAYS validate TOML before switching to driftwm
6. wlrctl: `wlrctl toplevel focus title:TITLE` (with title: prefix)
7. Odysseus: cd ~/odysseus before starting
8. driftwm binary: sudo rm first, then sudo cp (Text file busy otherwise)
9. No while True without SIGTERM handler
10. Server: nohup ... </dev/null >> logfile 2>&1 & disown
11. git push after every significant session
12. Disk at 97% — avoid large downloads

## Boot Sequence
```zsh
~/start-echo.sh
cursor --no-sandbox ~/vision_assistant &
Super+F12
# In driftwm:
nohup ~/vision_env/bin/python3 ~/vision_assistant/echo_shadow_cursor.py </dev/null >> /tmp/echo_shadow.log 2>&1 & disown
```

## Health Check
```zsh
curl -s http://localhost:8765/status | python3 -m json.tool
curl -s http://localhost:3210/status | python3 -m json.tool
df -h / | tail -1
pgrep -f echo_shadow_cursor && echo "shadow: running"
```

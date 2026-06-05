# Echo + DriftWM — Session Handoff
generated: 2026-06-05 (end of session)
repo: https://github.com/jesus999l/echo-vision

---

## What Was Fixed/Built This Session

### Echo Pipeline
- **Port 3211 → 3210 bug fixed** in `config.py` — architectural handoff doc had wrong port, all voice commands were failing
- **main.py restored** from `main.py.pre_memory_20260513_230313` — stub had overwritten the real entry point
- **echo_rest.py** — added `/v1/models` and `/v1/chat/completions` OpenAI-compatible endpoints
- **Odysseus → Echo bridge wired** — Odysseus now routes through Echo REST, gets full context (tasks, calendar, vault, web search)
- **Odysseus password reset** — hash written directly to `data/auth.json`, credentials: `admin` / `echo1234`
- **Whisper upgraded** — `base.en` → `small.en` for better transcription accuracy
- **Transcription window extended** — MAX_SILENCE 8 → 20 (160ms → 400ms), stops cutting off mid-sentence
- **Wake word routing fixed** — was hitting :3211, now hits :3210, voice commands work

### DriftWM
- **TOML fixed** — broken `mod+e` line at line 60 was invalidating entire config, all keybindings were dead
- **New driftwm binary installed** — `sudo cp ~/driftwm/target/release/driftwm /usr/local/bin/driftwm`
- **Screenshots working** — `Print` = full screen → `~/Pictures/ss-{timestamp}.png` + notify-send
- **Waybar installed** — bottom panel with clock, CPU, RAM, battery, network, volume, tray, pinned app launchers
- **Waybar auto-hide** — slides away when not hovered, slides back on mouse-to-bottom
- **drift_panel bottom margin** — 32px margin added so waybar doesn't overlap kill buttons
- **xdg-desktop-portal-wlr installed** — enables Discord screen share in Wayland
- **input group** — `sudo usermod -aG input jesus999l` done, needs relogin to activate side buttons fully
- **Echo desktop entry** — Echo shows up in fuzzel launcher (`mod+space`)
- **EchoChatWidget** added to drift_panel — text input + mic button + response area at bottom of panel
- **Warframe window rule** — updated to 1275×750

### Infrastructure
- **start-echo.sh** — Odysseus `cd ~/odysseus` fix applied
- **All code pushed to GitHub** — `jesus999l/echo-vision`, commit `48abe37`

---

## Current Service Map
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
Health check: `curl -s http://localhost:8765/status | python3 -m json.tool`

---

## Known Issues / Remaining Wires

### Immediate
| Item | Notes |
|---|---|
| Relogin needed | `input` group change needs logout/login to activate side buttons |
| shift+Print region select | slurp command works but TOML quoting fragile — test after relogin |
| drift_panel typing | Layer-shell keyboard focus — ON_DEMAND mode works but driftwm may not fully implement it. EXCLUSIVE works but steals all keyboard focus. |
| Mic in drift_panel | Uses `arecord hw:0,0` — test if it records correctly without stealing EasyEffects |
| mod+e Echo terminal | Removed due to TOML quote issues — needs clean reimplementation |

### High Value
| Item | Notes |
|---|---|
| Subconscious distillation | 698 files in `~/Documents/ObsidianVault/Echo/Subconscious/` waiting |
| set_obsidian_bridge missing | `ai.py` missing this attribute, Obsidian bridge fails on startup |
| set_web_searcher missing | `ai.py` missing this attribute, web search fails on startup |
| Shadow cursor | `echo_shadow.py` exists, needs keybind wired |
| Hermes OpenRouter key | Fix 30min Discord response time |
| .gitignore | Add chroma_db/, *.bak, *.pre_* to avoid large file warnings |

### Architecture
| Item | Notes |
|---|---|
| Build own Proxima into Echo | Fold echo_proxima_native.py directly into ai.py routing — remove external dependency |
| Proxima watchdog | Alert if Proxima dies silently |
| Echo → driftwm IPC | Voice control windows ("focus Discord", "close this") |
| Scribe pipeline | ChatGPT/Claude/Gemini conversation history → Obsidian |
| driftwm hardware accel | XWayland glamor fix |
| button8 hold + scroll zoom | Smooth incremental zoom — driftwm supports modifiers, needs Rust implementation |

---

## DriftWM Config State
- Config: `~/.config/driftwm/config.toml` — TOML VALID as of this session
- Autostart: drift_panel.py, xbindkeys, xdg-desktop-portal-wlr, waybar
- Warframe rule: 1275×720 at [100, 50]
- Screenshots: `Print` = full, `shift+Print` = region (slurp)
- Toggle: `Super+F12` Cinnamon→driftwm | `mod+XF86Favorites` driftwm→quit

## Waybar
- Config: `~/.config/waybar/config.jsonc`
- Style: `~/.config/waybar/style.css`
- Position: bottom, auto-hide on hover
- Pinned apps: Firefox, Discord, Terminal, Cursor, Obsidian, Odysseus, Steam
- **To add your own app**: edit `~/.config/waybar/config.jsonc`, add a `custom/myapp` block, add name to `modules-left`

## Odysseus
- URL: http://192.168.4.46:7000
- Login: admin / echo1234
- Models: points to http://192.168.4.46:8765/v1 (Echo REST)
- Must start from `cd ~/odysseus` — uses relative DB path (already in start-echo.sh)

---

## Rules (for any AI picking this up)
1. Commands in fenced blocks only — user pastes into zsh
2. `~/vision_env/bin/python3` always — never system python
3. Claude is last resort — exhaust Proxima (ChatGPT/Gemini/Perplexity) first
4. Vault writes → Subconscious/ only, never Knowledge_Base/ directly
5. Proxima port is **:3210** — ignore any doc saying :3211
6. TOML config — always validate with `python3 -c "import tomllib; tomllib.load(open('...','rb'))"` before switching to driftwm
7. wlrctl syntax: `wlrctl toplevel focus title:TITLE` — plain args segfault
8. Odysseus must `cd ~/odysseus` before starting
9. No while True without SIGTERM handler
10. Server pattern: `nohup ... </dev/null >> logfile 2>&1 & disown`

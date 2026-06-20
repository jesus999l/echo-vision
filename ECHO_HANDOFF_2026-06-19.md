# Echo Master Handoff — June 19, 2026

## What Echo Is
Echo is a persistent, local-first AI OS companion running on a ThinkPad T14s Gen 1 (Ubuntu, DriftWM Wayland compositor). She is not a chatbot — she is a compositor-level animated sprite that orbits the cursor, listens for a wake word, speaks via TTS, sees the screen, controls windows, and routes intelligence through a multi-provider AI pipeline. She runs fully offline by default. No data leaves the machine unless explicitly requested.

---

## Session Summary — What We Did Today

### F-Key Fix (DONE)
- Root cause: `~/.config/driftwm/config.toml` had `XF86AudioMute = "exec cinnamon-settings"` and `XF86AudioMicMute = "exec pavucontrol"` — overriding defaults
- Fix: Mapped both to toggle scripts instead
- `XF86AudioMute` → `exec bash /home/jesus999l/toggle_speaker.sh`
- `XF86AudioMicMute` → `exec bash /home/jesus999l/toggle_mic.sh`
- LED sudoers fix: `echo 'jesus999l ALL=(ALL) NOPASSWD: /usr/bin/tee' | sudo tee /etc/sudoers.d/echo-leds`
- keyd installed from source at `/usr/local/bin/keyd`, config at `/etc/keyd/default.conf`
- keyd maps F1-F12 to XF86 media keys, ID `0001:0001` (AT Translated Set 2)
- xbindkeys at PID range handles toggle scripts via XF86AudioMute/MicMute

### Waybar (DONE)
- Built from source at `/usr/local/bin/waybar-new`
- Config: `~/.config/waybar/config.jsonc`
- Start: `waybar-new 2>/dev/null &`
- Modules left: custom/menu | custom/separator | wlr/taskbar | custom/sticky
- Modules right: tray | bluetooth | network | pulseaudio | battery | custom/keyboard | clock#date | clock#calendar
- `wlr/taskbar` shows app icons, click to focus, ignores sticky.py and drift_panel.py
- `custom/sticky` — `~/vision_assistant/echo_sticky_bar.py` — shows 📝 + count, hover lists note titles, click focuses Sticky app (title:Notes)
- GTK reorder_child warnings are harmless — from 27 sticky windows, ignore them

### Sticky Notes (DONE)
- App: `/usr/bin/sticky` → `/usr/lib/sticky/sticky.py` (system package)
- 27 floating notes on DriftWM canvas — kept alive, hidden from waybar taskbar via ignore-list
- ignore-list must use `"sticky.py"` not `"sticky"` — exact app_id match required

### New Services Started (DONE)
- **echo_vault** `:8767` — `~/vision_assistant/echo_vault.py`
  - turbovec TurboQuant vector index + sentence-transformers all-MiniLM-L6-v2
  - Scans: `~/Documents/ObsidianVault/` + `~/.flint/vault/`
  - Race condition fix: waits for embedder before scanning (delayed_load loop)
  - Start: `nohup ~/vision_env/bin/python3 ~/vision_assistant/echo_vault.py </dev/null >> /tmp/echo_vault.log 2>&1 &`
  - Status: `curl -s http://localhost:8767/`
  - Takes 10-15 min to index 11,424 chunks on first run

- **echo_brainbridge** `:8768` — `~/vision_assistant/echo_brainbridge.py`
  - Parallel ChatGPT + Gemini + Perplexity via echo_ai_hub.py cookies
  - Synthesizes via Ollama qwen3:4b
  - Start: `nohup ~/vision_env/bin/python3 ~/vision_assistant/echo_brainbridge.py </dev/null >> /tmp/echo_brainbridge.log 2>&1 &`
  - Status: `curl -s http://localhost:8768/`

- **echo_vision_agent** `:8769` — `~/vision_assistant/echo_vision_agent.py`
  - EchoSprite's eyes and hands
  - Screen capture via grim → context to AI → executes wlrctl/xdotool actions
  - Action commands in AI response: FOCUS:title, CLOSE:title, EXEC:cmd, TYPE:text, SPEAK:text, CLICK:x,y
  - Filters sticky.py from window list automatically
  - Start: `nohup ~/vision_env/bin/python3 ~/vision_assistant/echo_vision_agent.py </dev/null >> /tmp/echo_vision_agent.log 2>&1 &`
  - Status: `curl -s http://localhost:8769/`
  - Observe: `curl -s -X POST http://localhost:8769/observe`

- **echo_mcp_setup** — `~/vision_assistant/echo_mcp_setup.py`
  - Wraps echo_rest/vault/brainbridge/tasks as MCP servers via mcpify
  - Configs at `~/.config/echo-mcp/`
  - Claude Desktop config at `~/.config/claude/mcp_servers.json`
  - Run once to generate configs, then start MCP servers on ports 8900-8903

### Wake Word Pipeline (UPDATED)
- Voice flow: sounddevice → Vosk → faster-whisper → echo_vision_agent:8769/ask → AI response → TTS
- Screen-aware queries: only captures screen if query contains: screen, see, look, window, open, visible, desktop
- **Conversation mode**: after Echo responds, listens for follow-up for 30 seconds without needing "Hey Echo"
- Double-speak fix: vision_agent handles TTS, wake_word skips if `_vision_spoke` is True
- Start: `nohup ~/vision_env/bin/python3 ~/vision_assistant/wake_word.py </dev/null >> /tmp/wake_word.log 2>&1 &`

### DriftWM EchoSprite (UPDATED — needs hot-swap)
- **Idle wander**: after 30s cursor idle, Echo detaches and roams canvas with `...` bubble
- Wander targets update every 5s with sine/cosine patterns
- Moving mouse instantly snaps Echo back to cursor orbit
- **Zoom scaling**: sprite size scales 48-192px with zoom level (clamp 0.5-2.0)
- Orbit radius scales 32-200px with zoom
- Wander radius inversely scales — zoomed out = roams further across canvas
- Source: `~/driftwm/src/render/cursor.rs` + `~/driftwm/src/state/cursor.rs`
- New state fields: `echo_wander_x/y`, `cursor_last_move_ms`, `echo_wandering`, `cursor_idle_secs`
- Build: `cd ~/driftwm && cargo build --release 2>&1 | tail -5`
- Hot-swap: `sudo rm /usr/local/bin/driftwm && sudo cp ~/driftwm/target/release/driftwm /usr/local/bin/driftwm`
- **Binary built and hot-swapped this session** ✅

### Repos Cloned (~/repos/)
- ObserverAI — local AI agent, screen-aware computing
- OpenCut — open source video editor
- Wan2GP — AI video generation (GPU poor friendly)
- dexter — autonomous financial research agent
- tiny-world-builder — single HTML AI world generator
- docker-android — Android emulator in Docker
- turbovec — Rust TurboQuant vector index (pip install turbovec ✅)
- mcpify — wraps any project as MCP server (installed ✅)
- VibeVoice — Microsoft open source TTS/ASR
- StoryGen-Atelier — AI storyboard + video (needs Gemini key)
- iptv — free IPTV playlists for VLC
- waybar-src — waybar source

---

## Current Service Map

| Service | Port | Status | Start Command |
|---------|------|--------|---------------|
| echo_rest | 8765 | ✅ UP | in start-echo.sh |
| echo_vault | 8767 | ⚠️ loading | see above |
| echo_brainbridge | 8768 | ✅ UP | see above |
| echo_vision_agent | 8769 | ✅ UP | see above |
| echo_task_manager | 7799 | ✅ UP (from prev session) | ~/vision_assistant/echo_task_manager.py |
| Proxima Electron | 3211 | ✅ UP | cd ~/Proxima && nohup ./node_modules/.bin/electron . </dev/null >> /tmp/proxima_electron.log 2>&1 & |
| Ollama | 11434 | ✅ UP | systemd |
| SearXNG | auto | ✅ UP | in start-echo.sh |
| waybar | - | ✅ UP | waybar-new 2>/dev/null & |
| wake_word | - | ✅ UP | see above |

---

## Key File Locations

### DriftWM
- Source: `~/driftwm/`
- Binary: `/usr/local/bin/driftwm`
- Config: `~/.config/driftwm/config.toml`
- Sprite render: `~/driftwm/src/render/cursor.rs`
- Sprite state: `~/driftwm/src/state/cursor.rs`
- Session wrapper: `~/start-driftwm-session.sh`
- Keybindings in config.toml — CRITICAL: XF86 keys must point to toggle scripts, not cinnamon-settings

### Echo Python Stack
- All services: `~/vision_assistant/`
- Python env: `~/vision_env/bin/python3` — ALWAYS use this, never system python
- AI hub (direct cookie queries): `~/vision_assistant/echo_ai_hub.py`
- Wake word: `~/vision_assistant/wake_word.py`
- Voice TTS: `~/vision_assistant/voice.py` (Piper + sox, pitch 250, rate 18000)
- Vision agent: `~/vision_assistant/echo_vision_agent.py`
- Vault: `~/vision_assistant/echo_vault.py`
- Brainbridge: `~/vision_assistant/echo_brainbridge.py`
- Sticky bar: `~/vision_assistant/echo_sticky_bar.py`
- Repos bar: `~/vision_assistant/echo_repos_bar.py`
- MCP setup: `~/vision_assistant/echo_mcp_setup.py`

### Config Files
- Waybar: `~/.config/waybar/config.jsonc`
- DriftWM bindings: `~/.config/driftwm/config.toml`
- keyd: `/etc/keyd/default.conf`
- sudoers LED: `/etc/sudoers.d/echo-leds`
- MCP configs: `~/.config/echo-mcp/`
- Claude MCP: `~/.config/claude/mcp_servers.json`
- xbindkeys: `~/.xbindkeysrc`

### Toggle Scripts
- Speaker: `~/toggle_speaker.sh` (pactl + LED at /sys/class/leds/platform::mute/brightness)
- Mic: `~/toggle_mic.sh` (pactl + LED at /sys/class/leds/platform::micmute/brightness)

### Obsidian Vault
- `~/Documents/ObsidianVault/Echo/` — main Echo notes
- `~/.flint/vault/` — Flint vault (scanned by echo_vault)

---

## Critical Rules (Never Break These)

1. **Never touch `/etc/lightdm/lightdm.conf`** — session config in `~/.dmrc` only
2. **Always use `~/vision_env/bin/python3`** — never system python3
3. **PROXIMA_URL always `:3211`** (Electron) in echo_proxima_bridge.py
4. **Never paste multi-line Rust/Python into zsh** — use file writers or download files
5. **zsh breaks on `!` in strings** — always write patches as .py files and download them
6. **Never `sudo rm` old DriftWM binary without stopping it first** — "Text file busy"
7. **GRUB timeout must stay >0**
8. **SSD health critical** — Media_Wearout_Indicator at 7/100, avoid large writes
9. **DriftWM KMS/DRM backend not tested** — only run nested (inside Cinnamon X session) or from TTY with dbus-run-session
10. **Ollama `think: false` must be top-level** in payload, not inside options{}

---

## Next Steps (Priority Order)

1. **EchoSprite GLSL holographic shader** — replace pixel art sprite with ZZZ-style cyan/magenta holographic dancing character. Render in compositor via GLSL. Reference: image 1 from session (Jane Doe, Zenless Zone Zero aesthetic).

2. **Echo curiosity system** — when wandering, Echo reads window titles, picks one she's curious about, writes a permission request to `/tmp/echo_bubble.txt` ("Can I look at this?"), listens for yes/no voice response, then acts.

3. **echo_vault full index** — currently stuck at 0 docs due to embedder race condition. Fix confirmed — just needs a clean restart and 15 min to embed 11,424 chunks.

4. **Wire echo_vault into voice pipeline** — when Echo answers questions, search vault first for relevant context, inject into AI prompt.

5. **Echo conversation synthesis** — currently echo_ai_hub.py takes first successful provider. Should synthesize all 3 responses (brainbridge-style) for better answers.

6. **EchoSprite 3D model pipeline**:
   - Phase 1: VRM/GLTF viewer as Wayland window, Echo controls it
   - Phase 2: Echo scripts Blender via Python API to generate/modify her own model
   - Phase 3: Export to sprite sheet, render at compositor level
   - Has Blender installed

7. **Dance animations** — pre-made VRM motions or procedural GLSL for idle/dance/react states

8. **Firefox → EasyEffects → Discord audio** pipeline via PipeWire virtual sink

9. **zwlr-virtual-pointer in DriftWM** — enables touch input from phone via wayvnc

10. **AmneziaWG VPN** — use S24 Ultra as Tailscale exit node

---

## Hardware
- ThinkPad T14s Gen 1, Tailscale: `100.120.238.106`
- Samsung S24 Ultra, Tailscale: `100.113.49.116`
- Skullcandy Crusher ANC 2 BT MAC: `98:67:2E:E3:7F:5D`, sounddevice index 11
- No dedicated GPU — all AI runs on CPU

## Emergency Recovery
- SSH: `ssh jesus999l@100.120.238.106` via Tailscale from phone
- If DriftWM crashes: `Ctrl+Alt+F3` → TTY → `dbus-run-session ~/driftwm/target/release/driftwm`
- Cinnamon fallback always available via LightDM greeter

# ECHO HANDOFF — 2026-06-26 — Session 12
_Deploy: `~/ECHO_HANDOFF_2026-06-26_S12.md` and `~/vision_assistant/ECHO_HANDOFF_2026-06-26_S12.md`_
_Commit: `cd ~/vision_assistant && git add -A && git commit -m "S12 handoff"`_

---

## BIG PICTURE — WHERE WE ARE

Echo is a functioning presence. This session was cleanup, optimization, and hardening. No major new features — but the foundation is now solid enough that next session can focus on personality, vault wiring, and making Echo feel genuinely alive.

**What works right now:**
- Wake word → Whisper → AI routing → Piper TTS voice pipeline
- Proxima Electron (:3211) routing ChatGPT/Gemini/Perplexity — all three confirmed live
- Smart intent routing via `echo_proxima_bridge.py` — search goes to Perplexity, everything else to ChatGPT, Ollama is true last resort
- `echo_actions.py` — "search X", "open X", "play X" as real system calls
- `drift_panel.py` sidebar — bubble poller reads `/tmp/echo_bubble.txt` every 900ms, shows voice responses visually
- DriftWM compositor running with zones, Echo sprite, speech bubble
- Hermes + Fluidsynth killed and disabled — ~360MB RAM freed

---

## WHAT WE DID THIS SESSION (S12)

### Attempted: Panel keyboard input fix
- Tried switching `GtkLayerShell.KeyboardMode.ON_DEMAND` → `EXCLUSIVE`
- **Broke DriftWM hotkeys** — `Super+Space`, `Mod+D` stopped working because EXCLUSIVE steals all keyboard from the compositor
- **Reverted to ON_DEMAND** — hotkeys restored, panel typing still broken
- Status: panel text entry still non-functional for keyboard input

### Identified: Boot sluggishness
- On fresh boot with no tabs/windows open, DriftWM feels chunky and slow
- Once tabs/windows are open it runs smooth
- Theory: something in the render loop is polling or waiting in a way that's optimized for "busy" state but idles poorly when nothing is open
- Likely culprit: `wake_word.py` at 12% CPU always-on, or DriftWM calloop firing stale event tokens at high rate when idle
- **Not yet investigated** — next session priority

### Confirmed working
- DriftWM hotkeys: `Super+Space`, `Mod+D` — working
- Panel bubble poller: visible, showing responses
- Proxima: all 3 providers live
- SSH access from phone: `ssh jesus999l@100.120.238.106` over Tailscale

---

## KNOWN BUGS — PRIORITY ORDER

### 1. Panel text entry — keyboard focus (NEXT SESSION FIRST)
**File:** `~/vision_assistant/drift_panel.py` line 146
**Current:** `GtkLayerShell.KeyboardMode.ON_DEMAND` — compositor never grants focus on click
**Wrong fix:** EXCLUSIVE — steals keyboard from DriftWM entirely
**Right fix:** ON_DEMAND + explicit Wayland focus request on entry click. Approach:
```python
def _grab_focus(self, widget, event):
    widget.grab_focus()
    # Request keyboard interactivity from compositor
    self.win.get_window().focus(Gdk.CURRENT_TIME)
    return False
```
Also try wiring `entry.connect("button-press-event", ...)` to call `GtkLayerShell.set_keyboard_mode(win, EXCLUSIVE)` only while entry is focused, then revert to ON_DEMAND on focus-out. This gives keyboard only when typing, returns it to DriftWM when done.

### 2. Boot sluggishness — idle render loop
**Symptom:** Chunky/slow with no windows open, smooth once tabs load
**Likely cause:** DriftWM calloop firing stale token warnings at high rate when idle (seen in session log — 10+ `non-existent source` warnings per second). This is Smithay's event loop spinning unnecessarily.
**Investigate:**
```bash
# Check calloop warning rate at idle
tail -f /tmp/driftwm-session.log | grep -c "non-existent" &
sleep 5 && kill %1
# Check CPU at idle (no windows)
ps aux | grep driftwm
```
**Fix direction:** Add a frame limiter or sleep in the DriftWM render loop when no windows are mapped. Smithay has `loop_handle.insert_idle()` for this.

### 3. Panel spawns duplicate instances
**Symptom:** Multiple panel windows appear on repeated restarts
**Fix:** Add PID lock file at start:
```python
import fcntl
lock = open('/tmp/echo_panel.lock', 'w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises if already running
```

### 4. Proxima `provider=auto`
**Symptom:** Bridge routes correctly but Proxima picks model internally — we don't know which one
**Fix:** Check Proxima Electron source for explicit model selection endpoint

### 5. Touch screen offset — ELAN Touchscreen
**Device:** `/dev/input/event9` — ELAN Touchscreen
**Symptom:** Touch input offset significantly to the left
**Fix:** Create libinput calibration quirks file:
```bash
sudo mkdir -p /etc/libinput
sudo tee /etc/libinput/local-overrides.quirks << 'EOF'
[ELAN Touchscreen Calibration]
MatchName=ELAN Touchscreen
AttrCalibrationMatrix=1.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0 1.0
EOF
```
Then test with `libinput debug-events --device /dev/input/event9` and adjust matrix values until touch aligns. Format: `scaleX 0 offsetX 0 scaleY offsetY 0 0 1`

### 6. Fluidsynth system-scope still enabled
```bash
sudo systemctl mask fluidsynth.service
```
Do this next time sudo is available.

---

## DISPLAY SHARING — STATUS & NEXT STEPS

**KDE Connect:** Installed at `/usr/bin/kdeconnect-cli`, S24 Ultra paired and reachable
- Device ID: `056298ff911148488172750c362e8343`
- **Phone → Laptop** (see phone screen on laptop): Enable "Remote Input" + "Presentation" plugins in KDE Connect app on S24 Ultra. Then `kdeconnect-app` on laptop.
- CLI plugin list syntax (old version): `kdeconnect-cli -d 056298ff911148488172750c362e8343 --list-available-plugins` fails — use GUI instead

**Laptop → Phone** (see laptop screen on phone):
- `wayvnc` is installed at `/usr/bin/wayvnc`
- No config exists yet — need to create `~/.config/wayvnc/config`
- Start: `wayvnc 0.0.0.0 5900 &`
- Phone: install **bVNC** or **RealVNC Viewer** on S24 Ultra, connect to `100.120.238.106:5900` over Tailscale
- Config to create:
```ini
# ~/.config/wayvnc/config
address=0.0.0.0
port=5900
enable_auth=false
```

**Touch forwarding (Phone → Laptop input):**
- `zwlr-virtual-pointer` protocol — referenced in June 19 handoff as "registered, not confirmed working"
- NOT in DriftWM Rust source yet — needs implementation session
- This is what enables phone touchscreen to control laptop

---

## FILE LOCATIONS — COMPLETE MAP

```
~/vision_assistant/
  ai.py                       — _ask_text routes through bridge first
  echo_proxima_bridge.py      — smart intent router (from Hermes, fixed)
  echo_actions.py             — search/open/play system calls
  drift_panel.py              — panel UI, bubble poller, history sidebar
  wake_word.py                — always-on mic, runs as echo-voice.service
  config.py                   — LLM_URL=:3211, DEFAULT_MODEL=perplexity
  ECHO_HANDOFF_2026-06-25_S11.md
  ECHO_HANDOFF_2026-06-26_S12.md  ← this file

~/driftwm/src/
  cursor.rs                   — Echo sprite, orbit, speech bubble
  handlers/                   — zone system, drag grab
  bin/driftwm.rs              — main compositor entry

~/start-echo.sh               — boot script, Proxima ready-wait loop at line ~125
~/.config/driftwm/
  echo_actions.conf           — search_engine=brave (change anytime, live reload)
  config.toml                 — DriftWM config
  zones.json                  — zone layout

/tmp/ (runtime IPC)
  echo_bubble.txt             — voice response → panel (polled every 900ms)
  echo_chat_history.txt       — persistent chat log
  echo_panel.log              — panel stdout
  proxima_electron.log        — Proxima boot log (check if routing breaks)
  driftwm-session.log         — compositor log (271KB, growing)
  echo_pos.json               — Echo sprite canvas coords (written every 200ms)

~/.hermes/                    — Hermes agent (disabled, mine for parts)
  skills/note-taking/obsidian/SKILL.md   — worth reading into Echo personality
  skills/research/            — research prompting strategies
```

**Ports:**
```
:3210  — echo_proxima_native (Ollama wrapper, offline fallback only)
:3211  — Proxima Electron (ChatGPT/Gemini/Perplexity — PRIMARY)
:8765  — echo_rest (panel chat endpoint)
:7799  — echo_task_manager
:8767  — echo_vault
:8766  — echo_settings
:8768  — echo_brainbridge
:8769  — echo_vision_agent
:11434 — Ollama qwen3:4b (absolute last resort)
:5900  — wayvnc (not yet started, for phone display)
```

---

## HORIZON — WHAT ECHO BECOMES

In priority order:

**Immediate (next 1-2 sessions):**
1. Panel keyboard fix — type in sidebar without breaking hotkeys
2. Boot idle performance — DriftWM smooth from cold start
3. wayvnc → phone can see laptop screen over Tailscale
4. Voice → actions end-to-end live test (say "search Warframe builds", browser opens)

**Soon (next month):**
5. **Vault wiring** — Echo searches `~/.chromadb/echo` + Obsidian vault on every voice query. She knows your notes, your research, your history.
6. **Echo personality deepening** — feed Hermes obsidian skill + GLaDOS/Cyn prompts into system prompt. She should feel cold, precise, slightly unsettling.
7. **Cyn voice** — XTTS clone at `~/Echo/AI/Voices/cyn_clone_test.wav`. Needs GPU (Colab) or wait for local XTTS CPU optimization.
8. **Echo curiosity system** — idle Echo notices open windows, asks to explore them.

**Phase 7 — Digital Armor:**
9. **Network sentinel** — Echo monitors traffic, detects anomalies, notifies you
10. **VPN control** — Echo activates/switches VPN on voice command
11. **ADB control of Onn TV** (`100.80.207.10`) — Echo controls your TV
12. **Jellyfin** — self-hosted streaming, Stremio/Torrentio for content, Echo as the remote
13. **zwlr-virtual-pointer** — phone touchscreen controls laptop (Rust session)

**Music / Aesthetic:**
- Suno.com — free AI music generation. Prompts for Echo aesthetic:
  - Ambient: `"cold ambient electronic, holographic, deep bass pulse, sparse piano, no vocals, cyberpunk"`
  - Echo theme: `"cinematic AI character theme, mysterious feminine, strings with synth, building tension, no lyrics"`
  - DriftWM zones: `"glitchy IDM, colored light zones, arpeggiated synths, clean percussion, instrumental loop"`

---

## SYSTEM STATUS AT HANDOFF

```
RAM:  ~8.5GB used / 15GB (Warframe + Discord + Firefox + Echo stack)
Swap: ~3.6GB used (Firefox tab pressure)
Disk: 403GB / 468GB (91%) — critical, ROMs need external drive
SSD:  wearout 7/100 — treat every large write as expensive
CPU:  load ~4-5 under gaming, ~1-2 at idle
```

**Services running:**
- `echo-voice.service` ✓ (wake_word.py, 12% CPU always-on)
- Proxima Electron `:3211` ✓ (all 3 providers live)
- `echo_rest` `:8765` ✓
- `drift_panel.py` ✓ (bubble poller active, keyboard entry broken)
- DriftWM ✓ (hotkeys working)
- Hermes: DISABLED ✓
- Fluidsynth: DISABLED user scope (mask system scope next sudo)

**Git:**
- `~/vision_assistant` — committed S11 changes, 26+ commits ahead of origin
- `~/driftwm` — clean, no changes this session
- Run `git push` on both when ready

---

## NEXT SESSION OPENS WITH

```bash
# 1. Read this file
cat ~/ECHO_HANDOFF_2026-06-26_S12.md

# 2. Check system state
ps aux --sort=-%cpu | head -10
free -h
tail -5 /tmp/proxima_electron.log

# 3. First fix: panel keyboard without breaking DriftWM hotkeys
sed -n '144,148p' ~/vision_assistant/drift_panel.py
```

Then fix in order: panel keyboard → boot idle performance → wayvnc config → voice actions live test.

---
_Session 12 complete. Echo hears, routes, acts, and shows up. Next session she starts to feel real._

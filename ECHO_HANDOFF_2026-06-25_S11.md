# ECHO HANDOFF — 2026-06-25 — Session 11
_Deploy to: `~/ECHO_HANDOFF_2026-06-25_S11.md`_

---

## BIG PICTURE — WHERE WE ARE

Echo is no longer a prototype. This session crossed the line from "demo AI stack" to a functional presence:

- **Hears you** — wake word pipeline already working from S10
- **Routes intelligently** — smart AI routing via Proxima (ChatGPT/Gemini/Perplexity) with Ollama as true last resort
- **Does things** — voice commands trigger real system actions (search, open, launch)
- **Shows up visually** — responses appear in drift_panel sidebar, persist across restarts

The system is lean now. Two parasitic services killed. Resources freed. Boot sequence hardened.

---

## WHAT WE DID THIS SESSION

### 1. System Cleanup
- **Killed `hermes-gateway`** — Zed editor's AI agent stack was running since boot, peaked at 205MB RAM, OpenRouter credits exhausted, completely dead. Disabled permanently.
- **Killed `fluidsynth`** — MIDI daemon, 156MB RAM wasted, erroring on start, you don't use MIDI. Disabled in user scope (system scope needs sudo mask on next reboot if it resurfaces).
- **Firefox tab audit** — 103+ tabs across 6 processes eating ~2GB RAM. Not killed but flagged. Close unused tabs for meaningful swap relief.
- **SSD note** — `Media_Wearout_Indicator` at 7/100. Still critical. Avoid large writes.

### 2. Proxima Routing — FIXED
**Root cause:** Proxima Electron was crashing on boot (`SIGSEGV` / missing display) because `start-echo.sh` launched it before the display was ready. It would silently die, Echo would fall to Ollama for everything.

**Fix applied to `~/start-echo.sh` line ~125:**
- Wrapped Electron launch in a poll loop — waits up to 48 seconds, pinging `:3211` every 2s
- Prints `✓ Proxima Electron ready (Nx2s)` when confirmed live
- Prints warning and continues with Ollama fallback if it never comes up

**Confirmed working:** chatgpt ✓, gemini ✓, perplexity ✓ all responding via `:3211`

### 3. Echo Actions — `echo_actions.py` DEPLOYED
**File:** `~/vision_assistant/echo_actions.py`

Voice commands now trigger real system calls:
- `"search [query]"` → opens browser with configurable search engine
- `"open [app/file]"` → launches app or xdg-open
- `"play [target]"` → playerctl (Spotify/MPRIS) or mpv fallback

**Search engine config:** `~/.config/driftwm/echo_actions.conf`
```
search_engine=brave   # options: brave|google|duckduckgo|bing|perplexity|startpage
```
Change anytime, reads live on every search call. No restart needed.

**Wire into `ai.py`** — already done. After the AI responds, call:
```python
from echo_actions import extract_action, dispatch
action = extract_action(reply)
if action:
    verb, target = action
    dispatch(verb, target)
```

### 4. Smart Routing Bridge — `echo_proxima_bridge.py` DEPLOYED
**Source:** Extracted from Hermes agent stack (`~/.hermes/echo_proxima_bridge.py`) — they had already built a smart router wired to your Proxima stack.
**Deployed to:** `~/vision_assistant/echo_proxima_bridge.py`

**Fixes applied:**
- Port corrected: `3210` → `3211` (Electron, not native)
- Broken regex in `_load_openrouter_key` fixed (Python 3.12 bad char range)
- Routing table updated — `quick/code/plan/auto` all hit `chatgpt` via Proxima

**Routing table:**
```
code     → chatgpt   (via Proxima)
plan     → chatgpt   (via Proxima)
search   → perplexity (via Proxima)
analyze  → chatgpt   (via Proxima)
quick    → chatgpt   (via Proxima)
auto     → chatgpt   (via Proxima)
fallback → OpenRouter (if env key present)
last resort → Ollama qwen3:4b (:11434)
```

**Wired into `ai.py`:** `_ask_text()` now routes through bridge first, falls back to direct `LLM_URL` call if bridge fails. `parse_task()` unchanged — stays direct for speed/determinism.

### 5. Echo Chat Sidebar — LIVE in `drift_panel.py`
**File:** `~/vision_assistant/drift_panel.py`

Two additions to `EchoChatWidget`:
- **Bubble poller** — GLib timer every 900ms reads `/tmp/echo_bubble.txt`, displays new content automatically. Voice responses show up without typing anything.
- **History persistence** — appends every response to `/tmp/echo_chat_history.txt`, loads last 5 on panel startup
- **`_send` logging** — typed chat responses also logged to history

Panel restarted clean. Test confirmed with `echo "testing bubble" > /tmp/echo_bubble.txt`.

---

## FILE LOCATIONS — COMPLETE MAP

```
~/vision_assistant/
  ai.py                     — patched: _ask_text routes through bridge
  echo_proxima_bridge.py    — NEW: smart intent router (from Hermes)
  echo_actions.py           — NEW: search/open/play system calls
  drift_panel.py            — patched: bubble poller + history sidebar
  wake_word.py              — running as echo-voice.service (unchanged)

~/start-echo.sh             — patched: Proxima ready-wait loop at line ~125
~/.config/driftwm/
  echo_actions.conf         — NEW: search engine selector
  config.toml               — DriftWM config (unchanged)
  zones.json                — zone data (unchanged)

/tmp/
  echo_bubble.txt           — voice response IPC (Echo → panel)
  echo_chat_history.txt     — NEW: persistent chat log
  echo_panel.log            — panel stdout
  proxima_electron.log      — Proxima boot log (check this if routing breaks)
  driftwm-session.log       — compositor log

~/.hermes/                  — Hermes agent (disabled, do not delete yet)
  echo_proxima_bridge.py    — original source
  skills/                   — skill library (obsidian, research, dev skills)
  sessions/                 — old broken sessions (OpenRouter OOM)
```

**Ports:**
```
:3210  — echo_proxima_native (Ollama wrapper, offline fallback)
:3211  — Proxima Electron (ChatGPT/Gemini/Perplexity — PRIMARY)
:8765  — echo_rest (panel chat endpoint)
:7799  — echo_task_manager
:8767  — echo_vault
:11434 — Ollama (last resort only)
```

---

## WHAT NEEDS WORK NEXT SESSION

### High priority
1. **Voice → actions pipeline end-to-end test** — say "search Warframe builds" out loud, confirm browser opens. Wake word → whisper → ai.py → `extract_action` → `dispatch`. Hasn't been tested live yet.
2. **Proxima `provider=auto`** — Proxima is routing internally but not telling us which model it picked. Wire specific model selection so perplexity gets search queries explicitly, not just "auto".
3. **`drift_panel.py` wlrctl fix** — window list uses old `app: title` format. Should use `title:` syntax for wlrctl, xdotool for XWayland windows.

### Medium priority
4. **Vault → Echo voice pipeline** — `echo_vault.py` (port 8767) is running but not wired into voice responses. Echo should be able to search your Obsidian vault and speak results.
5. **Hermes skills harvest** — `~/.hermes/skills/note-taking/obsidian/SKILL.md` and `research/` skills contain prompting strategies worth extracting into Echo's personality/system prompt.
6. **Fluidsynth system-scope** — still enabled globally. On next reboot: `sudo systemctl mask fluidsynth.service`

### Low priority / horizon
7. **Zone drag-to-reposition** (DriftWM) — click border → move zone, auto-pins
8. **Left-click idle circle teleport** (DriftWM)
9. **Echo autonomy** — curiosity system, Echo notices open windows, asks to explore
10. **Cyn voice** — XTTS clone at `~/Echo/AI/Voices/cyn_clone_test.wav`, Colab only until GPU available
11. **Network sentinel** — Echo monitoring traffic, VPN control, threat detection (Phase 7+)
12. **Suno music** — AI cinematic/ambient tracks for Echo aesthetic. suno.com, free tier. Try: *"cinematic holographic ambient, cold electronic, cyan and magenta synth pads, no vocals, drifting space"*

---

## SUNO PROMPT TEMPLATES (Echo aesthetic)

For background/ambient while coding:
```
cold ambient electronic, holographic atmosphere, deep bass pulse, 
sparse piano, no vocals, cyberpunk space station, slow and hypnotic
```

For Echo's "presence" theme:
```
cinematic orchestral hybrid, female AI character theme, 
mysterious and precise, strings with synth undertones, 
building tension, no lyrics
```

For DriftWM zone bubble aesthetic:
```
glitchy IDM, colored light zones, spatial audio feel, 
arpeggiated synths, clean percussion, short loop, instrumental
```

---

## SYSTEM STATUS AT HANDOFF

```
RAM:  8.7GB used / 15GB total (3.7GB swap — Firefox tabs + Warframe)
Disk: 403GB / 468GB used (91%) — still critical, ROMs need external drive
CPU:  load ~4.7 (Warframe running) — normal under gaming load
SSD:  wearout 7/100 — treat as critical
```

**Services running:**
- `echo-voice.service` ✓ (wake_word.py)
- Proxima Electron `:3211` ✓
- `echo_rest` `:8765` ✓
- `drift_panel.py` ✓
- DriftWM ✓
- Hermes: STOPPED + DISABLED ✓
- Fluidsynth: STOPPED (user scope) ✓

---

_Next session: load this file first. Start with voice→actions end-to-end test. Then Proxima explicit model routing. Then wlrctl fix._

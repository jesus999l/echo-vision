# Echo + DriftWM — Session Handoff 2
**Date:** 2026-06-08  
**Repo:** https://github.com/jesus999l/echo-vision (latest: d6f84f0)  
**Machine:** ThinkPad T14s Gen 1, i7-10610U, 16GB RAM, CPU-only, Linux Mint 22.3  
**Disk:** 98% full (13GB free) — ROMs cleanup is urgent

---

## What Was Accomplished This Session

### 1. Echo Sprite Fixed
- Wings now draw AFTER body (dist >= 20.0 guard) — eye always on top
- Sprite upgraded to 96x96: perspective ellipse halo, symmetric wings with fade gradient, large eye, iris pulse, glint highlight
- Orbit radius: 76px, velocity-driven angle (Echo trails behind cursor)
- LERP: 0.08, ANGLE_LERP: 0.06

### 2. GTK Shadow Cursor Killed
- `echo_shadow_cursor.py` removed from DriftWM autostart
- Rust compositor handles all Echo rendering
- `echo_shadow_launch.sh` also removed from autostart

### 3. Session Save/Restore
- `~/vision_assistant/echo_session.py` — save/restore/speak/daemon
- Auto-saves every 30s via daemon, auto-restores on compositor crash
- Keybindings: `mod+F9` = save, `mod+F10` = restore
- Session daemon in DriftWM autostart
- Restore passes `os.environ.copy()` so apps get correct WAYLAND_DISPLAY
- App map: firefox, gnome-terminal-server, discord, cursor, obsidian, steam, thunar

### 4. Speech Bubble (Compositor-Level)
- Rust reads `/tmp/echo_bubble.txt` every frame
- 280x36 dark panel, amber top border, monospace 13px white text
- Renders above Echo using `driftwm::text::fit_text` + `rasterize_into`
- Auto-clears via `bash -c 'sleep 5 && echo -n > /tmp/echo_bubble.txt'`

### 5. Echo Personality in ai.py
- `ECHO_PERSONALITY` constant injected after imports
- GLaDOS (dry wit, clinical, sarcastic) + Cyn (childlike, attached, stilted)
- Short sentences, lowercase, narrates actions, never sycophantic
- Prepended to `build_system_prompt()` return value
- `set_obsidian_bridge` and `set_web_searcher` stubs injected (fix startup errors)

### 6. Wake Word Pipeline Fixed
- Mic: PipeWire device (index 11) overrides pulse — correct BT headphone routing
- VAD: aggressiveness 1 (was 2), silence cutoff 400ms (was 160ms), onset 5s (was 3s)
- AI routing: `_stream_voice_response` now hits Proxima `:3210` with model `perplexity`
- `speak()` in wake_word.py writes to `/tmp/echo_bubble.txt` + clears after 6s
- `speak_stream()` in voice.py writes each sentence to bubble as it streams
- Wake word detects "hey echo" correctly via Vosk
- Command recording works but double Whisper load race condition still present

### 7. Piper TTS Installed
- Binary at `~/piper/piper`
- Model attempted: `en_US-amy-medium` — JSON config download failed (HuggingFace blocked)
- Fallback: espeak-ng with params `-v en-us+f3 -s 135 -p 50 -a 180` (decent but robotic)
- Best tested params: `-v en-us+f2 -s 128 -p 60 -a 180`
- Target voice: GLaDOS/Cyn blend — cold, measured, feminine, slightly unsettling

---

## Current DriftWM Autostart
```toml
autostart = [
    "/home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/echo_session.py daemon",
    "/home/jesus999l/vision_env/bin/python3 /home/jesus999l/vision_assistant/drift_panel.py",
    "xbindkeys",
    "xdg-desktop-portal-wlr",
    "waybar",
]
```

---

## Key Files Changed This Session
| File | Change |
|---|---|
| `~/driftwm/src/render/cursor.rs` | Wing z-order fix, speech bubble render |
| `~/driftwm/src/state/cursor.rs` | echo_angle, cursor_prev_x/y added |
| `~/vision_assistant/echo_session.py` | env fix, bubble clear via bash subprocess |
| `~/vision_assistant/wake_word.py` | PipeWire mic override, VAD tuning, Proxima routing, bubble write |
| `~/vision_assistant/voice.py` | speak_stream writes to bubble |
| `~/vision_assistant/ai.py` | ECHO_PERSONALITY, set_obsidian_bridge/set_web_searcher stubs |
| `~/.config/driftwm/config.toml` | Session daemon autostart, mod+F9/F10 |

---

## Remaining Issues / Next Session

### HIGH
| Issue | Notes |
|---|---|
| Piper voice model JSON missing | HuggingFace blocked, need raw.githubusercontent.com path or manual download |
| Double Whisper load race condition | Two `[wake] Loading faster-whisper` messages — command sometimes gets empty transcription |
| Wake word command empty transcription | Intermittent — VAD tuning helped but not solved |
| Disk at 98% | Move ROMs (~/Documents/Games ~16GB) to external /media/jesus999l/writable |
| Proxima ChatGPT/Gemini cookies stale | Log into ChatGPT and Google in Firefox to refresh |
| Session restore visual test | Apps launch but need fresh reboot test to confirm windows appear |

### MED  
| Issue | Notes |
|---|---|
| Echo autonomous mode | Echo roams freely doing tasks, not always following mouse — noted for future |
| Echo voice final tuning | Piper amy-medium is target, then pitch/speed post-process for GLaDOS/Cyn blend |
| Wake word → full response loop | Pipeline flows but response unreliable due to Whisper race + Proxima routing |
| 698 Subconscious/ vault files | Distillation pending |
| Hermes Discord 30min lag | OpenRouter key fix |

### LOW
| Issue | Notes |
|---|---|
| Echo transparency when text underneath | Echo fades when hovering over text |
| Echo startup snap | First frame snaps before lerp — add init delay |
| .gitignore | Add chroma_db/, *.bak |

---

## Next Session Priority Order
1. **Disk cleanup** — move ROMs to external, get below 90%
2. **Piper voice** — fix JSON, test amy-medium, tune for GLaDOS/Cyn
3. **Fix Whisper double-load** — add `_PROCESSING_LOCK` guard in `run_detector`
4. **Refresh Proxima cookies** — log into ChatGPT + Google in Firefox
5. **Full wake word test** — "hey echo" → response → bubble → TTS end to end
6. **Vault distillation** — 698 Subconscious/ files
7. **Echo autonomous mode** — planning phase

---

## Echo Voice Target
- Engine: Piper `en_US-amy-medium.onnx`
- JSON: `https://raw.githubusercontent.com/rhasspy/piper-voices/master/en/en_US/amy/medium/en_US-amy-medium.onnx.json`
- Post-process with sox for GLaDOS effect: `sox input.wav output.wav pitch -200 reverb 20`
- Fallback espeak params: `-v en-us+f2 -s 128 -p 60 -a 180`

## Echo Phase Roadmap
| Phase | Goal | Status |
|---|---|---|
| 1 | Ghost cursor overlay, animated, socket controlled | ✅ DONE |
| 2 | Vision assisted guidance | ✅ WIRED |
| 3 | Multi-step navigation | PENDING |
| 4 | Workflow learning / autonomous mode | PLANNED |
| 5 | Compositor-level rendering | ✅ DONE |
| 6 | Speech bubble + TTS voice | ✅ DONE (Piper pending) |
| 7 | Wake word → full voice loop | 🔧 IN PROGRESS |
| 8 | Session awareness + auto-restore | ✅ DONE |
| 9 | Echo autonomous roaming | PLANNED |

---

## Rules
1. Commands in fenced blocks only
2. `~/vision_env/bin/python3` always
3. Proxima `:3210` — never `:3211`
4. ALWAYS validate TOML before driftwm switch
5. `sudo rm` old driftwm binary before `sudo cp`
6. Disk at 98% — no large downloads without cleanup first
7. `mod+F9` = save session, `mod+F10` = restore
8. Wake word model: perplexity via Proxima
9. Piper binary: `~/piper/piper`, models: `~/piper/models/`
10. BT mic = PipeWire device index 11

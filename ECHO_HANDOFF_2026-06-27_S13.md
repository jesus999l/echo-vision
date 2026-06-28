# ECHO HANDOFF — 2026-06-27 — Session 13
_Deploy: `~/ECHO_HANDOFF_2026-06-27_S13.md` and `~/vision_assistant/ECHO_HANDOFF_2026-06-27_S13.md`_
_Commit: `cd ~/vision_assistant && git add -A && git commit -m "S13 handoff"`_

---

## OPEN WITH THESE COMMANDS

```bash
cat ~/ECHO_HANDOFF_2026-06-27_S13.md
free -h
tail -5 /tmp/proxima_electron.log
kdeconnect-cli --list-devices
flatpak list | grep -i sober
```

---

## WHAT'S WORKING

- DriftWM compositor ✓ — hotkeys, zones, Echo sprite, speech bubble
- Proxima Electron :3211 ✓ — ChatGPT/Gemini/Perplexity all live
- Smart routing bridge ✓ — `echo_proxima_bridge.py` intent-based routing
- `echo_actions.py` ✓ — search/open/play as real system calls
- `drift_panel.py` ✓ — bubble poller reads `/tmp/echo_bubble.txt`, shows responses
- Wake word → Whisper → TTS pipeline ✓
- KDE Connect ✓ — S24 Ultra paired and reachable at `100.113.49.116`
- Sober (Roblox) installed — v1.7.0, needs update

---

## SESSION 13 — DO THESE IN ORDER

### 1. Update Sober (2 minutes)
```bash
flatpak update org.vinegarhq.Sober -y
flatpak run org.vinegarhq.Sober
```
Confirm it launches and logs in. Done.

### 2. Fix Update Manager not showing in DriftWM
**What's happening:** `mintUpdate` runs (PID shows up) but DriftWM never maps its window. GTK scale factor errors on launch. XWayland window not being surfaced by the compositor.

**Diagnose first:**
```bash
DISPLAY=:0 xdotool search --name "Update Manager" 2>/dev/null
wlrctl toplevel list 2>/dev/null
DISPLAY=:0 mintupdate &
sleep 3 && DISPLAY=:0 xdotool search --class "mintUpdate" getwindowgeometry 2>/dev/null
```

**Likely fix:** DriftWM needs to handle XWayland window activation requests. Check `~/driftwm/src/handlers/` for XWayland surface mapping. The window exists but never receives `map` signal in Smithay.

**Quick workaround if Rust fix takes too long:**
```bash
# Force XWayland window to front after mintupdate launches
DISPLAY=:0 mintupdate & sleep 2 && DISPLAY=:0 xdotool search --name "Update Manager" windowraise windowfocus
```
Add this as an alias or Echo action.

### 3. Phone display on laptop (KDE Connect)
**Status:** Phone paired, reachable. KDE Connect GUI opened (`kdeconnect-app`).

**On S24 Ultra:** Open KDE Connect app → tap ThinkPad → enable these plugins:
- Remote Input
- Slideshow / Presentation  
- Share
- Multimedia Control

**On laptop after enabling plugins:**
```bash
kdeconnect-app &
# Click S24 Ultra in device list → look for "Remote Input" panel
```

**If KDE Connect screen share doesn't work** (it's limited on Wayland):
Install scrcpy for proper phone→laptop mirroring:
```bash
flatpak install flathub in.srev.guiscrcpy -y
# OR
sudo apt install scrcpy -y
# Then:
adb connect 100.113.49.116:5555
scrcpy --tcpip=100.113.49.116
```
Note: scrcpy over Tailscale needs ADB TCP enabled on phone (Developer Options → Wireless debugging).

### 4. Laptop display on phone (wayvnc)
```bash
mkdir -p ~/.config/wayvnc
cat > ~/.config/wayvnc/config << 'EOF'
address=0.0.0.0
port=5900
enable_auth=false
EOF
wayvnc &
sleep 2 && echo "wayvnc started — connect from phone"
```
On S24 Ultra: install **bVNC Free** or **RealVNC Viewer** → connect to `100.120.238.106:5900`.

### 5. Panel keyboard input fix (proper approach)
**File:** `~/vision_assistant/drift_panel.py` line 146
**Do NOT use EXCLUSIVE** — breaks DriftWM hotkeys.

**Right approach:** Toggle EXCLUSIVE only while entry is focused:
```python
# In EchoChatWidget.__init__, replace the entry focus handlers:
self.entry.connect("focus-in-event", self._keyboard_grab)
self.entry.connect("focus-out-event", self._keyboard_release)

def _keyboard_grab(self, widget, event):
    from gi.repository import GtkLayerShell
    GtkLayerShell.set_keyboard_mode(
        self.get_toplevel(), GtkLayerShell.KeyboardMode.EXCLUSIVE
    )
    return False

def _keyboard_release(self, widget, event):
    from gi.repository import GtkLayerShell
    GtkLayerShell.set_keyboard_mode(
        self.get_toplevel(), GtkLayerShell.KeyboardMode.ON_DEMAND
    )
    return False
```
This borrows keyboard only while typing, returns it to DriftWM immediately on focus-out.

### 6. Boot idle sluggishness
**Symptom:** Slow/chunky on fresh boot until windows open, then smooth.
**Investigate:**
```bash
# At idle (no windows open), check calloop warning rate
tail -f /tmp/driftwm-session.log | grep "non-existent" | head -20
# Check DriftWM CPU at idle
watch -n 1 'ps aux | grep driftwm | grep -v grep'
```
**Likely fix:** Frame limiter in DriftWM render loop. When no windows are mapped, Smithay's calloop fires stale token warnings at ~10/sec, spinning the CPU. Add idle sleep:
```rust
// In the main event loop, after processing events:
if self.space.elements().count() == 0 {
    std::thread::sleep(std::time::Duration::from_millis(16));
}
```

---

## BUGS BACKLOG

| Priority | Bug | File | Notes |
|----------|-----|------|-------|
| HIGH | Panel text entry no keyboard | `drift_panel.py:146` | Use focus-in/out toggle, not EXCLUSIVE |
| HIGH | Update Manager not mapping in DriftWM | `driftwm/src/` | XWayland window never surfaces |
| MED | Boot idle sluggishness | `driftwm/src/` | Calloop spinning at idle |
| MED | Panel duplicate instances | `drift_panel.py` | Add PID lock file |
| MED | Touch screen offset left | `/etc/libinput/` | libinput CalibrationMatrix quirk |
| LOW | Fluidsynth system-scope | systemd | `sudo systemctl mask fluidsynth.service` |
| LOW | Proxima provider=auto | `echo_proxima_bridge.py` | Explicit model selection |

---

## HORIZON FEATURES

**Near term:**
- Vault wiring — Echo searches Obsidian + ChromaDB on every voice query
- Echo personality deepening — GLaDOS/Cyn tone, ECHO_PERSONALITY in system prompt
- Cyn voice — XTTS clone at `~/Echo/AI/Voices/cyn_clone_test.wav` (needs Colab/GPU)
- Voice → actions end-to-end live test

**Phase 7 — Digital Armor:**
- Network sentinel — traffic monitoring, anomaly detection, notifications
- VPN control via voice
- ADB control of Onn TV (`100.80.207.10`)
- Jellyfin self-hosted streaming
- zwlr-virtual-pointer — phone touch controls laptop (Rust)

---

## FILE MAP

```
~/vision_assistant/
  ai.py                      — _ask_text routes through bridge
  echo_proxima_bridge.py     — smart intent router, port :3211
  echo_actions.py            — search/open/play system calls
  drift_panel.py             — panel UI, bubble poller, keyboard broken
  wake_word.py               — always-on mic, echo-voice.service

~/driftwm/src/
  cursor.rs                  — Echo sprite orbit + speech bubble
  handlers/                  — zones, XWayland, input

~/start-echo.sh              — Proxima ready-wait loop at line ~125
~/.config/driftwm/
  echo_actions.conf          — search_engine=brave
  config.toml                — DriftWM keybindings
~/.config/wayvnc/config      — CREATE THIS (see step 4 above)

/tmp/
  echo_bubble.txt            — voice → panel IPC
  echo_chat_history.txt      — chat log
  proxima_electron.log       — check if Proxima dies
  driftwm-session.log        — compositor log
```

**Ports:**
```
:3211  Proxima Electron — PRIMARY AI
:3210  echo_proxima_native — offline fallback
:8765  echo_rest
:7799  echo_task_manager
:8767  echo_vault
:11434 Ollama — last resort
:5900  wayvnc — laptop display (not yet started)
```

---

## SYSTEM STATE AT HANDOFF
```
Disk:  403/468GB (91%) — critical
SSD:   7/100 wearout — treat writes as expensive
RAM:   ~8.5GB / 15GB
Swap:  ~3.6GB
Git:   26+ commits ahead of origin on vision_assistant
       run: cd ~/vision_assistant && git push
```

---
_Next session: Sober update → Update Manager fix → phone display → panel keyboard fix._

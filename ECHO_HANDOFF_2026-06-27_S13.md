# ECHO HANDOFF — 2026-06-27 — Session 13

## WHAT WE DID

### screencopy unwrap fix (DONE)
- `~/driftwm/src/protocols/screencopy.rs` lines 268, 425
- Replaced `get_mut(manager).unwrap()` with `let Some(queue) = ... else { return; }`
- Built and deployed — DriftWM no longer panics on wayvnc disconnect
- Committed to driftwm repo

### panel EchoChatWidget win reference (DONE)
- `EchoChatWidget.__init__` now accepts `win=None` and stores `self.win`
- Line 209: `EchoChatWidget(win=self.win)` passes the window reference down
- `_grab_focus` and `_release_focus` are clean — no EXCLUSIVE calls remain
- Panel loads without crashing now

### start-echo.sh cleanup (DONE)
- Hermes gateway removed from boot
- wayvnc added to boot: `wayvnc --disable-input -f 15 0.0.0.0 5900`
- UFW rule added: port 5900/tcp open

### fluidsynth masked (DONE)
- `sudo systemctl mask fluidsynth.service`

### wayvnc + AVNC (PARTIAL)
- AVNC connects, shows DriftWM screen for ~1 second then drops
- Root cause: DriftWM runs in winit/nested mode — EGL BAD_SURFACE spam
- screencopy over nested backend is fundamentally unstable
- wayvnc will only work reliably on KMS/udev backend (real hardware mode)
- Fix: S14 needs to enable and test KMS backend boot from TTY

### KDE Connect touchpad (BROKEN)
- Phone shows "device no longer reachable"
- Cause: AppGuard DNS / private proxy on S24 Ultra blocking KDE Connect ports
- Fix: disable AppGuard temporarily to test, then whitelist KDE Connect ports

---

## KNOWN BUGS — PRIORITY ORDER

### 1. wayvnc stable screen share → needs KMS backend
- DriftWM must boot from TTY on KMS/udev backend (not nested winit)
- Test: `Ctrl+Alt+F3` → `dbus-run-session /usr/local/bin/driftwm`
- Then wayvnc runs against real DRM output, screencopy works properly
- Risk: KMS backend untested — have SSH fallback ready

### 2. Panel keyboard entry still broken
- Panel loads clean now but keyboard focus still doesn't work on click
- ON_DEMAND mode means compositor never grants focus
- Real fix needs DriftWM-side keyboard focus grant for layer shell surfaces
- Rust session needed

### 3. PTT Super+Ctrl+Space not working
- Proxima wasn't running at time of complaint — may be fixed now Proxima is up
- Test: say wake word or press Super+Ctrl+Space, check `/tmp/echo_bubble.txt`
- If still broken: check `pgrep -f wake_word` and `ss -tlnp | grep 3211`

### 4. KDE Connect touchpad
- Disable AppGuard/proxy on phone temporarily and test Remote Input
- If it works, whitelist ports 1714-1764 TCP/UDP in AppGuard

### 5. zones.json reload spam
- Log shows rapid `zones.json reloaded` every 150ms when panel starts
- File watcher is too aggressive — add debounce or inotify cooldown

---

## SYSTEM STATUS AT HANDOFF

**Services:**
- DriftWM ✓
- Proxima Electron :3211 ✓
- echo_proxima_native :3210 ✓
- echo_rest :8765 ✓
- wake_word.service ✓ (~13% CPU)
- drift_panel ✓ (running, keyboard broken)
- wayvnc :5900 — in start-echo.sh but unstable on winit backend
- KDE Connect daemon ✓ (phone unreachable due to AppGuard)

**Git:**
- `~/vision_assistant` — committed S13 changes
- `~/driftwm` — committed screencopy unwrap fix

---

## NEXT SESSION OPENS WITH

```bash
cat ~/vision_assistant/ECHO_HANDOFF_2026-06-27_S13.md
ps aux --sort=-%cpu | head -10
free -h
ss -tlnp | grep -E "3211|8765|5900"
echo "PTT test:" && cat /tmp/echo_bubble.txt
```

Then in order:
1. Test PTT — press Super+Ctrl+Space, check if Proxima routes it
2. KDE Connect — disable AppGuard on phone, test Remote Input
3. KMS backend test from TTY — biggest win for wayvnc stability
4. zones.json debounce fix

---

## HORIZON

- KMS backend → wayvnc stable → phone sees laptop → USB-C HDMI to any TV
- zwlr-virtual-pointer → phone touch controls laptop cursor
- Vault distillation — 698 raw Obsidian files pending
- Cyn voice XTTS (needs GPU/Colab)
- Echo curiosity system — idle Echo notices open windows
- Network sentinel, VPN control, ADB TV control, Jellyfin

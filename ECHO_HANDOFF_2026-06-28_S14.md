# ECHO HANDOFF — 2026-06-28 — Session 14

## OPEN WITH THESE COMMANDS
cat ~/ECHO_HANDOFF_2026-06-28_S14.md
ss -tlnp | grep -E "5900|3211|8765"
adb devices


## WHAT'S WORKING
- wayvnc :5900 — laptop→phone display ✓ (bVNC/RealVNC on S24)
- scrcpy v4.0 — phone→laptop display + touch control ✓
- ADB over Tailscale — 100.113.49.116:42161 ✓
- polkit-mate auth agent — added to start-echo.sh ✓
- apt updates — all 39 packages cleared ✓
- All above added to start-echo.sh for boot persistence

## UNCONFIRMED
- Update Manager install button — polkit agent added but no updates available to test
  Suspected fix: polkit-mate-authentication-agent-1 was missing, now in start-echo.sh
- bVNC touch input — zwlr-virtual-pointer is registered in DriftWM but untested

## KNOWN ISSUES
- ADB port 42161 may change on phone reboot (wireless debugging assigns random port)
  Fix: after reboot, re-pair via Developer Options → Wireless Debugging → connection port
- scrcpy launched manually; not in start-echo.sh (it opens a window, user should launch)
- wayvnc killed DriftWM session when pkill was used — always use: pkill wayvnc (safe now, disowned)

## BUGS BACKLOG (unchanged from S13)
- drift_panel.py keyboard grab — focus-in/out toggle not yet implemented
- DriftWM idle sluggishness — calloop spinning, frame limiter not added
- Touch screen offset left — libinput CalibrationMatrix quirk

## PORTS
:3211  Proxima Electron
:3210  echo_proxima_native  
:8765  echo_rest
:5900  wayvnc (auto-started)
:42161 ADB S24 Ultra (may change on reboot)

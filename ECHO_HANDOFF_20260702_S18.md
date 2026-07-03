# ECHO HANDOFF — 2026-07-02 — Session S18

Continuation of S17-FINAL. This session: Echo Command Center (backend + frontend v1),
scan_and_play.py root-cause diagnosis, SmartTube fix, minor cleanup.

---

## ECHO COMMAND CENTER (renamed from "Vision Assistant v2")

### Status: backend complete + verified, frontend v1 built, NOT yet deployed/tested on device

**Split of work going forward:**
- Claude → frontend only, contract-locked to 4 endpoints below
- ChatGPT → backend, instrumentation, `ai.py`/task routing/memory

**Backend — `~/vision_assistant/echo_dashboard_api.py`**
Runs standalone on `:8766`. Verified working end-to-end this session:
```
GET  /api/metrics    — real psutil (cpu/ram/disk/net/battery/temp)
GET  /api/services   — heartbeat-based, reads /tmp/echo_events.jsonl
                        schema: {"type":"pong","source":"<name>","timestamp":<float>}
GET  /api/pipeline    — coarse idle/thinking state, real service booleans
POST /api/chat        — calls ai.chat() directly, real pipeline, no reimplementation
GET  /api/health
```
Confirmed via curl: `/api/chat` returns real replies (12s latency on trivial prompt —
**flagged as a problem, not yet fixed** — likely Ollama/Proxima routing overhead,
not measured per-stage yet).

Known deploy footgun (hit twice this session): browser saves duplicate downloads as
`file(1).py`, `file(2).py` — always verify with `diff` against what's already in
`~/vision_assistant/` before copying, don't trust filename/timestamp alone.

**Frontend — `echo_command_center.html`**
Single-file HTML/CSS/JS, no build step, polls the 4 endpoints above every 2s.
Delivered but **not yet opened/tested on the ThinkPad**. Deploy:
```bash
cp ~/Downloads/echo_command_center.html ~/vision_assistant/
```
Open in Firefox: `file:///home/jesus999l/vision_assistant/echo_command_center.html`
**Watch for:** mixed-content blocking (https artifact page fetching http://localhost —
should work since localhost is a secure-context exception, but unverified on real
Firefox/Mint). If gauges don't populate, check F12 console for fetch errors first.

Design: dark void/cyan/magenta palette (GLaDOS precision / Cyn chaos), JetBrains Mono,
signature element is a canvas oscilloscope trace for the AI pipeline — flatlines cyan
at idle, spikes magenta when `/api/pipeline` reports `state: thinking`.

### Next priorities (in order)
1. **Deploy + test frontend on device** — first real render, fix whatever breaks
2. **Instrument `/api/chat` latency by stage** (context build / memory / Proxima-Ollama /
   parse) — 12s is too slow to ship as "responsive," need to know where it's going
   before optimizing blind. ChatGPT's proposed `timing: {}` response field is the
   right shape; not yet implemented.
3. Richer `/api/services` fields (pid, cpu%, ram, uptime) — ChatGPT backend work,
   frontend already tolerant of missing fields (progressive enhancement)
4. `/api/task`, `/api/history`, `/api/models` — not started

---

## scan_and_play.py — ROOT CAUSE FOUND, NOT YET FIXED

**Bug is NOT in the scanner.** Proven empirically this session, not guessed:
- Drive has exactly 765 `.mp4` + 755 `.mkv` = **1520** files, zero `.avi`/`.m4v`/`.mov`/`.webm`
- Script's extension whitelist already covers 100% of real files
- `"sample"` filter: zero false-positive risk (confirmed via `find -iname "*sample*"` → empty)
- `os.walk()` is recursive — nested season folders scan fine, no fix needed there
- Reproduced the scan logic standalone: **SCAN COUNT: 1520** — exact match to real file count

**Real suspect: VLC itself**, not the Python indexer.
`~/scan_and_play.py` line ~68 does:
```python
subprocess.run(["vlc"] + playlist, env=env)
```
This passes up to 1520 individual CLI arguments to VLC in one spawn. Suspected causes
of "some movies appear, some don't": ARG_MAX/argv parsing limits, VLC playlist UI
truncating or mishandling registration at this scale. **Not yet confirmed** — this is
the leading hypothesis based on how VLC is being invoked, not a proven root cause the
way the scanner completeness was proven.

### Fix to try next session
Switch from CLI-argument injection to a `.m3u` playlist file:
```bash
python3 -c "
import os
MEDIA_EXT = ('.mp4', '.mkv', '.avi', '.webm')
files = []
for d,_,fs in os.walk('/media/jesus999l/BE95-C353'):
    for f in fs:
        if f.lower().endswith(MEDIA_EXT) and 'sample' not in f.lower():
            files.append(os.path.join(d,f))
print(chr(10).join(files))
" > /tmp/playlist.m3u
vlc /tmp/playlist.m3u
```
If this fixes the "missing movies" symptom, the real fix is rewriting
`scan_and_play.py` to write an `.m3u` and launch VLC against the file instead of argv.
**This has not been tested yet** — do this test first before rewriting the script.

Do NOT prematurely rewrite scan_and_play.py's scanner logic (mount detection, resume
logic) — both were checked against the real drive structure and work correctly for
this setup. Rewriting working code here would be solving a problem that doesn't exist.

### Echo TV — separate, unexplored
`~/echo_tv_app/main.py` (50 lines) is confirmed to be ONLY an Android Kivy WebView
wrapper pointing at `http://192.168.4.46:59996` — it does not scan, index, or launch
anything itself. That IP/port needs verification (stale? matches echo_browser_server?).
Echo TV concept (toggleable virtual channels / random shuffle mode) is unbuilt — spec
only exists in conversation, not code. Decide later whether it becomes a Command
Center "Media" module or stays standalone — hold that decision until scan_and_play
fix is confirmed working.

---

## SmartTube (Onn Android TV) — LIKELY RESOLVED, unconfirmed

Symptom: multiple streaming apps stopped connecting; YouTube official app worked fine
(search + playback), SmartTube specifically lost search while playback partially
still worked ("continue watching" functioned).

Diagnosis: SmartTube v30.48 client drifted out of sync with YouTube backend API
changes — classic reverse-engineered-client-vs-moving-target failure, not a network/
DNS/router issue (ruled out: YouTube official app worked throughout, proving network/
DNS/TLS/clock were all fine).

Action taken: told to update SmartTube via Settings → About → Update, or sideload
latest APK from GitHub releases if in-app updater also fails.
**Not yet confirmed fixed** — need to verify search works post-update next session.

---

## CLEANUP DONE THIS SESSION

- `logging`, `ollama`, `os`, `subprocess` (4x ~12MB files in `~/vision_assistant/`
  root) — confirmed via `file` to be harmless ImageMagick PostScript exports, NOT
  Python stdlib shadows. Moved to `~/vision_assistant/archive/postscript/`.
- `echo_dashboard_api.py` committed (`361c525`)

## CLEANUP STILL PENDING (low priority, not blocking)
- Dozens of loose `.bak`/`.pre_*`/timestamped files in `~/vision_assistant/` root
  should eventually move into `archive/` — cosmetic, not urgent
- `parse_task()` in `ai.py` — confirmed working this session via /api/chat, but
  still carries multiple generations of patches per S17 handoff; revisit if it
  ever breaks again, not broken now

---

## HARDWARE / ENVIRONMENT NOTES CARRIED FORWARD

- SSD: 7/100 health — still critical, avoid large writes
- CPU throttling theory (from earlier "choppy"/fling investigation): **ruled out**.
  `scaling_max_freq` == `cpuinfo_max_freq` (4.9GHz), no TLP running, intel_pstate
  behaving normally. 1.7-1.8GHz readings were normal idle dynamic scaling.
- Warframe "fling into the void" stutter — **shelved, unresolved**. Leading theories
  still: DriftWM compositor frame stall accumulating input deltas, or disk I/O stall
  given SSD health. Needs live iostat/vmstat/intel_gpu_top capture during an actual
  stutter to diagnose — not done this session, user chose to deprioritize.

---

## TERMINAL HYGIENE NOTES (recurring friction points this session)

- zsh chokes on `#` comments when pasted as part of a multi-line block with commands
  — strip comments from anything meant to be pasted as a block
- Heredocs (`<< 'EOF'` / `<< 'PY'`) have caused `quote>` hung-prompt issues at least
  once this session — prefer single-line `python3 -c "..."` for anything short
  enough to fit, reserve heredocs for genuinely long scripts and write them to a
  file with `create_file`-equivalent methods rather than pasting inline
- Always verify actual PID/value before running commands with it — `<PID>` style
  placeholders in copy-pasted commands will error, substitute the real value first

---

## PRIORITY QUEUE — NEXT SESSION

1. Test `.m3u` playlist fix for VLC "missing movies" — confirms or kills the leading
   hypothesis before any code changes to scan_and_play.py
2. Deploy + test echo_command_center.html on the actual ThinkPad — first real render
3. Confirm SmartTube search works post-update
4. Instrument /api/chat latency by pipeline stage (12s is currently a black box)
5. `.bak`/`.pre_*` file sweep into archive/ — whenever there's a lull, not urgent

## THE RULE (carried forward)
Before building anything new:
```
~/vision_env/bin/python3 ~/echo_scan.py
```
Echo is reconnecting organs, not building new ones.

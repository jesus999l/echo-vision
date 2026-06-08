"""
Wake word + voice command handler.
Vosk for wake detection (lightweight), Whisper for commands (accurate).
"""
import os, sys, json, threading, subprocess, time, re, tempfile, wave
sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

VOSK_MODEL_PATH = os.path.expanduser("~/vosk-model-small-en-us-0.15")
VA_PYTHON       = "/home/jesus999l/vision_env/bin/python"
VA_MAIN         = "/home/jesus999l/vision_assistant/main.py"
MIC_DEVICE      = 11
COOLDOWN        = 3.0
COMMAND_TIMEOUT = 6
WAKE_PHRASES    = ["hey echo", "echo wake", "wake up echo"]

_running        = False
_last_trigger   = 0
_whisper_model  = None
_original_volume = None

# ── WHISPER ───────────────────────────────────────────────────────────────────
def _load_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        print("[wake] Loading Whisper small.en...")
        _whisper_model = whisper.load_model("small.en")
        print("[wake] Whisper ready.")
    return _whisper_model

def _transcribe_whisper(audio_path):
    try:
        m = _load_whisper()
        result = m.transcribe(
            audio_path, language="en", fp16=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            temperature=0.0,
        )
        if result.get("segments"):
            if result["segments"][0].get("no_speech_prob", 0) > 0.6:
                print("[wake] rejected — no speech")
                return ""
        return result["text"].strip().lower()
    except Exception as e:
        print(f"[wake] whisper error: {e}")
        return ""

# ── AUDIO ─────────────────────────────────────────────────────────────────────
def _make_stream(pa):
    import pyaudio
    return pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                   input=True, frames_per_buffer=2048,
                   input_device_index=MIC_DEVICE)

def _play_beep():
    for cmd in [
        ["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"],
        ["aplay", "/usr/share/sounds/alsa/Front_Left.wav"],
    ]:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except: pass

def _record_command(pa, seconds=COMMAND_TIMEOUT):
    """Wait for speech to start, then record until silence."""
    import audioop
    frames = []
    stream = _make_stream(pa)
    stream.start_stream()

    # Wait up to 3s for speech to start (vol > 800)
    deadline = time.time() + 3.0
    speech_started = False
    while time.time() < deadline:
        data = stream.read(2048, exception_on_overflow=False)
        if audioop.rms(data, 2) > 800:
            frames.append(data)
            speech_started = True
            break

    if speech_started:
        silence = 0
        for _ in range(int(16000 / 2048 * seconds)):
            data = stream.read(2048, exception_on_overflow=False)
            frames.append(data)
            vol = audioop.rms(data, 2)
            silence = silence + 1 if vol < 400 else 0
            if silence > 24 and len(frames) > 8:
                break

    stream.stop_stream(); stream.close()

    path = tempfile.mktemp(suffix=".wav")
    wf = wave.open(path, "wb")
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
    wf.writeframes(b"".join(frames)); wf.close()
    return path

# ── VOLUME DUCKING ────────────────────────────────────────────────────────────
def _duck_audio():
    global _original_volume
    try:
        r = subprocess.run("amixer get Master", shell=True, capture_output=True, text=True)
        m = re.search(r'\[(\d+)%\]', r.stdout)
        if m:
            _original_volume = int(m.group(1))
            ducked = max(10, int(_original_volume * 0.25))
            subprocess.run(f"amixer set Master {ducked}%", shell=True, capture_output=True)
            print(f"[duck] {_original_volume}% -> {ducked}%")
    except: pass

def _unduck_audio():
    global _original_volume
    try:
        if _original_volume is not None:
            subprocess.run(f"amixer set Master {_original_volume}%", shell=True, capture_output=True)
            print(f"[duck] restored {_original_volume}%")
            _original_volume = None
    except: pass

# ── NOTIFY / SPEAK ────────────────────────────────────────────────────────────
def _notify(msg):
    try:
        subprocess.Popen(["notify-send", "Echo", msg, "-t", "3000"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

def speak(text):
    try:
        from voice import speak as _speak
        _speak(text)
    except:
        try:
            subprocess.Popen(["espeak", "-s", "150", text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass

# ── ACTIONS ───────────────────────────────────────────────────────────────────
def _open_vision():
    subprocess.Popen([VA_PYTHON, VA_MAIN, "--ui"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _web_search(query):
    import urllib.parse
    _notify(f"🔍 {query}")
    subprocess.Popen(["xdg-open", f"https://www.google.com/search?q={urllib.parse.quote(query)}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def _read():
        try:
            from ai import chat
            resp = chat(f"Answer briefly in 1-2 sentences: {query}")
            if resp:
                speak(". ".join(resp.strip().split(". ")[:2]))
        except Exception as e:
            print(f"[wake] search error: {e}")
    threading.Thread(target=_read, daemon=True).start()

def _steam_charts(game):
    import urllib.parse
    subprocess.Popen(["xdg-open", f"https://steamcharts.com/search/?q={urllib.parse.quote(game)}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _notify(f"🎮 {game}")
    def _read():
        try:
            from ai import chat
            resp = chat(f"How many players are currently playing {game} on Steam? One sentence answer.")
            if resp: speak(resp.strip().split(".")[0])
        except Exception as e:
            print(f"[wake] steam error: {e}")
    threading.Thread(target=_read, daemon=True).start()

def _add_task(text):
    try:
        from memory import add_goal
        add_goal(text.strip(), category="task")
        _notify(f"✓ Task: {text}")
    except Exception as e:
        print(f"[wake] task error: {e}")

def _add_habit(text):
    try:
        from memory import add_habit
        text = text.strip().strip(".,!?")
        if text.startswith("to "): text = text[3:]
        add_habit(text, frequency="daily")
        _notify(f"◈ Habit: {text}")
    except Exception as e:
        print(f"[wake] habit error: {e}")

def _add_journal(text):
    try:
        from memory import save_journal_entry
        save_journal_entry(text.strip(), mood=3)
        _notify("✦ Journal saved")
    except Exception as e:
        print(f"[wake] journal error: {e}")

def _add_note(text):
    try:
        import sqlite3, time as _t
        from config import DB_PATH
        c = sqlite3.connect(DB_PATH)
        c.execute("CREATE TABLE IF NOT EXISTS quick_notes "
                  "(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, "
                  "content TEXT, created_at REAL, updated_at REAL)")
        now = _t.time()
        title = text[:40] + ("..." if len(text) > 40 else "")
        c.execute("INSERT INTO quick_notes (title,content,created_at,updated_at) VALUES (?,?,?,?)",
                  (title, text.strip(), now, now))
        c.commit(); c.close()
        _notify(f"📝 {title}")
    except Exception as e:
        print(f"[wake] note error: {e}")

def _parse_event_time(text):
    """Extract datetime from phrases like 'at 3pm', 'tomorrow at 9am'."""
    import datetime
    now = datetime.datetime.now()
    base = now + datetime.timedelta(days=1) if "tomorrow" in text else now
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2) or 0)
        mer = m.group(3)
        if mer == "pm" and h < 12: h += 12
        elif mer == "am" and h == 12: h = 0
        return base.replace(hour=h, minute=mn, second=0, microsecond=0)
    return base + datetime.timedelta(hours=1)

def _add_event(text):
    try:
        from memory import add_calendar_event
        import datetime
        start = _parse_event_time(text)
        end   = start + datetime.timedelta(hours=1)
        title = re.sub(r'\s*(at|on|tomorrow)\s+[\d:apm\s]+', '', text,
                       flags=re.IGNORECASE).strip() or text
        add_calendar_event(title, start.timestamp(), end.timestamp())
        _notify(f"◷ {title} — {start.strftime('%b %d %I:%M %p')}")
    except Exception as e:
        print(f"[wake] event error: {e}")

def _set_reminder(time_str, task_str):
    try:
        from briefing import add_reminder
        import datetime
        now = datetime.datetime.now()
        if "min" in time_str:
            mins = int(re.search(r'\d+', time_str).group())
            remind_at = now + datetime.timedelta(minutes=mins)
        else:
            m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', time_str)
            if m:
                h, mn = int(m.group(1)), int(m.group(2) or 0)
                mer = m.group(3)
                if mer == "pm" and h < 12: h += 12
                elif mer == "am" and h == 12: h = 0
                remind_at = now.replace(hour=h, minute=mn, second=0)
                if remind_at < now: remind_at += datetime.timedelta(days=1)
            else:
                remind_at = now + datetime.timedelta(hours=1)
        add_reminder(task_str, remind_at.timestamp())
        t = remind_at.strftime("%I:%M %p").lstrip("0")
        _notify(f"⏰ Reminder: {task_str} at {t}")
        speak(f"Reminder set for {t}")
    except Exception as e:
        print(f"[wake] reminder error: {e}")

def _play_music(query=None):
    try:
        from browser_control import play_liked, play_music
        result = play_music(query) if query else play_liked()
        _notify(f"🎵 {result}")
    except Exception as e:
        print(f"[wake] music error: {e}")

def _media(action):
    try:
        from browser_control import media_pause, media_next, media_prev, volume_up, volume_down, volume_mute
        {"pause": media_pause, "next": media_next, "previous": media_prev,
         "louder": volume_up, "quieter": volume_down, "mute": volume_mute}[action]()
    except Exception as e:
        print(f"[wake] media error: {e}")

def _ask_ai(question):
    try:
        _notify("💭 Thinking...")
        from ai import chat
        resp = chat(question)
        if resp:
            short = ". ".join(resp.split(". ")[:2])
            speak(short)
            _notify(short[:120])
    except Exception as e:
        print(f"[wake] ai error: {e}")

def _briefing():
    try:
        from briefing import get_morning_briefing, format_briefing_text
        b = get_morning_briefing()
        text = format_briefing_text(b)
        lines = [l for l in text.split("\n") if l.strip()]
        speak(". ".join(lines[:6]))
        _notify(text[:200])
    except Exception as e:
        print(f"[wake] briefing error: {e}")

# ── COMMAND ROUTER ────────────────────────────────────────────────────────────
def route_command(text):
    t = text.lower().strip()
    for wp in WAKE_PHRASES:
        t = t.replace(wp, "").strip()
    if not t:
        return
    print(f"[wake] routing: {t}")

    # Music playback
    if any(x in t for x in ["play my music","play music","play my playlist","play my liked","play liked"]):
        _play_music(); return
    if re.match(r"play\s+\S", t):
        q = re.sub(r"^play\s+(song\s+|the song\s+)?", "", t).strip()
        _play_music(q); return
    if any(x in t for x in ["pause","stop music"]): _media("pause"); return
    if any(x in t for x in ["next song","next track","skip"]): _media("next"); return
    if any(x in t for x in ["previous song","go back","last song"]): _media("previous"); return
    if any(x in t for x in ["louder","volume up","turn it up"]): _media("louder"); return
    if any(x in t for x in ["quieter","volume down","turn it down"]): _media("quieter"); return
    if "mute" in t: _media("mute"); return

    # Game player count
    for pat in [r"how many players.{0,10}(?:in|playing|on)\s+(.+?)(?:\s+right now|\s+today)?$",
                r"player count.{0,10}(?:for|of|in)\s+(.+)",
                r"steam charts?\s+(?:for\s+)?(.+)"]:
        m = re.search(pat, t)
        if m: _steam_charts(m.group(1).strip()); return

    # Reminders
    m = re.search(r"remind me (?:at |in )?(.+?)\s+to\s+(.+)", t)
    if m: _set_reminder(m.group(1).strip(), m.group(2).strip()); return

    # Tasks
    for pat in [r"add (?:a )?task\s+(.+)", r"create (?:a )?task\s+(.+)"]:
        m = re.search(pat, t)
        if m: _add_task(m.group(1)); return

    # Habits
    for pat in [r"add (?:a )?habit\s+(.+)", r"new habit\s+(.+)", r"track habit\s+(.+)"]:
        m = re.search(pat, t)
        if m: _add_habit(m.group(1)); return

    # Journal
    if any(x in t for x in ["journal", "diary entry"]):
        for pat in [r"journal(?:\s+entry)?\s+(.+)",
                    r"write (?:in )?(?:my )?journal\s+(.+)",
                    r"(?:add|save)\s+journal\s+(.+)"]:
            m = re.search(pat, t)
            if m: _add_journal(m.group(1)); return
        rest = t[t.find("journal")+7:].strip()
        if rest: _add_journal(rest); return

    # Notes
    if any(x in t for x in ["note", "take a note", "save a note"]):
        for pat in [r"(?:take|save|write|add)\s+(?:a\s+)?note\s+(.+)", r"note\s+(.+)"]:
            m = re.search(pat, t)
            if m: _add_note(m.group(1)); return
        rest = t[t.find("note")+4:].strip()
        if rest: _add_note(rest); return

    # Calendar event
    for pat in [r"add (?:an? )?event\s+(.+)", r"schedule\s+(.+)", r"create (?:an? )?event\s+(.+)"]:
        m = re.search(pat, t)
        if m: _add_event(m.group(1)); return

    # Briefing
    if any(x in t for x in ["briefing", "morning briefing", "what's today", "what is today", "my day"]):
        _briefing(); return

    # Open app
    if t in ("open", "show", "wake up", "open echo") or len(t) < 8:
        _open_vision(); return

    # Web search
    for pat in [r"search (?:for\s+)?(.+)", r"google\s+(.+)", r"look up\s+(.+)"]:
        m = re.search(pat, t)
        if m: _web_search(m.group(1)); return
    if re.match(r"(?:what|who|how|when|where|why)\s+", t):
        _web_search(t); return

    # AI fallback
    _ask_ai(text)

# ── WAKE DETECTOR ─────────────────────────────────────────────────────────────
def _is_wake(text):
    return any(p in text.lower() for p in WAKE_PHRASES)

def run_detector(status_cb=None):
    global _running, _last_trigger
    _running = True

    try:
        import pyaudio
        from vosk import Model, KaldiRecognizer
    except ImportError as e:
        print(f"[wake] Missing dependency: {e}"); return

    print("[wake] Loading Vosk...")
    model = Model(VOSK_MODEL_PATH)
    pa    = pyaudio.PyAudio()

    threading.Thread(target=_load_whisper, daemon=True).start()

    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(False)
    stream = _make_stream(pa)
    stream.start_stream()
    print("[wake] Ready — say 'Hey Echo'")
    if status_cb: status_cb("listening")

    try:
        while _running:
            data = stream.read(2048, exception_on_overflow=False)
            if not rec.AcceptWaveform(data):
                continue
            text = json.loads(rec.Result()).get("text", "").strip()
            if not text or not _is_wake(text):
                continue

            now = time.time()
            if now - _last_trigger < COOLDOWN:
                continue
            _last_trigger = now
            print(f"[wake] Triggered: '{text}'")

            inline = text.lower()
            for wp in WAKE_PHRASES:
                inline = inline.replace(wp, "").strip()

            stream.stop_stream(); stream.close()
            _duck_audio()
            _play_beep()
            time.sleep(0.3)

            if inline and len(inline) > 3:
                route_command(inline)
                _unduck_audio()
            else:
                print("[wake] Listening for command...")
                audio_path = _record_command(pa)
                cmd = _transcribe_whisper(audio_path)
                _unduck_audio()
                try: os.unlink(audio_path)
                except: pass
                if cmd:
                    cmd = cmd.strip().strip(".,!?")
                    cmd = cmd.replace("hey echo", "").replace("echo", "").strip()
                if cmd and len(cmd) > 2:
                    print(f"[wake] heard: {cmd}")
                    route_command(cmd)
                else:
                    print("[wake] No command heard")

            rec = KaldiRecognizer(model, 16000)
            rec.SetWords(False)
            stream = _make_stream(pa)
            stream.start_stream()
            print("[wake] Listening again...")

    except KeyboardInterrupt:
        pass
    finally:
        try: stream.stop_stream(); stream.close()
        except: pass
        pa.terminate()
        _running = False
        print("[wake] Stopped.")

def stop_detector():
    global _running
    _running = False

def start_in_background(status_cb=None):
    t = threading.Thread(target=run_detector, args=(status_cb,), daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    run_detector()

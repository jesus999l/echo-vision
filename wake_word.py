"""
Wake word + voice command handler.
Vosk for wake detection (lightweight), Whisper for commands (accurate).
"""
import os, sys, json, threading, subprocess, time, re, tempfile, wave
sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

VOSK_MODEL_PATH = os.path.expanduser("~/vosk-model-small-en-us-0.15")
VA_PYTHON       = "/home/jesus999l/vision_env/bin/python"
VA_MAIN         = "/home/jesus999l/vision_assistant/main.py"
def get_mic_device():
    """Dynamically find the best input device index at runtime."""
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            try:
                d = p.get_device_info_by_index(i)
                if d["maxInputChannels"] > 0:
                    devices.append((i, d["name"].lower()))
            except: pass
        p.terminate()
        # Priority: pulse > pipewire > default > sysdefault > first available
        for priority in ["pulse", "pipewire", "default", "sysdefault"]:
            for idx, name in devices:
                if priority in name:
                    print(f"[mic] Using device {idx}: {name}")
                    return idx
        if devices:
            print(f"[mic] Fallback device {devices[0][0]}: {devices[0][1]}")
            return devices[0][0]
    except Exception as e:
        print(f"[mic] Device detection failed: {e}")
    return None

MIC_DEVICE = get_mic_device()
COOLDOWN        = 3.0
COMMAND_TIMEOUT = 6
WAKE_PHRASES    = ["hey echo", "echo wake", "wake up echo"]

_running        = False
_last_trigger   = 0
_whisper_model   = None
_original_volume = None
_voice_profile   = None   # numpy mean MFCC fingerprint of enrolled user
_pa_instance     = None

# ── FASTER-WHISPER ────────────────────────────────────────────────────────────
def _load_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("[wake] Loading faster-whisper small.en (int8)...")
        _whisper_model = WhisperModel(
            "small.en", device="cpu", compute_type="int8",
            num_workers=2, cpu_threads=4,
        )
        print("[wake] Whisper ready.")
    return _whisper_model

def _transcribe_whisper(audio_path):
    try:
        m = _load_whisper()
        segs, info = m.transcribe(
            audio_path, language="en",
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
            temperature=0.0,
            beam_size=1,
        )
        if info.all_language_probs and info.language_probability < 0.6:
            print("[wake] rejected — low language confidence")
            return ""
        text = " ".join(s.text for s in segs).strip().lower()
        print(f"[wake] transcribed: {text!r}")
        return text
    except Exception as e:
        print(f"[wake] whisper error: {e}")
        return ""

# ── VOICE FINGERPRINT (multi-user) ───────────────────────────────────────────
VOICE_PROFILES_DIR = os.path.expanduser("~/vision_assistant/voice_profiles")
# Legacy single-profile path (kept for migration)
VOICE_PROFILE_PATH = os.path.expanduser("~/vision_assistant/voice_profile.npy")

def _extract_voice_features(audio_bytes):
    """Return energy-band fingerprint from raw PCM bytes."""
    try:
        import numpy as np
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) < 1600: return None
        chunk = len(samples) // 8
        return np.array([
            np.sqrt(np.mean(samples[i*chunk:(i+1)*chunk]**2))
            for i in range(8)
        ])
    except: return None

def enroll_voice(pa, seconds=4, label="main"):
    """Record voice for 4s and save as label (main or guest_name)."""
    os.makedirs(VOICE_PROFILES_DIR, exist_ok=True)
    name = "Main User" if label == "main" else label.replace("guest_","").title()
    print(f"[voice] Enrolling {name}...")
    speak(f"Recording {name}. Please speak naturally.")
    frames = []
    stream = _make_stream(pa)
    stream.start_stream()
    for _ in range(int(16000 / 2048 * seconds)):
        data = stream.read(2048, exception_on_overflow=False)
        frames.append(data)
    stream.stop_stream(); stream.close()
    raw = b"".join(frames)
    feat = _extract_voice_features(raw)
    if feat is not None:
        import numpy as np
        path = os.path.join(VOICE_PROFILES_DIR, f"{label}.npy")
        np.save(path, feat)
        print(f"[voice] Profile saved: {label}")
        speak(f"{name} enrolled.")
    else:
        print("[voice] Enrollment failed.")
        speak("Enrollment failed, please try again.")

def _load_all_profiles():
    """Load all enrolled voice profiles. Returns list of numpy arrays."""
    import numpy as np
    profiles = []
    # Load from profiles dir
    if os.path.exists(VOICE_PROFILES_DIR):
        for f in os.listdir(VOICE_PROFILES_DIR):
            if f.endswith(".npy"):
                try:
                    profiles.append(np.load(os.path.join(VOICE_PROFILES_DIR, f)))
                except: pass
    # Migrate legacy single profile
    if not profiles and os.path.exists(VOICE_PROFILE_PATH):
        try:
            feat = np.load(VOICE_PROFILE_PATH)
            os.makedirs(VOICE_PROFILES_DIR, exist_ok=True)
            np.save(os.path.join(VOICE_PROFILES_DIR, "main.npy"), feat)
            profiles.append(feat)
        except: pass
    return profiles

def _voice_matches(audio_bytes, threshold=0.72):
    """Return True if audio matches any enrolled profile (or none enrolled)."""
    _cfg = __import__("json").load(open(__import__("os").path.expanduser("~/vision_assistant/settings.json"))) if __import__("os").path.exists(__import__("os").path.expanduser("~/vision_assistant/settings.json")) else {}
    try:
        import json
        s = json.load(open(os.path.expanduser("~/vision_assistant/settings.json")))
        if not s.get("voice_id_enabled", False):
            return True  # feature disabled
    except: return True
    profiles = _load_all_profiles()
    if not profiles: return True
    feat = _extract_voice_features(audio_bytes)
    if feat is None: return True
    try:
        import numpy as np
        for profile in profiles:
            sim = np.dot(feat, profile) / (np.linalg.norm(feat) * np.linalg.norm(profile) + 1e-9)
            print(f"[voice] similarity: {sim:.2f}")
            if float(sim) > threshold:
                return True
        return False
    except: return True

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

# Instant Vosk-only command keywords — never touch Whisper
INSTANT_COMMANDS = {
    "pause": "pause",  "pause music": "pause", "stop music": "pause",
    "play":  "play",   "play music": "play",   "resume": "play",
    "next":  "next",   "next song": "next",    "skip": "next",
    "previous": "previous", "prev song": "previous",
    "stop": "stop",    "cancel": "stop",
    "open echo": "open",   "open dashboard": "open",
    "volume up": "volume up", "louder": "volume up",
    "volume down": "volume down", "quieter": "volume down",
    "mute": "mute",
}

def _noise_gate(raw_bytes, threshold=600):
    """Zero out frames below threshold (background noise suppression)."""
    import audioop, struct
    frame_size = 2  # 16-bit
    result = bytearray()
    for i in range(0, len(raw_bytes) - frame_size, frame_size):
        chunk = raw_bytes[i:i+frame_size]
        if audioop.rms(chunk, 2) < threshold:
            result += b""
        else:
            result += chunk
    return bytes(result)

def _record_command(pa, seconds=COMMAND_TIMEOUT):
    """webrtcvad-based recording: tight endpoint, noise gate, voice check."""
    import audioop
    # webrtcvad needs 10/20/30ms frames at 16kHz → 160/320/480 samples
    FRAME_MS   = 20
    FRAME_SAMP = int(16000 * FRAME_MS / 1000)   # 320 samples
    FRAME_BYTES = FRAME_SAMP * 2                  # 640 bytes

    try:
        import webrtcvad
        vad = webrtcvad.Vad(2)   # aggressiveness 0-3 (2 = balanced)
        use_vad = True
    except ImportError:
        use_vad = False
        import audioop as _ao

    frames = []
    raw_all = bytearray()
    stream = _make_stream(pa)
    stream.start_stream()

    # Wait up to 3s for speech onset
    speech_started = False
    deadline = time.time() + 3.0
    buf = b""
    while time.time() < deadline:
        chunk = stream.read(FRAME_BYTES, exception_on_overflow=False)
        buf += chunk
        while len(buf) >= FRAME_BYTES:
            frame = buf[:FRAME_BYTES]; buf = buf[FRAME_BYTES:]
            if use_vad:
                is_speech = vad.is_speech(frame, 16000)
            else:
                is_speech = audioop.rms(frame, 2) > 800
            if is_speech:
                frames.append(frame)
                raw_all += frame
                speech_started = True
                break
        if speech_started: break

    if speech_started:
        silence_frames = 0
        MAX_SILENCE = 20   # 8 × 20ms = 160ms of silence → stop
        max_frames = int(1000 / FRAME_MS * seconds)
        buf = b""
        for _ in range(max_frames):
            chunk = stream.read(FRAME_BYTES, exception_on_overflow=False)
            buf += chunk
            while len(buf) >= FRAME_BYTES:
                frame = buf[:FRAME_BYTES]; buf = buf[FRAME_BYTES:]
                frames.append(frame)
                raw_all += frame
                if use_vad:
                    is_speech = vad.is_speech(frame, 16000)
                else:
                    is_speech = audioop.rms(frame, 2) > 500
                silence_frames = 0 if is_speech else silence_frames + 1
                if silence_frames >= MAX_SILENCE and len(frames) > 10:
                    break
            else:
                continue
            break

    stream.stop_stream(); stream.close()

    # Voice identity check
    if raw_all and not _voice_matches(bytes(raw_all)):
        print("[wake] voice rejected — not enrolled user")
        return None

    # Noise gate
    gated = _noise_gate(bytes(raw_all)) if raw_all else b""

    path = tempfile.mktemp(suffix=".wav")
    wf = wave.open(path, "wb")
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
    wf.writeframes(gated if gated else b"".join(frames))
    wf.close()
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
        # Write to Echo speech bubble
        open("/tmp/echo_bubble.txt", "w").write(str(text))
        import threading
        def _clear():
            import time; time.sleep(6)
            try: open("/tmp/echo_bubble.txt", "w").write("")
            except: pass
        threading.Thread(target=_clear, daemon=False).start()
    except: pass
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
            gen = _stream_voice_response(
                f"Answer briefly in 1-2 sentences: {query}", full_context=False)
            from voice import speak_stream
            speak_stream(gen)
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
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] task error: {e}")

def _add_habit(text):
    try:
        import re as _re
        from memory import add_habit, update_habit_target, get_habits
        raw = text.strip().strip(".,!?")
        freq = "daily"
        for f in ["daily","weekly","monthly"]:
            if f in raw.lower():
                freq = f
                raw = _re.sub(f, "", raw, flags=_re.IGNORECASE).strip()
        target = 1
        m = _re.search(r"(\d+)\s*(?:times?|x\b)", raw)
        if m:
            target = int(m.group(1))
            raw = raw[:m.start()].strip()
        elif "twice" in raw:
            target = 2
            raw = raw.replace("twice","").strip()
        raw = raw.strip().strip(".,!?")
        if raw.startswith("to "): raw = raw[3:]
        if not raw: return
        add_habit(raw, frequency=freq)
        habits = get_habits()
        if habits:
            update_habit_target(habits[-1]["id"], target, freq)
        _notify(f"◈ Habit: {raw} ({target}x {freq})")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] habit error: {e}")

def _add_journal(text):
    try:
        from memory import save_journal_entry
        save_journal_entry(text.strip(), mood=3)
        _notify("✦ Journal saved")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] journal error: {e}")

def _add_note(text):
    try:
        import sqlite3, time as _t
        from config import DB_PATH
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE IF NOT EXISTS quick_notes "
                  "(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, "
                  "content TEXT, created_at REAL, updated_at REAL)")
        now = _t.time()
        title = text[:40] + ("..." if len(text) > 40 else "")
        c.execute("INSERT INTO quick_notes (title,content,created_at,updated_at) VALUES (?,?,?,?)",
                  (title, text.strip(), now, now))
        c.commit(); c.close()
        _notify(f"📝 {title}")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] note error: {e}")

def _next_weekday(now, weekday):
    import datetime
    days = (weekday - now.weekday() + 7) % 7 or 7
    return now + datetime.timedelta(days=days)

def _parse_event_time(text):
    import datetime
    now = datetime.datetime.now()
    base = now
    t = text.lower()
    if "tomorrow" in t:         base = now + datetime.timedelta(days=1)
    elif "next monday" in t:    base = _next_weekday(now, 0)
    elif "next tuesday" in t:   base = _next_weekday(now, 1)
    elif "next wednesday" in t: base = _next_weekday(now, 2)
    elif "next thursday" in t:  base = _next_weekday(now, 3)
    elif "next friday" in t:    base = _next_weekday(now, 4)
    elif "next saturday" in t:  base = _next_weekday(now, 5)
    elif "next sunday" in t:    base = _next_weekday(now, 6)
    else:
        for i, day in enumerate(["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]):
            if f"on {day}" in t:
                base = _next_weekday(now, i); break
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2) or 0)
        mer = m.group(3)
        if mer == "pm" and h < 12: h += 12
        elif mer == "am" and h == 12: h = 0
        return base.replace(hour=h, minute=mn, second=0, microsecond=0)
    return base.replace(hour=9, minute=0, second=0, microsecond=0)

def _add_event(text):
    try:
        from memory import add_calendar_event
        import datetime
        dur_mins = 60
        dm = re.search(r"for\s+(\d+)\s*(hour|hr|minute|min)", text, re.IGNORECASE)
        if dm:
            n = int(dm.group(1))
            dur_mins = n*60 if "h" in dm.group(2).lower() else n
        start = _parse_event_time(text)
        end   = start + datetime.timedelta(minutes=dur_mins)
        place = ""
        pm = re.search(r"\bat\s+([A-Za-z][\w\s']+?)(?=\s+at\s+\d|\s+for\s+\d|$)", text, re.IGNORECASE)
        if pm and not re.search(r"\d", pm.group(1)):
            place = pm.group(1).strip()
        title = text
        title = re.sub(r"\b(tomorrow|next\s+\w+day|on\s+\w+day)\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\bat\s+\d[\d:]*\s*(am|pm)?", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\bfor\s+\d+\s*(hour|hr|minute|min)s?", "", title, flags=re.IGNORECASE)
        title = title.strip().strip(".,!?") or text
        desc = f"📍 {place}" if place else ""
        add_calendar_event(title, start.timestamp(), end.timestamp(), description=desc)
        time_fmt = start.strftime("%-I:%M %p on %b %d")
        msg = f"◷ {title} — {time_fmt}"
        if place: msg += f" @ {place}"
        _notify(msg)
        speak(f"Event set: {title}, {time_fmt}")
        _signal_ui_refresh()
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
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] reminder error: {e}")

def _play_music(query=None):
    try:
        from browser_control import play_liked, play_music
        result = play_music(query) if query else play_liked()
        _notify(f"🎵 {result}")
    except Exception as e:
        print(f"[wake] music error: {e}")

def _play_usb(path=None):
    try:
        from browser_control import play_usb
        result = play_usb(path)
        print(f"[wake] usb: {result}")
    except Exception as e:
        print(f"[wake] usb error: {e}")

def _system_status_speak():
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from system_clean import system_status
        from voice import speak
        speak(system_status())
    except Exception as e:
        print(f"[wake] system status error: {e}")

def _system_clean_speak():
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from system_clean import clean_system
        from voice import speak
        speak("Starting system cleanup. This may take a moment.")
        result = clean_system()
        speak("Cleanup complete. " + result.split("\n")[0])
    except Exception as e:
        print(f"[wake] system clean error: {e}")

def _media(action):
    try:
        from browser_control import media_pause, media_next, media_prev, volume_up, volume_down, volume_mute
        {"pause": media_pause, "next": media_next, "previous": media_prev,
         "louder": volume_up, "quieter": volume_down, "mute": volume_mute}[action]()
    except Exception as e:
        print(f"[wake] media error: {e}")

# Keywords that need full memory context
_FULL_CTX_WORDS = {
    "my", "i have", "i've", "today", "tomorrow", "week", "month",
    "habit", "task", "goal", "journal", "event", "remind", "schedule",
    "mood", "streak", "progress", "note", "calendar",
}

def _needs_full_context(text):
    t = text.lower()
    return any(w in t for w in _FULL_CTX_WORDS)

def _stream_voice_response(question, full_context=False):
    """
    Stream Ollama response, yielding complete sentences as they arrive.
    fast path:  no system prompt, no memory, max_tokens=80
    full path:  light system prompt + memory context, max_tokens=200
    """
    import requests as _req, json as _json
    from config import LLM_URL, DEFAULT_MODEL

    messages = []

    if full_context:
        try:
            from memory import build_memory_context
            ctx = build_memory_context()
        except: ctx = ""
        try:
            import json as _j, os as _o
            _gl = _j.load(open(_o.path.expanduser("~/vision_assistant/settings.json"))).get("ai_guidelines","")
        except: _gl = ""
        sys_prompt = (
            "You are Echo, a concise voice assistant. "
            "Answer in 1-3 short sentences. No markdown, no lists. "
            "Use the user context only if directly relevant."
            + (("\n\n" + _gl) if _gl else "")
            + (ctx[:400] if ctx else "")
        ).strip()
        messages.append({"role": "system", "content": sys_prompt})
    else:
        messages.append({"role": "system",
                         "content": "You are Echo. Answer in 1-2 short sentences. No markdown."})

    messages.append({"role": "user", "content": question})

    max_tok = 200 if full_context else 80

    try:
        r = _req.post(
            LLM_URL,
            json={
                "model":       DEFAULT_MODEL,
                "messages":    messages,
                "max_tokens":  max_tok,
                "stream":      True,
                "temperature": 0.7,
            },
            stream=True,
            timeout=30,
        )
        buf = ""
        SENTENCE_END = {".", "!", "?"}
        for line in r.iter_lines():
            if not line: continue
            raw = line.decode("utf-8")
            if raw.startswith("data: "):
                raw = raw[6:]
            if raw in ("[DONE]", ""): break
            try:
                token = _json.loads(raw)["choices"][0]["delta"].get("content", "")
            except: continue
            buf += token
            # Yield on sentence boundaries
            while True:
                for i, ch in enumerate(buf):
                    if ch in SENTENCE_END and (i+1 >= len(buf) or buf[i+1] == " "):
                        sentence = buf[:i+1].strip()
                        buf = buf[i+2:].strip()
                        if sentence:
                            yield sentence
                        break
                else:
                    break
        if buf.strip():
            yield buf.strip()
    except Exception as e:
        print(f"[wake] stream error: {e}")
        yield ""


def _ask_ai(question):
    try:
        _notify("💭 Echo...")
        full = _needs_full_context(question)
        mode = "full" if full else "fast"
        print(f"[wake] AI {mode}: {question!r}")
        gen = _stream_voice_response(question, full_context=full)
        from voice import speak_stream
        first = None
        collected = []
        def _with_notify(g):
            nonlocal first
            for s in g:
                if first is None:
                    first = s
                    _notify(s[:120])
                collected.append(s)
                yield s
        speak_stream(_with_notify(gen))
        # Send full response to UI chat
        try:
            import socket, json as _j
            from config import IPC_HOST, IPC_PORT, IPC_MAGIC
            full_text = f"You: {question}\nEcho: {' '.join(collected)}"
            payload = _j.dumps({"magic": IPC_MAGIC, "screenshot": "", "ocr": full_text}).encode()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2); s.connect((IPC_HOST, IPC_PORT))
            s.sendall(payload); s.close()
        except: pass
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
def _fuzzy_correct(t):
    """Fix common Whisper mis-transcriptions before routing."""
    replacements = {
        # Pause variants
        "fause": "pause", "paus ": "pause ", "pausing": "pause",
        "paul's": "pause", "poses": "pause",
        # Play variants
        "plea": "play", "plane": "play", "playa": "play",
        # Next/previous
        "nex ": "next ", "neck song": "next song",
        "next on": "next song", "text song": "next song",
        "previous on": "previous song", "prefix song": "previous song",
        # Volume
        "louder please": "volume up", "turn up": "volume up",
        "quieter": "volume down", "turn down": "volume down",
        # System
        "system stasis": "system status", "system stats": "system status",
        "clean system please": "clean system",
        # Music
        "my music please": "my music", "play music please": "play music",
        # USB
        "play use b": "play usb", "play you as b": "play usb",
        # Common word errors
        "acko": "echo", "eko": "echo", "ecco": "echo",
    }
    result = t
    for wrong, right in replacements.items():
        result = result.replace(wrong, right)
    return result

def route_command(text):
    t = text.lower().strip()
    for wp in WAKE_PHRASES:
        t = t.replace(wp, "").strip()
    if not t:
        return
    # Apply fuzzy correction before routing
    corrected = _fuzzy_correct(t)
    if corrected != t:
        print(f"[wake] fuzzy: {t!r} → {corrected!r}")
        t = corrected
    print(f"[wake] routing: {t}")
    # Morning briefing
    if any(x in t for x in ["good morning","morning briefing","what's my day","whats my day"]):
        try:
            from briefing import get_morning_briefing, speak_morning_briefing
            import threading
            threading.Thread(target=lambda: speak_morning_briefing(get_morning_briefing()), daemon=True).start()
            _notify("🌅 Morning briefing...")
        except Exception as e:
            print(f"[wake] briefing error: {e}")
        return
    # Voice enrollment
    if any(x in t for x in ["enroll my voice","enroll voice","train my voice","remember my voice"]):
        if _pa_instance:
            threading.Thread(target=enroll_voice, args=(_pa_instance,), kwargs={"label":"main"}, daemon=True).start()
        else:
            speak("Microphone not ready yet.")
        return
    m = re.search(r"enroll\s+(?:guest\s+)?(\w+)(?:'s|s)?\s+voice", t)
    if m:
        name = m.group(1).lower()
        if _pa_instance:
            threading.Thread(target=enroll_voice, args=(_pa_instance,),
                             kwargs={"label": f"guest_{name}"}, daemon=True).start()
        else:
            speak("Microphone not ready yet.")
        return
    if any(x in t for x in ["forget my voice","reset voice","clear voice profile","clear all voices"]):
        import shutil
        if os.path.exists(VOICE_PROFILES_DIR):
            shutil.rmtree(VOICE_PROFILES_DIR)
            os.makedirs(VOICE_PROFILES_DIR)
        if os.path.exists(VOICE_PROFILE_PATH):
            os.unlink(VOICE_PROFILE_PATH)
        speak("All voice profiles cleared.")
        return
    m2 = re.search(r"(?:forget|remove|delete)\s+(?:guest\s+)?(\w+)(?:'s|s)?\s+voice", t)
    if m2:
        name = m2.group(1).lower()
        path = os.path.join(VOICE_PROFILES_DIR, f"guest_{name}.npy")
        if os.path.exists(path):
            os.unlink(path)
            speak(f"Removed {name}'s voice profile.")
        else:
            speak(f"No profile found for {name}.")
        return

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

    # USB / local media
    # Text selector
    if any(x in t for x in ["select text","read screen","copy text","text selector","scan text","read text"]):
        import threading, subprocess as _sp
        threading.Thread(target=lambda: _sp.Popen([
            "/home/jesus999l/vision_env/bin/python3",
            "/home/jesus999l/vision_assistant/text_selector.py"
        ]), daemon=True).start(); return

    if any(x in t for x in ["play usb","play from usb","play local","play media","play movie","play show","play from drive"]):
        _play_usb(); return
    if any(x in t for x in ["stop vlc","stop movie","stop video","stop playing"]): 
        from browser_control import vlc_stop; vlc_stop(); return

    # Warframe bot commands
    import re as _re
    _farm_match = _re.search(r"farm\s+(.+)", t)
    if _farm_match:
        resource = _farm_match.group(1).strip()
        def _start_farm(res=resource):
            try:
                import subprocess as _sp
                from voice import speak
                speak(f"Starting farm for {res}. Check the terminal for progress.")
                _sp.Popen([
                    "/home/jesus999l/vision_env/bin/python3",
                    "/home/jesus999l/echo_warframe/echo_warframe_bot.py",
                    "--resource", res
                ])
                _notify(f"🎮 Farming: {res}")
            except Exception as e:
                print(f"[wake] farm error: {e}")
        import threading; threading.Thread(target=_start_farm, daemon=True).start(); return

    if any(x in t for x in ["stop farming", "stop bot", "stop warframe bot"]):
        import subprocess as _sp
        _sp.run(["pkill", "-f", "echo_warframe_bot"], capture_output=True)
        from voice import speak
        speak("Farming stopped.")
        return

    if any(x in t for x in ["what should i farm", "farming tip", "where to farm", "best farm"]):
        def _farm_tip():
            try:
                from voice import speak
                speak("Tell me what resource you need and I will look it up. For example, say: farm orokin cells.")
            except Exception as e:
                print(f"[wake] farm tip error: {e}")
        import threading; threading.Thread(target=_farm_tip, daemon=True).start(); return

    # Game recorder queries
    if any(x in t for x in ["how do i play","my playstyle","game summary","how i play","warframe summary"]):
        def _playstyle():
            try:
                from echo_game_recorder import summarize_playstyle
                from voice import speak
                summary = summarize_playstyle()
                speak(summary)
                _notify(summary[:200])
            except Exception as e:
                print(f"[wake] playstyle error: {e}")
        import threading; threading.Thread(target=_playstyle, daemon=True).start(); return

    if any(x in t for x in ["game stats","last session","last game","session stats"]):
        def _game_stats():
            try:
                from echo_game_recorder import get_recent_sessions
                from voice import speak
                sessions = get_recent_sessions(1)
                if not sessions:
                    speak("No game sessions recorded yet.")
                    return
                s = sessions[0]
                msg = (f"Last session: {s.get('duration', 0):.0f} seconds, "
                       f"{s.get('events', 0)} inputs recorded, "
                       f"{s.get('focused', 0):.0f} seconds in focus.")
                speak(msg)
                _notify(msg)
            except Exception as e:
                print(f"[wake] game stats error: {e}")
        import threading; threading.Thread(target=_game_stats, daemon=True).start(); return

    # System status + cleanup
    if any(x in t for x in ["system status","how's the system","check system","cpu usage","ram usage","memory usage"]):
        import threading; threading.Thread(target=_system_status_speak, daemon=True).start(); return
    if any(x in t for x in ["clean system","clean up","system cleanup","free up space","clear cache"]):
        import threading; threading.Thread(target=_system_clean_speak, daemon=True).start(); return

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

    global _pa_instance
    _pa_instance = pa
    threading.Timer(8.0, _load_whisper).start()  # pre-warm after Vosk fully loaded

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
                # Check instant commands from Vosk text directly
                instant = INSTANT_COMMANDS.get(inline.lower())
                if instant:
                    route_command(instant)
                else:
                    route_command(inline)
                _unduck_audio()
            else:
                print("[wake] Listening for command...")
                audio_path = _record_command(pa)
                if audio_path is None:
                    # Voice rejected
                    _unduck_audio()
                    stream = _make_stream(pa); stream.start_stream()
                    continue
                cmd = _transcribe_whisper(audio_path)
                _unduck_audio()
                try: os.unlink(audio_path)
                except: pass
                if cmd:
                    cmd = cmd.strip().strip(".,!?")
                    cmd = cmd.replace("hey echo", "").replace("echo", "").strip()
                    # Check instant command map first (no Whisper needed next time via Vosk inline)
                    instant = INSTANT_COMMANDS.get(cmd.lower())
                    if instant:
                        route_command(instant); stream = _make_stream(pa); stream.start_stream(); continue
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

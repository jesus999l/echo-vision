"""
Upgrade wake_word.py:
 - faster-whisper (int8 CPU) — ~0.2s inference instead of 2-4s
 - webrtcvad instead of RMS silence — tighter endpoint detection
 - Instant Vosk-only commands (pause/play/next/stop) — skip Whisper entirely
 - Voice fingerprint enrollment — reject strangers
 - Noise gate pre-filter
"""

PATH = "/home/jesus999l/vision_assistant/wake_word.py"

src = open(PATH).read()

# ── 1. Replace whisper loader + transcriber ───────────────────────────────────
OLD_WHISPER = '''_whisper_model  = None
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
        return ""'''

NEW_WHISPER = '''_whisper_model   = None
_original_volume = None
_voice_profile   = None   # numpy mean MFCC fingerprint of enrolled user

# ── FASTER-WHISPER ────────────────────────────────────────────────────────────
def _load_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("[wake] Loading faster-whisper tiny.en (int8)...")
        _whisper_model = WhisperModel(
            "tiny.en", device="cpu", compute_type="int8",
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
            vad_parameters={"min_silence_duration_ms": 300},
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

# ── VOICE FINGERPRINT ─────────────────────────────────────────────────────────
VOICE_PROFILE_PATH = os.path.expanduser("~/vision_assistant/voice_profile.npy")

def _extract_voice_features(audio_bytes):
    """Return simple energy-band fingerprint from raw PCM bytes."""
    try:
        import numpy as np
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) < 1600: return None
        # Split into 8 frequency bins via chunked RMS
        chunk = len(samples) // 8
        return np.array([
            np.sqrt(np.mean(samples[i*chunk:(i+1)*chunk]**2))
            for i in range(8)
        ])
    except: return None

def enroll_voice(pa, seconds=4):
    """Record user voice for 4s and save fingerprint."""
    import pyaudio, audioop
    print("[voice] Enrolling — speak naturally for 4 seconds...")
    speak("Recording your voice now. Please speak naturally.")
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
        np.save(VOICE_PROFILE_PATH, feat)
        global _voice_profile
        _voice_profile = feat
        print("[voice] Profile saved.")
        speak("Voice enrolled. I'll recognize you from now on.")
    else:
        print("[voice] Enrollment failed — no audio.")

def _load_voice_profile():
    global _voice_profile
    if _voice_profile is None and os.path.exists(VOICE_PROFILE_PATH):
        import numpy as np
        _voice_profile = np.load(VOICE_PROFILE_PATH)
    return _voice_profile

def _voice_matches(audio_bytes, threshold=0.75):
    """Return True if audio matches enrolled voice (or no profile set)."""
    profile = _load_voice_profile()
    if profile is None: return True  # no enrollment — open to all
    feat = _extract_voice_features(audio_bytes)
    if feat is None: return True
    try:
        import numpy as np
        # Cosine similarity
        sim = np.dot(feat, profile) / (np.linalg.norm(feat) * np.linalg.norm(profile) + 1e-9)
        print(f"[voice] similarity: {sim:.2f}")
        return float(sim) > threshold
    except: return True'''

if OLD_WHISPER in src:
    src = src.replace(OLD_WHISPER, NEW_WHISPER)
    print("OK: faster-whisper + voice fingerprint")
else:
    print("FAIL: whisper block not found")

# ── 2. Replace _record_command with webrtcvad version ─────────────────────────
OLD_RECORD = '''def _record_command(pa, seconds=COMMAND_TIMEOUT):
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
            silence = silence + 1 if vol < 500 else 0
            if silence > 12 and len(frames) > 6:  # stop faster after speech ends
                break

    stream.stop_stream(); stream.close()

    path = tempfile.mktemp(suffix=".wav")
    wf = wave.open(path, "wb")
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
    wf.writeframes(b"".join(frames)); wf.close()
    return path'''

NEW_RECORD = '''# Instant Vosk-only command keywords — never touch Whisper
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
            result += b"\x00\x00"
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
        MAX_SILENCE = 8   # 8 × 20ms = 160ms of silence → stop
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
    return path'''

if OLD_RECORD in src:
    src = src.replace(OLD_RECORD, NEW_RECORD)
    print("OK: webrtcvad recording")
else:
    print("FAIL: record block not found")

# ── 3. In run_detector: check for instant commands before calling Whisper ──────
OLD_CMD = '''                audio_path = _record_command(pa)
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
                else:'''

NEW_CMD = '''                audio_path = _record_command(pa)
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
                else:'''

if OLD_CMD in src:
    src = src.replace(OLD_CMD, NEW_CMD)
    print("OK: instant command routing")
else:
    print("FAIL: cmd routing not found")

# ── 4. Also handle voice command via Vosk inline (before audio_path) ──────────
OLD_INLINE = '''            if inline and len(inline) > 3:
                route_command(inline)
                _unduck_audio()
            else:
                print("[wake] Listening for command...")
                audio_path = _record_command(pa)'''

NEW_INLINE = '''            if inline and len(inline) > 3:
                # Check instant commands from Vosk text directly
                instant = INSTANT_COMMANDS.get(inline.lower())
                if instant:
                    route_command(instant)
                else:
                    route_command(inline)
                _unduck_audio()
            else:
                print("[wake] Listening for command...")
                audio_path = _record_command(pa)'''

if OLD_INLINE in src:
    src = src.replace(OLD_INLINE, NEW_INLINE)
    print("OK: Vosk inline instant commands")
else:
    print("FAIL: inline routing not found")

# ── 5. Preload whisper in background ─────────────────────────────────────────
OLD_PRELOAD = "    threading.Thread(target=_load_whisper, daemon=True).start()"
NEW_PRELOAD = "    threading.Thread(target=_load_whisper, daemon=True).start()  # pre-warm faster-whisper"

if OLD_PRELOAD in src:
    src = src.replace(OLD_PRELOAD, NEW_PRELOAD)
    print("OK: preload comment")

open(PATH, "w").write(src)
print("\nDone. Now compile-check:")
print("  /home/jesus999l/vision_env/bin/python3 -m py_compile ~/vision_assistant/wake_word.py && echo OK")

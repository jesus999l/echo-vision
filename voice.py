"""
Voice — Vosk STT + Piper TTS.
"""
import os, sys, json, queue, threading, subprocess, tempfile

VOSK_MODEL_PATH = os.path.expanduser("~/vosk-model-small-en-us-0.15")
PIPER_BIN       = os.path.expanduser("~/piper/piper")
PIPER_MODEL     = os.path.expanduser("~/piper/models/en_US-lessac-medium.onnx")

_vosk_model = None

# ── AVAILABILITY ──────────────────────────────────────────────────────────────
def vosk_available():
    return os.path.exists(os.path.join(VOSK_MODEL_PATH, "am", "final.mdl"))

def piper_available():
    return os.path.exists(PIPER_BIN) and os.path.exists(PIPER_MODEL)

def tts_available():
    return piper_available() or (
        subprocess.run(["which", "espeak-ng"], capture_output=True).returncode == 0
    )

# ── STT ───────────────────────────────────────────────────────────────────────
def _load_vosk():
    global _vosk_model
    if _vosk_model is None:
        try:
            from vosk import Model
            _vosk_model = Model(VOSK_MODEL_PATH)
        except Exception as e:
            print(f"[voice] Vosk load error: {e}")
    return _vosk_model

def record_once(timeout=5, callback=None):
    """Record until silence or timeout, return transcribed text via callback."""
    try:
        import pyaudio
        from vosk import KaldiRecognizer
        model = _load_vosk()
        if not model:
            if callback: callback(None, "Vosk model not loaded")
            return
        rec    = KaldiRecognizer(model, 16000)
        pa     = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                         input=True, frames_per_buffer=4096)
        stream.start_stream()
        max_silence = int(timeout * 16000 / 4096)

        def _record():
            result_text  = ""
            silence_count = 0
            while silence_count < max_silence:
                data = stream.read(4096, exception_on_overflow=False)
                if rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "").strip()
                    if text:
                        result_text   = text
                        silence_count = max_silence
                else:
                    partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                    silence_count = 0 if partial else silence_count + 1
            stream.stop_stream(); stream.close(); pa.terminate()
            if callback: callback(result_text, None)

        threading.Thread(target=_record, daemon=True).start()
    except Exception as e:
        if callback: callback(None, str(e))

# ── TTS ───────────────────────────────────────────────────────────────────────
def speak(text, blocking=False):
    """Speak text with Piper TTS, fallback to espeak-ng."""
    if not piper_available():
        try:
            subprocess.Popen(["espeak-ng", "-s", "150", text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        return

    def _speak():
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
            proc = subprocess.run(
                [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", wav_path],
                input=text.encode(), capture_output=True
            )
            if proc.returncode == 0:
                subprocess.run(["aplay", "-q", wav_path],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.unlink(wav_path)
        except Exception as e:
            print(f"[voice] TTS error: {e}")

    if blocking:
        _speak()
    else:
        threading.Thread(target=_speak, daemon=True).start()

# ── STREAMING TTS ─────────────────────────────────────────────────────────────
_tts_queue   = queue.Queue()
_tts_started = False

def _tts_sentence(text):
    """Render and play one sentence, blocking."""
    text = text.strip()
    if not text: return
    if not piper_available():
        try:
            subprocess.run(["espeak-ng", "-s", "150", text],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        return
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        proc = subprocess.run(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", wav_path],
            input=text.encode(), capture_output=True
        )
        if proc.returncode == 0:
            subprocess.run(["aplay", "-q", wav_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.unlink(wav_path)
    except Exception as e:
        print(f"[voice] TTS error: {e}")

def _tts_worker():
    while True:
        item = _tts_queue.get()
        if item is None: break
        _tts_sentence(item)
        _tts_queue.task_done()

def _ensure_tts_worker():
    global _tts_started
    if not _tts_started:
        _tts_started = True
        threading.Thread(target=_tts_worker, daemon=True).start()

def speak_stream(sentence_iter):
    """Speak sentences from iterator as they arrive — first word in ~0.8s."""
    _ensure_tts_worker()
    def _feed():
        for s in sentence_iter:
            s = s.strip()
            if s:
                _tts_queue.put(s)
                # Write to Echo speech bubble
                try:
                    open("/tmp/echo_bubble.txt", "w").write(s)
                except Exception:
                    pass
        # Clear bubble after stream ends
        import time; time.sleep(6)
        try: open("/tmp/echo_bubble.txt", "w").write("")
        except: pass
    threading.Thread(target=_feed, daemon=True).start()

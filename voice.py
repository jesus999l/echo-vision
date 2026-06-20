#!/usr/bin/env python3
"""
Voice — Vosk STT + Piper TTS (unified sox pipeline on all paths).
"""
import os
import sys
import json
import queue
import threading
import subprocess
import tempfile
import time

VOSK_MODEL_PATH = os.path.expanduser("~/vosk-model-small-en-us-0.15")
PIPER_BIN       = os.path.expanduser("~/Echo/AI/Voices/piper/piper")
PIPER_MODEL     = os.path.expanduser("~/Echo/AI/Voices/piper/models/en_US-lessac-medium.onnx")

# Sox processing params — locked
SOX_PITCH    = "250"
SOX_RATE     = "18000"
SOX_OVERDRIVE = "2"
SOX_VOL      = "0.6"

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
            result_text   = ""
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

# ── CORE TTS (shared by all paths) ───────────────────────────────────────────
def _run_piper_sox(text: str):
    """
    Single canonical TTS pipeline: piper → sox (pitch/overdrive/vol) → aplay.
    Blocking. Raises on failure so callers can catch and fallback.
    """
    piper_proc = subprocess.Popen(
        [
            PIPER_BIN,
            "--model", PIPER_MODEL,
            "--output_raw",
            "--length_scale", "1.05",
            "--noise_scale", "1.10",
            "--noise_w", "1.20",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    sox_proc = subprocess.Popen(
        [
            "sox",
            "-t", "raw", "-r", "22050", "-e", "signed", "-b", "16", "-",
            "-t", "wav", "-",
            "pitch", SOX_PITCH,
            "rate", SOX_RATE,
            "overdrive", SOX_OVERDRIVE,
            "vol", SOX_VOL,
        ],
        stdin=piper_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    aplay_proc = subprocess.Popen(
        ["aplay", "-q", "-"],
        stdin=sox_proc.stdout,
        stderr=subprocess.DEVNULL,
    )
    piper_proc.stdin.write(text.encode())
    piper_proc.stdin.close()
    aplay_proc.wait()
    piper_proc.wait()
    sox_proc.wait()

def _espeak_fallback(text: str):
    subprocess.run(
        ["espeak-ng", "-v", "en-us+f2", "-s", "128", "-p", "60", "-a", "180", text[:200]],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

# ── PUBLIC speak() ────────────────────────────────────────────────────────────
def speak(text: str, blocking: bool = False):
    """
    Speak text through Piper+sox pipeline.
    blocking=True  → caller blocks until audio finishes (use in wake_word listen_loop)
    blocking=False → fires in background thread (use in echo_session daemon speaks)
    """
    if not piper_available():
        try:
            if blocking:
                _espeak_fallback(text)
            else:
                threading.Thread(target=_espeak_fallback, args=(text,), daemon=True).start()
        except Exception:
            pass
        return

    def _speak():
        try:
            _run_piper_sox(text)
        except Exception as e:
            print(f"[voice] TTS error: {e}")
            try:
                _espeak_fallback(text)
            except Exception:
                pass

    if blocking:
        _speak()
    else:
        threading.Thread(target=_speak, daemon=True).start()

# ── STREAMING TTS ─────────────────────────────────────────────────────────────
_tts_queue   = queue.Queue()
_tts_started = False

def _tts_sentence(text: str):
    """Render and play one sentence through the canonical Piper+sox pipeline."""
    text = text.strip()
    if not text:
        return
    if not piper_available():
        _espeak_fallback(text)
        return
    try:
        _run_piper_sox(text)
    except Exception as e:
        print(f"[voice] streaming TTS error: {e}")
        try:
            _espeak_fallback(text)
        except Exception:
            pass

def _tts_worker():
    while True:
        item = _tts_queue.get()
        if item is None:
            break
        _tts_sentence(item)
        _tts_queue.task_done()

def _ensure_tts_worker():
    global _tts_started
    if not _tts_started:
        _tts_started = True
        threading.Thread(target=_tts_worker, daemon=True).start()

def speak_stream(sentence_iter):
    """
    Speak sentences from iterator as they arrive.
    Updates bubble per sentence. Clears bubble after final sentence finishes playing.
    """
    _ensure_tts_worker()

    def _feed():
        last_sentence = ""
        for s in sentence_iter:
            s = s.strip()
            if s:
                last_sentence = s
                _tts_queue.put(s)
                try:
                    open("/tmp/echo_bubble.txt", "w").write(s)
                except Exception:
                    pass
        # Wait for queue to drain — actual audio done
        _tts_queue.join()
        try:
            open("/tmp/echo_bubble.txt", "w").write("")
        except Exception:
            pass

    threading.Thread(target=_feed, daemon=True).start()

"""
Push-to-Talk for Echo Desktop.
Hold Ctrl+Alt+Space → records while held → Whisper → route_command().
Runs as a background daemon thread.
"""
import os, sys, threading, tempfile, wave, time
sys.path.insert(0, os.path.expanduser("~/vision_assistant"))

PTT_KEY_COMBO = {'ctrl', 'alt', 'space'}   # all three must be held
def _get_mic_device():
    """Find pulse/pipewire input device dynamically."""
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
        for priority in ["pulse", "pipewire", "default", "sysdefault"]:
            for idx, name in devices:
                if priority in name:
                    return idx
        return devices[0][0] if devices else None
    except: return None

MIC_DEVICE = _get_mic_device()
SAMPLE_RATE   = 16000
CHUNK         = 1024
MAX_HOLD_SEC  = 30     # safety cutoff

_held_keys   = set()
_recording   = False
_rec_thread  = None
_frames      = []
_pa          = None

def _beep(freq=880, duration=0.08):
    """Short audio cue via paplay/beep, non-blocking."""
    try:
        import subprocess as _sp
        _sp.Popen(
            ["python3", "-c",
             f"import os; os.system('paplay --volume=40000 /usr/share/sounds/freedesktop/stereo/audio-volume-change.oga 2>/dev/null || beep -f {freq} -l {int(duration*1000)} 2>/dev/null')"],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except: pass

def _notify(msg):
    try:
        import subprocess as _sp
        _sp.Popen(["notify-send", "-t", "1500", "-u", "low",
                   "-a", "Echo PTT", "🎙 Echo PTT", msg],
                  stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except: pass

def _start_recording():
    global _recording, _frames, _pa
    import pyaudio
    _recording = True
    _frames = []
    _beep(880, 0.07)
    _notify("Listening...")
    try:
        _pa = pyaudio.PyAudio()
        stream = _pa.open(
            format=pyaudio.paInt16, channels=1,
            rate=SAMPLE_RATE, input=True,
            input_device_index=MIC_DEVICE,
            frames_per_buffer=CHUNK
        )
        start = time.time()
        while _recording and (time.time() - start) < MAX_HOLD_SEC:
            data = stream.read(CHUNK, exception_on_overflow=False)
            _frames.append(data)
        stream.stop_stream()
        stream.close()
        _pa.terminate()
        _pa = None
    except Exception as e:
        print(f"[ptt] record error: {e}")
        _recording = False

def _stop_and_transcribe():
    global _recording
    _recording = False
    _beep(660, 0.07)
    if not _frames:
        return

    # Write WAV
    tmp = tempfile.mktemp(prefix="echo_ptt_", suffix=".wav")
    try:
        with wave.open(tmp, 'wb') as wf:
            import pyaudio
            wf.setnchannels(1)
            wf.setsampwidth(2)  # paInt16 = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(_frames))
    except Exception as e:
        print(f"[ptt] wav error: {e}")
        return

    # Transcribe
    try:
        sys.path.insert(0, os.path.expanduser("~/vision_assistant"))
        from wake_word import _transcribe_whisper, route_command
        text = _transcribe_whisper(tmp)
        if text.strip():
            print(f"[ptt] command: {text!r}")
            _notify(f"Heard: {text}")
            route_command(text)
        else:
            _notify("Nothing heard.")
    except Exception as e:
        print(f"[ptt] transcribe error: {e}")
    finally:
        try: os.unlink(tmp)
        except: pass

def _on_press(key):
    global _rec_thread
    try:
        from pynput.keyboard import Key
        name = key.char if hasattr(key, 'char') and key.char else str(key).replace('Key.', '')
        _held_keys.add(name.lower())
        # Check if full combo held
        if PTT_KEY_COMBO.issubset(_held_keys) and not _recording:
            _rec_thread = threading.Thread(target=_start_recording, daemon=True)
            _rec_thread.start()
    except: pass

def _on_release(key):
    try:
        from pynput.keyboard import Key
        name = key.char if hasattr(key, 'char') and key.char else str(key).replace('Key.', '')
        _held_keys.discard(name.lower())
        # Release if any PTT key lifted while recording
        if _recording and not PTT_KEY_COMBO.issubset(_held_keys):
            threading.Thread(target=_stop_and_transcribe, daemon=True).start()
    except: pass

def start_ptt():
    """Start PTT keyboard listener in background."""
    try:
        from pynput import keyboard
        listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
        listener.daemon = True
        listener.start()
        print("[ptt] Push-to-talk ready — hold Ctrl+Alt+Space to speak.")
        return listener
    except ImportError:
        print("[ptt] pynput not installed — run: pip install pynput --break-system-packages")
        return None
    except Exception as e:
        print(f"[ptt] failed to start: {e}")
        return None

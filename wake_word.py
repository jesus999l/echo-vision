#!/usr/bin/env python3
import os
import sys
import json
import pathlib
from pathlib import Path
import threading
import datetime
import subprocess
import time
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer

SOUNDDEVICE_INDEX = 17
SAMPLE_RATE = 16000
BLOCK_SIZE = 4000
SILENCE_TIMEOUT = 2.0

def _log_to_vault(q: str, a: str):
    def _w():
        try:
            d = datetime.datetime.now().strftime('%Y-%m-%d')
            t = datetime.datetime.now().strftime('%H:%M:%S')
            vp = Path(f'~/Documents/ObsidianVault/Echo/Subconscious/{d}-voice.md').expanduser()
            vp.parent.mkdir(parents=True, exist_ok=True)
            with open(vp, 'a') as f:
                f.write(f'\n## {t}\n**Q:** {q}\n**A:** {a}\n')
        except Exception:
            pass
    threading.Thread(target=_w, daemon=True).start()

is_processing = False

def _stream_voice_response(q: str):
    global is_processing
    is_processing = True
    try:
        print(f'[bridge] routing vision: {q}')
        try:
            import requests as _req
            _r = _req.post('http://localhost:8769/ask',
                          json={'question': q, 'screen': any(w in q.lower() for w in ['screen','see','look','window','open','visible','desktop'])}, timeout=35)
            _rj = _r.json() if _r.ok else {}
            a = _rj.get('response', '') if _r.ok else None
            _vision_spoke = bool(_rj.get('actions_executed'))
            if not a:
                raise Exception('vision agent empty')
        except Exception as _ve:
            print(f'[bridge] vision fallback: {_ve}')
            try:
                from echo_ai_hub import ask as ask_text
                try:
                    from echo_kb_context import get_kb_context
                    kb = get_kb_context(q)
                except Exception:
                    kb = ""
                a = ask_text(q, kb_context=kb)
            except Exception as _e2:
                print(f'[bridge] ask error: {_e2}')
                a = 'Routing layer issue.'
        print(f'[bridge] response: {a[:60]}...')
        try:
            Path('/tmp/echo_bubble.txt').write_text(a[:280])
        except Exception:
            pass
        try:
            import voice
            voice.speak(a, blocking=True) if not locals().get("_vision_spoke") else None
        except Exception as e:
            print(f'[bridge] TTS error: {e}')
            if not locals().get('_vision_spoke'):
                p = subprocess.Popen(
                    ['espeak-ng', '-v', 'en-us+f2', '-s', '128', a[:200]],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                p.wait()
        _log_to_vault(q, a)
    finally:
        is_processing = False


_vosk_model_instance = None

def _ptt_trigger_loop():
    """Watch /tmp/echo_wake_trigger — PTT path into voice pipeline."""
    global _vosk_model_instance
    import time
    trigger = Path('/tmp/echo_wake_trigger')
    trigger.unlink(missing_ok=True)
    print('[ptt] Push-to-talk trigger loop online.')
    while True:
        if trigger.exists():
            try:
                trigger.unlink()
            except:
                pass
            if is_processing:
                time.sleep(0.1)
                continue
            print('[ptt] Trigger fired — recording...')
            try:
                Path('/tmp/echo_bubble.txt').write_text('[Listening...]')
            except:
                pass
            result = {'text': None, 'done': False}
            def _cb(text, err):
                result['text'] = text
                result['done'] = True
            # Record using sounddevice on device 17 (same as wake word)
            import sounddevice as _sd
            import numpy as _np
            from vosk import KaldiRecognizer as _KR
            _fs = 16000
            _dur = 6
            print('[ptt] recording on device 17...')
            try:
                _audio = _sd.rec(int(_dur * _fs), samplerate=_fs, channels=1,
                                  dtype='int16', device=SOUNDDEVICE_INDEX)
                _sd.wait()
                _raw = _audio.tobytes()
            except Exception as _e:
                print(f'[ptt] mic error: {_e}')
                _raw = b''
            # Transcribe with vosk
            _m = _vosk_model_instance
            if _m is None:
                time.sleep(0.5); continue
            _rec2 = _KR(_m, _fs)
            chunk = 4000
            for i in range(0, len(_raw), chunk * 2):
                _rec2.AcceptWaveform(_raw[i:i+chunk*2])
            import json as _json
            txt = _json.loads(_rec2.FinalResult()).get('text', '').strip()
            print(f'[ptt] transcript: {repr(txt)}')
            if txt:
                t = threading.Thread(target=_stream_voice_response, args=(txt,), daemon=True)
                t.start()
                t.join()
                try:
                    Path('/tmp/echo_bubble.txt').write_text('[Listening...]')
                except:
                    pass
        time.sleep(0.05)

def listen_loop():
    mp = os.path.expanduser('~/vision_assistant/models/vosk-model-small-en-us-0.15')
    if not os.path.exists(mp):
        print(f'Missing model: {mp}')
        return

    global _vosk_model_instance
    m = Model(mp)
    _vosk_model_instance = m
    r = KaldiRecognizer(m, SAMPLE_RATE)

    # Verify sounddevice index exists
    try:
        devs = sd.query_devices()
        if SOUNDDEVICE_INDEX >= len(devs):
            print(f'[listener] WARNING: device {SOUNDDEVICE_INDEX} not found, falling back to default input')
            dev_idx = None
        else:
            print(f'[listener] Using device {SOUNDDEVICE_INDEX}: {devs[SOUNDDEVICE_INDEX]["name"]}')
            dev_idx = SOUNDDEVICE_INDEX
    except Exception as e:
        print(f'[listener] Device query error: {e}, using default')
        dev_idx = None

    print('[listener] Echo Conscious Loop Online. Listening...')
    threading.Thread(target=_ptt_trigger_loop, daemon=True).start()
    accumulated_query = ""
    conversation_mode = False
    conversation_expires = 0
    last_phrase_time = time.time()

    def audio_callback(indata, frames, time_info, status):
        nonlocal accumulated_query, last_phrase_time
        if status:
            pass  # suppress overflow noise in logs

        # While Echo is processing/speaking, drain buffer silently
        if is_processing:
            r.AcceptWaveform(bytes(indata))  # drain — don't parse result
            return

        raw = bytes(indata)
        if r.AcceptWaveform(raw):
            txt = json.loads(r.Result()).get('text', '').strip()
            wake_words = ['hey echo', 'yo echo', 'ok echo']
            hit = next((w for w in wake_words if w in txt), None)

            if time.time() > conversation_expires:
                conversation_mode = False
            if hit or (conversation_mode and txt and not is_processing):
                phrase = txt.split(hit)[-1].strip()
                if phrase:
                    accumulated_query = (accumulated_query + ' ' + phrase).strip()
                    last_phrase_time = time.time()
            elif accumulated_query and txt:
                # Trailing sentence after wake word already captured
                accumulated_query = (accumulated_query + ' ' + txt).strip()
                last_phrase_time = time.time()

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        dtype='int16',
        channels=1,
        device=dev_idx,
        callback=audio_callback
    ):
        while True:
            time.sleep(0.05)

            if accumulated_query and not is_processing:
                elapsed = time.time() - last_phrase_time
                if elapsed > SILENCE_TIMEOUT:
                    final_q = accumulated_query.strip()
                    accumulated_query = ""
                    if final_q:
                        try:
                            Path('/tmp/echo_bubble.txt').write_text('[Thinking...]')
                        except Exception:
                            pass
                        print(f'[listener] dispatching: ' + repr(final_q))
                        conversation_mode = True
                        conversation_expires = time.time() + 30
                        t = threading.Thread(target=_stream_voice_response, args=(final_q,), daemon=True)
                        t.start()
                        t.join()  # block main loop until response+TTS complete
                        try:
                            Path('/tmp/echo_bubble.txt').write_text('[Listening...]')
                        except Exception:
                            pass

if __name__ == '__main__':
    try:
        listen_loop()
    except KeyboardInterrupt:
        print('\nExit.')

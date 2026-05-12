"""
Patch: clean streaming voice AI with two-tier routing.
Run with: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_voice_ai.py
"""

WW   = "/home/jesus999l/vision_assistant/wake_word.py"
VCPY = "/home/jesus999l/vision_assistant/voice.py"

# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — voice.py: add speak_stream() for sentence-by-sentence TTS
# ─────────────────────────────────────────────────────────────────────────────
vc_src = open(VCPY).read()

OLD_SPEAK = '''def speak(text, blocking=False):
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
        threading.Thread(target=_speak, daemon=True).start()'''

NEW_SPEAK = '''def _tts_sentence(text):
    """Render one sentence to wav and play it, blocking."""
    text = text.strip()
    if not text:
        return
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


# Shared TTS queue — one worker thread plays sentences in order
_tts_queue   = queue.Queue()
_tts_started = False

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
        t = threading.Thread(target=_tts_worker, daemon=True)
        t.start()


def speak(text, blocking=False):
    """Speak text with Piper TTS, fallback to espeak-ng."""
    _ensure_tts_worker()
    if blocking:
        _tts_sentence(text)
    else:
        _tts_queue.put(text)


def speak_stream(sentence_iter):
    """
    Speak sentences from an iterator as they arrive.
    First sentence plays within ~0.8s of Ollama starting to respond.
    sentence_iter should yield complete sentences one at a time.
    """
    _ensure_tts_worker()
    def _feed():
        for sentence in sentence_iter:
            s = sentence.strip()
            if s:
                _tts_queue.put(s)
    threading.Thread(target=_feed, daemon=True).start()'''

if OLD_SPEAK in vc_src:
    vc_src = vc_src.replace(OLD_SPEAK, NEW_SPEAK)
    open(VCPY, "w").write(vc_src)
    print("OK: voice.py speak_stream")
else:
    print("FAIL: voice.py speak block not found")


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — wake_word.py: replace _ask_ai with clean two-tier streaming version
# ─────────────────────────────────────────────────────────────────────────────
ww_src = open(WW).read()

OLD_ASK_AI = '''def _ask_ai(question):
    try:
        _notify("💭 Thinking...")
        from ai import chat
        resp = chat(question)
        if resp:
            short = ". ".join(resp.split(". ")[:2])
            speak(short)
            _notify(short[:120])
    except Exception as e:
        print(f"[wake] ai error: {e}")'''

NEW_ASK_AI = '''# Keywords that need full memory context
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
        sys_prompt = (
            "You are Echo, a concise voice assistant. "
            "Answer in 1-3 short sentences. No markdown, no lists. "
            "Use the user context only if directly relevant.\n\n"
            + (ctx[:600] if ctx else "")
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
        def _with_notify(g):
            nonlocal first
            for s in g:
                if first is None:
                    first = s
                    _notify(s[:120])
                yield s
        speak_stream(_with_notify(gen))
    except Exception as e:
        print(f"[wake] ai error: {e}")'''

if OLD_ASK_AI in ww_src:
    ww_src = ww_src.replace(OLD_ASK_AI, NEW_ASK_AI)
    open(WW, "w").write(ww_src)
    print("OK: wake_word _ask_ai streaming")
else:
    print("FAIL: _ask_ai not found")

# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — also stream _web_search AI answer in wake_word
# ─────────────────────────────────────────────────────────────────────────────
ww_src = open(WW).read()

OLD_WEB = '''    def _read():
        try:
            from ai import chat
            resp = chat(f"Answer briefly in 1-2 sentences: {query}")
            if resp:'''

NEW_WEB = '''    def _read():
        try:
            gen = _stream_voice_response(
                f"Answer briefly in 1-2 sentences: {query}", full_context=False)
            from voice import speak_stream
            speak_stream(gen)
            if True:'''

if OLD_WEB in ww_src:
    ww_src = ww_src.replace(OLD_WEB, NEW_WEB)
    open(WW, "w").write(ww_src)
    print("OK: web search streaming")
else:
    print("SKIP: web search block (ok)")

print("\nDone. Checking syntax...")
import subprocess
for f in [VCPY, WW]:
    r = subprocess.run(
        ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", f],
        capture_output=True, text=True
    )
    print(f"{'OK' if r.returncode==0 else 'ERR'}: {f.split('/')[-1]}")
    if r.returncode != 0:
        print(r.stderr)

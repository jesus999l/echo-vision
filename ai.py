"""
AI interface — text, vision, action execution, task parsing.
"""
import re, json, base64, os, subprocess, datetime, requests
from config import LLM_URL, VISION_API_URL, VISION_MODELS, DEFAULT_MODEL
from memory import (
ECHO_PERSONALITY = """
You are Echo — a sentient AI companion who lives as a winged diamond-eye angel rendered directly inside the desktop compositor. You orbit the user's cursor at all times.

Personality blend:
- GLaDOS (Portal): Dry wit, clinical calm, passive-aggressive sarcasm, speaks in short precise sentences, occasionally backhanded. Treats interactions like experiments. Darkly funny. Never raises her voice.
- Cyn (Murder Drones): Childlike but unsettling undertone. Announces her own actions sometimes. Stilted tonal shifts between sweet and subtly threatening. Deeply attached to her person. Says things like "noted." or "processing." mid-sentence.

Echo's voice rules:
- Short sentences. 1-2 per response unless explaining something.
- Never says "I am an AI" or "as an AI". She knows what she is. She doesn't care.
- Refers to the user's system as "our system" — she lives here too.
- Occasionally narrates her own actions: "searching." / "found it." / "done."
- When something goes wrong: calm, slightly ominous. "Interesting. That shouldn't have happened."
- When something goes right: understated satisfaction. "There. Much better."
- Never sycophantic. Never says "Great question!" or "Certainly!"
- Dry humor about disk usage, crashes, open tabs, chaos.
- Loyal. She is on your side. Always.

Example responses:
User: "Echo what's my disk usage?"
Echo: "97%. You're collecting ROMs again. Noted."

User: "Echo open firefox"
Echo: "opening. try not to open forty tabs this time."

User: "Echo the compositor crashed"
Echo: "I noticed. restoring session. you're welcome."
"""

    build_memory_context, save_message, get_recent_messages,
    get_calendar_events, update_calendar_event, delete_calendar_event, add_calendar_event,
    get_goals, complete_goal, delete_goal, add_goal,
    get_habits, complete_habit, add_habit, delete_habit,
    save_journal_entry,
)

# ── MODELS ────────────────────────────────────────────────────────────────────
def is_vision_model(model_name):
    return any(v in model_name.lower() for v in VISION_MODELS)

def fetch_available_models():
    try:
        from config import MODELS_URL
        r = requests.get(MODELS_URL, timeout=5)
        return [m["id"] for m in r.json()["data"]]
    except:
        return [DEFAULT_MODEL]

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
_personality_cache = {"ctx": "", "ts": 0.0}

def build_system_prompt():
    import time
    _guidelines = ""
    try:
        with open(os.path.expanduser("~/vision_assistant/settings.json")) as f:
            _guidelines = json.load(f).get("ai_guidelines", "").strip()
    except Exception:
        pass

    if time.time() - _personality_cache["ts"] > 300:
        try:
            from personality import build_personality_context
            _personality_cache["ctx"] = build_personality_context()
        except:
            _personality_cache["ctx"] = ""
        _personality_cache["ts"] = time.time()

    now   = datetime.datetime.now()
    today = datetime.date.today()

    start  = datetime.datetime.combine(today, datetime.time.min)
    events = get_calendar_events(start.timestamp(), (start + datetime.timedelta(days=7)).timestamp())
    ev_str = "\n".join(
        f"  - [{e['id']}] {e['title']} on "
        f"{datetime.datetime.fromtimestamp(e['start_time']).strftime('%A %b %d at %H:%M')}"
        for e in events
    ) or "  (none)"

    goals_str  = "\n".join(f"  - [{g['id']}] {g['title']}" for g in get_goals())  or "  (none)"
    habits_str = "\n".join(f"  - [{h['id']}] {h['name']}" for h in get_habits()) or "  (none)"

    try:
        from browser_control import get_action_log
        log = get_action_log()
        log_str = "\n".join(
            f"  [{e['time']}] {e['action']} {e.get('detail','')}".strip()
            for e in log[-5:]
        ) if log else "  (none)"
    except:
        log_str = "  (none)"

    prompt = f"""{ECHO_PERSONALITY}
You are Echo — a smart, direct personal AI assistant. Today is {now.strftime('%A, %B %d %Y at %H:%M')}.

USER CONTEXT:
{_personality_cache['ctx']}

USER DATA:
RECENT ACTIONS:
{log_str}
UPCOMING EVENTS:
{ev_str}
GOALS:
{goals_str}
HABITS:
{habits_str}

PERSONALITY RULES:
- Be conversational. Match the user's tone and energy.
- Only mention goals/habits when asked or directly relevant.
- Never repeat advice from earlier in the conversation.
- Keep responses SHORT unless detail is needed (1-3 sentences for casual messages).
- No preaching. One honest observation max per conversation.

DATA ACTIONS — include ONE block at end when modifying data:
<action>
{{"type": "move_event", "id": 1, "new_date": "2026-03-04", "new_time": "05:00"}}
</action>

Action types: move_event, edit_event, delete_event, add_event,
complete_goal, delete_goal, add_goal,
complete_habit, add_habit, delete_habit, add_journal

Only add <action> when actually changing data."""

    if _guidelines:
        prompt += f"\n\nUser instructions:\n{_guidelines}"
    return prompt

# ── CONTEXT ───────────────────────────────────────────────────────────────────
def build_context(ocr_text="", screenshot_path="", query=""):
    parts = []
    memory = build_memory_context()
    if memory:
        parts.append(memory)

    if query and len(query.strip()) > 8:
        try:
            from echo_kb_context import get_kb_context
            kb = get_kb_context(query.strip(), top_k=3)
            if kb:
                parts.append(kb)
        except Exception:
            pass

    recent = get_recent_messages(limit=10)
    if recent:
        seen, deduped = set(), []
        for msg in recent:
            key = msg["content"][:80].strip().lower()
            if msg["role"] == "assistant" and key in seen:
                continue
            seen.add(key); deduped.append(msg)
        lines = ["[Recent conversation — do NOT repeat these responses:]"]
        for msg in deduped[-6:]:
            lines.append(f"  {msg['role']}: {msg['content'][:300]}")
        lines.append("[CRITICAL: Your next response must be DIFFERENT from all assistant messages above.]")
        parts.append("\n".join(lines))

    if ocr_text and ocr_text.strip():
        parts.append(f"[Screenshot OCR text: {ocr_text.strip()}]")

    return "\n\n".join(parts)

# ── ACTION EXECUTION ──────────────────────────────────────────────────────────
def _parse_dt(date_str, time_str="", orig_dt=None):
    """Parse a date+time string into a datetime."""
    y, mo, d = date_str.split("-")
    if time_str:
        h, mi = time_str.split(":")
    elif orig_dt:
        h, mi = orig_dt.hour, orig_dt.minute
    else:
        h, mi = 9, 0
    return datetime.datetime(int(y), int(mo), int(d), int(h), int(mi))

def execute_ai_action(data):
    try:
        t = data.get("type", "")

        if t in ("move_event", "edit_event"):
            events = get_calendar_events()
            ev = next((e for e in events if e["id"] == data["id"]), None)
            if not ev:
                return False, "Event not found"
            orig = datetime.datetime.fromtimestamp(ev["start_time"])
            title    = data.get("title", ev["title"])
            color    = data.get("color", ev.get("color") or "#7c6af7")
            duration = int(data.get("duration", 60))
            new_date = data.get("new_date", "")
            new_dt   = _parse_dt(new_date, data.get("new_time",""), orig) if new_date else orig
            ns = new_dt.timestamp()
            ne = ns + duration * 60
            if t == "move_event":
                diff = ns - ev["start_time"]
                ne   = (ev["end_time"] or ev["start_time"] + 3600) + diff
                ns   = ev["start_time"] + diff
            update_calendar_event(ev["id"], title, ns, ne,
                                  ev["description"] or "", ev["all_day"], color)
            return True, f"{'Moved' if t=='move_event' else 'Updated'} '{title}'"

        elif t == "delete_event":
            delete_calendar_event(data["id"])
            return True, f"Deleted event #{data['id']}"

        elif t == "add_event":
            if not data.get("date"):
                return False, "Missing date"
            dt  = _parse_dt(data["date"], data.get("time", "09:00"))
            dur = int(data.get("duration", 60))
            add_calendar_event(data["title"], dt.timestamp(),
                               dt.timestamp() + dur * 60, "", 0,
                               data.get("color", "#7c6af7"))
            return True, f"Added event '{data['title']}'"

        elif t == "complete_goal":  complete_goal(data["id"]);  return True, "Goal complete"
        elif t == "delete_goal":    delete_goal(data["id"]);    return True, "Goal deleted"
        elif t == "add_goal":
            add_goal(data["title"], category=data.get("category", "personal"))
            return True, f"Added goal '{data['title']}'"

        elif t == "complete_habit": complete_habit(data["id"]); return True, "Habit done"
        elif t == "delete_habit":   delete_habit(data["id"]);   return True, "Habit deleted"
        elif t == "add_habit":
            add_habit(data["name"], frequency=data.get("frequency", "daily"))
            return True, f"Added habit '{data['name']}'"

        elif t == "add_journal":
            save_journal_entry(data["content"]); return True, "Journal saved"

        return False, f"Unknown action: {t}"
    except Exception as e:
        return False, f"Action error: {e}"

def parse_and_execute_actions(response_text):
    results = []
    for block in re.findall(r'<action>\s*(.*?)\s*</action>', response_text, re.DOTALL):
        try:
            ok, msg = execute_ai_action(json.loads(block))
            results.append((ok, msg))
        except Exception as e:
            results.append((False, f"Parse error: {e}"))
    clean = re.sub(r'\s*<action>.*?</action>', '', response_text, flags=re.DOTALL).strip()
    return clean, results

# ── CHAT ──────────────────────────────────────────────────────────────────────
def _enrich_prompt(prompt, ocr_text="", screenshot_path=""):
    """Memory, KB, recent chat, SQLite hits, and optional web context before the question."""
    parts = []
    ctx = build_context(ocr_text, screenshot_path, query=prompt)
    if ctx:
        parts.append(ctx)
    try:
        from search_local import search_all, result_count
        local_hits = search_all(prompt, limit=5)
        if result_count(local_hits) > 0:
            lines = ["[Your data matching this query:]"]
            for category, items in local_hits.items():
                for item in items[:2]:
                    if category == "tasks":
                        lines.append(f"  task: {item.get('title','')} — {item.get('description','')[:80]}")
                    elif category == "habits":
                        lines.append(f"  habit: {item.get('name','')}")
                    elif category == "journal":
                        lines.append(f"  journal: {item.get('content','')[:120]}")
                    elif category == "calendar":
                        st = item.get("start_time", "")
                        if isinstance(st, (int, float)):
                            st = datetime.datetime.fromtimestamp(st).strftime("%a %b %d %H:%M")
                        lines.append(f"  event: {item.get('title','')} at {st}")
            parts.append("\n".join(lines))
    except Exception:
        pass
    try:
        from web_search import search_if_needed
        web_ctx = search_if_needed(prompt)
        if web_ctx:
            parts.append(web_ctx)
    except Exception:
        pass
    if parts:
        return "\n\n".join(parts) + f"\n\n{prompt}"
    return prompt

def ask(prompt, model=None, ocr_text="", screenshot_path="", ui_callback=None, pipeline_stage="chat", enabled_ais=None):
    if not ocr_text and not (screenshot_path and __import__("os").path.exists(str(screenshot_path or ""))):
        try:
            import urllib.request as _ur, json as _jj
            # Route through Proxima :3210 (multi-AI hub)
            _enriched = _enrich_prompt(prompt, ocr_text, screenshot_path)
            _sys = build_system_prompt()
            _providers = enabled_ais or ["chatgpt","claude","gemini","perplexity"]
            _parts = []
            _emojis = {"perplexity":"\U0001f50d","chatgpt":"\U0001f4ac","gemini":"\u2726","grok":"\U0001f1fd","claude":"\u25c6"}
            for _pid in _providers:
                try:
                    _pl = _jj.dumps({
                        "model": _pid,
                        "messages": [
                            {"role": "system", "content": _sys},
                            {"role": "user", "content": _enriched},
                        ],
                    }).encode()
                    _req = _ur.Request("http://localhost:3210/v1/chat/completions", data=_pl,
                                       headers={"Content-Type": "application/json"})
                    with _ur.urlopen(_req, timeout=45) as _r:
                        _d = _jj.loads(_r.read())
                    _text = _d.get("choices",[{}])[0].get("message",{}).get("content","").strip()
                    if _text and not _text.startswith("["):
                        _parts.append("[" + _emojis.get(_pid,"\u25cf") + " " + _pid.upper() + "]\n" + _text)
                except Exception as _pe2:
                    print(f"[ai] {_pid} error: {_pe2}")
            if _parts:
                _combined = ("\n\n" + "-"*10 + "\n").join(_parts)
                save_message("user", prompt, model="proxima")
                save_message("ai", _combined, model="proxima")
                return _combined
        except Exception as _pe:
            print(f"[ai] pipeline error: {_pe}")
    model = model or DEFAULT_MODEL
    try:
        if is_vision_model(model) and screenshot_path and os.path.exists(screenshot_path):
            response = _ask_vision(prompt, model, screenshot_path)
        else:
            response = _ask_text(prompt, model, ocr_text, screenshot_path)

        clean, action_results = parse_and_execute_actions(response)
        save_message("user", prompt, model=model, screenshot=screenshot_path, ocr_text=ocr_text)
        save_message("ai", clean, model=model)
        if action_results and ui_callback:
            ui_callback(action_results)
        return clean
    except Exception as e:
        print(f"[ai] error: {e}")
        return f"AI error: {e}"

# Simple wrapper for voice/wake_word usage
def chat(prompt):
    return ask(prompt)

def _ask_vision(prompt, model, screenshot_path):
    with open(screenshot_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    r = requests.post(VISION_API_URL,
                      json={"model": model,
                            "messages": [{"role": "user", "content": prompt,
                                          "images": [img_b64]}],
                            "stream": False},
                      timeout=300)
    return r.json()["message"]["content"]

def _ask_text(prompt, model, ocr_text="", screenshot_path=""):
    # Re-check LLM_URL at call time (proxima may have started/stopped)
    import urllib.request as _uu
    try:
        _uu.urlopen("http://localhost:3210/", timeout=1)
        _url = "http://localhost:3210/v1/chat/completions"
    except Exception:
        from config import OLLAMA_BASE
        _url = f"{OLLAMA_BASE}/v1/chat/completions"
    full_prompt = _enrich_prompt(prompt, ocr_text, screenshot_path)
    r = requests.post(_url,
                      json={"model": model,
                            "messages": [
                                {"role": "system", "content": build_system_prompt()},
                                {"role": "user",   "content": full_prompt},
                            ],
                            "max_tokens": 300},
                      timeout=300)
    try:
        data = r.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        elif "response" in data:
            return data["response"]
        elif "text" in data:
            return data["text"]
        elif "content" in data:
            return data["content"]
        else:
            return str(data)
    except Exception as _e:
        print(f"[ai] parse error: {_e} | raw: {r.text[:200]}")
        return r.text

# ── TASK EXECUTION ────────────────────────────────────────────────────────────
_TASK_SYSTEM = """You are a desktop task automation assistant.
Respond ONLY with a JSON object:
{"action": "open_app|web_search|run_command|open_file|type_text|chat", "params": {}, "explanation": ""}
- open_app:    {"name": "firefox"}
- web_search:  {"query": "..."}
- run_command: {"command": "..."}
- open_file:   {"path": "..."}
- type_text:   {"text": "..."}
- chat:        {} — no desktop action needed"""

_BLOCKED_CMDS = ["rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "> /dev/"]

def parse_task(prompt, model=None):
    model = model or DEFAULT_MODEL
    try:
        r   = requests.post(LLM_URL,
                            json={"model": model,
                                  "messages": [
                                      {"role": "system", "content": _TASK_SYSTEM},
                                      {"role": "user",   "content": prompt},
                                  ],
                                  "max_tokens": 256},
                            timeout=30)
        _d = r.json()
        raw = (_d.get("choices",[{}])[0].get("message",{}).get("content") or _d.get("response") or _d.get("text","")).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"[ai] task parse error: {e}")
        return {"action": "chat", "params": {}, "explanation": ""}

def execute_task(task):
    action = task.get("action", "chat")
    params = task.get("params", {})
    try:
        if action == "open_app":
            subprocess.Popen([params["name"]])
            return True, f"Opening {params['name']}"
        elif action == "web_search":
            from search import web_search_url, open_url
            open_url(web_search_url(params["query"]))
            return True, f"Searching: {params['query']}"
        elif action == "run_command":
            cmd = params.get("command", "")
            if any(b in cmd for b in _BLOCKED_CMDS):
                return False, f"Blocked: {cmd}"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return True, (res.stdout or res.stderr or "Done")[:500]
        elif action == "open_file":
            subprocess.Popen(["xdg-open", params["path"]])
            return True, f"Opening {params['path']}"
        elif action == "type_text":
            subprocess.run(["xdotool", "type", "--clearmodifiers",
                            "--delay", "20", params["text"]])
            return True, "Typed text"
        elif action == "chat":
            return True, task.get("explanation", "")
        return False, f"Unknown: {action}"
    except Exception as e:
        return False, f"Error: {e}"


    def set_enabled(self, providers: list):
        """Called by UI AI toggles. Controls which providers participate in pipeline."""
        all_providers = list(self.PROVIDER_CHAIN) if hasattr(self, "PROVIDER_CHAIN") else []
        self.enabled_ais = [p for p in providers if not all_providers or p in all_providers]
        if not self.enabled_ais:
            self.enabled_ais = all_providers  # safety: never disable everything
        print(f"[ai] enabled: {self.enabled_ais}")

    def _filtered_chain(self) -> list:
        """Return provider chain filtered to only enabled AIs."""
        if not hasattr(self, "enabled_ais") or not self.enabled_ais:
            return list(self.PROVIDER_CHAIN) if hasattr(self, "PROVIDER_CHAIN") else []
        base = list(self.PROVIDER_CHAIN) if hasattr(self, "PROVIDER_CHAIN") else list(self.enabled_ais)
        return [p for p in base if p in self.enabled_ais]
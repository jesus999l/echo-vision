"""
AI interface — text, vision, action execution, task parsing.
"""
import re, json, base64, os, subprocess, datetime, requests
from config import LLM_URL, VISION_API_URL, VISION_MODELS, DEFAULT_MODEL

try:
    from event_router import router as _router
except ImportError:
    _router = None
from memory import (
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

# ── INTEGRATION SINGLETONS (set by main.py at startup) ──────────────────────
_obsidian_bridge = None   # ObsidianBridge instance
_web_searcher    = None   # WebSearch instance

def set_obsidian_bridge(bridge):
    global _obsidian_bridge
    _obsidian_bridge = bridge

def set_web_searcher(searcher):
    global _web_searcher
    _web_searcher = searcher

def build_system_prompt():
    import time
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

    return f"""You are a smart, direct personal AI assistant. Today is {now.strftime('%A, %B %d %Y at %H:%M')}.

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

Only add <action> when actually changing data.""" + _vault_context_block()

def _vault_context_block() -> str:
    """Return Obsidian vault context string for prompt injection, or ''."""
    if _obsidian_bridge is None:
        return ""
    try:
        # Use last user message from recent history as query if available
        recent = get_recent_messages(limit=1)
        query  = recent[-1]["content"] if recent else ""
        ctx    = _obsidian_bridge.get_context_for_query(query, max_chars=1200)
        if ctx:
            return f"\n\nOBSIDIAN VAULT CONTEXT:\n{ctx}"
    except Exception as e:
        pass
    return ""

# ── CONTEXT ───────────────────────────────────────────────────────────────────
    if _guidelines:
        prompt += f"\n\nUser instructions:\n{_guidelines}"
    return prompt
def build_context(ocr_text="", screenshot_path=""):
    parts = []
    memory = build_memory_context()
    if memory:
        parts.append(memory)

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
        if _router:
            _router.activate("TASKS", 75)
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
    finally:
        if _router:
            _router.idle("TASKS")

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
def ask(prompt, model=None, ocr_text="", screenshot_path="", ui_callback=None):
    model = model or DEFAULT_MODEL
    if _router:
        _router.activate("LLM", 85)
        _router.activate("ROUTER", 70)
        _router.activate("CONTEXT", 60)
        _router.set_thought(prompt[:80])
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
    finally:
        if _router:
            _router.idle("LLM")
            _router.standby("ROUTER", 25)
            _router.standby("CONTEXT", 20)

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
    context     = build_context(ocr_text, screenshot_path)
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    # ── Web search injection ────────────────────────────────────────────────
    sys_prompt = build_system_prompt()
    try:
        if _web_searcher is not None:
            from web_search import needs_web_search
            if needs_web_search(prompt):
                result = _web_searcher.search(prompt)
                web_ctx = result.to_prompt_block(max_results=4)
                if web_ctx:
                    sys_prompt += f"\n\nWEB SEARCH RESULTS:\n{web_ctx}"
    except Exception:
        pass
    # ── end web search ───────────────────────────────────────────────────────
    r = requests.post(LLM_URL,
                      json={"model": model,
                            "messages": [
                                {"role": "system", "content": sys_prompt},
                                {"role": "user",   "content": full_prompt},
                            ],
                            "max_tokens": 300},
                      timeout=300)
    return r.json()["choices"][0]["message"]["content"]

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
        raw = r.json()["choices"][0]["message"]["content"].strip()
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

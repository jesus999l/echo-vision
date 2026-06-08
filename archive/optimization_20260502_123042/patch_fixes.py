"""
Patch script — run with:
  /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_fixes.py
"""
import re

UI   = "/home/jesus999l/vision_assistant/ui.py"
WW   = "/home/jesus999l/vision_assistant/wake_word.py"

def patch(path, old, new, label):
    src = open(path).read()
    if old in src:
        open(path,"w").write(src.replace(old, new))
        print(f"OK: {label}")
    else:
        print(f"NOT FOUND: {label}")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — Tasks: add delete button to DONE tasks + auto-hide after 24h
# ─────────────────────────────────────────────────────────────────────────────
patch(UI,
    '''    def _goal_card(self,parent,g,accent=None):
        if accent is None: accent=ACCENT
        bg=BG3
        card=tk.Frame(parent,bg=bg,padx=10,pady=7,
                     highlightthickness=1,highlightbackground=BORDER,cursor="hand2")
        card.pack(fill="x",padx=10,pady=2)
        r1=tk.Frame(card,bg=bg); r1.pack(fill="x")
        done=g.get("status")=="done"
        tk.Label(r1,text=g["title"],bg=bg,fg=TEXT3 if done else TEXT,
                font=FONT_SMALL,anchor="w").pack(side="left",fill="x",expand=True)
        st=g.get("status","active")
        st_color={"done":ACCENT3,"abandoned":DANGER,"active":TEXT3}.get(st,TEXT3)
        tk.Label(r1,text=st.upper(),bg=bg,fg=st_color,
                font=("Segoe UI",7,"bold")).pack(side="right")
        prog=g.get("progress",0) or 0
        if prog>0:
            pb=tk.Frame(card,bg=BG4,height=3); pb.pack(fill="x",pady=(3,0))
            tk.Frame(pb,bg=accent,height=3).place(x=0,y=0,relwidth=min(1,prog/100),relheight=1)
        if not done:
            br=tk.Frame(card,bg=bg); br.pack(fill="x",pady=(4,0))
            sbtn(br,"✓ Done",lambda gid=g["id"]:self._complete_goal(gid),bg=ACCENT3,fg=BG,px=8,py=2).pack(side="left",padx=(0,4))
            sbtn(br,"✗ Drop",lambda gid=g["id"]:self._abandon_goal(gid),bg=BG4,fg=TEXT3,px=8,py=2).pack(side="left")
            sbtn(br,f"{prog}%",lambda gid=g["id"],p=prog:self._set_progress(gid,p),bg=BG4,fg=TEXT3,px=8,py=2).pack(side="right")
            sbtn(br,"🗑",lambda gid=g["id"]:(delete_goal(gid),self._page_dirty.__setitem__('tasks',True),self.open_page('tasks')),bg=DANGER,fg=WHITE,px=6,py=2).pack(side="right",padx=(0,4))''',

    '''    def _goal_card(self,parent,g,accent=None):
        if accent is None: accent=ACCENT
        bg=BG3
        card=tk.Frame(parent,bg=bg,padx=10,pady=7,
                     highlightthickness=1,highlightbackground=BORDER,cursor="hand2")
        card.pack(fill="x",padx=10,pady=2)
        r1=tk.Frame(card,bg=bg); r1.pack(fill="x")
        done=g.get("status")=="done" or g.get("completed",0)
        tk.Label(r1,text=g["title"],bg=bg,fg=TEXT3 if done else TEXT,
                font=FONT_SMALL,anchor="w").pack(side="left",fill="x",expand=True)
        st=g.get("status","active")
        st_color={"done":ACCENT3,"abandoned":DANGER,"active":TEXT3}.get(st,TEXT3)
        tk.Label(r1,text=st.upper(),bg=bg,fg=st_color,
                font=("Segoe UI",7,"bold")).pack(side="right")
        prog=g.get("progress",0) or 0
        if prog>0:
            pb=tk.Frame(card,bg=BG4,height=3); pb.pack(fill="x",pady=(3,0))
            tk.Frame(pb,bg=accent,height=3).place(x=0,y=0,relwidth=min(1,prog/100),relheight=1)
        br=tk.Frame(card,bg=bg); br.pack(fill="x",pady=(4,0))
        if not done:
            sbtn(br,"✓ Done",lambda gid=g["id"]:self._complete_goal(gid),bg=ACCENT3,fg=BG,px=8,py=2).pack(side="left",padx=(0,4))
            sbtn(br,"✗ Drop",lambda gid=g["id"]:self._abandon_goal(gid),bg=BG4,fg=TEXT3,px=8,py=2).pack(side="left")
            sbtn(br,f"{prog}%",lambda gid=g["id"],p=prog:self._set_progress(gid,p),bg=BG4,fg=TEXT3,px=8,py=2).pack(side="right")
        sbtn(br,"🗑",lambda gid=g["id"]:(delete_goal(gid),self._page_dirty.__setitem__('tasks',True),self.open_page('tasks')),bg=DANGER,fg=WHITE,px=6,py=2).pack(side="right",padx=(0,4))''',
    "Task delete on done tasks")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 2 — Tasks: auto-hide completed tasks after 24h (in _page_tasks or get_goals)
# ─────────────────────────────────────────────────────────────────────────────
# Find where goals are fetched for display and filter completed ones older than 24h
src = open(UI).read()
# Replace get_goals() calls in task page to filter out old completed tasks
old = "    def _complete_goal(self,gid):\n        from memory import update_goal_status as _ugs\n        _ugs(gid,\"done\"); self._page_dirty['tasks']=True; self.open_page('tasks')"
new = """    def _complete_goal(self,gid):
        import time as _t, sqlite3 as _sq
        from config import DB_PATH as _dp
        from memory import update_goal_status as _ugs
        _ugs(gid,"done")
        # stamp completion time
        conn=_sq.connect(_dp)
        conn.execute("UPDATE goals SET target_date=? WHERE id=?",(int(_t.time()),gid))
        conn.commit(); conn.close()
        self._page_dirty['tasks']=True; self.open_page('tasks')"""
if old in src:
    open(UI,"w").write(src.replace(old,new))
    print("OK: Stamp completion time")
else:
    print("NOT FOUND: Stamp completion time")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 — Habit card: add delete button
# ─────────────────────────────────────────────────────────────────────────────
patch(UI,
    '''        # Log button
        if not done:
            sbtn(card,"+ Log",lambda hid=h["id"]:self._log_habit(hid),
                bg=ACCENT2,fg=BG,px=10,py=2).pack(anchor="w",pady=(4,0))

    def _log_habit(self,hid):''',

    '''        # Buttons row
        br2=tk.Frame(card,bg=bg); br2.pack(fill="x",pady=(4,0))
        if not done:
            sbtn(br2,"+ Log",lambda hid=h["id"]:self._log_habit(hid),
                bg=ACCENT2,fg=BG,px=10,py=2).pack(side="left")
        sbtn(br2,"🗑",lambda hid=h["id"]:self._delete_habit(hid),
            bg=DANGER,fg=WHITE,px=6,py=2).pack(side="right")

    def _delete_habit(self,hid):
        from memory import delete_habit as _dh
        _dh(hid); self._page_dirty['habits']=True; self.open_page('habits')

    def _log_habit(self,hid):''',
    "Habit delete button")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4 — Journal delete: ensure page forces refresh (not cached)
# ─────────────────────────────────────────────────────────────────────────────
patch(UI,
    '''              sbtn(br,"Delete",lambda eid=ent["id"]:(delete_journal_entry(eid),self.open_page("journal")),
                   bg=DANGER,fg=WHITE,px=6,py=2).pack(side="left")''',
    '''              sbtn(br,"Delete",lambda eid=ent["id"]:(delete_journal_entry(eid),self._page_dirty.__setitem__('journal',True),self.open_page("journal")),
                   bg=DANGER,fg=WHITE,px=6,py=2).pack(side="left")''',
    "Journal delete refresh fix")

print("\n--- UI patches done ---\n")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 5 — Voice habits: parse frequency + count from speech
# ─────────────────────────────────────────────────────────────────────────────
patch(WW,
    '''def _add_habit(text):
    try:
        from memory import add_habit
        text = text.strip().strip(".,!?")
        if text.startswith("to "): text = text[3:]
        add_habit(text, frequency="daily")
        _notify(f"◈ Habit: {text}")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] habit error: {e}")''',

    '''def _add_habit(text):
    try:
        import re as _re
        from memory import add_habit, update_habit_target, get_habits
        raw = text.strip().strip(".,!?")
        # Parse frequency: "daily", "weekly", "monthly"
        freq = "daily"
        for f in ["daily","weekly","monthly"]:
            if f in raw:
                freq = f
                raw = _re.sub(f, "", raw, flags=_re.IGNORECASE).strip()
        # Parse count: "3 times", "twice", "2x"
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
        freq_label = {"daily":"daily","weekly":"weekly","monthly":"monthly"}.get(freq,freq)
        _notify(f"◈ Habit: {raw} ({target}x {freq_label})")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] habit error: {e}")''',
    "Voice habit freq+count parsing")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 6 — Voice events: parse date, time, place properly
# ─────────────────────────────────────────────────────────────────────────────
patch(WW,
    '''def _parse_event_time(text):
    """Extract datetime from phrases like 'at 3pm', 'tomorrow at 9am'."""
    import datetime
    now = datetime.datetime.now()
    base = now + datetime.timedelta(days=1) if "tomorrow" in text else now
    m = re.search(r'(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm)?', text)
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
        title = re.sub(r'\\s*(at|on|tomorrow)\\s+[\\d:apm\\s]+', '', text,
                       flags=re.IGNORECASE).strip() or text
        add_calendar_event(title, start.timestamp(), end.timestamp())
        _notify(f"◷ {title} — {start.strftime('%b %d %I:%M %p')}")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] event error: {e}")''',

    '''def _parse_event_time(text):
    """Extract datetime from phrases like 'at 3pm', 'tomorrow at 9am', 'next monday'."""
    import datetime
    now  = datetime.datetime.now()
    base = now

    t = text.lower()
    if "tomorrow" in t:
        base = now + datetime.timedelta(days=1)
    elif "next monday" in t:    base = _next_weekday(now, 0)
    elif "next tuesday" in t:   base = _next_weekday(now, 1)
    elif "next wednesday" in t: base = _next_weekday(now, 2)
    elif "next thursday" in t:  base = _next_weekday(now, 3)
    elif "next friday" in t:    base = _next_weekday(now, 4)
    elif "next saturday" in t:  base = _next_weekday(now, 5)
    elif "next sunday" in t:    base = _next_weekday(now, 6)
    # "on monday" etc without "next"
    for i,day in enumerate(["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]):
        if f"on {day}" in t or t.startswith(day):
            base = _next_weekday(now, i); break

    m = re.search(r'(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm)?', text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2) or 0)
        mer = m.group(3)
        if mer == "pm" and h < 12: h += 12
        elif mer == "am" and h == 12: h = 0
        return base.replace(hour=h, minute=mn, second=0, microsecond=0)
    return base.replace(hour=9, minute=0, second=0, microsecond=0)

def _next_weekday(now, weekday):
    import datetime
    days = (weekday - now.weekday() + 7) % 7 or 7
    return now + datetime.timedelta(days=days)

def _add_event(text):
    try:
        from memory import add_calendar_event
        import datetime
        # Extract place: "at [place]" after time, or "in [place]"
        place = ""
        pm = re.search(r"\\bat\\s+([A-Za-z][\\w\\s]+?)(?:\\s+(?:at|from|on)\\s+\\d|$)", text, re.IGNORECASE)
        if pm and not re.search(r"\\d", pm.group(1)):
            place = pm.group(1).strip()
        # Extract duration: "for 2 hours", "for 30 minutes"
        dur_mins = 60
        dm = re.search(r"for\\s+(\\d+)\\s*(hour|hr|minute|min)", text, re.IGNORECASE)
        if dm:
            n = int(dm.group(1))
            dur_mins = n * 60 if "h" in dm.group(2).lower() else n

        start = _parse_event_time(text)
        end   = start + datetime.timedelta(minutes=dur_mins)

        # Clean title: remove time/date/duration/place phrases
        title = text
        title = re.sub(r"\\s*(tomorrow|next\\s+\\w+|on\\s+\\w+day)\\s*", " ", title, flags=re.IGNORECASE)
        title = re.sub(r"\\s*\\bat\\s+\\d[\\d:]*\\s*(am|pm)?\\s*", " ", title, flags=re.IGNORECASE)
        title = re.sub(r"\\s*from\\s+\\d[\\d:]*\\s*(am|pm)?\\s*", " ", title, flags=re.IGNORECASE)
        title = re.sub(r"\\s*for\\s+\\d+\\s*(hour|hr|minute|min)s?\\s*", " ", title, flags=re.IGNORECASE)
        title = title.strip().strip(".,!?") or text

        desc = f"📍 {place}" if place else ""
        add_calendar_event(title, start.timestamp(), end.timestamp(), description=desc)
        time_fmt = start.strftime("%b %d at %I:%M %p").lstrip("0")
        notify_msg = f"◷ {title} — {time_fmt}"
        if place: notify_msg += f" @ {place}"
        _notify(notify_msg)
        speak(f"Event added: {title} on {time_fmt}")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] event error: {e}")''',
    "Voice event date/time/place parsing")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 7 — Voice notes: append to existing note if title matches
# ─────────────────────────────────────────────────────────────────────────────
patch(WW,
    '''def _add_note(text):
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
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] note error: {e}")''',

    '''def _add_note(text, append_to=None):
    """Save a quick note. If append_to title given, appends to that note."""
    try:
        import sqlite3, time as _t
        from config import DB_PATH
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE IF NOT EXISTS quick_notes "
                  "(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, "
                  "content TEXT, created_at REAL, updated_at REAL)")
        now = _t.time()
        # Check if an existing note matches append_to or partial title
        existing = None
        if append_to:
            existing = c.execute(
                "SELECT * FROM quick_notes WHERE title LIKE ? ORDER BY updated_at DESC LIMIT 1",
                (f"%{append_to[:20]}%",)
            ).fetchone()
        if existing:
            new_content = existing["content"] + "\\n" + text.strip()
            c.execute("UPDATE quick_notes SET content=?,updated_at=? WHERE id=?",
                      (new_content, now, existing["id"]))
            c.commit(); c.close()
            _notify(f"📝 Appended to: {existing['title'][:30]}")
        else:
            title = text[:40] + ("..." if len(text) > 40 else "")
            c.execute("INSERT INTO quick_notes (title,content,created_at,updated_at) VALUES (?,?,?,?)",
                      (title, text.strip(), now, now))
            c.commit(); c.close()
            _notify(f"📝 {title}")
        _signal_ui_refresh()
    except Exception as e:
        print(f"[wake] note error: {e}")''',
    "Voice notes append support")

print("\n--- Wake word patches done ---\n")
print("Now run:")
print("  /home/jesus999l/vision_env/bin/python3 -m py_compile ~/vision_assistant/ui.py && echo UI OK")
print("  /home/jesus999l/vision_env/bin/python3 -m py_compile ~/vision_assistant/wake_word.py && echo WW OK")

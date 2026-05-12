"""
Patch: recurring calendar events.
- memory.py: get_calendar_events expands recurring events across date range
- ui.py: EventDialog gets recurring dropdown + update_calendar_event saves it
Run: /home/jesus999l/vision_env/bin/python3 ~/vision_assistant/patch_recurring.py
"""
import subprocess

MEM = "/home/jesus999l/vision_assistant/memory.py"
UI  = "/home/jesus999l/vision_assistant/ui.py"

# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — memory.py: expand recurring events in get_calendar_events
# ─────────────────────────────────────────────────────────────────────────────
mem_src = open(MEM).read()

old_get = '''def get_calendar_events(start=None, end=None):
    conn = get_db()
    if start and end:
        rows = conn.execute(
            "SELECT * FROM calendar_events WHERE start_time>=? AND start_time<=? "
            "ORDER BY start_time",
            (start, end)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM calendar_events ORDER BY start_time"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]'''

new_get = '''def _expand_recurring(event, start, end):
    """Generate virtual occurrences of a recurring event within [start, end]."""
    import datetime as _dt
    rule = event.get("recurring")
    if not rule: return []
    orig_start = event["start_time"]
    duration   = (event["end_time"] or orig_start + 3600) - orig_start
    results    = []
    deltas = {
        "daily":    _dt.timedelta(days=1),
        "weekly":   _dt.timedelta(weeks=1),
        "monthly":  None,  # handled separately
        "weekdays": _dt.timedelta(days=1),
    }
    cur = _dt.datetime.fromtimestamp(orig_start)
    end_dt   = _dt.datetime.fromtimestamp(end)
    start_dt = _dt.datetime.fromtimestamp(start)
    # Advance to range start
    if rule in ("daily", "weekdays"):
        delta = deltas[rule]
        while cur < start_dt:
            cur += delta
            if rule == "weekdays" and cur.weekday() >= 5:
                continue
    elif rule == "weekly":
        while cur < start_dt:
            cur += _dt.timedelta(weeks=1)
    elif rule == "monthly":
        while cur < start_dt:
            month = cur.month + 1
            year  = cur.year + (1 if month > 12 else 0)
            month = month if month <= 12 else 1
            try: cur = cur.replace(year=year, month=month)
            except ValueError: cur = cur.replace(year=year, month=month, day=28)
    # Collect occurrences
    seen = 0
    while cur <= end_dt and seen < 366:
        seen += 1
        if rule == "weekdays" and cur.weekday() >= 5:
            cur += _dt.timedelta(days=1)
            continue
        ts = cur.timestamp()
        if ts != orig_start:  # don't duplicate the original
            occ = dict(event)
            occ["start_time"] = ts
            occ["end_time"]   = ts + duration
            occ["id"]         = f"{event['id']}_r{int(ts)}"  # virtual id
            results.append(occ)
        if rule in ("daily", "weekdays"):
            cur += _dt.timedelta(days=1)
        elif rule == "weekly":
            cur += _dt.timedelta(weeks=1)
        elif rule == "monthly":
            month = cur.month + 1
            year  = cur.year + (1 if month > 12 else 0)
            month = month if month <= 12 else 1
            try: cur = cur.replace(year=year, month=month)
            except ValueError: cur = cur.replace(year=year, month=month, day=28)
        else:
            break
    return results

def get_calendar_events(start=None, end=None):
    conn = get_db()
    if start and end:
        # Get events in range + all recurring events (they may originate outside range)
        rows = conn.execute(
            "SELECT * FROM calendar_events WHERE "
            "(start_time>=? AND start_time<=?) OR recurring IS NOT NULL "
            "ORDER BY start_time",
            (start, end)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM calendar_events ORDER BY start_time"
        ).fetchall()
    conn.close()
    events = [dict(r) for r in rows]
    if not (start and end):
        return events
    # Expand recurring events
    result = []
    for ev in events:
        if not ev.get("recurring"):
            result.append(ev)
        else:
            # Always include the original if in range
            if start <= ev["start_time"] <= end:
                result.append(ev)
            # Add virtual occurrences
            result.extend(_expand_recurring(ev, start, end))
    result.sort(key=lambda e: e["start_time"])
    return result'''

if old_get in mem_src:
    mem_src = mem_src.replace(old_get, new_get)
    print("OK: recurring expansion in get_calendar_events")
else:
    print("FAIL: get_calendar_events not found")

# Fix update_calendar_event to save recurring field
old_update = '''def update_calendar_event(event_id, title, start_time, end_time=None,
                          description="", all_day=0, color="#7c6af7"):
    conn = get_db()
    conn.execute(
        "UPDATE calendar_events SET title=?,start_time=?,end_time=?,"
        "description=?,all_day=?,color=? WHERE id=?",
        (title, start_time, end_time, description, all_day, color, event_id)
    )
    conn.commit(); conn.close()'''

new_update = '''def update_calendar_event(event_id, title, start_time, end_time=None,
                          description="", all_day=0, color="#7c6af7", recurring=None):
    conn = get_db()
    conn.execute(
        "UPDATE calendar_events SET title=?,start_time=?,end_time=?,"
        "description=?,all_day=?,color=?,recurring=? WHERE id=?",
        (title, start_time, end_time, description, all_day, color, recurring, event_id)
    )
    conn.commit(); conn.close()'''

if old_update in mem_src:
    mem_src = mem_src.replace(old_update, new_update)
    print("OK: update_calendar_event recurring")
else:
    print("FAIL: update_calendar_event")

open(MEM, "w").write(mem_src)

# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — ui.py: add recurring dropdown to EventDialog
# ─────────────────────────────────────────────────────────────────────────────
ui_src = open(UI).read()

# Add recurring field after all-day checkbox
old_allday = '''        self.allday=tk.BooleanVar(value=bool(self.event and self.event["all_day"]))
        tk.Checkbutton(self,text="All day event",variable=self.allday,
                       bg=BG2,fg=TEXT2,selectcolor=BG3,activebackground=BG2,
                       font=FONT_SMALL,highlightthickness=0).pack(anchor="w",padx=16,pady=4)

        lbl("COLOR")'''

new_allday = '''        self.allday=tk.BooleanVar(value=bool(self.event and self.event["all_day"]))
        tk.Checkbutton(self,text="All day event",variable=self.allday,
                       bg=BG2,fg=TEXT2,selectcolor=BG3,activebackground=BG2,
                       font=FONT_SMALL,highlightthickness=0).pack(anchor="w",padx=16,pady=4)

        lbl("REPEAT")
        rec_row=tk.Frame(self,bg=BG2); rec_row.pack(fill="x",padx=16,pady=(0,4))
        self.rec_var=tk.StringVar(value=self.event["recurring"] if self.event and self.event.get("recurring") else "none")
        for val,lbl_txt in [("none","None"),("daily","Daily"),("weekdays","Weekdays"),
                             ("weekly","Weekly"),("monthly","Monthly")]:
            tk.Radiobutton(rec_row,text=lbl_txt,variable=self.rec_var,value=val,
                           bg=BG2,fg=TEXT2,selectcolor=BG3,activebackground=BG2,
                           font=FONT_SMALL,highlightthickness=0).pack(side="left",padx=4)

        lbl("COLOR")'''

if old_allday in ui_src:
    ui_src = ui_src.replace(old_allday, new_allday)
    print("OK: recurring UI in EventDialog")
else:
    print("FAIL: allday checkbox not found")

# Update _save to pass recurring
old_save = '''        color=self.sel_color.get()
        allday=int(self.allday.get())
        if self.event:
            update_calendar_event(self.event["id"],title,start,end,desc,allday,color)
        else:
            add_calendar_event(title,start,end,desc,allday,color)'''

new_save = '''        color=self.sel_color.get()
        allday=int(self.allday.get())
        rec=self.rec_var.get()
        recurring=rec if rec != "none" else None
        if self.event:
            update_calendar_event(self.event["id"],title,start,end,desc,allday,color,recurring)
        else:
            add_calendar_event(title,start,end,desc,allday,color,recurring)'''

if old_save in ui_src:
    ui_src = ui_src.replace(old_save, new_save)
    print("OK: EventDialog _save recurring")
else:
    print("FAIL: EventDialog _save")

# Show recurring badge on event pills/cards
old_pill = '''    def _event_pill(self,parent,ev):'''
# Find the event detail display and add recurring indicator
old_detail = '''    def _event_detail(self,ev):'''

# Add recurring label in event detail
if '    def _event_detail(self,ev):' in ui_src:
    idx = ui_src.find('    def _event_detail(self,ev):')
    # Find the title label in event detail
    chunk = ui_src[idx:idx+600]
    if 'ev["title"]' in chunk and 'recurring' not in chunk:
        old_detail_title = 'tk.Label(win,text=ev["title"]'
        # Find first occurrence after _event_detail
        pos = ui_src.find(old_detail_title, idx)
        if pos > 0 and pos < idx + 600:
            # Add recurring badge inline in title
            old_t = ui_src[pos:pos+80]
            # Just add a recurring indicator label after title
            insert_after = ui_src.find('\n', pos) + 1
            rec_label = '''            if ev.get("recurring"):
                rec_map={"daily":"↻ Daily","weekly":"↻ Weekly","monthly":"↻ Monthly","weekdays":"↻ Weekdays"}
                tk.Label(win,text=rec_map.get(ev["recurring"],f"↻ {ev['recurring']}"),
                         bg=BG2,fg=ACCENT2,font=("Segoe UI",8,"bold")).pack(anchor="w",padx=16,pady=(0,4))\n'''
            ui_src = ui_src[:insert_after] + rec_label + ui_src[insert_after:]
            print("OK: recurring badge in event detail")

open(UI, "w").write(ui_src)

# Syntax check
for label, path in [("memory.py", MEM), ("ui.py", UI)]:
    r = subprocess.run(
        ["/home/jesus999l/vision_env/bin/python3", "-m", "py_compile", path],
        capture_output=True, text=True
    )
    print(f"{'OK' if r.returncode==0 else 'ERR'}: {label}")
    if r.returncode != 0: print(r.stderr)

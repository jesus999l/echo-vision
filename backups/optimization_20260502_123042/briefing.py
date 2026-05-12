"""
Morning briefing, event notifications, and reminders.
"""
import os, time, datetime, subprocess, threading, sqlite3
from config import DB_PATH

_notified_events    = set()
_notified_reminders = set()

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
def send_notification(title, body="", urgency="normal", icon="dialog-information"):
    try:
        subprocess.Popen(["notify-send", "-u", urgency, "-i", icon,
                          "-a", "Vision Assistant", title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

# ── BRIEFING ──────────────────────────────────────────────────────────────────
def get_morning_briefing():
    conn  = get_db()
    today = datetime.date.today()

    day_start = datetime.datetime.combine(today, datetime.time.min).timestamp()
    day_end   = datetime.datetime.combine(today, datetime.time.max).timestamp()

    events = conn.execute(
        "SELECT * FROM calendar_events WHERE start_time BETWEEN ? AND ? ORDER BY start_time",
        (day_start, day_end)
    ).fetchall()

    habits    = conn.execute("SELECT * FROM habits WHERE active=1").fetchall()
    due_habits = []
    for h in habits:
        done   = conn.execute(
            "SELECT COUNT(*) FROM habit_completions WHERE habit_id=? AND date_str=?",
            (h["id"], today.isoformat())
        ).fetchone()[0]
        target = h["target"] or 1
        if done < target:
            due_habits.append({"name": h["name"], "done": done, "target": target})

    moods = conn.execute(
        "SELECT mood FROM journal WHERE timestamp > ? AND mood IS NOT NULL "
        "ORDER BY timestamp DESC LIMIT 7",
        (time.time() - 7 * 86400,)
    ).fetchall()
    mood_avg = sum(r["mood"] for r in moods) / len(moods) if moods else None

    goals = conn.execute(
        "SELECT * FROM goals WHERE status != 'done' ORDER BY created_at DESC LIMIT 3"
    ).fetchall()

    conn.close()
    return {
        "date":        today.strftime("%A, %B %d"),
        "events":      [dict(e) for e in events],
        "due_habits":  due_habits,
        "mood_avg":    mood_avg,
        "goals":       [dict(g) for g in goals],
        "event_count": len(events),
        "habit_count": len(due_habits),
    }

def format_briefing_text(b):
    lines = [f"Good morning — {b['date']}", ""]

    if b["events"]:
        lines.append(f"📅 {b['event_count']} event(s) today:")
        for ev in b["events"][:4]:
            dt = datetime.datetime.fromtimestamp(ev["start_time"])
            lines.append(f"   {dt.strftime('%I:%M %p').lstrip('0')}  {ev['title']}")
    else:
        lines.append("📅 No events today — wide open.")

    lines.append("")
    if b["due_habits"]:
        lines.append(f"◈ {b['habit_count']} habit(s) pending:")
        for h in b["due_habits"][:3]:
            lines.append(f"   {h['name']}  ({h['done']}/{h['target']})")
    else:
        lines.append("◈ All habits done ✓")

    if b["mood_avg"]:
        desc = {1:"rough", 2:"low", 3:"okay", 4:"good", 5:"great"}
        lines.append(f"\n✦ Mood this week: {desc.get(round(b['mood_avg']), 'okay')}")

    if b["goals"]:
        titles = ", ".join(g["title"] for g in b["goals"][:3])
        lines.append(f"\n✓ Active goals: {titles}")

    return "\n".join(lines)

def speak_morning_briefing(b):
    """Speak the morning briefing via Piper TTS — sentences queued in order."""
    try:
        from voice import speak_stream
        today = datetime.date.today()
        parts = [f"Good morning. Today is {today.strftime('%A, %B %d')}."]
        if b["events"]:
            ev = b["events"][0]
            dt = datetime.datetime.fromtimestamp(ev["start_time"])
            t  = dt.strftime("%I:%M %p").lstrip("0")
            parts.append(f"You have {b['event_count']} event{'s' if b['event_count']>1 else ''} today. First up: {ev['title']} at {t}.")
        else:
            parts.append("No events scheduled today.")
        if b["due_habits"]:
            names = ", ".join(h["name"] for h in b["due_habits"][:3])
            parts.append(f"{b['habit_count']} habit{'s' if b['habit_count']>1 else ''} pending: {names}.")
        if b["goals"]:
            parts.append(f"Active goals: {', '.join(g['title'] for g in b['goals'][:2])}.")
        speak_stream(iter(parts))
    except Exception as e:
        print(f"[briefing] speak error: {e}")

def show_morning_briefing_notification(b):
    parts = []
    if b["events"]:    parts.append(f"{b['event_count']} event(s) today")
    if b["due_habits"]: parts.append(f"{b['habit_count']} habit(s) pending")
    body = "  ·  ".join(parts) or "Nothing scheduled — free day."
    send_notification(f"Good morning — {b['date']}", body,
                      urgency="low", icon="appointment-soon")

# ── REMINDERS ─────────────────────────────────────────────────────────────────
def add_reminder(text, remind_time):
    conn = get_db()
    conn.execute(
        "INSERT INTO calendar_events (title, start_time, end_time, description, all_day) "
        "VALUES (?,?,?,?,0)",
        (text, remind_time, remind_time + 60, "reminder")
    )
    conn.commit(); conn.close()

def check_reminders():
    try:
        now  = time.time()
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM calendar_events "
            "WHERE start_time BETWEEN ? AND ? AND description='reminder'",
            (now - 30, now + 30)
        ).fetchall()
        conn.close()
        for ev in rows:
            if ev["id"] in _notified_reminders:
                continue
            _notified_reminders.add(ev["id"])
            t = datetime.datetime.fromtimestamp(ev["start_time"]).strftime("%I:%M %p").lstrip("0")
            send_notification(f"⏰ {ev['title']}", t,
                              urgency="critical", icon="appointment-soon")
            try:
                from voice import speak
                speak(f"Reminder: {ev['title']}")
            except: pass
    except Exception as e:
        print(f"[reminder] {e}")

def check_upcoming_events():
    try:
        now  = time.time()
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM calendar_events "
            "WHERE start_time BETWEEN ? AND ? AND all_day=0 AND description!='reminder'",
            (now, now + 16 * 60)
        ).fetchall()
        conn.close()
        for ev in rows:
            if ev["id"] in _notified_events:
                continue
            mins = int((ev["start_time"] - now) / 60)
            _notified_events.add(ev["id"])
            t = datetime.datetime.fromtimestamp(ev["start_time"]).strftime("%I:%M %p").lstrip("0")
            send_notification(
                f"⏰ In {mins} min: {ev['title']}", f"Starts at {t}",
                urgency="critical" if mins <= 5 else "normal",
                icon="appointment-soon"
            )
    except Exception as e:
        print(f"[events] {e}")

def start_reminder_daemon(interval=30):
    """Check reminders and upcoming events every 30 seconds."""
    def _loop():
        while True:
            check_reminders()
            check_upcoming_events()
            time.sleep(interval)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t

# Keep for backwards compat
start_notification_daemon = start_reminder_daemon

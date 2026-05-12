"""
Database layer — chat history, journal, habits, goals, calendar, memory.
"""
import sqlite3, os, json, time, datetime
from config import DB_PATH, BASE_DIR

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    os.makedirs(BASE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    return conn

def _create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  REAL NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            model      TEXT,
            screenshot TEXT,
            ocr_text   TEXT
        );
        CREATE TABLE IF NOT EXISTS journal (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            title     TEXT,
            content   TEXT NOT NULL,
            mood      INTEGER,
            tags      TEXT
        );
        CREATE TABLE IF NOT EXISTS habits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT,
            frequency   TEXT NOT NULL,
            target      INTEGER DEFAULT 1,
            period      TEXT    DEFAULT 'daily',
            created_at  REAL NOT NULL,
            active      INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS habit_completions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id  INTEGER NOT NULL,
            date_str  TEXT    NOT NULL,
            timestamp REAL    NOT NULL,
            note      TEXT,
            FOREIGN KEY (habit_id) REFERENCES habits(id)
        );
        CREATE TABLE IF NOT EXISTS calendar_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT,
            start_time  REAL NOT NULL,
            end_time    REAL,
            all_day     INTEGER DEFAULT 0,
            color       TEXT    DEFAULT '#7c6af7',
            recurring   TEXT,
            tags        TEXT
        );
        CREATE TABLE IF NOT EXISTS goals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT,
            category    TEXT,
            status      TEXT    DEFAULT 'active',
            target_date REAL,
            progress    INTEGER DEFAULT 0,
            created_at  REAL NOT NULL,
            completed   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ai_memory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  REAL NOT NULL,
            category   TEXT NOT NULL,
            content    TEXT NOT NULL,
            importance INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS quick_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT,
            content    TEXT,
            created_at REAL,
            updated_at REAL
        );
    """)
    conn.commit()

# ── CHAT ──────────────────────────────────────────────────────────────────────
def save_message(role, content, model=None, screenshot=None, ocr_text=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_history (timestamp,role,content,model,screenshot,ocr_text) "
        "VALUES (?,?,?,?,?,?)",
        (time.time(), role, content, model, screenshot, ocr_text)
    )
    conn.commit(); conn.close()

def get_recent_messages(limit=20):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM chat_history ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))

# ── JOURNAL ───────────────────────────────────────────────────────────────────
def save_journal_entry(content, title="", mood=None, tags=None):
    now        = time.time()
    mood_emoji = {1:"😔",2:"😐",3:"🙂",4:"😊",5:"🤩"}.get(mood or 3, "✦")
    preview    = content[:40].replace("\n", " ")
    conn = get_db()
    conn.execute(
        "INSERT INTO journal (timestamp,title,content,mood,tags) VALUES (?,?,?,?,?)",
        (now, title, content, mood, json.dumps(tags or []))
    )
    conn.execute(
        "INSERT INTO calendar_events "
        "(title,description,start_time,end_time,all_day,color,recurring) VALUES (?,?,?,?,?,?,?)",
        (f"{mood_emoji} Journal: {preview}", content[:200], now, now+1800, 0, "#a5d6a7", None)
    )
    conn.commit(); conn.close()

def update_journal_entry(entry_id, content, title="", mood=None):
    conn = get_db()
    conn.execute("UPDATE journal SET content=?,title=?,mood=? WHERE id=?",
                 (content, title, mood, entry_id))
    conn.commit(); conn.close()

def delete_journal_entry(entry_id):
    conn = get_db()
    conn.execute("DELETE FROM journal WHERE id=?", (entry_id,))
    conn.commit(); conn.close()

def get_journal_entries(limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM journal ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── HABITS ────────────────────────────────────────────────────────────────────
def get_habits():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM habits WHERE active=1 ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_habit(name, description="", frequency="daily"):
    now = time.time()
    conn = get_db()
    conn.execute(
        "INSERT INTO habits (name,description,frequency,created_at) VALUES (?,?,?,?)",
        (name, description, frequency, now)
    )
    conn.execute(
        "INSERT INTO calendar_events "
        "(title,description,start_time,end_time,all_day,color,recurring) VALUES (?,?,?,?,?,?,?)",
        (f"◈ Habit: {name}", f"New habit: {name} ({frequency})",
         now, now+1800, 0, "#4fc3f7", None)
    )
    conn.commit(); conn.close()

def update_habit(habit_id, name, frequency="daily"):
    conn = get_db()
    conn.execute("UPDATE habits SET name=?,frequency=? WHERE id=?",
                 (name, frequency, habit_id))
    conn.commit(); conn.close()

def update_habit_target(habit_id, target, period):
    conn = get_db()
    conn.execute("UPDATE habits SET target=?,period=? WHERE id=?",
                 (target, period, habit_id))
    conn.commit(); conn.close()

def delete_habit(habit_id):
    conn = get_db()
    conn.execute("DELETE FROM habit_completions WHERE habit_id=?", (habit_id,))
    conn.execute("DELETE FROM habits WHERE id=?", (habit_id,))
    conn.commit(); conn.close()

def complete_habit(habit_id, note=""):
    """Mark habit done today (once per day). Returns True if newly completed."""
    date_str = datetime.date.today().isoformat()
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM habit_completions WHERE habit_id=? AND date_str=?",
        (habit_id, date_str)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO habit_completions (habit_id,date_str,timestamp,note) VALUES (?,?,?,?)",
            (habit_id, date_str, time.time(), note)
        )
        conn.commit()
    conn.close()
    return not bool(existing)

def complete_habit_once(habit_id):
    """Add one completion for today (allows multiple per day)."""
    date_str = datetime.date.today().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO habit_completions (habit_id,date_str,timestamp) VALUES (?,?,?)",
        (habit_id, date_str, time.time())
    )
    conn.commit(); conn.close()

def habit_done_today(habit_id):
    date_str = datetime.date.today().isoformat()
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM habit_completions WHERE habit_id=? AND date_str=?",
        (habit_id, date_str)
    ).fetchone()
    conn.close()
    return row is not None

def get_habit_completions_count(habit_id, period="daily"):
    conn  = get_db()
    today = datetime.date.today()
    if period == "daily":
        count = conn.execute(
            "SELECT COUNT(*) FROM habit_completions WHERE habit_id=? AND date_str=?",
            (habit_id, today.isoformat())
        ).fetchone()[0]
    elif period == "weekly":
        monday = today - datetime.timedelta(days=today.weekday())
        count  = conn.execute(
            "SELECT COUNT(DISTINCT date_str) FROM habit_completions "
            "WHERE habit_id=? AND date_str>=?",
            (habit_id, monday.isoformat())
        ).fetchone()[0]
    elif period == "monthly":
        count = conn.execute(
            "SELECT COUNT(DISTINCT date_str) FROM habit_completions "
            "WHERE habit_id=? AND date_str LIKE ?",
            (habit_id, today.strftime("%Y-%m") + "%")
        ).fetchone()[0]
    else:
        count = 0
    conn.close()
    return count

# ── CALENDAR ──────────────────────────────────────────────────────────────────
def get_calendar_events(start=None, end=None):
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
    return [dict(r) for r in rows]

def add_calendar_event(title, start_time, end_time=None, description="",
                       all_day=0, color="#7c6af7", recurring=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO calendar_events "
        "(title,description,start_time,end_time,all_day,color,recurring) VALUES (?,?,?,?,?,?,?)",
        (title, description, start_time, end_time, all_day, color, recurring)
    )
    conn.commit(); conn.close()

def update_calendar_event(event_id, title, start_time, end_time=None,
                          description="", all_day=0, color="#7c6af7"):
    conn = get_db()
    conn.execute(
        "UPDATE calendar_events SET title=?,start_time=?,end_time=?,"
        "description=?,all_day=?,color=? WHERE id=?",
        (title, start_time, end_time, description, all_day, color, event_id)
    )
    conn.commit(); conn.close()

def delete_calendar_event(event_id):
    conn = get_db()
    conn.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
    conn.commit(); conn.close()

# ── GOALS ─────────────────────────────────────────────────────────────────────
_GOAL_COLORS = {
    "health":"#a5d6a7", "career":"#4fc3f7", "finance":"#ffcc80",
    "learning":"#ce93d8", "personal":"#7c6af7",
}

def get_goals(include_completed=False):
    conn = get_db()
    q    = ("SELECT * FROM goals ORDER BY created_at DESC" if include_completed
            else "SELECT * FROM goals WHERE completed=0 ORDER BY created_at DESC")
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_goal(title, description="", category="personal", target_date=None):
    now   = time.time()
    color = _GOAL_COLORS.get(category or "personal", "#7c6af7")
    conn  = get_db()
    conn.execute(
        "INSERT INTO goals (title,description,category,target_date,created_at) VALUES (?,?,?,?,?)",
        (title, description, category, target_date, now)
    )
    conn.execute(
        "INSERT INTO calendar_events "
        "(title,description,start_time,end_time,all_day,color,recurring) VALUES (?,?,?,?,?,?,?)",
        (f"✓ Goal: {title}", f"Goal added ({category})", now, now+3600, 0, color, None)
    )
    if target_date:
        conn.execute(
            "INSERT INTO calendar_events "
            "(title,description,start_time,end_time,all_day,color,recurring) VALUES (?,?,?,?,?,?,?)",
            (f"🎯 Due: {title}", f"Deadline ({category})",
             target_date, target_date+3600, 1, color, None)
        )
    conn.commit(); conn.close()

def update_goal(goal_id, title, description="", category="personal", progress=0):
    conn = get_db()
    conn.execute(
        "UPDATE goals SET title=?,description=?,category=?,progress=? WHERE id=?",
        (title, description, category, progress, goal_id)
    )
    conn.commit(); conn.close()

def update_goal_status(goal_id, status):
    conn = get_db()
    conn.execute("UPDATE goals SET status=? WHERE id=?", (status, goal_id))
    conn.commit(); conn.close()

def complete_goal(goal_id):
    conn = get_db()
    conn.execute("UPDATE goals SET completed=1,progress=100 WHERE id=?", (goal_id,))
    conn.commit(); conn.close()

def delete_goal(goal_id):
    conn = get_db()
    conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))
    conn.commit(); conn.close()

# ── AI MEMORY ─────────────────────────────────────────────────────────────────
def remember(content, category="fact", importance=1):
    conn = get_db()
    conn.execute(
        "INSERT INTO ai_memory (timestamp,category,content,importance) VALUES (?,?,?,?)",
        (time.time(), category, content, importance)
    )
    conn.commit(); conn.close()

def get_memories(category=None, limit=20):
    conn = get_db()
    if category:
        rows = conn.execute(
            "SELECT * FROM ai_memory WHERE category=? "
            "ORDER BY importance DESC, timestamp DESC LIMIT ?",
            (category, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ai_memory ORDER BY importance DESC, timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def build_memory_context():
    memories = get_memories(limit=15)
    if not memories:
        return ""
    lines = ["[What I remember about you:"]
    lines += [f"  - {m['content']}" for m in memories]
    lines.append("]")
    return "\n".join(lines)

"""
Universal local search across all data.
"""
import sqlite3, datetime, time
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def search_all(query, limit=30):
    """Search tasks, habits, journal, calendar. Returns grouped results."""
    if not query or len(query) < 2:
        return {}
    q = f"%{query.lower()}%"
    conn = get_db()
    results = {}

    # Tasks/Goals
    goals = conn.execute(
        "SELECT * FROM goals WHERE LOWER(title) LIKE ? OR LOWER(description) LIKE ? ORDER BY created_at DESC LIMIT ?",
        (q, q, limit)
    ).fetchall()
    if goals:
        results["tasks"] = [dict(g) for g in goals]

    # Habits
    habits = conn.execute(
        "SELECT * FROM habits WHERE LOWER(name) LIKE ? ORDER BY created_at DESC LIMIT ?",
        (q, limit)
    ).fetchall()
    if habits:
        results["habits"] = [dict(h) for h in habits]

    # Journal
    journal = conn.execute(
        "SELECT * FROM journal WHERE LOWER(content) LIKE ? OR LOWER(title) LIKE ? ORDER BY timestamp DESC LIMIT ?",
        (q, q, limit)
    ).fetchall()
    if journal:
        results["journal"] = [dict(j) for j in journal]

    # Calendar
    events = conn.execute(
        "SELECT * FROM calendar_events WHERE LOWER(title) LIKE ? OR LOWER(description) LIKE ? ORDER BY start_time DESC LIMIT ?",
        (q, q, limit)
    ).fetchall()
    if events:
        results["calendar"] = [dict(e) for e in events]

    conn.close()
    return results

def result_count(results):
    return sum(len(v) for v in results.values())

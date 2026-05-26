"""
Personality & long-term memory module.
Builds emotional context from journal mood trends,
task completion patterns, and habit streaks.
"""
import os
import json
import time
import datetime
import sqlite3
from config import DB_PATH

MEMORY_PATH = os.path.expanduser("~/vision_assistant/long_term_memory.json")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_long_term_memory():
    try:
        with open(MEMORY_PATH) as f:
            return json.load(f)
    except:
        return {
            "habit_history": {},    # habit_name -> list of start dates
            "goal_history": [],     # list of completed/abandoned goals
            "mood_trend": [],       # last 30 mood scores
            "focus_areas": [],      # categories user spends most time on
            "personality_notes": [] # AI-generated observations
        }

def save_long_term_memory(mem):
    with open(MEMORY_PATH, "w") as f:
        json.dump(mem, f, indent=2)

def get_mood_trend(days=30):
    """Get mood scores for last N days."""
    conn = get_db()
    cutoff = time.time() - days * 86400
    rows = conn.execute(
        "SELECT mood, timestamp FROM journal WHERE timestamp > ? AND mood IS NOT NULL ORDER BY timestamp",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [(r["mood"], datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%b %d")) for r in rows]

def get_habit_streaks():
    """Calculate current streak for each habit."""
    conn = get_db()
    habits = conn.execute("SELECT * FROM habits WHERE active=1").fetchall()
    streaks = {}
    today = datetime.date.today()
    for h in habits:
        streak = 0
        d = today
        for _ in range(365):
            date_str = d.isoformat()
            done = conn.execute(
                "SELECT COUNT(*) FROM habit_completions WHERE habit_id=? AND date_str=?",
                (h["id"], date_str)
            ).fetchone()[0]
            if done:
                streak += 1
                d -= datetime.timedelta(days=1)
            else:
                break
        streaks[h["name"]] = streak
    conn.close()
    return streaks

def get_goal_completion_rate():
    """What % of goals get completed vs abandoned."""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
    done  = conn.execute("SELECT COUNT(*) FROM goals WHERE completed=1").fetchone()[0]
    conn.close()
    if total == 0: return 0
    return round(done / total * 100)

def get_abandoned_habits():
    """Habits the user has added more than once (restarted)."""
    mem = load_long_term_memory()
    return {k: v for k,v in mem.get("habit_history",{}).items() if len(v) > 1}

def update_memory_from_db():
    """Sync long-term memory with current DB state."""
    mem = load_long_term_memory()
    conn = get_db()

    # Track habit restarts
    habits = conn.execute("SELECT name, created_at FROM habits").fetchall()
    for h in habits:
        name = h["name"]
        ts   = h["created_at"]
        if name not in mem["habit_history"]:
            mem["habit_history"][name] = []
        date_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        if date_str not in mem["habit_history"][name]:
            mem["habit_history"][name].append(date_str)

    # Track mood trend
    mood_data = get_mood_trend(30)
    mem["mood_trend"] = [m for m,_ in mood_data]

    # Track focus areas from goals
    cats = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM goals GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    mem["focus_areas"] = [r["category"] for r in cats if r["category"]]

    conn.close()
    save_long_term_memory(mem)
    return mem

def build_personality_context():
    """Build a rich personality context string for the AI system prompt."""
    try:
        mem = update_memory_from_db()
        mood_trend = get_mood_trend(14)
        streaks    = get_habit_streaks()
        comp_rate  = get_goal_completion_rate()
        abandoned  = get_abandoned_habits()

        parts = []

        # Mood analysis
        if mood_trend:
            scores = [m for m,_ in mood_trend]
            avg = sum(scores) / len(scores)
            recent_avg = sum(scores[-3:]) / len(scores[-3:]) if len(scores) >= 3 else avg
            trend = "improving" if recent_avg > avg else "declining" if recent_avg < avg - 0.5 else "stable"
            mood_desc = {1:"struggling",2:"low",3:"okay",4:"good",5:"great"}
            parts.append(f"MOOD: {mood_desc.get(round(avg),'okay')} overall, trend is {trend} recently.")

        # Habit streaks
        active_streaks = {k:v for k,v in streaks.items() if v > 0}
        if active_streaks:
            best = max(active_streaks, key=active_streaks.get)
            parts.append(f"HABITS: Best streak is '{best}' at {active_streaks[best]} days.")
        if abandoned:
            names = list(abandoned.keys())[:2]
            parts.append(f"PATTERN: User has restarted these habits multiple times: {', '.join(names)}. Be encouraging but honest about consistency.")

        # Goal patterns
        if comp_rate > 0:
            parts.append(f"GOALS: {comp_rate}% completion rate.")
            if comp_rate < 40:
                parts.append("User tends to set ambitious goals but struggles to complete them. Suggest breaking goals into smaller steps.")
            elif comp_rate > 70:
                parts.append("User is highly effective at completing goals. Can handle ambitious targets.")

        # Focus areas
        if mem.get("focus_areas"):
            parts.append(f"FOCUS: Primary areas are {', '.join(mem['focus_areas'][:3])}.")

        return "\n".join(parts) if parts else ""
    except Exception as e:
        return ""

def generate_reflective_summary():
    """Analyze recent activity and generate a learning summary."""
    try:
        mem = update_memory_from_db()
        mood_trend = get_mood_trend(7)
        comp_rate  = get_goal_completion_rate()

        summary = f"Reflective Summary - {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
        summary += f"Goal Completion Rate: {comp_rate}%\n"

        if mood_trend:
            avg_mood = sum(m for m, _ in mood_trend) / len(mood_trend)
            summary += f"Average Mood (last 7 days): {avg_mood:.1f}/5\n"

        if mem.get("focus_areas"):
            summary += f"Primary Focus: {', '.join(mem['focus_areas'][:2])}\n"

        summary += "\nEcho's Observation:\n"
        if comp_rate > 70:
            summary += "You've been highly productive. Echo is optimized for high-intensity support."
        elif comp_rate < 40:
            summary += "We're seeing a lot of pending tasks. Echo suggests breaking down large goals."
        else:
            summary += "Steady progress maintained. Cognitive alignment is nominal."

        return summary
    except Exception as e:
        return f"Reflective cycle error: {e}"

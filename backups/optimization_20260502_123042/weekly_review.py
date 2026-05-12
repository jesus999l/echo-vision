"""
Weekly review generator - summarizes the past 7 days.
"""
import os, time, datetime, sqlite3, json
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_weekly_data():
    conn = get_db()
    today = datetime.date.today()
    week_ago = datetime.datetime.combine(today - datetime.timedelta(days=7), datetime.time.min)
    week_ago_ts = week_ago.timestamp()
    now_ts = time.time()

    # Journal entries this week
    journals = conn.execute(
        "SELECT * FROM journal WHERE timestamp > ? ORDER BY timestamp DESC",
        (week_ago_ts,)
    ).fetchall()
    moods = [j["mood"] for j in journals if j["mood"]]
    mood_avg = sum(moods)/len(moods) if moods else None
    mood_trend = "improving" if len(moods)>=3 and moods[0]>moods[-1] else \
                 "declining" if len(moods)>=3 and moods[0]<moods[-1] else "stable"

    # Habit completion this week
    habits = conn.execute("SELECT * FROM habits WHERE active=1").fetchall()
    habit_stats = []
    for h in habits:
        target = (h["target"] or 1) * 7
        done = conn.execute(
            "SELECT COUNT(*) FROM habit_completions WHERE habit_id=? AND timestamp>?",
            (h["id"], week_ago_ts)
        ).fetchone()[0]
        pct = min(100, round(done/target*100)) if target else 0
        habit_stats.append({
            "name": h["name"], "done": done,
            "target": target, "pct": pct
        })

    # Goals completed this week
    goals_done = conn.execute(
        "SELECT * FROM goals WHERE status='done'"
    ).fetchall()

    # Goals still active
    goals_active = conn.execute(
        "SELECT * FROM goals WHERE status!='done'"
    ).fetchall()

    # Events this week
    events = conn.execute(
        "SELECT * FROM calendar_events WHERE start_time BETWEEN ? AND ? AND title NOT LIKE '✓ Goal:%' AND title NOT LIKE '◈ Habit:%' AND title NOT LIKE '% Journal:%'",
        (week_ago_ts, now_ts)
    ).fetchall()

    conn.close()

    return {
        "week_of": week_ago.strftime("%B %d"),
        "week_end": today.strftime("%B %d, %Y"),
        "journal_count": len(journals),
        "mood_avg": mood_avg,
        "mood_trend": mood_trend,
        "habit_stats": habit_stats,
        "goals_done": [dict(g) for g in goals_done],
        "goals_active": [dict(g) for g in goals_active],
        "events": [dict(e) for e in events],
    }

def format_weekly_prompt(data):
    """Build a prompt for the AI to generate a personalized weekly review."""
    mood_desc = {1:"rough",2:"low",3:"okay",4:"good",5:"great"}
    lines = [
        f"Generate a weekly review for the week of {data['week_of']} – {data['week_end']}.",
        f"Journal entries written: {data['journal_count']}",
    ]
    if data["mood_avg"]:
        lines.append(f"Average mood: {mood_desc.get(round(data['mood_avg']),'okay')} ({data['mood_avg']:.1f}/5), trend: {data['mood_trend']}")

    lines.append("\nHabit completion:")
    for h in data["habit_stats"]:
        bar = "█" * (h["pct"]//10) + "░" * (10 - h["pct"]//10)
        lines.append(f"  {h['name']}: {bar} {h['pct']}%")

    if data["goals_done"]:
        lines.append(f"\nGoals completed: {', '.join(g['title'] for g in data['goals_done'])}")
    if data["goals_active"]:
        lines.append(f"Goals in progress: {', '.join(g['title'] for g in data['goals_active'][:5])}")
    if data["events"]:
        lines.append(f"\nEvents this week: {len(data['events'])}")

    lines.append("\nWrite a direct, honest 4-6 sentence review. Acknowledge wins, call out patterns honestly, give one specific focus for next week. No fluff.")
    return "\n".join(lines)

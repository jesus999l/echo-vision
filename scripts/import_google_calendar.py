#!/usr/bin/env python3
"""Import Google Takeout .ics into memory.db calendar_events (schema-aware, deduped)."""
import re
import sqlite3
import datetime
from pathlib import Path

ICS = Path.home() / "Documents/Google_Takeout/Takeout/Calendar/jesuslopez8234@gmail.com.ics"
DB = Path.home() / "vision_assistant/memory.db"


def _get_field(block, field):
    m = re.search(rf"{field}[;:][^:]*:(.*)", block)
    if not m:
        m = re.search(rf"{field}:(.*)", block)
    return m.group(1).strip() if m else ""


def _parse_start(dtstart):
    ds = re.sub(r"[^0-9]", "", dtstart)
    if len(ds) >= 14:
        return datetime.datetime.strptime(ds[:14], "%Y%m%d%H%M%S")
    if len(ds) >= 8:
        return datetime.datetime.strptime(ds[:8], "%Y%m%d")
    return None


def main():
    if not ICS.exists():
        print(f"ICS not found: {ICS}")
        return 1

    raw = ICS.read_text(encoding="utf-8", errors="ignore")
    events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", raw, re.DOTALL)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(calendar_events)")
    columns = [col[1] for col in cur.fetchall()]
    if not columns:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_time REAL NOT NULL,
                end_time REAL,
                all_day INTEGER DEFAULT 0,
                color TEXT DEFAULT '#7c6af7',
                recurring TEXT,
                tags TEXT
            )
        """)
        columns = ["title", "start_time", "end_time", "description", "all_day"]

    imported = 0
    skipped = 0
    for block in events:
        title = _get_field(block, "SUMMARY")
        dtstart = _get_field(block, "DTSTART")
        dtend = _get_field(block, "DTEND")
        desc = _get_field(block, "DESCRIPTION")
        if not title or not dtstart:
            continue
        try:
            start_dt = _parse_start(dtstart)
            if not start_dt:
                continue
            ts = start_dt.timestamp()
            if dtend:
                end_dt = _parse_start(dtend)
                end_ts = end_dt.timestamp() if end_dt else ts + 3600
            else:
                end_ts = ts + 3600
            all_day = 1 if "VALUE=DATE" in block.split("DTSTART")[1].split("\n")[0] else 0

            exists = cur.execute(
                "SELECT 1 FROM calendar_events WHERE title=? AND ABS(start_time-?)<60",
                (title, ts),
            ).fetchone()
            if exists:
                skipped += 1
                continue

            val_map = {
                "title": title,
                "start_time": ts,
                "end_time": end_ts,
                "description": desc[:500],
                "all_day": all_day,
                "color": "#7c6af7",
            }
            present = [c for c in columns if c in val_map and c != "id"]
            placeholders = ", ".join(["?"] * len(present))
            col_names = ", ".join(present)
            vals = [val_map[c] for c in present]
            cur.execute(
                f"INSERT INTO calendar_events ({col_names}) VALUES ({placeholders})",
                tuple(vals),
            )
            imported += 1
        except Exception:
            pass

    conn.commit()
    total = cur.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]
    conn.close()
    print(f"imported {imported} new, skipped {skipped} duplicates, {total} total in {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

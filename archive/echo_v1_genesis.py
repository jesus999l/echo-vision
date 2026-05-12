"""
echo_v1_genesis.py — Echo v1 Genesis Integration
==================================================
Merges the new architectural pieces from the genesis design into
the existing Echo stack without breaking the proven schema.

What this adds:
  - Full TriageState lifecycle (stabilizing, candidate, consolidated, embedded)
  - URL canonicalization (strips tracking params, keeps signal)
  - Metabolism engine (48h temporal decay + 5000-event volumetric brake)
  - triage_config.json (externalized thresholds)
  - Schema migration (adds new columns to existing DB, preserves all data)
  - Updated project directory structure

What it preserves:
  - event_id TEXT PRIMARY KEY (UUID — keeps SQLite↔JSONL causal link)
  - received_at TEXT ISO format (keeps replay ordering)
  - fingerprint, priority, trace_id columns (keeps dedup + black box link)

Run:
  python3 echo_v1_genesis.py
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("~/vision_assistant").expanduser()


# =========================================================
# TRIAGE STATE LIFECYCLE
# Full state machine — replaces the 3-state pending/promoted/discarded
# =========================================================

TRIAGE_STATES = {
    # Entry state — event just landed in the buffer
    "pending":      "Received, awaiting triage worker",
    # Seen once, waiting to see if dwell time confirms it's real signal
    "stabilizing":  "Seen, waiting for dwell threshold confirmation",
    # Passed dwell check, being evaluated for promotion
    "candidate":    "High-signal candidate, awaiting consolidation",
    # Grouped with related events into a topic cluster
    "consolidated": "Merged into a cognitive event cluster",
    # Sent through Kernel, JSONL trace written, trace_id linked
    "promoted":     "Promoted to Kernel, trace_id recorded",
    # Embedding written to ChromaDB
    "embedded":     "Embedded in vector store",
    # Filtered out — noise, duplicate, low-priority, or decayed
    "discarded":    "Filtered by triage (noise/dup/decay)",
    # Processing failed — preserved for inspection, not deleted
    "errored":      "Encountered an error during processing",
}

# Legal transitions — enforced by TriageStateMachine
TRANSITIONS = {
    "pending":      {"stabilizing", "discarded", "errored"},
    "stabilizing":  {"candidate", "discarded", "errored"},
    "candidate":    {"consolidated", "promoted", "discarded", "errored"},
    "consolidated": {"promoted", "discarded", "errored"},
    "promoted":     {"embedded", "errored"},
    "embedded":     set(),         # terminal
    "discarded":    set(),         # terminal
    "errored":      {"pending"},   # allow retry
}


class TriageStateMachine:
    """
    Validates state transitions before writing to SQLite.
    Prevents events from jumping illegally between states.
    """

    def validate(self, current: str, next_state: str) -> bool:
        allowed = TRANSITIONS.get(current, set())
        return next_state in allowed

    def transition(
        self,
        conn: sqlite3.Connection,
        event_id: str,
        next_state: str,
        reason: str = "",
    ) -> bool:
        row = conn.execute(
            "SELECT triage_state FROM sensory_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()

        if row is None:
            return False

        current = row[0]
        if not self.validate(current, next_state):
            print(
                f"[StateMachine] ILLEGAL TRANSITION: "
                f"{event_id[:8]}... {current} → {next_state}"
            )
            return False

        conn.execute(
            "UPDATE sensory_events SET triage_state = ?, triage_reason = ? "
            "WHERE event_id = ?",
            (next_state, reason, event_id),
        )
        return True


# =========================================================
# URL CANONICALIZATION
# Strips tracking params before fingerprinting.
# Without this, utm_source=twitter and utm_source=email
# produce different fingerprints for the same article.
# =========================================================

def canonicalize_url(url: str) -> str:
    """
    Strip tracking and session params from URLs.
    Keeps only high-signal query params: v (YouTube), q (search).

    Examples:
      https://example.com/article?utm_source=twitter&utm_medium=social
        → https://example.com/article

      https://youtube.com/watch?v=abc123&feature=share&t=42
        → https://youtube.com/watch?v=abc123
    """
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

    if not url.startswith("http"):
        return url

    KEEP_PARAMS = {"v", "q"}   # YouTube video ID, search query

    parsed      = urlparse(url)
    query       = parse_qs(parsed.query)
    clean_query = {k: v for k, v in query.items() if k in KEEP_PARAMS}

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(clean_query, doseq=True),
        "",   # strip fragment
    ))


# =========================================================
# METABOLISM ENGINE
# Forgetting mechanism — keeps the DB bounded on the T14s.
# =========================================================

class Metabolism:
    """
    Runs maintenance on the sensory buffer to prevent SSD burnout
    and memory collapse on constrained hardware.

    Two forgetting laws:
      1. Temporal decay   — discard events older than 48 hours
      2. Volumetric brake — keep at most 5000 discarded rows total

    Call run_maintenance() periodically (e.g., every 5 minutes from
    the triage worker, or manually via CLI).
    """

    DECAY_WINDOW_MS   = 48 * 3600 * 1000   # 48 hours in milliseconds
    MAX_DISCARDED     = 5000

    def __init__(self, db_path: str):
        self.db_path = db_path

    def run_maintenance(self) -> dict:
        now_ms  = int(datetime.now(timezone.utc).timestamp() * 1000)
        cutoff  = now_ms - self.DECAY_WINDOW_MS

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")

            # 1. Temporal decay: delete old discarded events
            result = conn.execute(
                "DELETE FROM sensory_events "
                "WHERE triage_state = 'discarded' AND created_at_ms < ?",
                (cutoff,),
            )
            temporal_deleted = result.rowcount

            # 2. Volumetric brake: cap discarded at MAX_DISCARDED
            count_row = conn.execute(
                "SELECT COUNT(*) FROM sensory_events WHERE triage_state = 'discarded'"
            ).fetchone()
            discarded_count = count_row[0] if count_row else 0

            volumetric_deleted = 0
            if discarded_count > self.MAX_DISCARDED:
                overflow = discarded_count - self.MAX_DISCARDED
                conn.execute(
                    "DELETE FROM sensory_events WHERE id IN "
                    "(SELECT id FROM sensory_events WHERE triage_state = 'discarded' "
                    "ORDER BY created_at_ms ASC LIMIT ?)",
                    (overflow,),
                )
                volumetric_deleted = overflow

            conn.commit()

        report = {
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "temporal_deleted":   temporal_deleted,
            "volumetric_deleted": volumetric_deleted,
            "total_deleted":      temporal_deleted + volumetric_deleted,
            "decay_window_hours": 48,
            "max_discarded_cap":  self.MAX_DISCARDED,
        }
        return report


# =========================================================
# SCHEMA MIGRATION
# Adds new columns to existing DB, preserves all proven data.
# =========================================================

SCHEMA_MIGRATIONS = [
    # Full triage lifecycle state (replaces status column)
    "ALTER TABLE sensory_events ADD COLUMN triage_state TEXT NOT NULL DEFAULT 'pending'",
    # Human-readable reason for the state transition
    "ALTER TABLE sensory_events ADD COLUMN triage_reason TEXT",
    # Millisecond timestamp for Metabolism decay calculations
    "ALTER TABLE sensory_events ADD COLUMN created_at_ms INTEGER",
    # Fingerprint for dedup (added by bridge, may already exist)
    "ALTER TABLE sensory_events ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''",
    # Priority score 0-9 (added by bridge, may already exist)
    "ALTER TABLE sensory_events ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
]

# New indexes to support triage worker queries
NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_triage_state ON sensory_events(triage_state)",
    "CREATE INDEX IF NOT EXISTS idx_created_ms   ON sensory_events(created_at_ms)",
    "CREATE INDEX IF NOT EXISTS idx_fingerprint  ON sensory_events(fingerprint)",
]

def migrate_schema(db_path: str):
    """
    Apply schema migrations idempotently.
    Uses try/except on each ALTER TABLE — if the column exists, skip it.
    Never drops data.
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")

        for migration in SCHEMA_MIGRATIONS:
            try:
                conn.execute(migration)
                col = migration.split("ADD COLUMN")[1].strip().split()[0]
                print(f"   + Column added  : {col}")
            except sqlite3.OperationalError:
                col = migration.split("ADD COLUMN")[1].strip().split()[0]
                print(f"   = Column exists : {col}")

        # Backfill created_at_ms from received_at where null
        conn.execute("""
            UPDATE sensory_events
            SET created_at_ms = CAST(
                (julianday(received_at) - 2440587.5) * 86400000
                AS INTEGER
            )
            WHERE created_at_ms IS NULL AND received_at IS NOT NULL
        """)

        # Sync triage_state ← status (old column) where triage_state is still default
        conn.execute("""
            UPDATE sensory_events
            SET triage_state = status
            WHERE triage_state = 'pending' AND status != 'pending'
        """)

        for idx in NEW_INDEXES:
            try:
                conn.execute(idx)
            except sqlite3.OperationalError:
                pass

        conn.commit()


# =========================================================
# PROJECT STRUCTURE
# =========================================================

DIRS = [
    "core",
    "config",
    "tools",
    "data",
    "traces",
    "logs",
    "tests",
]

# triage_config.json — externalized thresholds, tune without code changes
TRIAGE_CONFIG = {
    "schema_version":        "1.0",
    "promotion_threshold":   1.5,    # minimum signal score to promote
    "dwell_threshold_sec":   45,     # seconds on page before it's considered signal
    "max_discard_vol":       5000,   # volumetric brake cap
    "decay_window_hours":    48,     # temporal decay window
    "backlog_warn":          100,    # queue warning threshold
    "backlog_slow":          500,    # start discarding low-priority
    "backlog_pause":         1000,   # refuse new events
    "priority_thresholds": {
        "text_selection":    8,
        "page_load":         6,
        "tab_change":        5,
        "tab_close":         3,
        "scroll":            1,
        "focus_change":      1,
        "mousemove":         0,
    },
}


def write_config(root: Path):
    config_path = root / "config" / "triage_config.json"
    if config_path.exists():
        print(f"   = Config exists : config/triage_config.json (not overwritten)")
        return
    with open(config_path, "w") as f:
        json.dump(TRIAGE_CONFIG, f, indent=2)
    print(f"   + Config written: config/triage_config.json")


# =========================================================
# GENESIS
# =========================================================

def run_genesis():
    print(f"\n{'=' * 60}")
    print(f"  Echo v1 Genesis Integration")
    print(f"  ABI: 11.8.FREEZE")
    print(f"{'=' * 60}\n")

    # 1. Directory structure
    print("[1/4] Creating directory structure...")
    for d in DIRS:
        path = ROOT / d
        path.mkdir(parents=True, exist_ok=True)
        status = "+" if not path.exists() else "="
        print(f"   = {d}/")
    print()

    # 2. Write config
    print("[2/4] Writing config...")
    write_config(ROOT)
    print()

    # 3. Migrate schema
    db_path = ROOT / "data" / "sensory_buffer.db"
    if not db_path.exists():
        print("[3/4] Initializing fresh database...")
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sensory_events (
                    event_id      TEXT PRIMARY KEY,
                    source        TEXT NOT NULL,
                    event_type    TEXT NOT NULL,
                    payload       TEXT NOT NULL,
                    fingerprint   TEXT NOT NULL DEFAULT '',
                    priority      INTEGER NOT NULL DEFAULT 0,
                    received_at   TEXT NOT NULL,
                    created_at_ms INTEGER,
                    triage_state  TEXT NOT NULL DEFAULT 'pending',
                    triage_reason TEXT,
                    promoted_at   TEXT,
                    trace_id      TEXT
                )
            """)
            for idx in NEW_INDEXES:
                conn.execute(idx)
            conn.commit()
        print(f"   + DB initialized: data/sensory_buffer.db (WAL mode)")
    else:
        print("[3/4] Migrating existing database (no data lost)...")
        migrate_schema(str(db_path))
    print()

    # 4. Verify
    print("[4/4] Verifying...")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sensory_events)").fetchall()]
        count = conn.execute("SELECT COUNT(*) FROM sensory_events").fetchone()[0]

    required = {"event_id", "triage_state", "fingerprint", "trace_id", "created_at_ms"}
    missing  = required - set(cols)

    print(f"   WAL mode     : {mode}")
    print(f"   Columns      : {len(cols)} present")
    print(f"   Existing rows: {count}")

    if missing:
        print(f"   ❌ Missing columns: {missing}")
        sys.exit(1)
    else:
        print(f"   ✅ All required columns present")

    print(f"\n{'=' * 60}")
    print(f"  ✅ GENESIS COMPLETE")
    print(f"  Directory  : {ROOT}")
    print(f"  Database   : {db_path}")
    print(f"  Schema     : 11.8.FREEZE compatible")
    print(f"\n  Next steps:")
    print(f"  1. python3 echo_v11_6_bootstrap.py       (verify existing tests pass)")
    print(f"  2. python3 echo_browser_bridge.py         (start WebSocket bridge)")
    print(f"  3. python3 test_browser_noise.py          (run noise storm)")
    print(f"  4. watch 'sqlite3 ~/vision_assistant/data/sensory_buffer.db")
    print(f'     "SELECT triage_state, COUNT(*) FROM sensory_events GROUP BY triage_state;"\'')
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    run_genesis()

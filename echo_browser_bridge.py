"""
echo_browser_bridge.py — Echo v1 Browser Ingestion Bridge
==========================================================
The browser's ONLY entry point into Echo.

Responsibilities (exactly one thing per layer):
  WebSocket handler  → accept connection, receive raw JSON, call buffer.push()
  SensoryBuffer      → fingerprint, deduplicate, WAL write, queue pressure check
  Everything else    → downstream. Not here.

The browser NEVER talks to:
  - ChromaDB
  - MemoryEngine
  - EchoKernel
  - TraceLogger

This is the airlock. It stays thin.

Usage:
  python3 echo_browser_bridge.py

Endpoints:
  ws://127.0.0.1:8765/ws      — browser extension WebSocket
  http://127.0.0.1:8765/status — queue health (GET)
  http://127.0.0.1:8765/tail   — last 10 events (GET)
"""

import os
import json
import uuid
import sqlite3
import hashlib
import asyncio
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

# =========================================================
# CONFIG
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "data", "sensory_buffer.db")

# Queue pressure thresholds (tuned for 16GB T14s with Ollama running)
BACKLOG_WARN    = 100    # log warning
BACKLOG_SLOW    = 500    # log critical, start discarding low-priority
BACKLOG_PAUSE   = 1000   # refuse new events until backlog drains

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BRIDGE] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bridge")


# =========================================================
# SCHEMA UPGRADE
# Extends the existing sensory_events table with:
#   fingerprint  — SHA-256 of payload, for dedup
#   priority     — 0 (normal) to 9 (urgent)
#   triage_state — pending / candidate / transient / discarded / promoted
# Runs safely on an existing DB (ALTER TABLE is idempotent via try/except)
# =========================================================

SCHEMA_BASE = """
CREATE TABLE IF NOT EXISTS sensory_events (
    event_id     TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    fingerprint  TEXT NOT NULL DEFAULT '',
    priority     INTEGER NOT NULL DEFAULT 0,
    received_at  TEXT NOT NULL,
    triage_state TEXT NOT NULL DEFAULT 'pending',
    promoted_at  TEXT,
    trace_id     TEXT
);
"""

# Applied after SCHEMA_BASE + migrations so they can safely reference new columns
SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_triage_state ON sensory_events(triage_state);
CREATE INDEX IF NOT EXISTS idx_fingerprint  ON sensory_events(fingerprint);
CREATE INDEX IF NOT EXISTS idx_received_at  ON sensory_events(received_at);
"""

# Columns added to existing DBs that were created without them
MIGRATIONS = [
    "ALTER TABLE sensory_events ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE sensory_events ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE sensory_events ADD COLUMN triage_state TEXT NOT NULL DEFAULT 'pending'",
]


def init_db(db_path: str) -> sqlite3.Connection:
    """
    Open a persistent connection with WAL mode enabled.
    WAL allows concurrent reads during writes — critical when the
    triage worker and the bridge are both active simultaneously.
    Initialized once at startup, not per-insert.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode and set synchronous=NORMAL
    # WAL: safe for concurrent access, faster than DELETE journal mode
    # NORMAL: fsync on checkpoint, not every write — acceptable for a queue
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript(SCHEMA_BASE)

    # Apply migrations for existing DBs (idempotent)
    for migration in MIGRATIONS:
        try:
            conn.execute(migration)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    return conn


# =========================================================
# FINGERPRINT + PRIORITY
# =========================================================

def compute_fingerprint(payload: Dict[str, Any]) -> str:
    STRIP_KEYS = {"timestamp", "t", "ts", "time", "scroll_depth"}
    stable = {k: v for k, v in payload.items() if k not in STRIP_KEYS}
    if "scroll_depth" in payload:
        stable["scroll_bucket"] = round(payload["scroll_depth"] * 4) / 4
    canonical = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def infer_priority(event_type: str, payload: Dict[str, Any]) -> int:
    """
    Assign a priority score 0–9 based on event type.
    Higher = more likely to be promoted by triage worker.

    Tune these as you observe real browser traffic.
    """
    rules = {
        "text_selection":  8,   # user selected text — high signal
        "page_load":       6,   # new page — medium signal
        "tab_change":      5,   # navigation — medium signal
        "tab_close":       3,   # low signal
        "scroll":          1,   # noise
        "focus_change":    1,   # noise
        "mousemove":       0,   # hard noise, should be filtered at source
    }
    base = rules.get(event_type, 4)

    # Boost if payload contains meaningful text
    text = payload.get("text", "") or payload.get("title", "") or ""
    if len(text) > 100:
        base = min(base + 2, 9)

    return base


# =========================================================
# BRIDGE BUFFER
# Thin wrapper around SQLite with the connection held open.
# =========================================================

class BridgeBuffer:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = asyncio.Lock()

    async def push(
        self,
        source:     str,
        event_type: str,
        payload:    Dict[str, Any],
    ) -> Optional[str]:
        """
        Write one event to the buffer.

        Returns event_id if accepted, None if:
          - fingerprint duplicate (exact same payload already pending)
          - queue pressure above BACKLOG_PAUSE
        """
        async with self._lock:

            # Queue pressure check
            backlog = self._backlog_count()
            if backlog >= BACKLOG_PAUSE:
                log.critical(
                    f"Queue at {backlog} — PAUSING ingestion. "
                    "Triage worker must drain before new events are accepted."
                )
                return None
            elif backlog >= BACKLOG_SLOW:
                log.warning(f"Queue pressure HIGH ({backlog}). Discarding low-priority events.")
                priority = infer_priority(event_type, payload)
                if priority < 4:
                    log.info(f"Discarding low-priority event: {event_type}")
                    return None

            fingerprint = compute_fingerprint(payload)

            # Dedup: if identical payload is already pending, skip
            existing = self._conn.execute(
                "SELECT event_id FROM sensory_events "
                "WHERE fingerprint = ? AND triage_state = 'pending' LIMIT 1",
                (fingerprint,),
            ).fetchone()
            if existing:
                log.debug(f"Dedup: {event_type} fingerprint {fingerprint[:12]}... already pending.")
                return None

            event_id  = str(uuid.uuid4())
            priority  = infer_priority(event_type, payload)

            # Server-side timestamp — never trust the browser clock
            # UTC ISO format, consistent with replay logic
            server_time = datetime.now(timezone.utc).isoformat()

            self._conn.execute(
                """
                INSERT INTO sensory_events
                  (event_id, source, event_type, payload, fingerprint,
                   priority, received_at, triage_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    event_id,
                    source,
                    event_type,
                    json.dumps(payload),
                    fingerprint,
                    priority,
                    server_time,
                ),
            )
            self._conn.commit()

            if backlog >= BACKLOG_WARN:
                log.warning(f"Queue backlog: {backlog + 1} pending events.")

            return event_id

    def _backlog_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM sensory_events WHERE triage_state = 'pending'"
        ).fetchone()
        return row[0] if row else 0

    def status(self) -> Dict[str, Any]:
        rows = self._conn.execute(
            "SELECT triage_state, COUNT(*) FROM sensory_events GROUP BY triage_state"
        ).fetchall()
        counts = {r[0]: r[1] for r in rows}
        backlog = counts.get("pending", 0)

        pressure = "ok"
        if backlog >= BACKLOG_PAUSE:
            pressure = "paused"
        elif backlog >= BACKLOG_SLOW:
            pressure = "high"
        elif backlog >= BACKLOG_WARN:
            pressure = "warn"

        return {
            "counts":   counts,
            "backlog":  backlog,
            "pressure": pressure,
            "thresholds": {
                "warn":  BACKLOG_WARN,
                "slow":  BACKLOG_SLOW,
                "pause": BACKLOG_PAUSE,
            },
        }

    def tail(self, n: int = 10) -> list:
        rows = self._conn.execute(
            """
            SELECT event_id, source, event_type, triage_state,
                   priority, fingerprint, received_at, trace_id
            FROM sensory_events
            ORDER BY received_at DESC LIMIT ?
            """,
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]


# =========================================================
# FASTAPI APP
# =========================================================

db_conn: Optional[sqlite3.Connection] = None
buffer:  Optional[BridgeBuffer]       = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_conn, buffer
    log.info(f"Opening WAL connection → {DB_PATH}")
    db_conn = init_db(DB_PATH)
    buffer  = BridgeBuffer(db_conn)
    log.info("Bridge ready. Waiting for browser connections on ws://127.0.0.1:8765/ws")
    yield
    if db_conn:
        db_conn.close()
    log.info("Bridge shut down.")


app = FastAPI(title="Echo Browser Bridge", version="1.0", lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client = websocket.client
    log.info(f"Browser connected: {client}")

    accepted = 0
    rejected = 0

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("Received non-JSON payload — ignored.")
                continue

            event_type = event.get("type", "unknown")
            payload    = event.get("data", {})

            event_id = await buffer.push("browser", event_type, payload)

            if event_id:
                accepted += 1
                await websocket.send_text(json.dumps({
                    "status":   "accepted",
                    "event_id": event_id,
                }))
            else:
                rejected += 1
                await websocket.send_text(json.dumps({
                    "status": "rejected",
                    "reason": "duplicate or queue pressure",
                }))

    except WebSocketDisconnect:
        log.info(
            f"Browser disconnected. Session: {accepted} accepted, {rejected} rejected."
        )


@app.get("/status")
async def get_status():
    return JSONResponse(buffer.status())


@app.get("/tail")
async def get_tail(n: int = 10):
    rows = buffer.tail(n)
    # Truncate fingerprint for readability
    for r in rows:
        r["fingerprint"] = r["fingerprint"][:16] + "..."
    return JSONResponse({"events": rows})


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    uvicorn.run(
        "echo_browser_bridge:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        reload=False,
    )

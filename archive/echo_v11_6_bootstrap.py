"""
echo_v11_6_bootstrap.py
========================
Self-contained bootstrap for Echo v11.6.

Builds the full data-flow hierarchy:

  Sensory Layer  (SQLite)  — raw events, fast writes, mutable
  Cognitive Layer (Kernel) — stateless, pure, injected context only
  Historical Layer (JSONL) — immutable append-only trace, the black box

Usage:
  python3 echo_v11_6_bootstrap.py            # create structure + run diagnostics
  python3 echo_v11_6_bootstrap.py inject     # inject a test event into SQLite
  python3 echo_v11_6_bootstrap.py promote    # promote oldest pending event through Kernel
  python3 echo_v11_6_bootstrap.py replay     # replay last JSONL trace (no SQLite touch)
  python3 echo_v11_6_bootstrap.py audit      # show SQLite buffer + JSONL tail

Requires: echo_memory.py in the same directory (already in ~/vision_assistant/)
"""

import os
import sys
import json
import uuid
import sqlite3
import hashlib
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, Optional, List

# Import the memory layer built in Phase B
from echo_memory import MemoryContext, MemoryEngine, MockDBBackend

# =========================================================
# PROJECT STRUCTURE
# =========================================================

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
LOGS_DIR   = os.path.join(BASE_DIR, "logs")
DB_PATH    = os.path.join(DATA_DIR, "sensory_buffer.db")
TRACE_PATH = os.path.join(LOGS_DIR, "event_trace.jsonl")

def ensure_structure():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)


# =========================================================
# SQLITE SENSORY BUFFER
# "Short-Term Memory" — high-churn, mutable, pre-Kernel
# =========================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS sensory_events (
    event_id     TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    promoted_at  TEXT,
    trace_id     TEXT
);

CREATE INDEX IF NOT EXISTS idx_status ON sensory_events(status);
CREATE INDEX IF NOT EXISTS idx_source ON sensory_events(source);
"""

class SensoryBuffer:
    """
    SQLite-backed event queue.

    Lifecycle of an event:
      pending   → received, awaiting triage
      promoted  → sent to Kernel, trace_id linked
      discarded → filtered out by triage (noise, duplicate, low-signal)
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)

    def push(
        self,
        source: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> str:
        """
        Write a raw event to the buffer. Returns the new event_id.
        This is the only write path — nothing else inserts into SQLite.
        """
        event_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sensory_events
                  (event_id, source, event_type, payload, received_at, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (
                    event_id,
                    source,
                    event_type,
                    json.dumps(payload),
                    datetime.now().isoformat(),
                ),
            )
        return event_id

    def pop_oldest_pending(self) -> Optional[Dict[str, Any]]:
        """
        Fetch the oldest pending event without removing it.
        Returns None if the buffer is empty.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM sensory_events
                WHERE status = 'pending'
                ORDER BY received_at ASC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def mark_promoted(self, event_id: str, trace_id: str):
        """
        Link the SQLite event to its JSONL trace entry.
        This is the permanent cross-reference between the two layers.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE sensory_events
                SET status = 'promoted',
                    promoted_at = ?,
                    trace_id = ?
                WHERE event_id = ?
                """,
                (datetime.now().isoformat(), trace_id, event_id),
            )

    def mark_discarded(self, event_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sensory_events SET status = 'discarded' WHERE event_id = ?",
                (event_id,),
            )

    def counts(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM sensory_events GROUP BY status"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def tail(self, n: int = 5) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT event_id, source, event_type, status, received_at, trace_id
                FROM sensory_events
                ORDER BY received_at DESC LIMIT ?
                """,
                (n,),
            ).fetchall()
        return [dict(r) for r in rows]


# =========================================================
# EXECUTION CONTEXT  (immutable, injected per cycle)
# =========================================================

@dataclass(frozen=True)
class ExecutionContext:
    replay_mode:       bool             = False
    frozen_time:       Optional[str]    = None
    frozen_state:      Optional[Dict]   = None
    deterministic_seed: int             = 42
    model_name:        str              = "phi4-mini"
    quantization:      str              = "Q4_K_M"
    backend:           str              = "llama.cpp"
    backend_version:   str              = "0.3.5"


# =========================================================
# TRACE ENTRY  (JSONL black box)
# =========================================================

@dataclass
class TraceEntry:
    trace_id:       str
    event_id:       str               # permanent link back to SQLite row
    timestamp:      str
    event:          Dict[str, Any]
    state_snapshot: Dict[str, Any]
    memory_context: Dict[str, Any]    # sealed MemoryContext, includes hash
    kernel_decision: Dict[str, Any]
    prompt_version: str
    model_info:     Dict[str, Any]
    risk_level:     str = "green"

    def to_json(self) -> Dict:
        return asdict(self)


class TraceLogger:

    def __init__(self, path: str = TRACE_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, trace: TraceEntry):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace.to_json()) + "\n")

    def load_last(self) -> Optional[Dict]:
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        return json.loads(lines[-1]) if lines else None

    def count(self) -> int:
        if not os.path.exists(self.path):
            return 0
        with open(self.path, "r", encoding="utf-8") as f:
            return sum(1 for l in f if l.strip())


# =========================================================
# KERNEL  (stateless, pure)
# =========================================================

class EchoKernel:

    def process(
        self,
        event:          Dict[str, Any],
        memory_context: MemoryContext,
        ctx:            ExecutionContext,
        state:          Dict[str, Any],
    ) -> Dict[str, Any]:

        timestamp = ctx.frozen_time if ctx.replay_mode else datetime.now().isoformat()

        return {
            "approved":   True,
            "response":   "Cognition stable.",
            "tool_calls": [
                {"tool": "system_monitor", "params": {"action": "report_cpu"}}
            ],
            "risk_level": "green",
            "reasoning_trace": {
                "timestamp_used":   timestamp,
                "active_window":    state.get("active_window"),
                "memory_hash_used": memory_context.memory_hash,
                "config": {
                    "temperature": 0.0 if ctx.replay_mode else 0.4,
                    "seed":        ctx.deterministic_seed,
                },
            },
        }


# =========================================================
# MOCK STATE PROVIDER
# Replace with psutil calls when wiring into real Echo
# =========================================================

class MockStateProvider:

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "cpu_percent":    32,
            "ram_percent":    68,
            "active_window":  "Firefox",
            "active_project": "Echo",
            "thermal_state":  "normal",
        }


# =========================================================
# ORCHESTRATOR
# The only component that touches both SQLite and JSONL
# =========================================================

class EchoOrchestrator:

    def __init__(self, db_backend=None):
        self.kernel         = EchoKernel()
        self.memory_engine  = MemoryEngine(db_backend=db_backend or MockDBBackend())
        self.state_provider = MockStateProvider()
        self.logger         = TraceLogger()
        self.buffer         = SensoryBuffer()

    def promote_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Promote a raw SQLite event through the full cognition cycle.

        1. Snapshot state
        2. Recall memory (live)
        3. Kernel decides
        4. Fossilize to JSONL
        5. Mark SQLite row as promoted with trace_id link
        """
        event_id = raw_event["event_id"]
        payload  = json.loads(raw_event["payload"])

        kernel_event = {
            "source":     raw_event["source"],
            "event_type": raw_event["event_type"],
            "timestamp":  raw_event["received_at"],
            "payload":    payload,
        }

        state = self.state_provider.get_snapshot()
        ctx   = ExecutionContext(frozen_state=state, frozen_time=raw_event["received_at"])

        memory   = self.memory_engine.recall(kernel_event, state)
        decision = self.kernel.process(kernel_event, memory, ctx, state)

        trace = TraceEntry(
            trace_id        = str(uuid.uuid4()),
            event_id        = event_id,
            timestamp       = raw_event["received_at"],
            event           = kernel_event,
            state_snapshot  = state,
            memory_context  = memory.to_dict(),
            kernel_decision = decision,
            prompt_version  = "v11.6",
            model_info      = {
                "model":           ctx.model_name,
                "quantization":    ctx.quantization,
                "backend":         ctx.backend,
                "backend_version": ctx.backend_version,
            },
            risk_level = decision["risk_level"],
        )

        self.logger.log(trace)
        self.buffer.mark_promoted(event_id, trace.trace_id)

        return decision

    def replay_trace(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        """
        Replay a JSONL trace entry. Never touches SQLite.
        Verifies memory hash integrity before proceeding.
        """
        injected = trace["memory_context"]
        replay_event = {
            **trace["event"],
            "state_snapshot": trace["state_snapshot"],
            "timestamp":      trace["timestamp"],
        }

        frozen_state = trace["state_snapshot"]
        ctx = ExecutionContext(
            replay_mode  = True,
            frozen_time  = trace["timestamp"],
            frozen_state = frozen_state,
        )

        memory   = self.memory_engine.recall(
            replay_event, frozen_state,
            replay_mode=True, injected_context=injected,
        )
        decision = self.kernel.process(replay_event, memory, ctx, frozen_state)

        return decision


# =========================================================
# DIAGNOSTIC RUNNER
# =========================================================

def run_diagnostics():
    print("\n" + "=" * 60)
    print("  Echo v11.6 — Diagnostic Runner")
    print("=" * 60)

    orch = EchoOrchestrator()

    # --- Test 1: Silence (null state) ---
    print("\n[1/3] Silence Test — empty buffer, null stable state")
    counts = orch.buffer.counts()
    total  = sum(counts.values())
    if total == 0:
        print("   ✅ Buffer is empty. Null-stable state confirmed.")
    else:
        print(f"   ℹ️  Buffer has {total} existing event(s): {counts}")

    trace_count = orch.logger.count()
    print(f"   ℹ️  JSONL trace contains {trace_count} existing entries.")

    # --- Test 2: Inject → Promote → Verify link ---
    print("\n[2/3] Memory Test — inject one event, promote, verify SQLite↔JSONL link")

    event_id = orch.buffer.push(
        source     = "diagnostic",
        event_type = "intent",
        payload    = {"command": "diagnostic self-check"},
    )
    print(f"   Injected event_id : {event_id[:16]}...")

    raw = orch.buffer.pop_oldest_pending()
    assert raw is not None, "Buffer should have a pending event"
    assert raw["event_id"] == event_id

    decision = orch.promote_event(raw)
    print(f"   Kernel decision   : {decision['risk_level']} / approved={decision['approved']}")

    # Verify the link
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status, trace_id FROM sensory_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "promoted", f"Expected 'promoted', got '{row[0]}'"
    assert row[1] is not None,   "trace_id should be set after promotion"
    print(f"   SQLite status     : {row[0]}")
    print(f"   Linked trace_id   : {row[1][:16]}...")
    print("   ✅ SQLite↔JSONL link verified.")

    # --- Test 3: Replay without touching SQLite ---
    print("\n[3/3] Determinism Test — replay last trace, no SQLite access")

    last_trace = orch.logger.load_last()
    assert last_trace is not None

    original_hash  = last_trace["memory_context"]["memory_hash"]
    original_calls = last_trace["kernel_decision"]["tool_calls"]

    replay_decision = orch.replay_trace(last_trace)
    replay_hash     = replay_decision["reasoning_trace"]["memory_hash_used"]
    replay_calls    = replay_decision["tool_calls"]

    assert original_hash  == replay_hash,  "Memory hash drifted during replay"
    assert original_calls == replay_calls, "Tool calls drifted during replay"

    print(f"   Original hash  : {original_hash[:32]}...")
    print(f"   Replay hash    : {replay_hash[:32]}...")
    print(f"   Tool calls     : stable ✅")
    print("   ✅ Deterministic replay confirmed. SQLite not touched.\n")

    print("=" * 60)
    print("  ✅ ALL DIAGNOSTICS PASSED")
    print("  SQLite sensory buffer: operational")
    print("  JSONL black box:       operational")
    print("  Deterministic replay:  operational")
    print("  SQLite↔JSONL link:     operational")
    print("=" * 60 + "\n")


# =========================================================
# CLI COMMANDS
# =========================================================

def cmd_inject():
    buf      = SensoryBuffer()
    event_id = buf.push(
        source     = "cli",
        event_type = "intent",
        payload    = {"command": "what is my cpu usage?"},
    )
    print(f"✅ Injected event: {event_id}")
    print(f"   Buffer counts: {buf.counts()}")


def cmd_promote():
    orch = EchoOrchestrator()
    raw  = orch.buffer.pop_oldest_pending()
    if raw is None:
        print("⚠️  No pending events in buffer. Run: python3 echo_v11_6_bootstrap.py inject")
        return
    print(f"Promoting event_id: {raw['event_id'][:16]}...")
    decision = orch.promote_event(raw)
    print(f"✅ Promoted. Decision: {decision['risk_level']} / {decision['response']}")


def cmd_replay():
    orch  = EchoOrchestrator()
    trace = orch.logger.load_last()
    if trace is None:
        print("⚠️  No traces in JSONL yet. Run inject + promote first.")
        return
    print(f"Replaying trace_id : {trace['trace_id'][:16]}...")
    print(f"Original hash      : {trace['memory_context']['memory_hash'][:32]}...")
    replay = orch.replay_trace(trace)
    replay_hash = replay["reasoning_trace"]["memory_hash_used"]
    drift = trace["kernel_decision"]["tool_calls"] != replay["tool_calls"]
    print(f"Replay hash        : {replay_hash[:32]}...")
    print(f"Decision drift     : {'❌ YES' if drift else '✅ NONE'}")


def cmd_audit():
    buf   = SensoryBuffer()
    orch  = EchoOrchestrator()
    print("\n── SQLite Buffer ──────────────────────────────")
    print(f"Counts : {buf.counts()}")
    for row in buf.tail(5):
        print(f"  [{row['status']:10}] {row['event_id'][:8]}... "
              f"{row['source']}/{row['event_type']} "
              f"trace→{row['trace_id'][:8] if row['trace_id'] else 'none'}")
    print("\n── JSONL Trace (last 3) ───────────────────────")
    count = orch.logger.count()
    print(f"Total entries: {count}")
    if os.path.exists(TRACE_PATH):
        with open(TRACE_PATH) as f:
            lines = [l for l in f if l.strip()]
        for line in lines[-3:]:
            t = json.loads(line)
            print(f"  trace_id={t['trace_id'][:8]}... "
                  f"event_id={t.get('event_id', 'legacy')[:8]}... "
                  f"hash={t['memory_context']['memory_hash'][:16]}... "
                  f"risk={t['risk_level']}")
    print()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    ensure_structure()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "diagnose"

    if cmd == "inject":
        cmd_inject()
    elif cmd == "promote":
        cmd_promote()
    elif cmd == "replay":
        cmd_replay()
    elif cmd == "audit":
        cmd_audit()
    else:
        run_diagnostics()

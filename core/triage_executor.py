"""
core/triage_executor.py — Echo v1 Triage Heartbeat
====================================================
Standalone process. Runs independently from the browser bridge.
If the bridge crashes, this keeps ticking through the backlog.

One clock tick:
  1. Fetch PENDING events that have aged past the dwell threshold
  2. Score each event (deterministic, rule-based — no LLM)
  3. Transition:
       score >= threshold → CANDIDATE → promote through Orchestrator
       score <  threshold → DISCARDED
  4. Promoted events get a trace_id linking SQLite ↔ JSONL (causal chain preserved)
  5. Sleep 1 second (thermal control for T14s)

Two modes (set in config/triage_config.json):
  "mode": "dev"   → dwell=500ms, process immediately, good for testing
  "mode": "prod"  → dwell=45s,   events must age before judgment

Usage:
  python3 core/triage_executor.py
  python3 core/triage_executor.py --dev     (force dev mode)
  python3 core/triage_executor.py --once    (one tick then exit, for testing)
"""

import os
import sys
import json
import time
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

# Add parent directory to path so we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echo_v11_6_bootstrap import EchoOrchestrator, SensoryBuffer, TraceLogger
from echo_v1_genesis import Metabolism

# =========================================================
# PATHS
# =========================================================

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "triage_config.json")
DB_PATH     = os.path.join(BASE_DIR, "data", "sensory_buffer.db")
TRACES_DIR  = os.path.join(BASE_DIR, "traces")

os.makedirs(TRACES_DIR, exist_ok=True)


# =========================================================
# SIGNAL SCORING
# Deterministic, rule-based — no LLM involved.
# Returns a float. Threshold from config (default 1.5).
# =========================================================

# Base weights per event type
SIGNAL_WEIGHTS = {
    "text_selection":     2.0,   # user selected text — highest signal
    "page_load":          1.5,   # navigation complete — high signal
    "navigation_complete": 1.5,
    "tab_change":         1.0,   # switched tabs — medium signal
    "tab_switch":         1.0,
    "tab_close":          0.5,   # low signal
    "focus_change":       0.3,
    "scroll":             0.2,   # noise
    "mousemove":          0.0,   # hard noise
}

def score_event(event_type: str, payload: Dict[str, Any]) -> float:
    """
    Deterministic signal score for one event.
    Base weight + bonuses for content richness.
    """
    base = SIGNAL_WEIGHTS.get(event_type, 0.5)

    # Bonus: payload contains meaningful text (article reading, selection)
    text = payload.get("text", "") or payload.get("title", "") or ""
    if len(text) > 200:
        base += 0.8
    elif len(text) > 50:
        base += 0.3

    # Bonus: URL looks like an article (has a path beyond root)
    url = payload.get("url", "")
    if url and len(url.split("/")) > 4:
        base += 0.2

    return round(base, 3)


# =========================================================
# TRIAGE EXECUTOR
# =========================================================

class TriageExecutor:

    MAINTENANCE_INTERVAL = 300   # run Metabolism every 5 minutes

    def __init__(self, config_path: str = CONFIG_PATH, dev_mode: bool = False):
        with open(config_path) as f:
            self.config = json.load(f)

        mode = "dev" if dev_mode else self.config.get("mode", "prod")

        if mode == "dev":
            self.dwell_ms = 500       # 0.5s — process almost immediately
        else:
            self.dwell_ms = int(self.config.get("dwell_threshold_sec", 45) * 1000)

        self.promotion_threshold = self.config.get("promotion_threshold", 1.5)
        self.batch_size          = 100
        self.mode                = mode

        # Wire into the proven orchestration stack
        # Orchestrator owns: Kernel, MemoryEngine, TraceLogger, SensoryBuffer
        self.orchestrator = EchoOrchestrator()
        self.metabolism   = Metabolism(DB_PATH)

        self._last_maintenance = time.time()
        self._total_processed  = 0
        self._total_promoted   = 0
        self._total_discarded  = 0
        self._tick_count       = 0

    # ----------------------------------------------------------
    # One clock cycle
    # ----------------------------------------------------------

    def tick(self) -> Tuple[int, int]:
        """
        Process one batch of ripened pending events.
        Returns (processed, promoted).
        """
        now_ms  = int(datetime.now(timezone.utc).timestamp() * 1000)
        cutoff  = now_ms - self.dwell_ms

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")

            batch = conn.execute(
                """
                SELECT * FROM sensory_events
                WHERE triage_state = 'pending'
                  AND (created_at_ms IS NULL OR created_at_ms < ?)
                ORDER BY created_at_ms ASC
                LIMIT ?
                """,
                (cutoff, self.batch_size),
            ).fetchall()

        processed = len(batch)
        promoted  = 0

        for row in batch:
            row_dict = dict(row)
            try:
                payload    = json.loads(row_dict.get("payload", "{}"))
                event_type = row_dict.get("event_type", "unknown")
                score      = score_event(event_type, payload)

                if score >= self.promotion_threshold:
                    self._promote(row_dict, score)
                    promoted += 1
                else:
                    self._discard(row_dict, score)

            except Exception as e:
                self._mark_errored(row_dict, str(e))

        self._total_processed += processed
        self._total_promoted  += promoted
        self._total_discarded += (processed - promoted)
        self._tick_count      += 1

        # Periodic maintenance
        if time.time() - self._last_maintenance > self.MAINTENANCE_INTERVAL:
            self._run_maintenance()

        return processed, promoted

    # ----------------------------------------------------------
    # Promotion — wires through EchoOrchestrator to preserve
    # the SQLite↔JSONL causal link (trace_id)
    # ----------------------------------------------------------

    def _promote(self, row: Dict[str, Any], score: float):
        """
        Promote through the Orchestrator.
        This maintains the trace_id link and writes to JSONL.
        """
        # Orchestrator.promote_event() expects the raw SQLite row format
        decision = self.orchestrator.promote_event(row)

        # The orchestrator already called mark_promoted() and wrote JSONL.
        # Additionally write a human-readable summary to traces/
        self._write_trace_summary(row, score, decision)

    def _discard(self, row: Dict[str, Any], score: float):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE sensory_events SET triage_state = 'discarded', "
                "triage_reason = ? WHERE event_id = ?",
                (f"score_{score}_below_threshold_{self.promotion_threshold}",
                 row["event_id"]),
            )

    def _mark_errored(self, row: Dict[str, Any], error: str):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE sensory_events SET triage_state = 'errored', "
                "triage_reason = ? WHERE event_id = ?",
                (f"error: {error[:120]}", row["event_id"]),
            )

    # ----------------------------------------------------------
    # Trace summary (human-readable, separate from JSONL black box)
    # ----------------------------------------------------------

    def _write_trace_summary(
        self,
        row:      Dict[str, Any],
        score:    float,
        decision: Dict[str, Any],
    ):
        summary_path = os.path.join(TRACES_DIR, "promoted_events.jsonl")
        entry = {
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "event_id":   row["event_id"],
            "event_type": row["event_type"],
            "source":     row["source"],
            "score":      score,
            "payload":    json.loads(row.get("payload", "{}")),
            "risk_level": decision.get("risk_level", "unknown"),
        }
        with open(summary_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # ----------------------------------------------------------
    # Maintenance
    # ----------------------------------------------------------

    def _run_maintenance(self):
        report = self.metabolism.run_maintenance()
        if report["total_deleted"] > 0:
            print(
                f"  🧹 Metabolism: deleted {report['total_deleted']} "
                f"(temporal={report['temporal_deleted']}, "
                f"volumetric={report['volumetric_deleted']})"
            )
        self._last_maintenance = time.time()

    # ----------------------------------------------------------
    # Stats
    # ----------------------------------------------------------

    def _queue_counts(self) -> Dict[str, int]:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT triage_state, COUNT(*) FROM sensory_events GROUP BY triage_state"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def _compression_ratio(self) -> str:
        if self._total_promoted == 0:
            return "∞ (no promotions yet)"
        ratio = self._total_processed / self._total_promoted
        return f"{ratio:.1f}:1"

    # ----------------------------------------------------------
    # Run loop
    # ----------------------------------------------------------

    def run_forever(self):
        print(f"\n💓 Triage Heartbeat Active")
        print(f"   Mode      : {self.mode}")
        print(f"   Dwell     : {self.dwell_ms}ms")
        print(f"   Threshold : {self.promotion_threshold}")
        print(f"   DB        : {DB_PATH}\n")

        while True:
            try:
                processed, promoted = self.tick()

                if processed > 0:
                    counts = self._queue_counts()
                    print(
                        f"  [{datetime.now().strftime('%H:%M:%S')}] "
                        f"Tick #{self._tick_count:04d} | "
                        f"Processed={processed:3d} | "
                        f"Promoted={promoted:3d} | "
                        f"Discarded={processed - promoted:3d} | "
                        f"Pending={counts.get('pending', 0):4d} | "
                        f"Compression={self._compression_ratio()}"
                    )

                time.sleep(1)   # thermal control

            except KeyboardInterrupt:
                self._print_summary()
                break
            except Exception as e:
                print(f"  ❌ Tick error: {e}")
                time.sleep(2)

    def run_once(self):
        """Single tick — for testing."""
        print(f"💓 Single tick (mode={self.mode}, dwell={self.dwell_ms}ms)")
        processed, promoted = self.tick()
        counts = self._queue_counts()
        print(f"   Processed : {processed}")
        print(f"   Promoted  : {promoted}")
        print(f"   Discarded : {processed - promoted}")
        print(f"   Queue now : {counts}")
        print(f"   Ratio     : {self._compression_ratio()}")

        # Show what got promoted
        summary_path = os.path.join(TRACES_DIR, "promoted_events.jsonl")
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                lines = f.readlines()
            print(f"\n   Promoted events ({len(lines)} total in traces/):")
            for line in lines[-5:]:
                e = json.loads(line)
                print(f"     [{e['event_type']:18}] score={e['score']} | "
                      f"{str(e['payload'])[:60]}...")

    def _print_summary(self):
        print(f"\n── Heartbeat Summary ──────────────────────────────")
        print(f"   Ticks          : {self._tick_count}")
        print(f"   Total processed: {self._total_processed}")
        print(f"   Total promoted : {self._total_promoted}")
        print(f"   Total discarded: {self._total_discarded}")
        print(f"   Compression    : {self._compression_ratio()}")
        counts = self._queue_counts()
        print(f"   Final queue    : {counts}")


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    dev_mode = "--dev" in sys.argv
    once     = "--once" in sys.argv

    executor = TriageExecutor(dev_mode=dev_mode)

    if once:
        executor.run_once()
    else:
        executor.run_forever()

"""
echo_memory.py — Echo v11.6 Memory Layer
=========================================
Implements the Memory Sandbox contract:

  Live Mode:   DB.query() → rank → compute hash → return MemoryContext
  Replay Mode: deserialize fossilized context → verify hash → return as-is
  Drift Audit: (optional, post-replay) compare live fingerprint vs fossilized

Three guarantees:
  1. Isolation   — no DB.query() calls fire during replay_mode=True
  2. Completeness — TraceEntry contains every byte the Kernel saw
  3. Provenance  — each memory record carries its query string + similarity score
"""

import json
import hashlib
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional


# =========================================================
# RETRIEVAL RECORD
# Carries full provenance for a single retrieved memory.
# =========================================================

@dataclass
class RetrievalRecord:
    """One entry from a DB query result."""

    doc_id: str
    summary: str
    similarity_score: float     # cosine or dot-product, 0.0–1.0
    source: str                 # e.g. "episodic", "semantic", "graph"
    retrieval_query: str        # the exact query string that produced this

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RetrievalRecord":
        return cls(**d)


# =========================================================
# MEMORY CONTEXT
# The complete memory payload passed to the Kernel.
# This entire structure is fossilized in TraceEntry.
# =========================================================

@dataclass
class MemoryContext:

    # --- Content fields (hashed for drift detection) ---
    episodic:        List[RetrievalRecord] = field(default_factory=list)
    semantic:        List[RetrievalRecord] = field(default_factory=list)
    graph_neighbors: List[RetrievalRecord] = field(default_factory=list)

    active_goals:  List[str] = field(default_factory=list)
    constraints:   List[str] = field(default_factory=list)

    # --- Metadata fields (not hashed, excluded from content hash) ---
    confidence:          float = 0.0
    retrieval_latency_ms: float = 0.0
    compression_model:   str = "phi4-mini"

    # --- Provenance identity ---
    # Computed from content fields only. Set after construction.
    memory_hash: str = ""

    def compute_hash(self) -> str:
        """
        SHA-256 over the stable content fields.

        Excludes latency, compression_model, and memory_hash itself
        so the hash reflects *what the Kernel saw*, not *how fast
        we retrieved it*.

        Lists are sorted by doc_id for stability — insertion order
        from the DB must not affect the fingerprint.
        """
        content = {
            "episodic": sorted(
                [r.to_dict() for r in self.episodic],
                key=lambda x: x["doc_id"]
            ),
            "semantic": sorted(
                [r.to_dict() for r in self.semantic],
                key=lambda x: x["doc_id"]
            ),
            "graph_neighbors": sorted(
                [r.to_dict() for r in self.graph_neighbors],
                key=lambda x: x["doc_id"]
            ),
            "active_goals": sorted(self.active_goals),
            "constraints":  sorted(self.constraints),
        }
        serialized = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def seal(self) -> "MemoryContext":
        """
        Compute and store the hash in-place.
        Call this once, after retrieval, before passing to the Kernel.
        Returns self for chaining.
        """
        self.memory_hash = self.compute_hash()
        return self

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Ensure RetrievalRecord lists serialize correctly
        for key in ("episodic", "semantic", "graph_neighbors"):
            d[key] = [r.to_dict() if isinstance(r, RetrievalRecord) else r
                      for r in getattr(self, key)]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryContext":
        """
        Deserialize a fossilized MemoryContext from a TraceEntry.
        Used exclusively in replay mode — no DB access.
        """
        def parse_records(lst):
            return [
                RetrievalRecord.from_dict(r) if isinstance(r, dict) else r
                for r in lst
            ]

        return cls(
            episodic        = parse_records(d.get("episodic", [])),
            semantic        = parse_records(d.get("semantic", [])),
            graph_neighbors = parse_records(d.get("graph_neighbors", [])),
            active_goals    = d.get("active_goals", []),
            constraints     = d.get("constraints", []),
            confidence          = d.get("confidence", 0.0),
            retrieval_latency_ms = d.get("retrieval_latency_ms", 0.0),
            compression_model   = d.get("compression_model", "phi4-mini"),
            memory_hash     = d.get("memory_hash", ""),
        )

    def verify_integrity(self) -> bool:
        """
        Recompute the hash and compare against the stored value.
        Returns True if the fossilized context is unmodified.
        """
        return self.memory_hash == self.compute_hash()


# =========================================================
# MEMORY ENGINE
# =========================================================

class MemoryEngine:
    """
    Stateless retrieval interface.

    In live mode:  queries the backend DB, ranks results, seals the context.
    In replay mode: deserializes the fossilized context, verifies integrity,
                    raises IsolationViolation if any live DB call would fire.
    """

    class IsolationViolation(RuntimeError):
        """Raised if replay mode tries to reach a live DB."""
        pass

    class IntegrityError(RuntimeError):
        """Raised if a fossilized context fails hash verification."""
        pass

    def __init__(self, db_backend=None):
        """
        db_backend: any object with a .query(text, n_results) method
                    returning List[RetrievalRecord].
                    Pass None to use the MockDBBackend (for testing).
        """
        self._db = db_backend or MockDBBackend()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def recall(
        self,
        event: Dict[str, Any],
        state: Dict[str, Any],
        replay_mode: bool = False,
        injected_context: Optional[Dict[str, Any]] = None,
    ) -> MemoryContext:
        """
        Central dispatch:

          replay_mode=False, injected_context=None  → live query
          replay_mode=True,  injected_context={...} → fossilized replay
          replay_mode=True,  injected_context=None  → IsolationViolation
        """
        if replay_mode:
            return self._recall_frozen(injected_context)
        else:
            return self._recall_live(event, state)

    def live_fingerprint(
        self,
        event: Dict[str, Any],
        state: Dict[str, Any],
    ) -> str:
        """
        Query the live DB and return only the hash — no side effects.
        Used by DriftAuditor to compare against a fossilized hash
        without replacing the frozen memory context.
        """
        ctx = self._recall_live(event, state)
        return ctx.memory_hash

    # ----------------------------------------------------------
    # Private: live path
    # ----------------------------------------------------------

    def _recall_live(
        self,
        event: Dict[str, Any],
        state: Dict[str, Any],
    ) -> MemoryContext:

        import time
        query_text = event.get("payload", {}).get("command", "")

        t0 = time.perf_counter()

        episodic        = self._db.query(query_text, source="episodic",  n_results=5)
        semantic        = self._db.query(query_text, source="semantic",  n_results=5)
        graph_neighbors = self._db.query(query_text, source="graph",     n_results=3)

        latency_ms = (time.perf_counter() - t0) * 1000

        goals, constraints = self._derive_goals_and_constraints(
            episodic + semantic, state
        )

        ctx = MemoryContext(
            episodic        = episodic,
            semantic        = semantic,
            graph_neighbors = graph_neighbors,
            active_goals    = goals,
            constraints     = constraints,
            confidence      = self._compute_confidence(episodic + semantic),
            retrieval_latency_ms = round(latency_ms, 2),
        )

        return ctx.seal()

    # ----------------------------------------------------------
    # Private: replay path
    # ----------------------------------------------------------

    def _recall_frozen(
        self,
        injected_context: Optional[Dict[str, Any]],
    ) -> MemoryContext:
        """
        Deserialize a fossilized context. No DB calls. Ever.
        """
        if injected_context is None:
            raise MemoryEngine.IsolationViolation(
                "replay_mode=True but no injected_context provided. "
                "The live DB must not be queried during replay. "
                "Pass the memory_context block from the TraceEntry."
            )

        ctx = MemoryContext.from_dict(injected_context)

        if not ctx.verify_integrity():
            raise MemoryEngine.IntegrityError(
                f"Fossilized memory_hash mismatch. "
                f"Stored: {ctx.memory_hash[:16]}... "
                f"Computed: {ctx.compute_hash()[:16]}... "
                "The TraceEntry may have been modified after logging."
            )

        return ctx

    # ----------------------------------------------------------
    # Private: helpers
    # ----------------------------------------------------------

    def _compute_confidence(self, records: List[RetrievalRecord]) -> float:
        if not records:
            return 0.0
        return round(
            sum(r.similarity_score for r in records) / len(records), 4
        )

    def _derive_goals_and_constraints(
        self,
        records: List[RetrievalRecord],
        state: Dict[str, Any],
    ):
        # Stub — replace with your real goal extraction logic.
        goals = ["Deterministic replay", "Stable cognition"]
        constraints = ["No live DB during replay", "No datetime.now() during replay"]
        return goals, constraints


# =========================================================
# DRIFT AUDITOR
# =========================================================

class DriftAuditor:
    """
    Post-replay analysis tool.

    Compares the memory fingerprint fossilized in a TraceEntry against
    what the live DB would return today for the same event.

    This is the ONLY place the live DB is queried in an audit context.
    It does not affect the replay result — it only reports divergence.
    """

    def __init__(self, memory_engine: MemoryEngine):
        self._engine = memory_engine

    def audit(
        self,
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Returns a drift report dict:
          {
            "drift_detected": bool,
            "fossilized_hash": str,
            "live_hash": str,
            "event_type": str,
            "timestamp": str,
          }
        """
        fossilized_hash = trace["memory_context"].get("memory_hash", "")

        live_hash = self._engine.live_fingerprint(
            event=trace["event"],
            state=trace["state_snapshot"],
        )

        drift = fossilized_hash != live_hash

        report = {
            "drift_detected":  drift,
            "fossilized_hash": fossilized_hash,
            "live_hash":       live_hash,
            "event_type":      trace["event"].get("event_type", "unknown"),
            "timestamp":       trace["timestamp"],
        }

        self._print_report(report)
        return report

    def _print_report(self, report: Dict[str, Any]):
        print("\n===== DRIFT AUDIT =====")
        if report["drift_detected"]:
            print("⚠️  RETRIEVAL DRIFT DETECTED")
            print(f"   Fossilized : {report['fossilized_hash'][:32]}...")
            print(f"   Live DB    : {report['live_hash'][:32]}...")
            print("   The vector space has changed since this trace was recorded.")
            print("   Kernel replay result may differ from original decision.")
        else:
            print("✅ MEMORY STABLE — live DB matches fossilized context.")
        print(f"   Event      : {report['event_type']}")
        print(f"   Timestamp  : {report['timestamp']}")


# =========================================================
# MOCK DB BACKEND
# Replace with your ChromaDB / SQLite-vec / Ollama-embed adapter.
# =========================================================

class MockDBBackend:
    """
    Deterministic stub for testing.
    Returns fixed records keyed by source.
    Swap this out for your real vector DB adapter.
    """

    _RECORDS = {
        "episodic": [
            RetrievalRecord(
                doc_id="ep_001",
                summary="User researched browser tab triage patterns",
                similarity_score=0.91,
                source="episodic",
                retrieval_query="",
            ),
            RetrievalRecord(
                doc_id="ep_002",
                summary="Echo v11.5 replay test passed on T14s",
                similarity_score=0.87,
                source="episodic",
                retrieval_query="",
            ),
        ],
        "semantic": [
            RetrievalRecord(
                doc_id="sem_001",
                summary="Deterministic cognition requires frozen state",
                similarity_score=0.95,
                source="semantic",
                retrieval_query="",
            ),
        ],
        "graph": [
            RetrievalRecord(
                doc_id="graph_001",
                summary="Echo_v11_6 → MemoryEngine → DriftAuditor",
                similarity_score=0.78,
                source="graph",
                retrieval_query="",
            ),
        ],
    }

    def query(
        self,
        query_text: str,
        source: str,
        n_results: int = 5,
    ) -> List[RetrievalRecord]:
        records = self._RECORDS.get(source, [])[:n_results]
        # Stamp the query string into provenance
        return [
            RetrievalRecord(
                doc_id=r.doc_id,
                summary=r.summary,
                similarity_score=r.similarity_score,
                source=r.source,
                retrieval_query=query_text,
            )
            for r in records
        ]

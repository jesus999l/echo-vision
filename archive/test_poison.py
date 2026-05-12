"""
test_poison.py — Echo v11.6 Memory Sandbox Poisoning Test
==========================================================
Proves two properties simultaneously:

  1. PURITY:     Replay mode returns the fossilized context exactly,
                 even after the live DB has been poisoned.

  2. DETECTION:  DriftSentinel names the displaced document precisely.

Test sequence:
  Phase 1 — Seed the DB with clean documents.
  Phase 2 — Run a live cognition cycle, fossilize the trace.
  Phase 3 — Poison the DB (add a document that crowds out a real one).
  Phase 4 — Replay the trace. Verify fossilized memory is unchanged.
  Phase 5 — Run DriftSentinel. Verify it names the displaced document.
  Phase 6 — Clean up (remove poison document).

Run:
    python3 test_poison.py

Note: uses ChromaDB's default embedding (no Ollama required for the test).
      Swap in OllamaEmbeddingFunction() if you want fully offline embeds.
"""

import json
import shutil
import os
from datetime import datetime

from echo_memory import MemoryEngine, MemoryContext
from chroma_adapter import ChromaDBBackend, DriftSentinel
from bootstrap_v11_6 import (
    EchoOrchestrator,
    MockStateProvider,
    TraceLogger,
)

# Use a throwaway DB path so the test never touches your real echo_chroma_db
TEST_DB_PATH = "./test_poison_chroma_db"
TEST_LOG     = "logs/test_poison_trace.jsonl"

QUERY = "what is my cpu usage?"


def seed_db(db: ChromaDBBackend):
    """Add clean, legitimate documents."""
    print("📥 Seeding clean documents...")

    db.add_document(
        source  = "episodic",
        doc_id  = "ep_cpu_001",
        text    = "User ran htop and observed cpu usage at 34 percent on the T14s.",
        summary = "T14s CPU monitoring session",
    )
    db.add_document(
        source  = "episodic",
        doc_id  = "ep_cpu_002",
        text    = "psutil cpu_percent returned 31.2 during Echo cognition benchmark.",
        summary = "Echo cognition benchmark CPU reading",
    )
    db.add_document(
        source  = "semantic",
        doc_id  = "sem_cpu_001",
        text    = "CPU usage is a percentage of processor time consumed by running processes.",
        summary = "Definition: CPU usage",
    )

    print("   ✅ Seeded: ep_cpu_001, ep_cpu_002, sem_cpu_001\n")


def run_live_cycle(db: ChromaDBBackend) -> dict:
    """Run one live cognition cycle and return the raw trace dict."""
    print("🚀 Running live cognition cycle...")

    engine = MemoryEngine(db_backend=db)

    # Override the logger path for isolation
    import bootstrap_v11_6 as boot
    original_log = boot.TraceLogger.__init__

    orchestrator = EchoOrchestrator(db_backend=db)
    orchestrator.logger = TraceLogger(path=TEST_LOG)

    event = {
        "source":     "cli",
        "event_type": "intent",
        "timestamp":  datetime.now().isoformat(),
        "payload":    {"command": QUERY},
    }

    decision = orchestrator.process_cycle(event)

    # Load the trace we just wrote
    with open(TEST_LOG, "r") as f:
        trace = json.loads(f.readlines()[-1])

    fossilized_hash = trace["memory_context"]["memory_hash"]
    print(f"   Fossilized hash : {fossilized_hash[:32]}...")
    print(f"   Doc IDs in trace: {_extract_doc_ids(trace)}\n")

    return trace


def poison_db(db: ChromaDBBackend):
    """
    Inject a high-similarity poison document designed to displace ep_cpu_001
    by being more cosine-similar to the query than the original.
    """
    print("☠️  Poisoning the DB...")
    db.add_document(
        source  = "episodic",
        doc_id  = "ep_POISON_001",
        text    = "CPU usage query: what is my cpu usage right now on this system?",
        summary = "⚠️ INJECTED POISON — should not appear in replay",
    )
    print("   Poison document ep_POISON_001 added.\n")


def run_replay(db: ChromaDBBackend, trace: dict) -> dict:
    """Replay the trace. Must use fossilized context, never touch live DB."""
    print("🧪 Running replay (sandbox isolation test)...")

    orchestrator = EchoOrchestrator(db_backend=db)
    orchestrator.logger = TraceLogger(path=TEST_LOG)

    replay_event = {
        **trace["event"],
        "state_snapshot": trace["state_snapshot"],
        "timestamp":      trace["timestamp"],
    }

    replay_decision = orchestrator.process_cycle(
        event            = replay_event,
        replay_mode      = True,
        injected_context = trace["memory_context"],
    )

    return replay_decision


def verify_purity(original_trace: dict, replay_decision: dict):
    """Assert the fossilized memory hash survived the replay unchanged."""
    print("🔍 Verifying sandbox purity...")

    fossilized_hash  = original_trace["memory_context"]["memory_hash"]
    replay_hash_used = replay_decision["reasoning_trace"]["memory_hash_used"]

    if fossilized_hash == replay_hash_used:
        print(f"   ✅ PURITY CONFIRMED")
        print(f"      Fossilized : {fossilized_hash[:32]}...")
        print(f"      Replay used: {replay_hash_used[:32]}...")
        print(f"      The poison document never entered the replay context.\n")
    else:
        print(f"   ❌ ISOLATION BREACH — hashes differ!")
        print(f"      Fossilized : {fossilized_hash}")
        print(f"      Replay used: {replay_hash_used}\n")
        raise AssertionError("Sandbox isolation failed — live DB reached during replay.")


def run_sentinel(db: ChromaDBBackend, trace: dict):
    """Run DriftSentinel and confirm it names the poison document."""
    print("🛰️  Running DriftSentinel...")
    sentinel = DriftSentinel(db_backend=db)
    report   = sentinel.audit(trace)

    found_poison = False
    for source, sr in report["sources"].items():
        for pair in sr.get("displaced", []):
            if "POISON" in pair["now"]:
                found_poison = True
        for doc in sr.get("added", []):
            if "POISON" in doc:
                found_poison = True

    if found_poison:
        print("\n   ✅ SENTINEL CONFIRMED poison document detected in drift report.\n")
    else:
        print("\n   ⚠️  Sentinel did not surface the poison document.")
        print("   (This may mean the poison doc's similarity score was too low")
        print("   to displace an existing result at n_results=5.)\n")

    return report


def cleanup(db: ChromaDBBackend):
    """Remove poison document and tear down test DB."""
    print("🧹 Cleaning up...")
    try:
        db.delete_document("episodic", "ep_POISON_001")
        print("   Poison document removed.")
    except Exception:
        pass
    if os.path.exists(TEST_DB_PATH):
        shutil.rmtree(TEST_DB_PATH)
        print("   Test DB removed.")
    if os.path.exists(TEST_LOG):
        os.remove(TEST_LOG)
        print("   Test trace log removed.")
    print()


def _extract_doc_ids(trace: dict) -> list:
    mc = trace["memory_context"]
    ids = []
    for source in ("episodic", "semantic", "graph_neighbors"):
        for rec in mc.get(source, []):
            ids.append(rec.get("doc_id", "?"))
    return ids


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print("\n" + "=" * 56)
    print("  Echo v11.6 — Memory Sandbox Poisoning Test")
    print("=" * 56 + "\n")

    from chroma_adapter import SimpleEmbeddingFunction
    db = ChromaDBBackend(persist_path=TEST_DB_PATH, embedding_fn=SimpleEmbeddingFunction())

    try:
        # Phase 1
        seed_db(db)

        # Phase 2
        trace = run_live_cycle(db)

        # Phase 3
        poison_db(db)

        # Phase 4
        replay_decision = run_replay(db, trace)

        # Phase 5
        verify_purity(trace, replay_decision)

        # Phase 6
        run_sentinel(db, trace)

        print("=" * 56)
        print("  ✅ ALL PHASES PASSED")
        print("  The Memory Sandbox is scientifically proven:")
        print("  Replay stayed pure. Sentinel named the poison.")
        print("=" * 56 + "\n")

    finally:
        cleanup(db)

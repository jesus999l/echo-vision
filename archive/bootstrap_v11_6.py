"""
bootstrap_v11_6.py — Echo v11.6 with Memory Sandbox
=====================================================
Changes from previous version:
  - MemoryEngine now accepts replay_mode + injected_context
  - TraceEntry fossilizes the full MemoryContext (including memory_hash)
  - ReplayEngine passes injected_context from trace; never calls live DB
  - DriftAuditor available as a separate post-replay audit pass
  - IsolationViolation raised if replay mode tries to reach live DB
"""

import os
import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, Optional, List

# Memory layer — the sandbox lives here
from echo_memory import MemoryContext, MemoryEngine, DriftAuditor


# =========================================================
# EXECUTION CONTEXT  (unchanged — frozen dataclass)
# =========================================================

@dataclass(frozen=True)
class ExecutionContext:
    replay_mode: bool = False
    frozen_time: Optional[str] = None
    frozen_state: Optional[Dict[str, Any]] = None
    deterministic_seed: int = 42

    model_name: str = "phi4-mini"
    quantization: str = "Q4_K_M"
    backend: str = "llama.cpp"
    backend_version: str = "0.3.5"


# =========================================================
# TRACE ENTRY
# memory_context now carries a sealed MemoryContext dict
# (includes memory_hash, full RetrievalRecords with scores)
# =========================================================

@dataclass
class TraceEntry:
    trace_id: str
    timestamp: str
    event: Dict[str, Any]
    state_snapshot: Dict[str, Any]
    memory_context: Dict[str, Any]   # sealed MemoryContext.to_dict()
    kernel_decision: Dict[str, Any]
    prompt_version: str
    model_info: Dict[str, Any]
    risk_level: str = "green"

    def to_json(self):
        return asdict(self)


# =========================================================
# TRACE LOGGER  (unchanged)
# =========================================================

class TraceLogger:

    def __init__(self, path="logs/event_trace.jsonl"):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, trace: TraceEntry):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace.to_json()) + "\n")


# =========================================================
# STATE PROVIDER  (unchanged)
# =========================================================

class MockStateProvider:

    def get_snapshot(self):
        return {
            "cpu_percent": 32,
            "ram_percent": 68,
            "active_window": "Firefox",
            "active_project": "Echo",
            "thermal_state": "normal"
        }


# =========================================================
# KERNEL  (unchanged — receives sealed MemoryContext either way)
# =========================================================

class EchoKernel:

    def _get_time(self, ctx: ExecutionContext):
        if ctx.replay_mode:
            return ctx.frozen_time
        return datetime.now().isoformat()

    def _get_state(self, ctx: ExecutionContext, provider):
        if ctx.replay_mode:
            return ctx.frozen_state
        return provider.get_snapshot()

    def process(
        self,
        event,
        memory_context: MemoryContext,
        ctx: ExecutionContext,
        provider,
    ):
        current_time  = self._get_time(ctx)
        current_state = self._get_state(ctx, provider)

        config = {
            "temperature": 0.0 if ctx.replay_mode else 0.4,
            "seed": ctx.deterministic_seed,
        }

        decision = {
            "approved": True,
            "response": "System cognition stable.",
            "tool_calls": [
                {
                    "tool": "system_monitor",
                    "params": {"action": "report_cpu"},
                }
            ],
            "risk_level": "green",
            "reasoning_trace": {
                "timestamp_used":  current_time,
                "active_window":   current_state.get("active_window"),
                "memory_hash_used": memory_context.memory_hash,
                "config": config,
            },
        }

        return decision


# =========================================================
# ORCHESTRATOR
# =========================================================

class EchoOrchestrator:

    def __init__(self, db_backend=None):
        self.logger         = TraceLogger()
        self.kernel         = EchoKernel()
        self.memory_engine  = MemoryEngine(db_backend=db_backend)
        self.state_provider = MockStateProvider()

    def process_cycle(
        self,
        event: Dict[str, Any],
        replay_mode: bool = False,
        injected_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        # --- Build frozen or live state ---
        if replay_mode:
            frozen_state = event["state_snapshot"]
            frozen_time  = event["timestamp"]
        else:
            frozen_state = self.state_provider.get_snapshot()
            frozen_time  = datetime.now().isoformat()

        ctx = ExecutionContext(
            replay_mode       = replay_mode,
            frozen_time       = frozen_time,
            frozen_state      = frozen_state,
        )

        # --- Memory retrieval (sandboxed) ---
        # Live:   queries DB, seals hash
        # Replay: deserializes fossilized context, verifies hash
        #         raises IsolationViolation if injected_context is None
        memory = self.memory_engine.recall(
            event            = event,
            state            = frozen_state,
            replay_mode      = replay_mode,
            injected_context = injected_context,
        )

        # --- Kernel decision ---
        decision = self.kernel.process(
            event          = event,
            memory_context = memory,
            ctx            = ctx,
            provider       = self.state_provider,
        )

        # --- Fossilize everything ---
        trace = TraceEntry(
            trace_id        = str(uuid.uuid4()),
            timestamp       = frozen_time,
            event           = event,
            state_snapshot  = frozen_state,
            memory_context  = memory.to_dict(),   # full provenance, sealed hash
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
        return decision


# =========================================================
# REPLAY ENGINE
# =========================================================

class ReplayEngine:
    """
    Loads the last TraceEntry from disk and replays it.

    Passes the fossilized memory_context as injected_context so the
    MemoryEngine never touches the live DB. If the DB has drifted,
    DriftAuditor will catch it in a separate audit pass.
    """

    def replay_last_trace(self, run_drift_audit: bool = True):

        with open("logs/event_trace.jsonl", "r", encoding="utf-8") as f:
            lines = f.readlines()

        last = json.loads(lines[-1])

        orchestrator = EchoOrchestrator()

        # Reconstruct the event with state_snapshot embedded so
        # the Orchestrator can freeze state correctly during replay.
        replay_event = {
            **last["event"],
            "state_snapshot": last["state_snapshot"],
            "timestamp":      last["timestamp"],
        }

        replay_decision = orchestrator.process_cycle(
            event            = replay_event,
            replay_mode      = True,
            injected_context = last["memory_context"],   # <-- sandbox key
        )

        # --- Decision drift check ---
        original = last["kernel_decision"]
        drift    = original["tool_calls"] != replay_decision["tool_calls"]

        print("\n===== REPLAY RESULT =====")
        print("❌ DECISION DRIFT" if drift else "✅ STABLE DECISION")
        print("\nOriginal:")
        print(json.dumps(original, indent=2))
        print("\nReplay:")
        print(json.dumps(replay_decision, indent=2))

        # --- Optional: memory fingerprint audit ---
        if run_drift_audit:
            auditor = DriftAuditor(orchestrator.memory_engine)
            auditor.audit(last)

        return replay_decision


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    orchestrator = EchoOrchestrator()

    event = {
        "source": "cli",
        "event_type": "intent",
        "timestamp": datetime.now().isoformat(),
        "payload": {
            "command": "what is my cpu usage?"
        },
    }

    print("\n🚀 Running live cognition cycle...\n")
    result = orchestrator.process_cycle(event)
    print(json.dumps(result, indent=2))

    print("\n🧪 Running replay + drift audit...\n")
    ReplayEngine().replay_last_trace(run_drift_audit=True)

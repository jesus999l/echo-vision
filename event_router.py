# event_router.py
# Place in ~/vision_assistant/ alongside your Echo desktop code
#
# Usage in echo_main.py:
#   from event_router import router
#
#   router.activate('STT', 85)     # node is processing
#   router.idle('STT')             # node goes dormant
#   router.set_thought("organizing habit data")
#   router.set_voice_state('ACTIVE')
#
# The FastAPI bridge reads ~/echo_state.json automatically.
# No restart needed — state updates are live on next poll.

import json
import time
from pathlib import Path
from threading import Lock

STATE_FILE = Path.home() / 'echo_state.json'
THOUGHT_FILE = Path.home() / 'echo_thought.txt'

# Default subsystem definitions
# activity: 0-100, drives node brightness in the lattice
_DEFAULTS = {
    'WAKE':    {'status': 'standby', 'activity': 10},
    'STT':     {'status': 'idle',    'activity': 0},
    'VISION':  {'status': 'idle',    'activity': 0},
    'ROUTER':  {'status': 'active',  'activity': 25},
    'LLM':     {'status': 'idle',    'activity': 0},
    'CONTEXT': {'status': 'active',  'activity': 20},
    'MEMORY':  {'status': 'idle',    'activity': 0},
    'VECTOR':  {'status': 'idle',    'activity': 0},
    'REFLECT': {'status': 'idle',    'activity': 0},
    'TTS':     {'status': 'standby', 'activity': 5},
    'TASKS':   {'status': 'active',  'activity': 15},
    'UI':      {'status': 'active',  'activity': 35},
    'TONE':    {'status': 'idle',    'activity': 0},
}

_lock = Lock()


class EventRouter:
    def __init__(self):
        self._nodes = {k: dict(v) for k, v in _DEFAULTS.items()}
        self._voice  = 'STANDBY'
        self._model  = 'qwen2.5:0.5b'
        self._cycle  = 'IDLE'
        self._memint = 100
        self._last   = None
        self._flush()

    # ── Public API ────────────────────────────────────────────────────

    def activate(self, node_id: str, activity: int = 80):
        """Mark a subsystem as actively processing."""
        self._set(node_id, 'active', min(100, max(0, activity)))

    def idle(self, node_id: str):
        """Return a subsystem to dormant state."""
        self._set(node_id, 'idle', 0)

    def standby(self, node_id: str, activity: int = 10):
        """Mark a subsystem as on standby (low activity)."""
        self._set(node_id, 'standby', activity)

    def set_voice_state(self, state: str):
        """state: 'ACTIVE' | 'STANDBY' | 'PROCESSING'"""
        with _lock:
            self._voice = state
            self._flush()

    def set_reflection(self, state: str):
        """state: 'IDLE' | 'PROCESSING' | 'COMPLETE'"""
        with _lock:
            self._cycle = state
            self._flush()

    def set_memory_integrity(self, pct: int):
        with _lock:
            self._memint = pct
            self._flush()

    def set_model(self, model_name: str):
        with _lock:
            self._model = model_name
            self._flush()

    def set_thought(self, text: str):
        """Update the thought stream shown on the relay station."""
        THOUGHT_FILE.write_text(text.strip())
        with _lock:
            self._last = time.strftime('%Y-%m-%d %H:%M')
            self._flush()

    def set_last_input(self, text: str = None):
        with _lock:
            self._last = text or time.strftime('%Y-%m-%d %H:%M')
            self._flush()

    # ── Convenience context managers ─────────────────────────────────

    def processing(self, node_id: str, activity: int = 80):
        """Use as: with router.processing('LLM'): ... """
        return _NodeContext(self, node_id, activity)

    # ── Internal ─────────────────────────────────────────────────────

    def _set(self, node_id: str, status: str, activity: int):
        with _lock:
            if node_id in self._nodes:
                self._nodes[node_id]['status']   = status
                self._nodes[node_id]['activity'] = activity
                self._flush()

    def _flush(self):
        # Derive inference_load from LLM node activity
        llm_activity = self._nodes.get('LLM', {}).get('activity', 0)

        thought = 'no current focus logged.'
        if THOUGHT_FILE.exists():
            t = THOUGHT_FILE.read_text().strip()
            if t:
                thought = t

        data = {
            'nodes':             self._nodes,
            'voice_pipeline':    self._voice,
            'inference_load':    llm_activity,
            'memory_integrity':  self._memint,
            'reflection_cycle':  self._cycle,
            'active_model':      self._model,
            'current_focus':     thought,
            'last_input':        self._last,
            'echo_status':       'ONLINE',
            'timestamp':         int(time.time()),
        }
        STATE_FILE.write_text(json.dumps(data, indent=2))


class _NodeContext:
    """Context manager: activate node on enter, idle on exit."""
    def __init__(self, router, node_id, activity):
        self._r = router
        self._n = node_id
        self._a = activity

    def __enter__(self):
        self._r.activate(self._n, self._a)
        return self

    def __exit__(self, *_):
        self._r.idle(self._n)


# Singleton — import this in Echo desktop
router = EventRouter()


# ── Example integration hooks ─────────────────────────────────────────
# Paste these calls into the relevant places in echo_main.py:
#
# On wake word detected:
#   router.activate('WAKE', 95)
#
# On STT start:
#   router.activate('STT', 80)
#   router.set_voice_state('ACTIVE')
#
# On STT end:
#   router.idle('STT')
#   router.set_voice_state('STANDBY')
#
# On LLM inference start:
#   router.activate('LLM', 90)
#   router.activate('ROUTER', 70)
#   router.activate('CONTEXT', 60)
#
# On LLM inference end:
#   router.idle('LLM')
#   router.standby('ROUTER', 25)
#   router.standby('CONTEXT', 20)
#
# On memory write:
#   router.activate('MEMORY', 75)
#   router.activate('VECTOR', 60)
#   # ... after write:
#   router.idle('MEMORY')
#   router.idle('VECTOR')
#
# On TTS speaking:
#   router.activate('TTS', 85)
#   router.set_voice_state('ACTIVE')
#   # ... after speech:
#   router.idle('TTS')
#   router.set_voice_state('STANDBY')
#
# On reflection cycle:
#   router.activate('REFLECT', 70)
#   router.set_reflection('PROCESSING')
#   # ... after:
#   router.idle('REFLECT')
#   router.set_reflection('IDLE')
#
# Thought stream update (call after any significant inference):
#   router.set_thought(f"processing: {user_input[:60]}")

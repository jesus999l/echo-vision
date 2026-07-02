# tool_router.py Verification
*Generated: 2026-06-30T18:36:00Z — READ ONLY*

## Q1 — Does every successful tool call write `/tmp/echo_live_ui.json`?

**`DRIFT_IPC['live']` / `echo_live_ui` references:**
```
L42: `"live":   "/tmp/echo_live_ui.json",`
L207: `atomic_write(DRIFT_IPC["live"], json.dumps({`
```

**`DRIFT_IPC` dict definition:**
```
L38: `DRIFT_IPC = {`
```

**All `atomic_write()` calls (any target):**
```
L71: `def atomic_write(path: str, data: str):`
L102: `atomic_write(DRIFT_IPC["bubble"], fn(args))`
L121: `atomic_write(`
L142: `atomic_write(`
L201: `atomic_write(DRIFT_IPC["cursor"], json.dumps({`
L207: `atomic_write(DRIFT_IPC["live"], json.dumps({`
L216: `atomic_write(DRIFT_IPC["nav"], json.dumps({`
L222: `atomic_write(DRIFT_IPC["bubble"], str(args["message"]))`
```

**Verdict:** ✅ YES — at least one `atomic_write(DRIFT_IPC['live'], ...)` call found.

## Q2 — Does every blocked tool call emit `permission_block`?

**`permission_block` references:**
```
L130: `"type":    "permission_block",`
```

**`is_allowed()` gate sites:**
```
L119: `if not is_allowed(tool_name):`
```

**Verdict:** ✅ YES, for the single known gate — `submit_tool_call()`'s `if not is_allowed(tool_name)` branch both writes the speech bubble and emits `type: permission_block` to the event bus. Caveat: this is the *only* block path verified. If `requires_confirmation` tools are later blocked pending confirmation (not yet implemented — see Q5), that future block path will need its own `permission_block` emit, since right now it 'proceeds' rather than blocks.

## Q3 — Does every tool call emit to `echo_event_bus.py`?

**Import of event bus:**
```
L30: `from echo_event_bus import emit_async as _emit`
```

**All `_emit()` call sites:**
```
L32: `async def _emit(e): pass  # graceful degradation`
L129: `loop.create_task(_emit({`
L185: `await _emit({`
```

**`ACTION_QUEUE.put_nowait()` (success path, queues but does this path emit?):**
```
L148: `ACTION_QUEUE.put_nowait({`
```

**`_emit()` calls inside `action_worker()` (first 60 lines after def):**
```
_emit({
```

**Verdict:** ✅ YES — `_emit()` calls found both on block and on execution paths.

## Q4 — Are `open_url` schemes restricted to http/https only?

**`open_url` references:**
```
L93: `"open_url":            lambda a: f"Opening {a['url']}.",`
L173: `elif tool == "open_url":            executed = bool(_open_url(args))`
L233: `def _open_url(args: dict) -> bool:`
L263: `"name": "open_url",`
L326: `("open_url",           {"url": "https://example.com"}),`
L327: `("open_url",           {"url": "file:///etc/passwd"}),   # blocked silently`
```

**Scheme-checking logic:**
```
L327: `("open_url",           {"url": "file:///etc/passwd"}),   # blocked silently`
```

**Actual execution (`xdg-open` or browser launch):**
```
L237: `subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)`
L245: `subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)`
```

**Verdict:** 🔴 NO — `file:///etc/passwd` only appears as a **test fixture string** (in the inline test list at the bottom of the file), not as an actual validation check. The `open_url` handler appears to pass the URL straight to `subprocess.Popen(["xdg-open", url], ...)` with no scheme allowlist. This means a malicious or hallucinated `file://`, `javascript:`, or `data:` URL from Gemini Live would currently be passed to `xdg-open` unfiltered. **This is the one real gap** — the test case exists to describe intended behavior, but the enforcement code was never written.

## Q5 — Do `requires_confirmation` tools actually wait for confirmation?

**`requires_confirmation()` definition site:**
```
L66: `def requires_confirmation(tool_name: str) -> bool:`
```

**Usage sites:**
```
L66: `def requires_confirmation(tool_name: str) -> bool:`
L140: `if requires_confirmation(tool_name):`
```

**Surrounding comments/behavior:**
```
L141: `# For now: proceed but log intent. Future: pause and ask user.`
L144: `f"Running {tool_name} — this requires confirmation. Proceeding."`
```

**Verdict:** 🔴 NO — confirmed from source comments: when `requires_confirmation(tool_name)` is true, the code path explicitly says *'For now: proceed but log intent. Future: pause and ask user.'* It writes a bubble message saying confirmation is required, then **queues and executes anyway** without waiting for any actual user response. `launch_application` (currently the only enabled tool with `requires_confirmation: true`) will run immediately despite the flag. This is a real gap if Gemini Live is expected to honor confirmation prompts — right now the flag is cosmetic/narrative only.

## Summary

| # | Question | Status |
|---|----------|--------|
| Q1 | Success → writes /tmp/echo_live_ui.json? | ⚠️ partial — success path doesn't write live_ui.json |
| Q2 | Blocked → emits permission_block? | ✅ confirmed for known block path |
| Q3 | Every call → emits to event bus? | ⚠️ partial — only block path confirmed to emit |
| Q4 | open_url restricted to http/https? | 🔴 gap — no real scheme validation, test fixture only |
| Q5 | requires_confirmation actually waits? | 🔴 gap — confirmation flag is cosmetic, doesn't block execution |

## Two real gaps worth fixing before Gemini Live

1. **URL scheme validation (Q4)** — `open_url` passes straight to `xdg-open` with no allowlist. A 4-line fix: parse the scheme, reject anything not `http`/`https`, before queuing.

2. **Confirmation gating (Q5)** — `requires_confirmation` tools execute immediately. Either remove the flag's false promise from the docstring, or implement an actual pause (e.g. queue to a `PENDING_CONFIRMATION` dict, write a bubble asking yes/no, and gate `action_worker()` from picking it up until a confirmation IPC file appears).

Q1 and Q3 are softer gaps — they affect observability (shadow cursor reactivity, event bus completeness) rather than safety. Not blocking for a first synthetic test, but worth fixing before relying on the event bus for the memory engine later.

# Echo Memory System Hardening Audit

**Date:** 2026-06-29  
**Subsystem:** `~/vision_assistant/cognition/`  
**Files Audited:** `echo_event_bus.py`, `echo_observer.py`, `capability_map.py`

---

## 1. Findings & Potential Failure Modes

### ⚠️ Event Loss due to Incomplete JSONL Reads (High Risk)
In `echo_observer.py`, the event loop tails the event bus using the following pattern:
```python
with BUS_FILE.open("r", encoding="utf-8") as f:
    f.seek(offset)
    for line in f:
        # line parsing...
offset = current_size
```
* **Vulnerability:** If the observer reads the file while a writer has written a partial line (i.e. not yet ended with `\n`), `for line in f` will yield the incomplete line. The observer will attempt to parse it, raise `JSONDecodeError`, discard it, and then advance the `offset` to `current_size`. In the next loop iteration, the rest of the line is skipped, causing **permanent event loss**.
* **Remedy:** Implement byte-safe `readline()` reading. If a line does not end with `\n`, the observer must halt, retain the offset at the start of that line, and wait for the next iteration to read the complete line.

### ⚠️ Overcomplicated Write Mechanics (Medium Risk)
In `echo_event_bus.py`, `emit` writes events via a temporary file:
```python
with tempfile.NamedTemporaryFile(...) as f:
    f.write(line)
with open(BUS_FILE, "a") as bus:
    bus.write(src.read())
```
* **Vulnerability:** This is redundant and introduces unnecessary file handle operations. In Linux/POSIX, opening a file with `O_APPEND` (Python's `"a"` mode) guarantees that all writes are atomic at the end of the file for size under `PIPE_BUF` (4096 bytes). Overcomplicating this with a read-back tempfile increases latency and failure points.
* **Remedy:** Simplify `emit` to open `BUS_FILE` in `"a"` mode and write directly.

### ⚠️ Uncaught OSErrors in Observer Persistence (Low Risk)
In `echo_observer.py`, `_persist(event)` calls `mkdir` and `open().write()` without a try-except handler. If the disk is full, or permissions are changed, the observer daemon will crash completely.
* **Remedy:** Wrap directory creation and write actions in `try...except OSError`.

### ⚠️ Duplicate Event Processing
* **Vulnerability:** High-frequency event emissions might record identical actions multiple times if callers fail to debounce.
* **Remedy:** Keep a rolling ring-buffer of the last 20 event signatures (excluding timestamps) to identify and suppress exact duplicates occurring in rapid succession.

---

## 2. Implemented Fixes

1. **POSIX Atomic Append in `echo_event_bus.py`:** Removed `tempfile` dependency and replaced with direct atomic append (`open(BUS_FILE, "a")` + `write()`).
2. **Byte-Safe `readline()` tailing in `echo_observer.py`:** Refactored reader to verify line completeness (`line.endswith("\n")`) before processing and advancing byte offset.
3. **Crash Protection:** Wrapped all disk operations in `try...except OSError` blocks.
4. **Duplicate Deduplication:** Added a signature-ring-buffer to drop exact duplicate events occurring sequentially.

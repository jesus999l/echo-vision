#!/usr/bin/env python3
"""
obsidian_bridge.py — Echo ↔ Obsidian Vault Bridge
Place in: ~/vision_assistant/obsidian_bridge.py

Watches your Obsidian vault for new/modified notes and:
  • Ingests notes tagged for Echo into a live context pool
  • Writes Echo activity back to the vault (habits, tasks, briefings, etc.)
  • Provides a get_context_for_query() call for AI prompt injection

Thread-safe. Designed to start alongside Echo's Tkinter main loop.

Tags Echo recognises in your vault:
  #echo-context    → injected into every AI system prompt (persistent guidelines)
  #echo-memory     → added to context pool, ranked by recency + relevance
  #echo-task       → imports as an Echo task on next sync
  #echo-journal    → imports as a journal entry
  #jules-task      → creates a Jules task note (future: auto-files GitHub issue)
  #echo-ignore     → never processed by Echo

Dependencies: watchdog (already in vision_env)
  pip install watchdog --break-system-packages   (if not already present)
"""

import os
import re
import json
import time
import queue
import logging
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, List, Any, Callable

# ---------------------------------------------------------------------------
# Optional watchdog import — bridge still works in write-only mode without it
# ---------------------------------------------------------------------------
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object   # fallback base

logger = logging.getLogger("echo.obsidian")


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_CONFIG: Dict[str, Any] = {
    # Absolute or ~ path to your Obsidian vault root
    "vault_path": "~/Documents/ObsidianVault",

    # Folders inside the vault that Echo will WRITE into
    "subfolders": {
        "daily":         "Echo/Daily",
        "habits":        "Echo/Habits",
        "tasks":         "Echo/Tasks",
        "briefings":     "Echo/Briefings",
        "memory":        "Echo/Memory",
        "conversations": "Echo/Conversations",
        "security":      "Echo/Security",
        "status":        "Echo/Status",
        "learning":      "Echo/Learning",
    },

    # Folders to watch for incoming notes (empty = watch entire vault)
    "watch_folders": [],

    # Folders to never process (Obsidian internals + your templates)
    "exclude_folders": [".obsidian", ".trash", "Templates", "Attachments"],

    # Notes with any of these tags get ingested into Echo's context
    "ingest_tags": ["echo-context", "echo-memory", "echo-task",
                    "echo-journal", "jules-task"],

    # Notes with any of these tags are always skipped
    "ignore_tags": ["echo-ignore", "draft", "wip"],

    # Max notes held in the live context pool at once
    "context_max_notes": 12,

    # Max characters injected into a single AI prompt from the vault
    "context_max_chars": 4000,

    # Echo can write to the vault (set false to make bridge read-only)
    "write_enabled": True,

    # Time (HH:MM, 24h) to auto-trigger daily summary write
    "daily_summary_time": "23:30",

    # Seconds between repeated events on the same file (debounce)
    "debounce_seconds": 2.5,

    # GitHub repo slug used when creating Jules task notes (owner/repo)
    "jules_default_repo": "",
}


def load_config(config_path: str = "obsidian_config.json") -> Dict[str, Any]:
    path = Path(config_path)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
            merged = {**DEFAULT_CONFIG, **user}
            # Deep merge subfolders so new keys aren't lost
            merged["subfolders"] = {
                **DEFAULT_CONFIG["subfolders"],
                **user.get("subfolders", {}),
            }
            return merged
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Could not read {config_path}: {e} — using defaults.")
    return dict(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any], config_path: str = "obsidian_config.json"):
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    logger.info(f"Config saved → {config_path}")


# ============================================================================
# Note parser
# ============================================================================

class ObsidianNote:
    """
    Parsed Obsidian Markdown note.
    Handles YAML frontmatter and inline #tag syntax.
    Does NOT require python-frontmatter — pure stdlib.
    """

    _FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n",
                                 re.DOTALL)
    _INLINE_TAG_RE  = re.compile(r"(?<!\w)#([\w/-]+)")

    def __init__(self, path: Path):
        self.path     = path
        self.raw      = ""
        self.body     = ""
        self.frontmatter: Dict[str, Any] = {}
        self.tags:     List[str] = []
        self.title:    str = path.stem
        self.modified: datetime = (
            datetime.fromtimestamp(path.stat().st_mtime)
            if path.exists() else datetime.now()
        )
        self._parse()

    # ------------------------------------------------------------------
    def _parse(self):
        if not self.path.exists():
            return
        try:
            self.raw = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning(f"Cannot read {self.path}: {e}")
            return

        fm_match = self._FRONTMATTER_RE.match(self.raw)
        if fm_match:
            self.frontmatter = _parse_minimal_yaml(fm_match.group(1))
            self.body        = self.raw[fm_match.end():]
        else:
            self.body = self.raw

        # --- Collect tags ---------------------------------------------------
        # From frontmatter `tags:` field
        fm_tags = self.frontmatter.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [t.strip().lstrip("#") for t in fm_tags.replace(",", " ").split()]
        elif isinstance(fm_tags, list):
            fm_tags = [str(t).lstrip("#") for t in fm_tags]
        self.tags = list(dict.fromkeys(fm_tags))   # dedupe, preserve order

        # From inline #tags in body (skip Echo-generated section headers)
        for t in self._INLINE_TAG_RE.findall(self.body):
            if t not in self.tags:
                self.tags.append(t)

        # Title override from frontmatter
        if "title" in self.frontmatter:
            self.title = str(self.frontmatter["title"]).strip('"\'')

    # ------------------------------------------------------------------
    def has_tag(self, *tags: str) -> bool:
        return any(t in self.tags for t in tags)

    def excerpt(self, max_chars: int = 600) -> str:
        """Return clean plain-text excerpt: strips wikilinks, images, headings."""
        text = self.body
        text = re.sub(r"!\[.*?\]\(.*?\)",       "",    text)   # images
        text = re.sub(r"\[\[([^\]|]+)\|?[^\]]*\]\]", r"\1", text)  # wikilinks
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # md links
        text = re.sub(r"#{1,6}\s+",              "",    text)   # headings markup
        text = re.sub(r"[*_`~]{1,3}",            "",    text)   # emphasis
        text = re.sub(r"\s+",                    " ",   text).strip()
        return text[:max_chars] + ("…" if len(text) > max_chars else "")

    def to_context_string(self, max_chars: int = 800) -> str:
        """Format for injection into an AI prompt."""
        return f"[Vault note: {self.title}]\n{self.excerpt(max_chars)}"

    def __repr__(self):
        return f"<ObsidianNote '{self.title}' tags={self.tags[:4]}>"


def _parse_minimal_yaml(text: str) -> Dict[str, Any]:
    """
    Parses a minimal YAML subset (strings, lists, booleans).
    Handles the 95% of Obsidian frontmatter without pulling in PyYAML.
    """
    result: Dict[str, Any] = {}
    current_list_key: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        # List item under a previous key
        stripped = line.lstrip()
        if stripped.startswith("- ") and current_list_key:
            val = stripped[2:].strip().strip('"\'')
            result[current_list_key].append(val)
            continue

        if ":" in line:
            key_part, _, val_part = line.partition(":")
            key = key_part.strip()
            val = val_part.strip()

            if not val or val == "[]":
                # Start of a block list (or empty list)
                result[key] = []
                current_list_key = key
            else:
                # Inline list  tags: [a, b, c]
                if val.startswith("["):
                    inner = val.strip("[]")
                    result[key] = [v.strip().strip('"\'') for v in inner.split(",") if v.strip()]
                    current_list_key = None
                else:
                    # Scalar
                    v = val.strip('"\'')
                    if v.lower() == "true":
                        result[key] = True
                    elif v.lower() == "false":
                        result[key] = False
                    else:
                        result[key] = v
                    current_list_key = None
        else:
            current_list_key = None

    return result


# ============================================================================
# Vault writer  (Echo → Obsidian)
# ============================================================================

class VaultWriter:
    """
    All methods that write Markdown files into the vault.
    Every generated file includes `echo-generated` in its tags so the
    watcher never re-ingests its own output.
    """

    def __init__(self, vault_root: Path, subfolders: Dict[str, str]):
        self.root = vault_root
        self._sf  = subfolders

    # ------------------------------------------------------------------
    def _folder(self, key: str) -> Path:
        rel  = self._sf.get(key, f"Echo/{key.title()}")
        full = self.root / rel
        full.mkdir(parents=True, exist_ok=True)
        return full

    @staticmethod
    def _today()      -> str: return date.today().isoformat()
    @staticmethod
    def _now_stamp()  -> str: return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _write(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info(f"Vault → {path.relative_to(self.root)}")

    def _append(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)

    # ------------------------------------------------------------------
    # Daily summary
    # ------------------------------------------------------------------
    def write_daily_summary(
        self,
        summary_text:  str,
        tasks_done:    Optional[List[str]] = None,
        habits:        Optional[Dict[str, bool]] = None,
    ) -> Path:
        today = self._today()
        path  = self._folder("daily") / f"{today}.md"

        tasks_md = ""
        if tasks_done:
            items    = "\n".join(f"- [x] {t}" for t in tasks_done)
            tasks_md = f"\n## Tasks completed\n\n{items}\n"

        habits_md = ""
        if habits:
            rows      = "\n".join(
                f"- {'[x]' if done else '[ ]'} {name}"
                for name, done in habits.items()
            )
            habits_md = f"\n## Habits\n\n{rows}\n"

        content = (
            f"---\n"
            f"title: \"Echo Daily — {today}\"\n"
            f"date: {today}\n"
            f"tags: [echo-daily, echo-generated]\n"
            f"---\n\n"
            f"# Echo Daily — {today}\n"
            f"*Generated {self._now_stamp()}*\n\n"
            f"{summary_text.strip()}\n"
            f"{tasks_md}"
            f"{habits_md}"
        )
        self._write(path, content)
        return path

    def write_learning_summary(self, summary_text: str) -> Path:
        today = self._today()
        ts    = datetime.now().strftime("%H%M%S")
        path  = self._folder("learning") / f"learning-{today}-{ts}.md"
        content = (
            f"---\n"
            f"title: \"Reflective Learning — {today}\"\n"
            f"date: {today}\n"
            f"tags: [echo-learning, echo-generated]\n"
            f"---\n\n"
            f"# Reflective Learning — {today}\n"
            f"*Generated {self._now_stamp()}*\n\n"
            f"{summary_text.strip()}\n"
        )
        self._write(path, content)
        return path

    # ------------------------------------------------------------------
    # Morning briefing
    # ------------------------------------------------------------------
    def write_morning_briefing(self, text: str, date_str: str = None) -> Path:
        today = date_str or self._today()
        path  = self._folder("briefings") / f"{today}.md"
        content = (
            f"---\n"
            f"title: \"Morning Briefing — {today}\"\n"
            f"date: {today}\n"
            f"tags: [echo-briefing, echo-generated]\n"
            f"---\n\n"
            f"# Morning Briefing — {today}\n"
            f"*Generated {self._now_stamp()}*\n\n"
            f"{text.strip()}\n"
        )
        self._write(path, content)
        return path

    # ------------------------------------------------------------------
    # Habit log  (append rows to today's table)
    # ------------------------------------------------------------------
    def append_habit_entry(
        self,
        name:      str,
        completed: bool,
        streak:    int = 0,
        note:      str = "",
    ) -> Path:
        today = self._today()
        path  = self._folder("habits") / f"{today}.md"

        if not path.exists():
            header = (
                f"---\n"
                f"title: \"Habits — {today}\"\n"
                f"date: {today}\n"
                f"tags: [echo-habits, echo-generated]\n"
                f"---\n\n"
                f"# Habit Log — {today}\n\n"
                f"| Habit | Done | Streak | Note |\n"
                f"|-------|:----:|:------:|------|\n"
            )
            self._write(path, header)

        icon = "✅" if completed else "❌"
        self._append(path, f"| {name} | {icon} | {streak} | {note} |\n")
        return path

    # ------------------------------------------------------------------
    # Task log  (append entries to today's file)
    # ------------------------------------------------------------------
    def append_task_entry(
        self,
        title:    str,
        status:   str = "done",
        priority: str = "normal",
        note:     str = "",
    ) -> Path:
        today = self._today()
        path  = self._folder("tasks") / f"{today}.md"

        if not path.exists():
            header = (
                f"---\n"
                f"title: \"Tasks — {today}\"\n"
                f"date: {today}\n"
                f"tags: [echo-tasks, echo-generated]\n"
                f"---\n\n"
                f"# Task Log — {today}\n\n"
            )
            self._write(path, header)

        icon_map = {"done": "✅", "cancelled": "🚫", "deferred": "⏭️", "started": "🔄"}
        icon     = icon_map.get(status, "📌")
        suffix   = f" — {note}" if note else ""
        self._append(
            path,
            f"- {icon} **{title}** *(priority: {priority})*{suffix}\n",
        )
        return path

    # ------------------------------------------------------------------
    # Conversation summary
    # ------------------------------------------------------------------
    def write_conversation_summary(self, summary: str, turns: int = 0) -> Path:
        ts   = datetime.now().strftime("%Y-%m-%d-%H%M")
        path = self._folder("conversations") / f"{ts}.md"
        content = (
            f"---\n"
            f"title: \"Conversation {ts}\"\n"
            f"date: {self._today()}\n"
            f"turns: {turns}\n"
            f"tags: [echo-conversation, echo-generated]\n"
            f"---\n\n"
            f"# Conversation — {ts}\n"
            f"*{self._now_stamp()} · {turns} turns*\n\n"
            f"{summary.strip()}\n"
        )
        self._write(path, content)
        return path

    # ------------------------------------------------------------------
    # Memory note  (persistent topic-based knowledge)
    # ------------------------------------------------------------------
    def write_memory_note(self, topic: str, content: str,
                          source: str = "echo") -> Path:
        safe = re.sub(r"[^\w\s-]", "", topic).strip()
        safe = re.sub(r"\s+", "-", safe).lower()[:60]
        path = self._folder("memory") / f"{safe}.md"
        text = (
            f"---\n"
            f"title: \"{topic}\"\n"
            f"updated: \"{self._now_stamp()}\"\n"
            f"source: {source}\n"
            f"tags: [echo-memory, echo-generated]\n"
            f"---\n\n"
            f"# {topic}\n"
            f"*Last updated: {self._now_stamp()}*\n\n"
            f"{content.strip()}\n"
        )
        self._write(path, text)
        return path

    # ------------------------------------------------------------------
    # Jules task note
    # ------------------------------------------------------------------
    def write_jules_task(
        self,
        title:       str,
        description: str,
        repo:        str = "",
        priority:    str = "normal",
    ) -> Path:
        today = self._today()
        ts    = datetime.now().strftime("%H%M%S")
        safe  = re.sub(r"[^\w\s-]", "", title).strip()
        safe  = re.sub(r"\s+", "-", safe).lower()[:35]
        path  = self._folder("tasks") / f"jules-{today}-{ts}-{safe}.md"
        content = (
            f"---\n"
            f"title: \"{title}\"\n"
            f"date: {today}\n"
            f"repo: \"{repo}\"\n"
            f"priority: {priority}\n"
            f"status: queued\n"
            f"tags: [jules-task, echo-generated]\n"
            f"---\n\n"
            f"# Jules Task: {title}\n\n"
            f"**Repo:** {repo or '(set jules_default_repo in obsidian_config.json)'}  \n"
            f"**Priority:** {priority}  \n"
            f"**Created:** {self._now_stamp()}\n\n"
            f"## Description\n\n{description.strip()}\n\n"
            f"## Status\n\n"
            f"- [ ] GitHub issue created\n"
            f"- [ ] Jules picked up task\n"
            f"- [ ] PR filed\n"
            f"- [ ] Merged into main\n"
        )
        self._write(path, content)
        return path

    # ------------------------------------------------------------------
    # Security report  (Shannon output)
    # ------------------------------------------------------------------
    def write_security_report(self, report: str, target: str = "echo") -> Path:
        today = self._today()
        path  = self._folder("security") / f"{today}-{target}.md"
        content = (
            f"---\n"
            f"title: \"Security — {target} — {today}\"\n"
            f"date: {today}\n"
            f"target: {target}\n"
            f"tags: [echo-security, shannon, echo-generated]\n"
            f"---\n\n"
            f"# Security Scan: {target}\n"
            f"*Run: {self._now_stamp()}*\n\n"
            f"{report.strip()}\n"
        )
        self._write(path, content)
        return path

    # ------------------------------------------------------------------
    # Status snapshot  (for Neocities publisher)
    # ------------------------------------------------------------------
    def write_status_snapshot(self, status_data: Dict[str, Any]) -> Path:
        today = self._today()
        path  = self._folder("status") / f"{today}.md"
        rows  = "\n".join(f"- **{k}**: {v}" for k, v in status_data.items())
        content = (
            f"---\n"
            f"title: \"Echo Status — {today}\"\n"
            f"date: {today}\n"
            f"tags: [echo-status, echo-generated]\n"
            f"---\n\n"
            f"# Echo Status — {today}\n"
            f"*{self._now_stamp()}*\n\n"
            f"{rows}\n"
        )
        self._write(path, content)
        return path


# ============================================================================
# Watchdog event handler
# ============================================================================

class _VaultHandler(FileSystemEventHandler):
    """
    Pushes debounced file-system events into a processing queue.
    Filters: only .md files, not excluded folders, not burst duplicates.
    """

    def __init__(self, event_queue: queue.Queue, config: Dict[str, Any]):
        if WATCHDOG_AVAILABLE:
            super().__init__()
        self._q       = event_queue
        self._exclude = set(config.get("exclude_folders", []))
        self._delay   = config.get("debounce_seconds", 2.5)
        self._seen:   Dict[str, float] = {}
        self._lock    = threading.Lock()

    def _should_process(self, path: str) -> bool:
        if not path.endswith(".md"):
            return False
        parts = Path(path).parts
        if any(p in self._exclude for p in parts):
            return False
        now = time.monotonic()
        with self._lock:
            if now - self._seen.get(path, 0) < self._delay:
                return False
            self._seen[path] = now
        return True

    def on_created(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            self._q.put({"type": "created", "path": event.src_path})

    def on_modified(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            self._q.put({"type": "modified", "path": event.src_path})


# ============================================================================
# Main bridge class
# ============================================================================

class ObsidianBridge:
    """
    Echo ↔ Obsidian vault bridge.

    Start once during Echo's __init__ or startup sequence:

        bridge = ObsidianBridge(on_note_ingested=my_callback)
        bridge.start()

    Then call write helpers throughout Echo's runtime:

        bridge.log_habit("Meditation", completed=True, streak=5)
        bridge.log_task("Fix STT pipeline", status="done")
        bridge.log_morning_briefing(briefing_text)
        bridge.queue_jules_task("Add QUIC sync", "...")

    Inject vault context into AI prompts:

        ctx = bridge.get_context_for_query(user_message)
        system_prompt = base_prompt + (f"\\n\\n{ctx}" if ctx else "")

    Shutdown cleanly with:

        bridge.stop()
    """

    def __init__(
        self,
        config_path:        str = "obsidian_config.json",
        on_note_ingested:   Optional[Callable[["ObsidianNote"], None]] = None,
        on_daily_summary:   Optional[Callable[[], None]] = None,
    ):
        self.config      = load_config(config_path)
        self.config_path = config_path

        vault_raw        = self.config.get("vault_path", "~/Documents/ObsidianVault")
        self.vault_root  = Path(vault_raw).expanduser().resolve()

        self.writer      = VaultWriter(self.vault_root, self.config["subfolders"])

        self._event_q:   queue.Queue                  = queue.Queue()
        self._pool:      List[ObsidianNote]           = []
        self._pool_lock  = threading.Lock()
        self._stop_evt   = threading.Event()

        self._observer:   Optional[Any]               = None  # watchdog Observer
        self._proc_thr:   Optional[threading.Thread]  = None
        self._sched_thr:  Optional[threading.Thread]  = None

        self.on_note_ingested = on_note_ingested
        self.on_daily_summary = on_daily_summary   # Echo calls this to generate text

        self._ready      = False
        self._vault_ok   = False

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def start(self):
        """
        Non-blocking startup — spawns daemon threads and returns immediately
        so Echo's main thread is never blocked.
        """
        self._vault_ok = self.vault_root.exists()

        if not self._vault_ok:
            logger.warning(
                f"Vault not found at {self.vault_root}. "
                "Bridge running in write-only mode. "
                "Create the vault or update vault_path in obsidian_config.json."
            )
        else:
            # Initial scan in background
            threading.Thread(
                target=self._initial_scan, daemon=True, name="obs-scan"
            ).start()

            # File watcher
            if WATCHDOG_AVAILABLE:
                self._start_watcher()
            else:
                logger.warning(
                    "watchdog not installed — live vault watching disabled.\n"
                    "  pip install watchdog --break-system-packages"
                )

        # Event processor (runs even in write-only mode so queue stays drained)
        self._proc_thr = threading.Thread(
            target=self._process_loop, daemon=True, name="obs-proc"
        )
        self._proc_thr.start()

        # Daily scheduler
        self._sched_thr = threading.Thread(
            target=self._scheduler_loop, daemon=True, name="obs-sched"
        )
        self._sched_thr.start()

        self._ready = True
        logger.info(f"ObsidianBridge started — vault: {self.vault_root}")

    def stop(self):
        """Signal all background threads to finish and join the observer."""
        self._stop_evt.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3.0)
        logger.info("ObsidianBridge stopped.")

    def _start_watcher(self):
        handler   = _VaultHandler(self._event_q, self.config)
        self._observer = Observer()

        watch_roots = self.config.get("watch_folders") or []
        if not watch_roots:
            watch_roots = [str(self.vault_root)]

        for folder in watch_roots:
            fp = Path(folder).expanduser().resolve()
            if fp.exists():
                self._observer.schedule(handler, str(fp), recursive=True)
            else:
                logger.warning(f"Watch folder not found, skipping: {fp}")

        self._observer.start()
        logger.debug("Vault watcher started.")

    # -----------------------------------------------------------------------
    # Initial scan
    # -----------------------------------------------------------------------

    def _initial_scan(self):
        ingest = set(self.config.get("ingest_tags", []))
        ignore = set(self.config.get("ignore_tags", []))
        excl   = set(self.config.get("exclude_folders", []))
        count  = 0

        # Sort by mtime descending so freshest notes fill the pool first
        all_md = sorted(
            self.vault_root.rglob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for md in all_md:
            if any(part in excl for part in md.parts):
                continue
            try:
                snippet = md.read_text(encoding="utf-8", errors="replace")[:300]
            except OSError:
                continue
            if "echo-generated" in snippet:
                continue

            note = ObsidianNote(md)
            if note.has_tag(*ignore):
                continue
            if note.has_tag(*ingest):
                self._pool_add(note)
                count += 1

        logger.info(f"Vault scan done — {count} notes loaded into context pool.")

    # -----------------------------------------------------------------------
    # Event processor loop
    # -----------------------------------------------------------------------

    def _process_loop(self):
        ingest = set(self.config.get("ingest_tags", []))
        ignore = set(self.config.get("ignore_tags", []))

        while not self._stop_evt.is_set():
            try:
                evt = self._event_q.get(timeout=1.0)
            except queue.Empty:
                continue

            path = Path(evt["path"])
            if not path.exists():
                continue

            try:
                snippet = path.read_text(encoding="utf-8", errors="replace")[:300]
            except OSError:
                continue
            if "echo-generated" in snippet:
                continue

            note = ObsidianNote(path)
            if note.has_tag(*ignore):
                continue
            if note.has_tag(*ingest):
                self._pool_add(note)
                logger.info(f"Ingested: '{note.title}' tags={note.tags[:4]}")
                if self.on_note_ingested:
                    try:
                        self.on_note_ingested(note)
                    except Exception as e:
                        logger.error(f"on_note_ingested error: {e}")

    # -----------------------------------------------------------------------
    # Scheduler loop
    # -----------------------------------------------------------------------

    def _scheduler_loop(self):
        """Fires daily summary callback at the configured time."""
        last_fired_date: Optional[date] = None

        while not self._stop_evt.wait(timeout=45):
            now         = datetime.now()
            cfg_time    = self.config.get("daily_summary_time", "23:30")
            try:
                h, m = map(int, cfg_time.split(":"))
            except ValueError:
                continue

            today = now.date()
            if (now.hour == h and now.minute == m
                    and last_fired_date != today):
                last_fired_date = today
                logger.info("Scheduler: daily summary time — firing callback.")
                if self.on_daily_summary:
                    try:
                        self.on_daily_summary()
                    except Exception as e:
                        logger.error(f"on_daily_summary error: {e}")

    # -----------------------------------------------------------------------
    # Context pool management
    # -----------------------------------------------------------------------

    def _pool_add(self, note: ObsidianNote):
        max_n = self.config.get("context_max_notes", 12)
        with self._pool_lock:
            self._pool = [n for n in self._pool if n.path != note.path]
            self._pool.append(note)
            self._pool.sort(key=lambda n: n.modified, reverse=True)
            self._pool = self._pool[:max_n]

    # -----------------------------------------------------------------------
    # Context API  (called by Echo's AI layer)
    # -----------------------------------------------------------------------

    def get_context_for_query(self, query: str = "",
                               max_chars: Optional[int] = None) -> str:
        """
        Return a string of relevant vault notes ready to inject into an AI prompt.

        Scoring:
          • notes tagged #echo-context always rank highest
          • keyword overlap with query adds weight
          • recency bonus for notes modified in the last 7 days

        This is intentionally simple (keyword matching).
        Ruflo + RuVector will replace it with vector similarity later.
        """
        max_chars = max_chars or self.config.get("context_max_chars", 4000)

        with self._pool_lock:
            pool = list(self._pool)

        if not pool:
            return ""

        q_words = set(
            w.lower() for w in re.findall(r"\w+", query) if len(w) > 3
        ) if query else set()

        def _score(note: ObsidianNote) -> float:
            s    = 0.0
            text = (note.title + " " + note.body).lower()
            for w in q_words:
                occ = text.count(w)
                if occ:
                    s += min(occ, 5) * 1.0   # cap per-word bonus
            # Recency boost
            age = (datetime.now() - note.modified).days
            s  += max(0.0, 7.0 - age) * 0.5
            # Hard priority for persistent context notes
            if note.has_tag("echo-context"):
                s += 20.0
            return s

        ranked = sorted(pool, key=_score, reverse=True)

        parts: List[str] = []
        used  = 0
        for note in ranked:
            chunk = note.to_context_string(600)
            if used + len(chunk) + 6 > max_chars:
                break
            parts.append(chunk)
            used += len(chunk) + 6  # separator length

        if not parts:
            return ""

        header = f"[Obsidian vault context — {len(parts)} note(s)]\n\n"
        return header + "\n\n---\n\n".join(parts)

    def get_notes_tagged(self, *tags: str) -> List[ObsidianNote]:
        """Return all pool notes matching any of the given tags."""
        with self._pool_lock:
            return [n for n in self._pool if n.has_tag(*tags)]

    def get_recent_user_notes(self, days: int = 1,
                               folder: str = "") -> List[ObsidianNote]:
        """
        Return notes the USER wrote in the last N days (excludes echo-generated).
        Used to enrich the morning briefing with recent Obsidian activity.
        """
        if not self.vault_root.exists():
            return []

        cutoff = time.time() - (days * 86_400)
        excl   = set(self.config.get("exclude_folders", []))
        root   = (self.vault_root / folder) if folder else self.vault_root

        if not root.exists():
            return []

        results: List[ObsidianNote] = []
        for md in root.rglob("*.md"):
            if any(p in excl for p in md.parts):
                continue
            if md.stat().st_mtime < cutoff:
                continue
            try:
                snippet = md.read_text(encoding="utf-8", errors="replace")[:200]
            except OSError:
                continue
            if "echo-generated" in snippet:
                continue
            results.append(ObsidianNote(md))

        return sorted(results, key=lambda n: n.modified, reverse=True)

    # -----------------------------------------------------------------------
    # Write API  (called throughout Echo's runtime)
    # -----------------------------------------------------------------------

    def _write_ok(self) -> bool:
        return bool(self.config.get("write_enabled", True))

    def log_habit(self, name: str, completed: bool,
                  streak: int = 0, note: str = "") -> Optional[Path]:
        if self._write_ok():
            return self.writer.append_habit_entry(name, completed, streak, note)

    def log_task(self, title: str, status: str = "done",
                 priority: str = "normal", note: str = "") -> Optional[Path]:
        if self._write_ok():
            return self.writer.append_task_entry(title, status, priority, note)

    def log_morning_briefing(self, text: str,
                              date_str: str = None) -> Optional[Path]:
        if self._write_ok():
            return self.writer.write_morning_briefing(text, date_str)

    def log_daily_summary(
        self,
        summary:    str,
        tasks_done: Optional[List[str]] = None,
        habits:     Optional[Dict[str, bool]] = None,
    ) -> Optional[Path]:
        if self._write_ok():
            return self.writer.write_daily_summary(summary, tasks_done, habits)

    def log_conversation(self, summary: str, turns: int = 0) -> Optional[Path]:
        if self._write_ok():
            return self.writer.write_conversation_summary(summary, turns)

    def save_memory(self, topic: str, content: str,
                    source: str = "echo") -> Optional[Path]:
        if self._write_ok():
            return self.writer.write_memory_note(topic, content, source)

    def queue_jules_task(self, title: str, description: str,
                          repo: str = "", priority: str = "normal") -> Optional[Path]:
        """
        Write a Jules task note to the vault.
        When the Jules pipeline is built, this note will auto-create a GitHub
        issue and dispatch jules remote new.
        """
        if not self._write_ok():
            return None
        repo = repo or self.config.get("jules_default_repo", "")
        path = self.writer.write_jules_task(title, description, repo, priority)
        logger.info(f"Jules task queued: '{title}' → {path.name}")
        return path

    def log_security_report(self, report: str,
                             target: str = "echo") -> Optional[Path]:
        if self._write_ok():
            return self.writer.write_security_report(report, target)

    def log_status_snapshot(self, data: Dict[str, Any]) -> Optional[Path]:
        if self._write_ok():
            return self.writer.write_status_snapshot(data)

    def log_learning_summary(self, summary_text: str) -> Optional[Path]:
        if self._write_ok():
            return self.writer.write_learning_summary(summary_text)

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        with self._pool_lock:
            pool_size = len(self._pool)
            top_notes = [n.title for n in self._pool[:5]]

        watcher_alive = (
            self._observer is not None and self._observer.is_alive()
        ) if self._observer else False

        return {
            "ready":              self._ready,
            "vault_exists":       self._vault_ok,
            "vault_path":         str(self.vault_root),
            "context_pool_size":  pool_size,
            "top_context_notes":  top_notes,
            "watcher_active":     watcher_alive,
            "write_enabled":      self.config.get("write_enabled", True),
        }

    def __repr__(self) -> str:
        s = self.status()
        return (
            f"<ObsidianBridge "
            f"vault={self.vault_root.name!r} "
            f"pool={s['context_pool_size']} "
            f"watch={'on' if s['watcher_active'] else 'off'}>"
        )


# ============================================================================
# Standalone smoke-test
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-20s  %(levelname)s  %(message)s",
    )

    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "obsidian_config.json"
    bridge   = ObsidianBridge(config_path=cfg_path)
    bridge.start()

    print("\nObsidianBridge status:")
    for k, v in bridge.status().items():
        print(f"  {k:<22} {v}")

    print("\nTesting writes...")
    bridge.log_habit("Morning walk",   completed=True,  streak=3)
    bridge.log_habit("No phone morning", completed=False, streak=0)
    bridge.log_task("Test bridge integration", status="done", priority="high")
    bridge.log_morning_briefing(
        "Good morning. You have 3 tasks today. Habit streak: 3 days. "
        "Recent vault activity: 2 notes modified yesterday."
    )
    bridge.queue_jules_task(
        "Add web search to Echo",
        "Integrate SearXNG into the two-tier streaming pipeline. "
        "Route queries through it when Ollama context is stale.",
        priority="high",
    )
    print("Writes done — check your vault's Echo/ folder.")

    print("\nContext pool (after initial scan):")
    ctx = bridge.get_context_for_query("goals habits")
    if ctx:
        print(ctx[:500])
    else:
        print("  (empty — no #echo-context / #echo-memory tagged notes yet)")

    try:
        print("\nWatching for vault changes... Ctrl-C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()
        print("Stopped.")

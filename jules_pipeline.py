#!/usr/bin/env python3
"""
jules_pipeline.py — Echo → Obsidian → GitHub → Jules Pipeline
Place in: ~/vision_assistant/jules_pipeline.py

Flow:
  1. User creates/updates a note in Obsidian tagged #jules-task
  2. ObsidianBridge detects it (file watcher) and calls our callback
  3. JulesPipeline creates a GitHub issue via REST API
  4. Assigns the issue to the Jules GitHub bot (which auto-picks it up)
  5. Polls GitHub for a PR from Jules
  6. On PR detected: updates the vault note checkboxes + notifies Echo
  7. Echo speaks the result

Prerequisites:
  • Jules GitHub App installed on your repo (jules.google.com → Connect repo)
  • GitHub Personal Access Token (classic) with repo scope
    Settings → Developer settings → Personal access tokens → Generate
  • Set GITHUB_TOKEN and GITHUB_REPO in .env or jules_config.json

Dependencies: requests (already in vision_env)
"""

import os
import re
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any, List

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

logger = logging.getLogger("echo.jules")

# ---------------------------------------------------------------------------
# Jules GitHub bot username (the app files PRs under this identity)
# ---------------------------------------------------------------------------
JULES_BOT_LOGIN = "google-labs-jules[bot]"

GITHUB_API = "https://api.github.com"


# ============================================================================
# Config
# ============================================================================

_DEFAULTS: Dict[str, Any] = {
    # "owner/repo" e.g. "jesus999l/echo-vision"
    "github_repo":          "",

    # GitHub Personal Access Token — or set env var GITHUB_TOKEN
    "github_token":         "",

    # How often (seconds) to poll GitHub for a Jules PR after issue creation
    "poll_interval_seconds": 60,

    # Stop polling after this many seconds (Jules can take 5-20 min)
    "poll_timeout_seconds":  1800,

    # Labels to add to every Jules issue (must exist in the repo)
    "issue_labels":          ["jules", "echo-generated"],

    # Default issue priority label
    "default_priority":      "normal",

    # Write PR link back into the Obsidian vault note when detected
    "update_vault_on_pr":    True,

    # Speak Echo notification when PR is filed
    "speak_on_pr":           True,
}


def load_jules_config(path: str = "jules_config.json") -> Dict[str, Any]:
    cfg = dict(_DEFAULTS)

    fp = Path(path)
    if fp.exists():
        try:
            with open(fp, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            logger.warning(f"Could not read {path}: {e}")

    # Env vars override config file
    if os.environ.get("GITHUB_TOKEN"):
        cfg["github_token"] = os.environ["GITHUB_TOKEN"]
    if os.environ.get("GITHUB_REPO"):
        cfg["github_repo"] = os.environ["GITHUB_REPO"]

    return cfg


def save_jules_config(cfg: Dict[str, Any], path: str = "jules_config.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ============================================================================
# GitHub REST API helpers
# ============================================================================

class GitHubClient:
    """Thin wrapper around GitHub REST API — no PyGithub dependency."""

    def __init__(self, token: str, repo: str):
        """
        token: Personal Access Token (classic), scope: repo
        repo:  "owner/repo" string
        """
        self.token = token.strip()
        self.repo  = repo.strip().strip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization":        f"Bearer {self.token}",
            "Accept":               "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent":           "Echo-Vision/1.0",
        })

    def _url(self, path: str) -> str:
        return f"{GITHUB_API}/repos/{self.repo}/{path.lstrip('/')}"

    def _get(self, path: str, params: dict = None) -> dict:
        r = self._session.get(self._url(path), params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        r = self._session.post(self._url(path), json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        r = self._session.patch(self._url(path), json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    def create_issue(
        self,
        title:    str,
        body:     str,
        labels:   List[str] = None,
        assignees: List[str] = None,
    ) -> Dict[str, Any]:
        """Create a GitHub issue. Returns the full issue JSON."""
        payload: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees

        data = self._post("issues", payload)
        logger.info(f"GitHub issue created: #{data['number']} — {title}")
        return data

    def get_issue(self, number: int) -> Dict[str, Any]:
        return self._get(f"issues/{number}")

    def close_issue(self, number: int) -> Dict[str, Any]:
        return self._patch(f"issues/{number}", {"state": "closed"})

    def list_pull_requests(self, state: str = "open") -> List[Dict[str, Any]]:
        """List PRs. Used to poll for Jules' PR."""
        return self._get("pulls", params={"state": state, "per_page": 20})

    def get_pr_for_issue(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """
        Find a PR that references the given issue number.
        Jules typically creates a branch named something like 'jules/issue-{N}-...'
        and the PR body contains 'Closes #N' or 'Fixes #N'.
        """
        # Check open PRs first, then closed
        for state in ("open", "closed"):
            prs = self._get("pulls", params={"state": state, "per_page": 50})
            if not isinstance(prs, list):
                continue
            for pr in prs:
                body  = (pr.get("body") or "").lower()
                head  = (pr.get("head", {}).get("ref") or "").lower()
                login = (pr.get("user", {}).get("login") or "").lower()

                issue_ref   = str(issue_number)
                closes_it   = bool(re.search(
                    rf"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#?{issue_ref}\b",
                    body,
                ))
                branch_match = f"issue-{issue_number}" in head or issue_ref in head
                from_jules   = "jules" in login or "google" in login

                if (closes_it or branch_match) and from_jules:
                    return pr

                # Fallback: any Jules PR created after the issue
                if from_jules and branch_match:
                    return pr

        return None

    def ensure_labels(self, labels: List[str]):
        """Create any labels that don't exist yet (so issue creation doesn't fail)."""
        try:
            existing = {l["name"] for l in self._get("labels", {"per_page": 100})}
        except Exception:
            return
        colors = {"jules": "7057ff", "echo-generated": "0075ca",
                  "high": "d93f0b", "normal": "e4e669", "low": "0e8a16"}
        for label in labels:
            if label not in existing:
                try:
                    self._post("labels", {
                        "name":  label,
                        "color": colors.get(label, "ededed"),
                    })
                    logger.info(f"Created GitHub label: {label}")
                except Exception as e:
                    logger.warning(f"Could not create label {label!r}: {e}")

    def validate_token(self) -> bool:
        """Return True if the token has repo access."""
        try:
            r = self._session.get(f"{GITHUB_API}/repos/{self.repo}", timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"GitHub token validation failed: {e}")
            return False


# ============================================================================
# Jules task record
# ============================================================================

class JulesTask:
    """Represents one in-flight Jules coding task."""

    def __init__(
        self,
        note_path:      Path,
        title:          str,
        description:    str,
        repo:           str,
        priority:       str = "normal",
        issue_number:   int = 0,
        issue_url:      str = "",
    ):
        self.note_path    = note_path
        self.title        = title
        self.description  = description
        self.repo         = repo
        self.priority     = priority
        self.issue_number = issue_number
        self.issue_url    = issue_url
        self.pr_url       = ""
        self.status       = "queued"   # queued → issue_created → pr_detected → done
        self.created_at   = datetime.now()

    def __repr__(self):
        return f"<JulesTask #{self.issue_number} {self.title[:40]!r} [{self.status}]>"


# ============================================================================
# Vault note updater
# ============================================================================

def _update_note_status(note_path: Path,
                         issue_url: str = "",
                         pr_url:    str = "",
                         merged:    bool = False):
    """
    Tick the status checkboxes in the Jules task note and append the PR link.
    Operates directly on the file — safe because bridge debounces its own writes.
    """
    if not note_path.exists():
        return
    try:
        text = note_path.read_text(encoding="utf-8")
    except OSError:
        return

    if issue_url:
        text = text.replace(
            "- [ ] GitHub issue created",
            f"- [x] GitHub issue created — {issue_url}",
        )

    if pr_url:
        text = text.replace(
            "- [ ] Jules picked up task",
            "- [x] Jules picked up task",
        ).replace(
            "- [ ] PR filed",
            f"- [x] PR filed — {pr_url}",
        )

    if merged:
        text = text.replace(
            "- [ ] Merged into main",
            "- [x] Merged into main",
        )

    # Update frontmatter status
    if issue_url and not pr_url:
        text = re.sub(r"^status: queued", "status: issue_created", text, flags=re.MULTILINE)
    elif pr_url and not merged:
        text = re.sub(r"^status: \w+", "status: pr_filed", text, flags=re.MULTILINE)
    elif merged:
        text = re.sub(r"^status: \w+", "status: merged", text, flags=re.MULTILINE)

    try:
        note_path.write_text(text, encoding="utf-8")
        logger.info(f"Vault note updated: {note_path.name}")
    except OSError as e:
        logger.error(f"Could not update note {note_path}: {e}")


# ============================================================================
# Main pipeline class
# ============================================================================

class JulesPipeline:
    """
    Connects Echo's Obsidian bridge to Google Jules via GitHub.

    Initialise once at Echo startup:
        pipeline = JulesPipeline(
            config_path   = "jules_config.json",
            on_pr_ready   = lambda task: app.speak(f"Jules filed a PR for {task.title}"),
            obsidian_bridge = bridge,    # pass your ObsidianBridge instance
        )
        pipeline.start()

    The pipeline registers itself with the ObsidianBridge so any note tagged
    #jules-task automatically flows through to GitHub and Jules.

    You can also trigger tasks directly from Echo voice commands:
        pipeline.dispatch(
            title       = "Add QUIC transport to Echo Mobile sync",
            description = "Replace the current WiFi Ollama sync with a QUIC...",
            priority    = "high",
        )
    """

    def __init__(
        self,
        config_path:      str = "jules_config.json",
        on_pr_ready:      Optional[Callable[["JulesTask"], None]] = None,
        on_issue_created: Optional[Callable[["JulesTask"], None]] = None,
        obsidian_bridge   = None,   # ObsidianBridge instance (optional)
    ):
        self.config         = load_jules_config(config_path)
        self.on_pr_ready    = on_pr_ready
        self.on_issue_created = on_issue_created
        self._bridge        = obsidian_bridge

        self._client:       Optional[GitHubClient] = None
        self._tasks:        Dict[int, JulesTask]   = {}   # issue_number → task
        self._task_lock     = threading.Lock()
        self._stop_evt      = threading.Event()
        self._dispatch_q:   "queue.Queue[JulesTask]" = __import__("queue").Queue()
        self._ready         = False

    # ------------------------------------------------------------------
    def start(self):
        if not REQUESTS_OK:
            logger.error("requests not installed — Jules pipeline disabled.")
            return

        token = self.config.get("github_token", "")
        repo  = self.config.get("github_repo", "")

        if not token or not repo:
            logger.warning(
                "Jules pipeline not fully configured.\n"
                "  Set github_token and github_repo in jules_config.json\n"
                "  or via GITHUB_TOKEN / GITHUB_REPO environment variables."
            )
            self._ready = False
            return

        self._client = GitHubClient(token, repo)

        if not self._client.validate_token():
            logger.error("GitHub token validation failed — check the token and repo name.")
            return

        # Ensure labels exist so issue creation never fails on a missing label
        labels = self.config.get("issue_labels", ["jules", "echo-generated"])
        self._client.ensure_labels(labels)

        # Register with ObsidianBridge if provided
        if self._bridge is not None:
            original_cb = self._bridge.on_note_ingested

            def _combined(note):
                if original_cb:
                    original_cb(note)
                if note and note.has_tag("jules-task"):
                    self._ingest_from_note(note)

            self._bridge.on_note_ingested = _combined
            logger.info("JulesPipeline hooked into ObsidianBridge.")

        # Dispatcher thread (processes the queue → creates GitHub issues)
        threading.Thread(
            target=self._dispatcher_loop, daemon=True, name="jules-dispatch"
        ).start()

        # Poller thread (watches for PRs on in-flight issues)
        threading.Thread(
            target=self._poller_loop, daemon=True, name="jules-poll"
        ).start()

        self._ready = True
        logger.info(f"JulesPipeline started — repo: {repo}")

    def stop(self):
        self._stop_evt.set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dispatch(
        self,
        title:       str,
        description: str,
        priority:    str   = "normal",
        repo:        str   = "",
        note_path:   Optional[Path] = None,
    ):
        """
        Queue a Jules task from anywhere in Echo (voice command, UI button, etc.)
        Non-blocking — returns immediately. Progress comes via on_pr_ready callback.
        """
        if not self._ready:
            logger.warning("Jules pipeline not ready. Check config and run start().")
            return

        task = JulesTask(
            note_path   = note_path or Path("/dev/null"),
            title       = title,
            description = description,
            repo        = repo or self.config.get("github_repo", ""),
            priority    = priority,
        )
        self._dispatch_q.put(task)
        logger.info(f"Jules task dispatched: {title!r}")

    def dispatch_from_vault_note(self, note_path: Path):
        """Manually trigger pipeline for a specific vault note file."""
        from obsidian_bridge import ObsidianNote  # late import — avoids circular dep
        note = ObsidianNote(note_path)
        self._ingest_from_note(note)

    def get_active_tasks(self) -> List[JulesTask]:
        with self._task_lock:
            return [t for t in self._tasks.values()
                    if t.status not in ("done", "failed")]

    def status(self) -> Dict[str, Any]:
        with self._task_lock:
            active = [t for t in self._tasks.values()
                      if t.status not in ("done", "failed")]
            done   = [t for t in self._tasks.values()
                      if t.status == "done"]
        return {
            "ready":        self._ready,
            "github_repo":  self.config.get("github_repo", ""),
            "active_tasks": len(active),
            "done_tasks":   len(done),
            "active":       [repr(t) for t in active],
        }

    # ------------------------------------------------------------------
    # Internal: ingest from Obsidian note
    # ------------------------------------------------------------------

    def _ingest_from_note(self, note):
        """
        Parse an #jules-task Obsidian note and queue a dispatch.
        Reads title, description, repo, priority from frontmatter.
        """
        if note is None:
            return

        # Skip notes already dispatched (status not 'queued' in frontmatter)
        fm_status = note.frontmatter.get("status", "queued")
        if fm_status not in ("queued", ""):
            logger.debug(f"Skipping already-dispatched note: {note.title}")
            return

        title       = note.title
        description = note.excerpt(1500)   # full body excerpt
        repo        = (note.frontmatter.get("repo", "")
                       or self.config.get("github_repo", "")).strip('"\'')
        priority    = note.frontmatter.get("priority", "normal")

        if not title or not description:
            logger.warning(f"Jules note missing title or body: {note.path}")
            return

        task = JulesTask(
            note_path   = note.path,
            title       = title,
            description = description,
            repo        = repo,
            priority    = priority,
        )
        self._dispatch_q.put(task)

    # ------------------------------------------------------------------
    # Dispatcher loop  (queue → GitHub issue)
    # ------------------------------------------------------------------

    def _dispatcher_loop(self):
        import queue as _queue
        while not self._stop_evt.is_set():
            try:
                task = self._dispatch_q.get(timeout=1.0)
            except _queue.Empty:
                continue

            self._create_issue_for_task(task)

    def _create_issue_for_task(self, task: JulesTask):
        if self._client is None:
            return

        # Build a rich issue body that gives Jules maximum context
        body = self._build_issue_body(task)

        labels = list(self.config.get("issue_labels", ["jules", "echo-generated"]))
        if task.priority in ("high", "critical"):
            labels.append("high")

        try:
            data = self._client.create_issue(
                title    = task.title,
                body     = body,
                labels   = labels,
                # Jules picks up issues assigned to the bot.
                # Alternatively: jules.google.com → the bot monitors labelled issues.
                # assignees = [JULES_BOT_LOGIN],  # ← uncomment if Jules app supports it
            )
        except Exception as e:
            logger.error(f"Failed to create GitHub issue for '{task.title}': {e}")
            task.status = "failed"
            return

        task.issue_number = data["number"]
        task.issue_url    = data["html_url"]
        task.status       = "issue_created"

        with self._task_lock:
            self._tasks[task.issue_number] = task

        # Update vault note — tick "GitHub issue created"
        if self.config.get("update_vault_on_pr", True) and task.note_path.exists():
            _update_note_status(task.note_path, issue_url=task.issue_url)

        logger.info(f"Issue #{task.issue_number} created: {task.issue_url}")

        if self.on_issue_created:
            try:
                self.on_issue_created(task)
            except Exception as e:
                logger.error(f"on_issue_created callback error: {e}")

    def _build_issue_body(self, task: JulesTask) -> str:
        return f"""## Echo-generated Jules task

**Requested by:** Echo (voice assistant, {datetime.now().strftime('%Y-%m-%d %H:%M')})  
**Priority:** {task.priority}  
**Source:** Obsidian vault note → `{task.note_path.name}`

---

## Description

{task.description}

---

## Context

- Project: Echo Vision Assistant (Python/Tkinter, Linux Mint)
- Venv: `~/vision_env`
- Project root: `~/vision_assistant/`
- Stack: Ollama (gemma3), Vosk STT, Piper TTS, webrtcvad, SQLite

## Acceptance criteria

- [ ] Code runs inside `vision_env` (Python 3.11, Linux Mint 22.3)
- [ ] No new heavy dependencies without a comment explaining why
- [ ] Compatible with the existing Tkinter main loop (thread-safe if async)
- [ ] A brief usage comment at the top of any new file

---
*Auto-filed by Echo's Jules pipeline — `jules_pipeline.py`*
"""

    # ------------------------------------------------------------------
    # Poller loop  (GitHub → PR detection)
    # ------------------------------------------------------------------

    def _poller_loop(self):
        """
        Polls GitHub every poll_interval_seconds for Jules PRs on active tasks.
        Designed to run for hours — very lightweight, just a few API calls.
        """
        interval = self.config.get("poll_interval_seconds", 60)
        timeout  = self.config.get("poll_timeout_seconds", 1800)

        while not self._stop_evt.wait(timeout=interval):
            with self._task_lock:
                active = [t for t in self._tasks.values()
                          if t.status == "issue_created"]

            now = datetime.now()
            for task in active:
                # Give up after timeout
                age = (now - task.created_at).total_seconds()
                if age > timeout:
                    logger.warning(
                        f"Jules task #{task.issue_number} timed out "
                        f"after {int(age/60)} min — no PR detected."
                    )
                    task.status = "timed_out"
                    continue

                self._check_for_pr(task)

    def _check_for_pr(self, task: JulesTask):
        if self._client is None:
            return
        try:
            pr = self._client.get_pr_for_issue(task.issue_number)
        except Exception as e:
            logger.debug(f"PR poll error for #{task.issue_number}: {e}")
            return

        if not pr:
            return

        task.pr_url = pr["html_url"]
        task.status = "pr_detected"

        logger.info(
            f"Jules PR detected for #{task.issue_number}: {task.pr_url}"
        )

        # Update vault note — tick "Jules picked up" and "PR filed"
        if self.config.get("update_vault_on_pr", True) and task.note_path.exists():
            _update_note_status(task.note_path, pr_url=task.pr_url)

        # Notify Echo
        if self.on_pr_ready:
            try:
                self.on_pr_ready(task)
            except Exception as e:
                logger.error(f"on_pr_ready callback error: {e}")

        # Close the tracking issue (Jules will reference it in the PR)
        try:
            self._client.close_issue(task.issue_number)
            task.status = "done"
        except Exception as e:
            logger.warning(f"Could not close issue #{task.issue_number}: {e}")


# ============================================================================
# Echo integration helpers  (call these from your main Echo file)
# ============================================================================

def build_jules_pipeline(
    obsidian_bridge,
    on_pr_ready:      Optional[Callable] = None,
    on_issue_created: Optional[Callable] = None,
    config_path:      str = "jules_config.json",
) -> JulesPipeline:
    """
    Convenience factory. Call once during Echo startup, pass your ObsidianBridge.

    Example Echo integration:

        from jules_pipeline import build_jules_pipeline

        # Inside EchoApp.__init__, after self.obsidian.start():
        self.jules = build_jules_pipeline(
            obsidian_bridge = self.obsidian,
            on_pr_ready     = lambda t: self.speak(
                f"Jules filed a pull request for: {t.title}. Check GitHub."
            ),
            on_issue_created = lambda t: self.speak(
                f"GitHub issue created. Jules is now working on: {t.title}"
            ),
        )
        self.jules.start()

        # Voice command hook — in your intent dispatcher:
        # "queue jules task add dark mode to echo"
        # → self.jules.dispatch(title="Add dark mode to Echo", description="...")

        # Shutdown:
        # self.jules.stop()
    """
    pipeline = JulesPipeline(
        config_path      = config_path,
        on_pr_ready      = on_pr_ready,
        on_issue_created = on_issue_created,
        obsidian_bridge  = obsidian_bridge,
    )
    return pipeline


# ============================================================================
# Smoke test
# ============================================================================

if __name__ == "__main__":
    import sys
    import queue
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-22s  %(levelname)s  %(message)s",
    )

    cfg = load_jules_config()

    if not cfg.get("github_token") or not cfg.get("github_repo"):
        print(
            "\nJules pipeline requires github_token and github_repo in jules_config.json.\n"
            "  1. Go to: github.com → Settings → Developer settings → Personal access tokens\n"
            "  2. Generate a classic token with 'repo' scope\n"
            "  3. Add to jules_config.json:\n"
            '     { "github_token": "ghp_...", "github_repo": "yourname/echo-vision" }\n'
            "\nInstall Jules GitHub App at: jules.google.com → 'Add to GitHub'\n"
        )
        sys.exit(0)

    client = GitHubClient(cfg["github_token"], cfg["github_repo"])
    print(f"\nValidating GitHub token for {cfg['github_repo']}...")
    if client.validate_token():
        print("  ✓ Token valid")
    else:
        print("  ✗ Token invalid — check github_token and github_repo")
        sys.exit(1)

    print("\nJules pipeline ready. In Echo, use:")
    print("  self.jules.dispatch(title='Fix X', description='Details...')")
    print("\nOr tag an Obsidian note with #jules-task and it will auto-dispatch.")

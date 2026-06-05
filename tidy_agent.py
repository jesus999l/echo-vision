import os
import shutil
import json
import subprocess
from datetime import datetime
from pathlib import Path


# Extension → folder name map. Extend as needed.
CATEGORY_MAP = {
    # Code
    ".py": "code/python",
    ".js": "code/javascript",
    ".ts": "code/typescript",
    ".sh": "code/shell",
    ".md": "docs/markdown",
    ".txt": "docs/text",
    ".pdf": "docs/pdf",
    # Media
    ".jpg": "media/images", ".jpeg": "media/images",
    ".png": "media/images", ".webp": "media/images",
    ".gif": "media/images", ".svg": "media/images",
    ".mp4": "media/video", ".mkv": "media/video",
    ".mp3": "media/audio", ".flac": "media/audio",
    ".wav": "media/audio",
    # Archives
    ".zip": "archives", ".tar": "archives",
    ".gz": "archives", ".7z": "archives",
    # Data
    ".json": "data", ".csv": "data",
    ".xml": "data", ".yaml": "data", ".yml": "data",
    # Config/dotfiles
    ".conf": "config", ".cfg": "config",
    ".ini": "config", ".toml": "config",
}

SKIP_NAMES = {".git", "__pycache__", "node_modules", ".obsidian", "venv", ".venv"}


class TidyAgent:
    def __init__(self, vault_path: str, git_repo_path: str):
        self.vault_path = Path(vault_path)
        self.git_repo_path = Path(git_repo_path)
        self.state = "idle"
        self.pending_plan = []

    # ------------------------------------------------------------------ #
    #  SCAN                                                                #
    # ------------------------------------------------------------------ #

    def scan(self, target_dir: str) -> dict:
        target = Path(target_dir).expanduser().resolve()
        if not target.exists():
            return {"status": "error", "message": f"Directory not found: {target}"}

        plan = []
        unclassified = []

        for item in target.iterdir():
            if item.name.startswith(".") or item.name in SKIP_NAMES:
                continue
            if item.is_dir():
                continue  # Don't touch subdirectories in first pass

            ext = item.suffix.lower()
            category = CATEGORY_MAP.get(ext)

            if category:
                dest = target / category / item.name
                plan.append({
                    "action": "move",
                    "src": str(item),
                    "dst": str(dest),
                    "category": category,
                })
            else:
                unclassified.append(item.name)

        self.pending_plan = plan
        self.state = "review"

        return {
            "status": "review",
            "target": str(target),
            "moves_planned": len(plan),
            "unclassified": unclassified,
            "plan": plan,
        }

    # ------------------------------------------------------------------ #
    #  EXECUTE                                                             #
    # ------------------------------------------------------------------ #

    def execute(self) -> dict:
        if self.state != "review" or not self.pending_plan:
            return {"status": "error", "message": "No approved plan to execute."}

        executed = []
        failed = []

        for op in self.pending_plan:
            try:
                src = Path(op["src"])
                dst = Path(op["dst"])
                dst.parent.mkdir(parents=True, exist_ok=True)

                # Don't overwrite — append timestamp suffix if collision
                if dst.exists():
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dst = dst.with_stem(f"{dst.stem}_{ts}")
                    op["dst"] = str(dst)

                shutil.move(str(src), str(dst))
                executed.append(op)
            except Exception as e:
                failed.append({"op": op, "error": str(e)})

        self.state = "done" if not failed else "partial"
        self._commit_manifest(executed, failed)
        self._write_obsidian_note(executed, failed)

        return {
            "status": self.state,
            "executed": len(executed),
            "failed": len(failed),
            "details": executed,
            "errors": failed,
        }

    def abort(self):
        self.pending_plan = []
        self.state = "aborted"
        return {"status": "aborted", "message": "Tidy plan discarded. No files moved."}

    # ------------------------------------------------------------------ #
    #  GIT MANIFEST                                                        #
    # ------------------------------------------------------------------ #

    def _commit_manifest(self, executed: list, failed: list):
        try:
            manifest_path = self.git_repo_path / "tidy_manifests"
            manifest_path.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            mfile = manifest_path / f"tidy_{ts}.json"
            mfile.write_text(json.dumps({
                "timestamp": ts,
                "executed": executed,
                "failed": failed,
            }, indent=2))

            subprocess.run(["git", "add", str(mfile)], cwd=self.git_repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"[TidyAgent] File organization manifest {ts}"],
                cwd=self.git_repo_path, check=True
            )
        except Exception as e:
            print(f"[TidyAgent] Git commit failed: {e}")

    # ------------------------------------------------------------------ #
    #  OBSIDIAN NOTE                                                       #
    # ------------------------------------------------------------------ #

    def _write_obsidian_note(self, executed: list, failed: list):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            note_dir = self.vault_path / "Echo" / "TidyAgent"
            note_dir.mkdir(parents=True, exist_ok=True)
            note_path = note_dir / f"tidy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

            lines = [
                f"# TidyAgent Run — {ts}",
                "",
                f"**Files moved:** {len(executed)}  |  **Failures:** {len(failed)}",
                "",
                "## Moves",
                "| File | → Destination |",
                "| --- | --- |",
            ]
            for op in executed:
                fname = Path(op["src"]).name
                dst_short = Path(op["dst"]).parent.name
                lines.append(f"| `{fname}` | `{dst_short}/` |")

            if failed:
                lines += ["", "## Failures"]
                for f in failed:
                    lines.append(f"- `{Path(f['op']['src']).name}`: {f['error']}")

            note_path.write_text("\n".join(lines))
        except Exception as e:
            print(f"[TidyAgent] Obsidian write failed: {e}")

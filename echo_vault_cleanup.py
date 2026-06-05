#!/usr/bin/env python3
"""
Echo Vault Cleanup Agent — Stage 1
Fixes the Plans/ shattering problem, cleans root orphans, rebuilds INDEX.md.
Run once on demand: python3 echo_vault_cleanup.py [--dry-run]
"""
import os, re, sys, shutil, json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

VAULT      = Path.home() / "Documents/ObsidianVault/Echo"
PLANS      = VAULT / "Plans"
KB         = VAULT / "Knowledge_Base"
ARCHIVE    = VAULT / "Archive"
COGNITION  = VAULT / "Cognition"
DRY_RUN    = "--dry-run" in sys.argv

# ── helpers ──────────────────────────────────────────────────────────

def log(msg): print(msg)

def read_file(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as e:
        return ""

def write_file(path, content):
    if DRY_RUN:
        log(f"  [dry] would write → {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def move_file(src, dst):
    if DRY_RUN:
        log(f"  [dry] would move {src.name} → {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

# ── Step 1: Detect & merge shattered Plans/ ──────────────────────────

TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})_(.+)\.md$")

def get_fragment_content(path):
    """Get content: prefer file body, fall back to filename text."""
    body = read_file(path)
    if body and len(body) > 10:
        return body
    # Decode content from filename
    stem = path.stem
    m = TIMESTAMP_RE.match(path.name)
    if m:
        raw = m.group(3)
        # Decode common substitutions from Echo's file naming
        text = raw.replace("-", " ").replace("_", " ")
        return text
    return stem

def merge_shattered_plans():
    """
    Group Plans/ files by date. Dates with >5 files are shattering events.
    Merge into single KB or Cognition entry, archive originals.
    """
    if not PLANS.exists():
        log("  Plans/ folder not found, skipping.")
        return []

    files = [f for f in PLANS.glob("*.md") if f.name != "INDEX.md"]
    if not files:
        log("  Plans/ is empty.")
        return []

    # Group by date
    groups = defaultdict(list)
    ungrouped = []
    for f in files:
        m = TIMESTAMP_RE.match(f.name)
        if m:
            groups[m.group(1)].append(f)
        else:
            ungrouped.append(f)

    results = []
    for date_key, group_files in sorted(groups.items()):
        if len(group_files) <= 5:
            # Not shattered — valid individual plan files, leave them
            log(f"  {date_key}: {len(group_files)} files — leaving as-is")
            continue

        # Shattering event — merge
        group_files.sort(key=lambda f: f.name)
        log(f"\n  {date_key}: {len(group_files)} fragments detected → merging")

        # Build content
        lines = []
        seen = set()
        for f in group_files:
            content = get_fragment_content(f)
            if content and content not in seen and len(content) > 2:
                seen.add(content)
                lines.append(content)

        # Produce merged document
        merged_body = "\n".join(lines)
        # Infer title from first meaningful line
        title_line = next((l for l in lines if len(l) > 10 and not l.startswith("---")), f"Echo Plan {date_key}")
        title_slug = re.sub(r"[^\w\-]", "-", title_line[:50].lower()).strip("-")
        out_path = COGNITION / f"plan-{date_key}-{title_slug[:30]}.md"

        now = datetime.now().isoformat(timespec="seconds")
        content = f"""---
compiled_at: {now}
source_files: {len(group_files)} fragments from Plans/{date_key}
tags: [distilled, plan, merged]
status: stable
---

# Echo Plan — {date_key}

{merged_body}
"""
        write_file(out_path, content)

        # Archive originals
        archive_sub = ARCHIVE / f"plans_merged_{date_key}"
        for f in group_files:
            dest = archive_sub / f.name
            move_file(f, dest)

        results.append({
            "date": date_key,
            "fragments": len(group_files),
            "output": out_path.name
        })
        log(f"  ✓ Merged {len(group_files)} fragments → {out_path.name}")

    # Handle ungrouped
    for f in ungrouped:
        content = read_file(f)
        if len(content) < 50:
            log(f"  [skip] {f.name} — too short ({len(content)} chars)")

    return results

# ── Step 2: Clean root orphans ────────────────────────────────────────

def clean_root_orphans():
    """Move malformed/stray .md files in vault root to Archive."""
    vault_root = VAULT.parent
    cleaned = []

    for f in vault_root.glob("*.md"):
        # Flag files with weird names (control chars, code fragments, etc.)
        if re.search(r"[<>`\[\]{}|\\]|ctrl\+|self\.", f.name):
            dest = ARCHIVE / f"root_orphan_{f.name}"
            move_file(f, dest)
            cleaned.append(f.name)
            log(f"  ✓ Archived root orphan: {f.name[:60]}...")

    return cleaned

# ── Step 3: Rebuild INDEX.md ──────────────────────────────────────────

def rebuild_index():
    """Write a fresh Plans/INDEX.md and a vault-wide VAULT_INDEX.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Collect all vault files
    kb_files      = sorted(KB.glob("*.md"))
    cognition_files = sorted(COGNITION.glob("*.md"))
    plan_files    = sorted([f for f in PLANS.glob("*.md") if f.name != "INDEX.md"])
    conv_files    = sorted((VAULT / "Conversations").glob("*.md"))
    daily_files   = sorted((VAULT / "Daily").glob("*.md"))

    lines = [
        f"# Echo Vault Index",
        f"updated: {now}",
        f"",
        f"## Knowledge Base ({len(kb_files)} entries)",
        ""
    ]
    for f in kb_files:
        lines.append(f"- [[Knowledge_Base/{f.stem}]]")

    if cognition_files:
        lines += ["", f"## Cognition / Plans ({len(cognition_files)} entries)", ""]
        for f in cognition_files:
            lines.append(f"- [[Cognition/{f.stem}]]")

    if plan_files:
        lines += ["", f"## Active Plans ({len(plan_files)})", ""]
        for f in plan_files:
            lines.append(f"- [[Plans/{f.stem}]]")

    lines += ["", f"## Conversations ({len(conv_files)})", ""]
    for f in conv_files[-10:]:  # last 10 only
        lines.append(f"- [[Conversations/{f.stem}]]")
    if len(conv_files) > 10:
        lines.append(f"- ... and {len(conv_files)-10} more")

    lines += ["", f"## Daily Notes ({len(daily_files)})", ""]
    for f in daily_files[-7:]:
        lines.append(f"- [[Daily/{f.stem}]]")

    content = "\n".join(lines) + "\n"

    # Write to Plans/INDEX.md and vault root
    write_file(PLANS / "INDEX.md", content)
    write_file(VAULT / "INDEX.md", content)

    log(f"  ✓ INDEX.md written ({len(lines)} lines)")
    return VAULT / "INDEX.md"

# ── Step 4: Verify KB entries have proper frontmatter ─────────────────

def audit_kb():
    """Flag KB entries missing frontmatter or status tags."""
    issues = []
    for f in KB.glob("*.md"):
        content = read_file(f)
        if not content.startswith("---"):
            issues.append((f.name, "missing frontmatter"))
        elif "status:" not in content[:300]:
            issues.append((f.name, "missing status tag"))
    return issues

# ── Main ──────────────────────────────────────────────────────────────

def run():
    if DRY_RUN:
        log("DRY RUN — no files will be modified\n")

    log("=" * 50)
    log("Echo Vault Cleanup Agent")
    log(f"Vault: {VAULT}")
    log("=" * 50)

    log("\n[1/4] Merging shattered Plans/ fragments...")
    merged = merge_shattered_plans()

    log("\n[2/4] Cleaning root orphans...")
    orphans = clean_root_orphans()
    if not orphans:
        log("  No orphans found.")

    log("\n[3/4] Rebuilding INDEX.md...")
    rebuild_index()

    log("\n[4/4] Auditing KB entries...")
    issues = audit_kb()
    if issues:
        for name, issue in issues:
            log(f"  ⚠ {name}: {issue}")
    else:
        log("  ✓ All KB entries have proper frontmatter.")

    log("\n" + "=" * 50)
    log("Summary:")
    log(f"  Plan clusters merged : {len(merged)}")
    log(f"  Root orphans archived: {len(orphans)}")
    log(f"  KB issues flagged    : {len(issues)}")
    if DRY_RUN:
        log("\n  (dry run — nothing written)")
    log("=" * 50)

if __name__ == "__main__":
    run()

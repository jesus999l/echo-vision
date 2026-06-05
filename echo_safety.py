#!/usr/bin/env python3
"""
echo_safety.py — Command Safety Filter + Token Discipline
Import in echo_research_loop.py:
    from echo_safety import is_safe, truncate, compact_prompt
"""
import re, shlex
from pathlib import Path

# ── BLOCKED: never run, ever ──────────────────────────────────────────
BLOCKED = [
    r"rm\s+-rf?\s*/",           # rm -rf /
    r"rm\s+-rf?\s*~",           # rm -rf ~
    r"mkfs",                    # format disk
    r"dd\s+if=",                # disk wipe
    r":\(\)\{.*\}",             # fork bomb
    r">\s*/dev/sd",             # overwrite disk
    r"chmod\s+-R\s+777\s+/",    # open system perms
    r"curl.*(bash|sh)\s*\|",    # curl pipe to shell
    r"wget.*(bash|sh)\s*\|",
    r"pkill\s+-9\s+-1",         # kill all processes
    r"shutdown|reboot|halt",    # system control
    r"systemctl\s+(stop|disable)\s+ssh",  # kill SSH
    r"iptables\s+-F",           # flush firewall
    r"DROP\s+TABLE",            # SQL destructive
]

# ── WARN: require manual gate even in semi/supervised mode ────────────
WARN = [
    r"sudo\s+rm",
    r"adb\s+factory-reset",
    r"adb\s+shell\s+wipe",
    r"git\s+(push|reset\s+--hard)",
    r"pip.*uninstall",
    r"systemctl\s+restart\s+(ollama|echo|hermes)",
    r"pkill.*python",
    r"mv\s+.*\s+/dev/null",
]

# ── PATH GUARDS: never write outside these ────────────────────────────
SAFE_WRITE_ROOTS = [
    Path.home() / "vision_assistant",
    Path.home() / "Documents/ObsidianVault",
    Path.home() / "echo_tv_native",
    Path.home() / "queue",
    Path("/tmp"),
]

def _matches(patterns, cmd):
    for pat in patterns:
        if re.search(pat, cmd, re.IGNORECASE):
            return pat
    return None

def is_safe(command: str) -> dict:
    """
    Returns {"safe": bool, "level": "ok|warn|blocked", "reason": str}
    """
    if not command or not command.strip():
        return {"safe": True, "level": "ok", "reason": "empty"}

    cmd = command.strip()

    # Check blocked
    pat = _matches(BLOCKED, cmd)
    if pat:
        return {"safe": False, "level": "blocked", "reason": f"Matches blocked pattern: {pat}"}

    # Check warn
    pat = _matches(WARN, cmd)
    if pat:
        return {"safe": True, "level": "warn", "reason": f"Elevated risk: {pat}"}

    return {"safe": True, "level": "ok", "reason": "clean"}

def check_plan(steps: list) -> list:
    """
    Check all steps in a plan. Returns list of issues.
    [{step_id, level, reason, command}]
    """
    issues = []
    for step in steps:
        cmd = step.get("command")
        if not cmd:
            continue
        result = is_safe(cmd)
        if result["level"] != "ok":
            issues.append({
                "step_id": step.get("id", "?"),
                "level": result["level"],
                "reason": result["reason"],
                "command": cmd
            })
    return issues

# ── TOKEN DISCIPLINE ──────────────────────────────────────────────────

MAX_OUTPUT    = 500   # chars from command output sent to LLM
MAX_KB_ENTRIES = 3    # max KB entries in any single prompt
MAX_PROMPT    = 2000  # total prompt char budget (soft limit)

def truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    """Truncate text, keeping start and end if too long."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n...[{len(text)-limit} chars truncated]...\n" + text[-half:]

def compact_prompt(objective: str, last_result: str = "", kb_context: str = "") -> str:
    """
    Build a token-efficient prompt.
    Rule: objective + last result + 3 KB entries MAX. Nothing else.
    """
    parts = [f"Objective: {objective}"]

    if kb_context:
        # Truncate KB context hard
        kb_lines = kb_context.split("\n")
        kb_short = "\n".join(kb_lines[:30])  # max 30 lines of KB
        parts.append(f"\nRelevant context:\n{kb_short}")

    if last_result:
        parts.append(f"\nLast result:\n{truncate(last_result, 300)}")

    return "\n".join(parts)

def summarize_output(raw_output: str, model_fn=None) -> str:
    """
    Summarize long command output before sending to LLM.
    If model_fn provided, uses LLM for smart summary.
    Otherwise truncates.
    """
    if not raw_output or len(raw_output) <= MAX_OUTPUT:
        return raw_output

    if model_fn:
        prompt = f"Summarize this command output in 2-3 sentences, preserving errors and key values:\n\n{raw_output[:2000]}"
        summary = model_fn(prompt)
        return summary if summary else truncate(raw_output)

    return truncate(raw_output)

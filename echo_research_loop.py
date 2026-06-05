#!/usr/bin/env python3
"""
Echo Research Loop Agent
Autonomous research → plan → execute → analyze → fix → repeat

Modes:
  manual     (C) — gate blocks, waits for your approval each step
  supervised (B) — gate auto-proceeds, notifies via Discord + log
  semi       (A) — gate posts to Discord, waits 60s, auto-proceeds if no STOP

Usage:
  python3 echo_research_loop.py "objective here"       # uses current mode
  python3 echo_research_loop.py --mode semi "obj"      # override mode
  python3 echo_research_loop.py --status               # show mode + loop state
  python3 echo_research_loop.py --set-mode manual      # save mode

Mode auto-detection (if ~/.echo_mode not set):
  idle > 5min AND hour 21-07 → semi
  multiple terminals active  → supervised
  otherwise                  → manual
"""

import os, sys, re, json, time, signal, logging, subprocess, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
from textwrap import indent

# ── AI Provider priority (Claude is LAST) ──
PROVIDER_CHAIN = [
    {"base_url": "http://localhost:3210/v1",  "model": "chatgpt",              "name": "ChatGPT"},
    {"base_url": "http://localhost:3210/v1",  "model": "gemini",               "name": "Gemini"},
    {"base_url": "http://localhost:3210/v1",  "model": "perplexity",           "name": "Perplexity"},
    {"base_url": "http://localhost:20128/v1", "model": "oc/auto",              "name": "OpenCode-Free"},
    {"base_url": "http://localhost:20128/v1", "model": "glm/glm-5.1",         "name": "GLM"},
    {"base_url": "http://localhost:20128/v1", "model": "kr/claude-sonnet-4.5","name": "Claude-LastResort"},
]
ACTIVE_PROVIDER = PROVIDER_CHAIN[0]  # start with ChatGPT

# ── CONFIG ────────────────────────────────────────────────────────────

VAULT        = Path.home() / "Documents/ObsidianVault/Echo"
KB           = VAULT / "Knowledge_Base"
SUBCONSCIOUS = VAULT / "Subconscious"
LOGS         = VAULT / "Logs"
MODE_FILE    = Path.home() / ".echo_mode"
LOOP_LOG     = Path.home() / "vision_assistant/logs/echo_loop.log"

OLLAMA_URL   = "http://127.0.0.1:11434/api/generate"
PLAN_MODEL   = "qwen3:4b"
FAST_MODEL   = "qwen3:4b"
EMBED_MODEL  = "nomic-embed-text"

SEMI_TIMEOUT    = 60    # seconds to wait before auto-proceeding in semi mode
MAX_RETRIES     = 3     # max fix attempts before giving up
HERMES_WEBHOOK  = None
NINER_API_KEY = ""
NTFY_TOPIC = "echojesus999"  # change to anything private  # set to Discord webhook URL if available

# ── LOGGING ───────────────────────────────────────────────────────────

LOOP_LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOOP_LOG),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("echo_loop")

# ── MODE MANAGEMENT ───────────────────────────────────────────────────

MODES = {"manual", "supervised", "semi"}

def detect_mode():
    """Auto-detect mode from system state."""
    try:
        hour = datetime.now().hour
        # Check idle time
        idle_ms = int(subprocess.check_output(["xprintidle"], stderr=subprocess.DEVNULL))
        idle_min = idle_ms / 60000
        if idle_min > 5 and (hour >= 21 or hour <= 7):
            return "semi"
        if idle_min > 2:
            return "supervised"
    except:
        pass
    # Check terminal count as proxy for multitasking
    try:
        terms = subprocess.check_output(
            ["pgrep", "-c", "-x", "zsh"], stderr=subprocess.DEVNULL
        )
        if int(terms.strip()) > 2:
            return "supervised"
    except:
        pass
    return "manual"

def get_mode():
    if MODE_FILE.exists():
        m = MODE_FILE.read_text().strip().lower()
        if m in MODES:
            return m
    return detect_mode()

def set_mode(mode):
    if mode not in MODES:
        raise ValueError(f"Invalid mode: {mode}. Choose: {MODES}")
    MODE_FILE.write_text(mode)
    log.info(f"Mode set to: {mode}")

# ── OLLAMA ────────────────────────────────────────────────────────────

def ollama(prompt, model=FAST_MODEL, timeout=300):
    # Try Proxima bridge first (Proxima → OpenRouter → local Ollama)
    try:
        sys.path.insert(0, str(Path.home() / "vision_assistant"))
        from echo_proxima_bridge import ask_text
        result = ask_text(prompt)
        if result:
            if "</think>" in result:
                result = result.split("</think>")[-1].strip()
            log.debug(f"Bridge response: {result[:50]}")
            return result
    except Exception as e:
        log.debug(f"Bridge unavailable, falling back to local: {e}")

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 800}
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            response = json.loads(r.read()).get("response", "").strip()
            # Strip qwen3 thinking section
            if "</think>" in response:
                response = response.split("</think>")[-1].strip()
            return response
    except Exception as e:
        log.error(f"Ollama error: {e}")
        return None

def ollama_json(prompt, model=FAST_MODEL):
    resp = ollama(prompt, model)
    if not resp:
        return None
    try:
        clean = re.sub(r"```json\s*|```\s*", "", resp).strip()
        return json.loads(clean)
    except:
        return {"raw": resp}

# ── KB CONTEXT ────────────────────────────────────────────────────────

def get_kb_context(query):
    try:
        sys.path.insert(0, str(Path.home() / "vision_assistant"))
        from echo_kb_context import get_kb_context as _get
        return _get(query)
    except:
        return ""

# ── NOTIFICATION ──────────────────────────────────────────────────────

def notify(message, level="info"):
    prefix = {"info":"ℹ️","warn":"⚠️","success":"✅","error":"❌","gate":"🔐"}.get(level,"•")
    log.info(f"[notify/{level}] {message}")
    if NINER_API_KEY = ""
NTFY_TOPIC:
        import urllib.request as _ur
        try:
            _r = _ur.Request(
                f"https://ntfy.sh/{NINER_API_KEY = ""
NTFY_TOPIC}",
                data=f"{prefix} {message}".encode(),
                headers={"Title": f"Echo [{level}]", "Priority": "default"}
            )
            _ur.urlopen(_r, timeout=5)
        except Exception as e:
            log.warning(f"ntfy failed: {e}")


def save_to_subconscious(title, content):
    """Drop a note into Subconscious/ for the watcher to pick up."""
    SUBCONSCIOUS.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\-]", "-", title.lower())[:50]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SUBCONSCIOUS / f"{ts}_{slug}.md"
    path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    log.info(f"Saved to Subconscious: {path.name}")
    return path

# ── GATE ──────────────────────────────────────────────────────────────

class Gate:
    def __init__(self, mode):
        self.mode = mode

    def request(self, plan_summary, commands, risk="medium"):
        """
        Show the plan and wait for approval based on mode.
        Returns True to proceed, False to abort.
        """
        border = "═" * 52
        print(f"\n{border}")
        print(f"  🔐 GATE — {self.mode.upper()} MODE")
        print(border)
        print(f"\n  Objective: {plan_summary}")
        print(f"\n  Commands to run:")
        for i, cmd in enumerate(commands, 1):
            print(f"    {i}. {cmd}")
        print(f"\n  Risk: {risk.upper()}")
        print(f"{border}\n")

        if self.mode == "manual":
            return self._manual_gate()
        elif self.mode == "supervised":
            return self._supervised_gate(plan_summary, commands)
        elif self.mode == "semi":
            return self._semi_gate(plan_summary, commands)

    def _manual_gate(self):
        """Block until explicit approval."""
        while True:
            try:
                ans = input("  Approve? [y/n/edit] > ").strip().lower()
            except EOFError:
                log.warning("Gate: no stdin — defaulting to abort in manual mode")
                return False
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", "abort"):
                return False
            if ans == "edit":
                print("  (Edit not yet implemented — approve or abort)")

    def _supervised_gate(self, summary, commands):
        """Auto-proceed, log everything."""
        notify(f"Auto-proceeding: {summary}", "gate")
        return True

    def _semi_gate(self, summary, commands):
        """Post to Discord, wait SEMI_TIMEOUT seconds. STOP = abort."""
        msg = (
            f"**Plan ready:** {summary}\n"
            f"Commands: `{'` | `'.join(commands[:3])}`\n"
            f"Auto-proceeding in {SEMI_TIMEOUT}s. Reply **STOP** to abort."
        )
        notify(msg, "gate")
        print(f"  Waiting {SEMI_TIMEOUT}s (type STOP to abort)...")

        class _Stopped(Exception): pass
        stopped = [False]

        def _listen():
            try:
                ans = input()
                if ans.strip().upper() == "STOP":
                    stopped[0] = True
            except:
                pass

        import threading
        t = threading.Thread(target=_listen, daemon=True)
        t.start()
        t.join(timeout=SEMI_TIMEOUT)

        if stopped[0]:
            notify("Aborted by STOP command.", "warn")
            return False
        return True

# ── RESEARCH PHASE ────────────────────────────────────────────────────

def research(objective):
    """
    Generate research findings for the objective.
    Uses KB context + Ollama to produce structured findings.
    Returns dict with: summary, findings, unknowns, suggested_approach
    """
    log.info(f"Research phase: {objective}")
    kb_ctx = get_kb_context(objective)

    prompt = f"""You are Echo's research agent. Given an objective, produce a research brief.
Return ONLY valid JSON:
{{"summary":"str","findings":["concrete finding"],"unknowns":["what is still unclear"],"suggested_approach":"one paragraph","estimated_commands":["command1","command2"],"risk":"low|medium|high"}}

{f'KNOWN CONTEXT FROM KB:{chr(10)}{kb_ctx}{chr(10)}' if kb_ctx else ''}

Objective: {objective}"""

    result = ollama_json(prompt, model=PLAN_MODEL)
    if not result or result.get("raw"):
        # Fallback
        result = {
            "summary": objective,
            "findings": ["No prior KB context found"],
            "unknowns": ["Approach unclear without prior data"],
            "suggested_approach": "Start with diagnostic commands to gather system state.",
            "estimated_commands": [],
            "risk": "medium"
        }

    log.info(f"Research complete. Risk: {result.get('risk','?')}")
    return result

# ── PLAN PHASE ────────────────────────────────────────────────────────

def generate_plan(objective, research_brief):
    """
    Generate an executable plan from research findings.
    Returns: {steps: [{action, command, risk, reversible, explanation}], total_risk}
    """
    log.info("Generating execution plan...")

    prompt = f"""You are Echo's code planner. Generate a safe, discrete execution plan.
Return ONLY valid JSON:
{{"task":"{objective}","total_risk":"low|medium|high","steps":[{{"id":"N","action":"str","command":"str or null","risk":"low|medium|high","reversible":true,"explanation":"str","verify":"command to verify success or null"}}]}}

Research brief: {json.dumps(research_brief, indent=2)}"""

    response = ollama(prompt, model=PLAN_MODEL)
    plan = None
    if response:
        try:
            import re as _re
            clean = _re.sub(r"```json\s*|```\s*","",response).strip()
            plan = json.loads(clean)
        except:
            pass
    if not plan or not plan.get("steps"):
        log.error(f"Plan generation failed: {str(response)[:100] if response else 'no response'}")
        return None

    log.info(f"Plan: {len(plan.get('steps',[]))} steps, risk: {plan.get('total_risk','?')}")
    return plan

# ── EXECUTE PHASE ─────────────────────────────────────────────────────

def execute_step(step):
    """
    Run a single step command. Returns {success, output, error}.
    """
    cmd = step.get("command")
    if not cmd:
        return {"success": True, "output": "(no command)", "error": None}

    log.info(f"  Exec [{step['id']}]: {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=120
        )
        output = (result.stdout + result.stderr).strip()
        success = result.returncode == 0
        return {"success": success, "output": output, "error": None, "rc": result.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Command timed out after 120s"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}

# ── ANALYZE PHASE ─────────────────────────────────────────────────────

def analyze_output(step, exec_result, objective):
    """
    Analyze execution result. Returns {status, learned, fix_command, done}.
    """
    if exec_result["success"]:
        return {
            "status": "success",
            "learned": [f"Step '{step['action']}' succeeded: {exec_result['output'][:200]}"],
            "fix_command": None,
            "done": True
        }

    prompt = f"""You are Echo's execution analyst. Analyze this failed step and suggest a fix.
Return ONLY valid JSON:
{{"status":"failed","root_cause":"str","fix_command":"str or null","fix_explanation":"str","learned":["str"],"skip_safe":true}}

Objective: {objective}
Step: {step['action']}
Command: {step.get('command','')}
Output: {exec_result.get('output','')[:500]}
Error: {exec_result.get('error','')}"""

    analysis = ollama_json(prompt, model=FAST_MODEL)
    if not analysis or analysis.get("raw"):
        return {
            "status": "failed",
            "learned": [f"Step failed: {exec_result.get('error') or exec_result.get('output','')[:100]}"],
            "fix_command": None,
            "done": False
        }

    return {
        "status": "failed",
        "learned": analysis.get("learned", []),
        "fix_command": analysis.get("fix_command"),
        "fix_explanation": analysis.get("fix_explanation", ""),
        "skip_safe": analysis.get("skip_safe", False),
        "done": False
    }

# ── DISTILL PHASE ─────────────────────────────────────────────────────

def distill_session(objective, steps_log):
    """Save session learnings to Subconscious/ for the watcher to pick up."""
    successes = [s for s in steps_log if s.get("status") == "success"]
    failures  = [s for s in steps_log if s.get("status") == "failed"]

    lines = [
        f"# Loop Session: {objective}",
        f"date: {datetime.now().isoformat(timespec='seconds')}",
        f"steps: {len(steps_log)} | successes: {len(successes)} | failures: {len(failures)}",
        "",
        "## What Worked"
    ]
    for s in successes:
        for l in s.get("learned", []):
            lines.append(f"- {l}")

    lines.append("\n## What Failed")
    for s in failures:
        for l in s.get("learned", []):
            lines.append(f"- {l}")

    content = "\n".join(lines)
    path = save_to_subconscious(f"loop-session-{re.sub(r'[^\\w]','-',objective[:30])}", content)
    log.info(f"Session distilled → {path.name} (watcher will pick up)")

# ── MAIN LOOP ─────────────────────────────────────────────────────────

def run_loop(objective, mode_override=None):
    mode = mode_override or get_mode()
    gate = Gate(mode)

    log.info(f"{'='*52}")
    log.info(f"Echo Research Loop")
    log.info(f"Objective : {objective}")
    log.info(f"Mode      : {mode.upper()}")
    log.info(f"{'='*52}")

    notify(f"Loop started ({mode}): {objective}", "info")

    # ── Phase 1: Research ──
    brief = research(objective)
    log.info(f"Brief: {brief.get('summary','')}")

    # ── Phase 2: Plan ──
    plan = generate_plan(objective, brief)
    if not plan:
        log.error("Could not generate plan. Aborting.")
        return

    steps = plan.get("steps", [])
    commands = [s["command"] for s in steps if s.get("command")]

    # ── Phase 3: Gate ──
    approved = gate.request(
        plan_summary=plan.get("task", objective),
        commands=commands,
        risk=plan.get("total_risk", "medium")
    )
    if not approved:
        log.info("Aborted at gate.")
        notify("Loop aborted at gate.", "warn")
        return

    # ── Phase 4-6: Execute → Analyze → Fix loop ──
    steps_log = []
    retry_count = 0

    for step in steps:
        log.info(f"\nStep {step['id']}: {step['action']}")
        log.info(f"  Command: {step.get('command','(none)')}")
        log.info(f"  Risk: {step.get('risk','?')} | Reversible: {step.get('reversible','?')}")

        attempt = 0
        while attempt <= MAX_RETRIES:
            exec_result = execute_step(step)
            analysis = analyze_output(step, exec_result, objective)
            steps_log.append({**analysis, "step": step["action"], "attempt": attempt})

            if analysis["status"] == "success":
                log.info(f"  ✓ Success")
                notify(f"Step '{step['action']}' succeeded", "success")
                break

            # Failed
            retry_count += 1
            log.warning(f"  ✗ Failed (attempt {attempt+1}/{MAX_RETRIES})")
            notify(f"Step '{step['action']}' failed: {analysis.get('fix_explanation','')}", "warn")

            if attempt >= MAX_RETRIES:
                log.error(f"  Max retries hit for step '{step['action']}'")
                if analysis.get("skip_safe"):
                    log.info("  Skipping (marked safe to skip)")
                else:
                    log.error("  Halting loop — unsafe to skip")
                    notify(f"Loop halted at step '{step['action']}' after {MAX_RETRIES} retries.", "error")
                    distill_session(objective, steps_log)
                    return
                break

            # Apply fix and retry
            fix_cmd = analysis.get("fix_command")
            if fix_cmd:
                log.info(f"  Applying fix: {fix_cmd}")

                # Gate on fix in manual mode
                if mode == "manual":
                    try:
                        ans = input(f"  Apply fix? [{fix_cmd}] [y/n] > ").strip().lower()
                        if ans not in ("y", "yes"):
                            log.info("  Fix rejected — skipping step")
                            break
                    except EOFError:
                        break

                fix_result = subprocess.run(
                    fix_cmd, shell=True, capture_output=True, text=True, timeout=60
                )
                log.info(f"  Fix output: {(fix_result.stdout+fix_result.stderr).strip()[:200]}")

                # Update step command to retry
                step = {**step, "command": step.get("command","")}

            attempt += 1

    # ── Phase 7: Distill ──
    distill_session(objective, steps_log)

    total = len(steps_log)
    successes = sum(1 for s in steps_log if s["status"] == "success")
    log.info(f"\n{'='*52}")
    log.info(f"Loop complete: {successes}/{total} steps succeeded")
    log.info(f"{'='*52}")
    notify(f"Loop complete: {successes}/{total} steps. Learnings saved to vault.", "success")

# ── STATUS ────────────────────────────────────────────────────────────

def status():
    mode = get_mode()
    mode_src = "file" if MODE_FILE.exists() else "auto-detected"
    kb_count = len(list(KB.glob("*.md"))) if KB.exists() else 0
    sub_count = len(list(SUBCONSCIOUS.glob("*.md"))) if SUBCONSCIOUS.exists() else 0
    log_exists = LOOP_LOG.exists()

    print(f"""
Echo Research Loop — Status
{'─'*40}
Mode        : {mode.upper()} ({mode_src})
KB entries  : {kb_count}
Subconscious: {sub_count} pending files
Loop log    : {LOOP_LOG if log_exists else '(not yet created)'}
Hermes hook : {'configured' if HERMES_WEBHOOK else 'not set (Discord notify disabled)'}
Ollama      : checking...
{'─'*40}""")

    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        print("Ollama      : running ✓")
    except:
        print("Ollama      : not running ✗")

# ── ENTRY POINT ───────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    if "--status" in args:
        status()
        sys.exit(0)

    if "--set-mode" in args:
        idx = args.index("--set-mode")
        if idx + 1 < len(args):
            set_mode(args[idx + 1])
            print(f"Mode saved: {args[idx+1]}")
        sys.exit(0)

    # Parse optional --mode override
    mode_override = None
    if "--mode" in args:
        idx = args.index("--mode")
        if idx + 1 < len(args):
            mode_override = args[idx + 1]
            args = [a for i, a in enumerate(args) if i not in (idx, idx+1)]

    # Remaining args = objective
    objective = " ".join(a for a in args if not a.startswith("--"))
    if not objective:
        print("Error: provide an objective")
        sys.exit(1)

    # Handle SIGTERM cleanly
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    run_loop(objective, mode_override=mode_override)

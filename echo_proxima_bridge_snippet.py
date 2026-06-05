# ─── ADD THIS TO vision_assistant.py ────────────────────────────────────────
# Drop this function anywhere in the file, then call it from your AI command
# handler or add a button to the Tkinter UI.

import requests as _prox_requests

PROXIMA_BRIDGE = "http://localhost:7799"

def run_proxima_plan(topic: str) -> str:
    """
    Send a topic to the Proxima planning engine and get Claude's final plan.
    Requires proxima_loop.py running with --server flag.

    Usage in your AI handler:
        if user_input.startswith("plan "):
            topic = user_input[5:]
            plan = run_proxima_plan(topic)
            speak(plan)
            return plan
    """
    try:
        r = _prox_requests.post(
            f"{PROXIMA_BRIDGE}/plan",
            json={"topic": topic},
            timeout=900  # planning takes ~5-10 min
        )
        return r.json().get("plan", "[No plan returned]")
    except _prox_requests.exceptions.ConnectionError:
        return "[Proxima bridge offline — start with: python3 proxima_loop.py --server]"
    except Exception as e:
        return f"[Bridge error: {e}]"


def proxima_status() -> dict:
    """Check which AI providers are up."""
    try:
        r = _prox_requests.get(f"{PROXIMA_BRIDGE}/status", timeout=5)
        return r.json()
    except Exception:
        return {"error": "bridge offline"}


# ─── EXAMPLE: Add to your wake-word / command handler ───────────────────────
# In your existing process_command() or handle_ai_response() function:
#
#   if "plan" in command or "design" in command or "architect" in command:
#       topic = command.replace("plan", "").replace("design", "").strip()
#       self.speak("Running multi-AI planning session. This will take a few minutes.")
#       plan = run_proxima_plan(topic)
#       self.add_to_notes(f"Plan: {topic}", plan)  # saves to Echo notes
#       self.speak("Planning complete. Saved to Obsidian.")
#       return plan

import os
import json
import subprocess
import datetime

# =========================
# ROUTER (EXECUTIVE FUNCTION)
# =========================
class EchoRouter:
    def __init__(self):
        self.fast_model = "phi4-mini"
        self.deep_model = "gemma3n-local"

    def classify(self, text):
        # lightweight deterministic fallback first (stability > AI guessing AI)
        if len(text) < 40:
            return "CHAT"
        if any(k in text.lower() for k in ["research", "find", "analyze"]):
            return "RESEARCH"
        if any(k in text.lower() for k in ["run", "execute", "delete", "install"]):
            return "ACTION"
        return "CHAT"

    def select_model(self, intent):
        if intent == "RESEARCH":
            return self.deep_model
        return self.fast_model


# =========================
# MEMORY (OBSIDIAN CONTRACT)
# =========================
class MemoryBridge:
    def __init__(self):
        self.base = os.path.expanduser("~/Documents/ObsidianVault/Echo")
        self.paths = {
            "CHAT": "Cognition",
            "RESEARCH": "Research",
            "ACTION": "Logs"
        }
        for p in self.paths.values():
            os.makedirs(os.path.join(self.base, p), exist_ok=True)

    def save(self, intent, content, model, router_note="EchoRouter"):
        folder = self.paths.get(intent, "Cognition")
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(self.base, folder, f"{ts}.md")

        yaml = f"""---
type: {intent}
model: {model}
router: {router_note}
timestamp: {datetime.datetime.now().isoformat()}
tags: [echo, {intent.lower()}]
---

"""

        body = f"# Echo Output\n\n{content}\n"

        with open(path, "w") as f:
            f.write(yaml + body)

        return path


# =========================
# EXECUTION CORE
# =========================
class EchoCore:
    def __init__(self):
        self.router = EchoRouter()
        self.memory = MemoryBridge()

    def run(self, user_input):
        intent = self.router.classify(user_input)
        model = self.router.select_model(intent)

        # model call
        try:
            result = subprocess.run(
                ["ollama", "run", model, user_input],
                capture_output=True
            ).stdout.decode()
        except Exception as e:
            result = f"[ERROR]: {str(e)}"

        # ALWAYS persist (this is the enforcement layer)
        path = self.memory.save(intent, result, model)

        return {
            "intent": intent,
            "model": model,
            "memory_path": path,
            "output": result
        }


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    echo = EchoCore()

    print("🧠 Echo Core Online. Type 'exit' to stop.\n")

    while True:
        user_input = input("> ")
        if user_input.lower() == "exit":
            break

        result = echo.run(user_input)

        print("\n---")
        print(f"Intent: {result['intent']}")
        print(f"Model: {result['model']}")
        print(f"Saved: {result['memory_path']}")
        print("Output:\n", result["output"])
        print("---\n")

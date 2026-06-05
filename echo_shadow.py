import time
import subprocess
import datetime
import os
import requests

# ===== CONFIG =====
SEARXNG_URL = "http://localhost:8081/search"
MODEL = "phi4-mini"
VAULT_PATH = os.path.expanduser("~/Documents/ObsidianVault/Echo/Research")
IDLE_TRIGGER = 600  # seconds

last_input_time = time.time()

# ===== MEMORY =====
def save_research(query, summary, sources):
    os.makedirs(VAULT_PATH, exist_ok=True)
    filename = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M") + ".md"
    path = os.path.join(VAULT_PATH, filename)

    content = f"""# Research: {query}

## Summary
{summary}

## Sources
{sources}

## Metadata
- created: {datetime.datetime.now()}
- type: research
"""

    with open(path, "w") as f:
        f.write(content)

    return path

# ===== SEARCH =====
def search(query):
    try:
        res = requests.get(SEARXNG_URL, params={
            "q": query,
            "format": "json"
        }, timeout=10)

        results = res.json().get("results", [])[:5]

        formatted = ""
        for r in results:
            formatted += f"{r.get('title')}\n{r.get('url')}\n\n"

        return formatted.strip()

    except Exception as e:
        return f"Search failed: {e}"

# ===== LLM =====
def summarize(text):
    prompt = f"""
Summarize this into useful insights:

{text}
"""
    try:
        result = subprocess.run(
            ["ollama", "run", MODEL],
            input=prompt.encode(),
            stdout=subprocess.PIPE
        )
        return result.stdout.decode()
    except Exception as e:
        return f"Summary failed: {e}"

# ===== VOICE =====
def speak(text):
    try:
        subprocess.run(["piper", "--text", text])
    except:
        print("[Echo Voice Fallback]:", text)

# ===== ROUTER =====
def route(text):
    text = text.lower()
    if "research" in text or "look into" in text:
        return "RESEARCH"
    return "UNKNOWN"

# ===== AGENT =====
def run_research(query):
    print(f"\n[Echo] Researching: {query}")

    sources = search(query)
    summary = summarize(sources)
    path = save_research(query, summary, sources)

    print(f"[Echo] Saved → {path}")
    speak("I've added something to your vault.")

# ===== CORE LOOP =====
def echo_loop():
    global last_input_time

    print("🌑 Echo Shadow Running...")

    while True:
        try:
            user_input = input("\n> ")

            if user_input.strip():
                last_input_time = time.time()
                intent = route(user_input)

                if intent == "RESEARCH":
                    run_research(user_input)
                else:
                    print("[Echo] ...listening.")

        except KeyboardInterrupt:
            print("\n[Echo] Shutting down.")
            break

        # ===== IDLE BEHAVIOR =====
        if time.time() - last_input_time > IDLE_TRIGGER:
            print("\n[Echo] Idle detected. Running background research...")
            run_research("latest developments in local AI systems")
            last_input_time = time.time()

# ===== START =====
if __name__ == "__main__":
    echo_loop()

#!/usr/bin/env python3
"""
echo_brainbridge.py — Parallel multi-AI query engine
Queries ChatGPT + Gemini + Perplexity simultaneously via Proxima Electron
Synthesizes into one answer via Ollama qwen3:4b
Usage: from echo_brainbridge import BrainBridge; bb = BrainBridge(); answer = await bb.ask("query")
Also runs as a REST server on :8768
"""
import asyncio, aiohttp, json, time, re
from flask import Flask, request, jsonify
import threading

PROXIMA_URL = "http://localhost:3211"
OLLAMA_URL  = "http://localhost:11434"

PROVIDERS = ["chatgpt", "gemini", "perplexity"]

SYNTH_SYSTEM = """You are Echo's synthesis engine. You receive responses from multiple AI providers about the same question.
Synthesize them into one clear, accurate, concise answer. Remove redundancy. Highlight where they disagree.
Be direct. No preamble. Response in 3-5 sentences max unless the question requires more."""

app = Flask(__name__)

class BrainBridge:
    def __init__(self):
        self.session = None

    async def _query_provider(self, session, provider, prompt):
        """Query a single provider via Proxima"""
        try:
            payload = {
                "provider": provider,
                "message": prompt,
                "think": False,
            }
            async with session.post(
                f"{PROXIMA_URL}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("response") or data.get("content") or data.get("text") or ""
                    # Strip think tags
                    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
                    return provider, text
                else:
                    return provider, None
        except Exception as e:
            print(f"[brainbridge] {provider} error: {e}")
            return provider, None

    async def _synthesize(self, question, responses):
        """Synthesize multiple responses via Ollama"""
        parts = []
        for provider, text in responses.items():
            if text:
                parts.append(f"[{provider.upper()}]: {text}")

        if not parts:
            return "No responses received from any provider."

        if len(parts) == 1:
            return list(responses.values())[0]

        combined = "\n\n".join(parts)
        prompt = f"Question: {question}\n\nProvider responses:\n{combined}\n\nSynthesize:"

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "qwen3:4b",
                    "prompt": prompt,
                    "system": SYNTH_SYSTEM,
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": 200, "temperature": 0.3},
                }
                async with session.post(
                    f"{OLLAMA_URL}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get("response", "").strip()
                        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
                        return text
        except Exception as e:
            print(f"[brainbridge] synthesis error: {e}")

        # Fallback: return best single response
        for p in ["perplexity", "chatgpt", "gemini"]:
            if responses.get(p):
                return responses[p]
        return "Synthesis failed."

    async def ask(self, question, providers=None):
        """Query all providers in parallel and synthesize"""
        providers = providers or PROVIDERS
        t0 = time.time()

        async with aiohttp.ClientSession() as session:
            tasks = [self._query_provider(session, p, question) for p in providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        responses = {}
        for result in results:
            if isinstance(result, tuple):
                provider, text = result
                if text:
                    responses[provider] = text

        print(f"[brainbridge] Got {len(responses)}/{len(providers)} responses in {time.time()-t0:.1f}s")

        synthesis = await self._synthesize(question, responses)

        return {
            "question": question,
            "synthesis": synthesis,
            "responses": responses,
            "providers_used": list(responses.keys()),
            "elapsed": round(time.time()-t0, 2),
        }

# Flask REST wrapper
bridge = BrainBridge()

@app.route("/ask", methods=["POST"])
def ask_endpoint():
    data = request.json or {}
    question = data.get("question") or data.get("message") or data.get("query", "")
    providers = data.get("providers", PROVIDERS)

    if not question:
        return jsonify({"error": "No question provided"}), 400

    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(bridge.ask(question, providers))
    loop.close()
    return jsonify(result)

@app.route("/ask/fast", methods=["POST"])
def ask_fast():
    """Single provider, no synthesis — fastest path"""
    data = request.json or {}
    question = data.get("question") or data.get("message", "")
    provider = data.get("provider", "chatgpt")

    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(bridge.ask(question, [provider]))
    loop.close()
    return jsonify({
        "question": question,
        "response": result["responses"].get(provider, ""),
        "provider": provider,
        "elapsed": result["elapsed"],
    })

@app.route("/")
def root():
    return jsonify({"status": "ready", "providers": PROVIDERS, "port": 8768})

if __name__ == "__main__":
    print("[brainbridge] Starting on :8768")
    print(f"[brainbridge] Providers: {PROVIDERS}")
    print(f"[brainbridge] Proxima: {PROXIMA_URL}")
    app.run(host="0.0.0.0", port=8768, debug=False)

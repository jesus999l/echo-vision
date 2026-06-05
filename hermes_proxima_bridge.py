"""
hermes_proxima_bridge.py
========================
Routes Discord (Hermes) messages through the Echo pipeline
instead of calling Claude directly.

BEFORE (broken flow):
  Discord → Hermes bot → Claude API directly

AFTER (fixed flow):
  Discord → Hermes bot → hermes_proxima_bridge → echo_browser_server :59996/pipeline
                                                → ChatGPT → Gemini → Perplexity → Claude

HOW TO USE:
  1. Drop this file in ~/vision_assistant/
  2. In your Hermes config.yaml, change the ai_backend to point here
  3. Or import and call ask_pipeline() from your Hermes message handler

CONFIG (hermes config.yaml):
  ai_backend: pipeline          # was: claude / openai
  pipeline_url: http://localhost:59996/pipeline
  pipeline_fallback: http://localhost:3210   # Proxima direct if pipeline down
"""

import asyncio
import aiohttp
import json
import logging
from typing import Optional

logger = logging.getLogger("echo.hermes_bridge")

# ── Config ────────────────────────────────────────────────────────────────────

PIPELINE_URL   = "http://localhost:59996/pipeline"
PROXIMA_URL    = "http://localhost:3210"          # fallback
GROUP_CHAT_URL = "http://localhost:8484"          # for broadcast mode
TIMEOUT        = 60  # seconds

# Map Discord channel names / prefixes to pipeline stages
CHANNEL_STAGE_MAP = {
    "general":    "chat",
    "research":   "research",
    "planning":   "plan",
    "warframe":   "chat",
    "brainstorm": "brainstorm",
    "discuss":    "discuss",
}

# ── Main ask function — drop-in for Hermes ────────────────────────────────────

async def ask_pipeline(
    message: str,
    channel: str = "general",
    author: str = "Discord",
    broadcast: bool = False,
) -> str:
    """
    Send a Discord message through the Echo pipeline.
    Returns the combined AI response as a string.

    Drop-in replacement for wherever Hermes currently calls Claude directly.
    """
    stage = CHANNEL_STAGE_MAP.get(channel.lower(), "chat")

    payload = {
        "message": message,
        "stage":   stage,
        "source":  f"discord:{author}",
        "channel": channel,
    }

    # Try pipeline first
    try:
        response = await _post(PIPELINE_URL, payload)
        if response:
            logger.info(f"[hermes→pipeline] {stage} response ({len(response)} chars)")
            return _format_for_discord(response, stage)
    except Exception as e:
        logger.warning(f"[hermes→pipeline] Pipeline failed: {e} — falling back to Proxima")

    # Fallback: Proxima direct
    try:
        proxima_payload = {"prompt": message, "model": "claude"}
        response = await _post(f"{PROXIMA_URL}/ask", proxima_payload)
        if response:
            return _format_for_discord(response, stage)
    except Exception as e:
        logger.error(f"[hermes→proxima] Fallback also failed: {e}")

    return "⚠️ Echo pipeline unavailable. Is echo_browser_server running?"


async def _post(url: str, payload: dict) -> Optional[str]:
    """POST to a pipeline endpoint, return response text."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                # Handle both {"response": "..."} and {"results": {...}} shapes
                if "response" in data:
                    return data["response"]
                elif "results" in data:
                    # Multi-AI results — combine them
                    parts = []
                    for provider, text in data["results"].items():
                        parts.append(f"**{provider.title()}:** {text}")
                    return "\n\n".join(parts)
                else:
                    return str(data)
            else:
                raise RuntimeError(f"HTTP {resp.status} from {url}")


def _format_for_discord(text: str, stage: str) -> str:
    """Format the pipeline response for Discord display."""
    # Stage label prefixes
    stage_labels = {
        "chat":       "",
        "research":   "🔍 **Research:**\n",
        "plan":       "📋 **Plan:**\n",
        "brainstorm": "💡 **Brainstorm:**\n",
        "discuss":    "💬 **Discussion:**\n",
    }
    prefix = stage_labels.get(stage, "")

    # Discord has 2000 char limit per message
    if len(text) > 1900:
        text = text[:1900] + "\n*[truncated — full response in vault]*"

    return prefix + text


# ── Hermes config.yaml patch helper ──────────────────────────────────────────

HERMES_CONFIG_PATCH = """
# Add/update these lines in ~/.hermes/config.yaml:
#
# ai:
#   backend: pipeline                          # was: claude or openai
#   pipeline_url: http://localhost:59996/pipeline
#   pipeline_fallback: http://localhost:3210   # Proxima direct
#   timeout: 60
#
# Then in your Hermes message handler, replace:
#   response = await claude.ask(message)
# With:
#   from hermes_proxima_bridge import ask_pipeline
#   response = await ask_pipeline(message, channel=ctx.channel.name, author=str(ctx.author))
"""

# ── Channel routing setup for Hermes ─────────────────────────────────────────

def get_stage_for_channel(channel_name: str) -> str:
    """Hermes calls this to pick the right pipeline stage per channel."""
    return CHANNEL_STAGE_MAP.get(channel_name.lower(), "chat")


# ── Standalone test ───────────────────────────────────────────────────────────

async def _test():
    logging.basicConfig(level=logging.INFO)
    print("Testing Hermes → Pipeline bridge...")
    print("(Make sure echo_browser_server.py is running on :59996)\n")

    response = await ask_pipeline(
        "What Warframe frame is best for farming Orokin Cells?",
        channel="warframe",
        author="TestUser",
    )
    print(f"Response:\n{response}")

if __name__ == "__main__":
    print(HERMES_CONFIG_PATCH)
    asyncio.run(_test())

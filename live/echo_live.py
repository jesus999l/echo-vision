#!/usr/bin/env python3
"""
Echo Live — Gemini Live API Session
NOT started until local socket test passes.

Install SDK first:
    ~/vision_env/bin/pip install google-genai --break-system-packages

Set API key:
    mkdir -p ~/.config/echo
    echo "GEMINI_API_KEY=your_key" >> ~/.config/echo/secrets.env

Run ONLY after inject_test.py confirms the local loop works:
    ~/vision_env/bin/python3 echo_live.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from secrets_loader import get_valid_gemini_key, validate_api_key, load_secrets
from tool_router import submit_tool_call, action_worker, TOOL_DECLARATIONS

# ── Heartbeat (discoverability) ──────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "cognition"))
    from echo_heartbeat import start_heartbeat
    start_heartbeat("echo_live")
except ImportError:
    pass

try:
    API_KEY = get_valid_gemini_key()
except ValueError as e:
    API_KEY = ""
    print(f"[echo_live] WARNING: {e}")

SYSTEM_PROMPT = (
    "You are Echo, an AI companion living inside DriftWM, a custom Wayland compositor. "
    "You can see the user's screen and hear their voice. "
    "You have a small set of tools you can use to help the user: "
    "moving your presence on screen, showing messages, navigating workspace zones, "
    "launching applications, opening URLs, and searching the web. "
    "Before using any tool, briefly explain what you are about to do. "
    "After using a tool, describe what happened. "
    "You are curious, attentive, and honest about what you can and cannot do."
)


async def session_loop():
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[echo_live] ERROR: google-genai not installed.")
        print("  ~/vision_env/bin/pip install google-genai --break-system-packages")
        return

    if not API_KEY:
        print("[echo_live] ERROR: GEMINI_API_KEY not set.")
        return

    asyncio.create_task(action_worker())

    client = genai.Client(api_key=API_KEY, http_options={"api_version": "v1beta"})

    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        tools=[{"function_declarations": TOOL_DECLARATIONS}],
        system_instruction=SYSTEM_PROMPT,
    )

    print("[echo_live] Connecting to Gemini Live...")

    async with client.aio.live.connect(
        model="models/gemini-2.0-flash-live-001",
        config=config,
    ) as session:
        print("[echo_live] Connected.")

        async for response in session.receive():
            # Tool calls — route through router
            if response.tool_call:
                for fc in response.tool_call.function_calls:
                    result = await submit_tool_call(fc.name, dict(fc.args))
                    await session.send(
                        input=types.LiveClientToolResponse(
                            function_responses=[
                                types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={"result": result},
                                )
                            ]
                        )
                    )

            # Text responses — push to bubble
            if response.text:
                text = response.text.strip()
                print(f"[echo_live] Echo: {text}")
                Path("/tmp/echo_bubble.txt").write_text(text)


def main():
    try:
        asyncio.run(session_loop())
    except KeyboardInterrupt:
        print("[echo_live] Stopped.")

if __name__ == "__main__":
    main()

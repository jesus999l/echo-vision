#!/usr/bin/env python3
"""
Echo Live — Unix Socket Server
Receives tool call JSON over /tmp/echo_live.sock and dispatches via tool_router.
This replaces the Gemini websocket for local testing.

Usage:
  Terminal 1: ~/vision_env/bin/python3 live_socket.py
  Terminal 2: ~/vision_env/bin/python3 inject_test.py
           or: echo '{"tool":"show_notification","args":{"message":"test"}}' | nc -U /tmp/echo_live.sock
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tool_router import submit_tool_call, action_worker, SOCKET_PATH

async def handle_client(reader, writer):
    data = await reader.read(4096)
    try:
        msg    = json.loads(data.decode())
        tool   = msg.get("tool", "")
        args   = msg.get("args", {})
        result = await submit_tool_call(tool, args)
        writer.write(json.dumps(result).encode())
        await writer.drain()
        print(f"[live_socket] {tool} → {result}")
    except Exception as e:
        writer.write(json.dumps({"ok": False, "error": str(e)}).encode())
        await writer.drain()
    finally:
        writer.close()

async def main():
    sock = Path(SOCKET_PATH)
    if sock.exists():
        os.unlink(sock)

    # Start action worker
    asyncio.create_task(action_worker())

    server = await asyncio.start_unix_server(handle_client, path=SOCKET_PATH)
    print(f"[live_socket] Listening on {SOCKET_PATH}")
    print("Inject: python3 inject_test.py")
    print("     or: echo '{"+"tool":"show_notification","args":{"message":"hi"}}' | nc -U /tmp/echo_live.sock")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())

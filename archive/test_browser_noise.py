"""
test_browser_noise.py — Echo v1 Browser Noise Simulator
=========================================================
Simulates real Firefox browsing patterns against the live bridge.
Run this BEFORE connecting your actual browser extension.

Measures:
  - acceptance rate under normal load
  - dedup effectiveness (duplicate URL/payload detection)
  - priority filtering under queue pressure
  - queue state after 60 seconds of simulated browsing

Usage:
  Terminal 1:  python3 echo_browser_bridge.py
  Terminal 2:  python3 test_browser_noise.py

Scenarios:
  1. Clean signal   — meaningful article text, tab changes
  2. Refresh storm  — same URL sent 20 times
  3. Scroll spam    — 50 rapid scroll events
  4. Mixed session  — realistic 1-minute browsing simulation
"""

import asyncio
import json
import time
import random
from datetime import datetime

import websockets

BRIDGE_URL = "ws://127.0.0.1:8765/ws"
STATUS_URL = "http://127.0.0.1:8765/status"
TAIL_URL   = "http://127.0.0.1:8765/tail"

# =========================================================
# SAMPLE DATA
# =========================================================

REAL_URLS = [
    "https://en.wikipedia.org/wiki/Deterministic_finite_automaton",
    "https://docs.python.org/3/library/sqlite3.html",
    "https://fastapi.tiangolo.com/tutorial/websockets/",
    "https://wiki.archlinux.org/title/Systemd",
    "https://github.com/chroma-core/chroma",
]

REAL_TITLES = [
    "Deterministic finite automaton - Wikipedia",
    "sqlite3 — DB-API 2.0 interface — Python 3 docs",
    "WebSockets - FastAPI",
    "systemd - ArchWiki",
    "chroma-core/chroma: the AI-native open-source embedding database",
]

REAL_SELECTIONS = [
    "A deterministic finite automaton is a finite-state machine that accepts or rejects a given string of symbols by running through a state sequence uniquely determined by the string.",
    "Connection objects can be used as context managers that automatically commit or rollback transactions.",
    "WebSockets allow a two-way interactive communication session between the user's browser and a server.",
    "systemd is a suite of basic building blocks for a Linux system.",
]


def make_tab_change(url: str, title: str) -> dict:
    return {
        "type": "tab_change",
        "data": {"url": url, "title": title, "timestamp": datetime.now().isoformat()},
    }

def make_page_load(url: str, title: str) -> dict:
    return {
        "type": "page_load",
        "data": {"url": url, "title": title, "readyState": "complete"},
    }

def make_text_selection(text: str, url: str) -> dict:
    return {
        "type": "text_selection",
        "data": {"text": text, "url": url, "length": len(text)},
    }

def make_scroll(url: str, depth: float) -> dict:
    return {
        "type": "scroll",
        "data": {"url": url, "scroll_depth": depth},
    }


# =========================================================
# SCENARIOS
# =========================================================

async def scenario_clean_signal(ws) -> dict:
    """Meaningful browsing: tab changes + article reads + text selections."""
    sent = accepted = rejected = 0

    for url, title in zip(REAL_URLS, REAL_TITLES):
        for event in [make_tab_change(url, title), make_page_load(url, title)]:
            await ws.send(json.dumps(event))
            resp = json.loads(await ws.recv())
            sent += 1
            if resp["status"] == "accepted":
                accepted += 1
            else:
                rejected += 1
            await asyncio.sleep(0.05)

        # Simulate reading: one text selection per article
        text = random.choice(REAL_SELECTIONS)
        await ws.send(json.dumps(make_text_selection(text, url)))
        resp = json.loads(await ws.recv())
        sent += 1
        if resp["status"] == "accepted":
            accepted += 1
        else:
            rejected += 1

    return {"scenario": "clean_signal", "sent": sent, "accepted": accepted, "rejected": rejected}


async def scenario_refresh_storm(ws) -> dict:
    """Same URL sent 20 times — simulates frantic refresh or redirect loop."""
    url   = REAL_URLS[0]
    title = REAL_TITLES[0]
    sent = accepted = rejected = 0

    for _ in range(20):
        event = make_tab_change(url, title)
        await ws.send(json.dumps(event))
        resp = json.loads(await ws.recv())
        sent += 1
        if resp["status"] == "accepted":
            accepted += 1
        else:
            rejected += 1
        await asyncio.sleep(0.02)

    return {"scenario": "refresh_storm", "sent": sent, "accepted": accepted, "rejected": rejected}


async def scenario_scroll_spam(ws) -> dict:
    """50 rapid scroll events — pure noise."""
    url  = REAL_URLS[2]
    sent = accepted = rejected = 0

    for i in range(50):
        depth = round(i / 50, 2)
        event = make_scroll(url, depth)
        await ws.send(json.dumps(event))
        resp = json.loads(await ws.recv())
        sent += 1
        if resp["status"] == "accepted":
            accepted += 1
        else:
            rejected += 1
        await asyncio.sleep(0.01)

    return {"scenario": "scroll_spam", "sent": sent, "accepted": accepted, "rejected": rejected}


async def scenario_mixed_session(ws) -> dict:
    """
    Realistic 1-minute browsing simulation.
    Interleaves meaningful events with noise at realistic cadence.
    """
    sent = accepted = rejected = 0
    start = time.time()
    duration = 10  # 10 seconds compressed simulation

    events_pool = (
        [make_tab_change(u, t) for u, t in zip(REAL_URLS, REAL_TITLES)] * 3
        + [make_text_selection(s, REAL_URLS[i % len(REAL_URLS)]) for i, s in enumerate(REAL_SELECTIONS)] * 2
        + [make_scroll(REAL_URLS[i % len(REAL_URLS)], random.random()) for i in range(20)]
        + [make_page_load(u, t) for u, t in zip(REAL_URLS[:3], REAL_TITLES[:3])]
    )
    random.shuffle(events_pool)

    for event in events_pool:
        if time.time() - start > duration:
            break
        await ws.send(json.dumps(event))
        resp = json.loads(await ws.recv())
        sent += 1
        if resp["status"] == "accepted":
            accepted += 1
        else:
            rejected += 1
        await asyncio.sleep(random.uniform(0.05, 0.2))

    return {"scenario": "mixed_session", "sent": sent, "accepted": accepted, "rejected": rejected}


# =========================================================
# RUNNER
# =========================================================

async def fetch_status() -> dict:
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(STATUS_URL)
        return resp.json()


async def fetch_tail() -> dict:
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(TAIL_URL)
        return resp.json()


async def run():
    print("\n" + "=" * 60)
    print("  Echo v1 — Browser Noise Simulator")
    print("=" * 60)
    print(f"  Target: {BRIDGE_URL}")
    print(f"  Start:  {datetime.now().isoformat()}\n")

    results = []

    try:
        async with websockets.connect(BRIDGE_URL) as ws:

            print("✅ Connected to bridge.\n")

            for name, coro in [
                ("Clean Signal",   scenario_clean_signal(ws)),
                ("Refresh Storm",  scenario_refresh_storm(ws)),
                ("Scroll Spam",    scenario_scroll_spam(ws)),
                ("Mixed Session",  scenario_mixed_session(ws)),
            ]:
                print(f"▶  Running: {name}...")
                result = await coro
                pct = round(result["accepted"] / max(result["sent"], 1) * 100, 1)
                print(f"   Sent={result['sent']}  "
                      f"Accepted={result['accepted']}  "
                      f"Rejected={result['rejected']}  "
                      f"Accept rate={pct}%")
                results.append(result)
                await asyncio.sleep(0.5)

    except ConnectionRefusedError:
        print("❌ Bridge not running.")
        print("   Start it first:")
        print("   python3 echo_browser_bridge.py")
        return

    # Final queue state
    print()
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            status = (await client.get(STATUS_URL)).json()
            tail   = (await client.get(TAIL_URL)).json()

        print("── Queue Status ────────────────────────────────────")
        print(f"   Counts  : {status['counts']}")
        print(f"   Backlog : {status['backlog']} pending")
        print(f"   Pressure: {status['pressure']}")

        print("\n── Last 5 Events ───────────────────────────────────")
        for ev in tail["events"][:5]:
            print(f"   [{ev['triage_state']:10}] p={ev['priority']} "
                  f"{ev['event_type']:16} fp={ev['fingerprint'][:12]}...")

    except Exception as e:
        print(f"   (Could not fetch status: {e})")

    # Summary
    total_sent     = sum(r["sent"]     for r in results)
    total_accepted = sum(r["accepted"] for r in results)
    total_rejected = sum(r["rejected"] for r in results)
    overall_rate   = round(total_accepted / max(total_sent, 1) * 100, 1)

    print("\n── Summary ─────────────────────────────────────────")
    print(f"   Total sent     : {total_sent}")
    print(f"   Total accepted : {total_accepted}")
    print(f"   Total rejected : {total_rejected}")
    print(f"   Overall accept : {overall_rate}%")

    print()
    print("  Interpretation:")
    if overall_rate > 80:
        print("  ⚠️  Rate too high — triage worker will be overwhelmed.")
        print("     Increase fingerprint aggressiveness or add source-side filtering.")
    elif overall_rate < 20:
        print("  ⚠️  Rate too low — may be discarding real signal.")
        print("     Check priority thresholds in infer_priority().")
    else:
        print("  ✅ Accept rate looks healthy for triage worker throughput.")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run())

#!/usr/bin/env python3
"""
Echo Capability Map
Reads capabilities.json and produces a human-readable self-description.
Echo can call this to explain what she can and cannot do.

Usage:
  from cognition.capability_map import describe_capabilities
  text = describe_capabilities()
  # → "VISION\n ✓ read screen\n ✗ click without approval\n..."
"""

import json
from pathlib import Path

CAPS_FILE = Path(__file__).parent.parent / "live" / "capabilities.json"

# How each tool maps to a capability category
CATEGORY_MAP = {
    "CURSOR": ["move_shadow_cursor"],
    "NAVIGATION": ["navigate_zone"],
    "COMMUNICATION": ["show_notification"],
    "BROWSER": ["open_url", "search_web"],
    "SYSTEM": ["launch_application", "focus_window", "close_window"],
    "KERNEL": ["run_shell", "write_file"],
}


def describe_capabilities() -> str:
    try:
        caps = json.loads(CAPS_FILE.read_text())
    except Exception:
        return "Capability map unavailable."

    lines = ["ECHO CAPABILITY MAP", ""]

    for category, tools in CATEGORY_MAP.items():
        lines.append(category)
        for tool in tools:
            cap = caps.get(tool, {})
            enabled  = cap.get("enabled", False)
            confirm  = cap.get("requires_confirmation", True)
            desc     = cap.get("description", tool)
            mark     = "✓" if enabled else "✗"
            note     = " (needs confirmation)" if enabled and confirm else ""
            lines.append(f"  {mark} {desc}{note}")
        lines.append("")

    return "\n".join(lines).strip()


def describe_as_speech() -> str:
    """First-person version for Echo's speech bubble."""
    try:
        caps = json.loads(CAPS_FILE.read_text())
    except Exception:
        return "I can't read my capability map right now."

    enabled  = [c["description"] for c in caps.values() if c.get("enabled")]
    disabled = [c["description"] for c in caps.values() if not c.get("enabled")]

    parts = []
    if enabled:
        parts.append("I can: " + ", ".join(enabled[:4]) +
                     ("..." if len(enabled) > 4 else "."))
    if disabled:
        parts.append("I cannot yet: " + ", ".join(disabled[:3]) +
                     ("..." if len(disabled) > 3 else "."))
    return " ".join(parts)


if __name__ == "__main__":
    print(describe_capabilities())
    print()
    print("Speech version:")
    print(describe_as_speech())

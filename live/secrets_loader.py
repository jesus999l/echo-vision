#!/usr/bin/env python3
"""
Echo Live — Secrets Loader
Validates GEMINI_API_KEY on startup. Rejects if missing, too short, or placeholder.
"""

import os
import sys
from pathlib import Path

SECRETS_FILE = Path.home() / ".config" / "echo" / "secrets.env"

PLACEHOLDER_STRINGS = [
    "your_key",
    "your_api_key",
    "paste",
    "placeholder",
    "changeme",
    "xxxx",
]


def load_secrets() -> str:
    """Load GEMINI_API_KEY into os.environ if present in ~/.config/echo/secrets.env."""
    if SECRETS_FILE.exists() and not os.environ.get("GEMINI_API_KEY"):
        try:
            for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["GEMINI_API_KEY"] = val
                    break
        except Exception:
            pass
    return os.environ.get("GEMINI_API_KEY", "")


def validate_api_key(key: str) -> tuple[bool, str]:
    """
    Validates GEMINI_API_KEY.
    Returns (is_valid, error_message).
    """
    if not key:
        return False, "GEMINI_API_KEY is missing."

    if len(key) < 20:
        return False, f"GEMINI_API_KEY is too short ({len(key)} chars)."

    key_lower = key.lower()
    for placeholder in PLACEHOLDER_STRINGS:
        if placeholder in key_lower:
            return False, f"GEMINI_API_KEY contains placeholder string ('{placeholder}')."

    return True, ""


def get_valid_gemini_key() -> str:
    """
    Loads secrets and validates GEMINI_API_KEY on startup.
    Raises ValueError if invalid.
    """
    key = load_secrets()
    is_valid, err = validate_api_key(key)
    if not is_valid:
        raise ValueError(f"Invalid GEMINI_API_KEY: {err}")
    return key


if __name__ == "__main__":
    try:
        k = get_valid_gemini_key()
        print(f"[secrets_loader] Valid GEMINI_API_KEY found ({len(k)} chars).")
    except ValueError as e:
        print(f"[secrets_loader] REJECTED: {e}")
        sys.exit(1)

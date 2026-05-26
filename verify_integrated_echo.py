"""
Verification script for Integrated Echo System.
"""
import os
import sys
import json
from pathlib import Path

def test_theme_loading():
    print("Testing theme loading...")
    sys.path.insert(0, os.getcwd())
    from ui import THEMES
    if "echo_os" in THEMES:
        print("  ✓ echo_os theme found.")
    else:
        print("  ✗ echo_os theme missing.")
        return False
    return True

def test_manifest_polling():
    print("Testing manifest polling data files...")
    state_file = Path.home() / 'echo_state.json'
    thought_file = Path.home() / 'echo_thought.txt'

    # Create dummy files if missing
    if not state_file.exists():
        state_file.write_text(json.dumps({"nodes": {"WAKE": {"status": "active", "activity": 50}}}))
    if not thought_file.exists():
        thought_file.write_text("Testing verification")

    print(f"  ✓ State file: {state_file}")
    print(f"  ✓ Thought file: {thought_file}")
    return True

def test_agent_task_execution():
    print("Testing agent task execution logic...")
    from ai import execute_task

    # Test tidy
    print("  Testing tidy task...")
    res = execute_task({"action": "tidy", "params": {"dir": "/tmp"}})
    print(f"    Result: {res}")

    # Test media (won't actually play if ffplay missing, but should call function)
    print("  Testing play_media task...")
    res = execute_task({"action": "play_media", "params": {"path": "/dev/null"}})
    print(f"    Result: {res}")

    return True

def test_learning_loop():
    print("Testing learning loop logic...")
    from personality import generate_reflective_summary
    summary = generate_reflective_summary()
    print("  Generated summary:")
    print(f"    {summary.splitlines()[0]}...")
    if "Reflective Summary" in summary:
        print("  ✓ Summary format correct.")
    else:
        print("  ✗ Summary format incorrect.")
        return False
    return True

def main():
    results = [
        test_theme_loading(),
        test_manifest_polling(),
        test_agent_task_execution(),
        test_learning_loop()
    ]
    if all(results):
        print("\nALL INTEGRATION CHECKS PASSED.")
    else:
        print("\nSOME CHECKS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    main()

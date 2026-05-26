"""
hyperspace_bridge.py — Echo ↔ Hyperspace (aios-cli) Bridge
==========================================================
Usage:
    bridge = HyperspaceBridge()
    bridge.index_file("note.md")
    results = bridge.search("query")

Acceptance criteria:
- Code runs inside vision_env (Python 3.11, Linux Mint 22.3)
- No new heavy dependencies
- Thread-safe for Tkinter integration
"""

import subprocess
import threading
import logging
import shutil
import os

logger = logging.getLogger("echo.hyperspace")

class HyperspaceBridge:
    def __init__(self, binary_path="hyperspace"):
        self.binary = binary_path
        self._lock = threading.Lock()
        self._available = shutil.which(self.binary) is not None
        if not self._available:
            logger.warning(f"Hyperspace binary '{self.binary}' not found in PATH.")

    def is_available(self):
        return self._available

    def get_status(self):
        """Returns the output of 'hyperspace status'."""
        if not self._available:
            return "Hyperspace not installed"
        try:
            res = subprocess.run([self.binary, "status"], capture_output=True, text=True, timeout=5)
            return res.stdout.strip()
        except Exception as e:
            return f"Error getting status: {e}"

    def index_file(self, filepath):
        """Indexes a file using 'hyperspace index <filepath>'."""
        if not self._available:
            return False
        if not os.path.exists(filepath):
            logger.error(f"File not found for indexing: {filepath}")
            return False

        def _run():
            with self._lock:
                try:
                    logger.info(f"Hyperspace: indexing {filepath}")
                    subprocess.run([self.binary, "index", filepath], check=True, capture_output=True, timeout=30)
                    return True
                except subprocess.CalledProcessError as e:
                    logger.error(f"Hyperspace index failed: {e.stderr}")
                    return False
                except Exception as e:
                    logger.error(f"Hyperspace index error: {e}")
                    return False

        # Run in thread to not block UI
        threading.Thread(target=_run, daemon=True).start()
        return True

    def search(self, query, limit=5):
        """Searches using 'hyperspace search <query>'."""
        if not self._available or not query:
            return ""

        with self._lock:
            try:
                # Assuming 'search' command exists and returns text
                res = subprocess.run([self.binary, "search", query, "--limit", str(limit)],
                                     capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    return res.stdout.strip()
                else:
                    logger.error(f"Hyperspace search failed: {res.stderr}")
                    return ""
            except Exception as e:
                logger.error(f"Hyperspace search error: {e}")
                return ""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = HyperspaceBridge()
    print(f"Available: {bridge.is_available()}")
    if bridge.is_available():
        print(f"Status: {bridge.get_status()}")

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure current dir is in path
sys.path.insert(0, os.getcwd())

from hyperspace_bridge import HyperspaceBridge
import ai

class TestHyperspaceIntegration(unittest.TestCase):
    @patch("shutil.which")
    def test_bridge_availability(self, mock_which):
        mock_which.return_value = "/usr/bin/hyperspace"
        bridge = HyperspaceBridge()
        self.assertTrue(bridge.is_available())

        mock_which.return_value = None
        bridge = HyperspaceBridge()
        self.assertFalse(bridge.is_available())

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_bridge_status(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/hyperspace"
        mock_run.return_value.stdout = "Status: RUNNING"
        bridge = HyperspaceBridge()
        self.assertEqual(bridge.get_status(), "Status: RUNNING")

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_bridge_search(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/hyperspace"
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Search result context"
        bridge = HyperspaceBridge()
        self.assertEqual(bridge.search("test query"), "Search result context")

    @patch("ai.get_recent_messages")
    def test_ai_integration_context_block(self, mock_recent):
        mock_bridge = MagicMock()
        mock_bridge.is_available.return_value = True
        mock_bridge.search.return_value = "Mocked Hyperspace results"

        ai.set_hyperspace_bridge(mock_bridge)
        mock_recent.return_value = [{"role": "user", "content": "hello"}]

        ctx = ai._hyperspace_context_block()
        self.assertIn("HYPERSPACE AGENT NETWORK CONTEXT", ctx)
        self.assertIn("Mocked Hyperspace results", ctx)
        mock_bridge.search.assert_called_with("hello")

if __name__ == "__main__":
    unittest.main()

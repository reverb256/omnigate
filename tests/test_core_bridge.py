"""Tests for core_bridge.py — Rust core bridge."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestCoreBridge(unittest.TestCase):
    def test_can_import_core_bridge(self):
        import core_bridge  # noqa: F401

    def test_core_bridge_has_hash_files_fn(self):
        from core_bridge import hash_files
        self.assertTrue(callable(hash_files))


if __name__ == "__main__":
    unittest.main()

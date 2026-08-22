"""Tests for sync.py — differential sync."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestSyncFunctions(unittest.TestCase):
    def test_can_import_sync(self):
        import sync  # noqa: F401

    def test_sync_has_plan_changes_fn(self):
        from sync import plan_changes
        self.assertTrue(callable(plan_changes))

    def test_sync_has_reflink_supported_fn(self):
        from sync import _reflink_supported
        self.assertTrue(callable(_reflink_supported))


if __name__ == "__main__":
    unittest.main()

"""Tests for restore.py — restore from backup."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestRestoreFunctions(unittest.TestCase):
    def test_can_import_restore(self):
        import restore  # noqa: F401

    def test_restore_has_build_restore_script_fn(self):
        from restore import build_restore_script
        self.assertTrue(callable(build_restore_script))


if __name__ == "__main__":
    unittest.main()

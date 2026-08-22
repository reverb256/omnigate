"""Tests for firstboot.py — post-migration welcome."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestFirstboot(unittest.TestCase):
    def test_can_import_firstboot(self):
        import firstboot  # noqa: F401

    def test_firstboot_has_show_fn(self):
        from firstboot import show
        self.assertTrue(callable(show))


if __name__ == "__main__":
    unittest.main()

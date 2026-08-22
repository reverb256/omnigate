"""Tests for steam.py — Steam user-data layer."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestSteam(unittest.TestCase):
    def test_can_import_steam(self):
        import steam  # noqa: F401

    def test_steam_has_find_steam_root_fn(self):
        from steam import find_steam_root
        self.assertTrue(callable(find_steam_root))


if __name__ == "__main__":
    unittest.main()

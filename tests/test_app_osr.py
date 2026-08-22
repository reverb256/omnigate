"""Tests for app.py OSR screen."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestOSRScreen(unittest.TestCase):
    def test_can_import_app(self):
        import app  # noqa: F401

    def test_app_has_build_osr_screen(self):
        from app import build_osr_screen
        self.assertTrue(callable(build_osr_screen))


if __name__ == "__main__":
    unittest.main()

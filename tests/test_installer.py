"""Tests for installer.py — install flow."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestInstaller(unittest.TestCase):
    def test_can_import_installer(self):
        import installer  # noqa: F401

    def test_installer_has_main_fn(self):
        from installer import main
        self.assertTrue(callable(main))

    def test_installer_has_suggest_fn(self):
        from installer import _suggest_safe
        self.assertTrue(callable(_suggest_safe))


if __name__ == "__main__":
    unittest.main()

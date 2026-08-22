"""Tests for omniport.py — Git-based migration workflow."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestOmniport(unittest.TestCase):
    def test_can_import_omniport(self):
        import omniport  # noqa: F401

    def test_omniport_has_main_fn(self):
        from omniport import main
        self.assertTrue(callable(main))

    def test_omniport_has_git_run_fn(self):
        from omniport import git_run
        self.assertTrue(callable(git_run))


if __name__ == "__main__":
    unittest.main()

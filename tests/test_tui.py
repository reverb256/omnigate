"""Tests for tui.py — terminal UI."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestTUI(unittest.TestCase):
    def test_can_import_tui(self):
        import tui  # noqa: F401

    def test_tui_has_render_picker_fn(self):
        from tui import render_picker
        self.assertTrue(callable(render_picker))


if __name__ == "__main__":
    unittest.main()

"""Tests for paradigm.py — new paradigm ceremony."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestParadigm(unittest.TestCase):
    def test_can_import_paradigm(self):
        import paradigm  # noqa: F401

    def test_paradigm_has_render_fn(self):
        from paradigm import render
        self.assertTrue(callable(render))


if __name__ == "__main__":
    unittest.main()

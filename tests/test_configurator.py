"""Tests for configurator.py — Omarchy-style configurator."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestConfigurator(unittest.TestCase):
    def test_can_import_configurator(self):
        import configurator  # noqa: F401

    def test_configurator_has_step_fn(self):
        from configurator import step
        self.assertTrue(callable(step))


if __name__ == "__main__":
    unittest.main()

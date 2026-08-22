"""Tests for mapper/compat.py — compat gate."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestCompatGate(unittest.TestCase):
    def test_can_import_compat(self):
        from mapper import compat  # noqa: F401

    def test_compat_has_gate_fn(self):
        from mapper.compat import gate
        self.assertTrue(callable(gate))


if __name__ == "__main__":
    unittest.main()

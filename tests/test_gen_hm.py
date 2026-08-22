"""Tests for generator/gen_hm.py — Home Manager profile generator."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestGenHM(unittest.TestCase):
    def test_can_import_gen_hm(self):
        from generator import gen_hm  # noqa: F401

    def test_gen_hm_has_gen_fn(self):
        from generator.gen_hm import gen
        self.assertTrue(callable(gen))


if __name__ == "__main__":
    unittest.main()

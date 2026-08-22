"""Tests for plan.py — transformation planner."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestPlan(unittest.TestCase):
    def test_can_import_plan(self):
        import plan  # noqa: F401

    def test_plan_has_generate_plan_fn(self):
        from plan import generate_plan
        self.assertTrue(callable(generate_plan))


if __name__ == "__main__":
    unittest.main()

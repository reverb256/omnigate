"""Tests for orchestrate.py — cluster orchestration."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestOrchestrate(unittest.TestCase):
    def test_can_import_orchestrate(self):
        import orchestrate  # noqa: F401

    def test_orchestrate_has_build_cluster_plan_fn(self):
        from orchestrate import build_cluster_plan
        self.assertTrue(callable(build_cluster_plan))

    def test_cluster_plan_has_stages(self):
        from orchestrate import build_cluster_plan
        plan = build_cluster_plan()
        self.assertIn("stages", plan)
        self.assertGreater(len(plan["stages"]), 0)

    def test_cluster_has_all_hosts(self):
        from orchestrate import CLUSTER
        for host in ["zephyr", "nexus", "forge", "sentry"]:
            self.assertIn(host, CLUSTER)


if __name__ == "__main__":
    unittest.main()

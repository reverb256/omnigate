"""Tests for mapper/port_configs.py — config porting."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestPortConfigs(unittest.TestCase):
    def test_can_import_port_configs(self):
        from mapper import port_configs  # noqa: F401

    def test_port_configs_has_port_fn(self):
        from mapper.port_configs import port
        self.assertTrue(callable(port))


if __name__ == "__main__":
    unittest.main()

"""Tests for audit.py — Stage-0 OS detection + storage discovery."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from audit import detect_source_os  # noqa: E402


class TestDetectSourceOS(unittest.TestCase):
    def test_local_is_nixos(self):
        result = detect_source_os(None)
        # zephyr is NixOS
        self.assertEqual(result, "nixos")

    def test_returns_known_values(self):
        result = detect_source_os(None)
        self.assertIn(result, ["linux", "nixos", "macos", "windows", "unknown"])


class TestAuditImportable(unittest.TestCase):
    def test_can_import_audit(self):
        import audit  # noqa: F401

    def test_full_scan_signature(self):
        from audit import full_scan
        import inspect
        params = inspect.signature(full_scan).parameters
        self.assertIn("target", params)


if __name__ == "__main__":
    unittest.main()

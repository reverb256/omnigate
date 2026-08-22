"""Tests for manifest.py — machine manifest."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestManifestFunctions(unittest.TestCase):
    def test_can_import_manifest(self):
        import manifest  # noqa: F401

    def test_manifest_has_build_fn(self):
        from manifest import build_manifest
        self.assertTrue(callable(build_manifest))


if __name__ == "__main__":
    unittest.main()

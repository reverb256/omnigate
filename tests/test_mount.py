"""Tests for mount.py — union-mount."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestMountFunctions(unittest.TestCase):
    def test_can_import_mount(self):
        import mount  # noqa: F401

    def test_mount_has_ghost_fn(self):
        from mount import cmd_ghost
        self.assertTrue(callable(cmd_ghost))

    def test_mount_has_mount_fn(self):
        from mount import cmd_mount
        self.assertTrue(callable(cmd_mount))

    def test_mount_has_unmount_fn(self):
        from mount import cmd_unmount
        self.assertTrue(callable(cmd_unmount))


if __name__ == "__main__":
    unittest.main()

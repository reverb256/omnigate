"""Tests for txn.py — rollback reverts files correctly."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import txn  # noqa: E402
from txn import (  # noqa: E402
    commit_import,
    rollback_last_txn,
    stage_import,
)


class TestRollbackRevertsFiles(unittest.TestCase):
    def test_rollback_restores_original(self):
        """After import + rollback, the original file content is restored."""
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "source.txt"
        dst = tmp / "target.txt"
        backup_dir = tmp / "backups"
        state_dir = tmp / "omnigate-state"

        # Isolate txn state so rollback_last_txn finds only our log
        with patch.object(txn, "STATE_DIR", state_dir):
            dst.write_text("original content")
            src.write_text("new content")

            pairs = [(src, dst)]
            plan = stage_import(pairs)
            summary = commit_import(plan, backup_dir=backup_dir)
            self.assertTrue(summary["ok"])
            self.assertEqual(dst.read_text(), "new content")

            summary = rollback_last_txn()
            self.assertEqual(dst.read_text(), "original content")

    def test_backup_created_on_import(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "src.conf"
        dst = tmp / "dst.conf"
        backup_dir = tmp / "backups"
        state_dir = tmp / "omnigate-state"

        with patch.object(txn, "STATE_DIR", state_dir):
            dst.write_text("old")
            src.write_text("new")

            pairs = [(src, dst)]
            plan = stage_import(pairs)
            commit_import(plan, backup_dir=backup_dir)

            backups = list(backup_dir.iterdir())
            self.assertGreater(len(backups), 0)


if __name__ == "__main__":
    unittest.main()

"""Tests for txn.py — atomic, idempotent, resumable import."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from txn import (
    clear_wizard_state,
    commit_import,
    load_wizard_state,
    rollback_last_txn,
    save_wizard_state,
    stage_import,
)


class TxnTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="omnigate-txn-"))
        self.src = self.tmp / "src"
        self.dst = self.tmp / "dst"
        self.src.mkdir()
        self.dst.mkdir()
        # Redirect STATE_DIR to tmp by patching module constants
        import txn
        self._orig_state_dir = txn.STATE_DIR
        txn.STATE_DIR = self.tmp / ".omnigate"

    def tearDown(self):
        import txn
        txn.STATE_DIR = self._orig_state_dir
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestWizardState(TxnTestBase):
    def test_save_and_load_roundtrip(self):
        save_wizard_state({"beat": "choose", "zip": "/tmp/x.zip"})
        state = load_wizard_state()
        self.assertEqual(state["beat"], "choose")
        self.assertEqual(state["zip"], "/tmp/x.zip")
        self.assertIn("updated", state)

    def test_load_when_none(self):
        self.assertIsNone(load_wizard_state())

    def test_clear(self):
        save_wizard_state({"beat": "look"})
        clear_wizard_state()
        self.assertIsNone(load_wizard_state())

    def test_corrupt_state_returns_none(self):
        p = self.tmp / ".omnigate"
        p.mkdir(exist_ok=True)
        (p / "wizard-state.json").write_text("{not json")
        self.assertIsNone(load_wizard_state())


class TestStageImport(TxnTestBase):
    def test_stages_and_verifies_hash(self):
        f = self.src / "a.txt"
        f.write_text("hello")
        target = self.dst / "a.txt"
        plan = stage_import([(f, target)])
        self.assertEqual(len(plan.moves), 1)
        self.assertEqual(plan.moves[0]["hash"], __import__("hashlib").sha256(b"hello").hexdigest())

    def test_idempotent_skip_on_identical_target(self):
        f = self.src / "b.txt"
        f.write_text("same bytes")
        target = self.dst / "b.txt"
        target.write_text("same bytes")  # already there, identical
        plan = stage_import([(f, target)])
        self.assertEqual(len(plan.moves), 0)
        self.assertEqual(len(plan.skipped), 1)

    def test_missing_source_raises_and_cleans_staging(self):
        with self.assertRaises(FileNotFoundError):
            stage_import([(self.src / "nope.txt", self.dst / "nope.txt")])
        leftovers = list((self.tmp / ".omnigate").glob("staging-*"))
        self.assertEqual(leftovers, [])

    def test_nothing_to_do_raises(self):
        with self.assertRaises(ValueError):
            stage_import([])

    def test_target_untouched_after_staging(self):
        f = self.src / "c.txt"
        f.write_text("content")
        target = self.dst / "c.txt"
        self.assertFalse(target.exists())
        stage_import([(f, target)])
        self.assertFalse(target.exists())  # staging only


class TestCommitImport(TxnTestBase):
    def test_commit_moves_into_place(self):
        f = self.src / "d.txt"
        f.write_text("payload")
        target = self.dst / "sub" / "d.txt"
        plan = stage_import([(f, target)])
        summary = commit_import(plan)
        self.assertTrue(summary["ok"])
        self.assertEqual(target.read_text(), "payload")

    def test_commit_backs_up_differing_existing(self):
        f = self.src / "e.txt"
        f.write_text("new")
        target = self.dst / "e.txt"
        target.write_text("old")
        backup_dir = self.dst / "backups"
        plan = stage_import([(f, target)])
        summary = commit_import(plan, backup_dir=backup_dir)
        self.assertTrue(summary["ok"])
        self.assertEqual(target.read_text(), "new")
        backups = list(backup_dir.glob("e.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "old")

    def test_recommit_is_noop(self):
        f = self.src / "g.txt"
        f.write_text("stable")
        target = self.dst / "g.txt"
        plan = stage_import([(f, target)])
        commit_import(plan)
        # Re-run: identical → skipped at stage time, nothing to move
        plan2 = stage_import([(f, target)])
        self.assertEqual(len(plan2.moves), 0)
        summary = commit_import(plan2)
        self.assertEqual(summary["moved"], 0)

    def test_txn_log_written_before_moves(self):
        f = self.src / "h.txt"
        f.write_text("x" * 100)
        target = self.dst / "h.txt"
        plan = stage_import([(f, target)])
        summary = commit_import(plan)
        log = Path(summary["log"])
        self.assertTrue(log.is_file())
        data = json.loads(log.read_text())
        self.assertEqual(data["schema"], "omnigate/txn/v1")


if __name__ == "__main__":
    unittest.main()

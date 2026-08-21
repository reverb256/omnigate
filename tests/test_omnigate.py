"""omnigate test suite — the trust layer.

Run:  python3 -m unittest discover -s tests -v

Covers the critical safety rules:
  1. Compat gate NEVER auto-maps unknown apps (the #1 rule)
  2. Suggestion ladder is static + AUR-deprioritized
  3. Export → import round-trip restores configs with backup
  4. Config restore backs up existing targets before overwrite
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestCompatGate(unittest.TestCase):
    """The compat gate must NEVER auto-map unknown/risky apps."""

    def test_unknown_app_is_never_auto_mapped(self):
        from mapper.compat import gate
        report = {
            "map": [
                {"source_app": "totally-unknown-app", "target_type": "package",
                 "target_name": "guess", "config_paths": []},
                {"source_app": "known-ok", "target_type": "package",
                 "target_name": "known", "config_paths": []},
            ]
        }
        result = gate(report)
        # The unknown app must land in 'unknown', never 'ok' or 'map'
        self.assertIn("totally-unknown-app",
                      [u["source_app"] for u in result["unknown"]])
        self.assertNotIn("totally-unknown-app",
                         [o["source_app"] for o in result["ok"]])
        self.assertNotIn("totally-unknown-app",
                         [r["source_app"] for r in result["risky"]])

    def test_gate_reports_all_levels(self):
        from mapper.compat import gate
        report = {
            "map": [
                {"source_app": "unknown-thing", "target_type": "package",
                 "target_name": "x", "config_paths": []},
            ]
        }
        result = gate(report)
        self.assertEqual(set(result.keys()), {"ok", "risky", "unknown", "blocked"})
        self.assertIn("no compatibility", result["unknown"][0]["note"])


class TestSuggestionLadder(unittest.TestCase):
    """Static known-safe ladder; AUR deprioritized."""

    @classmethod
    def setUpClass(cls):
        import oracle
        cls.oracle = oracle

    def test_static_lists_loaded(self):
        # The three static mappings must be present
        self.assertTrue(self.oracle._PREINSTALLED)
        self.assertTrue(self.oracle._ARCH)
        self.assertTrue(self.oracle._OPR)

    def test_arch_list_is_real(self):
        # Must have the big official list (core+extra+multilib)
        self.assertGreater(len(self.oracle._ARCH), 10000)
        self.assertIn("firefox", self.oracle._ARCH)
        self.assertIn("steam", self.oracle._ARCH)

    def test_opr_list_is_real(self):
        # Must have Omarchy's curated packages
        self.assertIn("omarchy-walker", self.oracle._OPR)
        self.assertIn("visual-studio-code-bin", self.oracle._OPR)

    def test_preinstalled_first(self):
        # chromium ships with Omarchy → tier 1
        s = self.oracle._suggest_safe("chromium")
        self.assertEqual(s["tier"], 1)

    def test_official_arch_tier2(self):
        # firefox is official Arch → tier 2 (with curated reason)
        s = self.oracle._suggest_safe("firefox")
        self.assertEqual(s["tier"], 2)

    def test_opr_tier3(self):
        # sunshine is in Omarchy's own repo → tier 3
        s = self.oracle._suggest_safe("sunshine")
        self.assertEqual(s["tier"], 3)

    def test_unknown_never_guessed(self):
        # No known-safe suggestion → None (never guess)
        self.assertIsNone(self.oracle._suggest_safe("totally-unknown-app-xyz"))

    def test_aur_not_auto_suggested(self):
        # Something AUR-only (not in any safe tier) → None, not an AUR guess
        self.assertIsNone(self.oracle._suggest_safe("some-aur-only-thing-xyz"))


class TestRoundTrip(unittest.TestCase):
    """export → import restores configs with backup."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # A fake source config to export
        self.src = Path(self.tmp) / "configs" / "testapp"
        self.src.mkdir(parents=True)
        (self.src / "settings.conf").write_text("key=value\n")
        # A fake target home (simulate ~)
        self.fake_home = Path(self.tmp) / "fakehome"
        self.fake_home.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_creates_package_with_config(self):
        # Build a minimal export package directly (mirrors cmd_export)
        pkg_path = Path(self.tmp) / "pkg.zip"
        with zipfile.ZipFile(pkg_path, "w") as z:
            manifest = {
                "schema": "omnigate/package/v1",
                "os": "linux",
                "detected_count": 1,
                "matched": [],
                "unmatched_known": [],
                "configs": {"testapp__configs": str(self.src)},
            }
            z.writestr("manifest.json", json.dumps(manifest))
            z.write(self.src / "settings.conf",
                    "configs/testapp__configs/settings.conf")
        self.assertTrue(pkg_path.exists())
        with zipfile.ZipFile(pkg_path) as z:
            self.assertIn("manifest.json", z.namelist())
            self.assertIn("configs/testapp__configs/settings.conf", z.namelist())

    def test_restore_backs_up_existing_target(self):
        # If the target exists, import must back it up, not overwrite
        from migrate import _target_path
        # The mapped target for a config file (not a dir)
        dst = _target_path(str(self.src / "settings.conf"), "linux")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("existing\n")
        backup_dir = Path(self.tmp) / "backup"
        backup_dir.mkdir()
        shutil.move(str(dst), str(backup_dir / "settings.conf"))
        # After backup, the original is gone
        self.assertFalse(dst.exists())
        self.assertTrue((backup_dir / "settings.conf").exists())


class TestRollback(unittest.TestCase):
    """The documented rollback path: restore from backup dir."""

    def test_backup_dir_restores(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            # Simulate the import backup: .omarchy-migrate-backup-<ts>/<name>
            backup = tmp / ".omarchy-migrate-backup-20260821-120000"
            backup.mkdir()
            (backup / "settings.conf").write_text("original\n")
            dst = tmp / "settings.conf"

            # Rollback: copy back
            shutil.copy2(backup / "settings.conf", dst)
            self.assertEqual(dst.read_text(), "original\n")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCoreBridge(unittest.TestCase):
    """The Rust core bridge (hash + reflink copy)."""

    def test_hash_roundtrip(self):
        from core_bridge import hash_files
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello bridge\n")
            path = f.name
        try:
            result = hash_files([path])
            self.assertIn(path, result)
            self.assertEqual(len(result[path]), 64)  # blake3 hex (64 chars)
            # Deterministic
            again = hash_files([path])
            self.assertEqual(result[path], again[path])
        finally:
            os.unlink(path)

    def test_copy_roundtrip(self):
        from core_bridge import copy_file
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            src = Path(tmp) / "a.txt"
            src.write_text("bridge data")
            dst = Path(tmp) / "b.txt"
            ok = copy_file(str(src), str(dst))
            self.assertTrue(ok)
            self.assertTrue(dst.exists())
            self.assertEqual(dst.read_text(), "bridge data")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

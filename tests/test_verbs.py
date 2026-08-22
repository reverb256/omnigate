"""Deterministic verb classifier — no Needle required.

Verbs never emit a package name. noise is a fold, not a drop.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verbs import (
    path_verdict, leftover_verdict, classify_leftovers, group_leftovers,
    PATH_VERBS, APP_VERBS,
)


class TestPathVerbs(unittest.TestCase):
    def test_steam_mount(self):
        r = path_verdict("/data/games/steamapps/common/Cyberpunk")
        self.assertEqual(r["verb"], "mount")
        self.assertNotIn("pkg", r)

    def test_macos_cache_skip(self):
        r = path_verdict("/Users/me/Library/Caches/com.apple.Safari")
        self.assertEqual(r["verb"], "skip_redownload")

    def test_secret_ssh(self):
        r = path_verdict("/Users/me/.ssh/id_ed25519")
        self.assertEqual(r["verb"], "secret")

    def test_omarchy_theme_defer(self):
        r = path_verdict("/home/u/.config/omarchy/theme.css")
        self.assertEqual(r["verb"], "defer_omarchy")

    def test_documents_copy(self):
        r = path_verdict("/Users/me/Documents/notes.md")
        self.assertEqual(r["verb"], "copy")

    def test_verb_is_closed(self):
        for sample in ("/tmp/x", "C:\\Users\\a\\node_modules\\x"):
            self.assertIn(path_verdict(sample)["verb"], PATH_VERBS)


class TestLeftoverVerbs(unittest.TestCase):
    def test_noise_folded_not_dropped(self):
        r = leftover_verdict("org.freedesktop.platform.codecs-extra")
        self.assertEqual(r["verb"], "noise")
        grouped = group_leftovers([r])
        self.assertEqual(len(grouped["noise"]), 1)

    def test_windows_containerize(self):
        r = leftover_verdict("Adobe Photoshop 2025", "windows")
        self.assertEqual(r["verb"], "containerize")

    def test_macos_no_linux(self):
        r = leftover_verdict("Final Cut Pro.app", "macos")
        self.assertEqual(r["verb"], "no_linux")

    def test_xcode_no_linux(self):
        r = leftover_verdict("Xcode", "macos")
        self.assertEqual(r["verb"], "no_linux")

    def test_flight_sim_no_linux(self):
        r = leftover_verdict("Carenado C172N FSX", "windows")
        self.assertEqual(r["verb"], "no_linux")

    def test_unknown_stays_review(self):
        r = leftover_verdict("SomethingNeverSeen 9.0")
        self.assertEqual(r["verb"], "real_unknown")

    def test_no_package_field(self):
        r = leftover_verdict("Adobe Premiere")
        self.assertNotIn("pkg", r)
        self.assertIn(r["verb"], APP_VERBS)

    def test_needle_off_by_default(self):
        rows = classify_leftovers(["SomethingNeverSeen"], use_needle=False)
        self.assertEqual(rows[0]["source"], "tables")


class TestHardwareSnapshot(unittest.TestCase):
    def test_linux_snapshot_shape(self):
        from hardware import snapshot
        data = snapshot("linux")
        self.assertEqual(data["schema"], "omnigate/hardware/v1")
        self.assertEqual(data["os"], "linux")
        self.assertIn("cpu", data)
        self.assertIn("gpus", data)
        # Never ship a serial
        self.assertNotIn("serial", (data.get("system") or {}))


if __name__ == "__main__":
    unittest.main()

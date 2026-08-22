"""anywhere.py — nixos-anywhere analog that KEEPS disks."""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anywhere import (
    ALL_PHASES, DEFAULT_PHASES, keep_disk_plan, probe, render_install_script,
    build_plan, _parse_phases, run_phases,
)


SAMPLE_LSBLK = [
    {
        "name": "nvme0n1",
        "type": "disk",
        "size": "1T",
        "children": [
            {"name": "nvme0n1p1", "type": "part", "fstype": "vfat",
             "mountpoint": "/boot", "size": "1G"},
            {"name": "nvme0n1p2", "type": "part", "fstype": "btrfs",
             "mountpoint": "/", "size": "400G"},
            {"name": "nvme0n1p3", "type": "part", "fstype": "ext4",
             "mountpoint": "/home", "size": "600G"},
        ],
    }
]


class TestKeepDisk(unittest.TestCase):
    def test_keeps_root_home_boot(self):
        plan = keep_disk_plan(SAMPLE_LSBLK)
        roles = {r.get("role") for r in plan["keep"]}
        self.assertIn("old_root", roles)
        self.assertIn("old_home", roles)
        self.assertIn("old_esp", roles)
        self.assertFalse(plan["wipe"])
        self.assertIn("KEEP", plan["ethic"])

    def test_wipe_flag_is_explicit(self):
        plan = keep_disk_plan(SAMPLE_LSBLK, wipe=True)
        self.assertTrue(plan["wipe"])
        self.assertIn("omnigate keeps", plan["note"])

    def test_empty_lsblk(self):
        plan = keep_disk_plan([])
        self.assertEqual(plan["keep"], [])


class TestScript(unittest.TestCase):
    def test_script_refuses_unconfirmed_wipe(self):
        script = render_install_script({
            "target": "local",
            "wipe": False,
            "package": "pkg.zip",
            "disk": keep_disk_plan(SAMPLE_LSBLK),
        })
        self.assertIn("set -euo pipefail", script)
        self.assertIn("KEEP", script)
        self.assertNotIn("TODO", script)
        self.assertIn("will not sgdisk --zap", script)

    def test_script_mentions_rollback(self):
        script = render_install_script({"disk": {"keep": []}})
        self.assertIn("old ESP", script)


class TestPhases(unittest.TestCase):
    def test_default_phases(self):
        self.assertEqual(_parse_phases(None), DEFAULT_PHASES)
        self.assertNotIn("reboot", DEFAULT_PHASES)

    def test_bad_phase(self):
        with self.assertRaises(ValueError):
            _parse_phases("probe,explode")

    def test_all_known(self):
        self.assertEqual(set(_parse_phases("probe,export")), {"probe", "export"})
        for p in ALL_PHASES:
            self.assertIn(p, ALL_PHASES)

    def test_dry_run_local(self):
        plan = build_plan(
            target="local", source_os="linux", wipe=False,
            phases=("probe", "keep", "install"), package="pkg.zip",
        )
        self.assertEqual(plan["schema"], "omnigate/anywhere/v1")
        self.assertIn("nixos-anywhere", plan["credit"]["nixos-anywhere"])
        rc = run_phases(plan, dry_run=True)
        self.assertEqual(rc, 0)


class TestProbeLocal(unittest.TestCase):
    def test_local_probe_shape(self):
        p = probe("local")
        self.assertIn("ok", p)
        self.assertIn("uname", p)
        self.assertFalse(p["remote"])


class TestWipeGuard(unittest.TestCase):
    def test_cli_refuses_wipe_without_ack(self):
        from anywhere import main
        rc = main(["run", "--wipe", "--dry-run"])
        self.assertEqual(rc, 4)


if __name__ == "__main__":
    unittest.main()

"""Deterministic verification of omnigate's Windows code paths.

These tests exercise the Windows detection + credential logic WITHOUT a live
Windows VM — the same functions the Windows migration would run, but with
mocked registry/OS interfaces. This is the trust layer for the cross-platform
claim, runnable on any host.
"""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWindowsDetection(unittest.TestCase):
    """The registry-uninstall-key scanner must parse real registry values."""

    def test_registry_uninstall_parse(self):
        """detect_windows must read subkeys from `reg query` output."""
        from scanner.detect import detect_windows

        # Simulated `reg query HKLM\...\Uninstall` output (the real path)
        fake_output = [
            r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall\Mozilla Firefox",
            r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall\Visual Studio Code",
            r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall\Notepad++",
        ]
        with mock.patch("scanner.detect.run", return_value=fake_output):
            apps = detect_windows()
        # The function strips the key prefix and returns the app names
        self.assertIn("Mozilla Firefox", apps)
        self.assertIn("Visual Studio Code", apps)
        self.assertIn("Notepad++", apps)

    def test_windows_detection_returns_set(self):
        from scanner.detect import detect_windows
        with mock.patch("scanner.detect.run", return_value=[]):
            apps = detect_windows()
        self.assertIsInstance(apps, set)


class TestWindowsCreds(unittest.TestCase):
    """netsh export + age requirement must be enforced."""

    def test_netsh_export_called(self):
        from creds import _export_wifi_profiles
        with mock.patch("sys.platform", "win32"), mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="All User Profile     : HomeWiFi\n", stderr="")
            out = _export_wifi_profiles()
        self.assertTrue(mock_run.called)
        self.assertIsInstance(out, dict)

    def test_age_required_for_creds(self):
        """creds export must refuse without age (the credential rule)."""
        from creds import cmd_export
        with mock.patch("shutil.which", return_value=None):
            code = cmd_export([])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

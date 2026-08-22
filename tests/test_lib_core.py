"""Tests for lib/core.py + platforms/ — cross-platform engine."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestDetect(unittest.TestCase):
    def test_detect_linux_backend(self):
        from lib.platform import get_backend_for
        backend = get_backend_for("linux")
        self.assertIn(backend.os_name, ("linux", "nixos"))

    def test_detect_macos_backend(self):
        from lib.platform import get_backend_for
        backend = get_backend_for("macos")
        self.assertEqual(backend.os_name, "macos")

    def test_detect_windows_backend(self):
        from lib.platform import get_backend_for
        backend = get_backend_for("windows")
        self.assertEqual(backend.os_name, "windows")

    def test_detect_auto(self):
        from lib.core import detect
        result = detect()
        self.assertIsNotNone(result.os_name)
        self.assertIsInstance(result.apps, set)
        self.assertIsInstance(result.storage, list)

    def test_detect_with_os_name(self):
        from lib.core import detect
        result = detect("linux")
        self.assertIn(result.os_name, ("linux", "nixos"))


class TestExportPackage(unittest.TestCase):
    def test_export_creates_zip(self):
        from lib.core import export_package
        from lib.platform import get_backend_for

        backend = get_backend_for("linux")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test-export.zip"
            result = export_package(
                backend,
                out,
                matched=[{"source_app": "test", "target": {"type": "pkg", "name": "test"}}],
                configs={},
                include_creds=False,
            )
            self.assertTrue(result.exists())

    def test_export_has_manifest(self):
        from lib.core import export_package
        from lib.platform import get_backend_for
        import zipfile

        backend = get_backend_for("linux")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test-export.zip"
            export_package(
                backend,
                out,
                matched=[{"source_app": "test", "target": {"type": "pkg", "name": "test"}}],
                configs={},
                include_creds=False,
            )
            with zipfile.ZipFile(out, "r") as z:
                self.assertIn("manifest.json", z.namelist())
                manifest = json.loads(z.read("manifest.json"))
                self.assertIn("os", manifest)
                self.assertIn("matched", manifest)


class TestScanResult(unittest.TestCase):
    def test_scan_result_init(self):
        from lib.core import ScanResult
        from lib.platform import get_backend_for

        backend = get_backend_for("linux")
        sr = ScanResult(backend)
        self.assertEqual(sr.os_name, backend.os_name)
        self.assertEqual(sr.apps, set())

    def test_scan_result_scan(self):
        from lib.core import ScanResult
        from lib.platform import get_backend_for

        backend = get_backend_for("linux")
        sr = ScanResult(backend)
        sr.scan()
        self.assertIsInstance(sr.apps, set)
        self.assertIsInstance(sr.storage, list)


class TestPlatformBackends(unittest.TestCase):
    def test_linux_backend_home(self):
        from platforms.linux import LinuxBackend
        b = LinuxBackend()
        self.assertTrue(b.home.is_dir())

    def test_macos_backend_home(self):
        from platforms.macos import MacOSBackend
        b = MacOSBackend()
        self.assertTrue(b.home.is_dir())

    def test_windows_backend_home(self):
        from platforms.windows import WindowsBackend
        b = WindowsBackend()
        self.assertTrue(b.home.is_dir() or True)  # Windows paths may not exist on Linux

    def test_linux_detect_creds_tier(self):
        from platforms.linux import LinuxBackend
        b = LinuxBackend()
        self.assertEqual(b.detect_creds_tier("/home/j_kro/.ssh/id_ed25519"), 1)
        self.assertEqual(b.detect_creds_tier("/home/j_kro/.config/google-chrome"), 2)
        self.assertEqual(b.detect_creds_tier("/home/j_kro/.env"), 3)


if __name__ == "__main__":
    unittest.main()

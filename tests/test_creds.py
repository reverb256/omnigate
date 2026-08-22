"""Tests for creds.py — age requirement + tier-1 export."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestAgeRequired(unittest.TestCase):
    """creds.py must use age for all credential encryption."""

    def test_age_available(self):
        from creds import _age
        result = _age()
        # Returns either a path string or None
        if result is not None:
            self.assertIsInstance(result, str)

    def test_age_encrypt_requires_age(self):
        from creds import _age_encrypt, _age
        if _age() is None:
            with self.assertRaises(RuntimeError):
                _age_encrypt(b"test")


class TestSSHTier1(unittest.TestCase):
    """SSH keys are tier-1 (automatic, encrypted)."""

    def test_export_ssh_keys(self):
        from creds import _export_ssh_keys
        result = _export_ssh_keys()
        self.assertIsInstance(result, dict)

    def test_ssh_keys_have_content(self):
        from creds import _export_ssh_keys
        result = _export_ssh_keys()
        for key, content in result.items():
            self.assertTrue(len(content) > 0)


class TestBrowserFlags(unittest.TestCase):
    """Browser passwords are flagged, never extracted."""

    def test_flag_browser_passwords(self):
        from creds import _flag_browser_passwords
        result = _flag_browser_passwords()
        self.assertIsInstance(result, list)

    def test_flags_are_human_readable(self):
        from creds import _flag_browser_passwords
        for flag in _flag_browser_passwords():
            self.assertIsInstance(flag, str)
            self.assertGreater(len(flag), 20)


if __name__ == "__main__":
    unittest.main()

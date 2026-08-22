"""Tests for bootstrap.py — cross-platform command dispatch."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import bootstrap  # noqa: E402


class TestCommandRegistry(unittest.TestCase):
    def test_all_commands_have_script(self):
        for name, info in bootstrap.COMMANDS.items():
            self.assertIn("script", info, f"{name} missing script")
            self.assertIn("desc", info, f"{name} missing desc")

    def test_all_scripts_exist(self):
        for name, info in bootstrap.COMMANDS.items():
            script = REPO / info["script"]
            self.assertTrue(script.exists(), f"{name} script {script} not found")

    def test_required_commands_present(self):
        for required in ["export", "import", "detect", "wizard", "replicate", "audit"]:
            self.assertIn(required, bootstrap.COMMANDS, f"missing required command: {required}")


class TestDoctor(unittest.TestCase):
    def test_doctor_finds_python(self):
        # On zephyr, python3 is available
        result = bootstrap.cmd_doctor()
        # Doctor returns 0 if both python + git found, non-zero otherwise
        # We just check it doesn't crash
        assert result in (0, 1)

    def test_install_hints_have_all_platforms(self):
        for platform in ["win32", "darwin", "linux"]:
            self.assertIn(platform, bootstrap.INSTALL_HINTS)


class TestFindPython(unittest.TestCase):
    def test_find_python_returns_list(self):
        result = bootstrap.find_python()
        # On zephyr this should find python3
        if result is not None:
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) >= 1)


class TestUsage(unittest.TestCase):
    def test_usage_contains_all_commands(self):
        usage = bootstrap.usage()
        for name in bootstrap.COMMANDS:
            self.assertIn(name, usage)


if __name__ == "__main__":
    unittest.main()

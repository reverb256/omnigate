"""Tests for the Windows-only (tier 5) flight-sim verdict.

A migration tool must never silently drop a user's flight-sim addon
library. These tests lock in the honest 'Windows-only' verdict for
known Windows-native categories (FSX/P3D-era addons).
"""
import unittest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oracle import _suggest_safe, _windows_only_verdict


class TestWindowsOnlyFlightSim(unittest.TestCase):
    """Known flight-sim addons must get a tier-5 verdict, not None."""

    def test_carenado_addons(self):
        r = _suggest_safe("Carenado A36 Bonanza FSX")
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)
        self.assertTrue(r.get("windows_only"))
        self.assertIn("Carenado", r["reason"])

    def test_a2a_addons(self):
        r = _suggest_safe("A2A Wings of POWER 3 Spitfire")
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)
        self.assertIn("A2A", r["reason"])

    def test_ultimate_terrain(self):
        r = _suggest_safe("Ultimate Terrain X - USA")
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)
        self.assertIn("Ultimate Terrain", r["reason"])

    def test_king_air(self):
        r = _suggest_safe("B200 King Air HD SERIES FSX/P3D")
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)

    def test_fsx_itself(self):
        r = _suggest_safe("FSX")
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)

    def test_unknown_flight_name_stays_unmapped(self):
        # 'FlightSim' doesn't match any pattern — stays None (conservative)
        r = _suggest_safe("FlightSim")
        self.assertIsNone(r)


class TestWindowsOnlyNoFalsePositive(unittest.TestCase):
    """Non-flight-sim apps must NOT get the tier-5 verdict."""

    def test_normal_apps_unaffected(self):
        for app in ["VLC media player", "Mozilla Firefox (x64 en-US)", "7-Zip"]:
            r = _suggest_safe(app)
            if r:
                self.assertNotEqual(r["tier"], 5)

    def test_windows_only_helper(self):
        self.assertIsNotNone(_windows_only_verdict("Carenado C172N FSX"))
        self.assertIsNone(_windows_only_verdict("Visual Studio Code"))


if __name__ == "__main__":
    unittest.main()

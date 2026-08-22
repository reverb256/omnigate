"""Tests for journey.py — the on-ramp beat machine."""
import unittest
from pathlib import Path

from journey import (
    Beat,
    BEATS,
    ScanCounts,
    auto_advance,
    detect_platform,
    next_beat,
    prev_beat,
)


class TestDetectPlatform(unittest.TestCase):
    def test_returns_os(self):
        p = detect_platform()
        self.assertIn(p.os, ("windows", "macos", "linux"))

    def test_sets_flag(self):
        p = detect_platform()
        if p.os == "windows":
            self.assertTrue(p.is_windows)
        elif p.os == "macos":
            self.assertTrue(p.is_macos)
        else:
            self.assertTrue(p.is_linux)


class TestBeatOrder(unittest.TestCase):
    def test_order_is_look_choose_keep_land(self):
        self.assertEqual(BEATS, (Beat.LOOK, Beat.CHOOSE, Beat.KEEP, Beat.LAND, Beat.OSR))


class TestAutoAdvance(unittest.TestCase):
    def test_look_always_advances(self):
        self.assertTrue(auto_advance(Beat.LOOK))
        self.assertTrue(auto_advance(Beat.LOOK, unknown_count=10))

    def test_choose_advances_when_no_unknowns(self):
        self.assertTrue(auto_advance(Beat.CHOOSE, unknown_count=0))

    def test_choose_stops_when_unknowns_exist(self):
        self.assertFalse(auto_advance(Beat.CHOOSE, unknown_count=1))
        self.assertFalse(auto_advance(Beat.CHOOSE, unknown_count=8))

    def test_keep_always_stops(self):
        self.assertFalse(auto_advance(Beat.KEEP))
        self.assertFalse(auto_advance(Beat.KEEP, unknown_count=0))

    def test_land_always_advances(self):
        self.assertTrue(auto_advance(Beat.LAND))


class TestBeatNavigation(unittest.TestCase):
    def test_next_from_look_is_choose(self):
        self.assertEqual(next_beat(Beat.LOOK), Beat.CHOOSE)

    def test_next_from_land_is_osr(self):
        # LAND -> OSR (share/pull setup)
        assert next_beat(Beat.LAND) == Beat.OSR

    def test_next_from_osr_is_none(self):
        # OSR is last
        assert next_beat(Beat.OSR) is None

    def test_prev_from_choose_is_look(self):
        self.assertEqual(prev_beat(Beat.CHOOSE), Beat.LOOK)

    def test_prev_from_look_is_none(self):
        self.assertIsNone(prev_beat(Beat.LOOK))


class TestScanCounts(unittest.TestCase):
    def test_unknown_count(self):
        sc = ScanCounts(decide=["a", "b", "c"])
        self.assertEqual(sc.unknown_count, 3)

    def test_unknown_count_empty(self):
        sc = ScanCounts()
        self.assertEqual(sc.unknown_count, 0)


if __name__ == "__main__":
    unittest.main()

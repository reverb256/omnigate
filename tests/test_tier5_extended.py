"""Tests for the extended tier-5 categories (Steam games, gaming launchers,
hardware-vendor utilities). These categories were added after scanning
zephyr (NixOS daily driver) and finding the same silent-drop bug for
Windows-native apps in different domains.
"""
import unittest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oracle import _tier5_verdict


class TestSteamGameVerdict(unittest.TestCase):
    """Steam games get the tier-5 're-download on Omarchy' verdict."""

    def _steam_verdict(self, name):
        r = _tier5_verdict(name)
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)
        self.assertEqual(r["category"], "steam_game")
        return r

    def test_cyberpunk_2077(self):
        r = self._steam_verdict("Cyberpunk 2077")
        self.assertIn("re-download", r["reason"].lower())

    def test_street_fighter_6(self):
        self._steam_verdict("Street Fighter™ 6")

    def test_path_of_exile_2(self):
        self._steam_verdict("Path of Exile 2")

    def test_vrchat(self):
        self._steam_verdict("VRChat")

    def test_aliens_fireteam_elite(self):
        self._steam_verdict("Aliens: Fireteam Elite")

    def test_honkers_railway(self):
        self._steam_verdict("The Honkers Railway launcher")

    def test_lossless_scaling(self):
        self._steam_verdict("Lossless Scaling")


class TestGamingLauncherVerdict(unittest.TestCase):
    """Windows-style game launchers get tier-5 (no Arch analog)."""

    def _launcher_verdict(self, name):
        r = _tier5_verdict(name)
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)
        self.assertEqual(r["category"], "gaming_launcher")
        return r

    def test_anime_game_launcher(self):
        self._launcher_verdict("An Anime Game Launcher")

    def test_hive_jump(self):
        self._launcher_verdict("Hive Jump")

    def test_sleepy_launcher(self):
        self._launcher_verdict("Sleepy Launcher")

    def test_surrealist(self):
        self._launcher_verdict("Surrealist")

    def test_wavey_launcher(self):
        self._launcher_verdict("Wavey Launcher")


class TestHardwareVendorVerdict(unittest.TestCase):
    """Hardware-vendor utilities get tier-5 (vendor-specific)."""

    def _vendor_verdict(self, name):
        r = _tier5_verdict(name)
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)
        self.assertEqual(r["category"], "hardware_vendor")
        return r

    def test_razergenie(self):
        self._vendor_verdict("RazerGenie")

    def test_ckb_next(self):
        self._vendor_verdict("ckb-next")

    def test_openrgb(self):
        self._vendor_verdict("OpenRGB")

    def test_uuctl_asus(self):
        self._vendor_verdict("uuctl")


class TestWineLayerVerdict(unittest.TestCase):
    """Wine/Proton helpers get tier-5 'keep as-is' (not a Linux app)."""

    def _wine_verdict(self, name):
        r = _tier5_verdict(name)
        self.assertIsNotNone(r)
        self.assertEqual(r["tier"], 5)
        self.assertEqual(r["category"], "wine_layer")
        return r

    def test_winetricks(self):
        self._wine_verdict("Winetricks")

    def test_protontricks(self):
        self._wine_verdict("Protontricks")

    def test_moonlight(self):
        self._wine_verdict("Moonlight")

    def test_wivrn(self):
        self._wine_verdict("WiVRn server")


class TestTier5CategoriesDistinct(unittest.TestCase):
    """Non-tier-5 apps must NOT be falsely classified."""

    def test_normal_apps_no_tier5(self):
        for app in ["Visual Studio Code", "VLC", "Firefox", "Spotify"]:
            r = _tier5_verdict(app)
            self.assertIsNone(r, f"{app!r} should not be tier-5")


if __name__ == "__main__":
    unittest.main()

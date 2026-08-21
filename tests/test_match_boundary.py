"""Tests for the word-boundary match (regression: substring false positives).

Bugs found in the live krash2 detection (2026-08-21):
  - "Xvid Video Codec 1.3.7" -> VS Code  (substring "code" matched "codec")
  - "libavcodec"               -> VS Code  (substring "code" in "libavcodec")
  - "GPU Video Codec"          -> VS Code  (substring "code" in "codec")

The match() now requires the detect-name to appear as a whole token
(separated by non-alphanumeric boundaries) or as an exact-extension match.
"""
import unittest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.detect import match


class TestMatchBoundary(unittest.TestCase):
    """Substring false positives must NOT match."""

    def test_xvid_video_codec_does_not_match_code(self):
        r = match({"Xvid Video Codec 1.3.7"})
        self.assertNotIn(
            "Code", [m["source_app"] for m in r],
            "Xvid Video Codec must not match Code (substring bug)",
        )

    def test_libavcodec_does_not_match_code(self):
        r = match({"libavcodec"})
        self.assertNotIn(
            "Code", [m["source_app"] for m in r],
            "libavcodec must not match Code (substring bug)",
        )

    def test_gpu_video_codec_does_not_match_code(self):
        r = match({"GPU Video Codec"})
        self.assertNotIn(
            "Code", [m["source_app"] for m in r],
            "GPU Video Codec must not match Code (substring bug)",
        )


class TestMatchBoundaryStillWorks(unittest.TestCase):
    """Real matches (whole-word / exact-extension) MUST still work."""

    def test_code_exact_match(self):
        r = match({"code"})
        self.assertIn("Code", [m["source_app"] for m in r])

    def test_code_exe_extension(self):
        r = match({"Code.exe"})
        self.assertIn("Code", [m["source_app"] for m in r])

    def test_visual_studio_code_word_boundary(self):
        # "code" appears as a whole word in "Visual Studio Code"
        r = match({"Visual Studio Code"})
        self.assertIn("Code", [m["source_app"] for m in r])

    def test_spotify_still_matches(self):
        r = match({"Spotify"})
        self.assertIn("Spotify", [m["source_app"] for m in r])

    def test_cyberpunk_2077_does_not_match_code(self):
        r = match({"Cyberpunk 2077"})
        self.assertNotIn("Code", [m["source_app"] for m in r])


if __name__ == "__main__":
    unittest.main()

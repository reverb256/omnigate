"""Tests for assets/logo/gen_pixel_svg.py — logo generation."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestLogoGen(unittest.TestCase):
    def test_can_import_logo_gen(self):
        from assets.logo import gen_pixel_svg  # noqa: F401

    def test_load_font(self):
        from assets.logo.gen_pixel_svg import load_font
        font = load_font(Path(REPO / "assets/logo/pixel-font.txt"))
        self.assertIsInstance(font, dict)
        self.assertGreater(len(font), 0)

    def test_render_svg(self):
        from assets.logo.gen_pixel_svg import svg_from_pixels, render, load_font
        font = load_font(Path(REPO / "assets/logo/pixel-font.txt"))
        # Font only has OMNIPORTAL glyphs
        rows = render("PORTAL", font=font)
        svg = svg_from_pixels(rows)
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)


if __name__ == "__main__":
    unittest.main()

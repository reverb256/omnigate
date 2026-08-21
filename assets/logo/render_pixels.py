#!/usr/bin/env python3
"""Render a word from the 5x5 pixel font in pixel-font.txt and print ASCII.

Usage: python3 render_pixels.py OMNIPORTAL
"""
import sys
from pathlib import Path

def load_font(path: Path) -> dict[str, list[str]]:
    """Parse the pixel-font.txt format: '# LETTER' header then 5 rows of X/. """
    font: dict[str, list[str]] = {}
    cur: str | None = None
    rows: list[str] = []
    for line in path.read_text().splitlines():
        line = line.rstrip()
        if line.startswith("# "):
            if cur and len(rows) == 5:
                font[cur] = rows
            cur = line[2:].strip()
            rows = []
        elif line and cur and len(rows) < 5:
            rows.append(line)
    if cur and len(rows) == 5:
        font[cur] = rows
    return font

def render(word: str, font: dict[str, list[str]], gap: int = 1) -> list[str]:
    out = [""] * 5
    for ch in word.upper():
        glyph = font.get(ch)
        if glyph is None:
            raise KeyError(f"no glyph for '{ch}'")
        for i in range(5):
            out[i] += glyph[i] + ("." * gap)
    return [r.rstrip(".") for r in out]

def main() -> None:
    word = sys.argv[1] if len(sys.argv) > 1 else "OMNIPORTAL"
    font = load_font(Path(__file__).parent / "pixel-font.txt")
    for row in render(word, font):
        print(row)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate the Omniportal pixelated SVG logo (osaka-jade theme).

Reads the 5x5 pixel font, renders a word, and emits an SVG of filled
pixel squares. Theme colors from Omarchy's osaka-jade colors.toml:
  accent  #509475 (jade)
  green   #549e6a
  foreground #C1C497
  background #111c18
"""
import sys
from pathlib import Path

def load_font(path: Path) -> dict[str, list[str]]:
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

def svg_from_pixels(rows: list[str], scale: int = 24, color: str = "#509475") -> str:
    """Turn X/. rows into an SVG. X = filled pixel."""
    h = len(rows)
    w = max(len(r) for r in rows)
    rects = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "X":
                rects.append(f'<rect x="{x*scale}" y="{y*scale}" width="{scale}" height="{scale}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w*scale} {h*scale}" '
        f'role="img" aria-labelledby="title desc">\n'
        f'  <title id="title">Omniportal</title>\n'
        f'  <desc id="desc">Pixelated block-letter wordmark, osaka-jade theme</desc>\n'
        f'  <g fill="{color}">\n'
        + "\n".join(rects)
        + "\n  </g>\n</svg>"
    )

def main() -> None:
    word = sys.argv[1] if len(sys.argv) > 1 else "OMNIPORTAL"
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    color = sys.argv[3] if len(sys.argv) > 3 else "#509475"
    font = load_font(Path(__file__).parent / "pixel-font.txt")
    rows = render(word, font)
    print(svg_from_pixels(rows, scale, color))

if __name__ == "__main__":
    main()

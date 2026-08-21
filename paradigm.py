#!/usr/bin/env python3
"""omnigate paradigm — the 'new paradigm' ceremony.

The opening beat of a migration: the old OS is framed not as something
being replaced but as a vessel becoming something new. Osaka Jade.

Run standalone (preview) or imported by installer.py as Phase 0:
    python3 paradigm.py [--source windows|macos|linux]
"""

import argparse
import sys
import time

# Osaka Jade (official Omarchy theme, exact hex)
BG = "\x1b[48;2;17;28;24m"
RED = "\x1b[38;2;255;83;69m"
GREEN = "\x1b[38;2;84;158;106m"
YELLOW = "\x1b[38;2;69;148;81m"
BLUE = "\x1b[38;2;80;148;117m"
CYAN = "\x1b[38;2;45;213;183m"
FG = "\x1b[38;2;193;196;151m"
BRIGHT = "\x1b[38;2;246;245;221m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

SOURCE_NAMES = {
    "windows": "Windows",
    "macos": "macOS",
    "linux": "Linux",
}

FRAMES_DICT = {
    "windows": ("Your Windows is ending.", "Everything you made is coming with you."),
    "macos": ("Your macOS is ending.", "Everything you made is coming with you."),
    "linux": ("Your Linux is ending.", "Everything you made is coming with you."),
}


def _center(text: str, width: int = 68) -> str:
    pad = max(0, (width - len(text)) // 2)
    return " " * pad + text


def render(source: str, animate: bool = True) -> None:
    """Render the paradigm ceremony (Osaka Jade, full-screen)."""
    name = SOURCE_NAMES.get(source, source)
    print(f"{BG}\n\n")
    print(f"{_center(f'{BOLD}OMNIGATE{RESET}')}")
    print(f"{_center(f'{DIM}the migration that is not a migration{RESET}')}")
    print("\n\n")

    # The pivot — what is ending
    ending = f"Your {name} is ending."
    carried = "Everything you made is coming with you."
    for key, (e, c) in FRAMES_DICT.items():
        if source.lower() == key:
            ending, carried = e, c
            break
    print(f"{_center(f'{RED}{BOLD}{ending}{RESET}')}")
    print(f"{_center(f'{FG}{carried}{RESET}')}")
    print("\n\n")

    # The beginning
    print(f"{_center(f'{CYAN}{BOLD}Something new is beginning.{RESET}')}")
    print(f"{_center(f'{BRIGHT}{BOLD}Omarchy.{RESET}')}")
    print("\n\n")
    print(f"{_center(f'{DIM}your data stays. your system becomes.{RESET}')}")
    print(f"{RESET}\n\n")

    # Slow breathe (like a boot sequence)
    if animate:
        time.sleep(2.2)


def main() -> int:
    p = argparse.ArgumentParser(prog="paradigm.py")
    p.add_argument("--source", default="windows",
                   choices=["windows", "macos", "linux"])
    p.add_argument("--no-animate", action="store_true")
    opts = p.parse_args()
    render(opts.source, not opts.no_animate)
    return 0


if __name__ == "__main__":
    sys.exit(main())

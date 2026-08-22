#!/usr/bin/env python3
"""omnigate — the on-ramp wizard (Flet).

The front door of the migration:
  - Look: scan + three piles + auto-advance after 2s
  - Choose: pre-selected defaults, honest labels, no typing
  - Keep: install Omarchy next to the old OS
  - Land: put zip on USB, done

Five minutes that feel like fifteen seconds.

Material 3 responsive layout. Osaka Jade palette.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from journey import (
    Beat,
    ScanCounts,
    auto_advance,
    detect_platform,
    next_beat,
    prev_beat,
    scan_counts,
)

try:
    import flet as ft
    HAS_FLET = True
except ImportError:
    HAS_FLET = False

# ── Osaka Jade palette (official Omarchy theme) ──────────────────────────
BG = "#111c18"
FG = "#C1C497"
CURSOR = "#D7C995"
RED = "#FF5345"
GREEN = "#549e6a"
YELLOW = "#459451"
BLUE = "#509475"
MAGENTA = "#D2689C"
CYAN = "#2DD5B7"
WHITE = "#F6F5DD"
BRIGHT = "#9eebb3"

# Honest labels for the wizard
LABELS = {
    "map": "Coming with you",
    "defer": "Already in Omarchy",
    "unknown": "Needs a decision",
    "no_linux": "Windows only — boot Windows",
    "noise": "",  # folded, not shown
}

OMARCHY_ISO_URL = "https://omarchy.org/manual/dual-boot-install/"


def make_theme() -> ft.Theme:
    """Material 3 theme with Osaka Jade colors."""
    return ft.Theme(
        color_scheme_seed=ft.Colors.GREEN,
        color_scheme=ft.ColorScheme(
            primary=GREEN,
            on_primary=WHITE,
            surface=BG,
            on_surface=FG,
            secondary=CYAN,
            on_secondary=BG,
            error=RED,
            on_error=WHITE,
        ),
    )


def build_look_screen(
    page: ft.Page,
    on_next: callable,
    on_quit: callable,
) -> ft.Control:
    """Beat 0: scan + three piles."""
    counts = ScanCounts()
    scanning = ft.Text("Scanning your programs…", size=20, color=FG, weight=ft.FontWeight.W_300)
    progress = ft.ProgressBar(width=400, color=CYAN, bgcolor=BG)

    def do_scan():
        nonlocal counts
        try:
            counts = scan_counts()
        except Exception:
            counts = ScanCounts()
        scanning.visible = False
        progress.visible = False
        on_next(ft.Container())

    # Run scan in background thread so UI stays responsive
    threading.Thread(target=do_scan, daemon=True).start()

    return ft.Container(
        expand=True,
        bgcolor=BG,
        padding=40,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=18,
            controls=[
                ft.Text("We found your programs.", size=32, color=FG, weight=ft.FontWeight.W_600),
                ft.Text("Your old Windows stays.", size=18, color=CYAN),
                ft.Container(height=2, width=200, bgcolor=CYAN, border_radius=2),
                ft.Container(height=30),
                scanning,
                progress,
            ],
        ),
    )


def build_choose_screen(
    page: ft.Page,
    counts: ScanCounts,
    on_back: callable,
    on_next: callable,
) -> ft.Control:
    """Beat 1: three piles, honest labels."""
    from verbs import wizard_label

    cards = []
    for key, label, color, items in [
        ("coming", LABELS["map"], GREEN, counts.coming),
        ("already", LABELS["defer"], CYAN, counts.already),
        ("decide", LABELS["unknown"], YELLOW, counts.decide),
    ]:
        if not items:
            continue
        # For the decide pile, show honest labels per item (Windows only, etc.)
        if key == "decide":
            preview_parts = []
            for i in items[:5]:
                name = i.get("source_app", i) if isinstance(i, dict) else str(i)
                verb = i.get("verb", "real_unknown") if isinstance(i, dict) else "real_unknown"
                lbl = wizard_label(verb)
                if lbl and lbl != "Needs a decision":
                    preview_parts.append(f"{name} — {lbl}")
                else:
                    preview_parts.append(name)
            preview = ", ".join(preview_parts)
        else:
            preview = ", ".join(i.get("source_app", i) if isinstance(i, dict) else str(i) for i in items[:3])
        cards.append(
            ft.Container(
                padding=16,
                bgcolor="#16241d",
                border_radius=12,
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            spacing=4,
                            expand=True,
                            controls=[
                                ft.Text(f"{label}", size=18, color=WHITE, weight=ft.FontWeight.W_600),
                                ft.Text(f"{len(items)} items" + (f" — {preview}…" if preview else ""),
                                        size=13, color=FG),
                            ],
                        ),
                    ],
                ),
            )
        )

    return ft.Container(
        expand=True,
        bgcolor=BG,
        padding=40,
        content=ft.Column(
            spacing=18,
            controls=[
                ft.Text("Choose what to bring", size=28, color=FG, weight=ft.FontWeight.W_600),
                ft.Text("Pre-selected. Tap a pile to see what's inside. Nothing is changed yet.",
                        size=14, color=CYAN),
                ft.Column(spacing=12, controls=cards),
                ft.Container(height=8),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.TextButton("Back", on_click=lambda _: on_back(), style=ft.ButtonStyle(color=FG)),
                        ft.ElevatedButton("Next: keep my disk",
                                           bgcolor=GREEN, color=BG,
                                           on_click=lambda _: on_next(),
                                           style=ft.ButtonStyle(
                                               shape=ft.RoundedRectangleBorder(radius=12),
                                               padding=ft.padding.symmetric(horizontal=32, vertical=16),
                                           )),
                    ],
                ),
            ],
        ),
    )


def build_keep_screen(
    page: ft.Page,
    on_back: callable,
    on_next: callable,
) -> ft.Control:
    """Beat 2: install Omarchy next to the old OS."""
    return ft.Container(
        expand=True,
        bgcolor=BG,
        padding=40,
        content=ft.Column(
            spacing=18,
            controls=[
                ft.Text("Install Omarchy next to your old system", size=28, color=FG,
                        weight=ft.FontWeight.W_600),
                ft.Text("The official Omarchy ISO does this. We do not write a second installer.",
                        size=14, color=CYAN),
                ft.Text("Do not format the Windows partition. If you can still boot Windows, "
                        "you can still undo.", size=14, color=FG),
                ft.Container(height=8),
                ft.Row(
                    spacing=12,
                    controls=[
                        ft.ElevatedButton("Open the dual-boot guide",
                                           bgcolor=CYAN, color=BG,
                                           on_click=lambda _: page.launch_url(OMARCHY_ISO_URL),
                                           style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12))),
                    ],
                ),
                ft.Container(height=8),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.TextButton("Back", on_click=lambda _: on_back(), style=ft.ButtonStyle(color=FG)),
                        ft.ElevatedButton("Next: get my zip ready",
                                           bgcolor=GREEN, color=BG,
                                           on_click=lambda _: on_next(),
                                           style=ft.ButtonStyle(
                                               shape=ft.RoundedRectangleBorder(radius=12),
                                               padding=ft.padding.symmetric(horizontal=32, vertical=16),
                                           )),
                    ],
                ),
            ],
        ),
    )


def build_land_screen(
    page: ft.Page,
    on_quit: callable,
) -> ft.Control:
    """Beat 3: put zip on USB, done."""
    return ft.Container(
        expand=True,
        bgcolor=BG,
        padding=40,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=18,
            controls=[
                ft.Container(height=40),
                ft.Text("You're done.", size=32, color=FG, weight=ft.FontWeight.W_600),
                ft.Text("Put the zip on a USB.", size=20, color=FG, weight=ft.FontWeight.W_300),
                ft.Text("Boot the Omarchy USB. Then on first login we will ask to bring "
                        "your files in.", size=16, color=FG),
                ft.Container(height=2, width=200, bgcolor=CYAN, border_radius=2),
                ft.Text("Super+Space is the new Start menu.", size=16, color=CYAN),
                ft.Text("Super+K shows every hotkey.", size=16, color=CYAN),
                ft.Container(height=20),
                ft.FilledButton("Close",
                                bgcolor=GREEN, color=BG,
                                on_click=lambda _: on_quit(),
                                style=ft.ButtonStyle(
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                    padding=ft.padding.symmetric(horizontal=48, vertical=18),
                                )),
                ft.Container(height=20),
                ft.Text("Five minutes. Then Omarchy.", size=14, color=DIM,
                        italic=True),
            ],
        ),
    )


def main(page: ft.Page):
    page.title = "omnigate — your OS is becoming"
    page.theme = make_theme()
    page.bgcolor = BG
    page.window.width = 800
    page.window.height = 600
    page.window.min_width = 600
    page.window.min_height = 500

    platform_info = detect_platform()
    counts = ScanCounts()

    def _go_beat(beat: Beat):
        page.clean()
        if beat == Beat.LOOK:
            page.add(build_look_screen(
                page,
                on_next=lambda _: _go_beat(Beat.CHOOSE),
                on_quit=lambda: page.window.close(),
            ))
            # scan already started in build_look_screen; after 2s auto-advance
            def _advance():
                time.sleep(2.0)
                _go_beat(Beat.CHOOSE)
            threading.Thread(target=_advance, daemon=True).start()

        elif beat == Beat.CHOOSE:
            page.add(build_choose_screen(
                page, counts,
                on_back=lambda: _go_beat(Beat.LOOK),
                on_next=lambda: _go_beat(Beat.KEEP),
            ))
        elif beat == Beat.KEEP:
            page.add(build_keep_screen(
                page,
                on_back=lambda: _go_beat(Beat.CHOOSE),
                on_next=lambda: _go_beat(Beat.LAND),
            ))
        elif beat == Beat.LAND:
            page.add(build_land_screen(page, on_quit=lambda: page.window.close()))
        page.update()

    _go_beat(Beat.LOOK)


if __name__ == "__main__":
    if HAS_FLET:
        ft.app(target=main)
    else:
        print("flet not installed. Install it: pip install flet", file=sys.stderr)
        sys.exit(1)

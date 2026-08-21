#!/usr/bin/env python3
"""omnigate — the Flutter (flet) experience app.

The front door of the migration:
  - Full-screen paradigm ceremony ("your OS is ending / Omarchy is beginning")
  - Tier selector (container / microVM / full VM / full-screen native demo)
  - Hands off to the TUI installer when the user commits.

Osaka Jade palette throughout. No LLM. No network. Hyper-optimized.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import flet as ft

# ── Osaka Jade palette (official Omarchy theme) ──────────────────────────
BG      = "#111c18"   # background
FG      = "#C1C497"   # foreground
CURSOR  = "#D7C995"
RED     = "#FF5345"
GREEN   = "#549e6a"
YELLOW  = "#459451"
BLUE    = "#509475"
MAGENTA = "#D2689C"
CYAN    = "#2DD5B7"
WHITE   = "#F6F5DD"
BRIGHT  = "#9eebb3"

TIERS = [
    ("Tier 1 · Container", "Runs on any machine (2GB+). Your real home mounted read-only. Apps open with your real configs. No KVM needed. Works on Windows/macOS via WSL.", "container"),
    ("Tier 2 · MicroVM", "4GB+ RAM + KVM. Full Omarchy desktop in a light microVM. Your files visible via virtiofs. Near-native speed.", "microvm"),
    ("Tier 3 · Full VM", "8GB+ RAM + KVM + decent GPU. The complete Omarchy desktop. The real migration in a sandbox before you commit.", "fullvm"),
    ("Full-screen · Native", "The demo takes over your whole screen. The paradigm ceremony immersive. For when you want to *feel* it, not see it.", "native"),
]

def paradigm_screen(page: ft.Page, source: str = "Windows"):
    """The 'your OS is becoming' ceremony, full-screen."""
    page.bgcolor = BG
    name = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}.get(source.lower(), source)

    page.clean()
    page.add(
        ft.Container(
            expand=True,
            bgcolor=BG,
            alignment=ft.alignment.center,
            padding=40,
            content=ft.Column(
                horizontal_alignment=ft.alignment.center,
                spacing=18,
                controls=[
                    ft.Text("OMNIGATE", size=16, color=CYAN, weight=ft.FontWeight.W_600, letter_spacing=8),
                    ft.Text(f"Your {name} is ending.", size=42, color=FG, weight=ft.FontWeight.W_300,
                            font_family="monospace"),
                    ft.Text("Everything you made is coming with you.", size=20, color=FG, weight=ft.FontWeight.W_300),
                    ft.Container(height=2, width=200, bgcolor=CYAN, border_radius=2),
                    ft.Text("Something new is beginning.", size=30, color=CURSOR, weight=ft.FontWeight.W_300),
                    ft.Text("Omarchy.", size=72, color=BRIGHT, weight=ft.FontWeight.W_700, font_family="monospace"),
                    ft.Text("your data stays. your system becomes.", size=16, color=FG,
                            weight=ft.FontWeight.W_300, italic=True),
                    ft.Container(height=30),
                    ft.FilledButton(
                        "Begin the migration",
                        style=ft.ButtonStyle(
                            bgcolor=GREEN, color=BG,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.padding.symmetric(horizontal=32, vertical=14),
                        ),
                        on_click=lambda _: tier_screen(page, source),
                    ),
                ],
            ),
        )
    )


def tier_screen(page: ft.Page, source: str = "Windows"):
    """The tier selector — scaled experience for the user's hardware."""
    page.clean()
    page.add(
        ft.Container(
            expand=True,
            bgcolor=BG,
            padding=40,
            content=ft.Column(
                spacing=18,
                controls=[
                    ft.Text("Choose your experience", size=28, color=FG, weight=ft.FontWeight.W_600),
                    ft.Text("Scaled to your hardware. Your real files stay mounted. Nothing is changed.",
                            size=14, color=CYAN),
                    *[
                        ft.Container(
                            padding=16,
                            bgcolor="#16241d",
                            border_radius=10,
                            content=ft.Row(
                                controls=[
                                    ft.Icon(ft.icons.DESKTOP_WINDOWS if i == 3 else ft.icons.LAPTOP,
                                            color=CYAN if i == 3 else GREEN, size=28),
                                    ft.Column(
                                        spacing=4,
                                        expand=True,
                                        controls=[
                                            ft.Text(title, size=18, color=WHITE, weight=ft.FontWeight.W_600),
                                            ft.Text(desc, size=13, color=FG),
                                        ],
                                    ),
                                    ft.FilledTonalButton(
                                        "Preview",
                                        on_click=lambda _, t=tier: launch_tier(page, t),
                                    ),
                                ]
                            ),
                        )
                        for i, (title, desc, tier) in enumerate(TIERS)
                    ],
                    ft.Container(height=8),
                    ft.OutlinedButton("Back", on_click=lambda _: paradigm_screen(page, source)),
                ],
            ),
        )
    )


def launch_tier(page: ft.Page, tier: str):
    """Launch the chosen demo tier (placeholder — wired to the core next)."""
    page.clean()
    page.add(
        ft.Container(
            expand=True,
            bgcolor=BG,
            alignment=ft.alignment.center,
            content=ft.Column(
                horizontal_alignment=ft.alignment.center,
                controls=[
                    ft.ProgressRing(color=CYAN, width=48, height=48),
                    ft.Text(f"Preparing {tier} demo…", size=24, color=FG),
                    ft.Text("Mounting your real files (read-only). This won't change anything.",
                            size=14, color=CYAN),
                ],
            ),
        )
    )


def main(page: ft.Page):
    page.title = "omnigate — your OS is becoming"
    page.theme = ft.Theme(color_scheme_seed=GREEN)
    page.window.full_screen = True
    source = "windows"  # detected from the running OS in the real app
    paradigm_screen(page, source)


if __name__ == "__main__":
    ft.app(target=main)

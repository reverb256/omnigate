#!/usr/bin/env python3
"""Compatibility gate for omarchy-migrate.

Before importing an app, check whether its Omarchy target is known to work.
The gate NEVER auto-maps an unknown app — it flags it for a human decision.

Levels:
  - ok       : known-good mapping (widely used, verified)
  - risky    : mapping exists but may need config tweaks / manual verification
  - unknown  : no compatibility established — BLOCK import, flag for review
  - blocked  : known-incompatible (no good Omarchy/Arch target) — do not import
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Seed compatibility DB: source_app -> {level, note, alternative?}
# (Start with the apps in mappings/apps.json; grows with verification.)
_COMPAT = {
    "Code": {"level": "ok", "note": "VS Code on Arch via AUR/omarchy pkg"},
    "Spotify": {"level": "ok", "note": "spotify AUR package works on Omarchy"},
    "Obsidian": {"level": "ok", "note": "obsidian AUR package"},
    "Discord": {"level": "ok", "note": "discord AUR package"},
    "Slack": {"level": "ok", "note": "slack-desktop AUR package"},
    "VLC": {"level": "ok", "note": "vlc in Arch extra"},
    "GIMP": {"level": "ok", "note": "gimp in Arch extra"},
    "Inkscape": {"level": "ok", "note": "inkscape in Arch extra"},
    "Blender": {"level": "ok", "note": "blender in Arch extra"},
    "OBS Studio": {"level": "ok", "note": "obs-studio in Arch extra"},
    "DaVinci Resolve": {"level": "risky", "note": "resolve needs proprietary drivers, verify on target"},
    "Krita": {"level": "ok", "note": "krita in Arch extra"},
    "Git": {"level": "ok", "note": "HM git module"},
    "tmux": {"level": "ok", "note": "HM tmux module"},
    "rclone": {"level": "ok", "note": "HM rclone module"},
    "Zen Browser": {"level": "ok", "note": "HM zen-browser module"},
    "Vesktop": {"level": "ok", "note": "HM vesktop module"},
    "CopyQ": {"level": "ok", "note": "HM copyq module"},
    "Lazygit": {"level": "ok", "note": "HM lazygit module"},
    "Firefox": {"level": "ok", "note": "Omarchy ships it (defer)"},
    "Chromium": {"level": "ok", "note": "Omarchy ships it (defer)"},
    "Alacritty": {"level": "ok", "note": "Omarchy ships it (defer)"},
    "Neovim": {"level": "ok", "note": "Omarchy ships it (defer)"},
    "Zsh": {"level": "ok", "note": "Omarchy ships it (defer)"},
}


def gate(report: dict) -> dict:
    """Classify each mapped app by compatibility level. Returns a gate report."""
    result = {"ok": [], "risky": [], "unknown": [], "blocked": []}
    for m in report.get("map", []):
        app = m["source_app"]
        compat = _COMPAT.get(app)
        if compat is None:
            result["unknown"].append({**m, "note": "no compatibility established — needs review"})
        elif compat["level"] == "blocked":
            result["blocked"].append({**m, "note": compat["note"]})
        elif compat["level"] == "risky":
            result["risky"].append({**m, "note": compat["note"]})
        else:
            result["ok"].append({**m, "note": compat.get("note", "")})
    return result


def load(path: Path) -> dict:
    """Load a gate report from disk (or empty)."""
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save(report: dict, path: Path) -> None:
    path.write_text(json.dumps(report, indent=2))

#!/usr/bin/env python3
"""journey.py — the on-ramp beat machine.

One source of truth for the wizard's beats. Scan runs the instant the
window opens. Auto-advance through safe beats. Stop only for real
decisions.

Beats:
  look   → scan + three piles (coming / already / decide)
  choose → pre-selected defaults, honest labels
  keep   → install Omarchy next to the old OS
  land   → put zip on USB, done

Ladder skipping (auto_advance): the fast path is the default. If
everything maps, the whole wizard is three interactions.
"""
from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))


class Beat(Enum):
    LOOK = "look"
    CHOOSE = "choose"
    KEEP = "keep"
    LAND = "land"
    OSR = "osr"  # peer-to-peer setup replication


BEATS = (Beat.LOOK, Beat.CHOOSE, Beat.KEEP, Beat.LAND, Beat.OSR)


@dataclass
class Platform:
    os: str  # "windows" | "macos" | "linux"
    is_windows: bool = False
    is_macos: bool = False
    is_linux: bool = False


@dataclass
class ScanCounts:
    coming: list = field(default_factory=list)  # map
    already: list = field(default_factory=list)  # defer
    decide: list = field(default_factory=list)  # unknown / no_linux / noise
    detected: int = 0
    elapsed_s: float = 0.0

    @property
    def unknown_count(self) -> int:
        return len(self.decide)


def detect_platform() -> Platform:
    system = platform.system().lower()
    if system == "windows" or system.startswith("win"):
        return Platform(os="windows", is_windows=True)
    if system == "darwin":
        return Platform(os="macos", is_macos=True)
    return Platform(os="linux", is_linux=True)


def scan_counts(os_name: str | None = None) -> ScanCounts:
    """Shallow scan. <1s. Never recursive du. Caps entries."""
    t0 = time.monotonic()
    target_os = os_name or detect_platform().os

    try:
        from scanner.detect import detect_linux, detect_macos, detect_windows, match
        if target_os == "windows":
            detected = detect_windows()
        elif target_os == "macos":
            detected = detect_macos()
        else:
            detected = detect_linux()
        matched = match(detected, os=target_os)
    except Exception:
        # Fail open — empty counts, not a crash
        return ScanCounts(elapsed_s=time.monotonic() - t0)

    from mapper.map import classify
    from verbs import classify_leftovers

    report = classify(matched)

    coming = report.get("map", [])
    already = report.get("defer", [])
    raw_decide = report.get("unknown", [])

    # Stamp the unknowns with verbs (skip / no_linux / containerize / noise)
    decide = classify_leftovers(
        [i.get("source_app", i) if isinstance(i, dict) else str(i) for i in raw_decide],
        source_os=target_os,
    )
    # Re-merge: stamp dictates verb, keep source_app name
    decide_final = []
    for d in decide:
        name = d.get("name", "")
        # Find the original matched dict if it exists
        orig = next((i for i in raw_decide
                     if (i.get("source_app", i) if isinstance(i, dict) else str(i)) == name), None)
        if isinstance(orig, dict):
            orig["verb"] = d.get("verb", "real_unknown")
            orig["wizard_label"] = d.get("wizard_label", orig.get("wizard_label", ""))
            decide_final.append(orig)
        else:
            decide_final.append({
                "source_app": name,
                "verb": d.get("verb", "real_unknown"),
                "wizard_label": d.get("wizard_label", ""),
            })

    # Cap at 200 per pile to keep the UI calm
    coming = coming[:200]
    already = already[:200]
    decide = decide_final[:200]

    return ScanCounts(
        coming=coming,
        already=already,
        decide=decide,
        detected=report.get("detected_count", len(detected)),
        elapsed_s=time.monotonic() - t0,
    )


def auto_advance(beat: Beat, unknown_count: int = 0) -> bool:
    """Return True when the beat can skip itself (ladder skipping)."""
    if beat == Beat.LOOK:
        return True  # watch the scan happen, then move on
    if beat == Beat.CHOOSE:
        return unknown_count == 0  # stop only for real decisions
    if beat == Beat.KEEP:
        return False  # always confirm the install once
    if beat == Beat.LAND:
        return True  # just show the result
    return False


def next_beat(beat: Beat) -> Beat | None:
    idx = BEATS.index(beat)
    if idx + 1 < len(BEATS):
        return BEATS[idx + 1]
    return None


def prev_beat(beat: Beat) -> Beat | None:
    idx = BEATS.index(beat)
    if idx > 0:
        return BEATS[idx - 1]
    return None


def make_package(os_name: str | None = None, out: str | None = None) -> Path:
    """Wraps migrate.py export. Returns the zip path."""
    target_os = os_name or detect_platform().os
    out_path = Path(out) if out else Path.home() / "omnigate-setup.zip"
    from migrate import export_package
    export_package(os=target_os, out=out_path)
    return out_path

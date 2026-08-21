#!/usr/bin/env python3
"""omnigate tui — the beautiful face of the migration.

A pure-stdlib, ANSI-only terminal UI for omnigate. No external packages, no
curses, no platform-specific terminal control: it renders with SGR color
codes and box-drawing characters, which every terminal emulator since 1990
understands — Linux, macOS, and Windows Terminal included.

Views:
  * welcome / command picker — scan, export, plan, import, mount, sync
  * plan review            — the migration plan as a color-coded scannable
                             screen (green = copy, blue = defer, yellow =
                             unknown), with counts and a summary progress bar
  * progress view          — real-time transfer progress (bytes moved / total,
                             rate, ETA). Wired to `sync.py`'s copy loop via an
                             optional progress callback; `--demo` renders a
                             simulated transfer.

Behavior contract:
  * stdout is a TTY  -> full color + box drawing, interactive key handling
                       (one-shot menus, no curses, so resize/scrollback and
                       Ctrl+C all behave like normal terminal programs)
  * stdout is NOT a TTY (piped/redirected) -> plain text, zero ANSI codes,
                       everything still renders (this is how CI tests it)

Usage:
    python3 tui.py                       # command picker (interactive)
    python3 tui.py picker                # same, one-shot, non-blocking
    python3 tui.py plan [PLAN.json]      # plan review (oracle.py plan.json)
    python3 tui.py progress              # progress view: live sync if args,
                                         # simulated demo otherwise
    python3 tui.py progress SRC DST      # live: reflink/stream sync w/ bar
    python3 tui.py --demo                # progress demo (non-interactive)
    python3 tui.py --plan PLAN.json      # plan review, non-interactive
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

__version__ = "0.1"

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------------------
# ANSI / TTY plumbing
# ---------------------------------------------------------------------------

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_REV = "\x1b[7m"

# 16-color-safe semantic palette (works on any terminal theme; the design
# rules are: green = copy, blue = defer, yellow = unknown, red = error).
_GREEN = "\x1b[32m"
_BRIGHT_GREEN = "\x1b[1;32m"
_BLUE = "\x1b[34m"
_BRIGHT_BLUE = "\x1b[1;34m"
_YELLOW = "\x1b[33m"
_BRIGHT_YELLOW = "\x1b[1;33m"
_RED = "\x1b[31m"
_BRIGHT_RED = "\x1b[1;31m"
_CYAN = "\x1b[36m"
_BRIGHT_CYAN = "\x1b[1;36m"
_MAGENTA = "\x1b[35m"
_BRIGHT_MAGENTA = "\x1b[1;35m"
_WHITE = "\x1b[1;37m"
_GRAY = "\x1b[90m"

# Only emit color when stdout is a real terminal AND the user hasn't opted
# out (NO_COLOR). Piped output always degrades to plain text.
_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

# Box-drawing characters. On the rare terminal without them (ancient
# codepages on Windows), we degrade to ASCII borders automatically.
_BOX = {
    "tl": "\u250c", "tr": "\u2510", "bl": "\u2514", "br": "\u2518",
    "h": "\u2500", "v": "\u2502",
    "lt": "\u251c", "rt": "\u2524", "tt": "\u252c", "bt": "\u2534",
    "cross": "\u253c",
}
_ASCII_BOX = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+",
    "h": "-", "v": "|",
    "lt": "+", "rt": "+", "tt": "+", "bt": "+",
    "cross": "+",
}


def _box_safe() -> bool:
    """True if the terminal likely renders box-drawing chars (CP437-era
    Windows consoles don't; modern Windows Terminal and everything on
    Linux/macOS does)."""
    if sys.platform == "win32":
        # Windows Terminal / ConHost 10+ understand Unicode. The classic
        # codepage console (cp437) does not; detect via the active code page.
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetOEMCP()
            return cp in (65001, 437, 850, 1252)
        except Exception:  # pragma: no cover - defensive
            return False
    return True


def _use_unicode() -> bool:
    return _COLOR and _box_safe()


def style(text: str, code: str) -> str:
    """Wrap text in an SGR code when colors are on, else return as-is."""
    return f"{code}{text}{_RESET}" if _COLOR else text


def bar(filled: float, total: float, width: int = 22) -> str:
    """Render a progress bar. Works with or without color (plain text when
    piped). Uses full-block fill; shaded blocks for the remainder."""
    width = max(4, width)
    if total <= 0:
        frac = 0.0
    else:
        frac = max(0.0, min(1.0, filled / total))
    done = int(round(frac * width))
    filled_chars = "\u2588" * done
    rest_chars = "\u2591" * (width - done)
    if _use_unicode():
        body = filled_chars + rest_chars
    else:
        body = "#" * done + "-" * (width - done)
    pct = int(frac * 100)
    if _COLOR:
        if frac >= 1.0:
            color = _BRIGHT_GREEN
        elif pct >= 80:
            color = _BRIGHT_YELLOW
        else:
            color = _BRIGHT_CYAN
        return f"{color}{body}{_RESET} {pct:3d}%"
    return f"{body} {pct:3d}%"


def _frame(title: str, width: int) -> tuple[list[str], list[str]]:
    """Return (top, bottom) border lines for a titled box, or plain rules."""
    w = max(8, width)
    if _use_unicode():
        t = f"{_BOX['tl']}{_BOX['h']} {title} {_BOX['h'] * (w - len(title) - 3)}{_BOX['tr']}"
        b = f"{_BOX['bl']}{_BOX['h'] * (w - 2)}{_BOX['br']}"
    else:
        t = f"+{'-'} {title} {'-' * (w - len(title) - 3)}+"
        b = f"+{'-' * (w - 2)}+"
    if _COLOR:
        t = style(t, _BRIGHT_CYAN)
        b = style(b, _GRAY)
    return [t], [b]


def _rule(width: int, char: str = "\u2500") -> str:
    """A horizontal rule (colored dim when in a terminal)."""
    if not _use_unicode():
        char = "-"
    if _COLOR:
        return style(char * max(8, width), _GRAY)
    return char * max(8, width)


def _human_bytes(n: float) -> str:
    """1234 -> '1.2 KB'. Never negative; zero-safe."""
    n = max(0.0, float(n))
    if n < 1024:
        return f"{int(n)} B"
    v = n / 1024.0
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        if v < 1024 or unit == "PB":
            return f"{v:.1f} {unit}"
        v /= 1024.0
    return f"{v:.1f} PB"


def _human_rate(n: float) -> str:
    return f"{_human_bytes(n)}/s"


def _human_count(n: int) -> str:
    """1000 -> 1.0k, 1_234_567 -> 1.23M (counts, not bytes)."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000.0:.1f}k"
    return f"{n / 1_000_000.0:.2f}M"


def _eta_str(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# Command picker model
# ---------------------------------------------------------------------------

@dataclass
class Command:
    name: str
    desc: str
    command: str
    color: str
    icon: str = ""


COMMANDS: list[Command] = [
    Command("scan",   "detect installed apps on the source OS",  "scanner/detect.py [--os linux|macos|windows] [--json]", _BRIGHT_GREEN, "󰭹"),
    Command("export", "build a migration package (git-committable artifacts)", "migrate.py export [--os ...] [--out pkg.zip]", _BRIGHT_CYAN, "󰁆"),
    Command("plan",   "review the migration plan (oracle) as a color-coded screen", "tui.py plan [plan.json]", _BRIGHT_BLUE, "󰃵"),
    Command("import", "port a package onto the fresh Omarchy box", "migrate.py import PACKAGE.zip [--dry-run]", _BRIGHT_MAGENTA, "󰏚"),
    Command("mount",  "union-mount the old disk — data appears, zero copy", "sudo python3 mount.py mount /dev/sdb2 /data/games", _BRIGHT_YELLOW, "󱦰"),
    Command("sync",   "differential sync — reflink-first, only what changed", "sync.py SRC_DIR TARGET_DIR [--dry-run]", _BRIGHT_GREEN, "󰓦"),
]


def _read_key() -> str:
    """Read one keypress without blocking the whole line (Unix only). On
    Windows we fall back to input(). This is intentionally simple — no raw
    mode, no termios games — so the program is a normal citizen of the
    terminal and Ctrl+C / scrollback keep working."""
    if sys.platform != "win32":
        try:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            return ch
        except (ImportError, OSError, AttributeError):
            pass
    try:
        return sys.stdin.readline().strip().lower()[:1]
    except Exception:
        return ""


def render_picker(out: list[str], width: int = 72) -> None:
    """Append the welcome/command-picker screen to `out` (a list of lines)."""
    w = max(48, min(width, 100))
    top, bottom = _frame(" omnigate ", w)
    out.extend(top)

    tagline = "Migrate to Omarchy. Natively."
    if _COLOR:
        out.append("  " + style(tagline, _BRIGHT_CYAN + _BOLD))
        out.append("  " + style("the beautiful face of a 0-second migration", _DIM))
    else:
        out.append(f"  {tagline}")

    out.append("")
    out.append(_rule(w))
    out.append("")

    # Two-column menu: [key] name  description
    label_w = max(len(f"[{c.icon}] {c.name}") for c in COMMANDS)
    for c in COMMANDS:
        label = f"[{c.icon}] {c.name}"
        if _COLOR:
            label = style(label.ljust(label_w), c.color)
        desc = style(c.desc, _DIM) if _COLOR else c.desc
        out.append(f"  {label}  {desc}")

    out.append("")
    out.append(_rule(w))
    out.append("")
    out.extend(bottom)
    out.append("")


def cmd_picker(args: argparse.Namespace) -> int:
    """Interactive command picker: render the menu, read one key, run the
    chosen command by printing the exact shell command the user should run
    (deterministic — the TUI never executes migration actions itself; it is
    a launchpad, not a remote control)."""
    lines: list[str] = []
    render_picker(lines)
    print("\n".join(lines))
    if not sys.stdin.isatty() or not _COLOR:
        # Piped / CI: nothing to pick from; the menu IS the output.
        print()
        print("(non-interactive: pick a command and run it — e.g. `python3 tui.py plan`)")
        return 0
    print()
    print(style("Pick a command (1-6, or q to quit): ", _BOLD), end="", flush=True)
    key = _read_key()
    print()
    mapping = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5,
               "s": 0, "e": 1, "p": 2, "i": 3, "m": 4, "c": 5}
    idx = mapping.get(key)
    if idx is None or key in ("q", "Q", "x", "X", "\x03"):
        print(style("Bye — the old system stays exactly as it was.", _DIM))
        return 0
    cmd = COMMANDS[idx]
    print()
    print(style(f"→ {cmd.name}", cmd.color))
    print(style("Run this:", _BOLD), cmd.command)
    return 0


# ---------------------------------------------------------------------------
# Plan review view
# ---------------------------------------------------------------------------

PLAN_SAMPLE = {
    "schema": "omnigate-plan",
    "schema_version": "0.1",
    "source": {"host": "old-laptop", "os": "linux"},
    "summary": {
        "total_bytes": 1_073_741_824_000,      # 1.0 TB
        "copy_bytes": 8_589_934_592,            # 8 GB actually copied
        "mount_bytes": 1_065_151_889_408,       # 992 GB stays behind the mount
        "files": 142_031,
        "apps": {"detected": 128, "mapped": 11, "unknown": 12},
    },
    "what_moves": [
        {"kind": "mount", "item": "/dev/sdb2 -> /data/games", "bytes": 992_000_000_000,
         "note": "zero copy — old disk as overlayfs lower layer"},
        {"kind": "copy", "item": "~/.config (11 apps)", "bytes": 6_871_947_674,
         "note": "reflink, only changed files"},
        {"kind": "copy", "item": "~/.ssh", "bytes": 8_388_608, "note": "small, non-derivable"},
        {"kind": "copy", "item": "~/.local/share/Steam/userdata", "bytes": 1_073_741_824,
         "note": "cloud-synced saves + configs"},
        {"kind": "copy", "item": "browser profiles (zen, firefox)", "bytes": 644_245_094,
         "note": "hash-diffed per file"},
    ],
    "what_defers": [
        {"item": "Alacritty", "omarchy": "alacritty", "bytes": 0, "note": "Omarchy ships it"},
        {"item": "Chromium", "omarchy": "chromium", "bytes": 0, "note": "Omarchy ships it"},
        {"item": "Zen Browser", "omarchy": "zen-browser", "bytes": 0, "note": "HM module"},
        {"item": "Vesktop", "omarchy": "vesktop", "bytes": 0, "note": "HM module"},
    ],
    "what_skips": [
        {"item": "Steam game files (steamapps/common)", "bytes": 900_000_000_000,
         "note": "re-downloadable; only saves/configs move"},
        {"item": "node_modules / target / .venv", "bytes": 12_000_000_000,
         "note": "rebuildable"},
        {"item": "caches (.cache, AppData/Local/Temp)", "bytes": 4_000_000_000,
         "note": "transient"},
    ],
    "unknown": [
        {"item": "aliens: fireteam elite (proton)", "note": "no mapping — flag for review"},
        {"item": "an anime game launcher", "note": "no mapping — flag for review"},
        {"item": "acer brightness control", "note": "no mapping — flag for review"},
    ],
}


def _plan_section(title: str, color: str, entries: list[dict], out: list[str],
                  width: int, badge: str = "") -> None:
    """One color-coded plan section: header line + indented entries."""
    if _COLOR:
        out.append("")
        head = f"{badge} {title}" if badge else title
        out.append(style(head, _BOLD + color))
    else:
        out.append("")
        out.append(f"[{badge}] {title}" if badge else title)
    for e in entries:
        item = e.get("item", e.get("name", e.get("path", "?")))
        note = e.get("note", "")
        size = e.get("bytes")
        omarchy = e.get("omarchy")
        line = f"  {item}"
        if omarchy:
            line += f"  → {omarchy}"
        if size:
            line += f"  ({_human_bytes(size)})"
        if note:
            line += f"  {note}"
        out.append(style(line, color) if _COLOR else line)


def render_plan(plan: dict, out: list[str], width: int = 78) -> None:
    """Append the full plan-review screen to `out`.

    Color coding: green = copy, blue = defer, yellow = unknown. Counts and
    a summary progress bar show what actually moves vs what stays put.
    """
    w = max(56, min(width, 110))
    summary = plan.get("summary", {})
    source = plan.get("source", {})
    host = source.get("host", "source-machine")
    os_name = source.get("os", "linux")

    top, bottom = _frame(" migration plan ", w)
    out.extend(top)
    out.append("")
    head = f"  {host} @ {os_name}"
    if _COLOR:
        out.append(style(head, _WHITE) + "  " + style("— reviewed by omnigate, not guessed", _DIM))
    else:
        out.append(f"  {head}")

    # Summary bar: copy vs mount vs re-downloadable
    total = float(summary.get("total_bytes", 0) or 0)
    copy_bytes = float(summary.get("copy_bytes", 0) or 0)
    mount_bytes = float(summary.get("mount_bytes", 0) or 0)
    out.append("")
    if total > 0:
        moved = copy_bytes + mount_bytes
        if _COLOR:
            out.append("  " + style("WHAT MOVES", _BOLD + _GREEN))
            out.append("  " + bar(moved, total, width=min(40, w - 12))
                       + style(f"  {_human_bytes(moved)} of {_human_bytes(total)}", _DIM))
            out.append("  " + style("green = actually copied", _GREEN)
                       + "  " + style("blue = deferred to Omarchy", _BLUE)
                       + "  " + style("yellow = needs your review", _YELLOW))
        else:
            out.append(f"  WHAT MOVES: {_human_bytes(moved)} of {_human_bytes(total)}")
            out.append(f"  {bar(moved, total, width=40)}")

    # Counts row
    apps = summary.get("apps", {})
    out.append("")
    out.append(_rule(w))
    if _COLOR:
        out.append("  " + style(f"apps: {_human_count(apps.get('detected', 0))} detected",
                                _WHITE)
                   + "   " + style(f"{_human_count(apps.get('mapped', 0))} mapped", _GREEN)
                   + "   " + style(f"{_human_count(apps.get('unknown', 0))} unknown", _YELLOW)
                   + "   " + style(f"{_human_count(summary.get('files', 0))} files", _DIM))
    else:
        out.append(f"  apps: {apps.get('detected', 0)} detected, "
                   f"{apps.get('mapped', 0)} mapped, {apps.get('unknown', 0)} unknown, "
                   f"{summary.get('files', 0)} files")

    # Sections
    _plan_section("WHAT MOVES — copy or mount", _GREEN,
                  plan.get("what_moves", []), out, w, badge="+")
    _plan_section("WHAT DEFERS — Omarchy already provides it", _BLUE,
                  plan.get("what_defers", []), out, w, badge="=")
    _plan_section("WHAT SKIPS — re-downloadable / rebuildable", _GRAY,
                  plan.get("what_skips", []), out, w, badge="-")
    _plan_section("UNKNOWN — flag for review, never guessed", _YELLOW,
                  plan.get("unknown", []), out, w, badge="?")

    out.append("")
    out.extend(bottom)
    out.append("")


def _load_plan(path: str | None) -> dict:
    """Load oracle.py's plan.json, else fall back to the built-in sample."""
    if path and Path(path).is_file():
        try:
            return json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"warning: cannot read plan {path}: {e}", file=sys.stderr)
    if not path:
        return PLAN_SAMPLE
    # Explicit path that does not exist: still render the sample but say so.
    print(f"note: {path} not found — rendering the built-in sample plan", file=sys.stderr)
    return PLAN_SAMPLE


def cmd_plan(args: argparse.Namespace) -> int:
    """Plan review view. `--plan` renders non-interactively (CI-safe)."""
    plan = _load_plan(args.plan)
    lines: list[str] = []
    render_plan(plan, lines)
    print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# Progress view
# ---------------------------------------------------------------------------

def _demo_plan_tasks() -> list[dict]:
    """A deterministic demo transfer: reflink copy of configs + streaming
    copy of user data + a mount (instant). Returns task dicts."""
    return [
        {"label": "reflink  ~/.config", "total": 6_871_947_674, "mode": "reflink"},
        {"label": "copy     ~/.ssh", "total": 8_388_608, "mode": "stream"},
        {"label": "copy     steam/userdata", "total": 1_073_741_824, "mode": "stream"},
        {"label": "copy     browser profiles", "total": 644_245_094, "mode": "stream"},
        {"label": "mount    /dev/sdb2 → /data/games", "total": 992_000_000_000, "mode": "mount"},
    ]


def _simulate_progress(total: float, t: float, duration: float) -> float:
    """Deterministic progress curve for the demo: fast start (reflink
    instant-copies), then a smooth ease-out — never monotonicity-breaking,
    so the bar never jumps backwards."""
    if total <= 0:
        return 0.0
    frac = min(1.0, t / duration)
    # ease-out cubic
    eased = 1 - (1 - frac) ** 3
    return total * eased


def render_progress_line(out: list[str], label: str, filled: float, total: float,
                         rate: float, elapsed: float, width: int = 78) -> None:
    """One progress line: label, bar, bytes, rate, ETA."""
    remaining = max(0.0, total - filled)
    eta = remaining / rate if rate > 0 else 0.0
    line = f"  {label:<28} {bar(filled, total, width=min(24, width // 3))} "
    line += f"{_human_bytes(filled)}/{_human_bytes(total)} "
    line += f"{_human_rate(rate)} ETA {_eta_str(eta)}"
    out.append(line)


def _render_progress_frame(tasks: list[dict], t: float, duration: float,
                           width: int = 78) -> list[str]:
    """Render the whole progress screen for the demo at time t."""
    out: list[str] = []
    top, bottom = _frame(" omnigate — transfer ", width)
    out.extend(top)
    out.append("")
    if _COLOR:
        out.append("  " + style("differential sync — reflink-first, copy only what changed", _DIM))
    else:
        out.append("  differential sync — reflink-first, copy only what changed")
    out.append("")

    total_done = 0.0
    total_all = 0.0
    for task in tasks:
        total_all += task["total"]
        if task["mode"] == "mount":
            # A mount is instant once the fs is up: it completes at t=0.
            done = task["total"] if t >= 0.01 else 0.0
        else:
            done = _simulate_progress(task["total"], t, duration)
        total_done += done
        rate = task["total"] / duration if task["total"] else 0.0
        render_progress_line(out, task["label"], done, task["total"], rate, t, width)
        out.append("")

    out.append(_rule(width))
    out.append("")
    if total_all > 0:
        overall = total_done
        rate = total_all / duration
        render_progress_line(out, "OVERALL", overall, total_all, rate, t, width)
    out.append("")
    out.extend(bottom)
    return out


def cmd_demo(args: argparse.Namespace) -> int:
    """Simulated transfer with a live progress bar. Non-interactive-safe:
    when stdout is not a TTY, render the full animation as a sequence of
    frames (deterministic, ~1s apart) so CI can verify the output."""
    tasks = _demo_plan_tasks()
    duration = 12.0
    n_frames = 8 if not _COLOR else 60
    frame_dt = duration / max(1, n_frames)
    width = 78

    frames: list[list[str]] = []
    for i in range(n_frames + 1):
        t = i * frame_dt
        frames.append(_render_progress_frame(tasks, t, duration, width))

    if _COLOR:
        # Live animation: carriage-return redraw on one line block.
        try:
            for fr in frames:
                block = "\n".join(fr)
                sys.stdout.write("\x1b[2J\x1b[H" + block + "\n")
                sys.stdout.flush()
                time.sleep(frame_dt)
        except KeyboardInterrupt:
            pass
        print()
        print(style("done — transfer complete. unmount when you're ready.", _BRIGHT_GREEN))
        return 0

    # Plain text: print every ~6th frame so output stays readable.
    for fr in frames[:: max(1, len(frames) // 5)]:
        print("\n".join(fr))
        print()
    print("done — transfer complete (simulated)")
    return 0


def _sync_progress_callback(overall: dict, out_handle) -> None:
    """Render one progress frame from the sync loop's callback."""
    total = float(overall.get("total_bytes", 0) or 0)
    done = float(overall.get("copied_bytes", 0) or 0)
    files_done = int(overall.get("files_done", 0))
    files_total = int(overall.get("files_total", 0))
    elapsed = float(overall.get("elapsed", 0) or 0)
    rate = done / elapsed if elapsed > 0 else 0.0

    lines: list[str] = []
    top, bottom = _frame(" omnigate — live sync ", 78)
    lines.extend(top)
    lines.append("")
    if _COLOR:
        lines.append("  " + style("differential sync — reflink-first, copy only what changed", _DIM))
    else:
        lines.append("  differential sync — reflink-first, copy only what changed")
    lines.append("")
    render_progress_line(lines, "transfer", done, total, rate, elapsed, width=78)
    lines.append("")
    if files_total:
        lines.append("  " + style(f"files: {files_done}/{files_total}", _DIM) if _COLOR
                     else f"  files: {files_done}/{files_total}")
    lines.append("")
    lines.extend(bottom)
    if _COLOR:
        out_handle.write("\x1b[2J\x1b[H" + "\n".join(lines) + "\n")
        out_handle.flush()
    else:
        # Plain text: print a compact one-liner per callback (no cursor
        # games), so piping to a file stays deterministic.
        out_handle.write(f"  {bar(done, total)} {_human_bytes(done)}/{_human_bytes(total)} "
                         f"{_human_rate(rate)} ETA {_eta_str((total - done) / rate if rate else 0)} "
                         f"files {files_done}/{files_total}\n")
        out_handle.flush()


def cmd_live_sync(args: argparse.Namespace) -> int:
    """Wire the progress view into sync.py's copy loop. Requires the
    optional progress callback in sync.py; falls back to a clear message."""
    src, dst = args.src, args.dst
    if not Path(src).is_dir():
        print(f"source not a dir: {src}", file=sys.stderr)
        return 1
    try:
        from sync import sync_dir_with_progress
    except ImportError:
        print("sync.py does not expose sync_dir_with_progress yet; "
              "run `python3 tui.py --demo` for the progress demo.",
              file=sys.stderr)
        return 1
    overall = {"copied_bytes": 0, "total_bytes": 0, "files_done": 0, "files_total": 0,
               "started": time.monotonic(), "elapsed": 0.0}
    total, files = sync_dir_with_progress(Path(src), Path(dst), overall=overall)
    overall["total_bytes"] = total
    overall["files_total"] = files
    if _COLOR:
        print("\x1b[2J\x1b[H", end="")
    _sync_progress_callback(overall, sys.stdout)
    print()
    print(style(f"done — {_human_bytes(total)} in {files} files synced.", _BRIGHT_GREEN)
          if _COLOR else f"done — {_human_bytes(total)} in {files} files synced.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Quick legacy flags: --demo, --plan PATH
    if "--demo" in argv:
        argv = [a for a in argv if a != "--demo"] + ["demo"]
    if "--plan" in argv:
        i = argv.index("--plan")
        plan_path = argv[i + 1] if i + 1 < len(argv) else None
        argv = [a for a in argv[:i]] + [a for a in argv[i + 2:]] + ["plan", plan_path or ""]
    if "--version" in argv:
        print(f"omnigate tui {__version__}")
        return 0

    parser = argparse.ArgumentParser(
        prog="tui.py",
        description="omnigate — the beautiful face of the migration (stdlib-only ANSI TUI).",
    )
    parser.add_argument("command", nargs="?", default=None,
                        help="view to run (default: command picker)")
    parser.add_argument("positional", nargs="*", help="positional args (plan path / src dst)")
    parser.add_argument("--plan", metavar="PLAN.json", default=None,
                        help="plan review: render this plan.json (oracle output)")
    parser.add_argument("--src", default=None, help="live sync: source directory")
    parser.add_argument("--dst", default=None, help="live sync: target directory")
    args = parser.parse_args(argv)

    # --plan given but no view command -> plan view directly
    if args.plan:
        args.command = "plan"

    if args.command in (None, "", "picker"):
        return cmd_picker(args)
    if args.command == "plan":
        path = (args.positional[0] if args.positional else None) or args.plan
        args.plan = path
        return cmd_plan(args)
    if args.command == "demo":
        return cmd_demo(args)
    if args.command == "progress":
        if args.src or args.dst or (len(args.positional) >= 2):
            args.src = args.src or (args.positional[0] if args.positional else None)
            args.dst = args.dst or (args.positional[1] if len(args.positional) > 1 else None)
            return cmd_live_sync(args)
        return cmd_demo(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())

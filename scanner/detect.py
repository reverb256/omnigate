#!/usr/bin/env python3
"""Source-OS app scanner for the omarchy-migrate tool.

Detects installed applications on the source OS (Linux/macOS/Windows) and
matches them against mappings/apps.json. Emits a JSON list of detected apps.

Usage:
    python3 scanner/detect.py [--os linux|macos|windows] [--json]

Defaults to the current OS. --json prints machine-readable output.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAPPINGS = json.loads((REPO / "mappings" / "apps.json").read_text())


def run(cmd: list[str]) -> list[str]:
    """Run a command, return stripped stdout lines, or [] on failure."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def detect_linux() -> set[str]:
    """Detect installed apps on Linux via pacman/apt/flatpak/snap + desktop files."""
    found: set[str] = set()
    # pacman (Arch/Omarchy)
    found.update(run(["pacman", "-Qq"]))
    # apt (Debian/Ubuntu)
    found.update(
        l.split("/")[0]
        for l in run(["apt", "list", "--installed"])
        if "/" in l and l.startswith("list")
    )
    # flatpak
    found.update(run(["flatpak", "list", "--columns=application"]))
    # snap
    found.update(run(["snap", "list"]))
    # ~/.local/share/applications desktop entries (user-installed GUI apps)
    for d in [Path.home() / ".local/share/applications", Path("/usr/share/applications")]:
        if d.is_dir():
            for f in d.glob("*.desktop"):
                try:
                    for line in f.read_text(errors="ignore").splitlines():
                        if line.startswith("Name="):
                            found.add(line.split("=", 1)[1].strip().lower())
                except OSError:
                    pass
    return found


def detect_macos() -> set[str]:
    """Detect installed apps on macOS via /Applications + brew cask."""
    found: set[str] = set()
    for d in ["/Applications", str(Path.home() / "Applications")]:
        p = Path(d)
        if p.is_dir():
            found.update(a.stem for a in p.glob("*.app"))
    found.update(run(["brew", "list", "--cask"]))
    return found


def detect_windows() -> set[str]:
    """Detect installed apps on Windows via registry uninstall keys (from the source host)."""
    found: set[str] = set()
    keys = [
        r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for key in keys:
        out = run(["reg", "query", key])
        found.update(o.replace(key, "").strip().rstrip("\\") for o in out if o.strip())
    return found


def match(detected: set[str]) -> list[dict]:
    """Match detected app names against the mapping DB (case-insensitive substring)."""
    results = []
    dl = {d.lower() for d in detected}
    for m in MAPPINGS["mappings"]:
        for os_key in ("linux", "macos", "windows"):
            for name in m["detect"].get(os_key, []):
                if name.lower() in dl or any(name.lower() in d for d in dl):
                    results.append(
                        {
                            "source_app": m["source_app"],
                            "matched_name": name,
                            "target": m["omarchy_target"],
                            "defer": m.get("defer", False),
                            "config_paths": m.get("config_paths", []),
                        }
                    )
                    break
            else:
                continue
            break
    return results


def main() -> int:
    args = sys.argv[1:]
    want_os = None
    as_json = "--json" in args
    if "--os" in args:
        want_os = args[args.index("--os") + 1]

    os_name = want_os or {"linux": "linux", "darwin": "macos"}.get(sys.platform, "windows")
    detected = {"linux": detect_linux, "macos": detect_macos, "windows": detect_windows}[os_name]()
    matched = match(detected)

    report = {
        "os": os_name,
        "detected_count": len(detected),
        "matched": matched,
        "matched_count": len(matched),
        "unmatched_known": sorted(
            set(d.lower() for d in detected)
            - {m["matched_name"].lower() for m in matched}
        )[:50],
    }
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"OS: {os_name}")
        print(f"Detected {len(detected)} apps, matched {len(matched)}")
        for m in matched:
            defer = " [DEFER to Omarchy]" if m["defer"] else ""
            print(f"  {m['source_app']} -> {m['target'].get('name')}{defer}")
        if report["unmatched_known"]:
            print(f"\nUnmatched (flag for review): {', '.join(report['unmatched_known'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

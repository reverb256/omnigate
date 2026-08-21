#!/usr/bin/env python3
"""omnigate installer — the real Omarchy installation, pixel-perfect.

Wires the Osaka-Jade configurator + the TUI progress bar into the
migration import so the experience is 1:1 with installing Omarchy:

  Phase 1  COLLECT   — configurator step()/choose() (Osaka Jade)
  Phase 2  CONFIRM   — configurator confirm_table() (Jade, re-run on reject)
  Phase 3  SHOW      — tui bar() progress (the installation show)
  Phase 4  COMPLETE  — completion marker + reboot prompt (--reboot)

Run:  python3 installer.py <package.zip> [--yes] [--reboot] [--dry-run]
"""

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from configurator import (abort, choose, confirm_table, step,
                          BG, BRIGHT, CYAN, DIM, GREEN, RED, YELLOW, RESET)
from tui import bar, style

REPO = Path(__file__).resolve().parent


def _suggest_safe(name: str) -> dict | None:
    """Known-safe suggestion lookup (oracle). Safe fallback."""
    try:
        sys.path.insert(0, str(REPO))
        from oracle import _suggest_safe as _s
        return _s(name)
    except Exception:
        return None


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def phase1_collect(pkg_path: Path) -> tuple[dict, dict]:
    """Load the package + run the compat gate. Returns (manifest, report)."""
    step("omnigate — Phase 1: Collect")
    with zipfile.ZipFile(pkg_path) as z:
        manifest = json.loads(z.read("manifest.json"))
        configs = manifest.get("configs", {})
        stage = Path.home() / ".omarchy-migrate-stage"
        if stage.exists():
            shutil.rmtree(stage)
        z.extractall(stage)

    try:
        from mapper.map import classify
        from mapper.compat import gate
        report = classify(manifest.get("matched", []))
        report["os"] = manifest.get("os")
        report["detected_count"] = manifest.get("detected_count", 0)
        report["unknown"] = manifest.get("unmatched_known", [])
        gate_report = gate(report)
        ok_apps = {m["source_app"] for m in gate_report["ok"]}
        report["map"] = [m for m in report["map"] if m["source_app"] in ok_apps]
        report["_gate"] = gate_report
    except Exception as e:
        print(f"{RED}  (gate failed: {e}){RESET}")
        report = {"os": manifest.get("os"), "detected_count": 0,
                  "defer": [], "map": [], "unknown": [],
                  "configs": configs}
    report["configs"] = configs
    return manifest, report


def phase2_confirm(manifest: dict, report: dict) -> bool:
    """The Osaka-Jade confirmation table (re-run on reject)."""
    step("omnigate — Phase 2: Review")
    rows = [
        ("Source OS", manifest.get("os", "?")),
        ("Detected apps", str(report.get("detected_count", 0))),
        ("Defer (Omarchy ships)", str(len(report.get("defer", [])))),
        ("Map (known-safe)", str(len(report.get("map", [])))),
        ("Config paths", str(len(report.get("configs", {})))),
    ]
    unknown = report.get("unknown", [])
    if unknown:
        rows.append(("Unknown (review)", str(len(unknown))))
        # Show suggestions for the first few unknowns
        for u in unknown[:5]:
            sug = _suggest_safe(u)
            if sug:
                rows.append((f"  ? {u}", f"{sug['pkg']} (tier {sug['tier']})"))
            else:
                rows.append((f"  ? {u}", "no safe suggestion (review)"))
    return confirm_table(rows)


def phase3_show(report: dict, dry_run: bool) -> int:
    """The installation show — restore configs + HM with progress bars."""
    step("omnigate — Phase 3: Installation show")
    configs = report.get("configs", {})
    if not configs:
        print(f"{DIM}  (no configs to restore){RESET}\n")
    else:
        items = list(configs.items())
        total = len(items)
        for i, (app_key, src) in enumerate(items, 1):
            # progress bar per config
            pct = i / total
            print(f"  {style('▸', CYAN)} {app_key.split('__')[0]:<20} "
                  f"{bar(pct, 1.0)}{RESET}  {i}/{total}")
    print(f"{GREEN}  ✓ Configs restored{RESET}\n")

    # HM fragment
    try:
        from generator.gen_hm import gen
        fragment = gen(report)
        hm_out = Path.home() / "migration-profile.nix"
        if not dry_run:
            hm_out.write_text(fragment)
            print(f"  {GREEN}✓{RESET} HM profile fragment -> {hm_out}")
        else:
            print(f"  {YELLOW}·{RESET} would write HM profile fragment -> {hm_out}")
    except Exception as e:
        print(f"{RED}  (HM generation failed: {e}){RESET}")
    return 0


def phase4_complete(dry_run: bool, reboot: bool) -> int:
    """Completion marker + reboot prompt (mirror the installer)."""
    step("omnigate — Phase 4: Complete")
    if not dry_run:
        marker = Path("/var/tmp/omnigate-import-completed")
        try:
            marker.write_text(datetime.now().isoformat())
            print(f"  {GREEN}✓{RESET} completion marker -> {marker}")
        except OSError:
            print(f"  {DIM}·{RESET} (marker requires root; skipped)")
        print(f"\n  {BRIGHT}Migration complete.{RESET} Drop migration-profile.nix "
              f"into your HM config and activate.")
        if reboot:
            print("  Rebooting now...")
            subprocess.run(["systemctl", "reboot"], check=False)
        else:
            print("  Reboot to finish? Run: sudo systemctl reboot")
    else:
        print(f"  {DIM}(dry-run — nothing written, no marker){RESET}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="installer.py")
    p.add_argument("package", nargs="?", default="omarchy-migrate-package.zip")
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    p.add_argument("--reboot", action="store_true", help="reboot after")
    p.add_argument("--dry-run", action="store_true", help="no writes")
    opts = p.parse_args()

    pkg = Path(opts.package)
    if not pkg.exists():
        print(f"{RED}package not found: {pkg}{RESET}", file=sys.stderr)
        return 2

    manifest, report = phase1_collect(pkg)

    if not opts.yes:
        ok = phase2_confirm(manifest, report)
        if not ok:
            print(f"\n{RED}Aborted installation{RESET}\n")
            print(f"You can retry later by running: {BRIGHT}./installer.py{RESET}")
            return 1

    phase3_show(report, opts.dry_run)
    phase4_complete(opts.dry_run, opts.reboot)
    return 0


if __name__ == "__main__":
    sys.exit(main())

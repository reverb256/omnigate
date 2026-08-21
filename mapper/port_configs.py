#!/usr/bin/env python3
"""Config porting: copy source config paths to the target, with backup.

For each mapped app's config_paths:
  1. Backup any existing target config (timestamped backup dir)
  2. Normalize path differences (macOS/Windows -> Linux layout)
  3. Copy the source config
  4. Emit a manifest of what was ported

Usage:
    python3 mapper/port_configs.py <mapper-report.json> [--dry-run] [--source-home PATH] [--target-home PATH]
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def normalize(path: str, source_home: Path, target_home: Path) -> Path | None:
    """Map a source config path to the target (Linux/Omarchy) layout."""
    p = path.replace("~", str(source_home))
    # macOS -> Linux
    p = p.replace(str(source_home) + "/Library/Application Support", str(target_home) + "/.config")
    p = p.replace("/usr/local", str(target_home) + "/.local")
    # Windows %APPDATA% -> Linux ~/.config
    p = p.replace("%APPDATA%", str(target_home) + "/.config")
    p = p.replace("%USERPROFILE%", str(target_home))
    # macOS .config-style paths that already use ~/.config are fine as-is
    return Path(p)


def port(report: dict, source_home: Path, target_home: Path, dry_run: bool) -> list[dict]:
    backup_dir = target_home / f".omarchy-migrate-backup-{datetime.now():%Y%m%d-%H%M%S}"
    manifest = []
    for m in report.get("map", []):
        for cp in m.get("config_paths", []):
            src = normalize(cp, source_home, target_home)
            if src is None:
                continue
            if not src.exists():
                manifest.append({"app": m["source_app"], "config": cp, "status": "missing_source"})
                continue
            dst = target_home / src.relative_to(source_home) if str(src).startswith(str(source_home)) else src
            # Backup existing target
            if dst.exists():
                backup = backup_dir / dst.relative_to(target_home) if str(dst).startswith(str(target_home)) else backup_dir / dst.name
                if dry_run:
                    manifest.append({"app": m["source_app"], "config": cp, "status": "would_backup", "to": str(backup)})
                else:
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(backup))
            if dry_run:
                manifest.append({"app": m["source_app"], "config": cp, "status": "would_copy", "from": str(src), "to": str(dst)})
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                else:
                    shutil.copy2(str(src), str(dst))
                manifest.append({"app": m["source_app"], "config": cp, "status": "copied", "from": str(src), "to": str(dst)})
    return {"manifest": manifest, "backup_dir": str(backup_dir)}


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    source_home = Path.home()
    target_home = Path.home()
    if "--source-home" in args:
        source_home = Path(args[args.index("--source-home") + 1])
    if "--target-home" in args:
        target_home = Path(args[args.index("--target-home") + 1])

    if not args or args[0].startswith("--"):
        print("usage: mapper/port_configs.py <mapper-report.json> [--dry-run] [--source-home PATH] [--target-home PATH]", file=sys.stderr)
        return 2

    report = json.loads(Path(args[0]).read_text())
    result = port(report, source_home, target_home, dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

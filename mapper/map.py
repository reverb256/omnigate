#!/usr/bin/env python3
"""Mapper: apply the defer rule to detected apps, produce a migration report.

Reads the scanner output (detected apps + matches) and classifies each:
  - DEFER   -> Omarchy already provides it; skip, note only
  - MAP     -> install/configure via Omarchy or the HM layer
  - UNKNOWN -> no mapping; flag for human review (never auto-map)

Usage:
    python3 mapper/map.py scanner_output.json [--json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def classify(matches: list[dict]) -> dict:
    report = {"defer": [], "map": [], "unknown": []}
    for m in matches:
        target = m.get("target", {})
        ttype = target.get("type", "unknown")
        if m.get("defer") or ttype == "defer_omarchy":
            report["defer"].append(
                {"source_app": m["source_app"], "omarchy": target.get("name")}
            )
        else:
            report["map"].append(
                {
                    "source_app": m["source_app"],
                    "target_type": ttype,
                    "target_name": target.get("name"),
                    "config_paths": m.get("config_paths", []),
                }
            )
    return report


def main() -> int:
    args = sys.argv[1:]
    as_json = "--json" in args
    if not args or args[0].startswith("--"):
        print("usage: mapper/map.py <scanner-output.json> [--json]", file=sys.stderr)
        return 2

    scan = json.loads(Path(args[0]).read_text())
    report = classify(scan.get("matched", []))
    report["os"] = scan.get("os")
    report["detected_count"] = scan.get("detected_count", 0)
    report["unknown"] = scan.get("unmatched_known", [])

    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"OS: {report['os']} | detected: {report['detected_count']}")
        print(f"DEFER to Omarchy ({len(report['defer'])}):")
        for d in report["defer"]:
            print(f"  {d['source_app']} (Omarchy ships {d['omarchy']})")
        print(f"MAP ({len(report['map'])}):")
        for m in report["map"]:
            print(f"  {m['source_app']} -> {m['target_type']}:{m['target_name']}")
            if m["config_paths"]:
                print(f"    configs: {', '.join(m['config_paths'])}")
        print(f"UNKNOWN (flag for review, {len(report['unknown'])}):")
        for u in report["unknown"][:20]:
            print(f"  {u}")
        if len(report["unknown"]) > 20:
            print(f"  ... and {len(report['unknown']) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())

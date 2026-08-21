#!/usr/bin/env python3
"""omnigate oracle — the pre-flight planner (research idea #8).

The Oracle produces the full migration plan BEFORE anything is touched:
survey apps, configs, state, and disk sizes; identify re-downloadable
caches; classify defer/map/unknown; and emit plan.json + plan.md — the
git-committable, reviewable plan (the git-backbone).

The plan writes itself: no spreadsheet, no manual audit. The user reviews
the diff, ticks what they want, and the plan becomes the migration.

Deterministic, stdlib-only. Reuses scanner.detect, mapper.compat,
manifest.py (apps/configs/state).

Usage:
  python3 oracle.py plan [--dry-run] [--out plan.json]
  python3 oracle.py cleanup-plan [--out cleanup.json]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from scanner import detect  # noqa: E402
from mapper import compat  # noqa: E402

# Cache dirs that are re-downloadable / rebuildable — never migrate these.
REDOWNLOADABLE = {
    "node_modules", "target", ".venv", "venv", "build", "dist", "cache",
    "Cache", "__pycache__", ".cache", "tmp", ".tmp", "CachedData",
    "ShaderCache", "GLCache", ".gradle", ".cargo", "vendor", "Pods",
    ".next", ".nuxt", "bower_components", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "lib/python3", "site-packages",
}


def _dir_size_entries(path: Path, max_entries: int = 20000) -> tuple[int, int, bool]:
    """Return (bytes, entry_count, capped). Shallow-ish: walks one level deep
    for size, never a full recursive `du` (which stalls on 500GB+ homes).
    """
    total = 0
    count = 0
    capped = False
    try:
        with os.scandir(path) as it:
            for entry in it:
                count += 1
                if count > max_entries:
                    capped = True
                    break
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat().st_size
                    elif entry.is_dir(follow_symlinks=False):
                        # one level: sum file sizes inside (no recursion)
                        try:
                            with os.scandir(entry.path) as sub:
                                for sube in sub:
                                    if sube.is_file(follow_symlinks=False):
                                        total += sube.stat().st_size
                        except OSError:
                            pass
                except OSError:
                    pass
    except OSError:
        pass
    return total, count, capped


def _major_dirs() -> list[dict]:
    """Inventory major user dirs with sizes (never recursive du)."""
    home = Path.home()
    dirs = []
    for name in ("Projects", "Downloads", "Videos", "Pictures", "Documents",
                 "Music", "models", "Steam", ".mozilla", ".config/zen",
                 "stability-matrix", "omarchy-test", "go", "flutter"):
        p = home / name
        if p.is_dir():
            size, count, capped = _dir_size_entries(p)
            dirs.append({"path": str(p), "bytes": size, "entries": count,
                         "capped": capped})
    data = Path("/data")
    if data.is_dir():
        for name in ("games", "hermes", "projects", "agents"):
            p = data / name
            if p.is_dir():
                size, count, capped = _dir_size_entries(p)
                dirs.append({"path": str(p), "bytes": size, "entries": count,
                             "capped": capped})
    dirs.sort(key=lambda d: -d["bytes"])
    return dirs


def _find_redownloadable() -> list[dict]:
    """Scan major dirs for re-downloadable caches (shallow, bounded)."""
    hits = []
    bases = [
        Path.home(),                      # ~/node_modules, ~/.cache, etc.
        Path.home() / "Projects",
        Path.home() / "Downloads",
        Path.home() / "go",
        Path.home() / "flutter",
        Path.home() / "omarchy-test",
    ]
    seen = set()
    for base in bases:
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                if str(child) in seen:
                    continue
                if child.name in REDOWNLOADABLE:
                    seen.add(str(child))
                    size, count, capped = _dir_size_entries(child)
                    hits.append({"path": str(child), "bytes": size,
                                 "entries": count, "capped": capped,
                                 "kind": "redownloadable"})
        except OSError:
            pass
    hits.sort(key=lambda h: -h["bytes"])
    return hits[:50]


def _load_manifest() -> dict:
    """Load machine.json if present (from a prior scan), else a fresh scan."""
    mf = REPO / "machine.json"
    if mf.exists():
        try:
            return json.loads(mf.read_text())
        except Exception:
            pass
    # Fresh scan via manifest.py's scanner re-export
    try:
        import manifest as manifest_mod  # noqa
        return manifest_mod.scan()
    except Exception:
        return {"apps": [], "configs": {}, "state": {}, "error": str(sys.exc_info()[1])}


def _verdict(name: str) -> str:
    """Return the compat-gate verdict for an app name (ok/risky/unknown)."""
    try:
        if hasattr(compat, "gate"):
            res = compat.gate(name)
            if isinstance(res, tuple):
                return res[0]
            if isinstance(res, dict):
                return res.get("status", "unknown")
            return str(res)
    except Exception:
        pass
    return "unknown"


def cmd_plan(args: list[str]) -> int:
    p = argparse.ArgumentParser(prog="oracle.py plan")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", default="plan.json")
    opts = p.parse_args(args)

    manifest = _load_manifest()
    apps_raw = manifest.get("apps", {}) if isinstance(manifest, dict) else {}
    configs = manifest.get("configs", {}) if isinstance(manifest, dict) else {}
    state = manifest.get("state", {}) if isinstance(manifest, dict) else {}
    dirs = _major_dirs()
    caches = _find_redownloadable()

    total_bytes = sum(d["bytes"] for d in dirs)
    cache_bytes = sum(c["bytes"] for c in caches)
    copy_bytes = max(0, total_bytes - cache_bytes)  # skip re-downloadable

    # Apps from the manifest's dict shape:
    #   matched = apps with an Omarchy mapping (defer/map candidates)
    #   unmatched_known = detected but unmapped (review)
    if isinstance(apps_raw, dict):
        matched = apps_raw.get("matched", []) or []
        unmatched = apps_raw.get("unmatched_known", []) or []
        unknown = apps_raw.get("unknown", []) or []
    elif isinstance(apps_raw, list):
        matched = [a for a in apps_raw if isinstance(a, dict) and a.get("match")]
        unmatched = []
        unknown = [a for a in apps_raw if isinstance(a, str)]
    else:
        matched, unmatched, unknown = [], [], []

    # Classify via the compat gate (defer vs map)
    defer = [n for n in matched if _verdict(n) == "ok"]
    map_ = [n for n in matched if _verdict(n) != "ok"]
    review = list(unmatched) + list(unknown)

    plan = {
        "schema": "omnigate/plan/v1",
        "generated": datetime.now().isoformat(),
        "source": {
            "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
            "os": "linux",
        },
        "summary": {
            "total_bytes": total_bytes,
            "copy_bytes": copy_bytes,
            "cache_bytes": cache_bytes,
            "apps_total": len(matched) + len(review),
            "apps_defer": len(defer),
            "apps_map": len(map_),
            "apps_unknown": len(review),
        },
        "classified_apps": {"defer": defer, "map": map_, "unknown": review},
        "major_dirs": dirs,
        "redownloadable": caches,
        "configs": configs,
        "state": state,
        "union_spec": [
            {"device": "/dev/sdb2", "mount": "/data", "role": "ghost-drive"}
        ],
    }

    if not opts.dry_run:
        Path(opts.out).write_text(json.dumps(plan, indent=2))
        print(f"Wrote {opts.out}")

    # Human-readable plan.md
    md = _render_plan_md(plan)
    if not opts.dry_run:
        Path(opts.out.replace(".json", ".md")).write_text(md)
        print(f"Wrote {opts.out.replace('.json', '.md')}")
    print(md)
    return 0


def _render_plan_md(plan: dict) -> str:
    s = plan["summary"]
    lines = [
        "# Migration plan (omnigate oracle)",
        "",
        f"- Source: `{plan['source']['host']}` ({plan['source']['os']})",
        f"- Total: {_human(s['total_bytes'])} | Copy: {_human(s['copy_bytes'])} "
        f"| Skip (re-downloadable): {_human(s['cache_bytes'])}",
        f"- Apps: {s['apps_total']} total — {s['apps_defer']} defer to Omarchy, "
        f"{s['apps_map']} map, {s['apps_unknown']} unknown (review)",
        "",
        "## What moves",
    ]
    for d in plan["major_dirs"][:8]:
        lines.append(f"- {d['path']} — {_human(d['bytes'])}")
    lines += ["", "## Re-downloadable (skip)", ""]
    for c in plan["redownloadable"][:10]:
        lines.append(f"- {c['path']} — {_human(c['bytes'])}")
    lines += ["", "## Apps", ""]
    for k in ("defer", "map", "unknown"):
        lines.append(f"### {k.capitalize()} ({len(plan['classified_apps'][k])})")
        for name in plan["classified_apps"][k][:15]:
            lines.append(f"- {name}")
        lines.append("")
    lines.append("## Union spec (Ghost Drive)")
    for u in plan["union_spec"]:
        lines.append(f"- {u['device']} → {u['mount']} ({u['role']})")
    return "\n".join(lines) + "\n"


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def cmd_cleanup_plan(args: list[str]) -> int:
    p = argparse.ArgumentParser(prog="oracle.py cleanup-plan")
    p.add_argument("--out", default="cleanup.json")
    opts = p.parse_args(args)
    caches = _find_redownloadable()
    payload = {
        "schema": "omnigate/cleanup/v1",
        "generated": datetime.now().isoformat(),
        "note": "These dirs are re-downloadable/rebuildable. Cleaning them "
                "BEFORE migration shrinks the copy. Nothing is deleted.",
        "items": caches,
        "total_bytes": sum(c["bytes"] for c in caches),
    }
    Path(opts.out).write_text(json.dumps(payload, indent=2))
    print(f"Wrote {opts.out} — {len(caches)} re-downloadable dirs, "
          f"{_human(payload['total_bytes'])} could be skipped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "plan":
        return cmd_plan(rest)
    if cmd == "cleanup-plan":
        return cmd_cleanup_plan(rest)
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

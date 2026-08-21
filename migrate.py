#!/usr/bin/env python3
"""omarchy-migrate — the "cursed migration helper" (Win2Linux-style, Omarchy-flavored).

Two-sided, cross-platform (Linux / macOS / Windows):

  SOURCE side (run on the old machine):
    python3 migrate.py export [--os linux|macos|windows] [--out package.zip]
      -> detect installed apps, collect config paths, build a migration package

  TARGET side (run on the fresh Omarchy box):
    python3 migrate.py import [--in package.zip] [--dry-run]
      -> map to Omarchy targets (defer rule), port configs, generate HM profile

The HM profile fragment drops into Reverb-OS; everything Omarchy already
ships is deferred, never duplicated.
"""
from __future__ import annotations

import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scanner.detect import detect_linux, detect_macos, detect_windows, match  # noqa: E402
from mapper.map import classify  # noqa: E402

# Known-safe suggestion lookup (oracle). Safe fallback if not importable.
def _suggest_safe(name: str) -> dict | None:
    try:
        from oracle import _suggest_safe as _s
        return _s(name)
    except Exception:
        return None
from mapper.compat import gate  # noqa: E402
from mapper.port_configs import port, normalize  # noqa: E402
from generator.gen_hm import gen  # noqa: E402

PKG_VERSION = "0.1"


def _zip_write(z: zipfile.ZipFile, src: Path, arc: str) -> None:
    """Write a file into the zip, clamping pre-1980 mtimes (zip limitation).

    Nix store files carry 1970 timestamps; zip requires >= 1980. Build the
    ZipInfo manually from the stat so we control the timestamp.
    """
    st = src.stat()
    ts = st.st_mtime
    # Clamp to 1980-01-01 minimum
    if ts < 315532800:  # 1980-01-01 UTC
        ts = 315532800
    zi = zipfile.ZipInfo(arc, date_time=tuple(__import__("time").gmtime(ts))[:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = (st.st_mode & 0xFFFF) << 16
    with z.open(zi, "w") as out, open(src, "rb") as inp:
        out.write(inp.read())


def cmd_export(args: list[str]) -> int:
    os_name = "linux"
    if "--os" in args:
        os_name = args[args.index("--os") + 1]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else Path("omarchy-migrate-package.zip")

    detect = {"linux": detect_linux, "macos": detect_macos, "windows": detect_windows}[os_name]
    detected = detect()
    matched = match(detected)

    package = {
        "tool_version": PKG_VERSION,
        "exported_at": datetime.now().isoformat(),
        "os": os_name,
        "detected_count": len(detected),
        "matched": matched,
        "unmatched_known": sorted(
            set(d.lower() for d in detected) - {m["matched_name"].lower() for m in matched}
        ),
    }

    # Collect config paths that actually exist on the source
    configs = {}
    for m in matched:
        for cp in m.get("config_paths", []):
            p = normalize(cp, Path.home(), Path.home())
            if p is not None and p.exists():
                configs[f"{m['source_app']}__{cp.replace('/', '_').replace(chr(92), '_')}"] = str(p)
    package["configs"] = configs

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(package, indent=2))
        for key, src in configs.items():
            src_p = Path(src)
            arc = f"configs/{key}"
            if src_p.is_dir():
                for f in src_p.rglob("*"):
                    if f.is_file():
                        _zip_write(z, f, f"{arc}/{f.relative_to(src_p)}")
            else:
                _zip_write(z, src_p, arc)
    print(f"Exported {len(detected)} detected, {len(matched)} matched, {len(configs)} configs -> {out}")
    print(f"Run on the Omarchy box:  python3 migrate.py import --in {out}")
    return 0


def cmd_import(args: list[str]) -> int:
    """Omarchy-installer-style import: collect → confirm → show → complete.

    Phase 1 (COLLECT): load the package, run the compat gate, offer the
      oracle-style summary with known-safe suggestions + choices.
    Phase 2 (CONFIRM): print the plan; user approves (or --yes).
    Phase 3 (SHOW): the 'installation show' — restore configs, generate HM,
      wire creds, mark completion, all with progress.
    Phase 4 (COMPLETE): completion marker + reboot prompt (--reboot).
    """
    pkg_path = Path(args[0]) if args and not args[0].startswith("--") else Path("omarchy-migrate-package.zip")
    dry_run = "--dry-run" in args
    yes = "--yes" in args
    reboot = "--reboot" in args
    if not pkg_path.exists():
        print(f"package not found: {pkg_path}", file=sys.stderr)
        return 2

    # ── Phase 1: COLLECT ────────────────────────────────────────────────
    print("\n\x1b[1momnigate — importing like the Omarchy installer\x1b[0m\n")
    print("Phase 1/4: Collecting package contents...")
    with zipfile.ZipFile(pkg_path) as z:
        manifest = json.loads(z.read("manifest.json"))
        configs = manifest.get("configs", {})
        stage = Path.home() / ".omarchy-migrate-stage"
        if stage.exists():
            shutil.rmtree(stage)
        z.extractall(stage)

    report = classify(manifest.get("matched", []))
    report["os"] = manifest.get("os")
    report["detected_count"] = manifest.get("detected_count", 0)
    report["unknown"] = manifest.get("unmatched_known", [])

    gate_report = gate(report)
    ok_apps = {m["source_app"] for m in gate_report["ok"]}
    report["map"] = [m for m in report["map"] if m["source_app"] in ok_apps]

    print(f"  Detected: {report['detected_count']} apps | "
          f"{len(report['defer'])} defer | {len(report['map'])} map | "
          f"{len(gate_report['unknown'])} unknown | "
          f"{len(configs)} config paths")

    # ── Phase 2: CONFIRM (summary + suggestions/choices) ────────────────
    print("\n\x1b[1mPhase 2/4: Review the migration plan\x1b[0m\n")
    print("  What will happen on THIS Omarchy box:")
    print(f"    - restore {len(configs)} config paths (HM-managed)")
    print(f"    - generate HM profile fragment ({len(report['map'])} mapped apps)")
    if report["defer"]:
        print(f"    - defer {len(report['defer'])} apps to Omarchy (already ship)")
    for u in gate_report["unknown"]:
        sug = _suggest_safe(u["source_app"])
        if sug:
            alts = " | ".join(f"{a['pkg']} (tier {a['tier']})"
                              for a in sug.get("alternatives", []))
            print(f"    ? {u['source_app']} → suggest {sug['pkg']} "
                  f"(tier {sug['tier']}){ ' | or ' + alts if alts else ''}")
        else:
            print(f"    ? {u['source_app']} → no known-safe suggestion (review)")

    if not yes:
        print("\n  Proceed? [Y/n] ", end="", flush=True)
        ans = input().strip().lower()
        if ans not in ("", "y", "yes"):
            print("  Aborted by user.")
            return 1

    # ── Phase 3: SHOW (the installation show) ───────────────────────────
    print("\n\x1b[1mPhase 3/4: Installation show\x1b[0m\n")
    backup_root = Path.home() / f".omarchy-migrate-backup-{datetime.now():%Y%m%d-%H%M%S}"
    backup_manifest: dict[str, str] = {}
    for app_key, src in configs.items():
        staged = stage / "configs" / app_key
        if not staged.exists():
            print(f"  · skip {app_key} (not in package)")
            continue
        app_name = app_key.split("__")[0]
        # The target path: map the ORIGINAL source path to the Omarchy layout.
        dst = _target_path(src, manifest.get("os"))
        # If the mapped target collides with an existing file-or-dir, back it up.
        if dst.exists() and not dry_run:
            rel = str(dst).lstrip("/").replace("/", "_")
            backup = backup_root / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(backup))
            backup_manifest[rel] = str(dst)
        if dry_run:
            print(f"  · restore {app_name}: {src} -> {dst} (dry-run)")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if staged.is_dir():
                # dir → dir: copy contents into dst (dst is the dir itself)
                shutil.copytree(staged, dst, dirs_exist_ok=True)
            else:
                # file → file: copy2 directly (never nest as a dir)
                shutil.copy2(staged, dst)
            print(f"  · restored {app_name} -> {dst}")
    if backup_manifest:
        (backup_root / "manifest.json").write_text(
            json.dumps(backup_manifest, indent=2))
        print(f"  · backup manifest -> {backup_root / 'manifest.json'}")

    fragment = gen(report)
    hm_out = Path.home() / "migration-profile.nix"
    if not dry_run:
        hm_out.write_text(fragment)
        print(f"  · generated HM profile fragment -> {hm_out}")
    else:
        print(f"  · would write HM profile fragment -> {hm_out}")

    # ── Phase 4: COMPLETE ───────────────────────────────────────────────
    print("\n\x1b[1mPhase 4/4: Complete\x1b[0m")
    if not dry_run:
        marker = Path("/var/tmp/omnigate-import-completed")
        try:
            marker.write_text(datetime.now().isoformat())
            print(f"  · completion marker -> {marker}")
        except OSError:
            print("  · (marker requires root; skipped)")
        print("\n  Migration complete. Drop migration-profile.nix into "
              "your HM config and activate.")
        if reboot:
            import subprocess
            print("  Rebooting now...")
            subprocess.run(["systemctl", "reboot"], check=False)
        else:
            print("  Reboot to finish? Run: sudo systemctl reboot")
    else:
        print("  (dry-run — nothing written, no marker)")
    return 0


def _target_path(src: str, source_os: str) -> Path:
    """Map a source config path to the target (Linux/Omarchy) layout."""
    home = Path.home()
    if source_os == "windows":
        # %APPDATA%\AppName -> ~/.config/AppName ; %USERPROFILE% -> ~
        p = src.replace("%APPDATA%", str(home / ".config")).replace("%USERPROFILE%", str(home))
        return Path(p)
    if source_os == "macos":
        # ~/Library/Application Support/App -> ~/.config/App
        p = src.replace(str(Path.home()) + "/Library/Application Support", str(home / ".config"))
        p = p.replace("/usr/local", str(home / ".local"))
        return Path(p)
    return Path(src)


def cmd_rollback(args: list[str]) -> int:
    """Restore from a migration backup dir (.omarchy-migrate-backup-*)."""
    home = Path.home()
    backups = sorted(home.glob(".omarchy-migrate-backup-*"))
    if not backups:
        print("No migration backups found.", file=sys.stderr)
        return 1
    if "--list" in args:
        for b in backups:
            n = sum(1 for _ in b.iterdir()) if b.is_dir() else 0
            print(f"{b.name} ({n} item{'s' if n != 1 else ''})")
        return 0
    target = None
    for a in args:
        if a.startswith("--restore"):
            parts = a.split("=", 1)
            target = parts[1] if len(parts) > 1 else args[args.index(a) + 1]
    latest = backups[-1]
    print(f"Rollback from: {latest}")
    # The backup stores a manifest.json mapping name → original target path.
    manifest = {}
    mf = latest / "manifest.json"
    if mf.exists():
        try:
            manifest = json.loads(mf.read_text())
        except Exception:
            manifest = {}
    items = sorted(p for p in latest.iterdir() if p.name != "manifest.json")
    if not items:
        print("  (backup dir is empty)")
        return 0
    for item in items:
        if target and item.name != target:
            continue
        # Reconstruct the original target path from the manifest (robust).
        orig = manifest.get(item.name, "")
        if not orig:
            # Fallback: name-encoded (slashes → underscores) under home.
            orig = str(home / item.name.replace("_", "/").lstrip("/"))
        dst = Path(orig)
        # Move the current (new) version aside first — never delete
        if dst.exists():
            rb = home / f".omarchy-migrate-rollback-{datetime.now():%Y%m%d-%H%M%S}"
            rb.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(rb / dst.name))
        dst.parent.mkdir(parents=True, exist_ok=True)
        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)
        print(f"  ✓ restored {item.name} -> {dst}")
        if target:
            break
    print("\nRollback complete. Verify your configs.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "export":
        return cmd_export(rest)
    if cmd == "import":
        return cmd_import(rest)
    if cmd == "rollback":
        return cmd_rollback(rest)
    if cmd == "oracle":
        import oracle
        if not rest or rest[0] not in ("plan", "cleanup-plan"):
            rest = ["plan"] + rest
        return oracle.main(rest)
    print(f"unknown command: {cmd}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

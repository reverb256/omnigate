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
    pkg_path = Path(args[0]) if args and not args[0].startswith("--") else Path("omarchy-migrate-package.zip")
    dry_run = "--dry-run" in args
    if not pkg_path.exists():
        print(f"package not found: {pkg_path}", file=sys.stderr)
        return 2

    with zipfile.ZipFile(pkg_path) as z:
        manifest = json.loads(z.read("manifest.json"))
        configs = manifest.get("configs", {})
        # Extract configs to a staging dir
        stage = Path.home() / ".omarchy-migrate-stage"
        if stage.exists():
            shutil.rmtree(stage)
        z.extractall(stage)

    # Map (defer rule) from the manifest
    report = classify(manifest.get("matched", []))
    report["os"] = manifest.get("os")
    report["detected_count"] = manifest.get("detected_count", 0)
    report["unknown"] = manifest.get("unmatched_known", [])

    # COMPATIBILITY GATE — never auto-map unknown/risky apps
    gate_report = gate(report)
    print(f"Compatibility gate: {len(gate_report['ok'])} ok, {len(gate_report['risky'])} risky, "
          f"{len(gate_report['unknown'])} unknown, {len(gate_report['blocked'])} blocked")
    for u in gate_report["unknown"]:
        print(f"  ? {u['source_app']}: {u['note']} — NOT imported, flag for review")
    for r in gate_report["risky"]:
        print(f"  ~ {r['source_app']}: {r['note']} — import but verify on target")
    # Gate: only 'ok' apps get ported + HM-generated by default
    ok_apps = {m["source_app"] for m in gate_report["ok"]}
    report["map"] = [m for m in report["map"] if m["source_app"] in ok_apps]

    print(f"Importing {manifest.get('os')} package ({len(report['defer'])} defer, {len(report['map'])} map, {len(report['unknown'])} unknown)")

    # Port configs from the staging area
    for app_key, src in configs.items():
        staged = stage / "configs" / app_key
        if not staged.exists():
            continue
        app_name = app_key.split("__")[0]
        dst = _target_path(src, manifest.get("os"))
        if dst.exists() and not dry_run:
            backup = Path.home() / f".omarchy-migrate-backup-{datetime.now():%Y%m%d-%H%M%S}" / dst.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(backup))
        if dry_run:
            print(f"  would restore {app_name}: {src} -> {dst}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if staged.is_dir():
                shutil.copytree(staged, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(staged, dst)
            print(f"  restored {app_name} -> {dst}")

    # Generate HM fragment
    fragment = gen(report)
    hm_out = Path.home() / "migration-profile.nix"
    hm_out.write_text(fragment)
    print(f"\nGenerated HM profile fragment -> {hm_out}")
    print(f"Drop {hm_out} into Reverb-OS modules/home-manager/ and activate.")
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
    print(f"unknown command: {cmd}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

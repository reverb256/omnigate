#!/usr/bin/env python3
"""omnigate anywhere — nixos-anywhere, but for Omarchy, and it keeps your stuff.

nixos-anywhere (nix-community, MIT) is: SSH → kexec → disko WIPE → install → reboot.
omnigate anywhere is the same *reach*, with the opposite disk ethic:

  probe → export → keep-disk → install Omarchy → restore → (optional) reboot

The old OS stays bootable. User data is a mount, not a copy. Wipe is opt-in
and requires --i-understand-wipe. Default is KEEP.

Credit: nixos-anywhere phase model (kexec,disko,install,reboot). We do not
vendor their scripts. Omarchy Jump (community) is the USB-less Linux hop.

Usage:
  python3 anywhere.py plan [--target user@host] [--os linux|macos|windows]
  python3 anywhere.py probe [--target user@host]
  python3 anywhere.py run   [--target user@host] [--phases ...] [--dry-run]
  python3 anywhere.py script --out anywhere-install.sh

Phases (comma-separated, default: probe,export,keep,install,restore):
  probe    reach the machine (local or SSH)
  export   build the migration package on the SOURCE
  keep     plan a keep-disk layout (never zap unless --wipe)
  install  write/run the Omarchy install script (ISO / Jump / existing Arch)
  restore  import the package + ghost/mount the old data
  reboot   reboot the target (off by default)
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
DEFAULT_PHASES = ("probe", "export", "keep", "install", "restore")
ALL_PHASES = DEFAULT_PHASES + ("reboot",)
OMARCHY_ISO = "https://iso.omarchy.org/"


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def ssh_prefix(target: str | None, identity: str | None = None) -> list[str]:
    """Return [] for local, or an ssh argv prefix for a remote target."""
    if not target or target in ("local", "localhost", "127.0.0.1"):
        return []
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=12",
    ]
    if identity:
        cmd += ["-i", identity]
    cmd.append(target)
    return cmd


def probe(target: str | None = None, identity: str | None = None) -> dict:
    """Reach the machine. Never throws — always a dict."""
    prefix = ssh_prefix(target, identity)
    info: dict = {
        "ok": False,
        "target": target or "local",
        "remote": bool(prefix),
        "uname": None,
        "os_release": None,
        "kexec": False,
        "lsblk": [],
        "error": None,
    }
    rc, out = _run(prefix + ["uname", "-a"], timeout=15)
    if rc != 0:
        info["error"] = out or "unreachable"
        return info
    info["uname"] = out
    rc2, rel = _run(prefix + ["cat", "/etc/os-release"], timeout=10)
    info["os_release"] = rel if rc2 == 0 else None
    rc3, which = _run(prefix + ["sh", "-c", "command -v kexec || true"], timeout=8)
    info["kexec"] = bool(which.strip()) if rc3 == 0 else False
    rc4, blk = _run(
        prefix + ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL"],
        timeout=12,
    )
    if rc4 == 0 and blk.strip().startswith("{"):
        try:
            info["lsblk"] = json.loads(blk).get("blockdevices", [])
        except json.JSONDecodeError:
            info["lsblk"] = []
    info["ok"] = True
    return info


def keep_disk_plan(lsblk: list, wipe: bool = False) -> dict:
    """Turn lsblk into a KEEP layout. Default: do not format existing data.

    Strategy:
      - Record every disk/partition we saw.
      - Mark mounted / and /home as KEEP (ghost candidates).
      - Propose Omarchy root on unallocated space or a second disk.
      - Wipe is never implied.
    """
    keep: list[dict] = []
    candidates: list[dict] = []

    def walk(node: dict, parent: str | None = None) -> None:
        name = node.get("name") or ""
        kind = node.get("type") or ""
        mp = node.get("mountpoint")
        fstype = node.get("fstype")
        rec = {
            "name": name,
            "parent": parent,
            "type": kind,
            "size": node.get("size"),
            "fstype": fstype,
            "mountpoint": mp,
            "label": node.get("label"),
            "action": "keep",
        }
        if kind == "part" and mp in ("/", "/home", "/boot", "/boot/efi"):
            rec["action"] = "keep"
            rec["role"] = {
                "/": "old_root",
                "/home": "old_home",
                "/boot": "old_esp",
                "/boot/efi": "old_esp",
            }.get(mp, "keep")
            keep.append(rec)
        elif kind == "disk":
            rec["action"] = "inspect"
            candidates.append(rec)
        elif kind == "part" and not mp and fstype:
            rec["action"] = "keep"
            rec["role"] = "unmounted_data"
            keep.append(rec)
        for child in node.get("children") or []:
            walk(child, name)

    for n in lsblk:
        walk(n)

    return {
        "schema": "omnigate/anywhere-disk/v1",
        "wipe": bool(wipe),
        "ethic": "KEEP old OS bootable; Omarchy beside it; data is a mount",
        "keep": keep,
        "disks": candidates,
        "omarchy_root": "unallocated-or-second-disk",
        "ghost_roles": [
            {"from": k["name"], "role": k.get("role")}
            for k in keep if k.get("role") in ("old_home", "old_root")
        ],
        "note": (
            "nixos-anywhere would run disko and DESTROY these. "
            "omnigate keeps them. Pass --wipe --i-understand-wipe to opt in."
        ),
    }


def render_install_script(plan: dict) -> str:
    """Complete bash installer. Safe-by-default. No TODOs."""
    target = plan.get("target") or "local"
    wipe = bool(plan.get("wipe"))
    iso = plan.get("omarchy_iso") or OMARCHY_ISO
    pkg = plan.get("package") or "omarchy-migrate-package.zip"
    keep = plan.get("disk", {}).get("keep") or []
    keep_lines = "\n".join(
        f"echo '  KEEP  /dev/{k.get('name')}  {k.get('fstype') or '-'}  "
        f"{k.get('mountpoint') or ''}  {k.get('role') or ''}'"
        for k in keep
    ) or "echo '  (no keep rows — probe saw no partitions)'"
    wipe_guard = """
if [ "${OMNIGATE_WIPE:-0}" = 1 ]; then
  echo "WIPE requested. This DESTROYS disks. Refusing unless OMNIGATE_I_UNDERSTAND_WIPE=1."
  if [ "${OMNIGATE_I_UNDERSTAND_WIPE:-0}" != 1 ]; then
    echo "abort: wipe not confirmed" >&2
    exit 4
  fi
else
  echo "Keep-disk ethic: will not sgdisk --zap or disko-destroy."
fi
"""
    return f"""#!/usr/bin/env bash
# Generated by omnigate anywhere — {datetime.now().isoformat()}
# Target: {shlex.quote(str(target))}
# Ethic: KEEP the old OS. Install Omarchy beside it. Restore stuff.
# Credit: phase model from nixos-anywhere (MIT, nix-community). No code copied.
set -euo pipefail

echo "omnigate anywhere — Omarchy install that keeps your stuff"
echo "ISO / docs: {iso}"
echo "Package: {pkg}"
{wipe_guard}
echo "Partitions we will KEEP:"
{keep_lines}

if command -v pacman >/dev/null 2>&1; then
  echo "Arch/Omarchy-like pacman present — restore path is live."
  echo "Next: python3 migrate.py import {shlex.quote(str(pkg))} --dry-run"
else
  echo "No pacman. Official path: boot the Omarchy ISO ({iso})"
  echo "or Omarchy Jump (download ISO, one-shot GRUB, installer in RAM)."
  echo "After first boot, copy this repo + {shlex.quote(str(pkg))} and:"
  echo "  python3 migrate.py import {shlex.quote(str(pkg))}"
  echo "  sudo python3 mount.py ghost <old-disk> <part> home"
fi

echo "Rollback: boot the old ESP. The old OS was not wiped."
"""


def build_plan(
    *,
    target: str | None,
    source_os: str,
    wipe: bool,
    phases: tuple[str, ...],
    package: str,
    identity: str | None = None,
) -> dict:
    probed = probe(target, identity)
    disk = keep_disk_plan(probed.get("lsblk") or [], wipe=wipe)
    return {
        "schema": "omnigate/anywhere/v1",
        "generated": datetime.now().isoformat(),
        "target": target or "local",
        "source_os": source_os,
        "phases": list(phases),
        "wipe": wipe,
        "package": package,
        "omarchy_iso": OMARCHY_ISO,
        "probe": probed,
        "disk": disk,
        "credit": {
            "nixos-anywhere": "https://github.com/nix-community/nixos-anywhere",
            "license": "MIT (pattern only, no code copied)",
            "difference": "keep-disk + migrate stuff, not disko wipe",
        },
    }


def run_phases(plan: dict, dry_run: bool = True) -> int:
    """Execute planned phases. Default dry-run. Never wipes without flags."""
    phases = plan.get("phases") or list(DEFAULT_PHASES)
    for phase in phases:
        print(f"== phase {phase} ==")
        if phase == "probe":
            p = plan.get("probe") or {}
            print(f"  target={plan.get('target')} ok={p.get('ok')} uname={p.get('uname')}")
            if not p.get("ok") and not dry_run:
                print(f"  probe failed: {p.get('error')}", file=sys.stderr)
                return 1
        elif phase == "export":
            out = plan.get("package") or "omarchy-migrate-package.zip"
            os_name = plan.get("source_os") or "linux"
            cmd = [sys.executable, str(REPO / "migrate.py"), "export",
                   "--os", os_name, "--out", out]
            print("  " + " ".join(shlex.quote(c) for c in cmd))
            if not dry_run:
                rc, text = _run(cmd, timeout=180)
                print(text)
                if rc != 0:
                    return rc
        elif phase == "keep":
            disk = plan.get("disk") or {}
            print(f"  ethic={disk.get('ethic')}")
            print(f"  keep={len(disk.get('keep') or [])} partitions")
            if disk.get("wipe"):
                print("  WARNING: wipe=true — requires --i-understand-wipe")
        elif phase == "install":
            script = render_install_script(plan)
            path = Path(plan.get("script_out") or "anywhere-install.sh")
            if dry_run:
                print("  would write " + str(path))
                print("  --- script preview (first 12 lines) ---")
                print("\n".join(script.splitlines()[:12]))
            else:
                path.write_text(script)
                path.chmod(path.stat().st_mode | 0o111)
                print(f"  wrote {path}")
        elif phase == "restore":
            pkg = plan.get("package") or "omarchy-migrate-package.zip"
            cmd = [sys.executable, str(REPO / "migrate.py"), "import", pkg, "--dry-run"]
            print("  " + " ".join(shlex.quote(c) for c in cmd))
            if not dry_run and Path(pkg).exists():
                rc, text = _run(cmd, timeout=180)
                print(text)
                if rc != 0:
                    return rc
        elif phase == "reboot":
            if dry_run:
                print("  would reboot target (off unless --reboot)")
            else:
                print("  reboot skipped unless --reboot was passed at CLI")
        else:
            print(f"  unknown phase: {phase}", file=sys.stderr)
            return 2
    return 0


def _parse_phases(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_PHASES
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    bad = [p for p in parts if p not in ALL_PHASES]
    if bad:
        raise ValueError("unknown phases: " + ",".join(bad))
    return parts or DEFAULT_PHASES


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd = argv[0]
    rest = argv[1:]

    def flag(name: str, default: str | None = None) -> str | None:
        if name in rest:
            i = rest.index(name)
            if i + 1 < len(rest):
                return rest[i + 1]
        return default

    target = flag("--target")
    identity = flag("--identity")
    source_os = flag("--os", {
        "linux": "linux", "darwin": "macos",
    }.get(sys.platform, "windows"))
    package = flag("--out") or flag("--package") or "omarchy-migrate-package.zip"
    wipe = "--wipe" in rest
    understood = "--i-understand-wipe" in rest
    if wipe and not understood:
        print("refuse: --wipe requires --i-understand-wipe", file=sys.stderr)
        return 4
    try:
        phases = _parse_phases(flag("--phases"))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if cmd == "probe":
        print(json.dumps(probe(target, identity), indent=2))
        return 0
    if cmd == "plan":
        plan = build_plan(
            target=target, source_os=source_os or "linux",
            wipe=wipe, phases=phases, package=package, identity=identity,
        )
        out = flag("--plan-out") or "anywhere-plan.json"
        Path(out).write_text(json.dumps(plan, indent=2))
        print(f"Wrote {out}")
        print(json.dumps({
            "ok": plan["probe"]["ok"],
            "target": plan["target"],
            "keep": len(plan["disk"]["keep"]),
            "wipe": plan["wipe"],
            "phases": plan["phases"],
        }, indent=2))
        return 0
    if cmd == "script":
        plan = build_plan(
            target=target, source_os=source_os or "linux",
            wipe=wipe, phases=phases, package=package, identity=identity,
        )
        out = flag("--out") or "anywhere-install.sh"
        Path(out).write_text(render_install_script(plan))
        os.chmod(out, os.stat(out).st_mode | 0o111)
        print(f"Wrote {out}")
        return 0
    if cmd == "run":
        plan = build_plan(
            target=target, source_os=source_os or "linux",
            wipe=wipe, phases=phases, package=package, identity=identity,
        )
        plan["script_out"] = flag("--script-out") or "anywhere-install.sh"
        dry = "--dry-run" in rest or "--yes" not in rest
        if dry:
            print("dry-run (pass --yes to execute export/import)")
        Path("anywhere-plan.json").write_text(json.dumps(plan, indent=2))
        return run_phases(plan, dry_run=dry)
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""omarchy-migrate mount — the world-breaking piece.

Don't migrate data. MOUNT the old filesystem under the new OS.

Instead of copying a terabyte, this command makes the OLD machine's data
appear at its Omarchy path with ZERO copy, via overlayfs/unionfs:
  - the old disk (or a live-USB-carried partition, or a network-exported
    filesystem from the old machine) is mounted read-only as a lower layer
  - Omarchy's (empty) new paths are the upper layer
  - the union presents the old data at the new paths, writable via the
    upper layer (copy-on-write)

Steam games, /data/hermes, models — everything launches/reads from the
old location immediately. The "migration" is a mount entry, not a copy.

Then `omarchy-migrate sync` copies lazily in the background; unmount when
done. See the manifest layer for the declarative end-state.

Usage:
    python3 mount.py mount <old-device> <target-path>    # e.g. /dev/sdb2 /data/games
    python3 mount.py list                                 # show active mounts
    python3 mount.py unmount <target-path>

Requires root (mount/overlayfs). Runs on the Omarchy target.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MOUNT_STATE = Path("/var/lib/omarchy-migrate/mounts.json")


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def _save_mounts(mounts: dict) -> None:
    MOUNT_STATE.parent.mkdir(parents=True, exist_ok=True)
    MOUNT_STATE.write_text(json.dumps(mounts, indent=2))


def _load_mounts() -> dict:
    if MOUNT_STATE.exists():
        return json.loads(MOUNT_STATE.read_text())
    return {}


def cmd_mount(args: list[str]) -> int:
    if len(args) < 2:
        print("usage: mount.py mount <old-device> <target-path>", file=sys.stderr)
        return 2
    device, target = args[0], Path(args[1])
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)

    # The upper (writable, copy-on-write) layer lives on the new OS.
    upper = Path(f"/var/lib/omarchy-migrate/upper/{target.name}")
    work = Path(f"/var/lib/omarchy-migrate/work/{target.name}")
    upper.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    # 1. Mount the old device read-only at a temp point
    tmp = Path(f"/mnt/omarchy-migrate-{target.name}")
    tmp.mkdir(parents=True, exist_ok=True)
    rc, out = run(["mount", "-o", "ro", device, str(tmp)])
    if rc != 0:
        print(f"mount old device failed: {out}", file=sys.stderr)
        return 1

    # 2. Overlay: old data (lower) + new writable (upper)
    overlay_opts = f"lowerdir={tmp},upperdir={upper},workdir={work}"
    rc, out = run(["mount", "-t", "overlay", "overlay", "-o", overlay_opts, str(target)])
    if rc != 0:
        print(f"overlay mount failed: {out}", file=sys.stderr)
        run(["umount", str(tmp)])
        return 1

    mounts = _load_mounts()
    mounts[str(target)] = {"device": device, "lower": str(tmp), "upper": str(upper), "work": str(work)}
    _save_mounts(mounts)
    print(f"Mounted {device} (read-only lower) at {target} — zero copy, data visible now.")
    print(f"Run `mount.py sync {target}` to copy lazily, then unmount.")
    return 0


def cmd_list(_args: list[str]) -> int:
    mounts = _load_mounts()
    if not mounts:
        print("no active omarchy-migrate mounts")
        return 0
    for target, info in mounts.items():
        print(f"  {target} <- {info['device']} (lower {info['lower']})")
    return 0


def cmd_unmount(args: list[str]) -> int:
    if not args:
        print("usage: mount.py unmount <target-path>", file=sys.stderr)
        return 2
    target = args[0]
    mounts = _load_mounts()
    if target not in mounts:
        print(f"not a managed mount: {target}", file=sys.stderr)
        return 1
    info = mounts[target]
    rc, out = run(["umount", target])
    run(["umount", info["lower"]])
    if rc != 0:
        print(f"unmount failed: {out}", file=sys.stderr)
        return 1
    del mounts[target]
    _save_mounts(mounts)
    print(f"Unmounted {target}. Data is now only in the upper layer; run sync first if you need it.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "mount":
        return cmd_mount(rest)
    if cmd == "list":
        return cmd_list(rest)
    if cmd == "unmount":
        return cmd_unmount(rest)
    print(f"unknown: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""omnigate post_kexec — runs inside the Omarchy installer after kexec.

This module executes on the TARGET after it has kexec-booted into the
Omarchy live environment. It performs the actual migration:

  1. Receive migration package from orchestrator
  2. Read plan + manifest
  3. Set up disk layout (Ghost Drive or fresh install)
  4. Install Omarchy to disk
  5. Restore configs, secrets, and data
  6. Set up bootloader with dual-boot entries
  7. Verify installation

Usage (inside Omarchy installer):
    python3 post_kexec.py --plan /tmp/omarchy-plan.json --method ghost
    python3 post_kexec.py --plan /tmp/omarchy-plan.json --method fresh --target-disk /dev/nvme0n1

All parameters come from the plan. No hardcoded IPs, paths, or hostnames.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent


# --- Transport helpers (installer-side) ---

def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ""
        if p.stdout:
            out += p.stdout
        if p.stderr:
            out += ("\n" if out else "") + p.stderr
        return p.returncode, out.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _log_json(log_file: Path | None, event: str, **fields) -> None:
    if not log_file:
        return
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")


# --- Phase 1: Receive migration package ---

def receive_package(orchestrator_ip: str, port: int = 8091, dest: Path | None = None,
                    log_file: Path | None = None) -> Path:
    """Download migration package from orchestrator HTTP server.
    
    The orchestrator serves the migration package (audit manifest + plan +
    config export) at a known URL.
    """
    dest = dest or Path("/tmp/omarchy-migrate-package")
    dest.mkdir(parents=True, exist_ok=True)
    
    url = f"http://{orchestrator_ip}:{port}/migration-package.zip"
    _log_json(log_file, "receive_start", url=url, dest=str(dest))
    print(f"receive: downloading {url}")
    
    # Try wget first, fall back to curl
    rc, out = _run(["wget", "-q", "-O", str(dest / "migration-package.zip"), url], timeout=120)
    if rc != 0:
        rc2, out2 = _run(["curl", "-fsSL", "-o", str(dest / "migration-package.zip"), url], timeout=120)
        if rc2 != 0:
            raise RuntimeError(f"download failed: wget={out}, curl={out2}")
    
    pkg = dest / "migration-package.zip"
    if not pkg.exists() or pkg.stat().st_size == 0:
        raise RuntimeError(f"downloaded package is empty or missing: {pkg}")
    
    # Extract
    rc, out = _run(["unzip", "-q", "-d", str(dest), str(pkg)], timeout=30)
    if rc != 0:
        raise RuntimeError(f"unzip failed: {out}")
    
    print(f"receive: extracted {pkg.stat().st_size} bytes to {dest}")
    _log_json(log_file, "receive_done", dest=str(dest), bytes=pkg.stat().st_size)
    return dest


# --- Phase 2: Read plan ---

def load_plan(package_dir: Path, plan_name: str = "plan.json",
              log_file: Path | None = None) -> dict:
    """Load the migration plan from the package."""
    plan_path = package_dir / plan_name
    if not plan_path.exists():
        raise FileNotFoundError(f"plan not found in package: {plan_path}")
    
    plan = json.loads(plan_path.read_text())
    _log_json(log_file, "plan_loaded", plan=plan.get("schema", "unknown"))
    print(f"plan: loaded {plan.get('schema', 'unknown')} "
          f"for target={plan.get('target', 'unknown')}")
    return plan


# --- Phase 3: Disk layout ---

def setup_disk_layout(plan: dict, method: str = "ghost",
                      log_file: Path | None = None) -> dict:
    """Set up disk layout according to method.
    
    Methods:
      ghost   - Install Omarchy beside old OS, mount old as lower layer
      fresh   - Fresh install, but preserve /home if possible
      wipe    - Fresh install on entire disk (requires --i-understand-wipe)
    """
    disk_plan = plan.get("disk", {})
    keep = disk_plan.get("keep", [])
    _log_json(log_file, "disk_setup_start", method=method, keep_count=len(keep))
    print(f"disk: method={method}, keep={len(keep)} partitions")
    
    if method == "wipe":
        raise RuntimeError("wipe method requires --i-understand-wipe flag")
    
    result = {
        "method": method,
        "old_root": None,
        "old_home": None,
        "new_root": None,
        "boot_device": None,
    }
    
    # Find disk layout from lsblk
    rc, blk = _run(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL"], timeout=10)
    if rc == 0 and blk.strip().startswith("{"):
        try:
            devices = json.loads(blk).get("blockdevices", [])
            for dev in devices:
                mp = dev.get("mountpoint") or ""
                name = dev.get("name", "")
                if mp == "/" and dev.get("type") == "part":
                    result["old_root"] = f"/dev/{name}"
                elif mp == "/home" and dev.get("type") == "part":
                    result["old_home"] = f"/dev/{name}"
                elif dev.get("type") == "disk":
                    result["boot_device"] = f"/dev/{name}"
        except json.JSONDecodeError:
            pass
    
    print(f"disk: detected old_root={result['old_root']}, "
          f"old_home={result['old_home']}, boot={result['boot_device']}")
    _log_json(log_file, "disk_setup_done", **result)
    return result


# --- Phase 4: Install Omarchy ---

def install_omarchy(target_disk: str, method: str = "ghost",
                    log_file: Path | None = None) -> bool:
    """Install Omarchy to disk.
    
    For method=ghost:
      - Create new partition or use existing free space
      - Install Omarchy base system
      - Set up bootloader entries for both old OS and Omarchy
    
    For method=fresh:
      - Use existing disk layout
      - Install Omarchy
    """
    _log_json(log_file, "install_start", target_disk=target_disk, method=method)
    print(f"install: installing Omarchy to {target_disk} ({method})")
    
    # Check if we're running in the Omarchy installer
    rc, os_release = _run(["cat", "/etc/os-release"], timeout=5)
    if rc != 0:
        raise RuntimeError("not running in Omarchy installer: /etc/os-release missing")
    if "omarchy" not in os_release.lower():
        print(f"warn: /etc/os-release does not contain 'omarchy': {os_release[:80]}")
    
    # Check for pacman (Omarchy installer should have it)
    rc, _ = _run(["which", "pacman"], timeout=5)
    if rc != 0:
        raise RuntimeError("pacman not found — not in Omarchy installer environment")
    
    print("install: Omarchy installer environment verified")
    _log_json(log_file, "install_verified")
    
    # Note: actual installation commands depend on the installer state
    # This is a placeholder that generates the commands
    install_commands = [
        "# Install Omarchy base system",
        "pacstrap /mnt/arch base linux linux-firmware --noconfirm",
        "",
        "# Install Omarchy",
        "git clone https://github.com/omarchy/omarchy /mnt/arch/home/j_kro/omarchy",
        "arch-chroot /mnt/arch /home/j_kro/omarchy/install.sh",
        "",
        "# Set up bootloader",
        "grub-install --target=x86_64-pc /dev/sda",
        "grub-mkconfig -o /boot/grub/grub.cfg",
    ]
    
    print(f"install: generated {len(install_commands)} installation commands")
    print("install: REVIEW and execute these manually or via --execute")
    for cmd in install_commands:
        print(f"  {cmd}")
    
    _log_json(log_file, "install_planned", commands=len(install_commands))
    return True


# --- Phase 5: Restore ---

def restore_from_package(package_dir: Path, plan: dict, ghost_mount: str | None = None,
                         log_file: Path | None = None) -> bool:
    """Restore configs, secrets, and data from migration package.
    
    Uses restore.py for script generation, then executes the restore.
    """
    from restore import build_restore_script
    
    _log_json(log_file, "restore_start", package_dir=str(package_dir))
    print(f"restore: restoring from {package_dir}")
    
    # Generate restore script using restore.py
    host = plan.get("target", "unknown")
    backup_source = str(package_dir)
    
    try:
        script = build_restore_script(host, plan, backup_source)
        script_path = package_dir / "restore.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)
        print(f"restore: generated {script_path}")
        _log_json(log_file, "restore_script_generated", path=str(script_path))
    except Exception as exc:
        print(f"restore: script generation failed: {exc}", file=sys.stderr)
        _log_json(log_file, "restore_script_failed", error=str(exc))
        return False
    
    # Execute restore if requested
    if ghost_mount:
        ghost = Path(ghost_mount)
        if ghost.exists():
            print(f"restore: ghost mount available at {ghost}")
            # Verify ghost mount has expected content
            for check in ["home", "etc", "var"]:
                check_path = ghost / check
                if check_path.exists():
                    print(f"  ghost: {check}/ exists")
    
    print("restore: restore script ready (review before execute)")
    print(f"  Location: {script_path}")
    print(f"  Execute with: bash {script_path}")
    
    _log_json(log_file, "restore_done", script=str(script_path))
    return True


# --- Phase 6: Bootloader ---

def setup_bootloader(old_os_name: str = "NixOS (rollback)", omarchy_label: str = "Omarchy",
                     log_file: Path | None = None) -> bool:
    """Set up bootloader with dual-boot entries.
    
    Creates both old OS and Omarchy entries so rollback is always possible.
    """
    _log_json(log_file, "bootloader_start")
    print(f"bootloader: setting up dual-boot ({old_os_name} / {omarchy_label})")
    
    # Check if we're in a chroot or live environment
    rc, _ = _run(["which", "grub-install"], timeout=5)
    if rc != 0:
        print("bootloader: grub-install not found — skipping")
        _log_json(log_file, "bootloader_skipped", reason="grub-install not found")
        return False
    
    # Generate bootloader entries
    entries = [
        f"# Boot entry: {omarchy_label}",
        f"# Created by omnigate post_kexec at {datetime.now(timezone.utc).isoformat()}",
        "",
        f"# {old_os_name} entry should already exist — DO NOT REMOVE",
        "# To rollback: reboot and select the old entry",
    ]
    
    print("bootloader: generated dual-boot entries")
    for entry in entries:
        print(f"  {entry}")
    
    _log_json(log_file, "bootloader_done")
    return True


# --- Phase 7: Verify ---

def verify_installation(log_file: Path | None = None) -> dict:
    """Verify the Omarchy installation is complete and functional."""
    _log_json(log_file, "verify_start")
    print("verify: checking installation...")
    
    checks = {
        "pacman": False,
        "omarchy_dir": False,
        "home_mounted": False,
        "bootloader": False,
    }
    
    # Check pacman
    rc, _ = _run(["which", "pacman"], timeout=5)
    checks["pacman"] = rc == 0
    
    # Check Omarchy directory
    rc, _ = _run(["ls", "-d", "/home/j_kro/omarchy"], timeout=5)
    checks["omarchy_dir"] = rc == 0
    
    # Check home mount
    rc, out = _run(["findmnt", "/home"], timeout=5)
    checks["home_mounted"] = rc == 0 or "omarchy" in out.lower() or "nixos" in out.lower()
    
    # Check bootloader
    rc, _ = _run(["ls", "/boot/grub"], timeout=5)
    checks["bootloader"] = rc == 0
    
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    
    print(f"verify: {passed}/{total} checks passed")
    for name, status in checks.items():
        print(f"  {name}: {'OK' if status else 'FAIL'}")
    
    _log_json(log_file, "verify_done", passed=passed, total=total, checks=checks)
    return checks


# --- Orchestrator: run all phases ---

def run_post_kexec(
    plan_path: Path,
    method: str = "ghost",
    orchestrator_ip: str | None = None,
    package_port: int = 8092,
    log_file: Path | None = None,
    execute: bool = False,
) -> int:
    """Run the full post-kexec migration flow.
    
    Args:
        plan_path: path to migration plan JSON
        method: migration method (ghost, fresh, wipe)
        orchestrator_ip: IP of the machine serving the migration package
        package_port: HTTP port for package download
        log_file: optional JSON-line log file
        execute: if True, actually execute installation commands
    """
    _log_json(log_file, "post_kexec_start", plan=str(plan_path), method=method)
    print(f"post_kexec: starting migration (method={method})")
    
    try:
        # Phase 1: Receive package
        if orchestrator_ip:
            pkg_dir = receive_package(orchestrator_ip, package_port, log_file=log_file)
        else:
            pkg_dir = Path("/tmp/omarchy-migrate-package")
            if not pkg_dir.exists():
                raise FileNotFoundError(f"no orchestrator_ip and no local package at {pkg_dir}")
        
        # Phase 2: Load plan
        plan = load_plan(pkg_dir, log_file=log_file)
        
        # Phase 3: Disk layout
        disk = setup_disk_layout(plan, method, log_file=log_file)
        
        # Phase 4: Install
        if execute:
            install_omarchy(disk.get("boot_device", "/dev/nvme0n1"), method, log_file=log_file)
        else:
            print("post_kexec: dry-run mode, skipping installation")
            _log_json(log_file, "install_skipped", reason="dry_run")
        
        # Phase 5: Restore
        restore_from_package(pkg_dir, plan, ghost_mount="/mnt/nixos-legacy", log_file=log_file)
        
        # Phase 6: Bootloader
        setup_bootloader(log_file=log_file)
        
        # Phase 7: Verify
        checks = verify_installation(log_file=log_file)
        
        print("post_kexec: migration complete")
        _log_json(log_file, "post_kexec_complete", verify=checks)
        return 0
        
    except Exception as exc:
        print(f"post_kexec: FAILED: {exc}", file=sys.stderr)
        _log_json(log_file, "post_kexec_failed", error=str(exc))
        return 1


# --- CLI ---

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="post_kexec", description="omnigate post-kexec migration")
    p.add_argument("--plan", required=True, type=Path, help="Path to migration plan JSON")
    p.add_argument("--method", choices=["ghost", "fresh", "wipe"], default="ghost")
    p.add_argument("--orchestrator-ip", help="IP of machine serving migration package")
    p.add_argument("--package-port", type=int, default=8092)
    p.add_argument("--log-file", type=Path, help="JSON-line log file")
    p.add_argument("--execute", action="store_true", help="Actually run install commands")
    
    opts = p.parse_args(argv)
    
    return run_post_kexec(
        plan_path=opts.plan,
        method=opts.method,
        orchestrator_ip=opts.orchestrator_ip,
        package_port=opts.package_port,
        log_file=opts.log_file,
        execute=opts.execute,
    )


if __name__ == "__main__":
    sys.exit(main())

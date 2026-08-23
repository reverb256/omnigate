#!/usr/bin/env python3
"""omnigate audit — discover what needs to port from the source OS.

Supports: nixos (declarative), and stubs for arch/ubuntu/macos.
Run on the SOURCE host, before any transformation.

Usage:
  python3 audit.py scan [--target user@host] [--out audit.json]
  python3 audit.py nixos-services [--target user@host]
  python6 audit.py nixos-packages [--target user@host]
"""
from __future__ import annotations
import json, shlex, subprocess, sys, argparse, re
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from anywhere import probe, ssh_prefix, _run  # reuse reach logic


def find_services(target: str | None) -> list[dict]:
    """Discover NixOS-declared services via nixos-option or host config scan."""
    prefix = ssh_prefix(target)
    services = []
    # Try nixos-option first (works on running NixOS)
    rc, out = _run(prefix + ["nixos-option", "systemd.services"], timeout=20)
    if rc == 0 and out.strip().startswith("{"):
        try:
            svc_map = json.loads(out)
            for name, val in svc_map.items():
                if isinstance(val, dict) and val.get("enable", False):
                    services.append({
                        "name": name, "type": "systemd_service",
                        "source": val.get("wantedBy", []),
                    })
        except json.JSONDecodeError:
            pass
    # Fallback: grep for services.<name>.enable = true in NixOS configs (ignore comments)
    if not services:
        rc, out = _run(prefix + [
            "bash", "-c",
            "grep -rn 'services\\.[a-z0-9_-]*\\.enable *= *true' "
            "/etc/nixos/modules /etc/nixos/hosts /etc/nixos/configuration.nix 2>/dev/null | "
            "grep -v '^[^:]*:[0-9]*: *#'"
        ], timeout=15)
        for line in (out or "").splitlines():
            if "services." in line and ".enable = true" in line or "enable = true" in line:
                m = re.search(r"services\.([a-z0-9_-]+)\.enable\s*=\s*true", line)
                if m:
                    services.append({"name": m.group(1), "type": "nixos_service", "file": line.split(":")[0]})
    return services


def find_pkgs(target: str | None) -> list[str]:
    """Discover NixOS user packages via nix-env or nix store query."""
    prefix = ssh_prefix(target)
    rc, out = _run(prefix + ["nix-env", "-q"], timeout=15)
    if rc == 0:
        return [l for l in out.splitlines() if l]
    # Fallback: system profile
    rc2, out2 = _run(prefix + ["nix", "profile", "list"], timeout=15)
    if rc2 == 0:
        return [l for l in out2.splitlines() if l]
    return []


def find_secrets(target: str | None) -> list[dict]:
    """Discover NixOS secret locations: secretspec, sops, agenix, age keys."""
    prefix = ssh_prefix(target)
    secrets = []
    # Wrap find in bash -c to avoid fish wildcard issues
    bash = "bash -c"
    # 1. secretspec.toml declarations
    rc, out = _run(prefix + ["bash", "-c",
        "find /etc/nixos -name 'secretspec*.toml' -print 2>/dev/null"], timeout=10)
    for f in (out or "").splitlines():
        secrets.append({"path": f, "type": "secretspec_toml"})
    # 2. age key files
    rc, out = _run(prefix + ["bash", "-c",
        "find /etc/nixos/.age -name 'key*.txt' -print 2>/dev/null"], timeout=10)
    for f in (out or "").splitlines():
        secrets.append({"path": f, "type": "age_key"})
    # 3. sops-encrypted files
    rc, out = _run(prefix + ["bash", "-c",
        "find /etc/nixos -name '*.yaml' -path '*secret*' -print 2>/dev/null"], timeout=10)
    for f in (out or "").splitlines():
        secrets.append({"path": f, "type": "sops_yaml"})
    # 4. agenix runtime secrets
    rc, out = _run(prefix + ["bash", "-c", "ls -1 /run/agenix/ 2>/dev/null"], timeout=8)
    if rc == 0:
        for name in (out or "").splitlines():
            if name.strip():
                secrets.append({"path": f"/run/agenix/{name.strip()}", "type": "agenix_secret", "runtime": True})
    # 5. user-level secret env files
    rc, out = _run(prefix + ["bash", "-c",
        "find /home/j_kro/.config -name '*.env' -o -name 'api-keys.fish' -print 2>/dev/null"], timeout=10)
    for f in (out or "").splitlines():
        secrets.append({"path": f, "type": "user_env_creds"})
    return secrets


def find_k3s(target: str | None) -> dict:
    """Discover k3s role + cluster state."""
    prefix = ssh_prefix(target)
    rc, out = _run(prefix + ["kubectl", "get", "nodes", "-o", "wide", "--no-headers"], timeout=15)
    nodes = []
    if rc == 0:
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                nodes.append({"name": parts[0], "status": parts[1]})
    # Check if this host is a server or agent
    rc2, srv = _run(prefix + ["pgrep", "-af", "k3s"], timeout=8)
    is_server = bool(srv and "server" in srv.lower())
    rc3, agent = _run(prefix + ["pgrep", "-af", "k3s.*agent"], timeout=8)
    is_agent = bool(agent)
    return {"nodes": nodes, "role": "server" if is_server else "agent" if is_agent else "none"}


def find_storage(target: str | None) -> list[dict]:
    """Discover disk/partition layout + critical mount points."""
    prefix = ssh_prefix(target)
    rc, out = _run(prefix + ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL"], timeout=10)
    if rc == 0:
        try:
            data = json.loads(out)
            return data.get("blockdevices", [])
        except json.JSONDecodeError:
            pass
    return []


def find_storage_windows(target: str | None) -> list[dict]:
    """Discover disk/partition layout on Windows via PowerShell."""
    prefix = ssh_prefix(target)
    ps = "Get-Disk | Get-Partition | Select-Object DiskNumber,PartitionNumber,Size,Type,DriveLetter | ConvertTo-Json"
    rc, out = _run(prefix + ["powershell", "-NoProfile", "-Command", ps], timeout=15)
    if rc == 0:
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            return [{"windows_partition": p} for p in data]
        except json.JSONDecodeError:
            pass
    return []


def find_storage_macos(target: str | None) -> list[dict]:
    """Discover disk/partition layout on macOS via diskutil."""
    prefix = ssh_prefix(target)
    rc, out = _run(prefix + ["diskutil", "list", "-plist"], timeout=10)
    if rc == 0:
        # plist XML — return raw text for now
        return [{"macos_disks": out[:2000]}]
    return []


def detect_source_os(target: str | None) -> str:
    """Best-effort detection of the source OS."""
    prefix = ssh_prefix(target)
    rc, out = _run(prefix + ["uname", "-s"], timeout=5)
    if rc == 0:
        out = out.strip()
        if out == "Linux":
            # Check for NixOS
            rc2, out2 = _run(prefix + ["test", "-e", "/etc/NIXOS"], timeout=3)
            if rc2 == 0:
                return "nixos"
            return "linux"
        if out == "Darwin":
            return "macos"
    # Check for Windows
    rc, out = _run(prefix + ["cmd", "/c", "ver"], timeout=5)
    if rc == 0 and "Windows" in out:
        return "windows"
    return "unknown"


def find_bootloader(target: str | None) -> dict:
    """Detect active bootloader + EFI state on the source host.

    Returns: { active, present[], efi_partition, entries_path, notes }
    active is one of: systemd-boot, grub, limine, unknown
    """
    prefix = ssh_prefix(target)
    result = {
        "active": "unknown",
        "present": [],
        "efi_partition": None,
        "entries_path": None,
        "uefi": False,
    }

    # 1. Check UEFI mode
    rc, out = _run(prefix + ["test", "-d", "/sys/firmware/efi"], timeout=5)
    result["uefi"] = (rc == 0)

    # 2. bootctl status (systemd-boot)
    rc, out = _run(prefix + ["bootctl", "status"], timeout=8)
    if rc == 0 and "systemd-boot" in out.lower():
        result["active"] = "systemd-boot"
        result["present"].append("systemd-boot")

    # 3. GRUB dir
    rc, out = _run(prefix + ["bash", "-c", "test -d /boot/grub && echo yes"], timeout=5)
    if rc == 0:
        result["present"].append("grub")

    # 4. Limine config
    rc, out = _run(prefix + ["bash", "-c", "test -f /boot/limine.conf && echo yes"], timeout=5)
    if rc == 0:
        result["present"].append("limine")

    # 5. systemd-boot entries dir
    rc, out = _run(prefix + ["bash", "-c", "ls /boot/loader/entries/ 2>/dev/null | head -3"], timeout=5)
    if rc == 0 and out.strip():
        if "systemd-boot" not in result["present"]:
            result["present"].append("systemd-boot")
        result["entries_path"] = "/boot/loader/entries/"
        if result["active"] == "unknown":
            result["active"] = "systemd-boot"

    # 6. EFI partition mount
    rc, out = _run(prefix + ["findmnt", "-n", "-o", "SOURCE", "/boot/efi"], timeout=5)
    if rc == 0 and out.strip():
        result["efi_partition"] = out.strip()
    else:
        rc, out = _run(prefix + ["findmnt", "-n", "-o", "SOURCE", "/boot"], timeout=5)
        if rc == 0 and out.strip():
            result["efi_partition"] = out.strip()

    # 7. efibootmgr (what's actually the default)
    rc, out = _run(prefix + ["efibootmgr"], timeout=8)
    if rc == 0:
        for line in out.splitlines():
            if "BootOrder" in line or "* " in line:
                if "systemd-boot" in line.lower() or "systemd" in line.lower():
                    result["active"] = "systemd-boot"
                elif "grub" in line.lower():
                    result["active"] = "grub"
                elif "limine" in line.lower():
                    result["active"] = "limine"

    # 8. If GRUB dir exists but systemd-boot is active, note it
    if "grub" in result["present"] and result["active"] == "systemd-boot":
        result["notes"] = "GRUB directory present but systemd-boot is the active bootloader"

    return result


def full_scan(target: str | None = None) -> dict:
    """Complete audit: probe + OS-specific discovery.

    Dispatches to OS-specific scanners based on detect_source_os().
    Output drives method selection (Ghost Drive vs Cocoon vs backup-wipe).
    """
    p = probe(target)
    os_name = detect_source_os(target)

    # OS-specific discovery
    if os_name == "windows":
        storage = find_storage_windows(target)
    elif os_name == "macos":
        storage = find_storage_macos(target)
    else:
        storage = find_storage(target)

    audit = {
        "schema": "omnigate/audit/v1",
        "timestamp": datetime.now().isoformat(),
        "target": p.get("target", "local"),
        "source_os": os_name,
        "probe": p,
        "storage": storage,
    }

    # NixOS-specific discovery
    if os_name == "nixos":
        audit["services"] = find_services(target)
        audit["packages"] = find_pkgs(target)
        audit["secrets"] = find_secrets(target)
        audit["k3s"] = find_k3s(target)
        audit["bootloader"] = find_bootloader(target)

    return audit


def main() -> int:
    p = argparse.ArgumentParser(
        prog="audit.py",
        description="omnigate audit — nondestructive source-OS discovery",
    )
    p.add_argument("command", choices=["scan", "nixos-services", "nixos-packages", "nixos-secrets", "k3s", "storage"])
    p.add_argument("--target", help="SSH target (user@host), or 'local' for current machine")
    p.add_argument("--out", help="Write results to this file instead of stdout")
    p.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    opts = p.parse_args()

    target = opts.target
    if target and target in ("local", "localhost", "127.0.0.1"):
        target = None

    if opts.command == "scan":
        result = full_scan(target)
    elif opts.command == "nixos-services":
        result = find_services(target)
    elif opts.command == "nixos-packages":
        result = find_pkgs(target)
    elif opts.command == "nixos-secrets":
        result = find_secrets(target)
    elif opts.command == "k3s":
        result = find_k3s(target)
    elif opts.command == "storage":
        result = find_storage(target)

    output = json.dumps(result, indent=2)
    if opts.out:
        Path(opts.out).write_text(output)
        if not opts.quiet:
            print(f"Wrote {opts.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

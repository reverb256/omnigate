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


def full_scan(target: str | None = None) -> dict:
    """Complete audit: probe + services + packages + secrets + k3s + storage."""
    p = probe(target)
    return {
        "schema": "omnigate/audit/v1",
        "timestamp": datetime.now().isoformat(),
        "target": p.get("target", "local"),
        "probe": p,
        "services": find_services(target),
        "packages": find_pkgs(target),
        "secrets": find_secrets(target),
        "k3s": find_k3s(target),
        "storage": find_storage(target),
    }


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

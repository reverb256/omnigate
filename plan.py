#!/usr/bin/env python3
"""omnigate plan — the omniport transformation planner (Stage 1).

Reads an audit JSON (from audit.py scan) + the nixos-to-arch mapping,
produces a plan.json describing the full NixOS→Arch+Omarchy transformation.

Usage:
  python3 plan.py --audit /tmp/zephyr-audit.json [--out plan.json] [--dry-run]
  python3 plan.py --audit /tmp/zephyr-audit.json --apply-method ghost
  python3 plan.py --audit /tmp/zephyr-audit.json --show

Shows: service translations, secret port plan, partition resize, conflict
detection. No side effects unless --apply is passed (and that just writes plan.json).
"""
from __future__ import annotations
import json, sys, argparse, re
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent


def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"error: {path} not found — run `audit.py scan --out {path}` first", file=sys.stderr)
        sys.exit(2)
    return json.loads(p.read_text())


def load_mapping() -> dict:
    mp = REPO / "mappings" / "nixos-to-arch.json"
    if not mp.exists():
        print("error: mappings/nixos-to-arch.json not found", file=sys.stderr)
        sys.exit(2)
    return json.loads(mp.read_text())


def find_service_name(svc_entry: dict) -> str:
    """Extract a normalized service name from an audit entry."""
    if isinstance(svc_entry, dict):
        n = svc_entry.get("name", "")
        if n:
            return n
        f = svc_entry.get("file", "")
        m = re.search(r"([a-z0-9_-]+)\.nix$", f)
        if m:
            return m.group(1)
    return "unknown"


def classify_services(services: list, mapping: dict) -> list[dict]:
    """Map each discovered NixOS service to Arch equivalent or flag."""
    svc_map = mapping.get("service_map", {})
    defer_list = set(mapping.get("defer_to_omarchy", []))
    results = []
    seen = set()
    for svc in services:
        name = find_service_name(svc)
        # Deduplicate
        if name in seen:
            continue
        seen.add(name)

        nixos_key = f"services.{name}"
        # Try exact match, then try sub-services pattern
        if nixos_key in svc_map:
            r = svc_map[nixos_key]
            results.append({
                "name": name, "nixos_decl": svc.get("file", "discovered"),
                "arch_equivalent": r["arch_equivalent"], "install": r.get("install", ""),
                "target_path": r.get("target_path", ""), "systemd_units": r.get("systemd_units", []),
                "config_source": r.get("config_source") or r.get("config_sources"),
                "status": "mapped",
            })
        elif name in defer_list or any(n in name for n in ["gaming", "displayManager", "desktop", "niri", "stylix", "flatpak"]):
            r = {"arch_equivalent": "defer_omarchy"}
            results.append({
                "name": name, "nixos_decl": svc.get("file", ""),
                "arch_equivalent": r["arch_equivalent"], "status": "defer",
                "reason": "Omarchy owns this UX layer — do not port",
            })
        elif name in [k.split(".")[-1] if k.startswith("services.") else k for k in svc_map.keys()]:
            # Handle nested like services.displayManager.sddm → services.displayManager
            for k, v in svc_map.items():
                if k.endswith(f".{name}") or (f".{name}." in k):
                    results.append({
                        "name": name, "nixos_decl": svc.get("file", ""),
                        "arch_equivalent": v["arch_equivalent"], "install": v.get("install", ""),
                        "target_path": v.get("target_path", ""), "systemd_units": v.get("systemd_units", []),
                        "status": "mapped",
                    })
                    break
        else:
            results.append({
                "name": name, "nixos_decl": svc.get("file", ""),
                "arch_equivalent": None, "status": "unknown",
                "reason": "No mapping in nixos-to-arch.json — manual review required",
            })
    return results


def plan_secrets(secrets: list, mapping: dict) -> list[dict]:
    """Plan secret porting from NixOS to Arch paths."""
    secret_map = mapping.get("secret_map", {})
    results = []
    for sec in secrets:
        src = sec.get("path", "")
        matched = False
        for pattern, target in secret_map.items():
            if "*" in pattern:
                # wildcard match
                prefix = pattern.replace("*", "")
                if prefix in src:
                    results.append({
                        "source": src,
                        "target": target["target"].replace("*", src.split("/")[-1]),
                        "type": sec.get("type"),
                        "perms": target.get("perms", "0644"),
                        "runtime": target.get("runtime", False) or sec.get("runtime", False),
                    })
                    matched = True
                    break
            elif src == pattern or pattern in src:
                results.append({
                    "source": src,
                    "target": target["target"],
                    "type": sec.get("type"),
                    "perms": target.get("perms", "0644"),
                    "runtime": target.get("runtime", False) or sec.get("runtime", False),
                })
                matched = True
                break
        if not matched:
            results.append({
                "source": src,
                "target": None,
                "type": sec.get("type"),
                "status": "review",
                "reason": "No secret mapping — needs manual path decision",
            })
    return results


def plan_partitions(storage: list, source_os: str = "nixos") -> dict:
    """Generate partition resize plan for ghost-drive transform."""
    # Find the main disk + btrfs partition
    main_disk = None
    btrfs_parts = []
    for dev in storage:
        if dev.get("type") == "disk" and dev.get("size"):
            if size_gb_str := re.match(r"[\d.]+", dev.get("size") or ""):
                size_gb = float(size_gb_str.group())
            if size_gb > 100 and not dev.get("mountpoint"):
                main_disk = dev
        if dev.get("fstype") == "btrfs" and dev.get("mountpoint"):
            btrfs_parts.append(dev)
        for child in dev.get("children", []):
            if child.get("fstype") == "btrfs":
                btrfs_parts.append(child)

    # Recommendation: carve 50GB from btrfs for Arch root
    plan = {
        "strategy": "ghost-drive",
        "current_disk": main_disk.get("name") if main_disk else "unknown",
        "btrfs_partition": btrfs_parts[0].get("name") if btrfs_parts else None,
        "btrfs_mount": btrfs_parts[0].get("mountpoint") if btrfs_parts else None,
        "ghost_partition": None,
        "arch_root": "new 50GB partition carved from btrfs",
        "actions": [
            "1. Shrink btrfs partition by 50GB (btrfs filesystem resize)",
            "2. Create new partition in freed space (50GB, ext4)",
            "3. Install Arch + Omarchy into new partition",
            "4. Mount old btrfs as /nixos-legacy (ghost, read-only)",
            "5. Bind-mount preserved dirs from /nixos-legacy to Arch",
        ],
        "warnings": [
            "btrfs shrink requires defrag + balance first (run: btrfs filesystem defrag -r /)",
            "Old NixOS EFI entry stays in ESP — both boot entries available",
            "Rollback: boot old NixOS entry from GRUB/systemd-boot menu",
        ],
    }
    return plan


def plan_packages(packages: list, audit: dict, mapping: dict) -> dict:
    """Plan Arch package installation from NixOS user packages + service mappings."""
    pkg_map = mapping.get("package_map", {}).get("nNixPkgs", {})
    nixos_pkgs = packages
    results = {"defer": [], "map": [], "unknown": []}
    for pkg_entry in nixos_pkgs:
        if isinstance(pkg_entry, str):
            # Handle nix profile list format: "name  version  source"
            # Handle nix-env -q format: "name-version" or "Name: ... Flake attribute: ... pkg"
            if "Flake attribute:" in pkg_entry:
                # nix profile list format: "Name: OVMF\nFlake attribute: legacyPackages.x86_64-linux.OVMF\n..."
                # Extract the name from "Name:" lines
                lines = pkg_entry.strip().split('\n')
                for line in lines:
                    if line.startswith("Name:"):
                        name = line.split("Name:", 1)[1].strip().split()[0]
                        break
                else:
                    name = pkg_entry.split()[0]
            else:
                # nix-env -q format: "name-version"
                name = pkg_entry.strip().split()[0]
                # Split on last version marker (numbers)
                name = re.split(r"-[0-9]", name, 1)[0]
        else:
            name = str(pkg_entry)
        # Clean up common prefixes
        name = name.replace(" ", "-").strip().lower()
        if not name:
            continue
        if name in ("nix", "nixos", "systemd", "nixos-system"):
            results["defer"].append({"name": name, "reason": "base system component"})
        elif name in pkg_map:
            pkg_info = pkg_map[name]
            results["map"].append({
                "name": name,
                "arch_pkg": pkg_info.get("name", name) if isinstance(pkg_info, dict) else str(pkg_info),
            })
        else:
            results["unknown"].append({"name": name, "reason": "no Arch mapping known"})
    return results


def generate_plan(audit: dict, mapping: dict) -> dict:
    """Build the full transformation plan."""
    source = audit.get("probe", {})
    os_ver = source.get("os_release", "").split('\n')
    nix_ver = [x for x in os_ver if x.startswith("VERSION_ID")][0] if os_ver else "unknown"

    services = classify_services(audit.get("services", []), mapping)
    secrets = plan_secrets(audit.get("secrets", []), mapping)
    partitions = plan_partitions(audit.get("storage", []))
    packages = plan_packages(audit.get("packages", []), audit, mapping)

    conflicts = []
    # Conflict detection
    if partitions.get("strategy") == "ghost-drive":
        btrfs_part = partitions.get("btrfs_partition")
        if btrfs_part and partitions.get("arch_root", "").startswith("new"):
            # Check if btrfs has enough free space
            conflicts.append({
                "type": "info",
                "msg": "btrfs partition needs defrag+balance before shrink",
                "resolvable": True,
            })

    # Check secrets for runtime-only paths
    for s in secrets:
        if s.get("runtime") and not s.get("target"):
            conflicts.append({
                "type": "warning",
                "msg": f"Runtime secret {s.get('source')} has no target path",
                "resolvable": "manual",
            })

    summary = {
        "services_mapped": len([s for s in services if s["status"] == "mapped"]),
        "services_defer": len([s for s in services if s["status"] == "defer"]),
        "services_unknown": len([s for s in services if s["status"] == "unknown"]),
        "secrets_mapped": len([s for s in secrets if s.get("target")]),
        "secrets_review": len([s for s in secrets if not s.get("target")]),
        "packages_map": len(packages["map"]),
        "packages_defer": len(packages["defer"]),
        "packages_unknown": len(packages["unknown"]),
    }

    return {
        "schema": "omnigate/plan/v1",
        "generated": datetime.now().isoformat(),
        "source": {
            "host": audit.get("target", source.get("target", "unknown")),
            "os": nix_ver,
            "kernel": source.get("uname", "unknown"),
            "kexec": source.get("kexec", False),
            "k3s_role": audit.get("k3s", {}).get("role", "none"),
        },
        "summary": summary,
        "services": services,
        "secrets": secrets,
        "partitions": partitions,
        "packages": packages,
        "conflicts": conflicts,
        "stages": [
            {"id": 0, "name": "discovery", "status": "complete", "desc": "audit.py scan executed"},
            {"id": 1, "name": "plan", "status": "complete", "desc": "plan.py generated this transformation plan"},
            {"id": 2, "name": "vm-test", "status": "pending", "desc": "Boot omarchy ISO in QEMU, validate configs restore"},
            {"id": 3, "name": "transform", "status": "pending", "desc": "Ghost-drive: shrink btrfs, install Arch+omarchy beside NixOS"},
            {"id": 4, "name": "restore", "status": "pending", "desc": "Bind-mount preserved dirs, port services, port secrets"},
        ],
        "methods": {
            "ghost": "Shrink btrfs, dual-boot with instant rollback",
            "kexec": "kexec into ISO installer (headless capable)",
            "vm": "Boot ISO in QEMU, test restore without touching host disk",
        },
    }


def render_plan_md(plan: dict) -> str:
    """Human-readable plan overview."""
    s = plan["summary"]
    src = plan["source"]
    lines = [
        "# Omniport Transformation Plan",
        "",
        f"Source: {src['host']} | {src['os']} | kernel: {src['kernel'][:60]}",
        f"k3s role: {src['k3s_role']} | kexec: {src['kexec']}",
        "",
        "## Summary",
        f"- Services: {s['services_mapped']} mapped, {s['services_defer']} defer to Omarchy, {s['services_unknown']} unknown",
        f"- Secrets: {s['secrets_mapped']} mapped, {s['secrets_review']} need review",
        f"- Packages: {s['packages_map']} mapped, {s['packages_defer']} deferred, {s['packages_unknown']} unknown",
        "",
        "## Services",
    ]
    for svc in plan["services"][:25]:
        if svc["status"] == "defer":
            lines.append(f"- **{svc['name']}** → defer to Omarchy")
        elif svc["status"] == "unknown":
            lines.append(f"- **{svc['name']}** → UNK (review: {svc.get('reason','')})")
        else:
            units = ", ".join(svc.get("systemd_units", [])) or "n/a"
            lines.append(f"- **{svc['name']}** → {svc['arch_equivalent']} ({units})")
    if len(plan["services"]) > 25:
        lines.append(f"- ... and {len(plan['services']) - 25} more")
    lines += ["", "## Secrets", ""]
    for sec in plan["secrets"]:
        tgt = sec.get("target", "UNMAPPED")
        lines.append(f"- {sec['source']} → {tgt} ({sec['type']})")
    lines += ["", "## Partitions", ""]
    p = plan["partitions"]
    lines.append(f"Strategy: {p['strategy']}")
    lines.append(f"Disk: {p.get('current_disk', '?')} | ghost partition: {p.get('ghost_partition', 'none')}")
    lines.append("Actions:")
    for a in p["actions"]:
        lines.append(f"  {a}")
    if p.get("warnings"):
        lines.append("Warnings:")
        for w in p["warnings"]:
            lines.append(f"  ⚠ {w}")
    lines += ["", "## Conflicts", ""]
    if plan["conflicts"]:
        for c in plan["conflicts"]:
            lines.append(f"[{c['type']}] {c['msg']}")
    else:
        lines.append("None detected.")
    lines += ["", "## Stages"]
    for st in plan["stages"]:
        lines.append(f"- Stage {st['id']}: {st['name']} — {st['status']} — {st['desc']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="plan.py", description="omnigate transformation planner")
    p.add_argument("--audit", required=True, help="Path to audit.py output JSON")
    p.add_argument("--out", default="plan.json", help="Output plan file (default: plan.json)")
    p.add_argument("--mapping", default=None, help="Custom nixos-to-arch mapping JSON")
    p.add_argument("--apply", action="store_true", help="Write plan files (default: dry-run)")
    p.add_argument("--show", action="store_true", help="Print human-readable plan after generating")
    p.add_argument("--method", choices=["ghost", "kexec", "vm", "full-wipe"], default="ghost",
                   help="Install method to plan for (default: ghost)")
    opts = p.parse_args(argv)

    audit = load_json(opts.audit)
    mapping = load_json(opts.mapping) if opts.mapping else load_mapping()

    plan = generate_plan(audit, mapping)
    # Override method if specified
    plan["methods"]["default"] = opts.method

    md = render_plan_md(plan)
    json_out = json.dumps(plan, indent=2)

    if opts.apply:
        Path(opts.out).write_text(json_out)
        Path(opts.out.replace(".json", ".md")).write_text(md)
        print(f"Wrote {opts.out} + {opts.out.replace('.json', '.md')}")
    else:
        print(f"dry-run: would write {opts.out}")
        print()

    if opts.show or not opts.apply:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""omnigate orchestrate — Stage 4 cluster transformation orchestrator.

Handles multi-host transformation with dependency ordering:
1. Sentry → Nexus → Zephyr+Forge (parallel)

Uses Git commits as synchronization barriers — each host's manifest + plan
+ scripts must be committed before proceeding to the next stage.
"""
from __future__ import annotations
import json, sys, argparse, subprocess
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent


# Cluster topology from AGENTS.md
CLUSTER = {
    "zephyr": {"role": "workstation", "ip": "10.1.0.110", "disk": "nvme0n1", "deps": ["sentry", "nexus"], "parallel": "forge"},
    "nexus": {"role": "k3s-server-builder", "ip": "10.0.1.120", "disk": "nvme0n1", "deps": ["sentry"], "parallel": None},
    "forge": {"role": "mining-gpu", "ip": "10.0.1.110", "disk": "nvme0n1", "deps": ["sentry", "nexus"], "parallel": "zephyr"},
    "sentry": {"role": "control-plane", "ip": "10.1.1.140", "disk": "nvme0n1", "deps": [], "parallel": None},
}

TRANSFORM_ORDER = ["sentry", "nexus", ("zephyr", "forge")]  # tuple = parallel


def build_cluster_plan() -> dict:
    """Generate ordered cluster transform plan with rollback safety."""
    plan = {
        "schema": "omnigate/cluster-plan/v1",
        "generated": datetime.now().isoformat(),
        "hosts": CLUSTER,
        "stages": [],
    }

    for i, stage in enumerate(TRANSFORM_ORDER):
        if isinstance(stage, str):
            plan["stages"].append({
                "order": i,
                "hosts": [stage],
                "parallel": False,
                "barrier": f"git-commit:manifests/{stage}",
                "rollback_barrier": f"git-tag:{stage}-pre-transform",
            })
        else:
            plan["stages"].append({
                "order": i,
                "hosts": list(stage),
                "parallel": True,
                "barrier": f"git-commit:plans/{{host}}",
                "rollback_barrier": f"git-tag:{{host}}-pre-transform",
            })

    return plan


def cmd_plan_cluster(args: argparse.Namespace) -> int:
    """Stage 4a: Generate the cluster-wide transformation plan."""
    PLAN = REPO / "plans" / "cluster"
    PLAN.mkdir(parents=True, exist_ok=True)

    cluster_plan = build_cluster_plan()
    (PLAN / "transform-plan.json").write_text(json.dumps(cluster_plan, indent=2))

    # Also write markdown version
    md = ["# Cluster Transformation Plan\n"]
    md.append(f"Generated: {cluster_plan['generated']}\n")
    md.append("## Execution Order\n\n")
    for stage in cluster_plan["stages"]:
        hosts = ", ".join(stage["hosts"])
        mode = "parallel" if stage["parallel"] else "sequential"
        md.append(f"{stage['order'] + 1}. **{hosts}** ({mode})\n")
        md.append(f"   - Rollback barrier: `{stage['rollback_barrier']}`\n")

    md.append("\n## Host Details\n\n")
    for host, info in CLUSTER.items():
        deps = ", ".join(info["deps"]) if info["deps"] else "none"
        md.append(f"### {host} ({info['role']})\n")
        md.append(f"- IP: {info['ip']}\n")
        md.append(f"- Disk: {info['disk']}\n")
        md.append(f"- Dependencies: {deps}\n")
        md.append(f"- Parallel: {info['parallel'] or 'none'}\n\n")

    (PLAN / "README.md").write_text("\n".join(md))

    import subprocess
    subprocess.run(["git", "-C", str(REPO), "add", str(PLAN)], check=True)
    subprocess.run(["git", "-C", str(REPO), "commit", "-m",
                    "plan: cluster-wide NixOS→Arch transformation order\n\nStages: sentry → nexus → (zephyr || forge)\nEach host: audit → plan → ghost-install → restore\nGit tag per host as rollback barrier"], check=True)

    print("Cluster transformation plan written:")
    print(f"  {PLAN}/transform-plan.json")
    print(f"  {PLAN}/README.md")
    print("\nExecution order:")
    for stage in cluster_plan["stages"]:
        hosts = ", ".join(stage["hosts"])
        mode = "parallel" if stage["parallel"] else "sequential"
        print(f"  {stage['order'] + 1}. {hosts} ({mode})")
    return 0


def cmd_audit_all(args: argparse.Namespace) -> int:
    """Stage 4b: Audit ALL cluster hosts and commit manifests."""
    import subprocess

    for host in CLUSTER:
        if args.hosts and host not in args.hosts:
            continue
        print(f"Auditing {host}...")
        result = subprocess.run([
            sys.executable, str(REPO / "omniport.py"), "audit", "--host", host
        ], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"  ✓ {host} audited")
        else:
            print(f"  ✗ {host} audit failed: {result.stderr[:200]}")
    return 0


def cmd_plan_all(args: argparse.Namespace) -> int:
    """Stage 4c: Generate plans for all audited hosts."""
    import subprocess

    for host in CLUSTER:
        plan_dir = REPO / "plans" / host
        if not plan_dir.exists():
            print(f"Skipping {host} — no audit manifest found")
            continue
        print(f"Planning {host}...")
        result = subprocess.run([
            sys.executable, str(REPO / "omniport.py"), "plan", "--host", host
        ], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"  ✓ {host} planned")
        else:
            print(f"  ✗ {host} plan failed: {result.stderr[:200]}")
    return 0


def cmd_transform(args: argparse.Namespace) -> int:
    """Stage 4d: Execute the full cluster transformation (WITH APPROVAL)."""
    print("=" * 60)
    print("CLUSTER TRANSFORMATION — NixOS → Arch+omarchy")
    print("=" * 60)
    print()
    print("WARNING: This will transform all hosts in order:")
    print("1. sentry (control plane — must go first)")
    print("2. nexus (k3s server)")
    print("3. zephyr || forge (parallel — workstation + mining)")
    print()
    print("Each host:")
    print("  a) Creates rollback tag (git tag)")
    print("  b) Runs ghost-subvolume install (non-destructive)")
    print("  c) Restores configs + secrets via symlinks")
    print("  d) Enables systemd services")
    print()
    print("Rollback: reboot to NixOS via GRUB menu entry.")
    print()

    if not args.yes:
        resp = input("Type 'confirm' to proceed: ")
        if resp != "confirm":
            print("Aborted.")
            return 0

    # Execute in order
    for i, stage in enumerate(TRANSFORM_ORDER):
        if isinstance(stage, str):
            hosts = [stage]
            parallel = False
        else:
            hosts = list(stage)
            parallel = True

        print(f"\n--- Stage {i + 1}: {', '.join(hosts)} ({'parallel' if parallel else 'sequential'}) ---")

        for host in hosts:
            # Tag for rollback
            tag = f"{host}-pre-transform-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            subprocess.run(["git", "-C", str(REPO), "tag", "-a", tag, "-m", f"{host} pre-transform rollback point"], check=False)
            print(f"  {host}: created rollback tag {tag}")

            # Execute ghost install
            script = REPO / "rollbacks" / host / "ghost-script.sh"
            if script.exists():
                print(f"  {host}: running ghost-script.sh")
                if args.execute:
                    r = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=600)
                    print(f"  {host}: exit {r.returncode}")
                    if r.returncode != 0:
                        print(f"  {host}: FAILED — check {host} logs, rollback via GRUB")
                else:
                    print(f"  {host}: DRY RUN — script not executed (add --execute to run)")
            else:
                print(f"  {host}: no ghost-script.sh found — run `omniport.py install --host {host} --method ghost` first")

    print("\n" + "=" * 60)
    print("TRANSFORMATION COMPLETE")
    print("Verify each host, then proceed to restore configs")
    print("=" * 60)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="orchestrate.py", description="omnigate Stage 4 — cluster orchestration")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_cluster = sub.add_parser("cluster-plan", help="Generate cluster-wide transform plan")
    p_audit = sub.add_parser("audit-all", help="Audit all cluster hosts")
    p_audit.add_argument("--hosts", nargs="+", help="Limit to specific hosts")
    p_plans = sub.add_parser("plan-all", help="Generate plans for all audited hosts")
    p_trans = sub.add_parser("transform", help="Execute full cluster transformation")
    p_trans.add_argument("--yes", action="store_true", help="Skip confirmation")
    p_trans.add_argument("--execute", action="store_true", help="Actually run the scripts (DANGEROUS)")

    opts = p.parse_args(argv)

    if opts.cmd == "cluster-plan":
        return cmd_plan_cluster(opts)
    elif opts.cmd == "audit-all":
        return cmd_audit_all(opts)
    elif opts.cmd == "plan-all":
        return cmd_plan_all(opts)
    elif opts.cmd == "transform":
        return cmd_transform(opts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
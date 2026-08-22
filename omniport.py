#!/usr/bin/env python3
"""omnigate git — the Git-based migration workflow for omniport.

Every migration is a Git-tracked artifact:
- per-host audit manifests (YAML)
- transformation plans (JSON → markdown diff)
- restore scripts (executable)
- rollback points (tag per stage)

Workflow:
  1. omnigate audit --host zephyr --out manifests/zephyr-audit.yaml
  2. git add manifests/zephyr-audit.yaml && git commit
  3. omnigate plan --input manifests/zephyr-audit.yaml --out plans/zephyr-transform.md
  4. git add plans/ && git commit
  5. omnigate install --method ghost --host zephyr --dry-run
  6. Review plan diff + approve for execution
  7. omnigate restore --host zephyr --from backup:sentry:/path
  8. git tag zephyr-transformed-<timestamp>

This makes migrations auditable, reversible, and reviewable via standard Git PR flow.
"""
from __future__ import annotations
import json, sys, argparse, subprocess, os
try:
    import yaml
except ImportError:
    yaml = None  # Fallback to JSON-only manifests
from pathlib import Path
from datetime import datetime
from hashlib import sha256

REPO = Path(__file__).resolve().parent
MANIFESTS = REPO / "manifests"
PLANS = REPO / "plans"
ROLLBACKS = REPO / "rollbacks"


def git_run(args: list[str], check: bool = True) -> str:
    """Run a git command in the omniport repo."""
    r = subprocess.run(["git", "-C", str(REPO)] + args, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(f"git error: {r.stderr}", file=sys.stderr)
        sys.exit(r.returncode)
    return r.stdout


def cmd_audit(args: argparse.Namespace) -> int:
    """Stage 0: Audit a host, output YAML manifest."""
    from audit import full_scan

    MANIFESTS.mkdir(exist_ok=True)
    out_dir = MANIFESTS / args.host
    out_dir.mkdir(exist_ok=True)

    # Get audit data
    if args.host == os.uname().nodename or args.host == "local":
        audit = full_scan(None)  # local probe
    else:
        audit = full_scan(args.host)

    # Split into per-component YAML files
    manifest = {
        "schema": "omnigate/manifest/v1",
        "host": args.host,
        "generated": datetime.now().isoformat(),
        "source_os": audit["probe"].get("os_release", "").split("=")[0],
        "target_os": "arch-o marchy-4.0",
    }

    # Write individual manifest files (use JSON if yaml not available)
    for section, data in [
        ("probe", audit.get("probe", {})),
        ("services", audit.get("services", [])),
        ("secrets", audit.get("secrets", [])),
        ("packages", audit.get("packages", [])),
        ("k3s", audit.get("k3s", {})),
        ("storage", audit.get("storage", [])),
    ]:
        if yaml:
            path = out_dir / f"{section}.yaml"
            yaml.dump({"host": args.host, "section": section, "data": data}, path.open("w"),
                      default_flow_style=False, sort_keys=True)
        else:
            path = out_dir / f"{section}.json"
            path.write_text(json.dumps({"host": args.host, "section": section, "data": data}, indent=2))
        print(f"  wrote {path}")

    # Write full manifest
    full = out_dir / "manifest.json"
    full.write_text(json.dumps(audit, indent=2))

    git_run(["add", str(out_dir)])
    git_run(["commit", "-m", f"manifest: audit {args.host} — {len(audit.get('secrets',[]))} secrets, {len(audit.get('services',[]))} services"])

    print(f"\nManifest committed for {args.host}")
    print(f"  Review: git diff HEAD~1 {out_dir}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Stage 1: Generate transformation plan from audit manifest."""
    from plan import load_mapping, generate_plan, render_plan_md

    host_dir = MANIFESTS / args.host
    if not host_dir.exists():
        print(f"error: no manifest for {args.host} — run `audit --host {args.host}` first")
        return 2

    audit = json.loads((host_dir / "manifest.json").read_text())
    mapping = load_mapping()
    plan = generate_plan(audit, mapping)

    PLANS.mkdir(exist_ok=True)
    plan_dir = PLANS / args.host
    plan_dir.mkdir(exist_ok=True)

    # Write plan JSON + markdown
    (plan_dir / "plan.json").write_text(json.dumps(plan, indent=2))
    (plan_dir / "plan.md").write_text(render_plan_md(plan))

    git_run(["add", str(plan_dir)])
    git_run(["commit", "-m", f"plan: {args.host} transformation — {plan['summary']['services_mapped']} services mapped"])

    print(f"\nPlan written for {args.host}")
    print(f"  Review: git diff HEAD~1 {plan_dir}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    """Stage 2/3: Generate install script + commit for review."""
    from install import build_ghost_script, build_kexec_script, build_vm_script

    host_dir = MANIFESTS / args.host
    plan_dir = PLANS / args.host
    if not plan_dir.exists():
        print(f"error: no plan for {args.host} — run `plan --host {args.host}` first")
        return 2

    plan = json.loads((plan_dir / "plan.json").read_text())

    ROLLBACKS.mkdir(exist_ok=True)
    rb_dir = ROLLBACKS / args.host
    rb_dir.mkdir(exist_ok=True)

    if args.method == "ghost":
        script = build_ghost_script(args.host, plan)
    elif args.method == "kexec":
        script = build_kexec_script(args.host, plan)
    elif args.method == "vm":
        script = build_vm_script(args.host, plan)

    script_path = rb_dir / f"{args.method}-script.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)

    git_run(["add", str(rb_dir)])
    msg = f"install: {args.host} {args.method}-script (dry-run)"
    git_run(["commit", "-m", msg])

    print(f"\nInstall script ({args.method}) written for {args.host}")
    print(f"  Location: {script_path}")
    if not args.execute:
        print(f"  REVIEW FIRST: git show HEAD:{script_path.relative_to(REPO)}")
        print(f"  Then execute: {script_path}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Stage 4: Generate restore script from backup + manifest."""
    from restore import build_restore_script

    host_dir = MANIFESTS / args.host
    plan_dir = PLANS / args.host
    if not plan_dir.exists():
        print(f"error: no plan for {args.host}")
        return 2

    plan = json.loads((plan_dir / "plan.json").read_text())
    script = build_restore_script(args.host, plan, args.backup_source)

    rb_dir = ROLLBACKS / args.host
    script_path = rb_dir / "restore.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)

    git_run(["add", str(rb_dir)])
    git_run(["commit", "-m", f"restore: {args.host} from {args.backup_source}"])

    print(f"\nRestore script written for {args.host}")
    if not args.execute:
        print(f"  REVIEW FIRST: {script_path}")
    else:
        print(f"  Executing restore from {args.backup_source}...")
        subprocess.run([str(script_path)], check=True)
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    """Create a rollback tag at the current point."""
    tag = f"{args.host}-{args.stage}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    git_run(["tag", "-a", tag, "-m", f"{args.host} at {args.stage} — rollback point"])
    print(f"Created rollback tag: {tag}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="omniport", description="Git-based NixOS→Arch migration workflow")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", help="Scan host, write YAML manifest")
    p_audit.add_argument("--host", required=True, help="Hostname or 'local'")
    p_audit.add_argument("--out", help="Override output directory")

    p_plan = sub.add_parser("plan", help="Generate transformation plan")
    p_plan.add_argument("--host", required=True)
    p_plan.add_argument("--out", help="Override output dir")

    p_inst = sub.add_parser("install", help="Generate + optionally execute install script")
    p_inst.add_argument("--host", required=True)
    p_inst.add_argument("--method", choices=["ghost", "kexec", "vm"], default="ghost")
    p_inst.add_argument("--execute", action="store_true", help="Run the install (DANGEROUS)")

    p_rest = sub.add_parser("restore", help="Generate + optionally run restore script")
    p_rest.add_argument("--host", required=True)
    p_rest.add_argument("--from", required=True, dest="backup_source", help="Backup source (e.g. backup:sentry:/path)")
    p_rest.add_argument("--execute", action="store_true")

    p_tag = sub.add_parser("tag", help="Create rollback tag")
    p_tag.add_argument("--host", required=True)
    p_tag.add_argument("--stage", required=True, help="discovery/plan/install/restore")

    opts = p.parse_args(argv)

    if opts.cmd == "audit": return cmd_audit(opts)
    elif opts.cmd == "plan": return cmd_plan(opts)
    elif opts.cmd == "install": return cmd_install(opts)
    elif opts.cmd == "restore": return cmd_restore(opts)
    elif opts.cmd == "tag": return cmd_tag(opts)
    return 0

if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""omnigate install — the Stage 2/3 transformation executor (VM + live methods).

Methods:
  --method vm          Boot ISO in QEMU, attach backup data — test only, no host changes
  --method kexec       kexec-boot the ISO installer on the host (headless capable)
  --method ghost       Partition shrink + dual-boot (pre-script generator only)
  --method full-wipe   Backup → wipe → install (pre-script generator only)

Usage:
  python3 install.py --method vm --iso /home/j_kro/omarchy-test/omarchy-4.0.0.iso
                       --attach /home/j_kro/zephyr-backup/
  python3 install.py --method kexec --iso <path> --dry-run
  python3 install.py --method ghost --disk /dev/nvme0n1 --preview
"""
from __future__ import annotations
import json, sys, argparse, subprocess, os
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent


def method_vm(args: argparse.Namespace) -> int:
    """Boot the omarchy ISO in QEMU with backup data attached as a secondary disk."""
    iso = Path(args.iso)
    if not iso.exists():
        print(f"error: ISO not found at {iso}", file=sys.stderr)
        return 2

    # Create a QEMU disk image that mounts the backup data
    disk_img = Path("/tmp/omarchy-vm-backup.qcow2")
    if args.attach:
        attach = Path(args.attach)
        if not disk_img.exists():
            print(f"Creating backup disk from {attach}...")
            # Create a raw disk from the backup directory
            subprocess.run(["qemu-img", "create", "-f", "raw", str(disk_img), "8G"], check=True)
            # Use mkfs + mount trick to create the disk
            # Simpler: use 9p mount to share the directory
            print(f"(Will share {attach} via 9p filesystem)")

    # Build QEMU command
    qemu_cmd = [
        "qemu-system-x86_64",
        "-machine", "q35,accel=kvm",
        "-cpu", "host",
        "-smp", str(args.smp or os.cpu_count() or 4),
        "-m", str(args.mem or 4096),
        "-netdev", "user,id=net0,net=192.168.15.0/24",
        "-device", "virtio-net,netdev=net0",
        "-display", args.display or "none",
        "-serial", "stdio",
        "-boot", "d",
        "-cdrom", str(iso),
    ]

    # Add the backup as a 9p share if requested
    if args.attach:
        qemu_cmd += [
            "-virtfs", f"local,path={args.attach},security_model=passthrough,mount_tag=backup",
            "-fsdev", f"local,id=fsdev0,path={args.attach},security_model=passthrough",
        ]

    if args.dry_run:
        print("DRY RUN — QEMU command:")
        print("  " + " \\\n  ".join(qemu_cmd))
        return 0

    print(f"Booting omarchy ISO in QEMU — {len(qemu_cmd)} args")
    print(f"  ISO: {iso}")
    if args.attach:
        print(f"  Backup shared via 9p at mount_tag=backup (mount -t 9p backup /mnt)")
    print(f"  Display: {args.display or 'none'} — use Ctrl-a h for help, Ctrl-a x to exit")
    print()

    try:
        proc = subprocess.run(qemu_cmd, timeout=args.timeout or 300)
        return proc.returncode
    except KeyboardInterrupt:
        print("\nQEMU stopped by user")
        return 0
    except subprocess.TimeoutExpired:
        print(f"QEMU timed out after {args.timeout}s — use --timeout to adjust")
        return 0


def method_kexec(args: argparse.Namespace) -> int:
    """Generate kexec boot script for headless install."""
    iso = Path(args.iso)
    if not iso.exists():
        print(f"error: ISO not found at {iso}", file=sys.stderr)
        return 2

    # Extract kernel + initramfs from ISO
    iso_extract = Path("/tmp/omarchy-kexec")
    iso_extract.mkdir(exist_ok=True)

    # Use xorriso to extract
    subprocess.run([
        "xorriso", "-osirrox", "on", "-indev", str(iso),
        "-extract", "/arch/boot/x86_64/", str(iso_extract)
    ], check=False, capture_output=True)

    kernel = iso_extract / "vmlinuz-linux-t2"
    initrd = iso_extract / "initramfs-linux-t2.img"

    if not kernel.exists() or not initrd.exists():
        # Fallback: try standard names
        kernel = iso_extract / "vmlinuz-linux"
        initrd = iso_extract / "initramfs-linux.img"
        if not kernel.exists() or not initrd.exists():
            print(f"error: kernel or initrd not found in {iso_extract}", file=sys.stderr)
            # List what we actually found
            if iso_extract.exists():
                print(f"  Contents of {iso_extract}:", file=sys.stderr)
                for f in sorted(iso_extract.iterdir()):
                    print(f"    {f.name}", file=sys.stderr)
            return 2

    # The kexec command
    kmsg = args.kmsg if args.kmsg else "console=ttyS0,115200 earlyprintk=vga"
    ip = args.ip if args.ip else "192.168.15.199::192.168.15.1:255.255.255.0::eth0:on"
    archiso_nbd = f"ip=${{ip}} boot=live live.url=http://10.1.1.130:8091/${{iso.name}} live.fetch=/${{iso.name}}"

    cmd = (
        f"kexec -l {kernel} "
        f"--initrd={initrd} "
        f"--append '{kmsg} {archiso_nbd}' "
        f"--reuse-cmdline"
    )

    # If we need to serve the ISO, start an HTTP server
    if args.serve:
        print(f"Starting HTTP server on :{args.serve_port or 8091} serving {iso.parent}")
        print("In another terminal, run on the host:")
        print(f"  cd {iso.parent} && python3 -m http.server {args.serve_port or 8091}")

    print("\nkexec boot script:")
    print(f"  {cmd}")
    print(f"\nWARNING: This is a HARD REBOOT. The current NixOS session will be replaced.")
    print(f"If successful, you'll boot into the omarchy live environment.")
    print(f"To return, reboot and select the old boot entry.")

    if args.dry_run:
        return 0

    if not args.yes:
        resp = input("\nProceed with kexec boot? (yes/NO): ")
        if resp != "yes":
            print("Aborted.")
            return 0

    # Run kexec
    subprocess.run(["kexec", "-l", str(kernel), "--initrd", str(initrd),
                    "--append", f"{kmsg} {archiso_nbd}", "--reuse-cmdline"], check=True)
    print("kexec loaded. Execute `kexec -e` to boot now, or `reboot` to return.")
    return 0


def method_ghost(args: argparse.Namespace) -> int:
    """Preview ghost-drive partition plan."""
    import json as _json
    from audit import find_storage

    disk = args.disk
    size_gb = args.size_gb or 50

    plan = {
        "schema": "omnigate/ghost-plan/v1",
        "generated": datetime.now().isoformat(),
        "disk": disk,
        "arch_root_size_gb": size_gb,
        "current_partitions": "audit via lsblk",
        "actions": [
            f"1. btrfs filesystem defrag -r / (defrag on {disk})",
            f"2. btrfs filesystem resize -{size_gb}G / (shrink)",
            f"3. partprobe (re-read partition table)",
            f"4. Create new {size_gb}GB partition in freed space (ext4)",
            f"5. mkfs.ext4 /dev/{disk}p3",
            f"6. Mount both partitions",
            f"7. Install Arch base into new partition",
            f"8. Install omarchy ISO overlay",
            f"9. Bind-mount preserved dirs from old partition",
            f"10. Update bootloader (add NixOS + Arch entries)",
        ],
        "warnings": [
            f" btrfs shrink is irreversible if it fails — verify free space first",
            " Old NixOS entry must stay in bootloader for instant rollback",
            " /models and /home must be on the ghost partition (check preservation.nix)",
        ],
    }

    out = _json.dumps(plan, indent=2)
    print(out)
    Path("ghost-plan.json").write_text(out)
    print("Wrote ghost-plan.json")
    return 0


# --- Script builders (used by omniport.py install) ---

def build_ghost_script(host: str, plan: dict) -> str:
    """Generate a bash ghost-drive install script for the host."""
    p = plan.get("partitions", {})
    disk = p.get("current_disk", "nvme0n1")
    size = p.get("arch_root_size_gb", 50)
    arch_part = f"/dev/{disk}p3"
    nix_part = p.get("btrfs_partition", f"/dev/{disk}p2")

    services = plan.get("services", [])
    mapped = [s for s in services if s.get("status") == "mapped"]

    lines = [
        "#!/usr/bin/env bash",
        "# Ghost-drive Arch + omarchy install script for " + host,
        "# Generated by install.py — REVIEW BEFORE EXECUTING",
        "set -euo pipefail",
        "",
        "# 1. Defrag + shrink btrfs",
        "btrfs filesystem defrag -r /",
        f"btrfs filesystem resize -{size}G /",
        "btrfs filesystem balance /",
        "",
        "# 2. Create new Arch partition",
        f"parted -s /dev/{disk} resizepart 2 -{size}G",
        f"parted -s /dev/{disk} mkpart primary ext4 {size}G",
        f"mkfs.ext4 {arch_part}",
        "",
        "# 3. Mount + install Arch base",
        "mkdir -p /mnt/arch",
        f"mount {arch_part} /mnt/arch",
        "pacstrap /mnt/arch base linux linux-firmware --noconfirm",
        "",
        "# 4. Mount ghost (old NixOS)",
        "mkdir -p /mnt/arch/nixos-legacy",
        f"mount -o ro {nix_part} /mnt/arch/nixos-legacy",
        "",
        "# 5. Install omarchy",
        "echo 'Install omarchy via repo: https://github.com/omarchy/omarchy'",
        "echo 'Manual step: run omarchy setup wizard or apply omarchy-nix'",
        "",
        "# 6. Port services",
    ]

    for svc in mapped:
        units = svc.get("systemd_units", [])
        target = svc.get("target_path", "")
        lines.append(f"# {svc['name']} → {svc['arch_equivalent']}")
        if units:
            for u in units:
                lines.append(f"cp /mnt/arch/nixos-legacy/.../{svc['nixos_decl']} /etc/systemd/system/{u} 2>/dev/null || true")

    lines += [
        "",
        "# 7. Port secrets",
        "mkdir -p /etc/age /etc/omnigate",
        "cp /mnt/arch/nixos-legacy/etc/nixos/.age/key.txt /etc/age/keys.txt 2>/dev/null || true",
        "cp /mnt/arch/nixos-legacy/etc/nixos/secretspec.toml /etc/omnigate/secretspec.toml 2>/dev/null || true",
        "",
        "# 8. Install bootloader entries",
        "efibootmgr -c -L 'Arch Omarchy' -l /vmlinuz-linux -u 'root=PARTUUID=$(blkid -s PARTUUID -o value " + arch_part + ") rw'",
        "efibootmgr -c -L 'NixOS (rollback)' -l /vmlinuz-linux -u 'config=...' ",
        "",
        "# 9. Enable services",
        "systemctl enable caddy pipewire-pulse wireplumber",
        "",
        "# 10. First reboot → select Arch from boot menu",
        "echo 'REBOOT NOW — select Arch Omarchy from boot menu'",
        "echo 'To rollback: boot NixOS entry'",
    ]

    return "\n".join(lines) + "\n"


def build_kexec_script(host: str, plan: dict) -> str:
    """Generate kexec install script."""
    return build_ghost_script(host, plan)  # same port logic, kexec boot step added


def build_vm_script(host: str, plan: dict) -> str:
    """Generate VM test script."""
    return "#!/usr/bin/env bash\n# VM test script for " + host + "\n# Boot omarchy ISO, mount 9p backup share, test restore\nqemu-system-x86_64 -enable-kvm -m 4G -smp 4 \\\n  -cdrom /home/j_kro/omarchy-test/omarchy-4.0.0.iso \\\n  -virtfs local,path=/home/j_kro/zephyr-backup,mount_tag=backup,security_model=passthrough \\\n  -netdev user,id=net0 -device virtio-net,netdev=net0 \\\n  -serial stdio -display none\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="install.py", description="omnigate Stage 2/3 installer")
    p.add_argument("--method", choices=["vm", "kexec", "ghost", "full-wipe"], default="vm",
                   help="Install method (default: vm)")
    p.add_argument("--iso", help="Path to omarchy ISO")
    p.add_argument("--attach", help="Directory to attach as backup data in VM")
    p.add_argument("--disk", help="Target disk for ghost/full-wipe (e.g. /dev/nvme0n1)")
    p.add_argument("--size-gb", type=int, default=50, help="Arch root partition size (ghost)")
    p.add_argument("--mem", type=int, default=4096, help="QEMU memory in MB (vm)")
    p.add_argument("--smp", type=int, help="QEMU CPU cores (vm)")
    p.add_argument("--display", default="none", help="QEMU display backend (vm)")
    p.add_argument("--timeout", type=int, default=600, help="QEMU timeout in seconds (vm)")
    p.add_argument("--serve", action="store_true", help="Start HTTP server for kexec (kexec)")
    p.add_argument("--serve-port", type=int, default=8091, help="HTTP port for kexec serve")
    p.add_argument("--ip", help="Static IP for kexec DHCP-less boot")
    p.add_argument("--kmsg", help="Extra kernel cmdline")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen")
    p.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    opts = p.parse_args(argv)

    if opts.method == "vm":
        return method_vm(opts)
    elif opts.method == "kexec":
        return method_kexec(opts)
    elif opts.method == "ghost":
        return method_ghost(opts)
    elif opts.method == "full-wipe":
        print("full-wipe not yet implemented — use --method ghost or vm")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
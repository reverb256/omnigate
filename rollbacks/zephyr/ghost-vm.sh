#!/usr/bin/env bash
# ghost-vm.sh — Living Ghost VM: boot the frozen NixOS as a VM (no bare-metal reboot)
#
# After the transform, the old NixOS partition is a Ghost Drive (frozen snapshot
# + Discoverable Partitions GUID). If you need to inspect old configs, run a
# NixOS-only tool, or "roll back" for real work during the 1-month window,
# launch it as a VM with virtiofs DAX — the old OS keeps running while Arch
# owns the metal. Zero NixOS on bare metal; the ghost is a guest.
#
# PREREQ: qemu + virtiofsd installed on the Arch host. The old partition is the
# qcow2 backing file (read-only) so the ghost can't corrupt the frozen source.
set -euo pipefail

HOST="${HOST:-zephyr}"
DISK="${DISK:-/dev/nvme0n1}"
PART="${PART:-${DISK}p2}"
GHOST_SNAPSHOT="@nixos-ghost-$(date +%Y%m%d)"
BACKING="/var/lib/ghost/${HOST}-nixos.qcow2"
VM_IMG="/var/lib/ghost/${HOST}-nixos-rw.qcow2"

echo "=== Living Ghost VM: $HOST ==="

# 1. Create a qcow2 that uses the frozen NixOS partition as a read-only backing file.
#    Writes from the VM land in the overlay (VM_IMG), never touching the ghost.
mkdir -p /var/lib/ghost
if [[ ! -f "$BACKING" ]]; then
  # Build a qcow2 whose backing is the raw partition (read-only)
  sudo qemu-img create -f qcow2 -b "/dev/disk/by-partlabel/${GHOST_SNAPSHOT}" -F raw "$BACKING" 2>/dev/null \
    || sudo qemu-img create -f qcow2 -b "$PART" -F raw "$BACKING"
fi
# RW overlay on top of the read-only backing
[[ -f "$VM_IMG" ]] || qemu-img create -f qcow2 -b "$BACKING" -F qcow2 "$VM_IMG" 40G

# 2. Boot with virtiofs DAX (page cache shared into guest → ~20x faster, no double cache)
#    The Arch host's /nixos-ghost (the auto-mounted old partition) is exposed to
#    the VM via virtiofs so the ghost can read live host state if needed.
sudo virtiofsd --socket-path=/tmp/ghost-virtiofs.sock \
  --shared-dir=/nixos-ghost --cache=always &

sudo qemu-system-x86_64 \
  -machine q35,accel=kvm -cpu host -smp 4 -m 8192 \
  -drive file="$VM_IMG",format=qcow2,if=virtio \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:2223-:22 -device virtio-net,netdev=net0 \
  -chardev socket,path=/tmp/ghost-virtiofs.sock,id=fs0 \
  -device vhost-user-fs-pci,chardev=fs0,tag=ghost \
  -display gtk -name "NixOS Ghost ($HOST)" &

echo "Living Ghost VM launched. SSH: ssh -p 2223 root@127.0.0.1"
echo "virtiofs tag 'ghost' mounts /nixos-ghost inside the VM."
echo "Stop: kill the qemu + virtiofsd processes. Overlay ($VM_IMG) holds VM writes."

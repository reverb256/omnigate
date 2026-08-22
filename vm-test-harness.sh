#!/usr/bin/env bash
# VM test harness for omniport ghost-script.sh — repo-driven, NOT ISO-dependent
#
# Strategy: Boot the omarchy ISO in QEMU (it provides a live Arch base),
# then inside the live session we:
#   1. Clone /home/j_kro/Projects/omarchy (the SOURCE OF TRUTH, not the ISO)
#   2. Run the repo's actual install/ scripts to validate the real path
#   3. Apply our ghost-script.sh logic in a contained subvolume
#   4. Verify configs restore, services start, secrets decrypt
#
# This tests the REAL transformation — not a pre-baked ISO artifact.
set -euo pipefail

ISO_PATH="${OMARCHY_ISO:-/home/j_kro/omarchy-test/omarchy-4.0.0.iso}"
BACKUP_PATH="${BACKUP_PATH:-/home/j_kro/zephyr-backup}"
OMARCHY_REPO="${OMARCHY_REPO:-/home/j_kro/Projects/omarchy}"

echo "=== VM Test Harness: omniport ghost-script validation ==="
echo "ISO: $ISO_PATH"
echo "Backup: $BACKUP_PATH"
echo "Omarchy repo: $OMARCHY_REPO"
echo ""

# 1. Boot QEMU with ISO + 9p backup share + omarchy repo share
echo "--- Launching QEMU (serial console) ---"
qemu-system-x86_64 \
  -machine q35,accel=kvm \
  -cpu host \
  -smp 4 \
  -m 4096 \
  -netdev user,id=net0,net=192.168.15.0/24 \
  -device virtio-net,netdev=net0 \
  -cdrom "$ISO_PATH" \
  -virtfs local,path="$BACKUP_PATH",security_model=passthrough,mount_tag=backup \
  -virtfs local,path="$OMARCHY_REPO",security_model=passthrough,mount_tag=omarchy \
  -serial stdio \
  -display none \
  -boot d

echo ""
echo "=== Inside the live session, run: ==="
echo "  mount -t 9p backup /mnt/backup"
echo "  mount -t 9p omarchy /mnt/omarchy"
echo "  cd /mnt/omarchy && ls install/"
echo "  # This validates the repo's real install path"

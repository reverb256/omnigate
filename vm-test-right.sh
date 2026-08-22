#!/usr/bin/env bash
# omniport VM test — repo-driven, btrfs-isolated, root-accessible
#
# Design:
#   1. Boot omarchy ISO LIVE (root@ttyS0, no TUI installer)
#   2. Attach 20G qcow2 disk -> format btrfs INSIDE vm (host mkfs is blocked)
#   3. 9p share zephyr backup -> validates restore.sh symlink logic
#   4. git clone https://github.com/basecamp/omarchy -> tests SOURCE OF TRUTH
#   5. Run ghost-script.sh subvolume logic on the test disk (non-destructive)
#
# No new VM sprawl: reuses the single QEMU invocation pattern.
set -euo pipefail

ISO="${OMARCHY_ISO:-/home/j_kro/omarchy-test/omarchy-4.0.0.iso}"
BACKUP="${BACKUP_PATH:-/home/j_kro/zephyr-backup}"
TESTDISK="${TEST_DISK:-/tmp/btrfs-test.qcow2}"
REPO_URL="${OMARCHY_REPO_URL:-https://github.com/basecamp/omarchy}"

# Create test disk if missing (qcow2, no mkfs on host)
[ -f "$TESTDISK" ] || qemu-img create -f qcow2 "$TESTDISK" 20G

echo "=== omniport VM test ==="
echo "ISO:     $ISO"
echo "Backup:  $BACKUP"
echo "TestDisk:$TESTDISK (btrfs formatted INSIDE vm)"
echo "Repo:    $REPO_URL"
echo ""

qemu-system-x86_64 \
  -machine q35,accel=kvm -cpu host -smp 4 -m 4096 \
  -netdev user,id=net0,net=192.168.15.0/24 \
  -device virtio-net,netdev=net0 \
  -cdrom "$ISO" -boot d \
  -drive file="$TESTDISK",format=qcow2,if=virtio,index=1 \
  -virtfs local,path="$BACKUP",security_model=passthrough,mount_tag=backup \
  -serial stdio -display none

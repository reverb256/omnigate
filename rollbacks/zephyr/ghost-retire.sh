#!/usr/bin/env bash
# ghost-retire.sh — retire the Ghost Drive after the 1-month rollback window
#
# Deletes the frozen NixOS snapshot and reverts the GPT GUID so the old
# partition is no longer auto-mounted by systemd-gpt-auto-generator.
# Run ONLY after you're confident Arch+omarchy is the permanent OS.
#
# NON-DESTRUCTIVE of Arch: this only touches the old NixOS snapshot + GPT GUID.
# If you change your mind, the snapshot is already gone — so confirm first.
set -euo pipefail

HOST="${HOST:-zephyr}"
DISK="${DISK:-/dev/nvme0n1}"
PART="${PART:-${DISK}p2}"
GHOST_SNAPSHOT="@nixos-ghost-$(date +%Y%m%d)"

echo "=== Retire Ghost Drive: $HOST ==="
echo "This deletes the frozen NixOS snapshot + reverts GPT GUID."
read -r -p "Type 'RETIRE' to confirm: " CONFIRM
[[ "$CONFIRM" == "RETIRE" ]] || { echo "Aborted."; exit 1; }

# 1. Delete the read-only snapshot (frees CoW blocks)
if sudo btrfs subvolume list "$PART" 2>/dev/null | grep -q "$GHOST_SNAPSHOT"; then
  sudo btrfs subvolume delete "$PART" "$GHOST_SNAPSHOT"
  echo "Deleted snapshot: $GHOST_SNAPSHOT"
fi

# 2. Revert GPT GUID to a generic Linux partition type (no longer discoverable)
sudo sfdisk --part-type "$DISK" "$(echo "$PART" | grep -oE '[0-9]+$')" 0fc63daf-8483-4772-8e79-3d69d8477de4
echo "Reverted PARTTYPE -> generic Linux (Ghost Drive off)"

# 3. Remove the auto-mount point
sudo umount /nixos-ghost 2>/dev/null || true
sudo rmdir /nixos-ghost 2>/dev/null || true

echo "Ghost Drive retired. Arch+omarchy is now the sole OS."

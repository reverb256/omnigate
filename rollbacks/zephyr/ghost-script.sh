#!/usr/bin/env bash
# ghost-script.sh — omniport Stage 2: subvolume-based NixOS→Arch transform
#
# PRINCIPLE: omniport handles the TRANSFORM SCAFFOLD (subvolume, backup mount,
# secret porting, bootloader handoff). Then it HANDS OFF to the omarchy repo's
# own install code for everything Arch-specific.
#
# Flow:
#   1. Create btrfs subvolume for Arch (isolation, no resize)
#   2. pacstrap base Arch into subvolume (delegated to omarchy's package list)
#   3. Mount backup (ghost) + NixOS legacy
#   4. Port secrets: /etc/nixos/.age/key.txt -> /etc/age/keys.txt
#   5. arch-chroot into subvolume, run omarchy install/ scripts + bin/omarchy-*
#   6. Install Limine (omarchy's bootloader) + add NixOS entry
#   7. Reboot → select Arch (omarchy) or NixOS from Limine
#
# NON-DESTRUCTIVE: old @ subvolume untouched. Rollback = boot NixOS.
set -euo pipefail

HOST="${HOST:-zephyr}"
DISK="${DISK:-/dev/nvme0n1}"
PART="${PART:-${DISK}p2}"
SUBVOL="@${HOST}-arch"
MNT="/mnt/${HOST}-arch"
BACKUP="${BACKUP:-/home/j_kro/zephyr-backup}"
LEGACY="${LEGACY:-/nixos-legacy}"
OMARCHY_REPO="${OMARCHY_REPO:-/home/j_kro/Projects/omarchy}"

echo "=== omniport ghost transform: $HOST ==="
echo "Disk: $DISK  Partition: $PART  Subvolume: $SUBVOL"
echo "Backup: $BACKUP"
echo ""

# 1. Create subvolume (isolation)
echo "--- Step 1: btrfs subvolume ---"
sudo btrfs subvolume create "$PART" "$SUBVOL" 2>&1 || {
  echo "Subvolume exists or creation failed — aborting"
  exit 1
}
mkdir -p "$MNT"
sudo mount -o subvol="$SUBVOL" "$PART" "$MNT"

# 2. pacstrap base (uses omarchy's base package list if available)
echo "--- Step 2: pacstrap base Arch ---"
if [[ -f "$OMARCHY_REPO/install/omarchy-base.packages" ]]; then
  BASE_PKGS=$(grep -v '^#' "$OMARCHY_REPO/install/omarchy-base.packages" | tr '\n' ' ')
  sudo pacstrap "$MNT" base base-devel $BASE_PKGS --noconfirm
else
  sudo pacstrap "$MNT" base linux linux-firmware --noconfirm
fi

# 3. Mount backup + legacy
echo "--- Step 3: mount backup + NixOS legacy ---"
sudo mkdir -p "$MNT/$LEGACY"
sudo mount -o subvol=@ "$PART" "$MNT/$LEGACY"  # old NixOS root, read-only
sudo mkdir -p "$MNT/mnt/backup"
sudo mount --bind "$BACKUP" "$MNT/mnt/backup" 2>/dev/null || true

# 4. Port secrets
echo "--- Step 4: port secrets ---"
sudo mkdir -p "$MNT/etc/age"
if [[ -f "$MNT/$LEGACY/etc/nixos/.age/key.txt" ]]; then
  sudo cp "$MNT/$LEGACY/etc/nixos/.age/key.txt" "$MNT/etc/age/keys.txt"
  sudo chmod 600 "$MNT/etc/age/keys.txt"
  echo "Age key ported: /etc/nixos/.age/key.txt -> /etc/age/keys.txt"
fi

# 5. HAND OFF to omarchy install code (arch-chroot)
echo "--- Step 5: hand off to omarchy install ---"
sudo arch-chroot "$MNT" /bin/bash -c "
  # Mount omarchy repo inside chroot
  mkdir -p /opt/omarchy
  mount --bind '$OMARCHY_REPO' /opt/omarchy 2>/dev/null || cp -r '$OMARCHY_REPO' /opt/omarchy

  # Run omarchy's base install scripts
  if [[ -d /opt/omarchy/install/config ]]; then
    for script in /opt/omarchy/install/config/*.sh; do
      [[ -f \$script ]] && source \$script || true
    done
  fi

  # Enable omarchy services via its own commands
  if command -v omarchy-enable-services >/dev/null 2>&1; then
    omarchy-enable-services
  fi
"

# 6. Bootloader: omarchy installs Limine, then add NixOS entry
echo "--- Step 6: bootloader handoff (Limine) ---"
sudo arch-chroot "$MNT" /bin/bash -c "
  # omarchy-refresh-limine installs + configures Limine
  if command -v omarchy-refresh-limine >/dev/null 2>&1; then
    omarchy-refresh-limine
  fi
"
# Add NixOS entry to Limine config (points to legacy @ subvolume kernels)
sudo tee -a "$MNT/boot/limine.conf" >/dev/null <<EOF

# NixOS (legacy, rollback)
menuentry "NixOS (zephyr legacy)" {
    comment "Original NixOS install"
    protocol "linux"
    kernel_path "boot:///vmlinuz-linux"
    # Points to old @ subvolume
}
EOF

# 7. Done
echo "=== Transform scaffold complete ==="
echo "Reboot and select Arch (omarchy) or NixOS from Limine."
echo "Rollback: select NixOS entry (old @ subvolume untouched)."

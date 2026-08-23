#!/usr/bin/env bash
# ghost-script.sh — omniport Stage 2: subvolume-based NixOS→Arch transform
#
# PRINCIPLE: omniport = transform scaffold (subvolume, user/host preseed,
# secret port, fstab, bootloader handoff). Then HANDS OFF to omarchy's own
# install code for everything Arch-specific (config + user setup + services).
#
# omarchy install flow (from repo):
#   install/config/all.sh   → system config (services, firewall, theme, ssh)
#   install/user/all.sh     → user env (git, theme, keyring, mise)
#   bin/omarchy-provision-owner → interactive user creation (gum TUI)
#
# For non-interactive transform we preseed the owner and call the *all.sh
# scripts directly instead of the TUI provision-owner.
set -euo pipefail

HOST="${HOST:-zephyr}"
DISK="${DISK:-/dev/nvme0n1}"
PART="${PART:-${DISK}p2}"
SUBVOL="@${HOST}-arch"
HOME_SUBVOL="@home"          # reuse existing @home (user data preserved)
GHOST_SNAPSHOT="@nixos-ghost-$(date +%Y%m%d)"   # read-only 1-month safety net
MNT="/mnt/${HOST}-arch"
BACKUP="${BACKUP:-/home/j_kro/zephyr-backup}"
LEGACY="${LEGACY:-/nixos-legacy}"
OMARCHY_REPO="${OMARCHY_REPO:-/home/j_kro/Projects/omarchy}"
USERNAME="${USERNAME:-j_kro}"
HOSTNAME="${HOSTNAME:-zephyr}"
KEYBOARD="${KEYBOARD:-us}"
TIMEZONE="${TIMEZONE:-America/Winnipeg}"

echo "=== omniport ghost transform: $HOST ==="
echo "Disk: $DISK  Partition: $PART  Subvolume: $SUBVOL"
echo "Ghost snapshot: $GHOST_SNAPSHOT (read-only, 1-month rollback)"
echo "User: $USERNAME  Hostname: $HOSTNAME  TZ: $TIMEZONE"
echo ""

# 0. GHOST DRIVE: freeze NixOS as a permanent, reachable lower layer (non-destructive)
#    - read-only btrfs snapshot (CoW, ~0 space, uncorruptable)
#    - rewrite old partition GPT GUID -> Discoverable Partitions Spec so
#      systemd-gpt-auto-generator auto-mounts it forever under Arch
echo "--- Step 0: Ghost Drive (freeze + permanent mount) ---"
if ! sudo btrfs subvolume list "$PART" 2>/dev/null | grep -q "$GHOST_SNAPSHOT"; then
  sudo btrfs subvolume snapshot -r "$PART" "@" "$GHOST_SNAPSHOT"
  echo "Frozen read-only snapshot: $GHOST_SNAPSHOT"
fi
# Rewrite GPT type GUID to root (x8664) discoverable-partitions type so the
# old NixOS partition auto-mounts as /nixos-ghost under Arch (reversible).
OLD_GUID=$(lsblk -no PARTTYPE "$PART" 2>/dev/null)
if [[ "$OLD_GUID" != "4f68bce3-e8cd-4db1-96e7-fbcaf984b709" ]]; then
  echo "Old PARTTYPE: $OLD_GUID"
  sudo sfdisk --part-type "$DISK" "$(echo "$PART" | grep -oE '[0-9]+$')" 4f68bce3-e8cd-4db1-96e7-fbcaf984b709
  echo "Rewrote PARTTYPE -> Discoverable Partitions root (Ghost Drive on)"
fi
mkdir -p /nixos-ghost

# 1. Create subvolume (isolation, no resize)
echo "--- Step 1: btrfs subvolume ---"
if ! sudo btrfs subvolume list "$PART" 2>/dev/null | grep -q "$SUBVOL"; then
  sudo btrfs subvolume create "$PART" "$SUBVOL"
fi
mkdir -p "$MNT"
sudo mount -o subvol="$SUBVOL" "$PART" "$MNT"

# 2. pacstrap base + omarchy package sets
echo "--- Step 2: pacstrap ---"
BASE_PKGS=$(grep -v '^#' "$OMARCHY_REPO/install/omarchy-base.packages" 2>/dev/null | tr '\n' ' ')
OTHER_PKGS=$(grep -v '^#' "$OMARCHY_REPO/install/omarchy-other.packages" 2>/dev/null | tr '\n' ' ')
sudo pacstrap "$MNT" base base-devel $BASE_PKGS $OTHER_PKGS --noconfirm

# 3. fstab — subvolume-aware (omarchy assumes archiso did this; we do it)
echo "--- Step 3: fstab (subvolume-aware) ---"
sudo tee "$MNT/etc/fstab" >/dev/null <<EOF
# omniport-generated fstab for $HOST Arch subvolume
PARTUUID=$(blkid -s PARTUUID -o value "$PART")
/dev/disk/by-partuuid/$PARTUUID  /  btrfs  subvol=$SUBVOL,compress=zstd:3  0  0
/dev/disk/by-partuuid/$PARTUUID  /home  btrfs  subvol=$HOME_SUBVOL,compress=zstd:3  0  0
EOF

# 4. hostname + locale + timezone (preseed, non-interactive)
echo "--- Step 4: system identity ---"
sudo arch-chroot "$MNT" /bin/bash -c "
  echo '$HOSTNAME' > /etc/hostname
  ln -sf /usr/share/zoneinfo/$TIMEZONE /etc/localtime
  hwclock --systohc
  echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen
  locale-gen
  echo 'LANG=en_US.UTF-8' > /etc/locale.conf
  # keyboard for omarchy setup-form compatibility
  echo 'KEYMAP=$KEYBOARD' > /etc/vconsole.conf
"

# 5. Mount backup + legacy NixOS
echo "--- Step 5: mount backup + legacy ---"
sudo mkdir -p "$MNT/$LEGACY"
sudo mount -o subvol=@ "$PART" "$MNT/$LEGACY"
sudo mkdir -p "$MNT/mnt/backup"
sudo mount --bind "$BACKUP" "$MNT/mnt/backup" 2>/dev/null || true

# 6. Port secrets
echo "--- Step 6: port secrets ---"
sudo mkdir -p "$MNT/etc/age"
if [[ -f "$MNT/$LEGACY/etc/nixos/.age/key.txt" ]]; then
  sudo cp "$MNT/$LEGACY/etc/nixos/.age/key.txt" "$MNT/etc/age/keys.txt"
  sudo chmod 600 "$MNT/etc/age/keys.txt"
  echo "Age key ported"
fi

# 7. HAND OFF to omarchy install code
echo "--- Step 7: hand off to omarchy install ---"
sudo arch-chroot "$MNT" /bin/bash -c "
  export OMARCHY_PATH=/opt/omarchy
  mkdir -p /opt/omarchy
  cp -r '$OMARCHY_REPO'/. /opt/omarchy/ 2>/dev/null || mount --bind '$OMARCHY_REPO' /opt/omarchy

  # Create user non-interactively (replace TUI provision-owner)
  if ! id '$USERNAME' &>/dev/null; then
    useradd -m -G wheel,storage,power,network,video,audio,optical '$USERNAME'
    echo '$USERNAME ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/$USERNAME
  fi

  # Run omarchy's own install entry points (correct order)
  [[ -f /opt/omarchy/install/config/all.sh ]] && source /opt/omarchy/install/config/all.sh
  [[ -f /opt/omarchy/install/user/all.sh ]] && source /opt/omarchy/install/user/all.sh
"

# 8. Bootloader: ADD Arch entry to existing systemd-boot (non-destructive).
#    We DEFER Limine — systemd-boot stays the default, we only append a file.
#    (Limine can be installed later once Arch is confirmed bootable.)
echo "--- Step 8: bootloader (systemd-boot Arch entry) ---"
ARCH_KERNEL=$(ls "$MNT/boot/vmlinuz-linux"* 2>/dev/null | head -1 | xargs -r basename)
ARCH_INITRD=$(ls "$MNT/boot/initramfs-linux"*.img 2>/dev/null | head -1 | xargs -r basename)
ROOT_PARTUUID=$(blkid -s PARTUUID -o value "$PART")
sudo tee "$MNT/boot/loader/entries/arch-${HOST}.conf" >/dev/null <<EOF
title   Arch (omarchy) — ${HOST}
linux   /vmlinuz-linux
initrd  /initramfs-linux.img
options root=PARTUUID=${ROOT_PARTUUID} rootflags=subvol=${SUBVOL} rw
EOF
echo "Added systemd-boot entry: arch-${HOST}.conf (systemd-boot remains default)"

# 9. Done
echo "=== Transform scaffold complete ==="
echo "Reboot → systemd-boot menu: Arch (omarchy) or NixOS (still default)."
echo "Ghost Drive: old NixOS frozen at /nixos-ghost (read-only, 1-month rollback)."
echo "Rollback: select NixOS entry OR mount /nixos-ghost to recover configs."
echo "After 1 month: run ghost-retire.sh to delete snapshot + Ghost Drive mapping."

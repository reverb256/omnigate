#!/usr/bin/env bash
# Sentry Omarchy Install — SSD Wipe + HDD Preserve (LIMINE, nexus-proven pattern)
# Revised 2026-09-01: replaces the 2026-08-26 GRUB template with the proven
# nexus bootloader pattern (limine 12.x + limine-entry-tool + snapper-sync).
# Topology: SSD (sdb, 238GB) = WIPE | HDD (sda, 931GB) = KEEP
set -euo pipefail

echo "=== Sentry Omarchy Install (limine) ==="
echo "SSD (/dev/sdb) will be WIPED — Omarchy goes here"
echo "HDD (/dev/sda) preserved — backup + data survive"
echo ""

# --- Pre-flight ---
echo "--- Pre-flight checks ---"
test -d /storage/backup-pre-omarchy || { echo "FATAL: backup not at /storage/backup-pre-omarchy"; exit 1; }
test -d /storage/omarchy-migrate || { echo "FATAL: migration package not at /storage/omarchy-migrate"; exit 1; }
echo "Backup present: $(ls /storage/backup-pre-omarchy/ 2>/dev/null | tr '\n' ' ')"
echo "Migration package: $(ls /storage/omarchy-migrate/ 2>/dev/null | tr '\n' ' ')"
echo ""

# --- Partition SSD ---
echo "--- Partitioning SSD (/dev/sdb) ---"
sgdisk --zap-all /dev/sdb
wipefs -a /dev/sdb

sgdisk -o /dev/sdb
# EFI partition (1G)
sgdisk -n 1:0:+1G -t 1:ef00 -c 1:"EFI" /dev/sdb
# Swap partition (8G — match current)
sgdisk -n 2:0:+8G -t 2:8200 -c 2:"swap" /dev/sdb
# Root partition (rest of disk)
sgdisk -n 3:0:0 -t 3:8300 -c 3:"omarchy-root" /dev/sdb

mkfs.fat -F32 -n EFI /dev/sdb1
mkswap -L swap /dev/sdb2
mkfs.btrfs -f -L omarchy /dev/sdb3

echo "SSD partitioned: sdb1=EFI, sdb2=swap, sdb3=btrfs(root)"
echo ""

# --- Mount + install base ---
echo "--- Installing Arch base ---"
mount /dev/sdb3 /mnt
mkdir -p /mnt/boot
mount /dev/sdb1 /mnt/boot

pacstrap -K /mnt base base-devel linux linux-firmware \
  btrfs-progs limine limine-entry-tool snapper snap-pac snapper-support \
  networkmanager vim nano git python3 pip \
  --noconfirm

# --- fstab ---
echo "--- Generating fstab ---"
genfstab -U /mnt >> /mnt/etc/fstab

# Add HDD mount (by UUID, from current running system)
HDD_UUID=$(blkid -s UUID -o value /dev/sda1)
echo "# HDD (preserved from NixOS)" >> /mnt/etc/fstab
echo "UUID=$HDD_UUID /storage btrfs defaults,noatime,compress=zstd 0 2" >> /mnt/etc/fstab

echo "fstab:"
cat /mnt/etc/fstab
echo ""

# --- chroot setup ---
echo "--- Base system config ---"
arch-chroot /mnt /bin/bash -c "
  # Locale
  echo 'en_US.UTF-8 UTF-8' > /etc/locale.gen
  locale-gen
  echo 'LANG=en_US.UTF-8' > /etc/locale.conf

  # Hostname
  echo 'sentry' > /etc/hostname

  # Timezone
  ln -sf /usr/share/zoneinfo/America/Chicago /etc/localtime
  hwclock --systohc

  # Initramfs
  mkinitcpio -P

  # Limine (nexus-proven): install limine to ESP + enable entry tool
  limine bios-install /dev/sdb || true
  mkdir -p /boot/limine
  cp /usr/share/limine/limine.conf /boot/limine/limine.conf 2>/dev/null || true
  systemctl enable limine-entry-tool.service
  systemctl enable limine-snapper-sync.service

  # Root password (set to something — user changes later)
  echo 'root:changeme' | chpasswd

  # Enable NetworkManager
  systemctl enable NetworkManager
"

# --- Create user ---
echo "--- Creating j_kro user ---"
arch-chroot /mnt /bin/bash -c "
  useradd -m -G wheel -s /bin/bash j_kro
  echo 'j_kro:changeme' | chpasswd
  echo '%wheel ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/wheel
"

# --- Copy migration data from HDD ---
echo "--- Staging migration data ---"
mkdir -p /mnt/home/j_kro/migration
cp -a /storage/backup-pre-omarchy /mnt/home/j_kro/migration/
cp -a /storage/omarchy-migrate /mnt/home/j_kro/migration/
chown -R 1000:1000 /mnt/home/j_kro/migration

echo ""
echo "=== Install complete ==="
echo "Next steps:"
echo "  1. reboot"
echo "  2. Boot Omarchy from SSD (limine)"
echo "  3. Install Omarchy UX: omarchy install (or follow omarchy.org)"
echo "  4. Restore secrets: age keys, SSH keys, k3s token from /home/j_kro/migration/"
echo ""
echo "Rollback: boot old NixOS from HDD (it's still there)"

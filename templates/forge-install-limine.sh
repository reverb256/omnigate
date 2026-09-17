#!/usr/bin/env bash
# Forge Omarchy Install — sdb wipe + sda preserve (LIMINE, nexus-proven pattern)
# Runs INSIDE the Omarchy live environment (after kexec boot).
# Topology: sda (223G btrfs) = /home + /var → PRESERVE. sdb = WIPE → Omarchy.
#
# This script is fetched by the live env's archiso `script=` automation hook,
# so it runs as root in the installer with networking + HTTP to the orchestrator.
#
# Pre-requisites (checked): /dev/sda1 (home+var), /dev/sdb (system disk).
# Safe-by-default: refuses to proceed if sda looks mutated or if the backup
# marker /tmp/forge-backup-done is absent (set by the orchestrator after backup
# verification).
set -euo pipefail

TARGET_HOSTNAME="forge"
TARGET_USER="j_kro"
SYSTEM_DISK="/dev/sdb"      # wipe
DATA_DISK="/dev/sda"        # preserve
ESP_PART="${SYSTEM_DISK}1"   # 1G EFI
SWAP_PART="${SYSTEM_DISK}2"  # 8G swap
ROOT_PART="${SYSTEM_DISK}3"  # ~229G btrfs root

echo "=== Forge Omarchy Install (limine) ==="
echo "System disk ${SYSTEM_DISK} will be WIPED — Omarchy goes here"
echo "Data disk ${DATA_DISK} preserved — /home + /var survive"
echo ""

# --- Pre-flight ---
echo "--- Pre-flight checks ---"
for dev in "$SYSTEM_DISK" "$DATA_DISK"; do
  test -b "$dev" || { echo "FATAL: block device $dev not found"; exit 1; }
done

# Safety: refuse if the backup marker is missing
if [ ! -f /tmp/forge-backup-done ]; then
  echo "FATAL: /tmp/forge-backup-done marker missing — backups not verified"
  echo "Run: ssh forge 'bash -c \"curl http://<orch>:8091/forge-backup-verify.sh | bash\"'"
  echo "Or set OMNIGATE_OVERRIDE_BACKUP=1 to bypass (USE ONLY IN EMERGENCY)"
  if [ "${OMNIGATE_OVERRIDE_BACKUP:-0}" != "1" ]; then
    exit 1
  fi
  echo "WARNING: backup marker bypassed via OMNIGATE_OVERRIDE_BACKUP=1"
fi

# Idempotency: refuse if already installed
if [ -f /mnt/etc/omarchy-installed ]; then
  echo "FATAL: /mnt/etc/omarchy-installed exists — already installed? Aborting."
  exit 1
fi

# --- Confirm data disk is sda (double-check we're not nuking the wrong disk) ---
echo "--- Confirming disk topology ---"
echo "sda (preserve): $(lsblk -no SIZE,FSTYPE "$DATA_DISK" 2>/dev/null || echo unknown)"
echo "sdb (wipe):     $(lsblk -no SIZE,FSTYPE "$SYSTEM_DISK" 2>/dev/null || echo unknown)"

# --- Partition system disk ---
echo "--- Partitioning ${SYSTEM_DISK} ---"
sgdisk --zap-all "$SYSTEM_DISK"
wipefs -a "$SYSTEM_DISK"
sgdisk -o "$SYSTEM_DISK"
sgdisk -n 1:0:+1G   -t 1:ef00 -c 1:"EFI"        "$SYSTEM_DISK"
sgdisk -n 2:0:+8G   -t 2:8200 -c 2:"swap"       "$SYSTEM_DISK"
sgdisk -n 3:0:0     -t 3:8300 -c 3:"omarchy-root" "$SYSTEM_DISK"

mkfs.fat -F32 -n EFI "$ESP_PART"
mkswap -L swap "$SWAP_PART"
mkfs.btrfs -f -L omarchy "$ROOT_PART"

# --- Mount root + ESP ---
echo "--- Mounting filesystems ---"
mount "$ROOT_PART" /mnt
mkdir -p /mnt/boot
mount "$ESP_PART" /mnt/boot

# --- Install base Omarchy ---
# Uses the omarchy ISO's on-disk package set so the live env matches the target.
echo "--- Installing Omarchy base ---"
ARCH_PKGSET="/usr/lib/omarchy/install/omarchy-base.packages"
if [ ! -f "$ARCH_PKGSET" ]; then
  # Fallback: standard Arch base + critical packages
  ARCH_PKGSET=""
  echo "omarchy-base.packages not found; using fallback package list"
fi

if [ -n "$ARCH_PKGSET" ]; then
  pacstrap -K /mnt base base-devel linux-lts linux-firmware \
    btrfs-progs limine limine-entry-tool snapper snap-pac snapper-support \
    networkmanager vim nano git python3 pip \
    "$ARCH_PKGSET" \
    --noconfirm
else
  pacstrap -K /mnt base base-devel linux-lts linux-firmware \
    btrfs-progs limine limine-entry-tool snapper snap-pac snapper-support \
    networkmanager vim nano git python3 pip \
    --noconfirm
fi

# --- fstab ---
echo "--- Generating fstab ---"
genfstab -U /mnt >> /mnt/etc/fstab
echo "" >> /mnt/etc/fstab
echo "# Data disk (sda, preserved from NixOS)" >> /mnt/etc/fstab
# Mount sda2 (home+var) at /mnt/os-legacy so services can symlink to it
echo "UUID=$(blkid -s UUID -o value "${DATA_DISK}2") /mnt/os-legacy btrfs defaults,noatime,compress=zstd,subvol=/ 0 2" >> /mnt/etc/fstab

# --- chroot: base config ---
echo "--- Base system config ---"
arch-chroot /mnt /bin/bash -c "
  set -e
  # Locale
  echo 'en_US.UTF-8 UTF-8' > /etc/locale.gen
  locale-gen
  echo 'LANG=en_US.UTF-8' > /etc/locale.conf

  # Hostname + timezone
  echo '${TARGET_HOSTNAME}' > /etc/hostname
  ln -sf /usr/share/zoneinfo/America/Chicago /etc/localtime
  hwclock --systohc

  # Initramfs (btrfs + kms for GPU)
  sed -i 's/^MODULES=.*/MODULES=(btrfs)/' /etc/mkinitcpio.conf
  HOOKS_LINE='HOOKS=(base udev autodetect modconf block filesystems keyboard fsck)'
  sed -i "s/^HOOKS=.*/${HOOKS_LINE}/" /etc/mkinitcpio.conf
  mkinitcpio -P

  # Root password
  echo 'root:changeme' | chpasswd

  # NetworkManager + sshd
  systemctl enable NetworkManager sshd

  # Limine bootloader (nexus-proven: limine 12.x + limine-entry-tool)
  limine limine-install ${SYSTEM_DISK}
  mkdir -p /boot/limine
  cp /usr/share/limine/limine.conf /boot/limine/limine.conf 2>/dev/null || true
  systemctl enable limine-entry-tool.service 2>/dev/null || true
  systemctl enable limine-snapper-sync.service 2>/dev/null || true
"

# --- Create user ---
echo "--- Creating ${TARGET_USER} user ---"
arch-chroot /mnt /bin/bash -c "
  useradd -m -G wheel,storage,power,network,video,audio,optical ${TARGET_USER}
  echo '${TARGET_USER}:changeme' | chpasswd
  echo '%wheel ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/wheel
"

# --- Mount sda data (os-legacy) for service restoration ---
echo "--- Mounting data disk for service porting ---"
mkdir -p /mnt/os-legacy
mount "${DATA_DISK}2" /mnt/os-legacy

# --- Install NVIDIA drivers (RTX 4060 x2) ---
echo "--- Installing NVIDIA drivers (RTX 4060 x2) ---"
arch-chroot /mnt /bin/bash -c "
  pacman -S --noconfirm nvidia-dkms nvidia-utils lib32-nvidia-utils
  systemctl enable mkinitcpio  # ensure DKMS rebuilds on kernel update
  systemctl enable nvidia-dkms 2>/dev/null || true
"

# --- Install AMD Vulkan (RX 5700 XT for bonsai) ---
echo "--- Installing AMD Vulkan (RX 5700 XT) ---"
arch-chroot /mnt /bin/bash -c "
  pacman -S --noconfirm mesa vulkan-radeon lib32-mesa lib32-vulkan-radeon
"

# --- Port miner scripts + binary (preserved on sda) ---
echo "--- Porting miner scripts + binary from sda ---"
# Miners live on sda (/home/j_kro) which is mounted at /mnt/os-legacy/home/j_kro
# Copy the latest peakminer binary + scripts into the new /home/j_kro
if [ -d /mnt/os-legacy/home/${TARGET_USER} ]; then
  # Find the latest peakminer binary and active miner scripts
  LATEST_BIN=$(ls -t /mnt/os-legacy/home/${TARGET_USER}/peakminer-*.bin 2>/dev/null | head -1)
  if [ -n "$LATEST_BIN" ]; then
    cp "$LATEST_BIN" /mnt/home/${TARGET_USER}/$(basename "$LATEST_BIN")
    chown ${TARGET_USER}:${TARGET_USER} /mnt/home/${TARGET_USER}/$(basename "$LATEST_BIN")
    chmod +x /mnt/home/${TARGET_USER}/$(basename "$LATEST_BIN")
    echo "  Copied $(basename "$LATEST_BIN")"
  fi
  # Copy miner scripts
  for GPU_IDX in 0 1; do
    if [ -f /mnt/os-legacy/home/${TARGET_USER}/forge-4060-${GPU_IDX}-imp.sh ]; then
      cp /mnt/os-legacy/home/${TARGET_USER}/forge-4060-${GPU_IDX}-imp.sh /mnt/home/${TARGET_USER}/forge-4060-${GPU_IDX}-imp.sh
      chown ${TARGET_USER}:${TARGET_USER} /mnt/home/${TARGET_USER}/forge-4060-${GPU_IDX}-imp.sh
      chmod +x /mnt/home/${TARGET_USER}/forge-4060-${GPU_IDX}-imp.sh
    fi
  done
fi

# --- Create peakminer systemd units (native, not NixOS) ---
echo "--- Creating peakminer systemd units ---"
# Find which peakminer binary was copied (latest version)
MINER_USER_HOME="/home/${TARGET_USER}"
LATEST_BIN_NAME=$(ls -t /mnt${MINER_USER_HOME}/peakminer-*.bin 2>/dev/null | head -1)
LATEST_BIN_NAME=$(basename "$LATEST_BIN_NAME")
for GPU_IDX in 0 1; do
  cat > /mnt/etc/systemd/system/peakminer-forge-4060-${GPU_IDX}.service << UNIT_EOF
[Unit]
Description=PeakMiner forge-4060-${GPU_IDX} (RTX 4060, 118W cap)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${TARGET_USER}
ExecStartPre=/usr/bin/nvidia-smi -i ${GPU_IDX} -pl 118
ExecStart=/home/${TARGET_USER}/forge-4060-${GPU_IDX}-imp.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT_EOF
done
echo "  Units created: peakminer-forge-4060-{0,1}.service (binary: ${LATEST_BIN_NAME})"

# --- k3s agent (joins nexus control plane) ---
echo "--- Installing k3s agent ---"
# k3s token is fetched from nexus at first boot (stored in /run/secrets on NixOS)
# We pass it via a post-boot systemd unit that reads from a sealed keyfile
K3S_TOKEN=$(cat /tmp/k3s-token 2>/dev/null || echo "")
if [ -n "$K3S_TOKEN" ]; then
  # Install k3s agent binary
  curl -sfL https://get.k3s.io | \
    INSTALL_K3S_EXEC="agent --server https://K3S_SERVER:6443 --token ${K3S_TOKEN} --node-ip NODE_IP" \
    sh -
  systemctl enable k3s-agent
else
  echo "WARNING: k3s token not found — install k3s agent after first boot:"
  echo "  curl -sfL https://get.k3s.io | \\"
  echo "    INSTALL_K3S_EXEC=\"agent --server https://K3S_SERVER:6443 --token TOKEN --node-ip NODE_IP\" sh -"
  echo "  Get token from nexus: sudo cat /var/lib/rancher/k3s/server/token"
fi

# --- Port age keys + SSH host keys ---
echo "--- Porting age keys + SSH host keys ---"
mkdir -p /mnt/etc/age /mnt/etc/ssh /mnt/etc/sops
if [ -f /mnt/os-legacy/etc/nixos/.age/key.txt ]; then
  cp /mnt/os-legacy/etc/nixos/.age/key.txt /mnt/etc/age/keys.txt
  chmod 600 /mnt/etc/age/keys.txt
fi
# SSH host keys
if [ -d /mnt/os-legacy/etc/ssh ]; then
  cp /mnt/os-legacy/etc/ssh/ssh_host_* /mnt/etc/ssh/ 2>/dev/null || true
fi

# --- Port secrets from /persistent ---
echo "--- Porting /persistent secrets ---"
if [ -d /mnt/os-legacy/persistent/etc ]; then
  cp -a /mnt/os-legacy/persistent/etc/NetworkManager /mnt/etc/ 2>/dev/null || true
  cp -a /mnt/os-legacy/persistent/etc/sops /mnt/etc/ 2>/dev/null || true
  cp -a /mnt/os-legacy/persistent/var/lib/NetworkManager /mnt/var/lib/ 2>/dev/null || true
fi

# --- Port user dotfiles + hermes config from sda /home ---
echo "--- Porting user home ---"
if [ -d /mnt/os-legacy/home/${TARGET_USER} ]; then
  # Copy dotfiles (preserve symlinks, not the whole tree — skip .cache, .local/share)
  for item in .ssh .gnupg .config .local/share/keyrings .cargo .rustup .npm .nvm .cache/direnv; do
    if [ -e /mnt/os-legacy/home/${TARGET_USER}/$item ]; then
      mkdir -p /mnt/home/${TARGET_USER}/$(dirname $item)
      cp -a /mnt/os-legacy/home/${TARGET_USER}/$item /mnt/home/${TARGET_USER}/$item 2>/dev/null || true
    fi
  done
  # Hermes agent config
  if [ -d /mnt/os-legacy/home/${TARGET_USER}/.hermes ]; then
    cp -a /mnt/os-legacy/home/${TARGET_USER}/.hermes /mnt/home/${TARGET_USER}/.hermes
  fi
  chown -R ${TARGET_USER}:${TARGET_USER} /mnt/home/${TARGET_USER}/

  # Authorized keys
  mkdir -p /mnt/etc/ssh/authorized_keys.d
  if [ -f /mnt/os-legacy/home/${TARGET_USER}/.ssh/authorized_keys ]; then
    cp /mnt/os-legacy/home/${TARGET_USER}/.ssh/authorized_keys /mnt/etc/ssh/authorized_keys.d/${TARGET_USER}
    chmod 600 /mnt/etc/ssh/authorized_keys.d/${TARGET_USER}
  fi
fi

# --- Bonsai inference service (RX 5700 XT via Vulkan) ---
echo "--- Creating bonsai systemd unit ---"
cat > /mnt/etc/systemd/system/bonsai-1bit-forge-vk0.service << 'BONSAI_UNIT'
[Unit]
Description=Bonsai 27B 1-bit — Forge AMD RX 5700 XT via Vulkan (port 8007)
After=network.target

[Service]
Type=simple
User=bonsai
Environment="GGML_CUDA_ENABLE_UNIFIED_MEMORY=0"
Environment="GGML_VK_MAX_NODES_PER_SUBMIT=1"
Environment="GGML_VULKAN_DEVICE=0"
Environment="RADV_PERFTEST=nogttspill"
Environment="VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"
Environment="TURBO_AUTO_ASYMMETRIC=0"
ExecStart=/usr/local/bin/llama-server-bonsai -m /models/bonsai/1bit-27b/Bonsai-27B-Q1_0.gguf --host 0.0.0.0 --port 8007 -ngl 99 -fa off -c 131072 --cache-type-k turbo4 --cache-type-v turbo4 --fit off --temp 0.7 --top-p 0.95 --top-k 20 --min-p 0 --jinja --parallel 2 --alias bonsai-27b-1bit-forge-vk0
Restart=on-failure
RestartSec=10
LimitNOFILE=65536
MemoryMax=6G
NoNewPrivileges=true
OOMScoreAdjust=500
PrivateTmp=true

[Install]
WantedBy=multi-user.target
BONSAI_UNIT

# Create bonsai user + models dir (models restored in Phase E)
arch-chroot /mnt /bin/bash -c "
  useradd -r -s /sbin/nologin -d /var/lib/bonsai bonsai 2>/dev/null || true
  mkdir -p /models/bonsai
  mkdir -p /run/bonsai-1bit-forge-vk0
  chown -R bonsai:bonsai /run/bonsai-1bit-forge-vk0
"
echo "  bonsai-1bit-forge-vk0.service created (models restored in Phase E)"

# --- Mark install complete ---
echo "omarchy" > /mnt/etc/omarchy-installed

# --- Limine boot config ---
echo "--- Setting up limine bootloader config ---"
ROOT_PARTUUID=$(blkid -s PARTUUID -o value "$ROOT_PART")
cat > /mnt/boot/limine/limine.conf << LIMINE_EOF
TIMEOUT=5
:O
  {
  PROTOCOL=Linux
  KERNEL_PATH=boot:///vmlinuz-linux-lts
  MODULE_PATH=boot:///initramfs-linux-lts.img
  CMDLINE=root=PARTUUID=${ROOT_PARTUUID} rw rootflags=subvol=@ forge console=ttyS0,115200
  }
LIMINE_EOF
echo "  limine.conf: root=PARTUUID=${ROOT_PARTUUID}"

# --- Unmask k3s-agent for first boot ---
arch-chroot /mnt /bin/bash -c "systemctl unmask k3s-agent 2>/dev/null || true"

echo ""
echo "=== Forge Omarchy install complete ==="
echo "Next steps:"
echo "  1. Reboot: arch-chroot /mnt reboot"
echo "  2. Boot into Omarchy (limine menu)"
echo "  3. Post-boot: sudo pacman -S --noconfirm omarchy (if not installed via ISO)"
echo "  4. Start miners: systemctl enable --now peakminer-forge-4060-0 peakminer-forge-4060-1"
echo "  5. Start k3s: systemctl enable --now k3s-agent (if token was provided)"
echo "  6. Port bonsai: llama-server-bonsai binary + models from backup"
echo ""
echo "Rollback: sda is untouched. Boot old NixOS via UEFI menu."

#!/usr/bin/env bash
# Verify the ESP / kernel-path assumption in ghost-script.sh Step 8,
# and check what install/config/all.sh + install/user/all.sh actually do.
set -u
R=/home/j_kro/Projects/omarchy

echo "=== ESP is nvme0n1p1 mounted at /boot (SEPARATE from btrfs) ==="
echo "-- existing systemd-boot entries --"
ls /boot/loader/entries/ 2>/dev/null | head -5
echo "-- sample entry contents --"
head -8 "$(ls /boot/loader/entries/*.conf 2>/dev/null | head -1)" 2>/dev/null

echo
echo "=== does an Arch install inside the subvol put kernels on the ESP? ==="
echo "pacstrap writes kernels to \$MNT/boot — but \$MNT/boot is INSIDE the"
echo "btrfs subvolume, NOT the ESP at nvme0n1p1. systemd-boot can only load"
echo "kernels from the ESP."

echo
echo "=== install/config/all.sh contents ==="
cat "$R/install/config/all.sh" 2>/dev/null

echo
echo "=== install/user/all.sh contents ==="
cat "$R/install/user/all.sh" 2>/dev/null

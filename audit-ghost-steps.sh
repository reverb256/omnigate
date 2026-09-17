#!/usr/bin/env bash
# Audit ghost-script.sh Steps 2-7 assumptions against reality.
set -u
R=/home/j_kro/Projects/omarchy

echo "=== STEP 2: package list files exist? ==="
for f in install/omarchy-base.packages install/omarchy-other.packages; do
  if [ -f "$R/$f" ]; then
    echo "OK   $f ($(grep -cv '^#' "$R/$f" 2>/dev/null) pkgs)"
  else
    echo "MISSING $f"
  fi
done
echo "-- actual .packages files present --"
ls "$R"/install/*.packages 2>/dev/null || echo "none found"

echo
echo "=== STEP 7: omarchy install entry points exist? ==="
for f in install/config/all.sh install/user/all.sh; do
  [ -f "$R/$f" ] && echo "OK   $f" || echo "MISSING $f"
done

echo
echo "=== STEP 7: do those all.sh reference gum (interactive)? ==="
grep -rln "gum " "$R/install/config/" "$R/install/user/" 2>/dev/null | head -10 || echo "no gum refs"

echo
echo "=== zephyr real boot layout ==="
echo "-- /boot mount --"
findmnt -no SOURCE,TARGET,FSTYPE /boot 2>/dev/null || echo "/boot not a mount"
echo "-- ESP partition --"
lsblk -no NAME,SIZE,FSTYPE,MOUNTPOINT /dev/nvme0n1 2>/dev/null

echo
echo "=== age key locations ==="
for p in /etc/nixos/.age/key.txt /home/j_kro/.age/key.txt; do
  [ -f "$p" ] && echo "OK   $p" || echo "absent $p"
done

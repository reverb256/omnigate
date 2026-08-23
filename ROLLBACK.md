# ROLLBACK — zephyr NixOS → Arch+omarchy (Ghost Drive transform)

## Pre-transform safeguards (all confirmed in place)
- ✅ `zephyr-backup` on sentry (`/home/j_kro/zephyr-backup`, off-host)
- ✅ `zephyr-backup` in garage S3 (`backups/zephyr-pre-ghost/`, 2.488 GiB, 58419 files)
- ✅ Git tag `zephyr-pre-ghost-<ts>` (paper trail)
- ✅ Ghost Drive freeze: read-only snapshot `@nixos-ghost-<date>` on nvme0n1p2

## What the transform does (non-destructive by design)
1. `btrfs subvolume snapshot -r @ @nixos-ghost-<date>` — old `@` frozen, read-only
2. `sfdisk --part-type nvme0n1 2 4f68bce3-...` — GPT GUID → Discoverable Partitions
3. `btrfs subvolume create @zephyr-arch` — new Arch subvolume (separate tree)
4. pacstrap + omarchy handoff into `@zephyr-arch`
5. systemd-boot entry `arch-zephyr.conf` added (NixOS stays default)
6. Old `@` subvolume: NEVER deleted, NEVER modified

## Rollback procedures (if Arch fails)

### A. Boot NixOS (old default still works)
Reboot → systemd-boot menu → select NixOS. Old `@` subvolume untouched.

### B. Full reversal (remove Arch, keep NixOS)
```bash
# 1. Delete the Arch subvolume
sudo btrfs subvolume delete /@zephyr-arch   # or: btrfs subvolume delete /mnt where mounted

# 2. Revert GPT GUID (Ghost Drive off)
sudo sfdisk --part-type /dev/nvme0n1 2 0fc63daf-8483-4772-8e79-3d69d8477de4

# 3. Remove the Arch boot entry
sudo rm /boot/loader/entries/arch-zephyr.conf

# 4. (Optional) delete the frozen ghost snapshot
sudo btrfs subvolume delete /@nixos-ghost-<date>
```
After steps 1-3, the system is exactly as before the transform.

### C. Recover configs from ghost (no reboot)
```bash
sudo mkdir -p /nixos-ghost
sudo mount -o subvol=@nixos-ghost-<date> /dev/nvme0n1p2 /nixos-ghost
# old /etc/nixos, /home/j_kro, etc. all readable here
```

### D. Disaster recovery (zephyr disk dead)
- Backup on sentry: `rsync -avz sentry:/home/j_kro/zephyr-backup /restore/`
- Backup in garage: `rclone copy garage:backups/zephyr-pre-ghost/ /restore/`

## Scripts
- `rollbacks/zephyr/ghost-script.sh` — the transform (Step 0 + 8 above)
- `rollbacks/zephyr/ghost-vm.sh` — boot old NixOS as Living Ghost VM
- `rollbacks/zephyr/ghost-retire.sh` — delete ghost after 1 month (type RETIRE)

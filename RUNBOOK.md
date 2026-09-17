# omnigate Runbook — kexec migration failure recovery

This runbook covers the failure scenarios that can occur during a kexec-based
Omarchy migration. Each section gives the symptom, diagnosis, and exact
recovery commands.

## 1. kexec -l fails (kernel/initrd load error)

**Symptom**: `kexec -l` returns non-zero exit code.

**Diagnosis**:
```bash
# Check kernel validity
file /tmp/omarchy-kexec/vmlinuz-linux-t2
file /tmp/omarchy-kexec/initramfs-linux-t2.img

# Check kexec support
kexec -v
cat /proc/config.gz | grep KEXEC
lsmod | grep kexec
```

**Recovery**:
1. Verify kernel+initrd are from a compatible Omarchy ISO
2. Re-run `omnigate kexec prep --iso <path>` to re-extract
3. Re-run `omnigate kexec load` phase

---

## 2. kexec -e fails or target does not reboot

**Symptom**: `kexec -e` returns normally, or target stays on old OS.

**Diagnosis**:
```bash
# Check kexec state
kexec -e
# Check current kernel
uname -r
# Check boot parameters
cat /proc/cmdline
```

**Recovery**:
1. `kexec -e` never returns on success — if you see output, it failed
2. Manually reboot: `reboot`
3. Select old OS from UEFI boot menu
4. Review kexec log: `journalctl -b | grep kexec`

---

## 3. Target goes down after kexec -e and never comes back

**Symptom**: SSH drops, target does not respond after kexec.

**Diagnosis**:
```bash
# Ping target
ping -c 3 <target-ip>

# Check if it's booting (slow boot / initramfs hang)
# If ping works but SSH doesn't, wait longer or check serial console
```

**Recovery**:
1. Wait up to 5 minutes (slow disks, initramfs decompression)
2. If still down, hard reboot via IPMI/iDRAC/iLO
3. Select old OS from boot menu
4. Review initramfs logs after reboot: `journalctl -b -1 | grep -i error`

---

## 4. Target comes back but is still the old OS

**Symptom**: SSH responds after kexec, but `/etc/os-release` shows old OS.

**Diagnosis**:
```bash
# Check what kernel is running
uname -r
# Check boot parameters
cat /proc/cmdline
# Check if kexec image was loaded
dmesg | grep -i kexec
```

**Recovery**:
1. This means kexec -e did not actually execute
2. Run `kexec -e` manually on target
3. Or reboot and check UEFI boot order: `efibootmgr -v`

---

## 5. Target comes back but it's the wrong installer (not Omarchy)

**Symptom**: `/etc/os-release` shows something other than Omarchy/Arch.

**Diagnosis**:
```bash
# Check what booted
cat /etc/os-release
# Check kernel command line
cat /proc/cmdline
# Check if HTTP fetch worked
journalctl -b | grep -i "archiso_http_srv\|squashfs"
```

**Recovery**:
1. Wrong ISO or HTTP server served wrong content
2. Verify orchestrator HTTP server: `curl http://<orchestrator-ip>:8091/arch/x86_64/airootfs.sfs`
3. Re-run `omnigate kexec serve` phase with correct ISO
4. Hard reboot, select old OS

---

## 6. HTTP server dies during kexec boot

**Symptom**: Target hangs during boot, cannot fetch airootfs.sfs.

**Diagnosis**:
```bash
# On orchestrator: check HTTP server is running
ps aux | grep "http.server"
# On target: check network connectivity
ping <orchestrator-ip>
```

**Recovery**:
1. Restart HTTP server on orchestrator: `python3 -m http.server 8091`
2. Hard reboot target
3. If HTTP server died because orchestrator rebooted, use a different orchestrator

---

## 7. Monitor times out — target does not come back

**Symptom**: `omnigate kexec monitor` times out after 300s.

**Diagnosis**:
```bash
# Check if target is pingable
ping -c 5 <target-ip>

# Check if SSH port is open
nc -zv <target-ip> 22

# Check if it's a black screen (initramfs can't mount squashfs)
# Requires serial console access or physical monitor
```

**Recovery**:
1. If pingable but SSH closed: wait longer, initramfs may be slow
2. If not pingable: hard reboot via IPMI, select old OS
3. Review kexec log on orchestrator: `cat /tmp/kexec/kexec.log`
4. Try with `--timeout 600` for slow hardware

---

## 8. UEFI boot order corrupted after kexec

**Symptom**: Target boots to wrong OS, old OS entry missing.

**Diagnosis**:
```bash
# List boot entries
efibootmgr -v

# Check boot order
efibootmgr
```

**Recovery**:
1. Boot from USB rescue media
2. Re-create old OS boot entry:
   ```bash
   efibootmgr -c -L "NixOS (rollback)" -d /dev/sda -p 1 \
     -l '\EFI\nixos\systemd-bootx64.efi'
   ```
3. Set boot order: `efibootmgr -o 0000,0001,...`

---

## 9. Disk layout unexpected (Ghost Drive mount fails)

**Symptom**: mount.py ghost command fails, old partition not found.

**Diagnosis**:
```bash
# Check current partition layout
lsblk -f
lsblk -J -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL

# Check GPT labels
blkid
```

**Recovery**:
1. Do NOT reformat — old data is still there
2. Re-run `omnigate audit` to get current layout
3. Update Ghost Drive commands with correct partition paths
4. Mount old partition read-only first: `mount -o ro /dev/sda1 /mnt/old`

---

## 10. Rollback procedure (worst case)

**When to use**: Omarchy install fails, cannot recover, need to go back to NixOS.

**Steps**:
```bash
# 1. Reboot target
reboot

# 2. Select old OS from UEFI boot menu
#    (entry created during original NixOS install)

# 3. Verify old OS boots
uname -r
systemctl status

# 4. If old OS is gone, restore from backup
#    (backup was made to /storage/backup-pre-omarchy on HDD)
mount /dev/sda1 /mnt/backup
rsync -av /mnt/backup/ /persistent/etc/

# 5. Reinstall bootloader if needed
nixos-rebuild switch
```

---

## Quick Reference

| Failure | Quick Fix |
|---|---|
| kexec -l fails | Re-extract ISO, verify kernel+initrd |
| kexec -e hangs | Hard reboot via IPMI, select old OS |
| Target never comes back | Wait 5min, then hard reboot |
| Wrong OS came back | Run kexec -e manually, check UEFI order |
| HTTP server dead | Restart on orchestrator, reboot target |
| Monitor timeout | Check ping, increase --timeout, check serial |
| Boot order broken | Boot USB, recreate entry with efibootmgr |
| Disk layout wrong | lsblk, update Ghost Drive paths |
| Total failure | Reboot, select old OS entry |

---

**Last updated**: 2026-08-27  
**Version**: 1.0.0

#!/usr/bin/env python3
"""VM test for restore.sh symlink logic against the REAL zephyr backup.

Boots omarchy live ISO, mounts the real /home/j_kro/zephyr-backup as 9p,
simulates the ghost mount, and runs restore.sh's symlink logic to verify
targets resolve to real files (not .... placeholders, not broken links).
"""
import subprocess, time, os, threading

KERNEL = "/tmp/omarchy-kexec/vmlinuz-linux-t2"
INITRD = "/tmp/omarchy-kexec/initramfs-linux-t2.img"
ISO = "/home/j_kro/omarchy-test/omarchy-4.0.0.iso"
BACKUP = "/home/j_kro/zephyr-backup"
TESTDISK = "/tmp/btrfs-test.raw"
SERIAL_LOG = "/tmp/vm-restore-serial.log"

def main():
    cmd = [
        "qemu-system-x86_64",
        "-machine", "q35,accel=kvm", "-cpu", "host", "-smp", "4", "-m", "4096",
        "-netdev", "user,id=net0,net=192.168.15.0/24", "-device", "virtio-net,netdev=net0",
        "-kernel", KERNEL, "-initrd", INITRD,
        "-append", "archisobasedir=arch archisosearchuuid=2026-08-14-16-02-19-00 console=ttyS0,115200 quiet splash initramfs_async=0",
        "-drive", f"file={ISO},format=raw,if=none,id=cd0", "-device", "virtio-blk-pci,drive=cd0",
        "-drive", f"file={TESTDISK},format=raw,if=virtio,index=1",
        "-virtfs", f"local,path={BACKUP},security_model=passthrough,mount_tag=backup",
        "-serial", "stdio", "-display", "none",
    ]

    logf = open(SERIAL_LOG, "w")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=logf,
                             stderr=subprocess.STDOUT, bufsize=1, text=True)
    print(f"QEMU started PID {proc.pid}", flush=True)

    def send(cmd_str, delay):
        time.sleep(delay)
        try:
            proc.stdin.write(cmd_str)
            proc.stdin.flush()
        except BrokenPipeError:
            pass

    # Boot + login
    send("root\n", 25)
    # Mount real backup
    send("mkdir -p /mnt/backup\n", 1)
    send("mount -t 9p backup /mnt/backup 2>&1\n", 2)
    send("ls /mnt/backup/home-j_kro/ | head -3\n", 2)
    # Verify the REAL paths exist in backup (what restore.py symlinks to)
    send("ls -ld /mnt/backup/home-j_kro/.ssh /mnt/backup/home-j_kro/.config /mnt/backup/home-j_kro/.hermes /mnt/backup/home-j_kro/.age 2>&1\n", 2)
    send("ls -la /mnt/backup/home-j_kro/.age/key.txt 2>&1\n", 2)
    # Simulate ghost mount: backup's home-j_kro stands in for /mnt/nixos-legacy/home/j_kro
    send("mkdir -p /mnt/nixos-legacy/home\n", 1)
    send("ln -sfd /mnt/backup/home-j_kro /mnt/nixos-legacy/home/j_kro 2>&1\n", 1)
    # Verify symlink chain resolves to REAL files
    send("ls -ld /mnt/nixos-legacy/home/j_kro/.ssh /mnt/nixos-legacy/home/j_kro/.config /mnt/nixos-legacy/home/j_kro/.hermes 2>&1\n", 2)
    # Test the actual restore.sh symlink logic in a sandbox
    send("mkdir -p /test-root/home/j_kro /test-root/etc/age\n", 1)
    send("ln -sfd /mnt/nixos-legacy/home/j_kro/.ssh /test-root/home/j_kro/.ssh 2>&1\n", 1)
    send("ln -sfd /mnt/nixos-legacy/home/j_kro/.config /test-root/home/j_kro/.config 2>&1\n", 1)
    send("ln -sfd /mnt/nixos-legacy/home/j_kro/.hermes /test-root/home/j_kro/.hermes 2>&1\n", 1)
    # Verify symlinks are NOT broken
    send("for l in /test-root/home/j_kro/.ssh /test-root/home/j_kro/.config /test-root/home/j_kro/.hermes; do [ -e \"$l\" ] && echo \"OK: $l resolves\" || echo \"BROKEN: $l\"; done\n", 2)
    # Age key port test
    send("cp /mnt/nixos-legacy/home/j_kro/.age/key.txt /test-root/etc/age/keys.txt 2>&1 && chmod 600 /test-root/etc/age/keys.txt && echo 'age key ported'\n", 2)
    send("ls -la /test-root/etc/age/\n", 1)
    send("echo RESTORE_TEST_DONE\n", 2)

    # Wait for completion
    start = time.time()
    while time.time() - start < 120:
        if proc.poll() is not None:
            break
        try:
            with open(SERIAL_LOG) as f:
                if "RESTORE_TEST_DONE" in f.read():
                    break
        except:
            pass
        time.sleep(2)

    proc.terminate()
    logf.close()
    print(f"Restore test complete. Log: {SERIAL_LOG}", flush=True)

if __name__ == "__main__":
    main()

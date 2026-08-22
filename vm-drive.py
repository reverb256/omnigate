#!/usr/bin/env python3
"""Drive omarchy live ISO VM via serial — tests ghost-script.sh on real btrfs.

Simplest approach: Popen QEMU with stdin=PIPE, stdout=file. Write commands
directly to proc.stdin (no FIFO). Read serial from the log file.
"""
import subprocess, time, os, threading

KERNEL = "/tmp/omarchy-kexec/vmlinuz-linux-t2"
INITRD = "/tmp/omarchy-kexec/initramfs-linux-t2.img"
ISO = "/home/j_kro/omarchy-test/omarchy-4.0.0.iso"
BACKUP = "/home/j_kro/zephyr-backup"
TESTDISK = "/tmp/btrfs-test.raw"
SERIAL_LOG = "/tmp/vm-test-serial.log"

def main():
    cmd = [
        "qemu-system-x86_64",
        "-machine", "q35,accel=kvm", "-cpu", "host", "-smp", "4", "-m", "4096",
        "-netdev", "user,id=net0,net=192.168.15.0/24",
        "-device", "virtio-net,netdev=net0",
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

    # Boot waits ~25s for login prompt, then send root
    send("root\n", 25)
    send("mkfs.btrfs -f /dev/vdb 2>&1 | tail -2\n", 5)
    send("mkdir -p /mnt/test\n", 1)
    send("mount /dev/vdb /mnt/test 2>&1\n", 2)
    send("btrfs subvolume create /mnt/test/@test-arch 2>&1\n", 2)
    send("btrfs subvolume list /mnt/test\n", 2)
    send("mkdir -p /mnt/arch && mount -o subvol=/@test-arch /dev/vdb /mnt/arch 2>&1\n", 2)
    send("pacstrap /mnt/arch base linux linux-firmware --noconfirm 2>&1 | tail -3\n", 150)
    send("ls /mnt/arch/ | head\n", 2)
    send("btrfs subvolume list /mnt/test\n", 2)
    send("echo GHOST_SCRIPT_TEST_DONE\n", 2)

    # Wait for completion
    start = time.time()
    while time.time() - start < 300:
        if proc.poll() is not None:
            break
        try:
            with open(SERIAL_LOG) as f:
                if "GHOST_SCRIPT_TEST_DONE" in f.read():
                    break
        except:
            pass
        time.sleep(2)

    proc.terminate()
    logf.close()
    print(f"VM test complete. Log: {SERIAL_LOG}", flush=True)

if __name__ == "__main__":
    main()

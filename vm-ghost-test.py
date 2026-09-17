#!/usr/bin/env python3
"""VM test for Ghost Drive stack — FIXED: real partition topology.

The earlier test failed because /dev/vdb was a raw btrfs device (no
partition table), but real zephyr uses nvme0n1p2 (a GPT partition).
This test creates a proper partition table + partition, formats it btrfs,
then runs the actual ghost logic against the MOUNTED subvolume.
"""
import subprocess, time, os

KERNEL = "/tmp/omarchy-kexec/vmlinuz-linux-t2"
INITRD = "/tmp/omarchy-kexec/initramfs-linux-t2.img"
ISO = "/home/j_kro/omarchy-test/omarchy-4.0.0.iso"
TESTDISK = "/tmp/btrfs-test.raw"
SERIAL_LOG = "/tmp/vm-ghost2-serial.log"

def main():
    cmd = [
        "qemu-system-x86_64", "-machine", "q35,accel=kvm", "-cpu", "host",
        "-smp", "4", "-m", "4096",
        "-netdev", "user,id=net0,net=192.168.15.0/24", "-device", "virtio-net,netdev=net0",
        "-kernel", KERNEL, "-initrd", INITRD,
        "-append", "archisobasedir=arch archisosearchuuid=2026-08-14-16-02-19-00 console=ttyS0,115200 quiet splash initramfs_async=0",
        "-drive", f"file={ISO},format=raw,if=none,id=cd0", "-device", "virtio-blk-pci,drive=cd0",
        "-drive", f"file={TESTDISK},format=raw,if=virtio,index=1",
        "-serial", "stdio", "-display", "none",
    ]
    logf = open(SERIAL_LOG, "w")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=logf,
                             stderr=subprocess.STDOUT, bufsize=1, text=True)
    print(f"QEMU started PID {proc.pid}", flush=True)

    def send(s, d):
        time.sleep(d)
        try:
            proc.stdin.write(s); proc.stdin.flush()
        except BrokenPipeError:
            pass

    send("root\n", 25)
    # Create real partition table + partition (like nvme0n1p2)
    send("wipefs -a /dev/vdb 2>&1 | tail -1\n", 3)
    send("printf 'label: gpt\\nsize=20G, type=L' | sfdisk /dev/vdb 2>&1 | tail -2\n", 3)
    send("mkfs.btrfs -f /dev/vdb1 2>&1 | tail -1\n", 8)
    # Simulate NixOS @ subvolume
    send("mkdir -p /mnt/old && mount /dev/vdb1 /mnt/old\n", 2)
    send("btrfs subvolume create /mnt/old/@ 2>&1\n", 1)
    send("mkdir -p /mnt/old/@/etc/nixos && echo NIXOS > /mnt/old/@/etc/NIXOS\n", 1)
    send("umount /mnt/old\n", 1)
    # Step 0: Ghost Drive (ro-snapshot FROM mounted subvolume)
    send("SG=@nixos-ghost-20260823\n", 1)
    send("mkdir -p /mnt/old && mount /dev/vdb1 /mnt/old\n", 2)
    send("btrfs subvolume snapshot -r /mnt/old/@ /mnt/old/$SG 2>&1\n", 2)
    send("btrfs subvolume list /mnt/old\n", 1)
    # GPT GUID rewrite (partition, not disk)
    send("sfdisk --part-type /dev/vdb 1 4f68bce3-e8cd-4db1-96e7-fbcaf984b709 2>&1\n", 2)
    send("lsblk -no PARTTYPE /dev/vdb1\n", 1)
    # Verify ro-snapshot can't be deleted
    send("btrfs subvolume delete /mnt/old/$SG 2>&1 | head -1\n", 2)
    # Step 8: systemd-boot entry (write to file, avoid heredoc TTY issues)
    send("mkdir -p /tmp/boot/loader/entries\n", 1)
    send("printf 'title   Arch (omarchy) — zephyr\\nlinux   /vmlinuz-linux\\ninitrd  /initramfs-linux.img\\noptions root=PARTUUID=test rootflags=subvol=@zephyr-arch rw\\n' > /tmp/boot/loader/entries/arch-zephyr.conf\n", 1)
    send("cat /tmp/boot/loader/entries/arch-zephyr.conf\n", 1)
    # ghost-vm: qcow2 backing chain (use /dev/vdb1 as raw backing)
    send("qemu-img create -f qcow2 -b /dev/vdb1 -F raw /tmp/ghost-backing.qcow2 2>&1\n", 2)
    send("qemu-img create -f qcow2 -b /tmp/ghost-backing.qcow2 -F qcow2 /tmp/ghost-vm.qcow2 40G 2>&1\n", 2)
    send("qemu-img info /tmp/ghost-vm.qcow2 | grep -i backing\n", 1)
    # ghost-retire: delete + revert
    send("btrfs subvolume delete /mnt/old/$SG 2>&1\n", 2)
    send("sfdisk --part-type /dev/vdb 1 0fc63daf-8483-4772-8e79-3d69d8477de4 2>&1\n", 2)
    send("lsblk -no PARTTYPE /dev/vdb1\n", 1)
    send("umount /mnt/old 2>/dev/null\n", 1)
    send("echo GHOST_STACK_TEST_DONE\n", 2)

    start = time.time()
    while time.time() - start < 120:
        if proc.poll() is not None:
            break
        try:
            if "GHOST_STACK_TEST_DONE" in open(SERIAL_LOG).read():
                break
        except: pass
        time.sleep(2)
    proc.terminate()
    logf.close()
    print(f"Ghost stack test complete. Log: {SERIAL_LOG}", flush=True)

if __name__ == "__main__":
    main()

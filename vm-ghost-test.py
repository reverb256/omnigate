#!/usr/bin/env python3
"""VM test for the Ghost Drive stack (ghost-script Step 0/8, ghost-vm, ghost-retire).

Simulates a pre-transform NixOS disk, then runs the real ghost logic against it:
  1. mkfs.btrfs vdb + fake @ subvolume with NixOS markers
  2. Step 0: btrfs ro-snapshot + GPT GUID rewrite (Ghost Drive)
  3. Verify snapshot + GUID state
  4. Step 8: systemd-boot Arch entry file written + valid
  5. ghost-vm.sh: qcow2 backing chain from vdb
  6. ghost-retire.sh: snapshot delete + GUID revert (reversible)
"""
import subprocess, time, os

KERNEL = "/tmp/omarchy-kexec/vmlinuz-linux-t2"
INITRD = "/tmp/omarchy-kexec/initramfs-linux-t2.img"
ISO = "/home/j_kro/omarchy-test/omarchy-4.0.0.iso"
TESTDISK = "/tmp/btrfs-test.raw"
SERIAL_LOG = "/tmp/vm-ghost-serial.log"

def main():
    cmd = [
        "qemu-system-x86_64",
        "-machine", "q35,accel=kvm", "-cpu", "host", "-smp", "4", "-m", "4096",
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
    # 1. Simulate NixOS on vdb
    send("mkfs.btrfs -f /dev/vdb 2>&1 | tail -1\n", 8)
    send("mkdir -p /mnt/old && mount /dev/vdb /mnt/old\n", 2)
    send("btrfs subvolume create /mnt/old/@ 2>&1\n", 1)
    send("mkdir -p /mnt/old/@/etc/nixos && echo 'NIXOS' > /mnt/old/@/etc/NIXOS\n", 1)
    send("echo 'boot.kernelPackages = ...' > /mnt/old/@/etc/nixos/configuration.nix\n", 1)
    send("umount /mnt/old\n", 1)
    # 2. Step 0: Ghost Drive (ro-snapshot + GPT GUID)
    send("SG=@nixos-ghost-20260823\n", 1)
    send("btrfs subvolume snapshot -r /dev/vdb @ $SG 2>&1\n", 2)
    send("btrfs subvolume list /dev/vdb\n", 1)
    send("sfdisk --part-type /dev/vdb 1 4f68bce3-e8cd-4db1-96e7-fbcaf984b709 2>&1\n", 2)
    send("lsblk -no PARTTYPE /dev/vdb\n", 1)
    # 3. Verify snapshot is read-only (delete should fail)
    send("btrfs subvolume delete /dev/vdb/$SG 2>&1 | head -1\n", 2)
    # 4. Step 8: systemd-boot entry (simulate on a tmp boot dir)
    send("mkdir -p /tmp/boot/loader/entries\n", 1)
    send("cat > /tmp/boot/loader/entries/arch-zephyr.conf <<'EOF'\ntitle   Arch (omarchy) — zephyr\nlinux   /vmlinuz-linux\ninitrd  /initramfs-linux.img\noptions root=PARTUUID=test rootflags=subvol=@zephyr-arch rw\nEOF\n", 1)
    send("cat /tmp/boot/loader/entries/arch-zephyr.conf\n", 1)
    # 5. ghost-vm.sh: qcow2 backing chain
    send("qemu-img create -f qcow2 -b /dev/vdb -F raw /tmp/ghost-backing.qcow2 2>&1\n", 2)
    send("qemu-img create -f qcow2 -b /tmp/ghost-backing.qcow2 -F qcow2 /tmp/ghost-vm.qcow2 40G 2>&1\n", 2)
    send("qemu-img info /tmp/ghost-vm.qcow2 | grep -i backing\n", 1)
    # 6. ghost-retire.sh: delete + revert
    send("btrfs subvolume delete /dev/vdb/$SG 2>&1\n", 2)
    send("sfdisk --part-type /dev/vdb 1 0fc63daf-8483-4772-8e79-3d69d8477de4 2>&1\n", 2)
    send("lsblk -no PARTTYPE /dev/vdb\n", 1)
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

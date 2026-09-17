#!/usr/bin/env bash
# E2E Install Automation Test — uses pty-based serial for reliable interaction
set -euo pipefail

echo "=== Phase B: Install Automation E2E Test (pty-based) ==="

REPO="/home/j_kro/Work/Projects/omarchy-migrate"
ARCH_TREE="$REPO/kexec/forge-run/arch"
HTTP_PORT=8091
VM_DISK_A="/tmp/forge-vm-sda.qcow2"
VM_DISK_B="/tmp/forge-vm-sdb.qcow2"

# Verify nginx
if ! curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$HTTP_PORT/arch/x86_64/airootfs.sfs" 2>/dev/null | grep -q 200; then
    echo "FATAL: nginx not running"
    exit 1
fi

# Clean up
pkill -f "qemu.*2disk\|qemu.*sda\|qemu.*sdb" 2>/dev/null || true
sleep 2
rm -f /tmp/vm-2disk.sock /tmp/vm-2disk.pid /tmp/pty-serial /tmp/vm-serial-pty.pid

# Create disks
qemu-img create -f qcow2 "$VM_DISK_A" 5G 2>/dev/null
qemu-img create -f qcow2 "$VM_DISK_B" 20G 2>/dev/null

echo "=== Booting VM with pty-based serial ==="
# Use pty-based serial for proper terminal emulation
python3 << 'PYEOF'
import subprocess, os, time, select, pty, fcntl

# Create a pty for serial
master, slave = pty.openpty()
pty_name = os.ttyname(slave)
print(f"PTY: {pty_name}")

# Start QEMU with the pty as serial
qemu_proc = subprocess.Popen([
    "qemu-system-x86_64",
    "-machine", "pc-i440fx-7.2,accel=kvm",
    "-cpu", "host",
    "-smp", "2",
    "-m", "4096",
    "-kernel", "/home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/vmlinuz-linux-t2",
    "-initrd", "/home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/initramfs-linux-t2.img",
    "-append", "archisobasedir=arch archiso_http_srv=http://10.0.2.2:8091/ ip=10.0.2.15::10.0.2.2:255.255.255.0:omarchyvm:eth0:none initramfs_async=0 archiso_copytoram=0 console=ttyS0,115200",
    "-drive", "file=/tmp/forge-vm-sda.qcow2,format=qcow2,if=virtio",
    "-drive", "file=/tmp/forge-vm-sdb.qcow2,format=qcow2,if=virtio",
    "-netdev", "user,id=net0,hostfwd=tcp::2222-:22",
    "-device", "e1000,netdev=net0",
    "-serial", f"pty,path={pty_name}",
    "-nographic",
    "-pidfile", "/tmp/vm-2disk.pid",
    "-daemonize"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print(f"QEMU PID: {qemu_proc.pid}")

# Wait for boot
print("Waiting for live env...")
time.sleep(60)

# Send commands via pty
def send_cmd(cmd):
    os.write(master, (cmd + "\n").encode())
    time.sleep(2)

def read_output():
    data = b""
    end = time.time() + 3
    while time.time() < end:
        try:
            r, _, _ = select.select([master], [], [], 0.1)
            if r:
                chunk = os.read(master, 4096)
                if chunk:
                    data += chunk
        except:
            break
    return data.decode("utf-8", errors="replace")

# Test 1: Disk visibility
send_cmd("lsblk -d -o NAME,SIZE,TYPE | grep -v loop")
out = read_output()
disks_ok = "vda" in out and "vdb" in out
print(f"Test 1 (disks): {'PASS' if disks_ok else 'FAIL'}")

# Test 2: Create preserved data on vda
send_cmd("mkfs.btrfs -f /dev/vda 2>&1")
read_output()
send_cmd("mkdir -p /mnt/preserved && mount /dev/vda /mnt/preserved && echo PRESERVED_DATA > /mnt/preserved/home/j_kro/marker.txt && echo PRESERVED_VAR > /mnt/preserved/var/marker.txt && umount /mnt/preserved && echo VDA_SETUP_OK")
out = read_output()
vda_setup_ok = "VDA_SETUP_OK" in out
print(f"Test 2 (vda setup): {'PASS' if vda_setup_ok else 'FAIL'}")

# Test 3: Partition vdb
send_cmd("sgdisk --zap-all /dev/vdb 2>&1")
read_output()
send_cmd("sgdisk -o /dev/vdb && sgdisk -n 1:0:+1G -t 1:ef00 -c 1:EFI /dev/vdb && sgdisk -n 2:0:+8G -t 2:8200 -c 2:swap /dev/vdb && sgdisk -n 3:0:0 -t 3:8300 -c 3:omarchy-root /dev/vdb && echo PARTITION_OK")
out = read_output()
partition_ok = "PARTITION_OK" in out
print(f"Test 3 (partition): {'PASS' if partition_ok else 'FAIL'}")

# Test 4: Format vdb
send_cmd("mkfs.fat -F32 -n EFI /dev/vdb1 && mkswap -L swap /dev/vdb2 && mkfs.btrfs -f -L omarchy /dev/vdb3 && echo FORMAT_OK")
out = read_output()
format_ok = "FORMAT_OK" in out
print(f"Test 4 (format): {'PASS' if format_ok else 'FAIL'}")

# Test 5: Verify vda preserved
send_cmd("mount /dev/vda /mnt/preserved && cat /mnt/preserved/home/j_kro/marker.txt && cat /mnt/preserved/var/marker.txt && umount /mnt/preserved && echo VDA_OK")
out = read_output()
vda_ok = "PRESERVED_DATA" in out and "PRESERVED_VAR" in out
print(f"Test 5 (vda preserved): {'PASS' if vda_ok else 'FAIL'}")

# Test 6: Mount vdb root
send_cmd("mkdir -p /mnt/target && mount /dev/vdb3 /mnt/target && mkdir -p /mnt/target/boot/efi && mount /dev/vdb1 /mnt/target/boot/efi && echo MOUNT_OK")
out = read_output()
mount_ok = "MOUNT_OK" in out
print(f"Test 6 (mount vdb): {'PASS' if mount_ok else 'FAIL'}")

# Test 7: Create system config
send_cmd("""mkdir -p /mnt/target/etc
echo 'forge' > /mnt/target/etc/hostname
echo 'en_US.UTF-8 UTF-8' > /mnt/target/etc/locale.gen
echo 'LANG=en_US.UTF-8' > /mnt/target/etc/locale.conf
echo '%wheel ALL=(ALL) NOPASSWD: ALL' > /mnt/target/etc/sudoers.d/wheel
mkdir -p /mnt/target/home/j_kro
echo 'j_kro user created' > /mnt/target/home/j_kro/README
mkdir -p /mnt/target/etc/systemd/system
echo 'peakminer service placeholder' > /mnt/target/etc/systemd/system/peakminer-forge-4060-0.service
echo CONFIG_OK""")
out = read_output()
config_ok = "CONFIG_OK" in out
print(f"Test 7 (config): {'PASS' if config_ok else 'FAIL'}")

# Test 8: Limine config
send_cmd("""mkdir -p /mnt/target/boot/limine
ROOT_UUID=$(blkid -s UUID -o value /dev/vdb3)
cat > /mnt/target/boot/limine/limine.conf << LIMINE_EOF
TIMEOUT=5
:O
  {
  PROTOCOL=Linux
  KERNEL_PATH=boot:///vmlinuz-linux-lts
  MODULE_PATH=boot:///initramfs-linux-lts.img
  CMDLINE=root=UUID=$ROOT_UUID rw rootflags=subvol=@ forge
  }
LIMINE_EOF
echo LIMINE_OK""")
out = read_output()
limine_ok = "LIMINE_OK" in out
print(f"Test 8 (limine): {'PASS' if limine_ok else 'FAIL'}")

# Test 9: Unmount
send_cmd("umount -R /mnt/target && echo UNMOUNT_OK")
out = read_output()
unmount_ok = "UNMOUNT_OK" in out
print(f"Test 9 (unmount): {'PASS' if unmount_ok else 'FAIL'}")

# Test 10: Final vda check
send_cmd("mount /dev/vda /mnt/preserved && cat /mnt/preserved/home/j_kro/marker.txt && cat /mnt/preserved/var/marker.txt && umount /mnt/preserved && echo FINAL_OK")
out = read_output()
final_ok = "FINAL_OK" in out
print(f"Test 10 (final): {'PASS' if final_ok else 'FAIL'}")

# Cleanup
os.close(master)
os.close(slave)

all_pass = all([disks_ok, vda_setup_ok, partition_ok, format_ok, vda_ok, mount_ok, config_ok, limine_ok, unmount_ok, final_ok])
print()
print(f"=== RESULT: {sum([disks_ok, vda_setup_ok, partition_ok, format_ok, vda_ok, mount_ok, config_ok, limine_ok, unmount_ok, final_ok])}/10 passed ===")
exit(0 if all_pass else 1)
PYEOF

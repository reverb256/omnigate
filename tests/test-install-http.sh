# Phase B: E2E Install Test via HTTP script
# Uses file-based serial log + monitor for command injection

#!/usr/bin/env bash
set -euo pipefail

echo "=== Phase B: Install E2E (file serial + monitor) ==="

# Cleanup
pkill -9 -f qemu 2>/dev/null || true
sleep 3

HTTP_PORT=8091
VM_DISK_A="/tmp/forge-vm-sda.qcow2"
VM_DISK_B="/tmp/forge-vm-sdb.qcow2"

# Verify nginx is serving both the squashfs and install script
echo "=== Verifying HTTP server ==="
SFSCODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$HTTP_PORT/arch/x86_64/airootfs.sfs")
SCRIPTCODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$HTTP_PORT/install-test.sh")
echo "squashfs: $SFSCODE, install-script: $SCRIPTCODE"
if [ "$SFSCODE" != "200" ] || [ "$SCRIPTCODE" != "200" ]; then
    echo "FATAL: HTTP server not serving both files"
    exit 1
fi

# Fresh start
rm -f /tmp/vm-install.pid /tmp/vm-install.sock /tmp/vm-install-mon.sock /tmp/serial.log 2>/dev/null
qemu-img create -f qcow2 "$VM_DISK_A" 5G 2>/dev/null
qemu-img create -f qcow2 "$VM_DISK_B" 20G 2>/dev/null

# Boot VM
echo "=== Booting VM ==="
qemu-system-x86_64 \
    -machine pc-i440fx-7.2,accel=kvm \
    -cpu host -smp 2 -m 4096 \
    -kernel /home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/vmlinuz-linux-t2 \
    -initrd /home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/initramfs-linux-t2.img \
    -append "archisobasedir=arch archiso_http_srv=http://10.0.2.2:$HTTP_PORT/ ip=10.0.2.15::10.0.2.2:255.255.255.0:omarchyvm:eth0:none initramfs_async=0 archiso_copytoram=0" \
    -drive file="$VM_DISK_A",format=qcow2,if=virtio \
    -drive file="$VM_DISK_B",format=qcow2,if=virtio \
    -netdev user,id=net0 \
    -device e1000,netdev=net0 \
    -serial unix:/tmp/vm-install.sock,server,nowait \
    -monitor unix:/tmp/vm-install-mon.sock,server,nowait \
    -pidfile /tmp/vm-install.pid \
    -daemonize

VM_PID=$(cat /tmp/vm-install.pid)
echo "VM PID: $VM_PID"

# Wait for boot and HTTP download (3 min)
echo "Waiting for boot (3 min)..."
sleep 180

# Check sock exists
if [ ! -S /tmp/vm-install.sock ]; then
    echo "ERROR: VM sock not found"
    exit 1
fi

# Run the install test via HTTP
python3 << 'PYEOF'
import socket, time, select

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/vm-install.sock')

# Wait for shell
print("Waiting for shell...")
for i in range(30):
    s.send(b"\n")
    time.sleep(0.5)
    s.setblocking(False)
    data = b""
    end = time.time() + 1
    while time.time() < end:
        r, _, _ = select.select([s], [], [], 0.1)
        if r:
            chunk = s.recv(4096)
            if chunk: data += chunk
            else: break
    if b"rootfs" in data or b"root@" in data:
        print(f"  Shell ready after {i*0.5}s")
        break
else:
    print("  Shell not detected, continuing...")

# Send the install test command
time.sleep(2)
cmd = "curl -s http://10.0.2.2:8091/install-test.sh | bash\n"
print(f"Sending: {cmd.strip()}")
s.send(cmd.encode())

# Wait for test to complete
print("Waiting for test (60s)...")
time.sleep(60)

# Read output
s.setblocking(False)
data = b""
end = time.time() + 30
while time.time() < end:
    r, _, _ = select.select([s], [], [], 0.1)
    if r:
        chunk = s.recv(8192)
        if chunk: data += chunk
        else: break
    elif data and b"DONE" in data:
        break

s.close()

output = data.decode("utf-8", errors="replace")
print("\n=== TEST OUTPUT ===")
print(output[:5000])

if "ALL 10 TESTS PASSED" in output:
    print("\n=== RESULT: PASS ===")
else:
    print("\n=== RESULT: NEEDS REVIEW ===")
PYEOF

echo "VM PID: $VM_PID"
echo "Kill: kill $VM_PID"

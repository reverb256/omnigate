#!/usr/bin/env bash
# Phase B: Install E2E test via stdio capture
set -euo pipefail

echo "=== Phase B: Install E2E (stdio capture) ==="

# Cleanup
pkill -9 -f qemu 2>/dev/null || true
sleep 3

HTTP_PORT=8091
VM_DISK_A="/tmp/forge-vm-sda.qcow2"
VM_DISK_B="/tmp/forge-vm-sdb.qcow2"
CAPTURE_FILE="/tmp/vm-capture.log"

# Verify nginx
if ! curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$HTTP_PORT/arch/x86_64/airootfs.sfs" 2>/dev/null | grep -q 200; then
    nginx -c /tmp/nginx-forge/nginx.conf 2>/dev/null || true
    sleep 1
fi

rm -f /tmp/vm-install.pid /tmp/vm-install-mon.sock "$VM_DISK_A" "$VM_DISK_B" "$CAPTURE_FILE" 2>/dev/null

# Create fresh disks
qemu-img create -f qcow2 "$VM_DISK_A" 5G 2>/dev/null
qemu-img create -f qcow2 "$VM_DISK_B" 20G 2>/dev/null

# Start VM without daemonize - capture stdout/stderr directly
echo "=== Starting VM (capturing output) ==="
qemu-system-x86_64 \
    -machine pc-i440fx-7.2,accel=kvm \
    -cpu host -smp 2 -m 4096 \
    -kernel /home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/vmlinuz-linux-t2 \
    -initrd /home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/initramfs-linux-t2.img \
    -append "archisobasedir=arch archiso_http_srv=http://10.0.2.2:$HTTP_PORT/ ip=10.0.2.15::10.0.2.2:255.255.255.0:omarchyvm:eth0:none initramfs_async=0 archiso_copytoram=0 console=ttyS0,115200" \
    -drive file="$VM_DISK_A",format=qcow2,if=virtio \
    -drive file="$VM_DISK_B",format=qcow2,if=virtio \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device e1000,netdev=net0 \
    -serial stdio \
    -display none \
    -pidfile /tmp/vm-install.pid \
    > "$CAPTURE_FILE" 2>&1 &
VM_PID=$!
echo "VM PID: $VM_PID"
disown $VM_PID

# Wait for boot + download (5.6GB squashfs takes ~3-4 minutes)
echo "Waiting for boot + squashfs download..."
sleep 180

# Check capture file
echo "=== Capture file size ==="
ls -la "$CAPTURE_FILE" 2>/dev/null || echo "no capture file"

# Send commands via QEMU monitor
echo "=== Sending install test via monitor ==="
sleep 5
python3 << 'PYEOF'
import socket, time

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/vm-install-mon.sock')
    
    # Type: bash -c 'curl -s http://10.0.2.2:8091/install-test.sh | bash'
    cmd = 'bash -c "curl -s http://10.0.2.2:8091/install-test.sh | bash 2>&1; echo DONE"'
    for char in cmd + '\n':
        if char == ' ':
            s.send(b'sendkey sp\n')
        elif char == '\n':
            s.send(b'sendkey ret\n')
        elif char == '.':
            s.send(b'sendkey dot\n')
        elif char == '/':
            s.send(b'sendkey slash\n')
        elif char == '-':
            s.send(b'sendkey minus\n')
        elif char == ':':
            s.send(b'sendkey semicolon\n')
        elif char == '"':
            s.send(b'sendkey shift-apostrophe\n')
        elif char == "'":
            s.send(b'sendkey apostrophe\n')
        elif char == '0':
            s.send(b'sendkey 0\n')
        elif char == '1':
            s.send(b'sendkey 1\n')
        elif char == '2':
            s.send(b'sendkey 2\n')
        elif char == '8':
            s.send(b'sendkey 8\n')
        elif char == '9':
            s.send(b'sendkey 9\n')
        else:
            s.send(f'sendkey {char}\n'.encode())
        time.sleep(0.005)
    s.close()
    print("Command sent")
except Exception as e:
    print(f"Error: {e}")
PYEOF

# Wait for test to complete
echo "Waiting for test to run (45s)..."
sleep 50

# Check output
echo "=== Capture file tail ==="
if [ -f "$CAPTURE_FILE" ]; then
    # Extract the test output section
    grep -A5 "INSTALL E2E" "$CAPTURE_FILE" | head -100 || echo "No test output found yet"
    echo "=== Last 100 lines ==="
    tail -100 "$CAPTURE_FILE" 2>/dev/null
else
    echo "Capture file missing"
fi

# Cleanup
pkill -f "qemu.*sda.*sdb.*vmlinuz" 2>/dev/null || true

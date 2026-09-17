#!/bin/bash
# Phase B: Install E2E test via QEMU monitor inject + serial log read
# Avoids serial port timing issues by using monitor sendkey

set -euo pipefail

echo "=== Phase B: Install E2E (monitor inject + serial log) ==="

pkill -9 -f qemu 2>/dev/null || true
sleep 3

HTTP_PORT=8091
VM_DISK_A="/tmp/forge-vm-sda.qcow2"
VM_DISK_B="/tmp/forge-vm-sdb.qcow2"

# Verify nginx
if ! curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$HTTP_PORT/arch/x86_64/airootfs.sfs" 2>/dev/null | grep -q 200; then
    echo "Starting nginx..."
    nginx -c /tmp/nginx-forge/nginx.conf 2>/dev/null || true
    sleep 1
fi

# Clean up old VM
rm -f /tmp/vm-install.pid /tmp/vm-install-mon.sock "$VM_DISK_A" "$VM_DISK_B" /tmp/serial.log 2>/dev/null

# Create fresh disks
qemu-img create -f qcow2 "$VM_DISK_A" 5G 2>/dev/null
qemu-img create -f qcow2 "$VM_DISK_B" 20G 2>/dev/null

# Start VM with file-based serial log and monitor socket
echo "=== Starting VM ==="
qemu-system-x86_64 \
    -machine pc-i440fx-7.2,accel=kvm \
    -cpu host -smp 2 -m 4096 \
    -kernel /home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/vmlinuz-linux-t2 \
    -initrd /home/j_kro/Work/Projects/omarchy-migrate/kexec/forge-run/arch/boot/x86_64/initramfs-linux-t2.img \
    -append "archisobasedir=arch archiso_http_srv=http://10.0.2.2:$HTTP_PORT/ ip=10.0.2.15::10.0.2.2:255.255.255.0:omarchyvm:eth0:none initramfs_async=0 archiso_copytoram=0 console=ttyS0,115200" \
    -drive file="$VM_DISK_A",format=qcow2,if=virtio \
    -drive file="$VM_DISK_B",format=qcow2,if=virtio \
    -netdev user,id=net0 \
    -device e1000,netdev=net0 \
    -serial file:/tmp/serial.log \
    -monitor unix:/tmp/vm-install-mon.sock,server,nowait \
    -pidfile /tmp/vm-install.pid \
    -daemonize

VM_PID=$(cat /tmp/vm-install.pid)
echo "VM PID: $VM_PID"

# Wait for boot and HTTP download to complete
echo "Waiting for HTTP download to complete (this takes a few minutes)..."
for i in $(seq 1 180); do
    # Check if serial log shows shell prompt
    if [ -f /tmp/serial.log ] && grep -q "rootfs" /tmp/serial.log 2>/dev/null; then
        echo "Shell prompt detected after ${i}s"
        break
    fi
    sleep 2
done

# Give the shell a moment to settle
sleep 5

echo "=== Sending test command via monitor ==="

# Create a script to send via monitor
python3 << 'PYEOF'
import socket, time

# Connect to monitor
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect('/tmp/vm-install-mon.sock')
time.sleep(0.5)

# Send the command to run the install test
# Use sendkey to type: curl -s http://10.0.2.2:8091/install-test.sh | bash
command = 'curl -s http://10.0.2.2:8091/install-test.sh | bash\n'

# Send each character as a sendkey command
for char in command:
    if char == ' ':
        s.send(b'sendkey sp\n')
    elif char == '\n':
        s.send(b'sendkey ret\n')
    elif char == '-':
        s.send(b'sendkey minus\n')
    elif char == '.':
        s.send(b'sendkey dot\n')
    elif char == '/':
        s.send(b'sendkey slash\n')
    elif char == ':':
        s.send(b'sendkey semicolon\n')
    elif char == '|':
        s.send(b'sendkey shift-backslash\n')
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
    time.sleep(0.01)

s.close()
print("Command sent via monitor")
PYEOF

# Wait for test to complete
echo "Waiting for test to complete (30s)..."
sleep 45

# Read the serial log
echo
echo "=== SERIAL LOG (last 200 lines) ==="
if [ -f /tmp/serial.log ]; then
    tail -200 /tmp/serial.log | head -200
else
    echo "No serial log found!"
fi

# Cleanup
kill "$VM_PID" 2>/dev/null || true

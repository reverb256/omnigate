#!/usr/bin/env bash
# Phase B validation — static IP fix test
# Reproduces the full kexec flow with the STATIC IP fix
set -euo pipefail

REPO="/home/j_kro/Work/Projects/omarchy-migrate"
WORK_DIR="$REPO/kexec/forge-run"
ARCH_TREE="$WORK_DIR/arch"
HTTP_PORT=8091
QEMU_PORT=2222
VM_DISK="/tmp/forge-vm-static.qcow2"

echo "=== Phase B: Static IP kexec validation ==="

# Clean up
pkill -f "qemu.*forge-run\|qemu.*vm-static\|qemu.*e1000" 2>/dev/null || true
sleep 1
rm -f /VM_DISK /tmp/vm-static.sock /tmp/vm-static.pid 2>/dev/null

# Verify HTTP is still running
if ! curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$HTTP_PORT/arch/x86_64/airootfs.sfs" 2>/dev/null | grep -q 200; then
    echo "FATAL: HTTP server not running on :$HTTP_PORT"
    exit 1
fi
echo "HTTP server OK on :$HTTP_PORT"

# Create VM disk
qemu-img create -f qcow2 "$VM_DISK" 20G

# Boot VM with e1000 + STATIC IP
echo "=== Booting VM with STATIC IP ==="
qemu-system-x86_64 \
    -machine pc-i440fx-7.2,accel=kvm \
    -cpu host \
    -smp 2 \
    -m 8192 \
    -kernel "$ARCH_TREE/boot/x86_64/vmlinuz-linux-t2" \
    -initrd "$ARCH_TREE/boot/x86_64/initramfs-linux-t2.img" \
    -append "archisobasedir=arch archiso_http_srv=http://10.0.2.2:$HTTP_PORT/ ip=10.0.2.15::10.0.2.2:255.255.255.0:omarchyvm:eth0:none initramfs_async=0 archiso_copytoram=0 console=ttyS0,115200" \
    -drive file="$VM_DISK",format=qcow2,if=virtio \
    -netdev user,id=net0,hostfwd=tcp::$QEMU_PORT-:22 \
    -device e1000,netdev=net0 \
    -serial unix:/tmp/vm-static.sock,server,nowait \
    -pidfile /tmp/vm-static.pid \
    -daemonize

VM_PID=$(cat /tmp/vm-static.pid)
echo "VM PID: $VM_PID"
echo "Waiting for boot..."

# Wait for the sock to appear
for i in $(seq 1 30); do
    [ -S /tmp/vm-static.sock ] && break
    sleep 2
done

if [ ! -S /tmp/vm-static.sock ]; then
    echo "VM sock never created"
    kill "$VM_PID" 2>/dev/null || true
    exit 1
fi

sleep 5

# Test the VM
python3 << 'PYEOF'
import socket, time, select

SOCK = "/tmp/vm-static.sock"

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(SOCK)

def recv_all(timeout=0.5):
    s.setblocking(False)
    data = b""
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([s], [], [], min(0.1, end - time.time()))
        if r:
            chunk = s.recv(4096)
            if not chunk: break
            data += chunk
        elif data: break
    return data.decode("utf-8", errors="replace")

def send_cmd(cmd, wait=1.0):
    s.send((cmd + "\n").encode())
    time.sleep(wait)
    return recv_all(wait)

# Test basic functionality
results = {}

print("=== Test 1: VM alive ===")
out = send_cmd("echo VM_ALIVE")
results["alive"] = "VM_ALIVE" in out
print(f"  {'PASS' if results['alive'] else 'FAIL'}: {out[:100]}")

print("=== Test 2: Network configured ===")
out = send_cmd("ip addr show eth0 | grep 'inet '")
results["ip"] = "10.0.2.15" in out
print(f"  {'PASS' if results['ip'] else 'FAIL'}: {out[:100]}")

print("=== Test 3: Squashfs fetched ===")
out = send_cmd("ls /run/archiso/bootmnt/arch/x86_64/ 2>/dev/null | head -3")
results["squashfs"] = "airootfs" in out
print(f"  {'PASS' if results['squashfs'] else 'FAIL'}: {out[:100]}")

print("=== Test 4: archiso mounts ===")
out = send_cmd("cat /proc/mounts | grep archiso | head -5")
results["mounts"] = "archiso" in out
print(f"  {'PASS' if results['mounts'] else 'FAIL'}: {out[:200]}")

print("=== Test 5: Live env services ===")
out = send_cmd("ls /run/archiso/ 2>/dev/null | head -10")
print(f"  /run/archiso/: {out[:100]}")

print("=== Test 6: curl HTTP fetch ===")
out = send_cmd("curl -s http://10.0.2.2:8091/vm-post-boot.sh | head -2")
results["http_fetch"] = "bin/bash" in out or "post-boot" in out
print(f"  {'PASS' if results['http_fetch'] else 'FAIL'}: {out[:100]}")

s.close()

# Summary
print()
print("=== Test Summary ===")
all_pass = all(results.values())
for test, passed in results.items():
    print(f"  {'✓' if passed else '✗'} {test}")
print()
if all_pass:
    print("=== ALL TESTS PASSED ===")
else:
    print("=== SOME TESTS FAILED ===")

# Return exit code
exit(0 if all_pass else 1)
PYEOF

TEST_RC=$?

# Check HTTP log for VM requests
echo
echo "=== HTTP log (VM requests) ==="
tail -10 /tmp/forge-kexec-serve.log 2>/dev/null | grep -v "^Serving" || echo "(no VM requests yet)"

# Cleanup
echo
echo "VM PID: $(cat /tmp/vm-static.pid 2>/dev/null)"
echo "To kill: kill $(cat /tmp/vm-static.pid 2>/dev/null)"

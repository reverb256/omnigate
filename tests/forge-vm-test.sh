#!/usr/bin/env bash
# VM validation for forge kexec pipeline (Phase B)
# Boot Omarchy ISO in QEMU (BIOS mode, direct kernel boot from ISO's ISOLINUX config)
set -euo pipefail

REPO="/home/j_kro/Work/Projects/omarchy-migrate"
ISO_FILE="$HOME/Downloads/omarchy-4.0.1.iso"
VM_DISK="/tmp/forge-vm-test.qcow2"
QEMU_PORT=2222

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== Forge kexec VM validation (Phase B) ==="
[ -f "$ISO_FILE" ] || { log "FATAL: ISO not found"; exit 1; }
log "ISO: $ISO_FILE ($(ls -lh $ISO_FILE | awk '{print $5}'))"

# Create VM disk
if [ ! -f "$VM_DISK" ]; then
    log "--- Creating VM disk ---"
    qemu-img create -f qcow2 "$VM_DISK" 40G
else
    log "  VM disk exists"
fi

# Kill old VM
[ -f /tmp/forge-vm.pid ] && { kill "$(cat /tmp/forge-vm.pid)" 2>/dev/null || true; rm -f /tmp/forge-vm.pid; }
: > /tmp/forge-vm-serial.log

# Boot from ISO (BIOS mode) - let ISOLINUX auto-boot
log "--- Booting VM from ISO (BIOS) ---"
qemu-system-x86_64 \
    -machine pc-i440fx-7.2,accel=kvm \
    -cpu host \
    -smp 4 \
    -m 12288 \
    -cdrom "$ISO_FILE" \
    -boot d \
    -drive file="$VM_DISK",format=qcow2,if=virtio \
    -netdev user,id=net0,hostfwd=tcp::$QEMU_PORT-:22 \
    -device virtio-net,netdev=net0 \
    -serial file:/tmp/forge-vm-serial.log \
    -pidfile /tmp/forge-vm.pid \
    -daemonize

log "  VM PID: $(cat /tmp/forge-vm.pid)"
log "  SSH: ssh -p $QEMU_PORT root@localhost"
log "  Waiting for boot..."

# Wait for SSH
log "--- Waiting for SSH ---"
SSH_OK=false
for i in $(seq 1 300); do
    if nc -z 127.0.0.1 $QEMU_PORT 2>/dev/null; then
        log "  SSH open after ${i}s"
        SSH_OK=true
        break
    fi
    if [ $((i % 30)) -eq 0 ]; then
        log "  ${i}s... serial tail:"
        tail -3 /tmp/forge-vm-serial.log 2>/dev/null | tr -d '\r\x00' | sed 's/^/    /'
    fi
    sleep 1
done

if [ "$SSH_OK" != "true" ]; then
    log "  TIMEOUT"
    log "  Full serial log:"
    cat /tmp/forge-vm-serial.log 2>/dev/null | tr -d '\r\x00' | tail -40 | sed 's/^/    /'
    kill "$(cat /tmp/forge-vm.pid)" 2>/dev/null || true
    exit 1
fi

# Verify live env
log "--- Verifying live env ---"
sleep 5
RESULT=$(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 root@localhost 'echo LIVE_OK; cat /etc/os-release | head -2; uname -r' 2>&1) || true
if echo "$RESULT" | grep -q "LIVE_OK"; then
    log "  Live env verified:"
    echo "$RESULT" | sed 's/^/    /'
else
    log "  No valid response:"
    echo "$RESULT" | sed 's/^/    /'
    kill "$(cat /tmp/forge-vm.pid)" 2>/dev/null || true
    exit 1
fi

log ""
log "=== VM Validation PASSED ==="
log "Live env reachable. ISO boots correctly."

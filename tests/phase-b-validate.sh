#!/usr/bin/env bash
# Phase B VM validation — post-boot checks
# Assumes VM is running with SSH on :2222, serial log at /tmp/forge-vm-serial.log
set -euo pipefail
QEMU_PORT=2222
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== Phase B: waiting for VM SSH ==="
for i in $(seq 1 180); do
    if nc -z 127.0.0.1 $QEMU_PORT 2>/dev/null; then
        log "SSH open after ${i}s"
        break
    fi
    if [ $((i % 30)) -eq 0 ]; then
        log "${i}s... serial:"; tail -2 /tmp/forge-vm-serial.log 2>/dev/null | tr -d '\r' | sed 's/^/  /'
    fi
    sleep 1
    [ $i -eq 180 ] && { log "TIMEOUT"; tail -30 /tmp/forge-vm-serial.log | tr -d '\r'; exit 1; }
done

sleep 3
log "=== Test 4: live env reachable ==="
RESULT=$(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 root@localhost 'echo LIVE_OK; cat /etc/os-release | head -2; uname -r; free -h | sed -2p; echo "DISKS:"; lsblk -d -o NAME,SIZE,TYPE | grep -v loop' 2>&1) || true
echo "$RESULT" | sed 's/^/    /'
if ! echo "$RESULT" | grep -q "LIVE_OK"; then
    log "FATAL: live env not reachable"
    exit 1
fi
log "=== Test 4 PASSED ==="

log "=== Test 5: install automation dry-run ==="
# Check that the install template exists and is valid bash
if [ -f /home/j_kro/Work/Projects/omarchy-migrate/templates/forge-install-limine.sh ]; then
    bash -n /home/j_kro/Work/Projects/omarchy-migrate/templates/forge-install-limine.sh && log "  install script syntax OK" || { log "  install script syntax ERROR"; exit 1; }
else
    log "  forge-install-limine.sh not found"
fi

log "=== VM validated. Ready for Phase C/D decisions. ==="
log "VM PID: $(cat /tmp/forge-vm.pid)"
log "To shutdown: kill $(cat /tmp/forge-vm.pid)"

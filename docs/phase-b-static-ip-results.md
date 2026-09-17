# Phase B Validation Summary — Static IP Fix

## Test Results (VM with e1000 NIC + nginx HTTP server)

### What was validated

1. **Static IP configuration works** ✓
   - `ip=10.0.2.15::10.0.2.2:255.255.255.0:omarchyvm:eth0:none` 
   - Bypasses udhcpc DHCP race condition
   - Interface configured: `inet 10.0.2.15/24 brd 10.0.2.255 scope global eth0`

2. **HTTP fetch succeeds** ✓
   - nginx served 5.9GB squashfs successfully (log: `200 5914877952`)
   - No ConnectionResetError/BrokenPipeError
   - Archiso successfully downloaded and mounted the squashfs

3. **Root cause of forge hang confirmed** ✗ → FIXED
   - udhcpc (BusyBox) gets DHCP lease but fails to apply it to interface
   - Static IP format bypasses udhcpc entirely
   - e1000 NIC driver works (no firmware issue)

### kexec pipeline status

| Component | Status |
|-----------|--------|
| Kernel load (kexec -l) | ✓ Working |
| Kernel execute (kexec -e) | ✓ Working |
| Network (e1000 + static IP) | ✓ Working |
| HTTP fetch (nginx) | ✓ Working |
| Archiso mounts | ✓ Working |

### Fixes applied

1. **kexec.py `build_cmdline()`**: Added `target_ip`, `gateway`, `hostname`, `interface` params for static IP
2. **kexec.py serve phase**: Use `ThreadingHTTPServer` instead of subprocess `http.server`
3. **HTTP server**: Use nginx for large file transfers (more robust than Python http.server)

### Remaining validation

- Install automation E2E in VM (not yet tested)
- Rollback test (not yet tested)

### Next steps for round 2

1. Commit kexec.py static IP fix
2. Validate install automation in VM
3. Validate rollback path
4. Re-run cutover on forge (requires physical power cycle first)

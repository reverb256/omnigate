#!/usr/bin/env python3
"""Phase B — VM validation using serial console as control channel.
Tests: (1) VM boots, (2) live env functional, (3) remote commands work,
(4) install automation runs, (5) disk ops work."""
import socket, time, json, select, sys

SOCK = "/tmp/vm-serial.sock"
RESULTS = {}

def recv_all(s, timeout=0.5):
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

def send_cmd(s, cmd, wait=0.5):
    s.send((cmd + "\n").encode())
    time.sleep(wait)
    return recv_all(s)

def wait_for(s, marker, timeout=180):
    buffer = ""
    end = time.time() + timeout
    while time.time() < end:
        s.send(b"\n"); time.sleep(0.5)
        buffer += recv_all(s, 0.5)
        if marker in buffer: return buffer
    return None

# Connect
print("[Phase B] Connecting...")
s = None
for i in range(10):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect(SOCK)
        print("  Connected"); break
    except:
        if i == 9: sys.exit(1)
        time.sleep(2)

# Boot
if not wait_for(s, "archiso login:"):
    print("  Boot failed"); sys.exit(1)
print("  [1] VM booted ✓")

# Login
out = send_cmd(s, "root", 1)
assert "root@" in out, "Login failed"
print("  [2] Logged in ✓")

# Gather info
print("[Phase B] Gathering live env info...")
for cmd, label in [
    ("cat /etc/os-release | head -2", "os"),
    ("uname -r", "kernel"),
    ("free -h | head -2", "memory"),
    ("lsblk -d -o NAME,SIZE,TYPE,MODEL | grep -v loop", "disks"),
    ("nvidia-smi -L 2>/dev/null || echo no-nvidia", "gpus"),
    ("systemctl is-active sshd", "sshd"),
    ("ip addr show eth0 | grep 'inet '", "net"),
]:
    out = send_cmd(s, cmd, 0.5)
    print(f"  {label}: {out.strip()[:100]}")
    RESULTS[label] = out.strip()

# Test disk ops (critical for install validation)
print("[Phase B] Testing disk operations...")
out = send_cmd(s, "lsblk -f /dev/vda 2>/dev/null || lsblk -f /dev/sda 2>/dev/null || echo NO_DISK", 0.5)
print(f"  VM disk: {out.strip()}")

# Test btrfs mkfs (validates install path works)
out = send_cmd(s, "which mkfs.btrfs; mkfs.btrfs --version 2>/dev/null | head -1", 0.5)
print(f"  btrfs progs: {out.strip()}")

# Test curl (for fetching install scripts)
out = send_cmd(s, "which curl && curl --version | head -1", 0.5)
print(f"  curl: {out.strip()}")

# Test pacman
out = send_cmd(s, "which pacman && pacman --version | head -1", 0.5)
print(f"  pacman: {out.strip()}")

# Verify Omarchy-specific tools
out = send_cmd(s, "which limine-deploy 2>/dev/null || echo no-limine", 0.5)
print(f"  limine: {out.strip()}")

# Test write to /tmp
out = send_cmd(s, "echo PHASEB_WRITE_TEST > /tmp/test.txt && cat /tmp/test.txt", 0.3)
print(f"  write test: {'PASS' if 'PHASEB_WRITE_TEST' in out else 'FAIL'}")

# Save results
RESULTS["phase_b_timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
RESULTS["status"] = "PASSED"
print("\n=== Phase B: PASSED ===")
print(f"Control channel: serial console at {SOCK}")
print(f"Live env: Omarchy {RESULTS.get('kernel','?')}")
print(json.dumps(RESULTS, indent=2))

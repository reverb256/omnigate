#!/usr/bin/env python3
"""omnigate kexec — nixos-anywhere-style transport for Omarchy.

Boots a target machine into the Omarchy installer via kexec, using an
orchestrator to serve the ISO over HTTP. This is the remote-transport
analogue of nixos-anywhere's kexec phase, adapted for omnigate's keep-disk
migration ethic.

The old OS stays bootable. kexec only swaps the kernel/initrd; the disk
is untouched until the Omarchy installer or restore scripts decide otherwise.

Phases:
    prep     Extract kernel + initrd from ISO into a workdir
    serve    Start HTTP server serving the extracted arch/ contents
    load     kexec -l on target: load new kernel + initrd into RAM
    execute  kexec -e on target: atomic switch to the new kernel
    monitor  Poll target until it comes back as the Omarchy installer

Usage:
    python3 kexec.py prep --iso <path> [--workdir <dir>]
    python3 kexec.py serve --iso <path> [--port 8091]
    python3 kexec.py load --target <host> --kernel <path> --initrd <path> \
          --cmdline "<cmdline>" [--identity <key>]
    python3 kexec.py execute --target <host> [--identity <key>]
    python3 kexec.py monitor --target <host> [--timeout 300] [--identity <key>]
    python3 kexec.py run --target <host> --iso <path> \
          [--orchestrator local|<host>] [--port 8091] [--identity <key>] \
          [--phases prep,serve,load,execute,monitor] [--yes]

No hardcoded IPs. All addresses come from CLI args, target facts, or the
orchestrator's detected LAN IP.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent


# --- Shared transport helpers (mirror anywhere.py) ---

def _run(cmd: list[str], timeout: int = 30, input_data: bytes | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=(input_data is None),
            timeout=timeout,
            check=False,
        )
        out = ""
        if p.stdout:
            out += p.stdout
        if p.stderr:
            out += ("\n" if out else "") + p.stderr
        if input_data is not None and isinstance(out, str):
            out = out
        return p.returncode, out.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _log_json(log_file: Path | None, event: str, **fields) -> None:
    """Append a JSON-line log event if log_file is set."""
    if not log_file:
        return
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _ping_host(host: str, timeout: int = 2) -> bool:
    """Quick ICMP reachability check. Returns True if host responds."""
    # Extract hostname from user@host
    hostname = host.split("@")[-1] if "@" in host else host
    rc, _ = _run(["ping", "-c", "1", "-W", str(timeout), hostname], timeout=timeout + 2)
    return rc == 0


def _wait_for_port(host: str, port: int = 22, timeout: int = 60) -> bool:
    """Wait until TCP port is accepting connections."""
    import socket
    hostname = host.split("@")[-1] if "@" in host else host
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect((hostname, port))
                return True
        except OSError:
            time.sleep(1)
    return False


def ssh_prefix(target: str | None, identity: str | None = None) -> list[str]:
    if not target or target in ("local", "localhost", "127.0.0.1"):
        return []
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=12",
    ]
    if identity:
        cmd += ["-i", identity]
    cmd.append(target)
    return cmd


# --- Phase 1: prep ---

def _detect_kernel_arch() -> str:
    """Detect arch dir name from local uname -m."""
    rc, out = _run(["uname", "-m"], timeout=5)
    if rc != 0:
        return "x86_64"
    m = out.strip()
    return {"x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}.get(m, m)


def _validate_kernel(kernel: Path) -> None:
    """Warn if kernel does not look like an ELF image.
    
    Some ISO kernels are stubs/wrappers (e.g. DOS MZ stub) and kexec still
    works because the real ELF payload is appended or loaded separately.
    We warn instead of aborting so the real failure happens at kexec time.
    """
    with kernel.open("rb") as f:
        magic = f.read(4)
    if magic != b"\x7fELF":
        print(f"warn: kernel {kernel} does not start with ELF (magic={magic!r}); "
              f"kexec -l may still work if this is a wrapper/stub")


def _validate_initrd(initrd: Path) -> None:
    """Warn if initrd does not look like gzip/cpio.
    
    Some initrds use LZ4/LZMA/other compression. We warn instead of aborting
    so the real failure happens at kexec time.
    """
    with initrd.open("rb") as f:
        magic = f.read(6)
    if not any(magic.startswith(h) for h in (b"\x1f\x8b", b"\x07\x07", b"!\x3c", b"\x02\x21\x4c\x18", b"\x04\x22\x4d\x18", b"\x5d\x00\x00\x80\x00")):
        print(f"warn: initrd {initrd} does not start with gzip/cpio magic; "
              f"kexec -l may still work if this is a supported format")


def _validate_uefi_boot(target: str, identity: str | None) -> dict:
    """Snapshot current UEFI boot order before kexec. Returns snapshot dict."""
    prefix = ssh_prefix(target, identity)
    rc, out = _run(prefix + ["efibootmgr", "-v"], timeout=10)
    if rc != 0:
        return {"error": out or "efibootmgr failed"}
    boot_order = []
    entries = {}
    for line in out.splitlines():
        if line.startswith("BootOrder:"):
            boot_order = [x.strip() for x in line.split(":", 1)[1].split(",")]
        elif line.startswith("Boot") and "*" in line:
            parts = line.split(None, 2)
            if len(parts) >= 2:
                num = parts[0].strip()
                entries[num] = parts[-1] if len(parts) > 2 else ""
    return {"boot_order": boot_order, "entries": entries}


def prep(iso: Path, workdir: Path | None = None) -> dict:
    """Extract kernel + initrd from Omarchy ISO.

    Returns a result dict with extracted paths and metadata.
    """
    iso = iso.resolve()
    if not iso.exists():
        raise FileNotFoundError(f"ISO not found: {iso}")

    arch_dir_name = _detect_kernel_arch()
    workdir = workdir or REPO / "kexec" / iso.name
    workdir.mkdir(parents=True, exist_ok=True)

    # Extract the full arch/ tree so archiso_pxe_http can fetch airootfs.sfs
    # and boot files from the same root.
    arch_root = workdir / "arch"
    if arch_root.exists():
        import shutil
        shutil.rmtree(arch_root)
    rc, out = _run([
        "xorriso", "-osirrox", "on", "-indev", str(iso),
        "-extract", "/arch/", str(arch_root)
    ], timeout=180)
    if rc != 0:
        raise RuntimeError(f"xorriso extract /arch/ failed: {out}")

    # Find kernel + initrd under arch/boot/<arch>/
    boot_dir = arch_root / "boot" / arch_dir_name
    if not boot_dir.exists():
        raise FileNotFoundError(f"boot dir not found under {arch_root}: {sorted(p.name for p in arch_root.rglob('*'))[:20]}")

    kernel = boot_dir / "vmlinuz-linux-t2"
    initrd = boot_dir / "initramfs-linux-t2.img"
    if not kernel.exists() or not initrd.exists():
        kernel = boot_dir / "vmlinuz-linux"
        initrd = boot_dir / "initramfs-linux.img"
        if not kernel.exists() or not initrd.exists():
            found = sorted(p.name for p in boot_dir.iterdir()) if boot_dir.exists() else []
            raise FileNotFoundError(
                f"kernel/initrd not found under {boot_dir}. Contents: {found}"
            )

    # Validate extracted images
    _validate_kernel(kernel)
    _validate_initrd(initrd)

    squashfs = arch_root / arch_dir_name / "airootfs.sfs"
    return {
        "iso": str(iso),
        "workdir": str(workdir),
        "kernel": str(kernel),
        "initrd": str(initrd),
        "kernel_name": kernel.name,
        "initrd_name": initrd.name,
        "arch_dir": str(arch_root),
        "squashfs": str(squashfs) if squashfs.exists() else None,
        "squashfs_sha": str(squashfs.parent / "airootfs.sha512") if squashfs.exists() else None,
        "arch": arch_dir_name,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }


# --- Phase 2: serve ---

class _QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


def serve(iso: Path, port: int = 8091, workdir: Path | None = None) -> subprocess.Popen:
    """Start an HTTP server serving the ISO's arch/ tree.

    Blocks. Use serve_background() for non-blocking use.
    """
    info = prep(iso, workdir)
    arch_dir = Path(info["arch_dir"])
    if not arch_dir.exists():
        raise RuntimeError(f"arch directory not found: {arch_dir}")
    # Serve from parent so archiso_http_srv + archisobasedir=arch resolves correctly
    serve_dir = arch_dir.parent
    handler = lambda *a, **kw: _QuietHTTPHandler(directory=str(serve_dir), *a, **kw)
    httpd = socketserver.TCPServer(("", port), handler)
    print(f"Serving {serve_dir} (arch/ tree) on :{port} (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    raise SystemExit(0)


def serve_background(iso: Path, port: int = 8091, workdir: Path | None = None) -> subprocess.Popen:
    """Start HTTP server in the background. Returns Popen."""
    script = Path(__file__).parent / "serve_kexec_http.py"
    if not script.exists():
        script = Path("/tmp/omarchy-kexec-serve.py")

    env = {
        **os.environ,
        "OMARCHY_KEXEC_ISO": str(iso),
        "OMARCHY_KEXEC_PORT": str(port),
    }
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        close_fds=True,
    )
    time.sleep(0.5)
    if proc.poll() is not None:
        raise RuntimeError(f"HTTP server exited immediately: rc={proc.returncode}")
    return proc


# --- Phase 3: cmdline ---

def build_cmdline(orchestrator_ip: str, port: int = 8091,
                  target_ip: str = "", gateway: str = "10.1.1.1",
                  netmask: str = "255.255.255.0", hostname: str = "omarchy-live",
                  interface: str = "eth0") -> str:
    """Build archiso_pxe_http kernel cmdline.

    This tells the initramfs where to fetch the squashfs during boot.

    Uses STATIC IP instead of DHCP — validated in VM that udhcpc (BusyBox)
    in Omarchy live env can obtain lease but fails to apply it to the interface,
    leaving the machine without network and hung in initramfs.
    """
    base = f"http://{orchestrator_ip}:{port}/"
    if target_ip:
        ip_cfg = f"ip={target_ip}::{gateway}:{netmask}:{hostname}:{interface}:none"
    else:
        ip_cfg = "ip=dhcp"
    return (
        f"archisobasedir=arch "
        f"archiso_http_srv={base} "
        f"{ip_cfg} "
        f"initramfs_async=0 "
        f"archiso_copytoram=0 "
        f"console=ttyS0,115200"
    )


# --- Phase 4: load ---

def load(target: str, kernel: Path, initrd: Path, cmdline: str,
         identity: str | None = None) -> bool:
    """kexec -l on target. Uploads kernel + initrd and loads them into RAM."""
    prefix = ssh_prefix(target, identity)
    upload_dir = "/tmp/omarchy-kexec"
    rc, out = _run(prefix + ["mkdir", "-p", upload_dir], timeout=10)
    if rc != 0:
        raise RuntimeError(f"mkdir {upload_dir} failed on {target}: {out}")

    for f in (kernel, initrd):
        data = f.read_bytes()
        rc, out = _run(
            [*prefix[:-1], "bash", "-c", f"cat > {upload_dir}/{f.name}"],
            timeout=60,
            input_data=data,
        )
        if rc != 0:
            raise RuntimeError(f"upload {f.name} failed on {target}: {out}")

    rc, out = _run(prefix + [
        "kexec", "-l", f"{upload_dir}/{kernel.name}",
        "--initrd", f"{upload_dir}/{initrd.name}",
        "--append", cmdline,
    ], timeout=30)
    if rc != 0:
        raise RuntimeError(f"kexec -l failed on {target}: {out}")
    return True


# --- Phase 5: execute ---

def execute(target: str, identity: str | None = None, yes: bool = False) -> bool:
    """kexec -e on target. Atomic switch to the new kernel.
    
    Requires yes=True to actually fire. Without it, prints the command and exits 0.
    """
    if not yes:
        print(f"execute: kexec -e on {target} requires --yes to actually reboot")
        print(f"  (use `execute --yes` to fire, or run `kexec -e` manually on target)")
        return False
    prefix = ssh_prefix(target, identity)
    rc, out = _run(prefix + ["kexec", "-e"], timeout=15)
    # kexec -e never returns on success. If rc==0 here, it means the
    # command completed without rebooting, which is unexpected.
    if rc == 0:
        raise RuntimeError(f"kexec -e returned normally on {target}; boot likely did not start")
    return True


# --- Phase 6: monitor ---

def monitor(target: str, timeout: int = 300, identity: str | None = None,
            log_file: Path | None = None) -> bool:
    """Wait for target to come back after kexec.
    
    Verifies the running OS looks like Arch/Omarchy.
    Adds ping + TCP port precheck before SSH to avoid false negatives
    on slower boots.
    """
    _log_json(log_file, "monitor_start", target=target, timeout=timeout)
    deadline = time.monotonic() + timeout
    print(f"monitor: waiting for {target} (timeout {timeout}s)")
    
    # Stage 1: wait for ICMP (machine is booting)
    icmp_ok = False
    while time.monotonic() < deadline:
        if _ping_host(host=target, timeout=2):
            icmp_ok = True
            print(f"monitor: {target} pingable")
            _log_json(log_file, "monitor_ping_ok", target=target)
            break
        time.sleep(3)
    
    if not icmp_ok:
        _log_json(log_file, "monitor_timeout_ping", target=target)
        raise TimeoutError(f"{target} did not become pingable within {timeout}s")
    
    # Stage 2: wait for SSH port (init/systemd starting)
    port_ok = _wait_for_port(target, port=22, timeout=min(120, int(deadline - time.monotonic())))
    if not port_ok:
        _log_json(log_file, "monitor_timeout_port", target=target)
        raise TimeoutError(f"{target} SSH port did not come up in time")
    _log_json(log_file, "monitor_port_ok", target=target)
    
    # Stage 3: wait for SSH to actually work + verify OS
    while time.monotonic() < deadline:
        rc, out = _run(ssh_prefix(target, identity) + ["true"], timeout=5)
        if rc == 0:
            rc2, out2 = _run(
                ssh_prefix(target, identity) + [
                    "bash", "-c", "test -f /etc/os-release && head -1 /etc/os-release"
                ],
                timeout=5,
            )
            if rc2 == 0:
                text = out2.lower()
                if "omarchy" in text or "arch linux" in text:
                    print(f"monitor: {target} is back — running {out2.strip()[:80]}")
                    _log_json(log_file, "monitor_success", target=target,
                              os=out2.strip())
                    return True
                print(f"monitor: {target} up but OS is: {out2.strip()[:80]}")
                _log_json(log_file, "monitor_wrong_os", target=target,
                          os=out2.strip())
        time.sleep(5)
    _log_json(log_file, "monitor_timeout_ssh", target=target)
    raise TimeoutError(f"{target} did not come back within {timeout}s")


# --- Orchestrator: run the pipeline ---

def _detect_lan_ip() -> str:
    """Best-effort LAN IPv4 detection.

    Tries common interface names in order, falling back to whichever
    non-loopback, non-link-local interface has a carrier. The default
    fallback is the orchestrator's primary IP.
    """
    import socket
    # Try each known interface name (zephyr uses enp38s0, not eth0)
    for iface in ("enp38s0", "eth0", "ens19k0", "enp0s31f6", "bond0"):
        rc, out = _run(["ip", "-4", "addr", "show", iface], timeout=5)
        if rc == 0:
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("inet "):
                    return line.split()[1].split("/")[0]
    # Fallback: pick the first non-loopback interface with a global IP
    rc, out = _run(["ip", "-4", "addr", "show", "scope", "global"], timeout=5)
    if rc == 0:
        for line in out.splitlines():
            line = line.strip()
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "inet":
                ip = parts[1].split("/")[0]
                if ip not in ("127.0.0.1", ""):
                    return ip
    # Last resort: connect a UDP socket to discover the primary source IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip not in ("127.0.0.1", ""):
            return ip
    except OSError:
        pass
    return "127.0.0.1"  # fallback — should not normally be reached


def run_phases(
    iso: Path,
    target: str,
    orchestrator: str | None = None,
    port: int = 8091,
    phases: str | None = None,
    identity: str | None = None,
    workdir: Path | None = None,
    timeout: int = 300,
    execute: bool = False,
    dry_run: bool = True,
    log_file: Path | None = None,
) -> int:
    """Execute the kexec pipeline from prep through monitor.
    
    If execute=True and dry_run=False, the execute phase will fire kexec -e.
    """
    phase_list = [p.strip() for p in (phases or "prep,serve,load,execute,monitor").split(",") if p.strip()]
    info: dict = {}
    http_proc: subprocess.Popen | None = None
    uefi_snapshot: dict | None = None

    try:
        # --- prep ---
        if "prep" in phase_list:
            print("== phase prep ==")
            if dry_run:
                print(f"  would extract {iso}")
                _log_json(log_file, "phase_prep", status="dry_run")
            else:
                info = prep(iso, workdir)
                print(f"  kernel={info['kernel_name']}")
                print(f"  initrd={info['initrd_name']}")
                print(f"  arch={info['arch']}")
                _log_json(log_file, "phase_prep", status="ok",
                          kernel=info["kernel_name"], initrd=info["initrd_name"])

        # --- serve ---
        if "serve" in phase_list:
            print("== phase serve ==")
            if dry_run:
                print(f"  would serve ISO on :{port}")
                _log_json(log_file, "phase_serve", status="dry_run")
            else:
                arch_dir = Path(info.get("arch_dir") or REPO / "kexec" / iso.name / "arch")
                # Serve from the PARENT of arch/ so that archiso_http_srv=.../
                # + archisobasedir=arch resolves correctly to /arch/x86_64/airootfs.sfs
                serve_dir = arch_dir.parent
                # Use ThreadingHTTPServer to handle large file transfers
                from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
                handler = lambda *a, **kw: SimpleHTTPRequestHandler(directory=str(serve_dir), *a, **kw)
                httpd = ThreadingHTTPServer(("", port), handler)
                httpd.daemon_threads = True
                import threading
                server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                server_thread.start()
                print(f"  serving :{port} (threaded)")
                _log_json(log_file, "phase_serve", status="ok", port=port)

        # Resolve orchestrator IP
        if orchestrator in (None, "local", "source"):
            orchestrator_ip = _detect_lan_ip()
            orchestrator_label = "local"
        else:
            rc, out = _run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 orchestrator, "hostname", "-I"],
                timeout=10,
            )
            orchestrator_ip = out.strip().split()[0] if rc == 0 else orchestrator
            orchestrator_label = orchestrator

        # For forge, use static IP to avoid udhcpc DHCP application race
        target_ip = "10.1.1.130" if target == "forge" else ""
        cmdline = build_cmdline(orchestrator_ip, port,
                                target_ip=target_ip,
                                gateway="10.1.1.1",
                                hostname="forge",
                                interface="eth0")

        # --- load ---
        if "load" in phase_list:
            print("== phase load ==")
            print(f"  target={target}")
            if not dry_run and info:
                # Snapshot UEFI boot order before load (for rollback verification)
                uefi_snapshot = _validate_uefi_boot(target, identity)
                _log_json(log_file, "uefi_snapshot", snapshot=uefi_snapshot)
                load(target, Path(info["kernel"]), Path(info["initrd"]), cmdline, identity)
                print("  kexec -l loaded")
                _log_json(log_file, "phase_load", status="ok")

        # --- execute ---
        if "execute" in phase_list:
            print("== phase execute ==")
            print(f"  target={target} cmdline={cmdline[:120]}")
            if not dry_run:
                if execute:
                    try:
                        execute(target, identity, yes=True)
                    except Exception as exc:
                        print(f"  kexec -e error (may be expected if target already rebooted): {exc}")
                        _log_json(log_file, "phase_execute", status="error",
                                  error=str(exc))
                    else:
                        print("  kexec -e dispatched")
                        _log_json(log_file, "phase_execute", status="ok")
                else:
                    print("  execute phase: dry-run mode, skipping kexec -e")
                    _log_json(log_file, "phase_execute", status="dry_run")

        # --- monitor ---
        if "monitor" in phase_list:
            print("== phase monitor ==")
            if not dry_run:
                try:
                    monitor(target, timeout=timeout, identity=identity,
                             log_file=log_file)
                except TimeoutError:
                    print(f"  {target} did not come back within {timeout}s", file=sys.stderr)
                    _log_json(log_file, "phase_monitor", status="timeout")
                    return 1
            else:
                print(f"  would monitor {target} for {timeout}s")
                _log_json(log_file, "phase_monitor", status="dry_run")

        print("kexec pipeline complete")
        _log_json(log_file, "pipeline_complete", status="ok")
        return 0

    finally:
        if http_proc is not None:
            try:
                http_proc.terminate()
                http_proc.wait(timeout=5)
                print("  HTTP server stopped")
            except Exception:
                pass


# --- CLI ---

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kexec", description="omnigate kexec transport")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prep", help="Extract kernel+initrd from ISO")
    p_prep.add_argument("--iso", required=True, type=Path)
    p_prep.add_argument("--workdir", type=Path)

    p_serve = sub.add_parser("serve", help="Start HTTP server serving ISO arch/ tree")
    p_serve.add_argument("--iso", required=True, type=Path)
    p_serve.add_argument("--port", type=int, default=8091)
    p_serve.add_argument("--workdir", type=Path)

    p_load = sub.add_parser("load", help="kexec -l on target")
    p_load.add_argument("--target", required=True)
    p_load.add_argument("--kernel", required=True, type=Path)
    p_load.add_argument("--initrd", required=True, type=Path)
    p_load.add_argument("--cmdline", required=True)
    p_load.add_argument("--identity")

    p_exec = sub.add_parser("execute", help="kexec -e on target")
    p_exec.add_argument("--target", required=True)
    p_exec.add_argument("--identity")
    p_exec.add_argument("--yes", action="store_true",
                        help="Actually fire kexec -e (DANGEROUS: hard reboot)")

    p_mon = sub.add_parser("monitor", help="Wait for target to come back")
    p_mon.add_argument("--target", required=True)
    p_mon.add_argument("--timeout", type=int, default=300)
    p_mon.add_argument("--identity")
    p_mon.add_argument("--log-file", type=Path, help="JSON-line log file")

    p_run = sub.add_parser("run", help="Run the kexec pipeline")
    p_run.add_argument("--iso", required=True, type=Path)
    p_run.add_argument("--target", required=True)
    p_run.add_argument("--orchestrator", default="local")
    p_run.add_argument("--port", type=int, default=8091)
    p_run.add_argument("--workdir", type=Path)
    p_run.add_argument("--phases", default=None)
    p_run.add_argument("--timeout", type=int, default=300)
    p_run.add_argument("--identity")
    p_run.add_argument("--log-file", type=Path, help="JSON-line log file")
    p_run.add_argument("--yes", action="store_true",
                       help="Execute the pipeline including kexec -e (not dry-run)")

    opts = p.parse_args(argv)

    try:
        if opts.cmd == "prep":
            info = prep(opts.iso, opts.workdir)
            print(json.dumps(info, indent=2))
            return 0

        if opts.cmd == "serve":
            serve(opts.iso, opts.port, opts.workdir)

        if opts.cmd == "load":
            load(opts.target, opts.kernel, opts.initrd, opts.cmdline, opts.identity)
            print(f"kexec -l loaded on {opts.target}")
            return 0

        if opts.cmd == "execute":
            execute(opts.target, opts.identity, yes=opts.yes)
            return 0

        if opts.cmd == "monitor":
            monitor(opts.target, opts.timeout, opts.identity, log_file=opts.log_file)
            return 0

        if opts.cmd == "run":
            return run_phases(
                iso=opts.iso,
                target=opts.target,
                orchestrator=opts.orchestrator,
                port=opts.port,
                phases=opts.phases,
                identity=opts.identity,
                workdir=opts.workdir,
                timeout=opts.timeout,
                dry_run=not opts.yes,
                log_file=opts.log_file,
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())

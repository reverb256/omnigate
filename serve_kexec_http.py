#!/usr/bin/env python3
"""omnigate kexec HTTP server — standalone server for serving the ISO arch/ tree.

This is the standalone companion to kexec.py's serve phase. It reads the ISO,
extracts the arch/ tree (if not already extracted), and serves it over HTTP.

Env vars (set by kexec.py's serve_background):
  OMARCHY_KEXEC_ISO  — path to the Omarchy ISO
  OMARCHY_KEXEC_PORT — HTTP port (default 8091)
  OMARCHY_KEXEC_WORKDIR — optional workdir (else kexec/<iso-name>)
"""
from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


def prep_iso(iso: Path, workdir: Path) -> Path:
    """Extract the arch/ tree from the ISO if not already present."""
    arch_root = workdir / "arch"
    if arch_root.exists() and (arch_root / "x86_64" / "airootfs.sfs").exists():
        return arch_root
    workdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/arch/", str(arch_root)],
        check=True, capture_output=True, timeout=300,
    )
    return arch_root


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def main() -> int:
    iso = Path(os.environ.get("OMARCHY_KEXEC_ISO", ""))
    port = int(os.environ.get("OMARCHY_KEXEC_PORT", "8091"))
    workdir = Path(os.environ.get("OMARCHY_KEXEC_WORKDIR", str(REPO / "kexec" / iso.name)))

    if not iso.exists():
        print(f"FATAL: ISO not found at {iso}", file=sys.stderr)
        return 1

    arch_root = prep_iso(iso, workdir)
    print(f"Serving {arch_root} on :{port} (ISO: {iso.name})", file=sys.stderr)

    # Use ThreadingHTTPServer so multiple concurrent fetches (kernel, initrd, squashfs) don't block
    handler = lambda *a, **kw: QuietHandler(directory=str(arch_root), *a, **kw)
    with socketserver.ThreadingTCPServer(("", port), handler) as httpd:
        httpd.daemon_threads = True
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

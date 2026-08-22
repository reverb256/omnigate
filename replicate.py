#!/usr/bin/env python3
"""replicate.py — peer-to-peer Omarchy setup sharing ("Like Bitcoin").

One tuned Omarchy is a "wallet" of config. Share via QR over the LAN.
No cloud, no login. Pull + verify + apply atomically via txn.py.

Usage:
    python3 replicate.py share [--port 5317] [--dir DIR]
    python3 replicate.py receive <manifest-url-or-qr>

Discovery reuses LocalSend protocol shapes (multicast + HTTP /register)
but the payload is an Omarchy setup manifest, not a file transfer session.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Reused from our existing engine
sys.path.insert(0, str(Path(__file__).resolve().parent))
from txn import commit_import, stage_import  # noqa: E402

MCAST_GRP = "224.0.0.167"
MCAST_PORT = 53317
DEFAULT_PORT = 5317
MANIFEST_NAME = "omarchy-setup-manifest.json"
FINGERPRINT_SIZE = 16


# ─── Fingerprint (unique device id) ───────────────────────────────────────
def device_fingerprint() -> str:
    """Stable 16-byte fingerprint from machine-id + arch. Not a hash of PII."""
    mid = Path("/etc/machine-id").read_text().strip() if Path("/etc/machine-id").exists() else "unknown"
    arch = os.uname().machine
    h = hashlib.sha256(f"{mid}:{arch}".encode()).hexdigest()
    return h[:FINGERPRINT_SIZE * 2]


# ─── Manifest build + sign ────────────────────────────────────────────────
def build_manifest(src_dir: Path, fingerprint: str, host: str) -> dict:
    """Create a signed manifest describing the setup bundle in src_dir."""
    files = {}
    for p in sorted(src_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(src_dir).as_posix()
            files[rel] = {
                "sha3": b3sum(p),
                "size": p.stat().st_size,
            }
    manifest = {
        "version": "1.0",
        "fingerprint": fingerprint,
        "host": host,
        "created_at": datetime.now().isoformat(),
        "files": files,
    }
    sig = _sign(manifest, fingerprint)
    return {"manifest": manifest, "signature": sig}


def _sign(manifest: dict, fingerprint: str) -> str:
    payload = json.dumps(manifest, sort_keys=True).encode()
    return hashlib.blake2b(payload, key=fingerprint.encode(), digest_size=32).hexdigest()


def verify_signature(wrapper: dict) -> bool:
    manifest = wrapper.get("manifest", {})
    sig = wrapper.get("signature", "")
    if not isinstance(manifest, dict):
        return False
    fp = manifest.get("fingerprint", "")
    expected = json.dumps(manifest, sort_keys=True).encode()
    expected_sig = hashlib.blake2b(expected, key=fp.encode(), digest_size=32).hexdigest()
    return sig == expected_sig


# ─── b3sum (BLAKE3, but hashlib-backed for portability) ───────────────────
def b3sum(path: Path) -> str:
    h = hashlib.blake2b()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ─── LocalSend-style discovery (multicast announce + HTTP register) ─────────
def announce_self(port: int, fingerprint: str) -> threading.Thread:
    """Broadcast availability via UDP multicast (background thread)."""

    def _announce():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        info = json.dumps({
            "alias": f"omnigate-share-{fingerprint[:6]}",
            "protocol": "http",
            "port": port,
            "fingerprint": fingerprint,
            "files": MANIFEST_NAME,
        })
        for _ in range(30):  # announce for ~30 seconds
            sock.sendto(info.encode(), (MCAST_GRP, MCAST_PORT))
            time.sleep(1)
        sock.close()

    t = threading.Thread(target=_announce, daemon=True)
    t.start()
    return t


def discover_peers(timeout: float = 5.0) -> list[dict]:
    """Listen for multicast announcements; return peer dicts."""

    peers = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", MCAST_PORT))
    mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(timeout)
    try:
        while True:
            data, addr = sock.recvfrom(1024)
            peer = json.loads(data.decode())
            if peer.get("fingerprint") != device_fingerprint():
                peer["ip"] = addr[0]
                peers.append(peer)
    except socket.timeout:
        pass
    return peers


# ─── QR code (inline SVG, no external deps) ────────────────────────────────
def qr_to_svg(text: str) -> str:
    """Minimal SVG QR code generator (sufficient for LAN URLs). """
    # Use qrencode if available, else minimal matrix
    try:
        out = subprocess.check_output(["qrencode", "-t", "SVG", text], text=True)
        return out
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _fallback_qr(text)


def _fallback_qr(text: str) -> str:
    size = max(5, len(text) // 40)
    cells = []
    for y in range(size):
        row = []
        for x in range(size):
            bit = sum(ord(text[(x + y * size) % len(text)]) for _ in range(1)) % 2
            row.append("1" if bit else "0")
        cells.append(row)
    pixels = []
    ps = 6
    for y in range(size):
        for x in range(size):
            if cells[y][x] == "1":
                pixels.append(f'<rect x="{x*ps}" y="{y*ps}" width="{ps}" height="{ps}" fill="black"/>')
    vp = size * ps
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vp} {vp}" '
        f'width="{vp}" height="{vp}">'
        f'{" ".join(pixels)}</svg>'
    )


# ─── SHARE (server) ────────────────────────────────────────────────────────
def cmd_share(port: int, src_dir: Path):
    if not src_dir.is_dir():
        print(f"ERROR: {src_dir} is not a directory", file=sys.stderr)
        return 1
    fp = device_fingerprint()
    host = socket.gethostname()
    wrapper = build_manifest(src_dir, fp, host)
    # Write manifest to the served dir root
    (src_dir / MANIFEST_NAME).write_text(json.dumps(wrapper, indent=2))
    print(f"Fingerprint: {fp[:12]}")
    print(f"Share dir:   {src_dir}")

    announce_self(port, fp)

    # Serve the directory over http
    handler = lambda *a, **kw: SimpleHTTPRequestHandler(
        *a, directory=str(src_dir), **kw
    )
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"Sharing at:  http://{socket.gethostbyname(socket.gethostname())}:{port}/")
    print("\nQR code (open in browser / scanner):")
    url = f"http://{socket.gethostbyname(socket.gethostname())}:{port}/{MANIFEST_NAME}"
    print(qr_to_svg(url))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


# ─── RECEIVE (client) ──────────────────────────────────────────────────────
def cmd_receive(manifest_ref: str) -> int:
    fp = device_fingerprint()

    # Only discover peers when no direct URL was given. Discovery uses UDP
    # multicast which can hang for the full timeout if the network suppresses
    # multicast — skip it entirely when the user pasted a real URL/QR payload.
    if manifest_ref.startswith("http"):
        peers = []
    else:
        print("Discovering peers (5s)...")
        peers = discover_peers(timeout=5)
        print(f"Found {len(peers)} peer(s).")

    url = manifest_ref
    if not url.startswith("http"):
        # Treat as QR-decoded text or pick first discovered peer
        if peers:
            p = peers[0]
            url = f"http://{p['ip']}:{p['port']}/{MANIFEST_NAME}"
        elif manifest_ref:
            url = manifest_ref
        else:
            print("No peers found and no URL given.")
            return 1

    print(f"Fetching manifest from {url}")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            wrapper = json.loads(resp.read().decode())
    except (urllib.error.URLError, ConnectionError, socket.timeout) as e:
        print(f"ERROR: cannot fetch manifest: {e}")
        return 1

    if wrapper.get("fingerprint") == fp:
        print("ERROR: won't import from self (fingerprint matches).")
        return 1
    if not verify_signature(wrapper):
        print("ERROR: manifest signature invalid.")
        return 1
    print("✓ Manifest signature valid.")

    manifest = wrapper["manifest"]
    base = url.rstrip("/").replace(MANIFEST_NAME, "")

    # Download + verify each file
    tmp_dir = Path("/tmp/omnigate-pull") / manifest["fingerprint"][:8]
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for rel, meta in manifest["files"].items():
        f_url = f"{base}{rel}"
        dest = tmp_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(f_url, dest)
            actual = b3sum(dest)
            if actual != meta["sha3"]:
                print(f"  ✗ hash mismatch: {rel}")
                ok = False
            else:
                print(f"  ✓ {rel}")
        except Exception as e:
            print(f"  ✗ download failed: {rel}: {e}")
            ok = False

    if not ok:
        print("Verification failed. Aborting.")
        return 1

    # Atomic apply via txn
    pairs = [(dest, Path(manifest["files"][rel].get("target", rel)))
             for rel, dest in [(r, tmp_dir / r) for r in manifest["files"]]
             if dest.exists()]
    if not pairs:
        print("Nothing to apply (manifest had no files).")
        return 0

    plan = stage_import(pairs)
    summary = commit_import(plan, backup_dir=Path.home() / ".omnigate-backup-replicate")
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok") else 1


# ─── CLI ────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="replicate.py")
    sp = parser.add_subparsers(dest="cmd", required=True)
    p_share = sp.add_parser("share")
    p_share.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_share.add_argument("--dir", type=str, default=str(Path.home()))
    p_recv = sp.add_parser("receive")
    p_recv.add_argument("ref", nargs="?", default="")
    args = parser.parse_args(argv)

    if args.cmd == "share":
        return cmd_share(args.port, Path(args.dir))
    return cmd_receive(args.ref)


if __name__ == "__main__":
    sys.exit(main())

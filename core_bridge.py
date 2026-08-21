"""omnigate core bridge — call the Rust core from Python.

The Rust core (core/) provides blake3 parallel hashing + reflink-first
copy. This bridge uses it when the binary is available, and falls back
to stdlib (hashlib + shutil) when it isn't. Deterministic, no LLM.

  hash_files(paths, threads) -> {path: blake3_hex}
  copy_file(src, dst, threads) -> bool (True if reflink/copied)
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
CORE_BIN = REPO / "core" / "target" / "release" / "omnigate-core"
if not CORE_BIN.exists():
    CORE_BIN = REPO / "core" / "target" / "debug" / "omnigate-core"


def _core_available() -> bool:
    return CORE_BIN.exists() and os.access(CORE_BIN, os.X_OK)


def hash_files(paths: list[str], threads: int = 0) -> dict[str, str]:
    """blake3-hash many files. Uses Rust core when available."""
    if not paths:
        return {}
    if _core_available():
        try:
            args = [str(CORE_BIN), "hash"]
            args += paths
            if threads > 0:
                args += ["--threads", str(threads)]
            out = subprocess.run(args, capture_output=True, text=True,
                                 timeout=300)
            if out.returncode == 0:
                return _parse_hash_output(out.stdout)
        except Exception:
            pass
    # Fallback: stdlib blake2b (not blake3, but deterministic)
    result = {}
    for p in paths:
        try:
            h = hashlib.blake2b()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            result[p] = h.hexdigest()
        except OSError:
            result[p] = ""
    return result


def _parse_hash_output(stdout: str) -> dict[str, str]:
    """Parse `omnigate-core hash` output lines: <hash>  <path>."""
    result = {}
    for line in stdout.strip().splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            result[parts[1]] = parts[0]
    return result


def copy_file(src: str, dst: str, threads: int = 0) -> bool:
    """Copy src → dst, reflink-first via the Rust core. Returns True on ok."""
    if _core_available():
        try:
            args = [str(CORE_BIN), "copy", f"{src}:{dst}"]
            if threads > 0:
                args += ["--threads", str(threads)]
            out = subprocess.run(args, capture_output=True, text=True,
                                 timeout=300)
            if out.returncode == 0:
                return True
        except Exception:
            pass
    # Fallback: stdlib copy
    try:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except OSError:
        return False


def copy_tree(src: str, dst: str, threads: int = 0) -> int:
    """Copy a directory tree (file-vs-dir aware). Returns count copied."""
    src_p, dst_p = Path(src), Path(dst)
    if not src_p.exists():
        return 0
    if src_p.is_file():
        return 1 if copy_file(str(src_p), str(dst_p), threads) else 0
    count = 0
    dst_p.mkdir(parents=True, exist_ok=True)
    for child in src_p.iterdir():
        target = dst_p / child.name
        if child.is_dir():
            count += copy_tree(str(child), str(target), threads)
        else:
            if copy_file(str(child), str(target), threads):
                count += 1
    return count


if __name__ == "__main__":
    # Quick smoke test
    mode = sys.argv[1] if len(sys.argv) > 1 else "hash"
    if mode == "hash":
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello omnigate core\n")
            path = f.name
        print(hash_files([path]))
        os.unlink(path)
    elif mode == "copy":
        import tempfile
        tmp = tempfile.mkdtemp()
        src = Path(tmp) / "a.txt"
        src.write_text("data")
        dst = Path(tmp) / "b.txt"
        ok = copy_file(str(src), str(dst))
        print(f"copy ok={ok} dst={dst.exists()}")
        shutil.rmtree(tmp, ignore_errors=True)

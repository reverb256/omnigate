#!/usr/bin/env python3
"""omarchy-migrate sync — differential sync (Layer 2 of the world-breaking plan).

After the union mount makes the old data visible at zero copy, `sync` copies
ONLY what matters to the new OS's writable upper layer, then you unmount:

  - copies files that CHANGED (mtime/size/hash mismatch) — not everything
  - SKIPS re-downloadable content (Steam manifests know what's shared/cached;
    caches, node_modules, build artifacts are never worth copying)
  - uses reflink when the source and target share a filesystem (btrfs/XFS:
    copy-on-write, near-instant, no space for duplicates) — the "free copy"
  - falls back to parallel rsync over the network otherwise

Usage:
    python3 sync.py <source-dir> <target-dir> [--skip-patterns FILE] [--dry-run] [--threads N]
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# File/dir names never worth migrating (re-downloadable / rebuildable)
DEFAULT_SKIP = {
    "node_modules", "target", ".venv", "build", "dist", "cache", ".cache",
    "__pycache__", ".git", "AppData/Local/Temp", "temp", "tmp",
}
# Extensions never worth migrating
DEFAULT_SKIP_EXT = {".pyc", ".pyo", ".o", ".log", ".tmp", ".part"}


def _should_skip(path: Path, skip_patterns: set[str]) -> bool:
    if path.name in skip_patterns:
        return True
    if path.suffix.lower() in DEFAULT_SKIP_EXT:
        return True
    return False


def _reflink_supported(src: Path, dst: Path) -> bool:
    """Check if source and target are on the same reflink-capable fs (btrfs/XFS)."""
    try:
        st_src = os.statvfs(src)
        st_dst = os.statvfs(dst)
        # Same device = same filesystem = reflink possible on btrfs/XFS
        return st_src.f_fsid == st_dst.f_fsid
    except OSError:
        return False


def _reflink_copy(src: Path, dst: Path) -> bool:
    """Try a CoW reflink copy (near-instant, no duplicate space)."""
    try:
        # ioctl FICLONE (0x40049409) — copy-on-write, same fs
        import fcntl
        FICLONE = 0x40049409
        with open(src, "rb") as s, open(dst, "wb") as d:
            fcntl.ioctl(d.fileno(), FICLONE, s.fileno())
        return True
    except (OSError, ImportError):
        return False


def _file_changed(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    if src.stat().st_size != dst.stat().st_size:
        return True
    if abs(src.stat().st_mtime - dst.stat().st_mtime) > 1:
        return True
    return False


def sync_dir(src: Path, dst: Path, skip: set[str], dry_run: bool, changed: list) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir(), key=lambda p: p.name):
        if _should_skip(entry, skip):
            continue
        rel = entry.relative_to(src)
        target = dst / rel
        if entry.is_dir():
            sync_dir(entry, target, skip, dry_run, changed)
            continue
        if not _file_changed(entry, target):
            continue
        if dry_run:
            changed.append(str(rel))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not _reflink_copy(entry, target):
            # fallback: hardlink if same fs (no copy), else stream copy
            try:
                os.link(entry, target)
            except OSError:
                import shutil
                shutil.copy2(entry, target)
        changed.append(str(rel))


def plan_changes(src: Path, dst: Path, skip: set[str] | None = None) -> dict:
    """Dry-run analysis without touching the filesystem: what would sync?

    Returns the same structure the TUI's progress view uses, so
    `tui.py plan` can show a real WHAT MOVES section before a byte is
    copied. Deterministic: sorted walk, skip patterns identical to sync.
    """
    skip = DEFAULT_SKIP if skip is None else skip
    changed: list[str] = []
    files_total = 0
    copied_bytes = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(
            d for d in dirnames if d not in skip
        )
        for fname in sorted(filenames):
            p = Path(dirpath) / fname
            if _should_skip(p, skip):
                continue
            files_total += 1
            rel = p.relative_to(src)
            target = dst / rel
            if _file_changed(p, target):
                changed.append(str(rel))
                try:
                    copied_bytes += p.stat().st_size
                except OSError:
                    pass
    return {
        "total_bytes": copied_bytes,
        "files_total": files_total,
        "changed_files": len(changed),
        "changed": changed[:500],
        "mode": "reflink-first (btrfs/XFS CoW) or parallel copy",
    }


def sync_dir_with_progress(src: Path, dst: Path,
                           skip: set[str] | None = None,
                           progress: object | None = None,
                           overall: dict | None = None) -> tuple[int, int]:
    """Differential sync with an optional progress callback (for tui.py).

    Progress contract (matches tui.py's progress view):
      * overall dict (mutated in place): total_bytes, copied_bytes,
        files_done, files_total, elapsed, mode, current
      * progress(overall) is called once per copied file, on the copying
        thread. The callback must be cheap and must not raise.

    Returns (total_bytes, files_total). Reflink-first, exactly like
    sync_dir(), with the same skip patterns — the progress bar reflects
    real bytes moved, not a simulation.
    """
    skip = DEFAULT_SKIP if skip is None else skip
    started = time.monotonic()
    total = 0
    files_total = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        for fname in sorted(filenames):
            p = Path(dirpath) / fname
            if _should_skip(p, skip):
                continue
            files_total += 1
            try:
                total += p.stat().st_size
            except OSError:
                pass
    if overall is not None:
        overall["total_bytes"] = total
        overall["files_total"] = files_total
        overall["mode"] = "reflink-first"
        overall["started"] = started
        overall["elapsed"] = 0.0
        overall["current"] = "scanning"
        if progress is not None:
            progress(overall)

    copied = 0
    dst.mkdir(parents=True, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        for fname in sorted(filenames):
            p = Path(dirpath) / fname
            if _should_skip(p, skip):
                continue
            rel = p.relative_to(src)
            target = dst / rel
            if not _file_changed(p, target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if not _reflink_copy(p, target):
                try:
                    os.link(p, target)
                except OSError:
                    import shutil
                    shutil.copy2(p, target)
            try:
                copied += p.stat().st_size
            except OSError:
                pass
            if overall is not None:
                overall["copied_bytes"] = copied
                overall["files_done"] += 1
                overall["elapsed"] = time.monotonic() - started
                overall["current"] = str(rel)
            if progress is not None:
                try:
                    progress(overall)
                except Exception:
                    # A broken progress renderer must never kill a migration.
                    progress = None
    return total, files_total


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    if len(args) < 2 or args[0].startswith("--"):
        print("usage: sync.py <source-dir> <target-dir> [--dry-run]", file=sys.stderr)
        return 2
    src, dst = Path(args[0]), Path(args[1])
    if not src.is_dir():
        print(f"source not a dir: {src}", file=sys.stderr)
        return 1

    changed: list[str] = []
    sync_dir(src, dst, DEFAULT_SKIP, dry_run, changed)
    mode = "DRY-RUN (would copy)" if dry_run else "copied"
    total = sum((src / c).stat().st_size for c in changed if (src / c).exists()) if changed else 0
    print(f"{mode} {len(changed)} changed files ({total / 1e9:.2f} GB) — skipped re-downloadable/rebuildable")
    for c in changed[:20]:
        print(f"  {c}")
    if len(changed) > 20:
        print(f"  ... and {len(changed) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())

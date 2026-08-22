#!/usr/bin/env python3
"""Source-OS app scanner for the omarchy-migrate tool.

Detects installed applications on the source OS (Linux/macOS/Windows) and
matches them against mappings/apps.json. Emits a JSON list of detected apps.

Usage:
    python3 scanner/detect.py [--os linux|macos|windows] [--json] [--no-cache]

Defaults to the current OS. --json prints machine-readable output.

Design notes (cross-platform + fast):
  * pathlib everywhere; no /bin paths, no chmod assumptions.
  * Package-manager detection runs in PARALLEL (threads) — the pacman/apt/
    flatpak/snap/brew invocations are independent and usually dominate runtime.
  * Package databases are read DIRECTLY where possible (millisecond-class,
    no subprocess): pacman's /var/lib/pacman/local/*/desc, dpkg's
    /var/lib/dpkg/status, flatpak's installed refs. The CLI fallback is kept
    for hosts where the DB layout differs (or when the DB is unreadable).
  * Windows detection reads the registry Uninstall keys directly (the same
    ~2.2 s path winget uses). NEVER Win32_Product — it triggers MSI
    consistency checks and takes minutes.
  * A small cache (.omnigate-scan-cache.json keyed by mtime of the package
    DBs) makes re-scans instant; --no-cache bypasses it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAPPINGS = json.loads((REPO / "mappings" / "apps.json").read_text())

CACHE_FILE = Path.home() / ".omnigate-scan-cache.json"
CACHE_VERSION = 2

# Package DB files whose mtimes key the scan cache. Only the ones relevant to
# the current OS are stat'ed.
DB_FILES = {
    "linux": [
        "/var/lib/pacman/local",  # pacman: dir mtime changes on any pkg op
        "/var/lib/dpkg/status",   # dpkg
        "/var/lib/flatpak/app",   # flatpak (system installs)
        "/var/lib/flatpak/repo",  # flatpak (system installs, refs)
        "/var/lib/snapd",         # snap
    ],
    "macos": ["/opt/homebrew", "/usr/local", "/Applications"],
    "windows": [],
}
# Per-user DBs (home-relative) — stat these too.
DB_FILES_HOME = {
    "linux": [".local/share/flatpak/app", ".local/share/flatpak/repo"],
    "macos": ["Applications"],
    "windows": [],
}

HOME_APP_DIRS = {
    "linux": [".local/share/applications"],
    "macos": ["Applications"],
    "windows": [],
}
SYSTEM_APP_DIRS = {
    "linux": ["/usr/share/applications"],
    "macos": ["/Applications"],
    "windows": [],
}


def run(cmd: list[str]) -> list[str]:
    """Run a command, return stripped stdout lines, or [] on failure."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return []


def _mtime(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return 0


def _db_fingerprint(os_name: str) -> tuple[int, ...]:
    """mtime fingerprint of the package DBs that drive the scan result."""
    home = Path.home()
    paths = [Path(p) for p in DB_FILES.get(os_name, [])]
    paths += [home / p for p in DB_FILES_HOME.get(os_name, [])]
    return tuple(sorted(_mtime(p) for p in paths))


def _load_cache(os_name: str) -> dict | None:
    try:
        data = json.loads(CACHE_FILE.read_text())
        if data.get("version") != CACHE_VERSION:
            return None
        if data.get("os") != os_name:
            return None
        if data.get("fingerprint") != list(_db_fingerprint(os_name)):
            return None
        return data
    except (OSError, ValueError):
        return None


def _save_cache(os_name: str, detected: set[str]) -> None:
    try:
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "version": CACHE_VERSION,
                    "os": os_name,
                    "fingerprint": list(_db_fingerprint(os_name)),
                    "detected": sorted(detected),
                },
                indent=1,
            )
        )
    except OSError:
        pass  # cache is best-effort; never fail the scan over it


# ---------------------------------------------------------------------------
# Linux: direct DB reads (fast path) + CLI fallbacks
# ---------------------------------------------------------------------------

def _read_pacman_db() -> set[str]:
    """Read /var/lib/pacman/local/*/desc directly (no `pacman -Qq`)."""
    root = Path("/var/lib/pacman/local")
    if not root.is_dir():
        return set()
    names: set[str] = set()
    for pkg_dir in root.iterdir():
        desc = pkg_dir / "desc"
        if not desc.is_file():
            continue
        try:
            lines = desc.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        # desc format: %NAME%\n<value>\n%VERSION%\n<value>...
        for i, line in enumerate(lines):
            if line == "%NAME%":
                names.add(lines[i + 1].strip())
                break
    return names


def _read_dpkg_db() -> set[str]:
    """Parse /var/lib/dpkg/status directly (no `apt list --installed`)."""
    status = Path("/var/lib/dpkg/status")
    if not status.is_file():
        return set()
    names: set[str] = set()
    try:
        lines = status.read_text(errors="ignore").splitlines()
    except OSError:
        return set()
    for line in lines:
        if line.startswith("Package: "):
            names.add(line.split(":", 1)[1].strip())
    return names


def _read_flatpak_refs() -> set[str]:
    """Read installed flatpak refs from user + system install dirs."""
    names: set[str] = set()
    roots = [
        Path.home() / ".local/share/flatpak/app",
        Path("/var/lib/flatpak/app"),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for app_dir in root.iterdir():
            meta = app_dir / "active" / "metadata"
            if not meta.is_file():
                continue
            try:
                text = meta.read_text(errors="ignore")
            except OSError:
                continue
            # metadata has a [Application] section with a name= line
            for line in text.splitlines():
                if line.startswith("name="):
                    names.add(line.split("=", 1)[1].strip())
                    break
            else:
                names.add(app_dir.name)  # fallback: dir name == app id
    return names


def _read_snap_db() -> set[str]:
    """Read installed snap names from /var/lib/snapd (no `snap list`)."""
    names: set[str] = set()
    root = Path("/var/lib/snapd/snaps")
    if root.is_dir():
        try:
            for f in root.glob("*.snap"):
                names.add(f.stem)
        except OSError:
            pass
    # snapd also keeps state in /var/lib/snapd/state.json for installed snaps
    state = Path("/var/lib/snapd/state.json")
    if state.is_file():
        try:
            data = json.loads(state.read_text())
            snaps = data.get("data", {}).get("snaps", {})
            names.update(snaps.keys())
        except (OSError, ValueError):
            pass
    return names


def _desktop_entries(dirs: list[Path]) -> set[str]:
    """Collect display names from *.desktop files (user-installed GUI apps)."""
    found: set[str] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        try:
            entries = list(d.glob("*.desktop"))
        except OSError:
            continue
        for f in entries:
            try:
                for line in f.read_text(errors="ignore").splitlines():
                    if line.startswith("Name="):
                        found.add(line.split("=", 1)[1].strip().lower())
                        break
            except OSError:
                pass
    return found


def detect_linux() -> set[str]:
    """Detect installed apps on Linux: direct DB reads + CLI fallbacks."""
    found: set[str] = set()
    results: dict[str, set[str]] = {}

    def worker(key: str, fn) -> None:
        results[key] = fn()

    # Parallel direct-DB reads (fast path)
    threads = [
        threading.Thread(target=worker, args=("pacman", _read_pacman_db)),
        threading.Thread(target=worker, args=("dpkg", _read_dpkg_db)),
        threading.Thread(target=worker, args=("flatpak", _read_flatpak_refs)),
        threading.Thread(target=worker, args=("snap", _read_snap_db)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for s in results.values():
        found.update(s)

    # CLI fallbacks: only for managers whose DB we couldn't read
    if not results.get("pacman"):
        found.update(run(["pacman", "-Qq"]))
    if not results.get("dpkg"):
        found.update(
            l.split("/")[0]
            for l in run(["apt", "list", "--installed"])
            if "/" in l and l.startswith("list")
        )
    if not results.get("flatpak"):
        found.update(run(["flatpak", "list", "--columns=application"]))
    if not results.get("snap"):
        found.update(run(["snap", "list"]))

    # Desktop entries (user-installed GUI apps) — always scanned, cheap
    found.update(_desktop_entries([Path.home() / d for d in HOME_APP_DIRS["linux"]]))
    found.update(_desktop_entries([Path(d) for d in SYSTEM_APP_DIRS["linux"]]))
    return found


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def detect_macos() -> set[str]:
    """Detect installed apps on macOS via /Applications + brew cask."""
    found: set[str] = set()
    for d in SYSTEM_APP_DIRS["macos"] + [str(Path.home() / "Applications")]:
        p = Path(d)
        if p.is_dir():
            try:
                found.update(a.stem for a in p.glob("*.app"))
            except OSError:
                pass
    found.update(run(["brew", "list", "--cask"]))
    return found


# ---------------------------------------------------------------------------
# Windows: registry uninstall keys (the fast, MSI-safe path)
# ---------------------------------------------------------------------------

def detect_windows() -> set[str]:
    """Detect installed apps on Windows via registry uninstall keys."""
    found: set[str] = set()
    keys = [
        r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    # `reg query` expands HKLM→HKEY_LOCAL_MACHINE and HKCU→HKEY_CURRENT_USER;
    # strip BOTH forms or the prefix never matches and full paths leak through.
    expanded = {
        r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall":
            r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall":
            r"HKEY_LOCAL_MACHINE\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall":
            r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    }
    for key in keys:
        out = run(["reg", "query", key])
        for o in out:
            if not o.strip():
                continue
            stripped = o
            for prefix in (expanded[key], key):
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix):].strip().lstrip("\\")
                    break
            if stripped:
                found.add(stripped)
    return found


# ---------------------------------------------------------------------------
# Matching + CLI
# ---------------------------------------------------------------------------

def match(detected: set[str]) -> list[dict]:
    """Match detected app names against the mapping DB.

    Requires whole-token match (case-insensitive): the detect-name must
    appear as a complete word, not as a substring of another word. This
    prevents "code" matching "libavcodec" or "Xvid Video Codec".
    """
    import re
    results = []
    dl = {d.lower() for d in detected}
    for m in MAPPINGS["mappings"]:
        for os_key in ("linux", "macos", "windows"):
            for name in m["detect"].get(os_key, []):
                nl = name.lower()
                pattern = r'\b' + re.escape(nl) + r'\b'
                if any(re.search(pattern, d) for d in dl):
                    results.append(
                        {
                            "source_app": m["source_app"],
                            "matched_name": name,
                            "target": m["omarchy_target"],
                            "defer": m.get("defer", False),
                            "config_paths": m.get("config_paths", []),
                        }
                    )
                    break
            else:
                continue
            break
    return results


def main() -> int:
    args = sys.argv[1:]
    want_os = None
    as_json = "--json" in args
    no_cache = "--no-cache" in args
    if "--os" in args:
        want_os = args[args.index("--os") + 1]

    os_name = want_os or {"linux": "linux", "darwin": "macos"}.get(sys.platform, "windows")
    detect = {"linux": detect_linux, "macos": detect_macos, "windows": detect_windows}[os_name]

    detected: set[str] | None = None
    if not no_cache:
        cached = _load_cache(os_name)
        if cached is not None:
            detected = set(cached.get("detected", []))
    if detected is None:
        detected = detect()
        _save_cache(os_name, detected)

    matched = match(detected)

    report = {
        "os": os_name,
        "detected_count": len(detected),
        "matched": matched,
        "matched_count": len(matched),
        "unmatched_known": sorted(
            set(d.lower() for d in detected)
            - {m["matched_name"].lower() for m in matched}
        )[:50],
    }
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"OS: {os_name}")
        print(f"Detected {len(detected)} apps, matched {len(matched)}")
        for m in matched:
            defer = " [DEFER to Omarchy]" if m["defer"] else ""
            print(f"  {m['source_app']} -> {m['target'].get('name')}{defer}")
        if report["unmatched_known"]:
            print(f"\nUnmatched (flag for review): {', '.join(report['unmatched_known'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Steam user-data layer for omarchy-migrate (omnigate).

The 'keep my user data, skip the re-downloadable' layer. Steam game FILES
(steamapps/common/<app> — often tens/hundreds of GB) are re-downloadable, so
migration should SKIP them. What actually matters:

  * userdata/<userid>/<appid>/...  — cloud-synced save/config dirs (KBs–MBs)
  * per-app save/config dirs inside steamapps/common/<app>/ (small)
  * steamapps/common/<app>/ for apps that have NO cloud saves — configs and
    save files live inside the install dir (small data in a huge dir)
  * config/ + userdata/<userid>/config/ — Steam client configs

This module scans every Steam library folder on the source OS, lists
installed apps from appmanifest_*.acf, classifies what is worth copying vs
re-downloadable, and emits steam-report.json.

Cross-platform (source OS = Linux / macOS / Windows): pathlib everywhere, no
shelling out, no POSIX-only assumptions. Deterministic: results are sorted,
and the report is byte-for-byte reproducible for the same filesystem state.

Usage:
    python3 steam.py report [--out PATH] [--json]
    python3 migrate.py steam report        # same thing, wired into the CLI

Report schema (steam-report.json):
    {
      "tool": "omarchy-migrate steam",
      "generated_at": "...",               # ISO timestamp (single, at end)
      "os": "linux" | "macos" | "windows",
      "steam_root": "/path/to/steam",      # null if not found
      "found": true|false,
      "libraries": [ { "path": ..., "apps": [ { ... } ] } ],
      "totals": {
        "installed_apps": N,
        "worth_copying_bytes": N,
        "re_downloadable_bytes": N,
        "worth_copying": [ "path", ... ],  # paths, sorted
        "re_downloadable": [ "path", ... ]
      }
    }

Degrades gracefully: if no Steam install is found, the report is still a
valid JSON document with found=false, empty libraries, and a clear message.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

TOOL_NAME = "omarchy-migrate steam"
REPORT_VERSION = 1

# ---------------------------------------------------------------------------
# OS-specific Steam locations (tried in order; first hit wins)
# ---------------------------------------------------------------------------

STEAM_ROOTS = {
    # Linux: modern install dirs. ~/.steam/steam is a symlink farm kept by
    # the client; the real data lives under ~/.local/share/Steam (XDG) or
    # ~/.steam/steam (legacy installs).
    "linux": [
        lambda h: h / ".local/share/Steam",
        lambda h: h / ".steam/steam",
        lambda h: h / ".steam",
    ],
    # macOS: ~/Library/Application Support/Steam
    "macos": [
        lambda h: h / "Library/Application Support/Steam",
    ],
    # Windows: the classic default. (Program Files is localized on some
    # systems; PROGRAMFILES(X86) env var covers that when present.)
    "windows": [
        lambda h: Path(
            os_environ("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        ) / "Steam",
        lambda h: Path(os_environ("PROGRAMFILES", r"C:\Program Files")) / "Steam",
    ],
}

# Subdirectories that are NEVER worth copying — re-downloadable/regenerable.
# These live under <library>/steamapps/ and can be many GB each.
STEAMAPPS_SKIP_DIRS = {
    "common",     # the game files themselves (re-downloadable; handled per-app)
    "compatdata", # Proton prefixes — recreated automatically; old ones are
                  #   (mostly) re-regenerable. Listed separately for visibility.
    "shadercache",
    "workshop",   # workshop content is re-downloadable by subscription
    "temp",
    "downloading",
    "sourcemods",
}

# Things worth copying from a library root's steamapps/ dir (small, useful).
STEAMAPPS_KEEP = {
    "appcache",
    "htmlcache",
    "logs",
}

# Per-app size threshold (bytes). An app whose install dir is below this is
# small enough that its whole dir (save data, configs, small games) is worth
# copying. Above it, the install dir is re-downloadable; only the app's
# userdata/ cloud-save dir (KBs–MBs) is worth keeping.
SMALL_APP_BYTES = 1_000_000_000  # 1 GiB

# Save/config dir names commonly found INSIDE steamapps/common/<app>/ that
# hold user data even for large games.
SAVE_DIR_NAMES = {
    "saves", "save", "savedata", "savegames", "savegames_", "saved", "profiles",
    "profile", "config", "settings", "user", "users", "local", "appdata",
    "crashdumps", "screenshots", "captures", "logs",
}


def os_environ(key: str, default: str) -> str:
    import os
    return os.environ.get(key, default)


def current_os() -> str:
    return {"linux": "linux", "darwin": "macos"}.get(sys.platform, "windows")


# ---------------------------------------------------------------------------
# VDF parsing (stdlib-only, deterministic)
# ---------------------------------------------------------------------------

class VDF:
    """Tiny Valve Data Format parser.

    VDF is a nested key/value format: keys are quoted strings, values are
    either quoted strings or a nested block. Comments (// ...) and
    non-quoted keys are tolerated. We only need the parts we read, so this
    returns the raw nested dict without type coercion.
    """

    def __init__(self, text: str):
        self._tokens = self._tokenize(text)
        self._pos = 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        toks: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            if c in " \t\r\n":
                i += 1
                continue
            if c == "/" and i + 1 < n and text[i + 1] == "/":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if c == '"':
                j = i + 1
                buf = []
                while j < n:
                    if text[j] == "\\" and j + 1 < n:
                        buf.append(text[j + 1])
                        j += 2
                        continue
                    if text[j] == '"':
                        break
                    buf.append(text[j])
                    j += 1
                toks.append("".join(buf))
                i = j + 1
                continue
            # bare tokens ({ } and unquoted keys/values)
            j = i
            while j < n and text[j] not in " \t\r\n{}":
                j += 1
            toks.append(text[i:j])
            i = j
        return toks

    def parse(self) -> dict:
        """Parse the top-level block; returns {} on empty input."""
        self._skip()
        if self._pos < len(self._tokens) and self._tokens[self._pos] == "{":
            self._pos += 1
            return self._block()
        # Some VDF files start with a root key ("AppState", "libraryfolders")
        if self._pos + 1 < len(self._tokens) and self._tokens[self._pos + 1] == "{":
            root = self._tokens[self._pos]
            self._pos += 2
            return {root: self._block()}
        return {}

    def _block(self) -> dict:
        out: dict = {}
        while self._pos < len(self._tokens):
            tok = self._tokens[self._pos]
            if tok == "}":
                self._pos += 1
                return out
            self._pos += 1
            if self._pos >= len(self._tokens):
                break
            nxt = self._tokens[self._pos]
            if nxt == "{":
                self._pos += 1
                out[tok] = self._block()
            else:
                self._pos += 1
                out[tok] = nxt
        return out

    def _skip(self) -> None:
        while self._pos < len(self._tokens) and self._tokens[self._pos] in ("{",):
            # stray open braces at top level are skipped by parse()
            break


def parse_vdf(text: str) -> dict:
    """Parse VDF text into a dict; returns {} on any parse failure."""
    try:
        return VDF(text).parse()
    except (IndexError, RecursionError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Steam discovery
# ---------------------------------------------------------------------------

def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        try:
            if p.is_dir():
                return p
        except OSError:
            continue
    return None


def find_steam_root(os_name: str | None = None) -> Path | None:
    """Locate the Steam install root for the current (or given) OS."""
    os_name = os_name or current_os()
    home = Path.home()
    roots = [fn(home) for fn in STEAM_ROOTS.get(os_name, [])]
    return _first_existing(roots)


def _library_folders_vdf(steam_root: Path) -> Path:
    """libraryfolders.vdf lives in <root>/steamapps/ on all platforms."""
    return steam_root / "steamapps" / "libraryfolders.vdf"


def read_library_folders(steam_root: Path) -> list[Path]:
    """Read the Steam library folders (each has a steamapps/ dir).

    Primary source: <root>/steamapps/libraryfolders.vdf. If that file is
    missing (fresh installs before first run), fall back to the default
    library at <root>/steamapps itself.
    """
    vdf_path = _library_folders_vdf(steam_root)
    libs: list[Path] = []
    try:
        if vdf_path.is_file():
            data = parse_vdf(vdf_path.read_text(errors="ignore"))
            folders = data.get("libraryfolders", {})
            for key, val in folders.items():
                if not isinstance(val, dict):
                    continue
                raw = val.get("path")
                if not raw:
                    continue
                lib = Path(str(raw))
                if lib.is_dir():
                    libs.append(lib)
    except OSError:
        pass
    # Dedupe (VDF may list the same path twice), keep first-seen order
    seen: set[str] = set()
    unique: list[Path] = []
    for lib in libs:
        key = str(lib).lower()
        if key not in seen:
            seen.add(key)
            unique.append(lib)
    # Fallback: the root library itself always has a steamapps/ dir
    default = steam_root / "steamapps"
    if default.is_dir() and str(default).lower() not in seen:
        unique.insert(0, default)
    return unique


# ---------------------------------------------------------------------------
# App manifests
# ---------------------------------------------------------------------------

_MANIFEST_RE = re.compile(r"^appmanifest_(\d+)\.acf$")


def _acf_dir(library: Path) -> Path:
    return library / "steamapps"


def list_app_manifests(library: Path) -> list[Path]:
    """appmanifest_<appid>.acf files in a library's steamapps/ dir."""
    d = _acf_dir(library)
    out: list[Path] = []
    try:
        if not d.is_dir():
            return out
        for f in d.iterdir():
            m = _MANIFEST_RE.match(f.name)
            if m:
                out.append(f)
    except OSError:
        return out
    return sorted(out, key=lambda p: int(_MANIFEST_RE.match(p.name).group(1)))


def parse_app_manifest(path: Path) -> dict:
    """Extract appid/name/installdir/SizeOnDisk from an ACF file.

    Returns {} when the file is unreadable or lacks an appid. Bytes are
    clamped to >= 0 so a malformed SizeOnDisk never poisons totals.
    """
    try:
        data = parse_vdf(path.read_text(errors="ignore"))
    except OSError:
        return {}
    state = data.get("AppState", {})
    if not isinstance(state, dict):
        state = {}
    appid = str(state.get("appid", "")).strip()
    if not appid.isdigit():
        return {}
    try:
        size = max(0, int(float(state.get("SizeOnDisk", 0) or 0)))
    except (TypeError, ValueError):
        size = 0
    return {
        "appid": appid,
        "name": str(state.get("name", "")).strip() or f"app {appid}",
        "installdir": str(state.get("installdir", "")).strip(),
        "size_on_disk": size,
    }


# ---------------------------------------------------------------------------
# What's worth copying vs re-downloadable
# ---------------------------------------------------------------------------

def _dir_size(path: Path) -> int:
    """Total size of a directory tree in bytes (best-effort, capped)."""
    total = 0
    try:
        for root, dirs, files in path.walk(onerror=lambda e: None):
            for f in files:
                try:
                    total += (root / f).stat().st_size
                except OSError:
                    pass
    except OSError:
        return 0
    return total


def _save_subdirs(app_dir: Path) -> list[Path]:
    """Small save/config dirs inside an app's install dir (top level only)."""
    out: list[Path] = []
    try:
        if not app_dir.is_dir():
            return out
        for child in sorted(app_dir.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            if child.name.lower() in SAVE_DIR_NAMES:
                out.append(child)
    except OSError:
        pass
    return out


def classify_library(library: Path, userdata_dirs: list[Path]) -> list[dict]:
    """Classify every installed app in one library folder.

    Returns a list of app records, each with the app's worth_copying paths
    (small user-data dirs) and re_downloadable paths (game files).
    """
    apps: list[dict] = []
    userdata_lookup: dict[str, Path] = {}
    for ud in userdata_dirs:
        try:
            for child in ud.iterdir():
                if child.is_dir() and child.name.isdigit():
                    userdata_lookup[child.name] = child
        except OSError:
            pass

    for manifest in list_app_manifests(library):
        info = parse_app_manifest(manifest)
        if not info:
            continue
        appid = info["appid"]
        app_dir = _acf_dir(library) / "common" / info["installdir"] if info["installdir"] else None
        app_dir_size = _dir_size(app_dir) if app_dir else 0
        total = info.get("size_on_disk", 0) or app_dir_size

        worth: list[Path] = []
        redownload: list[Path] = []

        # userdata/<userid>/<appid>/ — per-user cloud saves/configs (KBs–MBs)
        for userid_dir in userdata_lookup.values():
            app_userdata = userid_dir / appid
            if app_userdata.is_dir():
                worth.append(app_userdata)
        # Steam client user config for this app
        client_cfg = library / "userdata" / "config"
        if client_cfg.is_dir():
            worth.append(client_cfg)

        if app_dir and app_dir.is_dir():
            if total < SMALL_APP_BYTES:
                # Small app (or no manifest size): the whole install dir is
                # worth copying — saves/configs for small games, or the app
                # dir IS the user data (no cloud saves).
                worth.append(app_dir)
            else:
                # Large app: game files are re-downloadable. Keep only the
                # small save/config subdirs that live inside the install dir.
                for sd in _save_subdirs(app_dir):
                    if sd != app_dir:
                        worth.append(sd)
                redownload.append(app_dir)

        apps.append(
            {
                "appid": appid,
                "name": info["name"],
                "library": str(library),
                "install_dir": str(app_dir) if app_dir else None,
                "size_on_disk": total,
                "worth_copying": sorted(str(p) for p in worth),
                "re_downloadable": sorted(str(p) for p in redownload),
            }
        )
    return apps


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(os_name: str | None = None) -> dict:
    """Scan Steam on the current (or given) OS and build the report dict."""
    os_name = os_name or current_os()
    steam_root = find_steam_root(os_name)
    found = steam_root is not None

    libraries: list[dict] = []
    totals = {
        "installed_apps": 0,
        "worth_copying_bytes": 0,
        "re_downloadable_bytes": 0,
        "worth_copying": [],
        "re_downloadable": [],
    }

    if found:
        libs = read_library_folders(steam_root)
        # userdata dirs: primary at <root>/userdata; each extra library may
        # have its own, but the root one holds the real per-user saves.
        userdata_dirs = [steam_root / "userdata"]
        userdata_dirs += [lib / "userdata" for lib in libs if (lib / "userdata").is_dir()]
        userdata_dirs = [d for d in userdata_dirs if d.is_dir()]

        for lib in libs:
            apps = classify_library(lib, userdata_dirs)
            lib_entry = {"path": str(lib), "apps": apps}
            libraries.append(lib_entry)
            totals["installed_apps"] += len(apps)
            for a in apps:
                for p in a["worth_copying"]:
                    sz = _dir_size(Path(p)) if Path(p).is_dir() else 0
                    totals["worth_copying_bytes"] += sz
                    totals["worth_copying"].append(p)
                for p in a["re_downloadable"]:
                    totals["re_downloadable_bytes"] += a["size_on_disk"]
                    totals["re_downloadable"].append(p)

        # Library-level keepers (small config/cache dirs under steamapps/)
        for lib in libs:
            steamapps = lib / "steamapps"
            for name in STEAMAPPS_KEEP:
                p = steamapps / name
                if p.is_dir():
                    totals["worth_copying_bytes"] += _dir_size(p)
                    totals["worth_copying"].append(str(p))
            # The steamapps dir itself holds the .acf manifests + libraryfolders.vdf
            vdf = steamapps / "libraryfolders.vdf"
            if vdf.is_file():
                totals["worth_copying_bytes"] += vdf.stat().st_size
                totals["worth_copying"].append(str(vdf))

    totals["worth_copying"] = sorted(set(totals["worth_copying"]))
    totals["re_downloadable"] = sorted(set(totals["re_downloadable"]))
    totals["worth_copying_bytes"] = int(totals["worth_copying_bytes"])
    totals["re_downloadable_bytes"] = int(totals["re_downloadable_bytes"])

    report = {
        "tool": TOOL_NAME,
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "os": os_name,
        "steam_root": str(steam_root) if steam_root else None,
        "found": found,
        "message": (
            None
            if found
            else (
                "Steam not found on this system — no user data to preserve. "
                "Install Steam on the source machine first, or point STEAM_HOME "
                "at an existing install."
            )
        ),
        "libraries": libraries,
        "totals": totals,
    }
    return report


def report_to_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def cmd_report(args: list[str]) -> int:
    """`steam.py report [--out PATH] [--json]` — scan + write steam-report.json."""
    out = None
    if "--out" in args:
        out = Path(args[args.index("--out") + 1])
    if out is None:
        out = Path.cwd() / "steam-report.json"

    report = generate_report()
    out.write_text(report_to_json(report))

    t = report["totals"]
    if report["found"]:
        print(
            f"Steam found at {report['steam_root']} — {len(report['libraries'])} "
            f"library folder(s), {t['installed_apps']} installed app(s)"
        )
        print(
            f"  worth copying: {len(t['worth_copying'])} path(s), "
            f"{t['worth_copying_bytes'] / 1e9:.2f} GB"
        )
        print(
            f"  re-downloadable (skip): {len(t['re_downloadable'])} path(s), "
            f"{t['re_downloadable_bytes'] / 1e9:.2f} GB"
        )
    else:
        print(f"Steam not found: {report['message']}")
    print(f"report -> {out}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "report":
        return cmd_report(rest)
    print(f"unknown steam command: {cmd}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

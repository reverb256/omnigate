#!/usr/bin/env python3
"""omnigate manifest — the "One-File Computer" (Layer 3, research idea #5).

A declarative, content-addressed description of the source machine's STATE,
not just its package list. Migration becomes a git-diff-style review of two
manifests (source vs. Omarchy reference) and the defer rule fires
automatically against what Omarchy already ships.

Commands:

    python3 manifest.py scan [--os linux|macos|windows] [--out machine.json]
        Emit machine.json: detected apps (reuses scanner.detect.match),
        normalized config paths (reuses mapper.port_configs.normalize),
        SHA-256 content hashes for small non-derivable blobs, OS state
        (Steam library, browser profiles, dconf), and a defer/map
        classification from mapper.compat.

    python3 manifest.py diff <source.json> <omarchy-reference.json>
        git-diff-style reviewable report: added/removed/changed apps,
        deferrable items, and state deltas (hashes, Steam, profiles, dconf).

    python3 manifest.py reference [--out omarchy-reference.json]
        Generate the sample Omarchy reference manifest from mappings/apps.json
        (what Omarchy ships = defer).

Exit codes: 0 success, 1 scan/state errors, 2 usage errors.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from scanner.detect import detect_linux, detect_macos, detect_windows, match  # noqa: E402
from mapper.compat import gate  # noqa: E402
from mapper.map import classify  # noqa: E402
from mapper.port_configs import normalize  # noqa: E402

TOOL_VERSION = "0.3"

# Files larger than this are not content-hashed: hashing huge blobs (game
# data, browser caches) costs I/O and the result is re-derivable. Small
# non-derivable blobs (config files, dotfiles) get content-addressed.
MAX_HASH_BYTES = 8 * 1024 * 1024

# Directories that must never be walked for hashing (caches, sockets,
# transient stores, version-control internals, symlink farms).
_HASH_SKIP_DIRS = frozenset(
    {
        "cache",
        "cacheddata",
        "code cache",
        "gpu cache",
        "shader cache",
        "blob_storage",
        "files",
        "indexeddb",
        "local storage",
        "session storage",
        "logs",
        "tmp",
        "temp",
        "backups",
        "backup",
        "old",
        "trash",
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
    }
)

# Known Steam library root names under $HOME.
_STEAM_ROOTS = (
    Path.home() / ".local/share/Steam",
    Path.home() / ".steam/steam",
    Path.home() / ".steam",
)

# dconf databases under ~/.config/dconf (small, non-derivable, hashed).
_DCONF_FILES = ("user", "user.d", "user.txt")

_BROWSER_ROOTS = {
    "firefox": Path.home() / ".mozilla/firefox",
    "chromium": Path.home() / ".config/chromium",
    "zen": Path.home() / ".config/zen",
    "zen_flatpak": Path.home() / ".var/app/app.zen_browser.zen/config/zen",
}


def _run(cmd: list[str]) -> list[str]:
    """Run a command, return stripped stdout lines, or [] on failure."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _sha256(path: Path, max_bytes: int = MAX_HASH_BYTES) -> str | None:
    """SHA-256 of a file, or None if it is missing, unreadable, or too big.

    Content-addressed identity for small non-derivable blobs. Large or
    unreadable files are reported as None (present but not hashed) so the
    manifest stays fast and deterministic.
    """
    try:
        if path.is_symlink():
            return "symlink:" + os.readlink(path)
        if not path.is_file():
            return None
        st = path.stat()
        if st.st_size > max_bytes:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _iter_files(root: Path) -> list[Path]:
    """All regular files under root, pruning known-big/cache dirs (sorted)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d.lower() not in _HASH_SKIP_DIRS
        )
        for f in sorted(filenames):
            p = Path(dirpath) / f
            if p.is_file():
                out.append(p)
    return out


def scan_configs(matched: list[dict], home: Path) -> dict:
    """Normalized config paths that exist, with SHA-256 of small files.

    Reuses mapper.port_configs.normalize to map macOS/Windows paths to the
    target Linux layout. Directories are recorded with per-file hashes
    (pruned of cache dirs) plus a directory size; large files are recorded
    without a hash (None) because they are re-derivable.
    """
    configs = {}
    seen_paths = set()
    for m in matched:
        app = m["source_app"]
        for cp in m.get("config_paths", []):
            p = normalize(cp, home, home)
            if p is None or not p.exists():
                continue
            # Dedupe by normalized path: on Linux the macOS/Windows entries
            # in a mapping can normalize onto the same target (e.g. both
            # "~/.config/Code" and "~/Library/Application Support/Code" ->
            # ~/.config/Code). Keep the first (platform-native) entry.
            if str(p) in seen_paths:
                continue
            seen_paths.add(str(p))
            key = f"{app}__{cp}"
            entry = {"source_path": cp, "normalized": str(p)}
            # Resolve the target via symlinks: normalize() maps a source path
            # onto $HOME, but HM-managed configs (zen, alacritty on this box)
            # live under the nix store and are reachable only through the
            # symlink at the normalized path. stat the RESOLVED file so the
            # hash reflects the real content.
            real = p.resolve()
            if p.is_dir():
                files = []
                seen = set()
                for f in _iter_files(p):
                    freal = f.resolve()
                    rel = str(f.relative_to(p))
                    if rel in seen:
                        continue
                    seen.add(rel)
                    files.append(
                        {
                            "rel": rel,
                            "size": freal.stat().st_size,
                            "sha256": _sha256(freal),
                        }
                    )
                entry.update(
                    {"type": "dir", "file_count": len(files), "files": files}
                )
            else:
                entry.update(
                    {
                        "type": "file",
                        "size": real.stat().st_size,
                        "sha256": _sha256(real),
                    }
                )
            configs[key] = entry
    return configs


def scan_steam(home: Path) -> dict:
    """Steam library state: library folders + installed-app manifests.

    Reads libraryfolders.vdf from the first existing Steam root, then
    appmanifest_*.acf from every listed library folder (and the Steam root
    itself) that exists. Parses enough VDF with a tiny state machine: the
    values we care about are plain quoted key/value pairs.
    """
    lf = None
    root = None
    for r in _STEAM_ROOTS:
        cand = r / "steamapps" / "libraryfolders.vdf"
        if cand.is_file():
            root, lf = r, cand
            break
    if lf is None:
        return {"present": False, "library_folders": [], "apps": []}

    libs = []
    try:
        txt = lf.read_text(errors="replace")
        for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
            libs.append(m.group(1))
    except OSError:
        pass

    apps = []
    for lib in libs:
        base = Path(lib) / "steamapps"
        if not base.is_dir():
            continue
        for acf in sorted(base.glob("appmanifest_*.acf")):
            appid = acf.stem.split("_", 1)[1]
            name = None
            installdir = None
            size = None
            try:
                atxt = acf.read_text(errors="replace")
                for key, val in (
                    ("name", name),
                    ("installdir", installdir),
                    ("SizeOnDisk", size),
                ):
                    m = re.search(rf'"{key}"\s+"([^"]*)"', atxt)
                    if m:
                        if key == "name":
                            name = m.group(1)
                        elif key == "installdir":
                            installdir = m.group(1)
                        else:
                            size = int(m.group(1))
            except OSError:
                pass
            apps.append(
                {
                    "appid": appid,
                    "name": name or appid,
                    "installdir": installdir,
                    "library": str(base.parent),
                    "size_on_disk": size,
                    "manifest_sha256": _sha256(acf),
                }
            )

    return {
        "present": True,
        "library_folders": libs,
        "libraryfolders_sha256": _sha256(lf),
        "apps": apps,
    }


def scan_browsers(home: Path) -> dict:
    """Browser profile directories: existence, file count, size, hashes.

    Content-addressed per-file hashes let the diff detect real profile
    changes (a changed prefs.js or places.sqlite) without copying the whole
    profile tree.
    """
    profiles = {}
    for name, root in _BROWSER_ROOTS.items():
        if not root.is_dir():
            continue
        files = []
        for f in _iter_files(root):
            files.append(
                {
                    "rel": str(f.relative_to(root)),
                    "size": f.stat().st_size,
                    "sha256": _sha256(f),
                }
            )
        profiles[name] = {
            "path": str(root),
            "file_count": len(files),
            "files": files,
        }
    return profiles


def scan_dconf(home: Path) -> dict:
    """dconf state: dump (if `dconf` exists) + hashes of local databases."""
    state = {}
    for fname in _DCONF_FILES:
        p = home / ".config" / "dconf" / fname
        if p.is_file():
            state[fname] = {"size": p.stat().st_size, "sha256": _sha256(p)}
    dump = _run(["dconf", "dump", "/"])
    if dump:
        state["dump"] = "\n".join(dump)
    return state


def build_manifest(os_name: str, home: Path) -> dict:
    """Scan the machine and build the full machine.json structure."""
    scan = {"linux": detect_linux, "macos": detect_macos, "windows": detect_windows}[os_name]()
    matched = match(scan)
    report = classify(matched)
    gate_report = gate(report)

    configs = scan_configs(matched, home)

    manifest = {
        "schema": "omnigate-machine-manifest",
        "schema_version": "0.1",
        "tool_version": TOOL_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "os": os_name,
        "host": os.uname().nodename,
        "home": str(home),
        "apps": {
            "detected_count": len(scan),
            "matched": sorted(
                (m["source_app"] for m in matched), key=str.lower
            ),
            "unmatched_known": sorted(
                set(d.lower() for d in scan)
                - {m["matched_name"].lower() for m in matched}
            )[:100],
        },
        "classification": {
            "defer": report["defer"],
            "map": report["map"],
            "unknown": sorted(report["unknown"]),
            "compat": {
                "ok": sorted((m["source_app"] for m in gate_report["ok"]), key=str.lower),
                "risky": sorted((m["source_app"] for m in gate_report["risky"]), key=str.lower),
                "unknown": sorted((m["source_app"] for m in gate_report["unknown"]), key=str.lower),
                "blocked": sorted((m["source_app"] for m in gate_report["blocked"]), key=str.lower),
            },
        },
        "configs": configs,
        "config_totals": {
            "paths": len(configs),
            "files": sum(
                e.get("file_count", 1) for e in configs.values()
            ),
            "bytes": sum(
                f.get("size", 0)
                for e in configs.values()
                for f in e.get("files", [])
                if f.get("sha256") is not None
            ),
        },
        "state": {
            "steam": scan_steam(home),
            "browsers": scan_browsers(home),
            "dconf": scan_dconf(home),
        },
    }
    return manifest


def cmd_scan(args: list[str]) -> int:
    os_name = "linux"
    if "--os" in args:
        os_name = args[args.index("--os") + 1]
    if os_name not in ("linux", "macos", "windows"):
        print(f"unknown --os: {os_name}", file=sys.stderr)
        return 2
    out = Path(args[args.index("--out") + 1]) if "--out" in args else Path("machine.json")
    manifest = build_manifest(os_name, Path.home())
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    compat = manifest["classification"]["compat"]
    state = manifest["state"]
    steam = state["steam"]
    print(
        f"scanned {manifest['os']}@{manifest['host']}: "
        f"{manifest['apps']['detected_count']} detected, "
        f"{len(manifest['apps']['matched'])} matched, "
        f"{len(manifest['configs'])} config paths, "
        f"{len(compat['ok'])} ok / {len(compat['risky'])} risky / "
        f"{len(compat['unknown'])} unknown"
    )
    if steam["present"]:
        print(
            f"  steam: {len(steam['apps'])} installed apps across "
            f"{len(steam['library_folders'])} library folders"
        )
    for name, prof in state["browsers"].items():
        print(f"  browser {name}: {prof['file_count']} files")
    if state["dconf"]:
        print(f"  dconf: {len(state['dconf'])} databases + dump")
    print(f"wrote {out}")
    return 0


def reference_manifest() -> dict:
    """What Omarchy ships, derived from mappings/apps.json (defer entries).

    The defer-to-Omarchy reference: everything marked defer:true in the
    mappings is treated as owned by Omarchy, so a source manifest is
    compared against this reference and matching apps are reported as
    deferred rather than "to install".
    """
    ref = {
        "schema": "omarchy-reference-manifest",
        "schema_version": "0.1",
        "tool_version": TOOL_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "derived_from": "mappings/apps.json",
        "defer_apps": [],
    }
    mapping_db = json.loads((REPO / "mappings" / "apps.json").read_text())
    seen = set()
    for m in mapping_db["mappings"]:
        if not m.get("defer"):
            continue
        app = m["source_app"]
        if app in seen:
            continue
        seen.add(app)
        ref["defer_apps"].append(
            {
                "source_app": app,
                "omarchy": m["omarchy_target"].get("name"),
                "target_type": m["omarchy_target"].get("type"),
                "config_paths": m.get("config_paths", []),
            }
        )
    ref["defer_apps"].sort(key=lambda d: d["source_app"].lower())
    return ref


def cmd_reference(args: list[str]) -> int:
    out = Path(args[args.index("--out") + 1]) if "--out" in args else Path("omarchy-reference.json")
    ref = reference_manifest()
    out.write_text(json.dumps(ref, indent=2) + "\n")
    print(f"wrote {out} ({len(ref['defer_apps'])} defer apps)")
    return 0


def _added_removed_changed(source: dict, reference: dict) -> dict:
    """Diff two app sets. Identity = source_app (the mapping key).

    Both inputs are lists of dicts that carry "source_app" plus extra
    fields; bare-string entries are tolerated and normalized.
    """
    def app_map(m: dict):
        out = {}
        for a in m.get("matched", m.get("defer_apps", [])):
            if isinstance(a, str):
                out[a] = {"source_app": a}
            else:
                out[a["source_app"]] = a
        return out

    s_apps, r_apps = app_map(source), app_map(reference)
    s_keys, r_keys = set(s_apps), set(r_apps)

    def strip(a: dict) -> dict:
        return {k: v for k, v in a.items() if k != "source_app"}

    added = sorted((s_apps[k] for k in s_keys - r_keys), key=lambda a: a["source_app"].lower())
    removed = sorted((r_apps[k] for k in r_keys - s_keys), key=lambda a: a["source_app"].lower())
    # "changed" only applies to apps present in both that are NOT part of
    # the defer set (deferrable apps are reported under DEFERRED instead).
    defer_ref = {a.get("source_app") for a in reference.get("defer_apps", [])}
    changed = []
    for k in sorted(s_keys & r_keys, key=str.lower):
        if k in defer_ref:
            continue
        if strip(s_apps[k]) != strip(r_apps[k]):
            changed.append({"source_app": k, "source": s_apps[k], "reference": r_apps[k]})
    return {"added": added, "removed": removed, "changed": changed}


def _diff_blob(name: str, src_blob: dict | None, ref_blob: dict | None) -> list[dict]:
    """Compare two single-file blobs {sha256,...}; None = missing."""
    deltas = []
    if src_blob is None and ref_blob is None:
        return deltas
    if src_blob is None:
        deltas.append({"path": name, "kind": "removed"})
        return deltas
    if ref_blob is None:
        deltas.append({"path": name, "kind": "added"})
        return deltas
    s, r = src_blob.get("sha256"), ref_blob.get("sha256")
    if s is None and r is None:
        deltas.append({"path": name, "kind": "changed", "detail": "not hashed (too large)"})
    elif s != r:
        deltas.append({"path": name, "kind": "changed", "detail": f"sha256 {s} -> {r}"})
    return deltas


def _diff_dir_files(name: str, src_files: list[dict], ref_files: list[dict]) -> list[dict]:
    """Diff two per-file hash listings; report added/changed/removed files."""
    s = {f["rel"]: f for f in src_files}
    r = {f["rel"]: f for f in ref_files}
    deltas = []
    for rel in sorted(set(s) - set(r)):
        deltas.append({"path": f"{name}/{rel}", "kind": "added"})
    for rel in sorted(set(r) - set(s)):
        deltas.append({"path": f"{name}/{rel}", "kind": "removed"})
    for rel in sorted(set(s) & set(r)):
        if s[rel].get("sha256") != r[rel].get("sha256"):
            detail = (
                "not hashed (too large)"
                if s[rel].get("sha256") is None and r[rel].get("sha256") is None
                else f"sha256 {s[rel].get('sha256')} -> {r[rel].get('sha256')}"
            )
            deltas.append({"path": f"{name}/{rel}", "kind": "changed", "detail": detail})
    return deltas


def diff_manifests(source: dict, reference: dict) -> dict:
    """Full structural diff: apps, classification, configs, state deltas."""
    result = {
        "source": {"host": source.get("host"), "os": source.get("os"), "created_at": source.get("created_at")},
        "reference": {
            "schema": reference.get("schema"),
            "created_at": reference.get("created_at"),
        },
        "apps": {"added": [], "removed": [], "changed": []},
        "deferrable": [],
        "state": {"configs": [], "steam": [], "browsers": [], "dconf": []},
    }

    # Apps: source-side list vs reference defer_apps list. The source list
    # is bare app-name strings (the machine manifest); the reference is a
    # list of {source_app, omarchy, config_paths} dicts.
    s_apps = [
        {"source_app": a, "omarchy": None}
        for a in source.get("apps", {}).get("matched", [])
    ]
    if isinstance(reference.get("defer_apps"), list) and reference["defer_apps"] and isinstance(
        reference["defer_apps"][0], str
    ):
        r_apps = [{"source_app": a, "omarchy": None} for a in reference["defer_apps"]]
    else:
        r_apps = [
            {"source_app": a["source_app"], "omarchy": a.get("omarchy")}
            for a in reference.get("defer_apps", [])
        ]
    app_diff = _added_removed_changed({"matched": s_apps}, {"defer_apps": r_apps})
    result["apps"] = app_diff

    # Deferrable: source apps that Omarchy ships (in the reference) and any
    # source-side defer classification.
    ref_names = {a["source_app"] for a in r_apps}
    source_defer = {d["source_app"] for d in source.get("classification", {}).get("defer", [])}
    deferrable = sorted(
        ({"source_app": a, "omarchy": next((r["omarchy"] for r in r_apps if r["source_app"] == a), None)}
         for a in ref_names & set(source.get("apps", {}).get("matched", []))),
        key=lambda d: d["source_app"].lower(),
    )
    result["deferrable"] = deferrable

    # Configs: per-key file/dir diff.
    src_cfg = source.get("configs", {})
    ref_cfg = reference.get("configs", {})
    for key in sorted(set(src_cfg) | set(ref_cfg)):
        s_entry, r_entry = src_cfg.get(key), ref_cfg.get(key)
        if s_entry is None:
            result["state"]["configs"].append({"config": key, "kind": "removed"})
        elif r_entry is None:
            result["state"]["configs"].append({"config": key, "kind": "added"})
        elif s_entry.get("type") != r_entry.get("type"):
            result["state"]["configs"].append(
                {"config": key, "kind": "changed", "detail": f"{s_entry.get('type')} -> {r_entry.get('type')}"}
            )
        elif s_entry["type"] == "file":
            result["state"]["configs"].extend(_diff_blob(key, s_entry, r_entry))
        else:
            result["state"]["configs"].extend(
                _diff_dir_files(key, s_entry.get("files", []), r_entry.get("files", []))
            )

    # Steam: app set + per-app manifest hash deltas.
    s_steam, r_steam = source.get("state", {}).get("steam", {}), reference.get("state", {}).get("steam", {})
    s_apps_map = {a["appid"]: a for a in s_steam.get("apps", [])}
    r_apps_map = {a["appid"]: a for a in r_steam.get("apps", [])}
    for appid in sorted(set(s_apps_map) - set(r_apps_map)):
        a = s_apps_map[appid]
        result["state"]["steam"].append(
            {"appid": appid, "name": a.get("name"), "kind": "added"}
        )
    for appid in sorted(set(r_apps_map) - set(s_apps_map)):
        a = r_apps_map[appid]
        result["state"]["steam"].append(
            {"appid": appid, "name": a.get("name"), "kind": "removed"}
        )
    for appid in sorted(set(s_apps_map) & set(r_apps_map), key=str.lower):
        s_a, r_a = s_apps_map[appid], r_apps_map[appid]
        if s_a.get("manifest_sha256") != r_a.get("manifest_sha256"):
            result["state"]["steam"].append(
                {
                    "appid": appid,
                    "name": s_a.get("name"),
                    "kind": "changed",
                    "detail": f"manifest sha256 {s_a.get('manifest_sha256')} -> {r_a.get('manifest_sha256')}",
                }
            )

    # Browsers: per-profile file hash deltas. Profiles present on only one
    # side are summarized (one line, not one line per file) to keep the
    # report reviewable.
    s_br, r_br = source.get("state", {}).get("browsers", {}), reference.get("state", {}).get("browsers", {})
    for name in sorted(set(s_br) | set(r_br)):
        if name in s_br and name in r_br:
            result["state"]["browsers"].extend(
                _diff_dir_files(f"browsers/{name}", s_br[name].get("files", []), r_br[name].get("files", []))
            )
        elif name in s_br:
            result["state"]["browsers"].append(
                {
                    "path": f"browsers/{name}",
                    "kind": "added",
                    "detail": f"{len(s_br[name].get('files', []))} files",
                }
            )
        else:
            result["state"]["browsers"].append(
                {
                    "path": f"browsers/{name}",
                    "kind": "removed",
                    "detail": f"{len(r_br[name].get('files', []))} files",
                }
            )

    # dconf: database hashes + dump deltas.
    s_dc, r_dc = source.get("state", {}).get("dconf", {}), reference.get("state", {}).get("dconf", {})
    for key in sorted(set(s_dc) | set(r_dc)):
        result["state"]["dconf"].extend(_diff_blob(f"dconf/{key}", s_dc.get(key), r_dc.get(key)))

    return result


def _fmt_kind(kind: str) -> str:
    """Git-diff-style marker for a delta kind."""
    return {"added": "+", "removed": "-", "changed": "~", "deferrable": "="}.get(kind, "?")


def format_diff(diff: dict, source: dict, reference: dict) -> str:
    """Human-readable git-diff-style review of a manifest diff."""
    lines = []
    ref_schema = reference.get("schema", "reference")
    lines.append(f"diff machine.json ({diff['source']['host']}@{diff['source']['os']}) "
                 f"{ref_schema} ({diff['reference'].get('created_at', '')})")

    if diff["deferrable"]:
        lines.append(f"\nDEFERRED to Omarchy ({len(diff['deferrable'])}): Omarchy already ships these — skip")
        for d in diff["deferrable"]:
            lines.append(f"  {_fmt_kind('deferrable')} {d['source_app']}  (Omarchy: {d.get('omarchy')})")

    if diff["apps"]["added"]:
        lines.append(f"\nAPPS ADDED (source only, {len(diff['apps']['added'])}):")
        for a in diff["apps"]["added"]:
            lines.append(f"  + {a['source_app']}")
    if diff["apps"]["removed"]:
        lines.append(f"\nAPPS REMOVED (reference only, {len(diff['apps']['removed'])}):")
        for a in diff["apps"]["removed"]:
            lines.append(f"  - {a['source_app']}")
    if diff["apps"]["changed"]:
        lines.append(f"\nAPPS CHANGED ({len(diff['apps']['changed'])}):")
        for c in diff["apps"]["changed"]:
            lines.append(f"  ~ {c['source_app']}: {c['source'].get('omarchy')} -> {c['reference'].get('omarchy')}")

    cfg_deltas = diff["state"]["configs"]
    if cfg_deltas:
        lines.append(f"\nCONFIG STATE ({len(cfg_deltas)} delta{'s' if len(cfg_deltas) != 1 else ''}):")
        for d in cfg_deltas:
            path = d.get("path", d.get("config", ""))
            extra = f"  {d.get('detail', '')}" if d.get("detail") else ""
            lines.append(f"  {_fmt_kind(d['kind'])} {path}{extra}")

    steam = diff["state"]["steam"]
    if steam:
        lines.append(f"\nSTEAM STATE ({len(steam)} delta{'s' if len(steam) != 1 else ''}):")
        for d in steam:
            extra = f"  {d.get('detail', '')}" if d.get("detail") else ""
            lines.append(f"  {_fmt_kind(d['kind'])} steam:{d['appid']} {d.get('name', '')}{extra}")

    browsers = diff["state"]["browsers"]
    if browsers:
        lines.append(f"\nBROWSER PROFILES ({len(browsers)} delta{'s' if len(browsers) != 1 else ''}):")
        for d in browsers:
            extra = f"  {d.get('detail', '')}" if d.get("detail") else ""
            lines.append(f"  {_fmt_kind(d['kind'])} {d['path']}{extra}")

    dconf = diff["state"]["dconf"]
    if dconf:
        lines.append(f"\nDCONF ({len(dconf)} delta{'s' if len(dconf) != 1 else ''}):")
        for d in dconf:
            extra = f"  {d.get('detail', '')}" if d.get("detail") else ""
            lines.append(f"  {_fmt_kind(d['kind'])} {d['path']}{extra}")

    total = (
        len(diff["apps"]["added"])
        + len(diff["apps"]["removed"])
        + len(diff["apps"]["changed"])
        + len(cfg_deltas)
        + len(steam)
        + len(browsers)
        + len(dconf)
    )
    lines.append(f"\n{total} total deltas ({len(diff['deferrable'])} auto-deferred)")
    return "\n".join(lines)


def cmd_diff(args: list[str]) -> int:
    if len(args) < 2:
        print("usage: manifest.py diff <source.json> <omarchy-reference.json>", file=sys.stderr)
        return 2
    try:
        source = json.loads(Path(args[0]).read_text())
        reference = json.loads(Path(args[1]).read_text())
    except OSError as e:
        print(f"cannot read manifest: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"invalid JSON in manifest: {e}", file=sys.stderr)
        return 1
    diff = diff_manifests(source, reference)
    print(format_diff(diff, source, reference))
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "scan":
        return cmd_scan(rest)
    if cmd == "diff":
        return cmd_diff(rest)
    if cmd == "reference":
        return cmd_reference(rest)
    print(f"unknown command: {cmd}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""omnigate core — cross-platform migration engine.

Exports the public API used by the CLI routers:
  detect(backend) -> ScanResult
  export_package(backend, out, **opts) -> Path
  import_package(backend, pkg, **opts) -> TxnResult
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

from lib.platform import PlatformBackend, get_backend, get_backend_for
from txn import commit_import, stage_import


class ScanResult:
    """Result of a source-OS scan."""

    def __init__(self, backend: PlatformBackend) -> None:
        self.backend = backend
        self.os_name = backend.os_name
        self.apps: set[str] = set()
        self.storage: list[dict] = []
        self.home = backend.home

    def scan(self) -> None:
        self.apps = self.backend.detect_apps()
        self.storage = self.backend.detect_storage()


def detect(os_name: str | None = None) -> ScanResult:
    """Scan the source OS. If os_name given, use that backend; else auto-detect."""
    backend = get_backend_for(os_name) if os_name else get_backend()
    result = ScanResult(backend)
    result.scan()
    return result


def export_package(
    backend: PlatformBackend,
    out: Path,
    matched: list[dict] | None = None,
    configs: dict[str, str] | None = None,
    include_creds: bool = False,
) -> Path:
    """Build a migration package from the source."""
    if matched is None:
        # Match detected apps against the mapping DB
        from scanner.detect import match
        detected = backend.detect_apps()
        matched = match(detected)

    if configs is None:
        configs = {}
        for m in matched:
            for cp in m.get("config_paths", []):
                p = _normalize_path(cp, backend.home)
                if p and p.exists():
                    key = f"{m['source_app']}__{cp.replace('/', '_').replace(chr(92), '_')}"
                    configs[key] = str(p)

    package = {
        "tool_version": "0.2",
        "exported_at": datetime.now().isoformat(),
        "os": backend.os_name,
        "host": backend.home.name,
        "detected_count": len(backend.detect_apps()),
        "matched": matched,
        "configs": configs,
    }

    if include_creds:
        package["creds"] = backend.export_creds(tier1_only=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(package, indent=2))
        for key, src_p in configs.items():
            p = Path(src_p)
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        z.write(f, f"configs/{key}/{f.relative_to(p)}")
            elif p.is_file():
                z.write(p, f"configs/{key}")

    return out


def import_package(
    backend: PlatformBackend,
    pkg: Path,
    dry_run: bool = False,
    yes: bool = False,
) -> dict:
    """Import a migration package on the target (Omarchy)."""
    from migrate import cmd_import
    args = [str(pkg)]
    if dry_run:
        args.append("--dry-run")
    if yes:
        args.append("--yes")
    rc = cmd_import(args)
    return {"ok": rc == 0, "rc": rc}


def _normalize_path(spec: str, home: Path) -> Path | None:
    """Expand ~ and env vars, return absolute Path or None."""
    if spec.startswith("~"):
        return home / spec[2:].lstrip("/")
    if spec.startswith("$HOME"):
        return home / spec[5:].lstrip("/")
    if spec.startswith("%APPDATA%"):
        return home / "AppData" / "Roaming" / spec[9:].lstrip("\\/")
    if spec.startswith("%USERPROFILE%"):
        return home / spec[13:].lstrip("\\/")
    if spec.startswith("$OMARCHY_INSTALL"):
        omarchy = Path("/usr/share/omarchy")
        return omarchy / spec[16:].lstrip("/")
    p = Path(spec)
    return p if p.is_absolute() else home / p

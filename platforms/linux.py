#!/usr/bin/env python3
"""Linux platform backend for omnigate."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


class LinuxBackend:
    """Linux source backend. Reads pacman/dpkg/flatpak/snap + lsblk."""

    def __init__(self) -> None:
        self._home = Path.home()

    @property
    def os_name(self) -> str:
        # Check for NixOS
        if Path("/etc/NIXOS").exists():
            return "nixos"
        return "linux"

    @property
    def home(self) -> Path:
        return self._home

    def detect_apps(self) -> set[str]:
        """Detect installed apps on Linux via package managers."""
        found: set[str] = set()

        # pacman: read desc files directly
        pacman_db = Path("/var/lib/pacman/local")
        if pacman_db.is_dir():
            for d in pacman_db.iterdir():
                desc = d / "desc"
                if desc.exists():
                    try:
                        text = desc.read_text()
                        lines = text.splitlines()
                        for i, line in enumerate(lines):
                            if line == "%NAME%" and i + 1 < len(lines):
                                found.add(lines[i + 1].strip())
                    except (OSError, ValueError):
                        pass

        # dpkg: read status file directly
        dpkg_status = Path("/var/lib/dpkg/status")
        if dpkg_status.exists():
            try:
                for block in dpkg_status.read_text().split("\n\n"):
                    for line in block.splitlines():
                        if line.startswith("Package: "):
                            found.add(line.split(": ", 1)[1].strip())
                            break
            except OSError:
                pass

        # flatpak
        flatpak_refs = Path("/var/lib/flatpak/app")
        if flatpak_refs.is_dir():
            for ref in flatpak_refs.iterdir():
                if ref.is_dir():
                    found.add(ref.name)

        # snap
        snap_dir = Path("/snap")
        if snap_dir.is_dir():
            for d in snap_dir.iterdir():
                if d.is_dir() and d.name not in ("bin", "current"):
                    found.add(d.name)

        return found

    def detect_storage(self) -> list[dict]:
        """Detect disk/partition layout via lsblk."""
        try:
            proc = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                return json.loads(proc.stdout).get("blockdevices", [])
        except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
            pass
        return []

    def detect_creds_tier(self, path: str) -> int:
        """Return credential tier for a path."""
        p = Path(path)
        name = p.name.lower()

        # Tier 1: auto + encrypted (SSH keys, age keys, Wi-Fi)
        if name.startswith(".ssh") or name.startswith(".age"):
            return 1

        # Tier 2: user-mediated (browsers)
        if "chrome" in name or "firefox" in name or "browser" in name:
            return 2

        # Tier 3: hard refuse (plaintext tokens, env files)
        if name == ".env" or "token" in name or "secret" in name:
            return 3

        return 1  # default: tier 1

    def export_creds(self, tier1_only: bool = True) -> dict:
        """Export tier-1 credentials (SSH keys)."""
        out: dict[str, str] = {}
        ssh_dir = self.home / ".ssh"
        if ssh_dir.is_dir():
            for key in ("id_ed25519", "id_ecdsa", "id_rsa"):
                p = ssh_dir / key
                if p.is_file():
                    out[f"ssh/{key}"] = p.read_text(encoding="utf-8", errors="replace")
        return out

    def get_config_dirs(self) -> list[Path]:
        """Return XDG config dirs."""
        dirs = [self.home / ".config"]
        xdg = Path.home() / ".config"
        if xdg.is_dir():
            dirs.append(xdg)
        return dirs

#!/usr/bin/env python3
"""macOS platform backend for omnigate."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class MacOSBackend:
    """macOS source backend. Reads /Applications + brew + diskutil."""

    def __init__(self) -> None:
        self._home = Path.home()

    @property
    def os_name(self) -> str:
        return "macos"

    @property
    def home(self) -> Path:
        return self._home

    def detect_apps(self) -> set[str]:
        """Detect installed apps on macOS via /Applications + brew cask."""
        found: set[str] = set()

        for d in (self._home / "Applications", Path("/Applications")):
            if d.is_dir():
                for app in d.glob("*.app"):
                    found.add(app.stem)

        # brew cask
        try:
            proc = subprocess.run(
                ["brew", "list", "--cask"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode == 0:
                found.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return found

    def detect_storage(self) -> list[dict]:
        """Detect disk/partition layout via diskutil."""
        try:
            proc = subprocess.run(
                ["diskutil", "list", "-plist"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                return [{"macos_disks": proc.stdout[:2000]}]
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return []

    def detect_creds_tier(self, path: str) -> int:
        """Return credential tier for a path."""
        name = Path(path).name.lower()
        if name.startswith(".ssh") or name.startswith(".age"):
            return 1
        if "keychain" in name or "chain" in name:
            return 2
        return 1

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
        """Return macOS config dirs."""
        return [
            self.home / "Library" / "Application Support",
            self.home / "Library" / "Preferences",
            self.home / ".config",
        ]

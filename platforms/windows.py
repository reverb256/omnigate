#!/usr/bin/env python3
"""Windows platform backend for omnigate."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class WindowsBackend:
    """Windows source backend. Reads registry + PowerShell + netsh."""

    def __init__(self) -> None:
        self._home = Path.home()

    @property
    def os_name(self) -> str:
        return "windows"

    @property
    def home(self) -> Path:
        return self._home

    def detect_apps(self) -> set[str]:
        """Detect installed apps on Windows via registry uninstall keys."""
        found: set[str] = set()
        keys = [
            r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        ]
        expanded = {
            r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall":
                r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall":
                r"HKEY_LOCAL_MACHINE\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall":
                r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        }
        for key in keys:
            try:
                proc = subprocess.run(
                    ["reg", "query", key],
                    capture_output=True, text=True, timeout=30,
                )
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        stripped = line.strip()
                        for prefix in (expanded[key], key):
                            if stripped.startswith(prefix):
                                stripped = stripped[len(prefix):].strip().lstrip("\\")
                                break
                        if stripped and not stripped.startswith("{"):
                            found.add(stripped)
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
        return found

    def detect_storage(self) -> list[dict]:
        """Detect disk/partition layout via PowerShell."""
        ps = "Get-Disk | Get-Partition | Select-Object DiskNumber,PartitionNumber,Size,Type,DriveLetter | ConvertTo-Json"
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                if isinstance(data, dict):
                    data = [data]
                return [{"windows_partition": p} for p in data]
        except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
            pass
        return []

    def detect_creds_tier(self, path: str) -> int:
        """Return credential tier for a path."""
        name = Path(path).name.lower()
        if name.startswith(".ssh") or name.startswith(".age"):
            return 1
        if "credential" in name or "token" in name:
            return 3
        return 1

    def export_creds(self, tier1_only: bool = True) -> dict:
        """Export tier-1 credentials (SSH keys + Wi-Fi profiles)."""
        out: dict[str, str] = {}
        ssh_dir = self.home / ".ssh"
        if ssh_dir.is_dir():
            for key in ("id_ed25519", "id_ecdsa", "id_rsa"):
                p = ssh_dir / key
                if p.is_file():
                    out[f"ssh/{key}"] = p.read_text(encoding="utf-8", errors="replace")

        # Wi-Fi profiles (netsh)
        try:
            proc = subprocess.run(
                ["netsh", "wlan", "show", "profiles"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    if ":" in line and "Profile" in line:
                        name = line.split(":", 1)[1].strip()
                        out[f"wifi/{name}"] = "netsh export"
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return out

    def get_config_dirs(self) -> list[Path]:
        """Return Windows config dirs."""
        return [
            Path.home() / "AppData" / "Roaming",
            Path.home() / "AppData" / "Local",
        ]

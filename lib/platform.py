#!/usr/bin/env python3
"""Platform abstraction for omnigate.

Each backend implements detect_apps(), detect_storage(), and the creds API.
All three source OSes (Linux, macOS, Windows) are first-class.
"""
from __future__ import annotations

import platform
from pathlib import Path
from typing import Protocol


class PlatformBackend(Protocol):
    """Interface every platform backend must implement."""

    @property
    def os_name(self) -> str: ...

    @property
    def home(self) -> Path: ...

    def detect_apps(self) -> set[str]: ...

    def detect_storage(self) -> list[dict]: ...

    def detect_creds_tier(self, path: str) -> int: ...

    def export_creds(self, tier1_only: bool = True) -> dict: ...

    def get_config_dirs(self) -> list[Path]: ...


def get_backend() -> PlatformBackend:
    """Return the correct backend for the current OS."""
    system = platform.system().lower()
    if system == "linux":
        from platforms.linux import LinuxBackend
        return LinuxBackend()
    elif system == "darwin":
        from platforms.macos import MacOSBackend
        return MacOSBackend()
    elif system == "windows":
        from platforms.windows import WindowsBackend
        return WindowsBackend()
    else:
        raise RuntimeError(f"unsupported platform: {system}")


def get_backend_for(os_name: str) -> PlatformBackend:
    """Return backend by name (for cross-platform testing)."""
    os_name = os_name.lower()
    if os_name in ("linux", "nixos"):
        from platforms.linux import LinuxBackend
        return LinuxBackend()
    elif os_name == "macos":
        from platforms.macos import MacOSBackend
        return MacOSBackend()
    elif os_name == "windows":
        from platforms.windows import WindowsBackend
        return WindowsBackend()
    else:
        raise RuntimeError(f"unsupported os: {os_name}")

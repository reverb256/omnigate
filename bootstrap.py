#!/usr/bin/env python3
"""omnigate bootstrap — cross-platform launcher for the omarchy-migrate tool.

Runs on the SOURCE machine (Linux / macOS / Windows) with only the Python
standard library. Responsibilities:

  1. Find a usable Python 3 — the `py -3` Windows launcher first on Windows,
     then `python3`, then `python`.
  2. Find git (the migration backbone: export artifacts are git-committable).
  3. Print clear per-OS install instructions when either is missing.
  4. Run the requested omnigate command with a deterministic cwd (the repo
     root), so relative imports resolve no matter where the wrapper was
     invoked from.

Usage:
    python3 bootstrap.py <command> [args...]
    python3 bootstrap.py --help | --version
    python3 bootstrap.py doctor

Commands (see each tool's own --help for full flags):
    export    migrate.py export            — source side: build migration package
    import    migrate.py import            — target side: port package on Omarchy
    detect    scanner/detect.py            — detect installed apps on the source OS
    map       mapper/map.py                — classify apps (defer / map / unknown)
    port      mapper/port_configs.py       — port configs to target layout
    gen       generator/gen_hm.py          — generate Reverb-OS HM profile fragment
    sync      sync.py                      — differential sync (reflink-first)
    mount     mount.py                     — union-mount old disk (Linux, root)

Pure stdlib — no third-party dependencies.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

TOOL_VERSION = "0.1"
MIN_PYTHON = (3, 9)  # the repo uses `X | None` annotations + f-strings

REPO = Path(__file__).resolve().parent

COMMANDS: dict[str, dict[str, str]] = {
    "export": {
        "script": "migrate.py",
        "subcommand": "export",  # migrate.py needs the subcommand word first
        "args": "[--os linux|macos|windows] [--out PATH]",
        "desc": "export a migration package from the source machine (git-committable artifacts)",
    },
    "import": {
        "script": "migrate.py",
        "subcommand": "import",
        "args": "PACKAGE.zip [--dry-run]",
        "desc": "import a package on the fresh Omarchy box",
    },
    "detect": {
        "script": "scanner/detect.py",
        "args": "[--os linux|macos|windows] [--json]",
        "desc": "detect installed apps on the source OS",
    },
    "map": {
        "script": "mapper/map.py",
        "args": "REPORT.json [--json]",
        "desc": "classify detected apps (defer / map / unknown)",
    },
    "port": {
        "script": "mapper/port_configs.py",
        "args": "REPORT.json [--dry-run] [--source-home PATH] [--target-home PATH]",
        "desc": "port configs to the target layout (dry-run safe)",
    },
    "gen": {
        "script": "generator/gen_hm.py",
        "args": "REPORT.json [--out PATH]",
        "desc": "generate a Reverb-OS Home Manager profile fragment",
    },
    "sync": {
        "script": "sync.py",
        "args": "SRC_DIR TARGET_DIR [--dry-run] [--threads N]",
        "desc": "differential sync (reflink-first)",
    },
    "mount": {
        "script": "mount.py",
        "args": "mount|list|unmount [ARGS]",
        "desc": "union-mount the old disk (Linux target only, requires root)",
    },
    "replicate": {
        "script": "replicate.py",
        "args": "share|receive [ARGS]",
        "desc": "peer-to-peer setup replication (Like Bitcoin): share your setup or pull a friend's",
    },
    "wizard": {
        "script": "app.py",
        "args": "",
        "desc": "launch the Flet on-ramp wizard (Look → Choose → Keep → Land → OSR)",
    },
}


INSTALL_HINTS = {
    "win32": (
        "Python: install from https://www.python.org/downloads/windows/ and tick\n"
        "        'Add python.exe to PATH' — or use the Microsoft Store 'python3' app.\n"
        "git:    install Git for Windows from https://git-scm.com/download/win\n"
        "        (default options put git on PATH)."
    ),
    "darwin": (
        "Python: run `xcode-select --install` (provides python3 + git), or\n"
        "        https://www.python.org/downloads/macos/  or  `brew install python`.\n"
        "git:    `xcode-select --install`  or  `brew install git`."
    ),
    "linux": (
        "Python: use your package manager, e.g. `sudo apt install python3`,\n"
        "        `sudo pacman -S python`, `sudo dnf install python3`.\n"
        "git:    e.g. `sudo apt install git`, `sudo pacman -S git`."
    ),
}


def install_hints() -> str:
    """Per-OS install instructions, defaulting to Linux for unknown platforms."""
    return INSTALL_HINTS.get(sys.platform, INSTALL_HINTS["linux"])


def _python_version(py_cmd: list[str]) -> tuple[int, int] | None:
    """Return (major, minor) if py_cmd runs a Python, else None."""
    try:
        out = subprocess.run(
            [*py_cmd, "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            return None
        parsed = ast.literal_eval(out.stdout.strip())
        if isinstance(parsed, tuple) and len(parsed) == 2:
            return int(parsed[0]), int(parsed[1])
        return None
    except (OSError, subprocess.SubprocessError, ValueError, SyntaxError):
        return None


def _python_version_str(py_cmd: list[str]) -> str:
    """Human-readable Python version, e.g. '3.13.14'."""
    try:
        out = subprocess.run(
            [*py_cmd, "-c", "import platform; print(platform.python_version())"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def find_python() -> list[str] | None:
    """Return the argv prefix that runs a usable Python 3, or None.

    Windows: prefer the `py` launcher (py -3), then python3, then python.
    macOS/Linux: python3, then python.
    """
    if sys.platform == "win32":
        candidates: list[list[str]] = [["py", "-3"], ["python3"], ["python"]]
    else:
        candidates = [["python3"], ["python"]]
    for cand in candidates:
        if not shutil.which(cand[0]):
            continue
        ver = _python_version(cand)
        if ver is not None and ver >= MIN_PYTHON:
            return cand
    return None


def find_git() -> Path | None:
    """Return the git executable path, or None.

    On Windows, also probes the standard Git for Windows locations when git
    is not on PATH.
    """
    found = shutil.which("git")
    if found:
        return Path(found)
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Git" / "cmd" / "git.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs" / "Git" / "cmd" / "git.exe",
        ]
        for cand in candidates:
            if cand.is_file():
                return cand
    return None


def usage() -> str:
    width = max(len(n) for n in COMMANDS)
    lines = [
        "omnigate — cross-platform migration to Omarchy (Linux / macOS / Windows)",
        "",
        f"Usage: python3 bootstrap.py <command> [args...]   (omnigate v{TOOL_VERSION})",
        "       python3 bootstrap.py --help | --version",
        "       python3 bootstrap.py doctor",
        "",
        "Commands:",
    ]
    for name, info in COMMANDS.items():
        args = info.get("args", "")
        lines.append(f"  {name:<{width}}  {info['desc']}")
        if args:
            lines.append(f"  {'':<{width}}  args: {args}")
    lines += [
        "",
        "bootstrap.py finds Python 3 and git, prints install instructions if",
        "either is missing, then runs the command with the repo root as cwd.",
    ]
    return "\n".join(lines)


def cmd_doctor() -> int:
    """Print the Python + git environment and exit non-zero if anything is missing."""
    py_cmd = find_python()
    git = find_git()
    ok = True

    if py_cmd is not None:
        print(f"python: {' '.join(py_cmd)}  ({_python_version_str(py_cmd)})")
    else:
        ok = False
        print("python: NOT FOUND")

    if git is not None:
        print(f"git:    {git}")
    else:
        ok = False
        print("git:    NOT FOUND")

    if not ok:
        print("\nInstall instructions:")
        print(install_hints())
        return 1
    print("\nEnvironment OK — run `python3 bootstrap.py --help` to see commands.")
    return 0


def run_command(py_cmd: list[str], command: str, rest: list[str]) -> int:
    """Run the omnigate subcommand, inheriting stdio so exit codes pass through."""
    info = COMMANDS[command]
    script = REPO / info["script"]

    if command == "mount" and sys.platform != "linux":
        print(
            "mount runs only on the Omarchy (Linux) target — it needs overlayfs and root.",
            file=sys.stderr,
        )
        return 2

    argv = [*py_cmd, str(script)]
    sub = info.get("subcommand")
    if sub is not None:
        argv.append(sub)
    argv.extend(rest)
    # Deterministic cwd: the repo root, so the tool's relative imports
    # (scanner/, mapper/, generator/) resolve regardless of invocation dir.
    return subprocess.run(argv, cwd=str(REPO)).returncode


def main() -> int:
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(usage())
        return 0
    if args[0] == "--version":
        print(f"omnigate v{TOOL_VERSION}")
        return 0

    command = args[0]
    if command == "doctor":
        return cmd_doctor()
    if command not in COMMANDS:
        print(f"unknown command: {command}", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 2

    py_cmd = find_python()
    if py_cmd is None:
        print(
            f"omnigate: no usable Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ found.",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print(install_hints(), file=sys.stderr)
        return 3

    git = find_git()
    if git is None:
        print(
            "omnigate: git not found — git is the migration backbone (export "
            "artifacts are git-committable).",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print(install_hints(), file=sys.stderr)
        return 3

    return run_command(py_cmd, command, args[1:])


if __name__ == "__main__":
    sys.exit(main())

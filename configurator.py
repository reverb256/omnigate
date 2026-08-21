#!/usr/bin/env python3
"""omnigate configurator — the real Omarchy installation, 1:1.

Mirrors the Omarchy ISO configurator (configs/airootfs/root/configurator)
screen-for-screen, prompt-for-prompt, palette-for-palette — but for a
MIGRATION instead of a fresh install. Same structure:
  step()       — clear screen + step header
  gum-style    — selection menus with preselect
  validation   — retry loops with notice
  confirmation — table, re-run on reject
  JSON out     — the migration plan (instead of archinstall configs)

Osaka Jade palette (official Omarchy theme):
  bg #111c18  red #FF5345  green #549e6a  yellow #459451
  blue #509475  magenta #D2689C  cyan #2DD5B7  fg #C1C497  bright #F6F5DD
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Osaka Jade palette (official Omarchy theme, exact hex) ───────────────
BG = "\x1b[48;2;17;28;24m"          # #111c18 background
RED = "\x1b[38;2;255;83;69m"        # #FF5345 errors
GREEN = "\x1b[38;2;84;158;106m"     # #549e6a success
YELLOW = "\x1b[38;2;69;148;81m"     # #459451 warnings
BLUE = "\x1b[38;2;80;148;117m"      # #509475 info
MAGENTA = "\x1b[38;2;210;104;156m"  # #D2689C highlights
CYAN = "\x1b[38;2;45;213;183m"      # #2DD5B7 accent
FG = "\x1b[38;2;193;196;151m"       # #C1C497 foreground
BRIGHT = "\x1b[38;2;246;245;221m"   # #F6F5DD bright white
BRIGHT_CYAN = "\x1b[38;2;140;211;203m"  # #8CD3CB bright cyan
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

PADDING_LEFT = "  "


def clear() -> None:
    """Mirror the Omarchy installer's screen clear (ttys + emulators)."""
    if sys.stdout.isatty():
        os.system("clear" if os.name != "nt" else "cls")


def step(title: str) -> None:
    """step() — clear screen + step header (exactly like the configurator)."""
    clear()
    print(f"{BOLD}{BG}  {title}  {RESET}\n")


def abort() -> int:
    """abort() — mirror the Omarchy exact abort message."""
    print(f"\n{RED}Aborted installation{RESET}\n")
    print(f"You can retry later by running: {BRIGHT}./configurator.py{RESET}")
    return 1


def notice(msg: str) -> None:
    """notice() — temporary notification with spinner feel."""
    print(f"{DIM}  ⠋ {msg}{RESET}", end="\r", flush=True)


def choose(title: str, options: list[str], preselect: str | None = None,
           height: int = 10) -> str:
    """gum choose — selection menu with preselect, keyboard-driven."""
    step(title)
    # Preselect index
    idx = 0
    if preselect:
        for i, o in enumerate(options):
            if preselect in o:
                idx = i
                break
    # Render visible window (gum --height)
    for i, o in enumerate(options):
        arrow = "›" if i == idx else " "
        sel = f"{CYAN}{arrow} {o}{RESET}" if i == idx else f"{FG}  {o}{RESET}"
        print(f"{PADDING_LEFT}{sel}")
    print(f"\n{DIM}  ↑/↓ navigate · Enter select · Esc abort{RESET}\n")
    # Keyboard loop
    while True:
        k = _read_key()
        if k in ("\x1b", "q"):  # Esc
            return ""
        if k in ("\r", "\n", " "):
            return options[idx]
        if k in ("A", "k"):  # up
            idx = max(0, idx - 1)
        elif k in ("B", "j"):  # down
            idx = min(len(options) - 1, idx + 1)
        else:
            # Arrow keys come as escape sequences; read the rest
            if k == "\x1b":
                seq = _read_key() + _read_key()
                if seq == "[A":
                    idx = max(0, idx - 1)
                elif seq == "[B":
                    idx = min(len(options) - 1, idx + 1)
        _redraw_menu(title, options, idx, height)


def _redraw_menu(title: str, options: list[str], idx: int, height: int) -> None:
    clear()
    print(f"{BOLD}{BG}  {title}  {RESET}\n")
    start = max(0, idx - height // 2)
    end = min(len(options), start + height)
    for i in range(start, end):
        o = options[i]
        arrow = "›" if i == idx else " "
        sel = f"{CYAN}{arrow} {o}{RESET}" if i == idx else f"{FG}  {o}{RESET}"
        print(f"{PADDING_LEFT}{sel}")
    print(f"\n{DIM}  ↑/↓ navigate · Enter select · Esc abort{RESET}\n")


def _read_key() -> str:
    """Read one keypress (raw mode on unix, input() on windows)."""
    if sys.platform != "win32":
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch
    return sys.stdin.readline().strip()[:1]


def prompt(label: str, validate=None, default: str = "",
           secret: bool = False) -> str:
    """gum input — labeled input with validation retry loop."""
    while True:
        if secret:
            print(f"{PADDING_LEFT}{BRIGHT}{label}: {RESET}", end="", flush=True)
            val = _read_secret()
            print()
        else:
            if default:
                print(f"{PADDING_LEFT}{BRIGHT}{label} [{default}]: {RESET}",
                      end="", flush=True)
            else:
                print(f"{PADDING_LEFT}{BRIGHT}{label}: {RESET}",
                      end="", flush=True)
            val = input().strip() or default
        if validate:
            err = validate(val)
            if err:
                print(f"{RED}  ✗ {err}{RESET}")
                continue
        return val


def _read_secret() -> str:
    """Password read without echo (getpass)."""
    try:
        import getpass
        return getpass.getpass("")
    except Exception:
        return input()


def confirm_table(rows: list[tuple[str, str]]) -> bool:
    """gum table — confirmation table, re-run on reject."""
    step("Confirm configuration")
    print(f"{DIM}  Configuration summary:{RESET}\n")
    w = max(len(k) for k, _ in rows) + 2
    for k, v in rows:
        print(f"{PADDING_LEFT}{FG}{k:<{w}}{RESET}{BRIGHT}{v}{RESET}")
    print()
    while True:
        ans = choose("Confirm?", ["Yes, looks good", "No, change it"])
        if ans == "Yes, looks good":
            return True
        if ans == "No, change it":
            return False
        # Esc → abort
        return False


def disk_confirm(disk: str) -> bool:
    """Destructive disk confirmation — EXACT Omarchy strings."""
    step("Confirm disk")
    print(f"{PADDING_LEFT}{BRIGHT}{disk}{RESET}\n")
    print(f"{RED}  Everything will be overwritten. There is no recovery possible.{RESET}\n")
    ans = choose("Proceed?", ["Yes, format disk", "No, change it"])
    return ans == "Yes, format disk"


def get_disk_info() -> list[tuple[str, str]]:
    """lsblk-based disk discovery like get_disk_info()."""
    disks = []
    try:
        out = subprocess.run(["lsblk", "-dno", "NAME,SIZE,MODEL"],
                             capture_output=True, text=True, timeout=5).stdout
        for line in out.strip().splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2:
                dev = f"/dev/{parts[0]}"
                size = parts[1]
                model = parts[2] if len(parts) > 2 else ""
                disks.append((f"{dev} ({size}){ ' - ' + model if model else ''}", dev))
    except Exception:
        pass
    return disks


def main() -> int:
    dry = len(sys.argv) > 1 and sys.argv[1] == "dry"
    auto = len(sys.argv) > 1 and sys.argv[1] == "--auto"
    step("omnigate — the real Omarchy installation")

    # ── 1. Keyboard (mirror the installer) ───────────────────────────────
    if auto:
        kb_code = "us"
    else:
        kb = choose("Keyboard layout", [
            "English (US)|us", "English (UK)|uk", "German|de", "French|fr",
            "Spanish|es", "Italian|it", "Polish|pl", "Russian|ru",
            "Japanese|jp106", "Dvorak|dvorak", "Brazilian|br-abnt2",
        ], preselect="English (US)")
        if not kb:
            return abort()
        kb_code = kb.split("|")[-1]

    # ── 2. User form (mirror the installer's user_form) ──────────────────
    def validate_username(v: str):
        import re
        return None if re.match(r"^[a-z_][a-z0-9_-]*$", v) else \
            "Username must match [a-z_][a-z0-9_-]*"

    def validate_hostname(v: str):
        import re
        return None if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", v) else \
            "Hostname must match [A-Za-z_][A-Za-z0-9_-]*"

    if auto:
        username, password, full_name = "migrated", "migrated-pass", ""
        email, hostname, timezone = "", "omarchy", "America/Chicago"
        kb_code = "us"
    else:
        username = prompt("Username", validate_username)
        password = prompt("Password", lambda v: None if v else "Password cannot be empty", secret=True)
        password2 = prompt("Confirm password", secret=True)
        while password != password2:
            print(f"{RED}  ✗ Passwords do not match{RESET}")
            password = prompt("Password", lambda v: None if v else "Password cannot be empty", secret=True)
            password2 = prompt("Confirm password", secret=True)
        full_name = prompt("Full name (optional)")
        email = prompt("Email (optional)")
        hostname = prompt("Hostname", validate_hostname, default="omarchy")
        timezone = prompt("Timezone", default="America/Chicago")

    # ── 3. Confirmation table (re-run on reject) ────────────────────────
    pw_stars = "*" * len(password)
    if not auto:
        while True:
            ok = confirm_table([
                ("Username", username),
                ("Password", pw_stars),
                ("Full name", full_name or "[Skipped]"),
                ("Email address", email or "[Skipped]"),
                ("Hostname", hostname),
                ("Timezone", timezone),
                ("Keyboard", kb_code),
            ])
            if ok:
                break
            # re-run the forms (like the installer)
            username = prompt("Username", validate_username)
            password = prompt("Password", lambda v: None if v else "Password cannot be empty", secret=True)
            password2 = prompt("Confirm password", secret=True)
            while password != password2:
                print(f"{RED}  ✗ Passwords do not match{RESET}")
                password = prompt("Password", lambda v: None if v else "Password cannot be empty", secret=True)
                password2 = prompt("Confirm password", secret=True)
            full_name = prompt("Full name (optional)")
            email = prompt("Email (optional)")
            hostname = prompt("Hostname", validate_hostname, default="omarchy")
            timezone = prompt("Timezone", default="America/Chicago")
            pw_stars = "*" * len(password)

    # ── 4. Disk selection + destructive confirm ──────────────────────────
    disks = get_disk_info()
    chosen = None
    if disks and not auto:
        chosen = choose("Select disk", [d[0] for d in disks])
        if not chosen:
            return abort()
        if not disk_confirm(chosen):
            return abort()

    # ── 5. JSON generation (the migration plan) ──────────────────────────
    out = {
        "schema": "omnigate/installer/v1",
        "keyboard": kb_code,
        "username": username,
        "full_name": full_name,
        "email": email,
        "hostname": hostname,
        "timezone": timezone,
        "disk": chosen if disks else None,
    }
    if dry:
        print(f"{YELLOW}  [dry-run] would write:{RESET}")
        import json
        print(json.dumps(out, indent=2))
        return 0
    Path("omarchy-user-config.json").write_text(
        __import__("json").dumps(out, indent=2))
    print(f"\n{GREEN}  ✓ Configuration written -> omarchy-user-config.json{RESET}")
    print(f"{DIM}  (dry: ./configurator.py dry){RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

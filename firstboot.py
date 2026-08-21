#!/usr/bin/env python3
"""omnigate firstboot — the post-migration welcome (Omarchy-style notices).

Mirrors Omarchy's first-boot notifications ("Update System", "Learn
Keybindings") with migration-specific equivalents:
  - "Your migration is live" — what was restored
  - "Activate your profile" — drop migration-profile.nix into HM
  - "Restore credentials" — if creds were exported, decrypt + import
  - "Update your system" — the Omarchy update notice

Runs from the completion marker (/var/tmp/omnigate-import-completed);
ships as a standalone script users can also run manually.

Osaka Jade palette (official Omarchy theme).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Osaka Jade (exact hex from basecamp/omarchy themes/osaka-jade)
BG = "\x1b[48;2;17;28;24m"
RED = "\x1b[38;2;255;83;69m"
GREEN = "\x1b[38;2;84;158;106m"
YELLOW = "\x1b[38;2;69;148;81m"
BLUE = "\x1b[38;2;80;148;117m"
CYAN = "\x1b[38;2;45;213;183m"
FG = "\x1b[38;2;193;196;151m"
BRIGHT = "\x1b[38;2;246;245;221m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"

MARKER = Path("/var/tmp/omnigate-import-completed")


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _recap() -> list[tuple[str, str]]:
    """Build the migration recap from the marker + backup dirs."""
    rows = []
    marker_time = ""
    try:
        marker_time = MARKER.read_text().strip()
    except OSError:
        pass
    if marker_time:
        rows.append(("Migration completed", marker_time))
    # Count configs restored from the newest backup manifest
    backups = sorted(Path.home().glob(".omarchy-migrate-backup-*"))
    if backups:
        latest = backups[-1]
        mf = latest / "manifest.json"
        if mf.exists():
            try:
                manifest = json.loads(mf.read_text())
                rows.append(("Configs backed up", str(len(manifest))))
            except Exception:
                pass
        else:
            n = sum(1 for _ in latest.iterdir())
            rows.append(("Configs backed up", str(n)))
    # HM fragment
    hm = Path.home() / "migration-profile.nix"
    if hm.exists():
        rows.append(("HM profile fragment", str(hm)))
    # Credentials?
    creds = Path.home() / ".omnigate-creds.age.json"
    if creds.exists():
        rows.append(("Encrypted credentials", "restore with age"))
    return rows


def show() -> int:
    """Render the first-boot welcome (Osaka Jade)."""
    rows = _recap()
    print(f"{BG}{BOLD}  omnigate — your migration is live{RESET}\n")
    print(f"{FG}  Welcome to your Omarchy box. The migration is complete.{RESET}\n")

    if rows:
        w = max(len(k) for k, _ in rows) + 2
        for k, v in rows:
            print(f"  {FG}{k:<{w}}{RESET}{BRIGHT}{v}{RESET}")
        print()

    # Notices (Omarchy-style)
    print(f"{CYAN}  ✓ Activate your profile{RESET}")
    print(f"    Drop {BRIGHT}migration-profile.nix{RESET} into your Home "
          f"Manager config and activate.")
    print()
    print(f"{CYAN}  ✓ Restore credentials{RESET}")
    print(f"    If you exported credentials, decrypt them now:")
    print(f"      {BRIGHT}age -d ~/.omnigate-creds.age.json > creds.json{RESET}")
    print()
    print(f"{YELLOW}  ✓ Update your system{RESET}")
    print(f"    Run the Omarchy updater (Super+Space → Update, or "
          f"{BRIGHT}omarchy update{RESET}).")
    print()
    print(f"{DIM}  (First boot notice — hidden on subsequent runs by the "
          f"completion marker.){RESET}")
    return 0


def main() -> int:
    # Manual run always shows; auto-run only if the marker exists
    if "--force" not in sys.argv and not MARKER.exists():
        print(f"{DIM}  No migration completion marker found — nothing to "
              f"show. (Use --force to preview.){RESET}")
        return 0
    return show()


if __name__ == "__main__":
    sys.exit(main())

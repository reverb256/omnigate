# Omarchy-Migrate Integration Architecture

## Design Goals

1. **Deep Omarchy integration** — follow all conventions from `~/Projects/omarchy`
2. **Cross-platform source side** — Windows, macOS, Linux all first-class
3. **Omarchy-side native** — runs as `omarchy-migrate` command, hooks into first-run, menu
4. **XDG compliant** — `~/.config/omarchy/migrate/` + `~/.local/share/omarchy/migrate/`

## Current vs Target

| Aspect | Current | Target |
|--------|---------|--------|
| Entry point | `bootstrap.py` (Python) | `bin/omarchy-migrate` (bash) + `bin/omarchy-migrate.ps1` (PS) |
| State dir | `~/.omnigate/` | `~/.local/state/omarchy/migrate/` |
| Config dir | none | `~/.config/omarchy/migrate/` |
| Cross-platform | Linux-first, Windows/macOS partial | All three equal |
| First-run hook | `contrib/omarchy/` custom | `install/user/first-run/migrate.hook` |
| Menu entry | none | `config/menu-entry.jsonc` |
| Notifications | stdout | `omarchy-notification-send` |

## Architecture

```
omarchy-migrate/
├── bin/
│   ├── omarchy-migrate            # bash router (Linux + macOS)
│   └── omarchy-migrate.ps1        # PowerShell router (Windows)
├── lib/
│   ├── core.py                    # Cross-platform: detect(), export(), import()
│   ├── platform.py                # Dispatches to os-specific backend
│   ├── crypto.py                  # age encryption wrapper
│   ├── state.py                   # omarchy-done ensure + state files
│   └── notify.py                  # omarchy-notification-send wrapper
├── platforms/
│   ├── linux.py                   # pacman/dpkg/flatpak/snap + lsblk
│   ├── macos.py                   # brew + system_profiler + diskutil
│   └── windows.py                 # reg query + PowerShell + netsh
├── install/
│   ├── user/first-run/
│   │   └── migrate.hook           # "Bring your files" invitation
│   └── post-install/
│       └── 1786600000.sh          # Register migrate menu entry
├── config/
│   ├── menu-entry.jsonc           # Omarchy menu entry
│   └── settings.toml              # Default settings
├── test/
│   └── ...
├── bootstrap.py                   # Launcher: find python3, delegate to lib/core.py
└── CHANGELOG.md
```

## Cross-Platform Source Detection

Each platform backend implements:

```python
class PlatformBackend:
    def detect_apps(self) -> set[str]
    def detect_storage(self) -> list[dict]
    def detect_creds_tier(self, path: str) -> int
    def export_creds(self, tier1_only: bool) -> dict
    def get_home(self) -> Path
    def get_config_dirs(self) -> list[Path]
```

### Linux (`platforms/linux.py`)
- **Apps**: pacman db (`/var/lib/pacman/local/*/desc`), dpkg (`/var/lib/dpkg/status`), flatpak, snap
- **Storage**: `lsblk -J -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL`
- **Configs**: XDG + legacy dotfiles

### macOS (`platforms/macos.py`)
- **Apps**: `/Applications/*.app` + `brew list --cask`
- **Storage**: `diskutil list -plist`
- **Configs**: `~/Library/Application Support/`, `~/Library/Preferences/`
- **Special**: Keychain export (flagged tier-2)

### Windows (`platforms/windows.py`)
- **Apps**: `reg query HKLM\...\Uninstall` + `reg query HKCU\...\Uninstall`
- **Storage**: PowerShell `Get-Disk | Get-Partition | ConvertTo-Json`
- **Configs**: `%APPDATA%`, `%LOCALAPPDATA%`, `%USERPROFILE%`
- **Special**: `netsh wlan` Wi-Fi profiles (tier-1, age-encrypted)

## Omarchy-Side Integration

### First-Run Hook (`install/user/first-run/migrate.hook`)

```bash
#!/bin/bash
set -e

# Only fire if we see evidence of a prior migration export
# (zip on a USB, or a known cloud location)
if ! omarchy-done ensure migrate-invitation; then
  exit 0
fi

omarchy-notification-send -u critical -g 󰇘 "Bring your files from your old PC" \
  "Click to import your apps, configs, and data from Windows or macOS." \
  --exec "omarchy-migrate menu"
fi
```

### Menu Entry (`config/menu-entry.jsonc`)

```jsonc
"setup.import": {
  "icon": "󰇘",
  "iconFont": "omarchy",
  "label": "Bring your files from another PC",
  "action": "omarchy-migrate"
}
```

### Post-Install Migration (`install/post-install/1786600000.sh`)

```bash
#!/bin/bash
set -e

# Register migrate commands into the omarchy-menu
omarchy-menu-group setup "Setup"
omarchy-menu-item setup.import "Bring files" "󰇘" "omarchy-migrate"
```

## Command Surface

```bash
# Detect (all platforms)
omarchy-migrate detect

# Export (source side: Windows/macOS/Linux)
omarchy-migrate export --out ~/old-pc.zip
omarchy-migrate export --os windows --out D:\migration.zip  # Windows

# Import (target side: Omarchy)
omarchy-migrate import ~/old-pc.zip --dry-run
omarchy-migrate import ~/old-pc.zip --yes

# P2P share/receive (all platforms)
omarchy-migrate share --dir ~/.config
omarchy-migrate receive http://192.168.1.10:5317/omarchy-setup-manifest.json

# Doctor (verify environment)
omarchy-migrate doctor
```

## State Management (omarchy-done pattern)

```
~/.local/state/omarchy/migrate/
├── state.json                     # wizard beat, scan counts
├── txn-*.json                     # committed import txns (for rollback)
└── wizard-state.json              # resumable wizard

~/.config/omarchy/migrate/
├── settings.toml                  # user preferences
└── excludes                       # export exclude patterns

~/.local/share/omarchy/migrate/
├── backups/                       # pre-import backups
│   └── 20260822-100000/
└── cache/                         # scan cache (for fast re-scan)
```

## Settings (`config/settings.toml`)

```toml
[export]
# Default OS to detect on the source
default_os = "linux"
# What to include
include_configs = true
include_creds = true
# Exclude patterns (gitignore syntax)
excludes = [
    "*.tmp",
    ".cache",
]

[import]
# Defer rule: skip anything Omarchy already provides
defer_to_omarchy = true
# Atomic: stage → commit (with rollback)
atomic = true

[replicate]
# Default share port
port = 5317
# Announce via multicast
multicast = true
```

## Migration to New Structure

Phase 1: Create `lib/` package, move `core` logic from `migrate.py`
Phase 2: Add `platforms/` backends, detect OS at runtime
Phase 3: Add `bin/omarchy-migrate` + `bin/omarchy-migrate.ps1`
Phase 4: Add `install/user/first-run/migrate.hook` + `config/menu-entry.jsonc`
Phase 5: Update state paths to `~/.local/state/omarchy/migrate/`
Phase 6: Tests for all platforms (mocked)

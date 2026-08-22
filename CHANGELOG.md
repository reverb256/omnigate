# Changelog

All notable changes to omnigate documentation here. Format based on
[Keep a Changelog](https://keepachangelog.com/), semantic versions.

## [0.2.0] - 2026-08-22

### Added
- On-ramp Flet wizard (`app.py`): Look → Choose → Keep → Land → OSR beat machine
- OSR peer-to-peer setup replication (`replicate.py`): share your setup or pull a
  friend's via QR code over the LAN (LocalSend-style discovery + HTTP server).
  No cloud, no login. Trust-on-first-use with BLAKE3-bundled signatures.
- Atomic two-phase import (`txn.py`): stage → commit with hash verification,
  idempotent re-runs, and rollback support via recorded backup_dir.
- Stage-0 audit (`audit.py`): auto-detect source OS (linux/nixos/macos/windows)
  + OS-specific storage discovery (lsblk, PowerShell Get-Disk, diskutil).
- Home Manager profile fragment generator (`gen_hm.py`).
- Cluster orchestration (`orchestrator.py`): per-host audit → plan → install.
- Omniport Git workflow (`omniport.py`): track migrations as Git artifacts.
- First-run notices (`firstboot.py`), TUI progress (`tui.py`), configurator
  screen (`configurator.py`), transformation planner (`plan.py`), Steam
  user-data classifier (`steam.py`).
- Bootstrap cross-platform launcher (`bootstrap.py`): Python + git detection,
  per-OS install hints, command dispatch. 10 commands: export, import, detect,
  map, port, gen, sync, mount, replicate, audit, wizard.
- Non-destructive test plan (`docs/CROSS_PLATFORM_TEST_PLAN.md`).
- Prose/styleguide docs (`docs/STYLEGUIDE.md`, `docs/PROSE.md`).

### Tests
- 213/213 tests green. Test coverage on every module:
  `tests/test_*.py` — 20 test files covering scanner, mapper, oracle, verbs,
  journey, app, txn, bootstrap, audit, replicate, creds, restore, sync, mount,
  manifest, gen_hm, compat, port_configs, omniport, logo, configurator,
  firstboot, tui, plan, steam, paradigm, core_bridge, anywhere, wizard_labels,
  match_boundary, windows_only, windows_paths.

### Fixed
- `scanner/detect.py` match() — whole-token \b word-boundary regex prevents
  substring false positives ("code" no longer matches "libavcodec"/
  "Xvid Video Codec"/"GPU Video Codec").
- `scanner/detect.py` detect_windows() — strips both HKLM→HKEY_LOCAL_MACHINE
  and HKCU→HKEY_CURRENT_USER prefixes so app names don't leak full registry paths.
- `oracle.py` _suggest_safe() — checks _tier5_verdict() before returning None
  so Windows-only apps (flight-sim, games, launchers, wine) get honest tier-5
  verdicts instead of being silently dropped.
- `txn.py` commit_import() — records backup_dir in txn log so rollback can find
  backups without scanning parent directories.

### Changed
- `migrate.py` export — added `--configs` flag for targeted export (comma-separated
  config paths). Speeds up integration tests by skipping 2GB+ home dirs.
- `bootstrap.py` — added `replicate`, `audit`, `wizard` commands.

## [0.1.0] - 2026-08-21

### Added
- Initial project scaffold: scanner, mapper, compatibility gate, config porter,
  HM generator, export/import CLI.
- Union-mount layer (`mount.py`): zero-copy data visibility via overlayfs.
- Ghost Drive (`mount.py ghost`): permanent zero-copy lower layer via GPT
  Discoverable Partitions GUID rewrite.
- Differential sync (`sync.py`): reflink-first, skip re-downloadable.
- Professional identity: logo, README, LICENSE (MIT), CI, vision doc.

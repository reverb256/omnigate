# Changelog

All notable changes to omnigate are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/), semantic versions.

## [Unreleased]

### Added
- Initial project scaffold: scanner, mapper, compatibility gate, config
  porter, HM generator, export/import CLI.
- Union-mount layer (`mount.py`): zero-copy data visibility via overlayfs.
- Ghost Drive (`mount.py ghost`): permanent zero-copy lower layer via GPT
  Discoverable Partitions GUID rewrite.
- Differential sync (`sync.py`): reflink-first, skip re-downloadable.
- Professional identity: logo, README, LICENSE (MIT), CI, vision doc.

### Fixed
- Word-boundary app matching — eliminates false positives where a detect
  name is a substring of another app (`Xvid Video Codec` / `libavcodec` no
  longer map to VS Code). `match()` now requires whole-token or
  exact-extension matches (`43d6829`).
- HKLM→HKEY_LOCAL_MACHINE registry prefix stripped from Windows Uninstall
  scan output (`717f782`).

### Extended
- Tier-5 "no Omarchy equivalent" categories: Steam games, gaming launchers,
  Wine/Proton layer, hardware-vendor utilities, NixOS-only — each with an
  honest verdict instead of silent drop (`78f2916`).
- Mapping DB grown from 25 → 45 entries: Telegram, Element, Helix, Caprine,
  Dolphin, Konsole, Kate, Meld, Vim, htop, lazydocker, Gammastep,
  LocalSend, FreeBuff, grsync, Claude Code, Hermes, gitlawb, Stability
  Matrix, atool.
- Test suite grown from 27 → 56 tests (boundary matching, tier-5
  categories, no-false-positive coverage).

### Verified
- End-to-end pipeline proven against a live Omarchy guest: `migrate.py
  export` → 1003 apps detected → 27 mapped, 2 deferred, 0 unknown → HM
  profile fragment generated.
- Zephyr (daily driver) migration report complete: 128 packages, 27 mapped,
  2 deferred, 0 unknown.

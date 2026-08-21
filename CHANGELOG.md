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

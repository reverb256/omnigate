# omnigate

**Migrate to Omarchy. Natively.**

![omnigate logo](assets/logo/omnigate-logo-horizontal.svg)

[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://img.shields.io/github/actions/workflow/status/reverb256/omnigate/ci.yml?style=flat-square)](https://github.com/reverb256/omnigate/actions/workflows/ci.yml)

`omnigate` moves a full OS setup — apps, configs, user data, even a 1 TB
game library — from Linux, macOS, or Windows to [Omarchy], without treating
migration as a file copy.

[Omarchy]: https://omarchy.org

## Why it's different

Copying a terabyte is the boring way. `omnigate` is built on three layers
that treat migration as a *mount*, then a *smart sync*, then a *manifest*:

| Layer | What it does | The world-breaking bit |
|-------|--------------|------------------------|
| **1 — Union mount** | Mount the old disk read-only as an overlayfs lower layer under the new OS | **Data appears at its new path with ZERO copy.** Steam games launch immediately. Migration = a mount entry, not a copy. |
| **2 — Differential sync** | Copy only what *changed*, skip what's re-downloadable | Reflink-first (btrfs/XFS CoW — near-instant, no duplicate space). 1 TB "migration" becomes a small copy of what matters. |
| **3 — Declarative manifest** | Describe the whole machine (apps, configs, data, library) as a rebuildable manifest | Migration stops being a thing — the machine *is* the manifest. |

Plus a two-sided export/import (Win2Linux-style) for apps + configs:

- **Source side** (old machine): detect installed apps, collect configs, build a package
- **Target side** (fresh Omarchy): map to Omarchy targets — **deferring to
  Omarchy on everything it already provides** — port configs, generate a
  Home Manager profile fragment for [Reverb-OS]

[Reverb-OS]: https://github.com/reverb256/Reverb-OS

## Status

Early but working. Scanner, mapper, compatibility gate, config porter, HM
generator, export/import, union mount, and differential sync are
implemented. See `docs/` for details.

## Quick start

```bash
# On the OLD machine — detect apps + configs, build a package
python3 migrate.py export --os linux --out my-setup.zip

# On the fresh Omarchy box — import (defer rule + compat gate + HM profile)
python3 migrate.py import my-setup.zip --dry-run

# World-breaking: mount the old disk, zero copy
sudo python3 mount.py mount /dev/sdb2 /data/games
python3 mount.py list
```

## Architecture

```
SOURCE (old machine)                    TARGET (fresh Omarchy)
────────────────────                    ─────────────────────
detect apps ──┐                         import: map (defer rule)
collect configs│  ── package.zip ──▶       compat gate
              │                          port configs
              └── old disk ──mount──▶   generate HM profile
                                        union mount (zero copy)
                                        differential sync
```

## Governing rule

> If Omarchy has a supported way to provide or configure something, defer to
> Omarchy. Never guess an unknown app — flag it for review.

This is what keeps `omnigate` additive: it never fights Omarchy, never
duplicates what Omarchy ships, and only carries what the user's system
genuinely adds on top.

## Development

`omnigate` is **AI-built**: agents design and write the code, curate the
mapping database, and tune the algorithms. The shipped runtime is
deterministic and hyper-optimized — no LLM calls at runtime.

```bash
python3 scanner/detect.py --os linux --json   # detect apps
python3 mapper/map.py scan.json               # classify (defer/map/unknown)
python3 mapper/port_configs.py map.json       # port configs (dry-run safe)
python3 generator/gen_hm.py map.json          # emit HM profile fragment
python3 sync.py <src> <dst> --dry-run         # differential sync
```

## License

MIT

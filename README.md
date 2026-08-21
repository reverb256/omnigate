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

## Cross-platform

`omnigate` runs on the **source** machine on all three OSes — Windows and
macOS included, not just as detection targets. The export side produces
git-committable artifacts (`machine.json`, `plan.md`) on any OS, and **git
is the backbone**: every machine gets a git repo of its migration state.

Three launchers ship with the repo — all stdlib, no third-party deps:

| File | OS | Notes |
|------|----|-------|
| `omnigate.sh` | macOS / Linux | POSIX sh; finds `python3`, delegates to `bootstrap.py` |
| `omnigate.ps1` | Windows | PowerShell ships with Windows; finds `py -3` / `python`, delegates to `bootstrap.py` |
| `bootstrap.py` | all three | finds Python 3 + git, prints install instructions if missing, runs the command |

**Windows**

```powershell
# PowerShell wrapper (built into Windows — no extra install)
powershell -ExecutionPolicy Bypass -File omnigate.ps1 --help
powershell -ExecutionPolicy Bypass -File omnigate.ps1 export --os windows --out my-setup.zip
powershell -ExecutionPolicy Bypass -File omnigate.ps1 doctor

# Or straight through the py launcher (Python 3.9+ required)
py -3 bootstrap.py export --os windows --out my-setup.zip
```

Requirements on Windows: **git** (install [Git for Windows](https://git-scm.com/download/win)
— default options put it on PATH) and **Python** (https://www.python.org/downloads/windows/,
tick *Add python.exe to PATH*, or the Microsoft Store `python3` app).
`bootstrap.py` checks both and prints these links if either is missing.

**macOS**

```bash
./omnigate.sh export --os macos --out my-setup.zip
```

Requirements: `xcode-select --install` provides both `python3` and git;
or install from python.org / `brew install python` and `brew install git`.

**Linux**

```bash
./omnigate.sh export --os linux --out my-setup.zip
# or directly:
python3 bootstrap.py export --os linux --out my-setup.zip
```

Check the environment on any OS:

```bash
python3 bootstrap.py doctor    # prints python + git locations/versions
```

The wrappers run from the repo root so relative imports resolve regardless
of where they are invoked; command exit codes pass through (3 = missing
toolchain, 2 = bad command/usage, 0 = success). `mount.py` is Linux-target
only (overlayfs + root).

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

## Beautiful & fast

**Beautiful.** `python3 tui.py` is a terminal UI with a command picker, a
color-coded migration-plan review (green = copy, blue = defer, yellow =
unknown), and a real-time progress bar with ETA. Box-drawn, ANSI-colored,
works on any terminal; degrades to plain text when not a TTY.

**Fast.** See [PERF.md](PERF.md) for the full design. The skip-ladder is the
#1 optimization: **mount > reflink > skip > dedup > hash-delta** — the tool
moves 20 GB, not 1 TB. The Rust core (`core/`) adds blake3 parallel hashing
(12× sha256) and reflink-first copies (0 bytes streamed), with a portable
Vulkan-compute GPU backend (CUDA/ROCm/SYCL feature-gated).

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

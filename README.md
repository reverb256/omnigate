# omarchy-migrate — migrate your OS to Omarchy, world-breaking edition

AI is used to BUILD this; the tool itself is deterministic and hyper-optimized.

## The vision: don't migrate data, MOUNT it

Copying a terabyte is the boring way. The world-breaking way:

```
Layer 1 — UNION MOUNT (mount.py):  the old disk is mounted read-only as a
  lower layer under the new Omarchy install (overlayfs). Data appears at its
  new path with ZERO copy. Steam games launch immediately. Migration = a mount
  entry, not a copy. Then sync lazily + unmount.

Layer 2 — DIFFERENTIAL SYNC:  copy only what changed/needs to be local in the
  background (skipping re-downloadable content — Steam manifests, caches).
  1TB "migration" becomes a 20G copy of what matters.

Layer 3 — DECLARATIVE MANIFEST (destination):  the whole machine — apps,
  configs, data, Steam library — described by a manifest. Rebuild any machine
  from it in minutes. Migration stops being a thing because the machine is
  declarative (this is the Reverb-OS/HM end-state).
```

## Two-sided, cross-platform

- SOURCE side (old machine, Linux/macOS/Windows): `migrate.py export` —
  detect apps, collect configs, build a package
- TARGET side (fresh Omarchy): `migrate.py import` — map (defer rule),
  port configs, generate HM profile; `mount.py mount` — union-mount the old
  data with zero copy

## Components

- `scanner/detect.py` — detect installed apps (Linux/macOS/Windows)
- `mapper/map.py` — classify: DEFER to Omarchy / MAP / UNKNOWN
- `mapper/compat.py` — compatibility gate (never auto-map unknown)
- `mapper/port_configs.py` — port configs (backup + normalize)
- `generator/gen_hm.py` — emit a Reverb-OS HM profile fragment
- `mount.py` — union-mount the old disk under Omarchy (the world-breaker)
- `migrate.py` — export/import CLI (Win2Linux-style two-sided helper)

## Governing rule

If Omarchy has a supported way to provide/configure something, defer to
Omarchy. Never guess an unknown app — flag it for review.

## Status

AI-built, deterministic runtime. Scanner + mapper + gate + generator +
export/import working. Union-mount designed (needs a root test on a real
overlay). Differential sync + manifest are the next layers. Plan:
`.hermes/plans/2026-08-21_omarchy-migration-tool.md`.

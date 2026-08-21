# Source-OS → Omarchy migration tool

Migrate an entire OS setup (Linux/macOS/Windows) to Omarchy, deferring to
Omarchy on everything it can provide, and porting the rest via the Reverb-OS
Home Manager layer.

```
TRANSPORT (nixos-anywhere-style)  → SSH → kexec → Omarchy install (cidata)
  → SCANNER (source-OS detect)    → detect installed apps on the source
    → MAPPER (defer rule)         → map to Omarchy targets, defer to Omarchy
      → GENERATOR (HM profile)    → emit a Reverb-OS HM profile fragment
```

## Layout

- `mappings/apps.json` — source-app → Omarchy-target mapping DB
- `scanner/detect.py` — detect installed apps on Linux/macOS/Windows
- `mapper/map.py` — apply the defer rule, produce a migration report
- `mapper/port_configs.py` — port config paths (with backup + normalization)
- `generator/gen_hm.py` — emit a Reverb-OS HM profile fragment
- `transport/bootstrap.sh` — nixos-anywhere-style kexec transport (gated)

## Governing rule

If Omarchy has a supported way to provide/configure something, defer to
Omarchy. The mapper never guesses an unknown app — it flags it for review.

## Status

Design + scaffold (2026-08-21). Tasks 1-2 in progress. See
`.hermes/plans/2026-08-21_omarchy-migration-tool.md`.

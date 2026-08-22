#4 Phase 9: Cross-OS Verification of dist/app

## Goal
Verify the packed Flet wizard (`dist/app`) actually launches on real Windows 11
and macOS hardware — not just under steam-run on NixOS.

## Problem
`pack.sh` succeeds with `flet pack` → 63MB `dist/app`. Smoke test on zephyr
runs under `steam-run` (works), but the real promise is double-click `.exe`
on Windows 11 and `.app` on macOS.

## Scope
### Windows (krash3, 10.1.1.150)
- Run `pack.sh` ON Windows? No — PyInstaller bundles everything; `flet pack`
  produces a standalone .exe that needs no Python on the target.
- So: run `pack.sh` on zephyr WITH cross-compilation output, then copy .exe
  to krash3 (read-write check only on the binary, no omnigate state written).
- Alternatively: use GitHub Actions / CI to produce signed .exe.
- Minimal check: `file dist/app.exe` has PE header + Win64; transfer to
  krash3 %TEMP%; run headless mode if available, or verify it doesn't
  immediately crash with missing DLL.

### macOS
- Need real macOS host or CI (GitHub Actions macos-latest).
- `flet pack --targets=macos` builds in `.app`; verify Gatekeeper
  (ad-hoc signed). Without signing, first run on a real Mac will need
  right-click-open bypass.

## Constraints
- Read-only on krash3 (no .exe execution that writes config)
- For the .app, a VM (cocoon) could work IF we solve #2 first

## Acceptance
- `file` confirms PE64+ (Windows) and Mach-O 64-bit (macOS) binaries are produced
- Windows .exe runs to window-open on real Win11 (even if headless)
- macOS .app passes `codesign --verify` or at least shows no dylib-missing errors

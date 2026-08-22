#2 macOS Testing Gap: Cocoon VM for detect_macos Validation

## Goal
Close the macOS cross-platform testing gap with a real run, not paper code.

## Problem
`detect_macos()` in `scanner/detect.py` (+ `hardware.py`) macOS path is written
but never executed. Cocoon (the macOS test VM) does not exist as a running
instance on this cluster — previous checks showed no cocoon VM directory or
qemu process.

## Scope
1. Reload `omarchy-guest-install-hm` skill → check cocoa VM harness availability
2. If a macOS VM can be provisioned (OVMF + macOS recovery ISO + serial kext):
   - Boot VM headless
   - Run `python3 scanner/detect.py --os macos` inside it
   - Capture + classify results (same as krash3 Windows run)
3. If no macOS target is available:
   - Document the gap honestly in docs/CROSS_PLATFORM_TEST_PLAN.md
   - Add `detect_macos` unit test (mocked subprocess + /Applications fake dir)

## Constraints
- Do not fabricate a macOS test that doesn't exist
- Do not modify real macOS hosts

## Acceptance
- Either: macOS detection ran on a real/macOS VM + classified ≥5 apps
- Or: documented gap + regression test for the macOS path

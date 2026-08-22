#3 Phase 8 Hardening: Real File Restore + Rollback on Guest

## Goal
Prove the three txn guarantees (atomic / idempotent / resumable) end-to-end
with real config files — not manifest-only.

## Problem
Current guest import (krash3 → guest) was manifest-only: 0 files restored.
The bug-fix proved no-op handling, but never exercised actual file movement.

## Scope
1. Create a real staged config dir on zephyr:
   `~/.config/omnigate-test/{foot.ini, starship.toml, ...}` (small, dummy content)
2. Build a zip containing those as `configs/<app>__<path>`:
   `python3 migrate.py restore <zip> --yes` (uses txn.stage_import + commit)
3. Run on Omarchy guest (omarchy@127.0.0.1:2222):
   - Files restored to correct paths
   - `b3sum` verifies content integrity
4. Run rollback:
   - Files reverted to pre-restore state
   - backup dir cleaned or preserved per policy
5. Re-run import → verifies idempotency (2nd run: 0 files, ok=True)

## Constraints
- Do not touch real Omarchy config files — use a test dir like `~/.config/omnigate-test`
- Guest is disposable — safe to mutate

## Acceptance
- Guest log shows `moved: N, skipped_identical: M, ok: True`
- Files present on guest at correct paths post-restore
- Files absent (or reverted) post-rollback
- Re-import produces `moved: 0` (idempotent)

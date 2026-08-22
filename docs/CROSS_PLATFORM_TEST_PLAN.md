# Non-destructive cross-platform test plan

Rule zero: **the krash machines are the user's real PCs.** Nothing we run
may write to them, change their state, or touch miners. Everything below is
designed around that.

## Write-audit (done 2026-08-22)

Grepped every module for writes (`write_text|mkdir|copy*|move|rmtree`):

| Module | Writes? | Where to |
|---|---|---|
| `scanner/detect.py` | ONE: scan cache `~/.omnigate-scan-cache.json` | **bypassed in export path now** (export calls detect directly, never `_save_cache`) |
| `hardware.py` | only `--out FILE` when asked | we omit it, or point at zephyr `/tmp` |
| `oracle.py`, `anywhere.py`, `audit.py` | only explicit `--out` files | run with outputs into `/tmp` on zephyr |
| `migrate.py import` | writes configs + backups | **never run on krash** — target-side only |
| `creds.py` | refuses without age; netsh *reads* Wi-Fi, writes nothing until export | flag-mode only on krash |
| `txn.py` | writes only under `~/.omnigate/` | runs on guest/zephyr only |
| `mount.py` | mounts + state file | never on krash |

## Transport safety (from homelab-ssh-probing skill)

- Windows OpenSSH: call native binaries DIRECTLY (`reg query`, `nvidia-smi`);
  no PowerShell pipelines (they hang), no CIM.
- Multi-statement remote work: script file → `ssh host 'sh -s' < file`.
  For Windows: `.ps1` via `powershell -NoProfile -NonInteractive -Command -`.
- Never `pkill -f <pattern>` over SSH (self-match kills session).
- Miners: krash2/krash3 run miners — read-only probes only; never touch
  GPU processes.

## Test matrix

### T1. krash3 (Win11, j_kro@10.1.1.150) — READ-ONLY
1. Reachability + identity check (hostname must say krash3).
2. App detection: `reg query` uninstall keys — read-only registry reads.
   Run ON ZEPHYR by pulling repo there? No — reg.exe exists only on
   Windows. Run detection remotely but cache-free:
   `ssh krash3 "reg query <key>"` per key, assemble list on zephyr,
   OR copy scanner+deps to krash3 %TEMP% and run python there if present.
   Decision: use direct `reg query` pulls (zero omnigate code on krash),
   feed results through `match()` locally on zephyr. **Nothing written
   on krash3 except nothing.**
3. Hardware snapshot: `nvidia-smi --query-gpu=...` direct call (read-only).
4. Wi-Fi profiles: `netsh wlan show profiles` (READ-only; NO `export
   key=clear` without explicit user go-ahead).

### T2. krash3 → package (built ON ZEPHYR)
- Assemble machine.json + zip from the pulled detection data on zephyr.
- Zip lives in /tmp on zephyr. krash3 untouched.

### T3. Omarchy guest — import + rollback (destructive ONLY to guest)
- scp zip to omarchy@127.0.0.1:2222.
- `migrate.py import zip --yes` (txn atomic path).
- Verify counts, then `rollback --list`. Guest is disposable; that's fine.

### T4. cocoon macOS VM — READ-ONLY detect + export inside VM
- VM is sandboxed; even writes would be contained, but still use
  cache-free detect and /tmp outputs.

## Success criteria
- Zero new files on krash2/krash3 after tests (`before`/`after` temp-dir listing).
- krash3 app count within sane range (>50 for a used Win11 box).
- At least one mapped app and one honest unknown from krash3.
- Guest import summary shows moves>0 or skipped_identical>0, ok=True.

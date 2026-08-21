# omnigate — Rollback

If a migration breaks something, restore from the backup.

## What gets backed up

During import, every config target that already exists is moved aside
BEFORE the new one is written:

```
~/.omarchy-migrate-backup-<YYYYMMDD-HHMMSS>/
  <mapped-path-with-underscores>   # e.g. home_j_kro_.config_alacritty
```

Each import run creates its own timestamped backup dir. Nothing is
overwritten silently — the old file/dir is always preserved.

## How to roll back

1. Find the backup dir:

```bash
ls -d ~/.omarchy-migrate-backup-*
```

2. Restore a single file/dir (pick the newest backup):

```bash
python3 migrate.py rollback --list                 # show backups
python3 migrate.py rollback --restore <path>       # restore one path
python3 migrate.py rollback --all                  # restore everything
```

3. Or manually, for one config:

```bash
BACKUP=$(ls -d ~/.omarchy-migrate-backup-* | tail -1)
cp -a "$BACKUP/home_j_kro_.config_alacritty" ~/.config/alacritty
```

## Rules

- Rollback never deletes the new file — it moves it to
  `.omarchy-migrate-rollback-<ts>/` first (same backup discipline).
- The HM profile fragment is NOT backed up (it's a text file you can
  regenerate with `python3 oracle.py plan` + `generator/gen_hm.py`).
- The migration package (`.zip`) is the ultimate source of truth —
  re-run `installer.py <pkg> --yes` to re-import cleanly.

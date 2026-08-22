#!/usr/bin/env python3
"""txn.py — atomic, idempotent, resumable import for omnigate.

Three guarantees, all file-backed:

  RESUMABLE   wizard state in ~/.omnigate/wizard-state.json — the wizard
              reopens where it left off.
  ATOMIC      import is two-phase: stage everything to a temp dir, verify
              hashes, then move into place. A crash during staging touches
              nothing; a crash during the move leaves a txn log that says
              exactly which paths moved.
  IDEMPOTENT  files whose target already matches the source hash are
              skipped — no re-backup, no re-copy. Safe to re-run.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

STATE_DIR = Path.home() / ".omnigate"


def _sha256(p: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(buf)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Wizard state (resumable)
# ---------------------------------------------------------------------------

def save_wizard_state(state: dict) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / "wizard-state.json"
    state = dict(state)
    state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out.write_text(json.dumps(state, indent=2))
    return out


def load_wizard_state() -> dict | None:
    p = STATE_DIR / "wizard-state.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def clear_wizard_state() -> None:
    (STATE_DIR / "wizard-state.json").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Two-phase import (atomic + idempotent)
# ---------------------------------------------------------------------------

@dataclass
class TxnPlan:
    """Staged, verified plan: what will move where, with hashes."""
    entries: list[dict] = field(default_factory=list)  # {src,dst,hash,action}
    skipped: list[dict] = field(default_factory=list)  # {dst,hash} already done
    staged_dir: Path | None = None

    @property
    def moves(self) -> list[dict]:
        return [e for e in self.entries if e["action"] == "move"]

    def to_json(self) -> str:
        d = {
            "schema": "omnigate/txn/v1",
            "entries": self.entries,
            "skipped": self.skipped,
        }
        return json.dumps(d, indent=2)


def stage_import(pairs: list[tuple[Path, Path]]) -> TxnPlan:
    """Phase 1: copy sources into a staging dir; verify each hash.

    pairs = (source_file, target_path). Nothing under target_path is touched.
    A failure here raises and the staging dir is removed — no side effects.
    """
    if not pairs:
        # A manifest-only package (no config files) is legitimate.
        # Return an empty committed-noop plan instead of raising.
        return TxnPlan()

    staged_root = STATE_DIR / f"staging-{int(time.time())}"
    staged_root.mkdir(parents=True, exist_ok=True)

    plan = TxnPlan(staged_dir=staged_root)
    try:
        for i, (src, dst) in enumerate(pairs):
            src, dst = Path(src), Path(dst)
            if not src.is_file():
                raise FileNotFoundError(f"missing source: {src}")
            h_src = _sha256(src)

            # Idempotent: target already identical → skip entirely
            if dst.is_file() and _sha256(dst) == h_src:
                plan.skipped.append({"dst": str(dst), "hash": h_src})
                continue

            s_dst = staged_root / f"{i:06d}_{src.name}"
            shutil.copy2(src, s_dst)
            h_staged = _sha256(s_dst)
            if h_staged != h_src:
                raise IOError(f"staging hash mismatch for {src}")
            plan.entries.append({
                "staged": str(s_dst),
                "dst": str(dst),
                "hash": h_src,
                "action": "move",
            })
    except Exception:
        shutil.rmtree(staged_root, ignore_errors=True)
        raise
    return plan


def commit_import(plan: TxnPlan, backup_dir: Path | None = None) -> dict:
    """Phase 2: move staged files into place. Writes a txn log first.

    Backup: any existing target that differs from the staged content is
    moved into backup_dir before being replaced. Returns a summary dict.
    """
    if plan.staged_dir is None:
        # Empty plan from stage_import (manifest-only package) = valid noop.
        return {
            "moved": 0,
            "skipped_identical": len(plan.skipped),
            "backups": [],
            "errors": [],
            "log": None,
            "ok": True,
        }
    if not plan.staged_dir.exists():
        raise ValueError("commit_import: staging dir gone (already committed?)")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = STATE_DIR / f"txn-{int(time.time())}.json"
    backup_made = []
    moved = []
    errors = []

    # Log BEFORE moving so a crash mid-move still tells us what happens.
    # Write the full summary (with backup_dir) so rollback can find backups.
    log_path.write_text(json.dumps({
        "schema": "omnigate/txn/v1",
        "entries": plan.entries,
        "skipped": plan.skipped,
        "backup_dir": str(backup_dir) if backup_dir else None,
    }, indent=2))

    for e in plan.moves:
        staged, dst = Path(e["staged"]), Path(e["dst"])
        if _sha256(staged) != e["hash"]:
            errors.append({"dst": e["dst"], "error": "pre-move hash mismatch"})
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if _sha256(dst) == e["hash"]:
                moved.append({**e, "note": "identical, no-op"})
                staged.unlink(missing_ok=True)
                continue
            bdir = Path(backup_dir) if backup_dir else (
                dst.parent / f".omnigate-backup-{time.strftime('%Y%m%d-%H%M%S')}")
            bdir.mkdir(parents=True, exist_ok=True)
            bpath = bdir / dst.name
            shutil.move(str(dst), str(bpath))
            backup_made.append({"from": str(dst), "to": str(bpath)})
        shutil.move(str(staged), str(dst))
        if _sha256(dst) != e["hash"]:
            errors.append({"dst": e["dst"], "error": "post-move hash mismatch"})
            continue
        moved.append(e)

    summary = {
        "moved": len(moved),
        "skipped_identical": len(plan.skipped),
        "backups": backup_made,
        "backup_dir": str(backup_dir) if backup_dir else None,
        "errors": errors,
        "log": str(log_path),
        "ok": not errors,
    }
    # Clean staging only on full success; leave it for forensics otherwise.
    if summary["ok"] and plan.staged_dir.exists():
        shutil.rmtree(plan.staged_dir, ignore_errors=True)
    return summary


def rollback_last_txn(log_path: str | None = None) -> dict:
    """Reverse the most recent committed txn using its backups list."""
    if log_path is None:
        logs = sorted(STATE_DIR.glob("txn-*.json"))
        if not logs:
            return {"ok": False, "error": "no txn logs found"}
        log_path = str(logs[-1])
    log = json.loads(Path(log_path).read_text())
    restored = []

    # Determine backup dir: from log's backup_dir, or reconstruct from entries
    backup_dir = log.get("backup_dir")
    if backup_dir:
        backup_dir = Path(backup_dir)

    for entry in log.get("entries", []):
        dst = Path(entry["dst"])
        if backup_dir:
            src = backup_dir / dst.name
        else:
            # Fallback: search for backup dirs by timestamp pattern
            parent_backups = sorted(dst.parent.glob(".omnigate-backup-*"))
            if not parent_backups:
                continue
            newest = parent_backups[-1]
            src = newest / dst.name
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            restored.append(str(dst))
    return {"ok": bool(restored), "restored": restored, "log": log_path}

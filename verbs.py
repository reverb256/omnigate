#!/usr/bin/env python3
"""Internal verb classifier — skip-ladder + leftover strategy.

This is NOT a user-facing surface and NEVER emits a package name.
Deterministic tables are the product. Needle (optional) may only stamp
a leftover that the tables left unlabeled. Fail-open: missing engine,
timeout, or empty call → unlabeled (same as today).

Path verbs (any OS, including macOS):
  mount | skip_redownload | copy | secret | defer_omarchy

Leftover-app verbs (Windows / macOS / Linux unknowns):
  skip | defer | containerize | no_linux | noise | real_unknown

Needle is part of omnigate. Tables run first. Needle fills leftovers
the tables left unlabeled (capped). Fail-open if the engine is missing.
Set OMNIGATE_NEEDLE=0 to skip the model. Never a package name.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

PATH_VERBS = frozenset(
    {"mount", "skip_redownload", "copy", "secret", "defer_omarchy"}
)
APP_VERBS = frozenset(
    {"skip", "defer", "containerize", "no_linux", "noise", "real_unknown"}
)

# Path fragments → skip (re-download / rebuild). Cross-OS, including macOS.
_SKIP_PARTS = (
    "node_modules", "target", ".venv", "venv", "__pycache__", ".cache",
    "Cache", "CachedData", "ShaderCache", "GLCache", ".gradle", ".cargo",
    "vendor", "Pods", ".next", ".nuxt", "bower_components", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages",
    "steamapps/common", "steamapps/downloading", "steamapps/shadercache",
    "steamapps/workshop", "Library/Caches", "Library/Logs",
    "DerivedData", ".npm", ".pnpm-store", "pip-cache",
)

# Steam / game libraries → mount, do not copy.
_MOUNT_PARTS = (
    "steamapps", "SteamLibrary", "Steam/steamapps",
    "/data/games", "Games/Steam",
)

# Never copy plaintext. Paths only — no values.
_SECRET_PARTS = (
    ".ssh/id_", ".gnupg", ".aws/credentials", ".netrc",
    "Login Keychain", "login.keychain", "Keychains/",
    "Credential Manager", "Local State",  # chromium OSCrypt key
    ".config/sops", "age/keys.txt",
)

# Omarchy already owns these — defer, do not clobber.
_DEFER_PARTS = (
    ".config/hypr", ".config/omarchy", "stylix",
    ".config/gtk-3.0", ".config/gtk-4.0",
)

# Leftover display-name patterns (Windows + macOS + Linux desktop noise).
_APP_NOISE = (
    "org.freedesktop", "gtk+", "gtk demo", "brightness",
    "color profile", "printer", "preferences", "settings panel",
    ".desktop",
)
_APP_SKIP = (
    "steam", "cyberpunk", "vrchat", "path of exile", "street fighter",
    "appmanifest",
)
_APP_CONTAINER = (
    "adobe", "photoshop", "illustrator", "premiere", "after effects",
    "microsoft office", "word 20", "excel 20", "outlook",
    "autocad", "solidworks",
)
_APP_NO_LINUX = (
    "carenado", "prepar3d", "fsx", "ultimate terrain", "accu-sim",
    "a2a ", "wings of power", "razer cortex", "razer synapse",
    "final cut", "logic pro", "xcode", "testflight",
    "imovie", "garageband", "keynote", "pages.app", "numbers.app",
)
_APP_DEFER = (
    "safari", "preview.app", "finder", "chromium", "firefox",
    "alacritty",
)

_NEEDLE_CAP = 20


def path_verdict(path: str) -> dict:
    """Stamp a path with a skip-ladder verb. Never a package name."""
    raw = path or ""
    p = raw.replace("\\", "/").lower()
    verb = "copy"
    reason = "default: keep user data"
    if any(s.lower() in p for s in _SECRET_PARTS):
        verb, reason = "secret", "credential/key material — do not copy plaintext"
    elif any(s.lower() in p for s in _DEFER_PARTS):
        verb, reason = "defer_omarchy", "Omarchy owns this surface"
    elif any(s.lower() in p for s in _MOUNT_PARTS):
        verb, reason = "mount", "library/install tree — mount, do not copy"
    elif any(s.lower() in p for s in _SKIP_PARTS):
        verb, reason = "skip_redownload", "cache/rebuildable — skip"
    return {
        "path": raw,
        "verb": verb,
        "reason": reason,
        "source": "tables",
    }


def leftover_verdict(name: str, source_os: str = "linux") -> dict:
    """Stamp an unmatched app. Never a package. Fail-open to real_unknown."""
    raw = name or ""
    key = raw.lower()
    verb = "real_unknown"
    reason = "no table hit — review"
    if any(s in key for s in _APP_NOISE):
        verb, reason = "noise", "desktop/portal noise — fold, do not drop"
    elif any(s in key for s in _APP_SKIP):
        verb, reason = "skip", "re-download or Proton/Steam mount"
    elif any(s in key for s in _APP_CONTAINER):
        verb, reason = "containerize", "no native equivalent — Windows/macOS container"
    elif any(s in key for s in _APP_NO_LINUX):
        verb, reason = "no_linux", "no Linux path — keep source OS / dual-boot"
    elif any(s in key for s in _APP_DEFER):
        verb, reason = "defer", "Omarchy already ships an equivalent"
    # macOS .app leftovers that look like Apple-only stay no_linux if unmatched
    if source_os == "macos" and verb == "real_unknown" and key.endswith(".app"):
        if any(s in key for s in ("final cut", "logic", "xcode", "testflight")):
            verb, reason = "no_linux", "Apple-only app"
    return {
        "name": raw,
        "verb": verb,
        "reason": reason,
        "source": "tables",
        "os": source_os,
        "wizard_label": wizard_label(verb),
    }


def classify_paths(paths: list[str]) -> list[dict]:
    return [path_verdict(p) for p in paths]


def classify_leftovers(
    names: list[str],
    source_os: str = "linux",
    use_needle: bool | None = None,
) -> list[dict]:
    """Classify unmatched names. Needle only fills still-unlabeled leftovers."""
    out = []
    for n in names:
        v = leftover_verdict(n, source_os)
        v["wizard_label"] = wizard_label(v["verb"])
        out.append(v)
    want = os.environ.get("OMNIGATE_NEEDLE", "1") != "0" if use_needle is None else use_needle
    if not want:
        return out
    unlabeled = [r for r in out if r["verb"] == "real_unknown"][:_NEEDLE_CAP]
    if not unlabeled:
        return out
    tagged = _needle_leftovers([r["name"] for r in unlabeled], source_os)
    by_name = {t["name"]: t for t in tagged}
    merged = []
    for r in out:
        extra = by_name.get(r["name"])
        if extra and extra.get("verb") in APP_VERBS and extra["verb"] != "real_unknown":
            merged.append(extra)
        else:
            merged.append(r)
    return merged


def _needle_leftovers(names: list[str], source_os: str) -> list[dict]:
    """Optional Needle overlay. Any failure → empty (fail-open)."""
    try:
        from needle import Needle  # type: ignore
    except Exception:
        return []
    weights = Path(__file__).resolve().parent / "needle2.cact"
    if not weights.is_file():
        return []

    def leftover_verb(name: str, verb: str, reason: str = "") -> dict:
        """Classify an unmatched app. verb is skip, defer, containerize, no_linux, noise, or real_unknown. Never a package name."""
        if verb not in APP_VERBS:
            verb = "real_unknown"
        return {"name": name, "verb": verb, "reason": reason or "needle", "source": "needle", "os": source_os}

    try:
        agent = Needle(weights=str(weights), tools=[leftover_verb])
    except Exception:
        return []
    tagged = []
    for name in names:
        try:
            resp = agent.complete(
                f"Unmatched {source_os} app {name!r}. "
                "Call leftover_verb. Never invent a package."
            )
        except Exception:
            continue
        if resp.get("type") != "call":
            continue
        calls = resp.get("function_calls") or []
        if not calls:
            continue
        args = calls[0].get("arguments") or {}
        verb = args.get("verb", "real_unknown")
        if verb not in APP_VERBS:
            continue
        tagged.append({
            "name": name,
            "verb": verb,
            "reason": args.get("reason") or "needle leftover",
            "source": "needle",
            "os": source_os,
        })
    return tagged


def group_leftovers(rows: list[dict]) -> dict[str, list[dict]]:
    """Group leftover stamps. noise is folded, never deleted."""
    groups: dict[str, list[dict]] = {v: [] for v in sorted(APP_VERBS)}
    for r in rows:
        groups.setdefault(r.get("verb", "real_unknown"), []).append(r)
    return groups


# Wizard-facing labels. Internal verb → what the user sees.
WIZARD_LABELS = {
    "skip": "Stays on your old drive (games)",
    "defer": "Omarchy already has this",
    "containerize": "Runs in a Windows box (later)",
    "no_linux": "Windows only — boot Windows",
    "noise": "",  # folded, not shown
    "real_unknown": "Needs a decision",
}


def wizard_label(verb: str) -> str:
    """Map an internal verb to the wizard's label."""
    return WIZARD_LABELS.get(verb, "Needs a decision")

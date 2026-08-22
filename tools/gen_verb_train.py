#!/usr/bin/env python3
"""Generate Needle training JSONL for verb tools (builder-only).

Does not invent packages. Output is gitignored (needle*.jsonl).
Train later with: needle finetune needle_verbs.jsonl --epochs 4
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PATH_EXAMPLES = [
    ("/data/games/steamapps/common/Game", "mount", "Steam library tree"),
    ("C:/Program Files (x86)/Steam/steamapps/common/X", "mount", "Steam library"),
    ("/Users/me/Library/Caches/com.apple.Safari", "skip_redownload", "macOS cache"),
    ("/home/u/Projects/foo/node_modules", "skip_redownload", "rebuildable"),
    ("/Users/me/.ssh/id_ed25519", "secret", "private key"),
    ("/home/u/.gnupg/private-keys-v1.d", "secret", "gpg"),
    ("/home/u/.config/omarchy/theme.css", "defer_omarchy", "Omarchy owns theme"),
    ("/Users/me/Documents/notes.md", "copy", "user documents"),
    ("/Users/me/Pictures/IMG_0001.HEIC", "copy", "user photos"),
    ("/home/u/.cache/huggingface", "skip_redownload", "cache"),
]

APP_EXAMPLES = [
    ("org.freedesktop.impl.portal.desktop", "linux", "noise"),
    ("GTK+ Demo", "linux", "noise"),
    ("Cyberpunk 2077", "windows", "skip"),
    ("VRChat", "windows", "skip"),
    ("Adobe Photoshop 2025", "windows", "containerize"),
    ("Microsoft Office 365", "windows", "containerize"),
    ("Carenado C172N FSX", "windows", "no_linux"),
    ("Final Cut Pro.app", "macos", "no_linux"),
    ("Xcode.app", "macos", "no_linux"),
    ("Logic Pro.app", "macos", "no_linux"),
    ("SomethingNeverSeen 3.2", "linux", "real_unknown"),
]


def main() -> int:
    tools_path = [
        {
            "name": "path_verdict",
            "description": "Skip-ladder verb for a filesystem path. Never a package.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "verb": {
                        "type": "string",
                        "enum": ["mount", "skip_redownload", "copy",
                                 "secret", "defer_omarchy"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["path", "verb"],
            },
        }
    ]
    tools_app = [
        {
            "name": "leftover_verb",
            "description": "Strategy for an unmatched app. Never a package name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "verb": {
                        "type": "string",
                        "enum": ["skip", "defer", "containerize",
                                 "no_linux", "noise", "real_unknown"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["name", "verb"],
            },
        }
    ]
    rows = []
    for path, verb, reason in PATH_EXAMPLES:
        rows.append({
            "query": f"Path {path}. Call path_verdict. Never invent a package.",
            "tools": tools_path,
            "function_calls": [{
                "name": "path_verdict",
                "arguments": {"path": path, "verb": verb, "reason": reason},
            }],
            "reasoning": reason,
        })
    for name, os_name, verb in APP_EXAMPLES:
        rows.append({
            "query": f"Unmatched {os_name} app {name!r}. Call leftover_verb. Never invent a package.",
            "tools": tools_app,
            "function_calls": [{
                "name": "leftover_verb",
                "arguments": {"name": name, "verb": verb, "reason": verb},
            }],
            "reasoning": f"{os_name} leftover → {verb}",
        })
    out = REPO / "needle_verbs.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"Wrote {len(rows)} examples → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

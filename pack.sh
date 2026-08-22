#!/usr/bin/env bash
# pack.sh — build the Omnigate desktop binary (Phase 9).
#
# Linux:  dist/omnigate/omnigate          (runnable here)
# Windows/macOS: run this on that OS with the same repo; flet pack emits
#   Omnigate.exe / Omnigate.app for the host platform.
#
# Prereqs: the .venv-flutter venv (flet 0.86.5). Never commit dist/.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv-flutter/bin"
if [[ ! -x "$VENV/flet" ]]; then
    echo "error: .venv-flutter not found — create it and 'pip install flet'" >&2
    exit 1
fi

rm -rf dist build
"$VENV/flet" pack app.py \
    --product-name "Omnigate" \
    || exit 1

echo
echo "Packed:"
find dist -maxdepth 2 -type f -perm -u+x | head -5

# NixOS note: dist/app is an FHS binary; NixOS has no /usr/lib. Verified
# launch recipe on zephyr (libsecret via our flake, rest from steam-run):
#   LD_LIBRARY_PATH=$(cd /etc/nixos && nix eval --raw \
#     '.#nixosConfigurations.zephyr.pkgs.libsecret.outPath')/lib \
#     steam-run dist/app
# Windows/macOS packs bundle all libs — users never need any of this.

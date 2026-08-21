#!/bin/sh
# omnigate — cross-platform migration to Omarchy (macOS / Linux wrapper).
#
# Finds python3, then delegates to bootstrap.py from the repo root so
# relative imports resolve no matter where this script is invoked from.
# bootstrap.py checks for git and prints install instructions if missing.
#
# Usage:
#   ./omnigate.sh --help
#   ./omnigate.sh export --os macos --out my-setup.zip
#   ./omnigate.sh doctor
#
# Requires: python3 (macOS: `xcode-select --install` or python.org) and git.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v python3 >/dev/null 2>&1; then
    echo "omnigate: no python3 found on PATH." >&2
    echo "" >&2
    echo "  macOS: run \`xcode-select --install\` (provides python3 + git)," >&2
    echo "         or install from https://www.python.org/downloads/macos/" >&2
    echo "  Linux: use your package manager, e.g. \`sudo apt install python3\`." >&2
    exit 3
fi

cd "$SCRIPT_DIR"
exec python3 bootstrap.py "$@"

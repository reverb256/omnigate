#!/bin/bash
# omarchy-migrate — migrate files from your old Windows or Mac
# Part of Omarchy. Routes to the omnigate Python engine.
#
# Usage:
#   omarchy-migrate detect                        — scan for old OS
#   omarchy-migrate export --out ~/old-pc.zip     — build migration package
#   omarchy-migrate import <package.zip>          — restore on Omarchy
#   omarchy-migrate share                         — share setup via QR
#   omarchy-migrate receive <url>                 — pull a friend's setup
set -euo pipefail

OMARCHY_MIGRATE_VERSION="0.2"

# Resolve the omnigate repo root
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(dirname "$SCRIPT_DIR")

# Run a Python omnigate command
run_py() {
    cd "$REPO"
    python3 "$@"
}

case "${1:-}" in
    detect)
        shift
        run_py migrate.py export --os linux --out /dev/null "$@" 2>&1 | head -20
        ;;
    export)
        shift
        run_py bootstrap.py export "$@"
        ;;
    import)
        shift
        run_py bootstrap.py import "$@"
        ;;
    share)
        shift
        run_py bootstrap.py replicate share "$@"
        ;;
    receive)
        shift
        run_py bootstrap.py replicate receive "$@"
        ;;
    *)
        echo "omarchy-migrate v${OMARCHY_MIGRATE_VERSION}"
        echo ""
        echo "Commands:"
        echo "  detect    scan for old OS"
        echo "  export    build migration package"
        echo "  import    restore on Omarchy"
        echo "  share     share your setup via QR"
        echo "  receive   pull a friend's setup"
        echo ""
        echo "Run 'omarchy-migrate <command> --help' for full flags."
        ;;
esac

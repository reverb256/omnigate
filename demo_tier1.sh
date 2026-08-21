#!/usr/bin/env bash
# omnigate Tier 1 — the container demo.
#
# Boots a lightweight Omarchy-flavored container that mounts the user's REAL
# home read-only (so nothing can be changed), launches a terminal with the
# Osaka Jade theme, and shows the "your OS is becoming" experience.
#
# Requirements: podman or docker (auto-detected), a Linux host (or WSL on
# Windows). No KVM. No GUI virtualization. Runs on a 2GB laptop.
set -euo pipefail

RUNTIME="${OMNIGATE_RUNTIME:-$(command -v podman || command -v docker)}"
[ -n "$RUNTIME" ] || { echo "need podman or docker"; exit 1; }

IMAGE="${OMNIGATE_IMAGE:-docker.io/library/archlinux:latest}"   # Omarchy repo image would replace this
MOUNT_POINT="${OMNIGATE_MOUNT:-/home/you}"
REAL_HOME="${HOME}"

echo "== omnigate Tier 1 · container demo =="
echo "runtime: $RUNTIME"
echo "mounting your real home ($REAL_HOME) read-only at $MOUNT_POINT"

# Pull the image if not present (fast for archlinux)
$RUNTIME image inspect "$IMAGE" >/dev/null 2>&1 || $RUNTIME pull "$IMAGE"

# Run the demo container:
#   - bind-mount the real home read-only
#   - launch a bash shell with the Osaka Jade prompt
#   - the user can browse their real files (ls, cat) but NOT modify them
exec $RUNTIME run --rm -it \
  --name omnigate-demo \
  -v "$REAL_HOME:$MOUNT_POINT:ro" \
  -e OMNIGATE_MOUNT="$MOUNT_POINT" \
  -e PS1='\[\e[38;5;42m\]omnigate-demo\[\e[0m\]:\[\e[38;5;34m\]\w\[\e[0m\]\$ ' \
  "$IMAGE" /bin/bash -c '
    echo ""
    echo "  ██████╗ ███╗   ███╗███╗   ██╗██╗ ██████╗  █████╗ ████████╗███████╗"
    echo " ██╔═══██╗████╗ ████║████╗  ██║██║██╔════╝ ██╔══██╗╚══██╔══╝██╔════╝"
    echo " ██║   ██║██╔████╔██║██╔██╗ ██║██║██║  ███╗███████║   ██║   █████╗  "
    echo " ██║   ██║██║╚██╔╝██║██║╚██╗██║██║██║   ██║██╔══██║   ██║   ██╔══╝  "
    echo " ╚██████╔╝██║ ╚═╝ ██║██║ ╚████║██║╚██████╔╝██║  ██║   ██║   ███████╗"
    echo "  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝"
    echo ""
    echo "  Your system is becoming Omarchy."
    echo "  Your real files are mounted read-only at $MOUNT_POINT."
    echo "  Nothing here can change them. Look around."
    echo "  Type:  ls $MOUNT_POINT   to see your real home"
    echo ""
    cd "$MOUNT_POINT"
    exec /bin/bash
  '

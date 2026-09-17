#!/bin/bash
# Apply the fleet sshd baseline + restart-forever drop-in to hosts.
# Usage: ./apply.sh host1 [host2 ...]   (run from a host that can ssh to them)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
for h in "$@"; do
  echo "== $h"
  scp -o BatchMode=yes "$DIR/sshd/12-fleet-sshd.conf" "$DIR/sshd/restart-forever.conf" "$h:/tmp/" >/dev/null
  ssh -o BatchMode=yes "$h" '
    sudo -n install -m 644 /tmp/12-fleet-sshd.conf /etc/ssh/sshd_config.d/12-fleet-sshd.conf
    sudo -n mkdir -p /etc/systemd/system/sshd.service.d
    sudo -n install -m 644 /tmp/restart-forever.conf /etc/systemd/system/sshd.service.d/restart-forever.conf
    sudo -n systemctl daemon-reload
    sudo -n sshd -t && sudo -n systemctl reload sshd
    echo "applied + reloaded"
  '
done

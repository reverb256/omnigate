#!/bin/bash
# Enable/disable Tailscale SSH on the fleet (run from zephyr).
# PREREQUISITE: ACL must be accept-mode (run apply-acl-accept.sh first), or
# tailnet ssh calls will hit the browser-check and automation will stall.
# Usage: ./enable-ts-ssh.sh            # enable all four
#        ./enable-ts-ssh.sh --rollback # disable all four
set -uo pipefail
MODE="${1:-enable}"
HOSTS="sentry nexus forge zephyr"

run_on() {
  if [ "$1" = "zephyr" ]; then bash -c "$2"; else ssh -o BatchMode=yes -o ConnectTimeout=8 "$1" "$2"; fi
}

for h in $HOSTS; do
  echo "== $h ($MODE)"
  if [ "$MODE" = "rollback" ]; then
    run_on "$h" "sudo -n tailscale set --ssh=false 2>&1 | tail -1"
  else
    run_on "$h" "sudo -n tailscale set --ssh --accept-risk=lose-ssh 2>&1 | tail -1"
  fi
  sleep 1
  echo -n "  RunSSH: "; run_on "$h" "tailscale debug prefs 2>/dev/null | grep -o '\"RunSSH\":[^,]*'"
done

echo "-- tnet ssh probe (must print hostnames, not a check URL):"
BAD=0
for h in $HOSTS; do
  out="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$h" hostname 2>&1 | tail -1)"
  echo "  $h -> $out"
  case "$out" in *"tailscale.com"*|*"additional check"*|*timed\ out*) BAD=1;; esac
done
if [ "$BAD" = "1" ]; then
  echo "RESULT: NEEDS-ACL (browser-check intercepted; ACL still check-mode)"
  exit 1
else
  echo "RESULT: ALL-OK"
fi

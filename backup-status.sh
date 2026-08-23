#!/usr/bin/env bash
# Status of the running garage backup.
set -u
LOG=/tmp/rclone-backup.log

echo "=== rclone alive? ==="
ps -eo pid,etime,args | grep "sw/bin/rclone" | grep -v grep | head -1 || echo "NOT RUNNING"

echo
echo "files copied: $(grep -c 'Copied (new)' "$LOG" 2>/dev/null)"

echo -n "excluded junk in log (expect 0): "
grep -cE 'flutter/bin/cache|StabilityMatrix|/target/|[.]rlib|[.]gguf' "$LOG" 2>/dev/null

echo
echo "=== last 3 log lines ==="
tail -3 "$LOG" 2>/dev/null

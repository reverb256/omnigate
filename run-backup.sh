#!/usr/bin/env bash
# Push zephyr /home/j_kro to nexus garage S3, excluding caches/blobs.
# Verified set: ~207k files / ~45.6 GiB (see verify-excludes.sh).
set -u

E=/home/j_kro/Projects/omarchy-migrate/backup-excludes.txt
DEST=garage:backups/zephyr-home-pre-ghost/
LOG=/tmp/rclone-backup.log

# Garage S3 creds live in nexus runtime secrets; pull them at run time so they
# are never written to disk here.
KEY=$(ssh -i /home/j_kro/.ssh/id_ed25519 -o BatchMode=yes -o ConnectTimeout=10 \
        -o IdentitiesOnly=yes -o StrictHostKeyChecking=no j_kro@10.1.1.120 \
        "sudo cat /run/secrets/garage-s3-access-key-id" 2>/dev/null)
SEC=$(ssh -i /home/j_kro/.ssh/id_ed25519 -o BatchMode=yes -o ConnectTimeout=10 \
        -o IdentitiesOnly=yes -o StrictHostKeyChecking=no j_kro@10.1.1.120 \
        "sudo cat /run/secrets/garage-s3-secret-key" 2>/dev/null)

if [ -z "$KEY" ] || [ -z "$SEC" ]; then
  echo "FATAL: could not read garage S3 creds from nexus" | tee -a "$LOG"
  exit 1
fi

export AWS_ACCESS_KEY_ID="$KEY"
export AWS_SECRET_ACCESS_KEY="$SEC"
export RCLONE_S3_ACCESS_KEY_ID="$KEY"
export RCLONE_S3_SECRET_ACCESS_KEY="$SEC"

echo "=== backup start $(date -Is) ===" >> "$LOG"

rclone copy /home/j_kro "$DEST" \
  --exclude-from "$E" \
  --transfers 16 --checkers 32 \
  --s3-chunk-size 16M \
  --retries 3 --low-level-retries 10 \
  --stats 30s --stats-one-line \
  --log-file "$LOG" --log-level INFO

rc=$?
echo "=== backup end $(date -Is) rc=$rc ===" >> "$LOG"
exit $rc

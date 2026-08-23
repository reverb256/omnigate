#!/usr/bin/env bash
# Report total SIZE of the filtered backup set + remaining top dirs.
set -u
E=/home/j_kro/Projects/omarchy-migrate/backup-excludes.txt

echo "=== total size of filtered set ==="
cd /home/j_kro || exit 1
timeout 400 rclone size /home/j_kro --exclude-from "$E" 2>/dev/null

echo
echo "=== remaining top-level dirs by file count (top 15) ==="
awk '{ $1=""; sub(/^ +/,""); print }' /tmp/filtered-list.txt | cut -d/ -f1 | sort | uniq -c | sort -rn | head -15

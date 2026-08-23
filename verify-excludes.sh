#!/usr/bin/env bash
# Verify the rclone exclude rules actually exclude dev caches.
set -u
E=/home/j_kro/Projects/omarchy-migrate/backup-excludes.txt
OUT=/tmp/filtered-list.txt

cd /home/j_kro || exit 1
timeout 300 rclone ls /home/j_kro --exclude-from "$E" 2>/dev/null > "$OUT"
echo "total files WITH filter: $(wc -l < "$OUT")"

for d in ".bun/" ".rustup/" ".npm-global/" ".cache/" "node_modules/" ".venv/" ".git/objects/"; do
  printf '%-18s hits: %s\n' "$d" "$(grep -c -- "$d" "$OUT")"
done

echo "--- critical data present? (expect nonzero) ---"
for d in ".gnupg/" ".pki/" "keyrings/" ".config/zen/" ".ssh/" "Projects/"; do
  printf '%-18s hits: %s\n' "$d" "$(grep -c -- "$d" "$OUT")"
done

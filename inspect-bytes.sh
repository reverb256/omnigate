#!/usr/bin/env bash
# Find what is consuming BYTES in the filtered set (file count is already sane).
set -u
OUT=/tmp/filtered-list.txt

echo "=== top 25 largest individual files in the filtered set ==="
sort -rn "$OUT" | head -25 | awk '{ sz=$1/1024/1024; $1=""; sub(/^ +/,""); printf "%10.1f MiB  %s\n", sz, $0 }'

echo
echo "=== bytes by top-level dir (top 15) ==="
awk '{ sz=$1; $1=""; sub(/^ +/,""); split($0,p,"/"); tot[p[1]] += sz } END { for (d in tot) printf "%12.2f GiB  %s\n", tot[d]/1024/1024/1024, d }' "$OUT" | sort -rn | head -15

#!/usr/bin/env bash
# Inspect what remains in the filtered list: top offenders by top-level dir
# and sample the residual .cache / .venv / .rustup paths.
set -u
OUT=/tmp/filtered-list.txt

echo "=== top-level dirs by file count (top 25) ==="
awk '{ $1=""; sub(/^ +/,""); print }' "$OUT" | cut -d/ -f1 | sort | uniq -c | sort -rn | head -25

echo
echo "=== sample residual .cache paths (10) ==="
awk '{ $1=""; sub(/^ +/,""); print }' "$OUT" | grep -- '\.cache' | head -10

echo
echo "=== sample residual .venv paths (5) ==="
awk '{ $1=""; sub(/^ +/,""); print }' "$OUT" | grep -- '\.venv' | head -5

echo
echo "=== sample residual .rustup paths (5) ==="
awk '{ $1=""; sub(/^ +/,""); print }' "$OUT" | grep -- '\.rustup' | head -5

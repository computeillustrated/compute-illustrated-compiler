#!/bin/bash
# Builds and runs the examples of episode 29 (addresses, records).
# The binaries go to a temporary folder, not into the repository.
set -e
cd "$(dirname "$0")"
OUT="${TMPDIR:-/tmp}/memory_examples"
mkdir -p "$OUT"
cc -O0 -o "$OUT/regions" regions.c
cc -O0 -o "$OUT/record" record.c
echo "== regions"; "$OUT/regions"
echo "== record";   "$OUT/record"

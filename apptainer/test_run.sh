#!/bin/sh
# Smoke test: run one model in the container with a bound /output directory
# and assert that export files were written.
#
# Usage: test_run.sh <sif> <output_dir> [model]
set -eu

sif="$1"
outdir="$2"
model="${3:-steel}"

rm -rf "$outdir"
mkdir -p "$outdir"

apptainer run --bind "$outdir:/output" "$sif" run --model "$model"

if [ -z "$(ls -A "$outdir/$model/export" 2>/dev/null)" ]; then
    echo "FAIL: no export files in $outdir/$model/export" >&2
    exit 1
fi
echo "OK: export files present in $outdir/$model/export"

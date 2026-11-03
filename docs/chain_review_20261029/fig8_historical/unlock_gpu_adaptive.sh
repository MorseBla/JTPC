#!/usr/bin/env bash
set -euo pipefail

GPU="/sys/devices/platform/17000000.gpu/devfreq/17000000.gpu"
GOV="${1:-nvhost_podgov}"

echo "Unlocking GPU DVFS: governor=$GOV"

echo 306000000  | sudo tee "$GPU/min_freq" >/dev/null
echo 1020000000 | sudo tee "$GPU/max_freq" >/dev/null
echo "$GOV"     | sudo tee "$GPU/governor" >/dev/null

echo "--- GPU state ---"
cat "$GPU/governor"
cat "$GPU/min_freq"
cat "$GPU/max_freq"
cat "$GPU/cur_freq"

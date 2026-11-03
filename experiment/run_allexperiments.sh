#!/usr/bin/env bash
# Offline reproduction from the bundled logs; never starts hardware collection.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for section in 6.1 6.2 6.3; do "$HERE/$section/run.sh"; done
cp "$HERE/6.2/Figures/fig7b_power_RTR090.pdf" "$HERE/Figures/fig7b_power_RTR090.pdf"

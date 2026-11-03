#!/usr/bin/env bash
set -euo pipefail

# Output is mW. Thor reads the kernel INA238 VIN input (module + carrier).
case "${1:-legacy}" in
  thor)
    root="${THOR_HWMON_ROOT:-/sys/bus/i2c/devices/2-0044/hwmon}"
    matches=()
    for node in "$root"/hwmon*; do
      [[ -r "$node/name" && -r "$node/label" ]] || continue
      [[ "$(<"$node/name")" == ina238 && "$(<"$node/label")" == VIN ]] || continue
      matches+=("$node/power1_input")
    done
    if [[ ${#matches[@]} -ne 1 ]]; then
      echo "Expected exactly one INA238 VIN sensor under $root" >&2
      exit 1
    fi
    raw="$(<"${matches[0]}")"
    if [[ ! "$raw" =~ ^[0-9]{1,18}$ ]]; then
      echo "Invalid INA238 power value: ${matches[0]}" >&2
      exit 1
    fi
    mw=$((10#$raw / 1000))
    if (( mw <= 0 || mw > 2147483647 )); then
      echo "INA238 power is outside the positive mW range" >&2
      exit 1
    fi
    printf '%s\n' "$mw"
    #printf '%s\n' "$mw" | awk '{print $1 / 1000}'
    ;;
  legacy)
    # head intentionally closes the streaming producer after its first sample.
    set +o pipefail
    LINE=$(sudo tegrastats --interval 1 | head -n 1)
    echo "$LINE" | grep -oP "VDD_CPU_GPU_CV \K[0-9]+"
    #echo "$LINE" | grep -oP "VDD_CPU_GPU_CV \K[0-9]+" | awk '{print $1 / 1000}'
    ;;
  *)
    echo "Usage: $0 [thor|legacy]" >&2
    exit 2
    ;;
esac

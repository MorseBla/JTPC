#!/usr/bin/env bash
set -euo pipefail

DURATION_VAL="120"
GPU_TEMP_LIMIT="52"
RTR="0.85"

POWERS=(11000 11500 12000 12500 13000)

METHODS=(
  "FC-GPU:FC_GPU_main_temp.sh"
  "JTPC:LQR_main_temp.sh"
  "DFS-only:DFS_main_temp.sh"
)

mkdir -p run_stdout/main_temp_power_sweep090_120

cleanup_runtime() {
  cd "$HOME/JPAP 1"
  pkill -f "Scheduler/bin/server" || true
  pkill -f "Scheduler/bin/scheduler" || true
  pkill -f "application/bin/hist" || true
  pkill -f "application/bin/stereo" || true
  pkill -f "application/bin/mm" || true
  sudo pkill -TERM tegrastats 2>/dev/null || true
  sleep 1
  sudo pkill -KILL tegrastats 2>/dev/null || true
}

cooldown() {
  cleanup_runtime
  echo "Cooling down until gpu <= ${GPU_TEMP_LIMIT}C"

  while true; do
    set +e
    line=$(tegrastats --interval 1000 2>/dev/null | head -n 1)
    set -e

    gpu_temp=$(echo "$line" | grep -oE 'gpu@[0-9.]+C' | grep -oE '[0-9.]+' || echo 999)
    echo "gpu_temp=${gpu_temp}C"

    awk -v t="$gpu_temp" -v lim="$GPU_TEMP_LIMIT" 'BEGIN{exit !(t <= lim)}' && break
    sleep 10
  done
}

for entry in "${METHODS[@]}"; do
  METHOD="${entry%%:*}"
  SCRIPT="${entry##*:}"

  for POWER in "${POWERS[@]}"; do
    echo
    echo "============================================================"
    echo "Running $METHOD P=$POWER RTR=$RTR"
    echo "DURATION=$DURATION_VAL"
    echo "============================================================"

    cooldown

    if [[ "$METHOD" == "FC-GPU" ]]; then
      cd "$HOME/JPAP 1"
      ./unlock_gpu_adaptive.sh nvhost_podgov
    fi

    cd "$HOME/JPAP 1/motivation"
    sudo -v

    SP="$RTR $RTR $RTR" POWER="$POWER" DURATION="$DURATION_VAL" ./"$SCRIPT" \
      2>&1 | tee "run_stdout/main_temp_power_sweep090_120/${METHOD}_P${POWER}_SP${RTR}.log"

    cleanup_runtime
  done
done

echo "Power sweep RTR=0.90 completed."

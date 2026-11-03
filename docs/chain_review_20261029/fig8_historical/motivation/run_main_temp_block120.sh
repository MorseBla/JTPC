#!/usr/bin/env bash
set -euo pipefail

DURATION_VAL="120"
GPU_TEMP_LIMIT="52"

POWERS=(11000 11500 12000 12500 13000)
RTRS=(0.70 0.75 0.80 0.85 0.90)

METHODS=(
  "FC-GPU:FC_GPU_main_temp.sh"
  "JTPC:LQR_main_temp.sh"
  "DFS-only:DFS_main_temp.sh"
)

mkdir -p run_stdout/main_temp_block120

cleanup_runtime() {
  cd "$HOME/JPAP 1"

  pkill -f "Scheduler/bin/server" || true
  pkill -f "Scheduler/bin/scheduler" || true
  pkill -f "application/bin/hist" || true
  pkill -f "application/bin/stereo" || true
  pkill -f "application/bin/mm" || true
  sudo pkill -f "tegrastats" || true
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
    echo "THERMAL BLOCK START"
    echo "METHOD=$METHOD"
    echo "SCRIPT=$SCRIPT"
    echo "POWER=$POWER"
    echo "DURATION=$DURATION_VAL"
    echo "RTRS=${RTRS[*]}"
    echo "============================================================"

    cooldown

    for R in "${RTRS[@]}"; do
      echo
      echo "------------------------------------------------------------"
      echo "Running $METHOD P=$POWER RTR=$R"
      echo "------------------------------------------------------------"

      if [[ "$METHOD" == "FC-GPU" ]]; then
        cd "$HOME/JPAP 1"
        ./unlock_gpu_adaptive.sh nvhost_podgov
      fi

      cd "$HOME/JPAP 1/motivation"
      sudo -v

      SP="$R $R $R" POWER="$POWER" DURATION="$DURATION_VAL" ./"$SCRIPT" \
        2>&1 | tee "run_stdout/main_temp_block120/${METHOD}_P${POWER}_SP${R}.log"

      # kill leftover tegrastats from the wrapper, but do not cool between RTRs
      sudo pkill -f "tegrastats --interval 1000" || true
      sleep 3
    done

    echo "THERMAL BLOCK DONE: $METHOD POWER=$POWER"
  done
done

cleanup_runtime

echo "All thermal blocks completed."

#!/usr/bin/env bash

# Local layout: preserve runtime relative paths, write new captures separately.
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$HERE/../../.." && pwd)"
cd "$PROJECT_ROOT/experiment"
set -euo pipefail

APP_DIR="../application"     
SCHED_DIR="../Scheduler"     

# Share system_identification_2's INA238 VIN reader; POWER and readings are mW.
#export JPAP_POWER_BACKEND="${JPAP_POWER_BACKEND:-thor}"
export JPAP_POWER_BACKEND="${JPAP_POWER_BACKEND:-tegrastats}"
if [[ "$JPAP_POWER_BACKEND" == thor ]]; then
  initial_power_mw="$(bash "$PROJECT_ROOT/scripts/get_power.sh" thor)"
  echo "Thor INA238 VIN power (module + carrier): ${initial_power_mw} mW"
fi

LOG_ROOT="${HERE}/../runs/JTPC"

# Available workloads
workloads=(
  #particle
  #quasi
  hist
  stereo
  mm
  #bfs
)

# Generate all unique 3-workload combinations
combinations=()
for ((i=0; i<${#workloads[@]}; i++)); do
  for ((j=i+1; j<${#workloads[@]}; j++)); do
    for ((k=j+1; k<${#workloads[@]}; k++)); do
      combinations+=("${workloads[i]} ${workloads[j]} ${workloads[k]}")
    done
  done
done

#default_rates=(0.060 0.100 0.060)
#default_rates=(0.160 0.080 0.0600)
default_rates=(0.020 0.005 0.010)
duration="${DURATION:-120}"
#duration=120
duration=300

# Direct-sysfs actuator settings for JTPC/LQR.
# Defaults mimic the old sudo set_gpu_freq.sh path: no LQR-command shaping,
# but wait for the physical devfreq state after each write.
export GPU_ACTUATION_CONFIRM_COUNT="${GPU_ACTUATION_CONFIRM_COUNT:-1}"
export GPU_SIGMA_PERIOD_MS="${GPU_SIGMA_PERIOD_MS:-1}"
export GPU_POWER_DEADBAND_MW="${GPU_POWER_DEADBAND_MW:-0}"
export GPU_RTR_GUARD_MARGIN="${GPU_RTR_GUARD_MARGIN:-0}"
export GPU_RTR_UP_GUARD_MARGIN="${GPU_RTR_UP_GUARD_MARGIN:-0}"
export GPU_RTR_DROP_GUARD_MARGIN="${GPU_RTR_DROP_GUARD_MARGIN:-0}"
export GPU_RTR_GUARDED_DOWN_STEP_MHZ="${GPU_RTR_GUARDED_DOWN_STEP_MHZ:-0}"
export GPU_FREQ_CMD_MAX_STEP_MHZ="${GPU_FREQ_CMD_MAX_STEP_MHZ:-0}"
export GPU_FREQ_CMD_MAX_UP_STEP_MHZ="${GPU_FREQ_CMD_MAX_UP_STEP_MHZ:-0}"
export GPU_FREQ_CMD_MAX_DOWN_STEP_MHZ="${GPU_FREQ_CMD_MAX_DOWN_STEP_MHZ:-0}"
export GPU_ACTUATION_WAIT_FOR_CUR_FREQ="${GPU_ACTUATION_WAIT_FOR_CUR_FREQ:-1}"
export GPU_ACTUATION_WAIT_MAX_STEPS="${GPU_ACTUATION_WAIT_MAX_STEPS:-100}"
export GPU_ACTUATION_WAIT_STEP_MS="${GPU_ACTUATION_WAIT_STEP_MS:-20}"

FC_GPU=1
N_PLUS_ONE=2
LQR=3
DFS=7
solution=3

# One RTR value applies to every task; a list supplies one value per task.
#SP="${SP:-0.90 0.90 0.90}"


# Edit this list: one complete experiment per power target, in this order (mW).
power_setpoints=(
  30000  # 30 W
  32000 # 20 W
  34000 # 10 W
  36000 # 10 W
  38000 # 10 W
)
power_setpoints=(
  28000  # 30 W
  29000  # 30 W
  30000  # 30 W
  31000  # 30 W
  32000  # 30 W
)
power_setpoints=(
  30000  # 30 W
)

# Preserve the existing optional single-target environment-variable override.
if [[ -n "${POWER:-}" ]]; then
  power_setpoints=("$POWER")
fi
if (( ${#power_setpoints[@]} == 0 )); then
  echo "ERROR: power_setpoints must contain at least one target in mW" >&2
  exit 1
fi
for power_mw in "${power_setpoints[@]}"; do
  if [[ ! "$power_mw" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: invalid power target '$power_mw'; use positive integer mW" >&2
    exit 1
  fi
done

#setpoint_combos=(
#  "$SP"
#)
setpoint_combos=(
    "0.90 0.90 0.90"
    "0.85 0.85 0.85"
    "0.80 0.80 0.80"
    "0.75 0.75 0.75"
    "0.70 0.70 0.70"
)
# -----------------------------
# Helpers
# -----------------------------
cleanup_shared_memory() {
  echo "Cleaning shared memory segments and related PIDs..."

  # Get shm segments created by this user
  ipcs -m | awk -v user="$USER" '
    NR>3 && $3==user {print $2}
  ' | while read -r shmid; do
      [[ -n "${shmid:-}" ]] || continue
      echo "Removing shm segment $shmid"
      ipcrm -m "$shmid" 2>/dev/null || true
  done

  echo "Killing processes attached to those shm segments..."

  ipcs -m -p | awk -v user="$USER" '
    NR>3 {print $2, $3, $4}
  ' | while read -r shmid cpid lpid; do
      # Kill only if PID belongs to current user
      for pid in "$cpid" "$lpid"; do
        if [[ "$pid" =~ ^[0-9]+$ ]] && ps -o user= -p "$pid" 2>/dev/null | grep -q "$USER"; then
          echo "Killing PID $pid"
          kill -9 "$pid" 2>/dev/null || true
        fi
      done
  done
}

cleanup_tasks() {
  echo "Killing running tasks/server (if any) and cleaning shared memory..."
  pkill -9 -f './t[0-9]$' 2>/dev/null || true
  pkill -9 -f './server$' 2>/dev/null || true
  pkill -9 -f './scheduler$' 2>/dev/null || true
  cleanup_shared_memory

  echo "Clearing logs/figures in current experiment folder..."
  rm -rf ./figures/* 2>/dev/null || true
  mkdir -p "$LOG_ROOT" ./figures
}

compile_tasks() {
  local index=1
  echo "Compiling workloads from: $APP_DIR/"
  make -C $APP_DIR EXTRA_FLAGS="-DJetson"
  #for task_name in "$@"; do
  #  local src="${APP_DIR}/${task_name}.cu"
  #  [[ -f "$src" ]] || { echo "ERROR: missing workload: $src" >&2; exit 1; }

  #  echo "Compiling $task_name as t$index..."
  #  if [[ "$task_name" == "dxtc" ]]; then
  #    nvcc -o "t$index" "$src" \
  #      -I ../Common/ -I ../Samples/5_Domain_Specific/dxtc/ \
  #      -L ../Common/ -lcudart -DT$index -DJetson -std=c++17
  #  else
  #    nvcc -o "t$index" "$src" \
  #      -I ../Common/ -L ../Common/ -lcudart -DT$index -DJetson -std=c++17
  #  fi
  #  ((index++))
  #done
}

compile_server() {
  echo "Compiling controller from: $SCHED_DIR/"
  # This Makefile does not track flags; rebuild the Jetson power-reader branch.
  make -B -C "$SCHED_DIR" EXTRA_FLAGS="-DJetson" #-DCLAMP_PERIODS -DBOUND=50
  #local src="${SCHED_DIR}/controller.cc"
  #local src2="${SCHED_DIR}/scheduler.cc"
  #[[ -f "$src" ]] || { echo "ERROR: missing controller: $src" >&2; exit 1; }
  #[[ -f "$src2" ]] || { echo "ERROR: missing scheduler: $src2" >&2; exit 1; }
  #g++ "$src" -o server -std=c++17 -lrt -pthread -I /usr/include/eigen3 -DJetson #-DCLAMP_PERIODS -DBOUND=50
  #g++ "$src2" -o scheduler -std=c++17 -lrt -pthread 
}

run_combination() {
  local ps_set="$1"
  shift
  local -a workloads=("$@")
  local num_tasks="${#workloads[@]}"

  # Build rates array sized to num_tasks (fallback to 0.300 if not provided)
  local -a rates=()
  for ((i=0; i<num_tasks; i++)); do
    rates+=("${default_rates[i]:-0.300}")
  done

  # Optional: adjust rate if dxtc present
  if [[ " ${workloads[*]} " == *" dxtc "* ]]; then
    rates[0]=0.600
  fi

  local comb_name
  comb_name=$(printf "%s" "${workloads[*]}" | tr ' ' '_')
  local comb_log_dir="${LOG_ROOT}/${comb_name}"
  mkdir -p "$comb_log_dir"

  echo "Running: ${workloads[*]}"
  echo "Power target: ${ps_set} mW"
  echo "Rates:   ${rates[*]}"
  echo "Logs at: $comb_log_dir"

  for sp_line in "${setpoint_combos[@]}"; do
   
    read -r -a setpoints <<< "$sp_line"

    if (( ${#setpoints[@]} == 1 && num_tasks > 1 )); then
      local shared_sp="${setpoints[0]}"
      local task_index
      for ((task_index=1; task_index<num_tasks; task_index++)); do
        setpoints+=("$shared_sp")
      done
      # Keep output names consistent with the actual per-task targets.
      sp_line="${setpoints[*]}"
    fi
    
    if [[ "${#setpoints[@]}" -ne "$num_tasks" ]]; then
      echo "ERROR: setpoints '$sp_line' has ${#setpoints[@]} values but num_tasks=$num_tasks" >&2
      exit 1
    fi
    
    local sp_dir="${comb_log_dir}/setpoint_${ps_set}_$(echo "$sp_line" | tr ' ' '_')"
    mkdir -p "$sp_dir"
    
    local scheduler_bin="../Scheduler/bin/scheduler"
    local app_bin_dir="../application/bin"
    
    local -a args=("$num_tasks" "$sp_dir" "$solution" "$duration" "$ps_set")
    
    for ((i=0; i<num_tasks; i++)); do
      #echo $workloads
      taskname="${workloads[i]}"   # should contain bfs, hist, mm, particle, quasi, stereo
      args+=("${app_bin_dir}/${taskname}" "${rates[i]}" "${setpoints[i]}")
    done
    
  echo "Executing: sudo -n env ... stdbuf -oL -eL ${scheduler_bin} ${args[*]}"
  sudo -n tegrastats --interval 1000 > "${sp_dir}/tegrastats_temp.log" 2>&1 &
  TEGRA_TEMP_PID=$!
  set +e
  sudo -n env \
    PATH="$PATH" \
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
    JPAP_POWER_BACKEND="${JPAP_POWER_BACKEND:-}" \
    INA260_I2C_DEV="${INA260_I2C_DEV:-}" \
    INA260_I2C_ADDR="${INA260_I2C_ADDR:-}" \
    GPU_DEVFREQ_PATH="${GPU_DEVFREQ_PATH:-}" \
    GPU_DIRECT_ACTUATION_LOG="${GPU_DIRECT_ACTUATION_LOG:-}" \
    GPU_ACTUATION_CONFIRM_COUNT="${GPU_ACTUATION_CONFIRM_COUNT}" \
    GPU_ACTUATION_MIN_INTERVAL_MS="${GPU_ACTUATION_MIN_INTERVAL_MS:-}" \
    GPU_SIGMA_PERIOD_MS="${GPU_SIGMA_PERIOD_MS}" \
    GPU_POWER_DEADBAND_MW="${GPU_POWER_DEADBAND_MW}" \
    GPU_RTR_GUARD_MARGIN="${GPU_RTR_GUARD_MARGIN}" \
    GPU_RTR_UP_GUARD_MARGIN="${GPU_RTR_UP_GUARD_MARGIN}" \
    GPU_RTR_DROP_GUARD_MARGIN="${GPU_RTR_DROP_GUARD_MARGIN}" \
    GPU_RTR_GUARDED_DOWN_STEP_MHZ="${GPU_RTR_GUARDED_DOWN_STEP_MHZ}" \
    GPU_FREQ_CMD_MAX_STEP_MHZ="${GPU_FREQ_CMD_MAX_STEP_MHZ}" \
    GPU_FREQ_CMD_MAX_UP_STEP_MHZ="${GPU_FREQ_CMD_MAX_UP_STEP_MHZ}" \
    GPU_FREQ_CMD_MAX_DOWN_STEP_MHZ="${GPU_FREQ_CMD_MAX_DOWN_STEP_MHZ}" \
    GPU_ACTUATION_WAIT_FOR_CUR_FREQ="${GPU_ACTUATION_WAIT_FOR_CUR_FREQ}" \
    GPU_ACTUATION_WAIT_MAX_STEPS="${GPU_ACTUATION_WAIT_MAX_STEPS}" \
    GPU_ACTUATION_WAIT_STEP_MS="${GPU_ACTUATION_WAIT_STEP_MS}" \
    stdbuf -oL -eL "${scheduler_bin}" "${args[@]}"
  RUN_STATUS=$?
  set -e
  sudo pkill -TERM -x tegrastats 2>/dev/null || true
  sleep 1
  sudo pkill -KILL -x tegrastats 2>/dev/null || true
  wait "$TEGRA_TEMP_PID" 2>/dev/null || true
  sudo chown -R "$USER:$USER" "$sp_dir" 2>/dev/null || true
  if [[ "$RUN_STATUS" -ne 0 ]]; then exit "$RUN_STATUS"; fi
 
  done

  sleep 5
}

# -----------------------------
# Main
# -----------------------------
cleanup_tasks
compile_server

echo "Generated ${#combinations[@]} 3-workload combinations:"
for comb in "${combinations[@]}"; do
  echo "  $comb"
done

for comb in "${combinations[@]}"; do
  read -r -a task_array <<< "$comb"
  compile_tasks "${task_array[@]}"
  for power_mw in "${power_setpoints[@]}"; do
    run_combination "$power_mw" "${task_array[@]}"
  done
done

echo "All task combinations completed."

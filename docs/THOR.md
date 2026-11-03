# Thor Whole-System Power Adapter

Target: `agx-thor@100.118.13.42`, project `/home/agx-thor/JTPC`.
Device inspection: NVIDIA Jetson AGX Thor Developer Kit, aarch64, Jetson Linux R39.2.1, CUDA 13.2.86. The actual carrier sensor is **INA238**, not INA286. Its `name` is `ina238`, `label` is `VIN`, and current node is `/sys/bus/i2c/devices/2-0044/hwmon/hwmon5/power1_input`. The hwmon number is discovered each invocation rather than fixed.

## Read power

```bash
cd /home/agx-thor/JTPC
bash scripts/get_power.sh thor
```

The command prints one positive integer in **mW**. The kernel input is **uW**, divided by 1000 with sub-mW truncation. VIN covers overall system input, including module and carrier board; it is not GPU-only power or AC wall-plug power. Existing driver settings and limits are not modified. Sensor name and VIN label must match; missing, ambiguous, invalid, or nonpositive input returns an error without a numeric substitute.

No Common/Thor directory or new kernel module is needed. The script uses the already installed kernel hwmon driver. `THOR_HWMON_ROOT` can override the hwmon parent for testing; leave it unset on the target. Running without the `thor` argument retains the historical tegrastats VDD_CPU_GPU_CV behavior, which is a different measurement boundary.

References: [NVIDIA Thor system power measurement](https://docs.nvidia.com/jetson/archives/r38.2.1/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonThor.html#system-power-measurement) and [Linux hwmon ABI](https://origin.kernel.org/doc/html/latest/hwmon/sysfs-interface.html). The NVIDIA page describes an earlier software release; device paths/name/label were independently checked on this R39 target.

## Controller integration

`JPAP_POWER_BACKEND=thor` selects `returnpowerrtx()` → `bash ../scripts/get_power.sh thor`. The existing controller working-directory contract is `experiment/`. Both monitoring threads share a mutex-protected sample for 100 ms (at most 10 shell invocations per second), avoiding a shell launch on the response monitor's approximately 1 ms loop.

The Thor backend accepts valid values above the old 20 W rejection threshold and does not add GPU_SHELL_EQUIV_POWER_MW. Other power backends keep their previous behavior. Startup validates one sensor read before device actuation. Read errors do not silently become 0 W, 11 W, or another component's power. A later failure is fatal to the controller and can bypass normal logging/shared-memory cleanup; graceful experiment restoration is not established by this adapter.

The selector must reach the controller environment. Existing hardware wrappers do not all preserve this variable through sudo, so exporting it alone is not a validated launch procedure for every experiment.

## Build and tests

The target lacked Eigen headers; `libeigen3-dev` was installed. Build with the target's own compiler, not copied x86 binaries:

```bash
cd /home/agx-thor/JTPC
make -B -C Scheduler EXTRA_FLAGS=-DJetson
make -B -C application NVCC=/usr/local/cuda/bin/nvcc EXTRA_FLAGS='-DJetson -arch=sm_110' -j2
python3 tests/test_thor_power.py -v
```

Use `-B` because the existing Scheduler Makefile does not track changed build flags. The test suite uses fake sysfs trees and fake legacy commands; it compiles and calls the actual controller power function and sampling loop without starting scheduler tasks or touching device controls. It covers units, hwmon renumbering, wrong/missing/duplicate sensors, malformed values, legacy streaming output, controller errors, shared caching, and the 20 W/offset behavior.

The local x86 `.venv` is excluded from deployment. Offline plotting on Thor requires a separately created compatible Python environment; the project logs, figures, paper, source, and English documentation are copied.

## Scope of this deployment

This prepares power measurement and deploys the project; it does **not** establish Thor closed-loop experiment readiness. Existing GPU paths (`17000000.gpu` versus Thor `gpu-gpc-0`), frequency tables, model coefficients, task periods/setpoints, wrapper environment propagation, and runs-to-logs selection still require platform adaptation and validation. Do not launch old collection entries on Thor as if they were already ported. No workload experiments, GPU clock changes, power-mode changes, or sensor-limit writes are part of this deployment.

Verification evidence, test output, transfer hashes, and deployment results are stored under `docs/thor_power_20261029/`. Original edited files are backed up outside the project in `../JTPC_sources_20261029/thor_power_before_20261029/`.

## Verified deployment result (2026-10-29)

- Deployed to `/home/agx-thor/JTPC` on `100.118.13.42`; original package contained 6,225 files, all matching SHA256. The final transfer manifest also includes the later build/test/smoke evidence.
- Native controller and dispatcher builds passed. All seven CUDA workloads compiled for sm_110 with CUDA 13.2. The particle source emitted five unused-function warnings; no build errors.
- All 13 tests passed locally and on Thor. Tests exercised fixture-based 125 W values as well as low-power values; no 125 W workload was run on hardware.
- Eight live read sets via the script and compiled controller function succeeded. Script values: 14,460–15,804 mW; controller function values: 15,532–16,150 mW. Raw, script, and controller values were sequential reads of a changing sensor, not simultaneous accuracy/calibration comparisons.
- Before/after settings matched: 120 W nvpmodel mode, GPU min/max 315/1386 MHz, governor nvhost_podgov, INA238 power1_max 167936000 uW.
- No CUDA workloads or closed-loop experiments were launched. Binary hashes and exact samples are in hardware_smoke.json.

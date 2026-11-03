# JTPC profiling and independent model checks on Jetson AGX Thor

All additions are isolated here. Existing experiments and feedback controllers
are unchanged. **The development host is not Thor. No target experiments have
been executed as part of implementation.** The suite never starts a feedback
controller or invokes old experiment wrappers.

Read [UNITS.md](UNITS.md) before interpreting coefficients. The checkout's PDF,
requested analytical equations, and controller coordinates disagree. B is
explicitly unresolved (`B: null`); profiling, alpha fitting, independent step
capture, and offline analysis are provided. No response/rate coefficients are
empirically refitted to hide that discrepancy.

## Prerequisites and configuration

On Thor: the repository's CUDA-capable Jetson installation, C++17 nvcc with
`sm_110` support, Python 3.10+, POSIX semaphores, readable INA238 VIN and GPU
temperature (sysfs or the installed tegrastats utility), and permission to write GPU devfreq min/max. No Jetson packages,
power modes, fan controls, sensor limits, or thermal protection are changed.
Offline plots use matplotlib and numpy from the repository requirements;
analysis calculations use Python's standard library.

Edit `system_identification_2/config.json` before capture. Default tasks are the
repository's hist/stereo/mm combination, with original sizes, two kernel passes,
launch geometry, input generation, allocations and global per-job serialization.
Workers get a private semaphore namespace; no controller shared memory is used.
See [WORKERS.md](WORKERS.md). Each task's `workload_parameters` configures
histogram elements/bins, matrix dimension, or stereo width/height/disparity.
Rebuild with the same `--config` after changing these values: only the generated
worker constants change. The original application files remain intact. A build
manifest records parameters, commands, source and binary hashes; capture rejects
stale built-in workers whose parameters/binary disagree with that manifest. Other worker commands
may be configured if they implement the documented protocol. The built-in adapter
supports these three existing tasks.

Default physical rates correspond to existing periods .160/.080/.060 seconds.
They are starting settings, **not demonstrated feasible on Thor**. Lower all
rates if profiling/backlog checks indicate overload, then use the same revised
config for alpha and validation. Record ambient temperature when available,
cooling policy, external workloads and intended operating range in config.
The controller interval defaults to the current source's 2 seconds. Warmup is
20 invocations, measured profiling 300 per task. Alpha uses a 10 s discard,
60 s measurement, three repeats, reproducibly shuffled seed 2941, and periodic
reference returns. Configure longer windows for slow tasks or thermal settling.
Ten seconds is a discard policy, not a claim of thermal equilibrium.

## Commands from repository root

Local development checks, all hardware independent:

```text
python3 -m compileall -q system_identification_2
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 -m unittest discover -s system_identification_2 -p 'test_*.py' -v
python3 system_identification_2/build_workers.py --dry-run
python3 system_identification_2/suite.py profile --dry-run
python3 system_identification_2/suite.py alpha --dry-run
python3 system_identification_2/suite.py validate --dry-run
```

Dry-run exits before subprocess launch, device inspection, directory creation,
or hardware writes. It prints configured commands, arguments, rates, settings,
and target frequency-selection rules; it cannot list target OPPs on this host.
Synthetic unit-test results are distinct from experimental results and use
throwaway temporary directories, never an experimental result path.

On **Jetson AGX Thor only**, with all other test tasks/controllers stopped:

```text
python3 system_identification_2/build_workers.py --cuda /usr/local/cuda/bin/nvcc
python3 system_identification_2/suite.py preflight --target-thor
sudo python3 system_identification_2/suite.py profile --target-thor
sudo python3 system_identification_2/suite.py alpha --target-thor
sudo python3 system_identification_2/suite.py validate --target-thor
```

Use `--config system_identification_2/config.json` (the default) or an explicitly
saved alternate config for every mode. Root is generally needed only for min/max
writes; run with the permissions appropriate to your target. Capture prints a
fresh result path immediately. Substitute that exact path below; analyze each
capture independently on Thor or a non-Jetson machine:

```text
sudo python3 system_identification_2/suite.py analyze --run system_identification_2/results/ACTUAL_PROFILE_RUN
sudo python3 system_identification_2/suite.py analyze --run system_identification_2/results/ACTUAL_ALPHA_RUN
sudo python3 system_identification_2/suite.py analyze --run system_identification_2/results/ACTUAL_VALIDATE_RUN
```

The sudo prefix above permits writing analysis beside sudo-owned target captures.
For copies owned by your local user, omit sudo; no Jetson dependency is needed.

Analysis produces human-readable and machine-readable reports and an unresolved
model record, including alpha when sufficient data exist. No GPU build is needed
for offline postprocessing. Keep all three run directories with their own config
and provenance; do not combine different reference points, workloads, cooling
policies, power channels or rates as one analytical model.

## Target preflight and frequency selection

Preflight is target-only and read-only for hardware: it inspects device-tree Thor
identity, GPU devfreq levels/bounds/governor, GPU temperature, INA238 VIN, fan
PWM/RPM snapshots and `nvpmodel -q`. It also rejects known controller/task process
names without signaling them. This name check is not a comprehensive GPU process
inventory: ensure your target has no unrelated GPU jobs or MPS server active.

The preferred Thor clock domain is `/sys/class/devfreq/gpu-gpc-0` only when it is
actually present. Otherwise discovery requires one unambiguous GPU domain; set
`frequency.devfreq_path` if necessary. Automatic temperature discovery tests each GPU thermal node's actual value;
a present node returning `ENODATA` is recorded as unavailable. If exactly one GPU
node is readable, it is selected. If none is readable, `temperature_backend=auto`
tries the `gpu@...C` field of one owned `tegrastats` process. No CPU/SoC field is
substituted. Capture keeps this process alive, saves its timestamped raw output,
rejects readings older than `temperature_max_age_s` (default 2 s), and stops/reaps
only that process on cleanup. Preflight starts and reaps a separate telemetry-only
probe. It launches no CUDA workloads and changes no hardware controls.

Set `telemetry.temperature_path` for an explicit millidegree-Celsius sensor;
explicit paths fail rather than silently switching sources. More than one readable
GPU node requires an explicit selection. `temperature_backend` may be `auto`,
`sysfs`, or `tegrastats`; clear `temperature_path` when forcing tegrastats. The
selected source and failed-node diagnostics appear in preflight output and saved
metadata. If tegrastats needs elevated read permissions, retry preflight with
`sudo python3 system_identification_2/suite.py preflight --target-thor`.
A GPU thermal node returning ENODATA plus tegrastats showing only `cpu@`, `tj@`
and `soc...@` means GPU temperature is unavailable in that inspection. Those
other fields and `VDD_GPU` power are not GPU temperature substitutes. Preflight
now returns its full report with `temperature_C: null`, source `unavailable`,
and `capture_ready: false`, rather than aborting the entire inspection. This is
not necessarily a permissions problem, and no CUDA workload is launched to probe it.

Capture still requires working temperature monitoring by default. To explicitly
collect demand/power/frequency while GPU temperature is unavailable, add
`--allow-missing-temperature` to each capture command (or set
`telemetry.allow_missing_temperature: true`). This opt-out is saved in the run
config, every missing temperature remains null, and analysis warns that thermal
drift/throttling cannot be assessed. A numeric alpha regression can be computed
from otherwise adequate trials, but is not thermally validated. B remains
unresolved. If a working source was selected and subsequently fails or becomes
stale, capture still aborts; this flag does not hide runtime sensor failures.

For example, only if you accept those measurement limitations:

```text
sudo python3 system_identification_2/suite.py profile --target-thor --allow-missing-temperature
sudo python3 system_identification_2/suite.py alpha --target-thor --allow-missing-temperature
sudo python3 system_identification_2/suite.py validate --target-thor --allow-missing-temperature
```

Missing frequency levels still fails explicitly, without guessed Orin clocks.

The reference is an interior supported level closest to the arithmetic midpoint
of the configured `range_hz` (ties choose lower). With one or two levels, select
from the available set. `reference_hz` overrides selection and must be legal.
Selection stays within the saved min/max bounds to respect the existing power-mode
operating range. Adjust power mode yourself before preflight if needed.
Automatic alpha selection samples up to five supported levels spanning that
range; explicit `levels_hz` must be supported. Every profile uses the same
selected reference. Selection is deterministic from saved levels/config; compare
`preflight.json` across capture directories to ensure the same reference.
If just one level is exposed, standalone capture remains available; alpha will
report that distinct achieved points are insufficient, rather than assume more
levels exist. A two-level fit has limited linearity evidence; prefer 3–5.

The existing `scripts/set_gpu_freq.sh` and controller actuator hard-code
`17000000.gpu`. Calling them on Thor would fail or select the wrong domain.
The isolated `Clock` adapter retains their min/max locking interface with a
discovered Thor path and safe bound-write ordering. It leaves the governor intact,
uses no dithering, snapshots original bounds before writes, and restores them.
No existing shared file needed modification. Requested and actual frequency are
recorded; mismatch/throttling symptoms must be reviewed, not relabeled as the
requested operating point. Thermal protections remain enabled.

## Power, timing, scheduling, and interpretation

The default channel reuses `bash scripts/get_power.sh thor`, which verifies
INA238 name and VIN label under `2-0044/hwmon` and discovers hwmon numbering.
It measures **overall module plus carrier input**, not GPU-only or AC wall power.
Kernel uW are truncated to helper mW, then converted to W. This matches the
controller only when `JPAP_POWER_BACKEND=thor`; the historical combined
VDD_CPU_GPU_CV backend is different. Do not combine those signals. A different
verified channel may be configured with an argv command, scale, precise label,
and controller-match declaration; use it consistently for alpha and validation.

Each process initializes once, signals READY, and completes each requested GPU
invocation before accepting another. CUDA events are synchronized and checked;
initialization and initial host/device transfers are outside timing. Hist's
per-pass bin reset precedes the event as in the source. Raw event sums, source
carry response, actual release/completion times, and wall response remain separate.
Event time excludes the global semaphore wait, so contention visible in wall
response can be missing from the controller-style response. See UNITS.md.

Standalone uses one task at a time and no queued invocations. Concurrent modes
use fixed absolute periodic releases, independent process streams, one outstanding
invocation per task, and the same semaphore policy. This absolute release policy
is explicit: the old launcher sleeps relative to dispatch, which can drift under
load. Late jobs are logged; growing backlog aborts at the configured bound, rather
than silently dropping releases or filling an unlimited queue. Achieved rates and
adequacy must be inspected. A completed capture is not necessarily usable data.

Validation defaults to nominal, one neighboring supported frequency step,
individual +3% rate steps with nominal returns, then combined steps and returns.
Set `validation.sequence` to a list of `{frequency_hz, rates_hz}` objects to
specify exact bounded operating points. Frequency steps are discrete; even a
neighbor can be too large for a local linearization. Review the generated plan.
Every step has a discard and steady window while raw transition traces remain.
No automatic validity verdict is made. Unresolved B prevents claimed numerical
B validation; measured settled deltas and interval summaries remain inspectable.

All configured output roots must be inside system_identification_2.
Outputs include unique UTC/UUID directories, config, launch plan, source/binary
hashes, revision when available (this checkout may have no Git metadata), device
settings, monotonic raw jobs/telemetry, requested/achieved frequencies,
complete/incomplete status, cleanup outcome, profiles, trial summaries, fit
residuals/uncertainty, model status, validation comparisons, and plots. Alpha uses
one time-weighted power/frequency mean per steady trial; individual telemetry
samples are not independent repetitions. The intercept is fitted freely and is
not a measured physical idle power. Negative slopes and poor fits remain visible.

## Interruption and recovery

Normal exit, exceptions, SIGINT and SIGTERM stop/reap only this suite's child
process groups, close/unlink its private semaphore, and restore saved clock bounds.
Raw data survive; interruptions remain incomplete. Cooling and power modes are
never altered. Worker timeouts bound failed-job waits. SIGKILL/power loss cannot
guarantee cleanup. After ensuring no suite workers remain, restore from the
exact interrupted directory on Thor:

```text
sudo python3 system_identification_2/suite.py reset --target-thor --run system_identification_2/results/ACTUAL_INTERRUPTED_RUN
```

Reset restores saved min/max only and signals no processes. Check cleanup.json
and the target bounds afterward. Do not reset while another experiment owns the
clock. If orphan workers remain after SIGKILL, use the saved process information
to terminate only those workers before reset; never use broad `pkill` commands.

## Diagnose a release-lateness abort

The original error `Accumulating backlog: mm` meant a single completed job's
release-to-completion time exceeded its period plus `safety.max_lateness_s`.
It did not by itself demonstrate a trend. The current runner retains the same
limit but reports `Release lateness limit exceeded` with task, window, requested
frequency/rate, execution time, dispatch lateness, wall time and limit. Raw timings
and incomplete status remain available; no automatic rate or threshold relaxation
is performed.

From the project root, inspect the recorded failed run without launching anything:

```text
python3 system_identification_2/diagnose_backlog.py system_identification_2/results/20261031T001207Z_alpha_6be76db8
```

Replace the directory for future failures. This read-only command works on a
non-Jetson host too. No build or sudo is required when result files are readable.
It reports per-task count, mean execution versus wall time, release dispatch
lateness, first/last excess past the period, and sampled event-time demand
`sum(rate_hz * mean_execution_s)`. Because the suite serializes GPU work per job,
a value >=1 indicates observed mean event demand already exceeds available time
at those requested rates. A value <1 does not prove feasibility: reset/lock/host
overheads, transients and unsampled frequencies remain. Wall-minus-event time is
not a direct measurement of semaphore wait.

Use complete standalone profiles and these diagnostics to choose a feasible
fixed rate set and intended frequency range; use the same revised config across
alpha and validation. Rates inherited from old experiments are not Thor-calibrated.
Avoid raising the lateness limit solely to make an overloaded sweep finish.
Changing rates requires no worker rebuild when workload sizes are unchanged.

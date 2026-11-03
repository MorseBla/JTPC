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

## Conservative configuration after the supplied Thor overload trace

The supplied partial reference-window diagnostic at **requested** 846 MHz had
mean event demands 59.025 ms (hist), 22.235 ms (stereo), 24.829 ms (mm). At rates
6.25/12.5/16.667 Hz, their serialized event-time demand sum was 1.06067 s/s,
before reset/host/lock overhead. MM's first/last ten-sample mean excess grew from
about 1.4 ms to 405.5 ms. This is evidence of overload and growing release delay,
not a slow MM invocation alone. The diagnostic does not establish achieved clock
or thermal stability; these remain separate checks.

`config.conservative.json` preserves workloads and safety limits, halves all
nominal rates to hist=3.125 Hz (period .32 s), stereo=6.25 Hz (.16 s),
mm=8.333333333333334 Hz (.12 s), and explicitly selects reference 846 MHz.
It restricts the intended sweep to supported points at or above that reference,
within the existing min/max bounds. Its `range_hz: [846000000, null]` uses the
highest currently permitted level as the upper endpoint. No upper frequency is
assumed. If fewer than two achieved operating levels remain, alpha cannot be
identified over this range. Default config.json remains unchanged.

The estimated event demand at the **same measured per-job demands** is 0.53033
s/s. This is a conservative starting point, not demonstrated feasibility or a
full overhead estimate. The sweep and validation still stop at the original
lateness limit and retain achieved-frequency checks. A fit using this config
applies only to its lower fixed rates and selected frequency range.

After copying updated suite.py and config.conservative.json to Thor, run from
the project root. No worker rebuild is needed because workload parameters are
unchanged. The missing-temperature flag keeps your previous explicit opt-out:

```text
python3 system_identification_2/suite.py preflight --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py profile --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py alpha --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py validate --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
```

Keep original failed captures. No rates are changed during a run; compare all
new results under this saved configuration. Missing GPU temperature still limits
thermal assessment, and B remains unresolved.

## Alternative: smaller workloads at the original rates

To reduce demand by changing workload size instead of rate, use `config.json`,
not `config.conservative.json`. Edit each task's `workload_parameters` and retain
its original `rate_hz`. Histogram exposes `num_elements` and `num_bins`, stereo
exposes width/height/disparity bounds, and matrix multiplication exposes
`matrix_n`. No sizes are changed automatically. Size changes affect work and
memory access differently; do not assume a fixed percentage reduction in size
produces that percentage reduction in execution time.

Rebuild with the revised config before capture:

```text
python3 system_identification_2/build_workers.py --config system_identification_2/config.json --cuda /usr/local/cuda/bin/nvcc
```

Then run preflight, profile, alpha and validation with `--config
system_identification_2/config.json` and your existing explicit
`--allow-missing-temperature` option. Exact commands are in run.sh. Use the same
new sizes for every stage and collect fresh measurements. Existing old-size
profiles and alpha estimates remain historical data. This changes only generated
workers, not the original application sources. Sufficient headroom still needs
verification on Thor; lowering measured demand just below one leaves no allowance
for host/reset/locking overhead.

## Further size reduction for the 315 MHz endpoint

The user-supplied `20261031T002820Z_alpha_a08683a5` diagnostics show that revised
workload sizes completed one reference capture at requested 846 MHz (event-demand
sum 0.49678), but overloaded at requested 315 MHz (partial event-demand sum
1.33419). These diagnostics alone do not verify achieved frequencies, a complete
alpha sweep, temperature stability, or model validity. Keep the original rates
when pursuing the selected workload-size approach.

A starting sizing target is roughly half the **current** per-task execution
demand at the low-frequency endpoint, giving an estimated event-demand sum
0.66710 if those reductions materialize. For the present kernels, possible
heuristics are histogram `num_elements` times 0.5, stereo width and height each
times sqrt(0.5) (~0.7071), and matrix `matrix_n` times cbrt(0.5) (~0.7937), rounded
to valid positive integers. Leave histogram bins and stereo disparity bounds
unchanged for this comparison. These are algorithmic work-scaling heuristics,
not measured execution-time laws: GPU occupancy, launch geometry, memory behavior
and fixed overhead can change the result. Apply factors to the target's current
config, not the original larger sizes. No sizes or rates are automatically changed.

The exact revised target sizes were not included in the supplied diagnostics, so
this checkout's default config is not presumed to contain them. Inspect the
current configuration on Thor, edit the selected sizes, rebuild using that same
config, and repeat profile/alpha/validation. The full command sequence is in
run.sh. Keep previous captures intact and retain safety limits. All frequencies
included in alpha must sustain the fixed task set; passing only the reference
window does not establish that.

## Offline review and system-validation figure (copied complete experiment)

The complete target captures copied on 2026-10-31 are under
`system_identification_2/system_identification_2/results`. This nested copy is
preserved in place. Root `plot2.py` is the style reference and remains unchanged.
Run from the project root (Python with numpy/matplotlib; no CUDA build):

```text
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/plot_validation.py --results system_identification_2/system_identification_2/results
```

The script creates a new `system_identification_2/review_<UTC>_<suffix>` directory.
`--output-dir PATH` selects a new output directory; overwrites are refused.
It prints the partial B and implied C, verifies matching config/build manifests
and copied binary/generated-source hashes, checks raw files remain unchanged,
and writes review.md, review.json, raw_sha256.json, matrices.txt/matrices.json,
validation_plot_data.json and PNG/PDF figures. `system_validation.pdf` matches
the dual-axis average-response/VIN style of root plot2.py, with data-adaptive
bands that preserve all points. Supplementary per-task, input-step, interval,
profile and alpha/drift plots retain detail hidden by the average.

Unlike the reference script's validation-data regressions, this plot uses the
separate alpha sweep and conditional analytical frequency response `-q0/f0`.
The nominal response/power point is the first validation window. B is **partial**:
physical rate cross-coefficients stay unknown, known zeros remain assumptions,
and curves are masked when changed inputs require unknown entries. No full B
or controller update is produced. Rows use [ms, ms, ms, W], input increments
[Hz, Hz, Hz, MHz]. The figure is a nominal operating-point comparison using
2-second completion bins, not a full one-interval state-prediction score.
`C=I` is printed only as the implied output mapping for `y=x` in matching units;
no separately identified C was found in this checkout.

The first review is at `review_complete_20261031/review.md`. Captures completed
without raw errors, with usable GPU temperatures and exact requested clocks.
Important limits: histogram standalone time changes from about 10.66 to 16.33 ms
within measurement, and alpha has R² about 0.72 with roughly 1.16 W reference
power variation. These issues and unresolved B units prevent an unqualified
model-validity conclusion. See the review for details and all source paths.

## Periodic staircase / trapezoid-shaped validation

The recovered `JTPC_system_validation/validation_control_period.csv` contains
120 two-second intervals: six frequency levels from 510 to 1020 MHz, four
intervals per hold, ascending/descending staircases repeated three times. The
flat sections and sloped transitions in the response/power plot come from this
input schedule. They cannot be recreated from the different input sequence of
the recent Thor validation run by changing the plotting style.

Reproduce the archived measurements offline (no build; numpy and matplotlib):

```text
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/plot_legacy_periodic.py
```

Its fitted curves reproduce the old same-data regressions and are labeled
**descriptive fits**, not independent new-Thor model validation. Source CSV
hashes and power unit conversion (mW to W) are recorded. Historical rail scope
is not established by this aggregate CSV; it is not relabeled as Thor VIN.
B/C are unavailable from that aggregate CSV. The source and old figures remain
unchanged.

For a new Thor test, `config.periodic.json` is derived from the completed target
alpha capture, retaining your actual reduced sizes: histogram 4,096,000 elements,
stereo 640x480 and MM N=700, with original 6.25/12.5/16.667 Hz rates. It uses
supported Thor levels 315/531/747/954/1170/1386 MHz, eight seconds per hold,
three cycles, plus two eight-second reference holds at 846 MHz. The first is
warmup; the second checks the reference operating point without recalibrating the saved model. Total requested
hold duration is 256 s plus runner transition/bracketing overhead. The normal
frequency/rate/backlog/cleanup checks remain active. No dithering is introduced.

Copy config.periodic.json to Thor. No worker rebuild is needed if those workload
parameters still match the active build. From the repository root on Thor:

```text
python3 system_identification_2/suite.py validate --config system_identification_2/config.periodic.json --dry-run
sudo python3 system_identification_2/suite.py validate --target-thor --config system_identification_2/config.periodic.json --allow-missing-temperature
```

This is an additional experiment; it has not been run locally. Actual response
shape is measured, not prescribed, and VIN power can remain noisy. A wide
frequency staircase also tests limitations of a local linear approximation.
Do not force a trapezoid by rearranging/synthesizing measured data.

After capture, plot the new run using the frozen model from the previous analysis:

```text
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/periodic_validation.py plot --run system_identification_2/results/ACTUAL_PERIODIC_RUN --model system_identification_2/identification_model.json
```

Use the actual copied periodic run path on this machine. The plot excludes the
declared initial warmup window, preserves raw records, prints the saved partial
B and implied C, and saves system_validation.png/pdf plus per-task/input plots.
All coefficients AND nominal q/P offsets are loaded unchanged from
identification_model.json; no periodic data are used to fit or recalibrate them. Unknown
cross-rate coefficients stay unresolved. The observation matrix convention and
partial-B limitations described above remain in effect.

To plan a different supported range or number of holds from a saved target
preflight/config, without touching hardware:

```text
python3 system_identification_2/periodic_validation.py plan --source-run system_identification_2/system_identification_2/results/20261031T011547Z_alpha_aedb2a4b --cycles 3 --levels 6 --hold-intervals 4 --out system_identification_2/config.periodic_alternate.json
```

`--low-hz`/`--high-hz` restrict the selected supported levels. `--dry-run` prints
without writing. Existing config/output paths are never overwritten; current
Thor preflight revalidates every requested level before capture.

## Use the frozen model from the previous identification/analysis

`identification_model.json` is a portable, frozen export of
`review_complete_20261031/matrices.json` plus the recorded training configuration
and source checksums. It contains the **previously obtained partial model**, not
a new full identification. B's unresolved cross-rate entries remain null, and
C=I remains the stated direct-state observation convention. Alpha and the nominal
q/P values retain their previously reported quality limitations and provenance;
q0/P0 came from the earlier small-step validation nominal window, not Equation(3)
or the new periodic test.

The periodic plot command now requires `--model` instead of `--alpha-run`:

```text
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/periodic_validation.py plot --run system_identification_2/results/ACTUAL_PERIODIC_RUN --model system_identification_2/identification_model.json
```

The new periodic capture supplies only measured outputs and achieved inputs.
The script does not rerun alpha fitting, derive a new B frequency column, adjust
intercepts, or recalibrate q0/P0 to the new nominal window. The actual frequency
delta is relative to the saved 846 MHz reference. Unknown rate effects remain
masked; held inputs do not add the same increment again. The initial reference
hold is retained as a measurement/check only.

`frozen_model.py` checks workload sizes, nominal rates, channel/units, resources,
interval, state/input order and the trained alpha frequency range. It rejects
incompatible captures instead of silently adapting the model. Output includes
an unchanged copy of the saved matrices and `model_provenance.json` with the
loaded model file SHA256 and `recalibrated_on_periodic_data: false`. No CUDA build
is needed for this offline change.

### Connected periodic lines

The plotting module uses solid connected curves for measured/estimated outputs.
At excluded transition bins with otherwise complete measured telemetry/task
outputs, it joins the adjacent valid plotting vertices. This changes display
only: raw data, excluded-bin flags, model coefficients and error scores remain
unchanged. True missing readings and unresolved rate effects still break a curve.
The plotting JSON records this display convention. The connected plot for
20261031T193235Z_validate_9dd3dac8 is in
periodic_plot_20261031T194704Z_ba3c02/system_validation.png (and .pdf).

### Longer holds and explicit plot averaging

`config.periodic.long.json` extends every frequency hold to60seconds, retaining
three cycles, actual reduced workloads, task rates and2-second controller interval.
The32holds take1920seconds (32minutes) plus transition overhead. This gives more
samples per plateau; it is not a claim that60seconds guarantees thermal settling.
Use the exact target command in run.sh. No worker rebuild is needed.

`periodic_validation.py plot --plot-bin-seconds 10` averages recorded outputs
into10-second display bins using timestamp-aware integration for power/frequency
and completed-job response means. The captured data, frozen model and native
controller interval remain unchanged. summary.json retains native2-second data;
validation_plot_data.json labels its display bin duration and aggregation-specific
errors. Axes distinguish plot bins from control periods. Bins crossing input
changes are excluded from statistics, with connecting display segments as already
documented. Actual missing data are not filled. The option is rejected if its
bin duration is shorter than the control interval or longer than a frequency hold.

Longer holds and averaging help compare plateau means; they do not establish the
cause of VIN fluctuations. Earlier alpha reference means already varied by about
1.16W despite60-second windows. A GPU-focused rail would need verified measurement
scope and fresh alpha identification/validation; the current frozen VIN model
must not be applied to another rail. Also, the response-frequency B column is a
local linearization near846MHz. Longer data cannot repair its systematic error
across315–1386MHz. A narrower supported range near the nominal point tests local
model accuracy, but has a smaller power change relative to VIN noise.

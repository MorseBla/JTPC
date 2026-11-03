# Local verification, 2026-10-30

This development machine is not Jetson AGX Thor. No CUDA compiler was invoked,
GPU work launched, Jetson device probed, clock/fan/power mode changed, or software
installed. Target compilation and measurements remain unverified.

Passed:

- `python3 -m compileall -q system_identification_2`
- `MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 -m unittest discover -s system_identification_2 -p 'test_*.py' -v` (17 tests)
- `python3 system_identification_2/build_workers.py --generate-only` (source transformation only)
- `python3 system_identification_2/build_workers.py --dry-run`
- `python3 system_identification_2/suite.py profile --dry-run`
- `python3 system_identification_2/suite.py alpha --dry-run`
- `python3 system_identification_2/suite.py validate --dry-run`
- Existing `verify.verify()` offline asset/syntax checks: 6,067 assets, 15 Figure
  7(b) groups and 10 PDFs. Its sole output write was redirected with a Python
  mock from `docs/verification.json` to this folder's
  `repository_verification.json`; existing artifacts were not overwritten.

Tests use synthetic fixtures, temporary ordinary files, and mocked workers and
clock controls. They check weighted integration, gaps/invalid samples, profile
completeness and warmup exclusion, regression and units, input ordering,
nonrepeated actuator deltas, completion-bin alignment, validation comparisons,
no-write/no-launch dry runs, source-derived worker preservation/configurable
sizes, frequency selection, full-window frequency holds, and cleanup on failure.
Synthetic tests do not establish GPU timing, target feasibility, actual frequency
holds, calibrated power measurements, thermal behavior, or model validity.

All implementation files and reports are under `system_identification_2`.
No Git metadata is present in this checkout, so a Git diff/revision was unavailable.
The source manifest integrity check passed; existing shared files were not edited.
The runtime preserves the same absence explicitly as a null revision.

## Temperature preflight correction

The user supplied Thor nvcc output compiling all three workers with unused-symbol
warnings, followed by an ENODATA error reading the selected GPU thermal node.
Those logs demonstrate target compilation, not successful workload execution.

Updated suite.py and test_suite.py to validate thermal-node readings, preserve
per-node diagnostics, and use an owned streaming tegrastats GPU-only temperature
field when automatic sysfs discovery yields no readable GPU sensor. Explicit
sensor paths fail closed; stale/exited streams are rejected. Configuration and
run instructions document backend selection and freshness limits. Worker source
and binaries are unchanged by this correction.

Local verification: 21 hardware-independent tests passed, including mocked ENODATA,
a readable alternate GPU node, tegrastats GPU parsing (no CPU substitution),
explicit-path failure, stale/exited monitor rejection, and existing capture cleanup
and dry-run tests. Python syntax and explicit preflight dry run passed. The fix
has not been exercised on Thor here; no workloads or hardware controls were used.

## Missing GPU-temperature field on the target

The next supplied Thor trace showed readable tegrastats output containing CPU,
TJ and SoC temperatures, but no gpu@...C field. The GPU sysfs node still returned
ENODATA. Preflight now reports that availability limitation as null temperature,
source diagnostics and capture_ready=false, rather than failing the entire
read-only inspection. It does not infer the cause or launch GPU work to probe it.

Capture is strict by default. An explicit --allow-missing-temperature flag (saved
in config) permits capture with null GPU temperature and unavailable thermal
assessment. Analysis can fit otherwise adequate power/frequency data, retains
invalid/missing temperature status, and emits warnings rather than claiming
thermal validation. Existing selected sensor failures/staleness still abort.

Local verification: 26 hardware-independent tests, Python syntax checks, preflight
dry run, and opt-out profile dry run passed. Regression fixtures include the
exact supplied no-GPU-temperature line, null-safe plots/analysis, capture gating,
and no-process missing-temperature readers. No Thor controls or workloads were
used. Target behavior after this correction remains unverified locally.

## Release-lateness diagnostics

The supplied target alpha run aborted on the old `Accumulating backlog: mm`
message. Source review establishes that this guard tests one release-to-completion
threshold crossing, not an observed accumulation trend. It now reports structured
job/window/frequency/rate values while retaining the original stop threshold.
Added a read-only diagnose_backlog.py for old and new raw runs, distinguishing
observed execution demand, wall time and dispatch lateness without changing rates
or fitting B. Actual failed-run timings were not available on this local machine;
no target-specific rate recommendation or root cause is asserted.

Local verification: all 28 suite tests passed, including synthetic diagnostic
records and truncated-record reporting; Python syntax checks passed. No target
workloads or hardware controls were used. No worker rebuild is required.

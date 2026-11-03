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

## Conservative configuration from the user's target diagnostic

The supplied 20261031T001717Z_alpha_46f0cb8b diagnostic provides partial task
means with total event demand 1.06066733 s/s at the original rates and requested
846 MHz. This supports overload under the source's per-job serialized scheduling;
MM's increasing excess also demonstrates growing release delay. No new target
execution is claimed. Added config.conservative.json with unchanged workloads,
half rates, explicit 846 MHz reference and a supported-level range with no
assumed upper OPP. Added nullable range bounds to suite.py; all min/max/safety
checks stay in place. The predicted 0.53033 event-demand sum is only a sizing
estimate at unchanged observed demands, not validated target feasibility.

Local verification: all 29 suite tests, Python syntax, and conservative alpha
no-hardware dry run passed. New tests cover fixed rates, unchanged workload
parameters, supported-level filtering, missing reference, one-level limitations,
validation bounds and reversed frequency ranges. No CUDA compilation or local
hardware experiments were performed.

## Copied complete experiment review and system-validation figure

Reviewed the profile/alpha/validate captures under
system_identification_2/system_identification_2/results. All three status records
are complete; cleanup records have no errors. Saved configs and build manifests
match across runs; copied binaries and generated sources match their manifest
hashes. All 53 top-level raw capture files were SHA256-checked before/after review
and remained unchanged. Root plot2.py was read as the visual reference and not
edited. No target binaries or hardware commands were run locally.

Implemented plot_validation.py and validation_figures.py with matrix exports,
reference-style dual-axis completion-bin validation plot, per-task plots, input
steps, alpha/drift and profile figures. B_full remains null; B_partial prints
unresolved cross-rate entries as ?. Resolved/conditional frequency entries use
ms/MHz and separate alpha uses W/MHz. The implied C=I is labeled y=x output
mapping, not an identified matrix. Unknown contributions are masked and held
inputs are not repeatedly accumulated. The main figure is an operating-point
comparison at two-second aggregation, not a full one-interval model score.

Final artifacts: system_identification_2/review_complete_20261031, containing
review.md/json, matrices.txt/json, raw_sha256.json, validation_plot_data.json,
10 PNG and 10 PDF figures. Visually inspected system_validation.png, individual
output panels, input-step plots, profile plots, and alpha/reference drift plots.
All PDF headers are valid. Full suite: 34 hardware-independent tests passed;
Python compileall passed. Two subagents independently audited the copied data;
one also implemented the plotting module, which the primary reviewed/corrected.

Key findings: 300 measured invocations/task, alpha 0.0020584784 W/MHz with
R2=0.72084, and a histogram profile regime change (first/last 50 means
10.6603/16.3338 ms). VIN reference means span 1.1645 W. These limitations and
unresolved cross-rate normalization prevent a full-B validity claim.

## Periodic staircase reconstruction and new Thor plan

Inspected JTPC_system_validation/plot2.py, the provided example PNG, controller
sources and validation_control_period.csv. The CSV establishes 120 two-second
intervals, four per frequency hold, six levels (510..1020 MHz) and three repeated
ascending/descending cycles. plot_legacy_periodic.py reproduced the archived
measurements and same-data regressions in legacy_periodic_figure_20261031 as
PNG/PDF with recorded source hash. Historical rail scope is not inferred; these
are archived measurements, not a newly executed Thor validation. B/C cannot be
identified from the aggregate CSV and remain unavailable in that reproduction.

Added periodic_validation.py and config.periodic.json using the actual completed
Thor run's config/preflight. The plan preserves hist4096000/stereo640x480/mm700
and nominal rates, selects legal315/531/747/954/1170/1386MHz, holds8s per step,
adds initial warmup and nominal reference holds at846MHz, then three cycles.
Total requested holds=256s, with runner overhead additional. Existing suite.py
custom-sequence capture, frequency mismatch checks, backlog limits and cleanup
are reused without changing shared/controller files. New periodic data plotting
uses separate alpha measurements, prints partial B and implied C, and does not
refit validation data. The initial warmup is excluded only in the plotting view;
raw records stay intact. No periodic Thor capture was launched here.

Local verification:38 suite tests passed (including archived actual-CSV rendering,
source preservation, cycle shape/frequency legality, fixed rates, size retention,
no-overwrite and dry-plan tests), compileall passed, explicit suite validate
--dry-run with config.periodic.json passed. Inspected the reproduced PNG visually.
One subagent implemented the archived plot/test module; primary implemented and
integrated the new capture plan and plotting entry point.

## Frozen prior model for periodic plotting

Changed periodic_validation.py plot to require --model identification_model.json.
It no longer reruns alpha fitting or constructs a new B frequency column and
nominal state from the periodic capture. identification_model.json freezes the
previous review_complete_20261031/matrices.json exactly, plus training config,
source checksums and limitations. Frozen values include alpha0.0020584784332285354
W/MHz, f0=846MHz, q0=[16.336371164957683,1.7430238293011984,
3.5913252792358397]ms and P0=22.11711515774291W. Nominal q/P provenance is the
previous small-step validation nominal window; no new periodic data are used.
B remains partial and C remains the implied direct-state identity map.

Added frozen_model.py and tests for compatibility, task/unit ordering, dimensions,
finite parameters, frequency domain and portable source provenance. Updated
validation_figures.py to honor frozen offsets in both window and interval views.
Outputs include model_provenance.json with model SHA256 and explicit no-
recalibration flag. Old --alpha-run plotting syntax is superseded in run.sh/README.
One subagent implemented the loader and focused tests; primary integrated the
plotting path and immutable artifact.

Verification:46 standard-library unittest tests passed, compileall passed, and
loading the artifact against config.periodic.json verified that its matrix is
exactly equal to the previous review export. Regression tests perturb the new
measured baseline and verify predictions/matrix exports remain unchanged. No
periodic target run or hardware controls were used locally.

## Connected periodic plotting curves

Updated validation_figures.py with display-only connected plotting vertices across
excluded, otherwise complete transition bins. Source records and numeric metrics
are not filled/interpolated or changed. True missing/unknown model terms still
remain gaps. Changed predicted and measured VIN styles to solid connected lines.
Added a regression test proving retained real gaps and unchanged input values.
All47 tests passed; Python syntax passed. Regenerated actual copied periodic run
20261031T193235Z_validate_9dd3dac8 using unchanged frozen model SHA256
2a7a10ca111e9e166d23ecce9304be403d33dcc5c74e3d499b6f6cfb44f2927d.
Visually checked system_validation.png in periodic_plot_20261031T194704Z_ba3c02.
No new workload or hardware control was executed. No subagents spawned for this
bounded plotting correction.

## Longer periodic test and display-bin option

Prepared config.periodic.long.json with unchanged task sizes, rates, controller
interval and frequency sequence, extending holds to60seconds (32minutes nominal).
Added --plot-bin-seconds for separately labeled, timestamp-aware display averages.
Native2-second summaries remain saved; frozen model offsets/coefficients are not
changed. Regression tests verify long holds preserve task settings and display
aggregation uses a separate config without modifying native timing/model values.
Local full suite48tests passed, syntax checks passed, and explicit long-config
validate dry run passed. No long target test was executed locally. No subagents
were spawned for this bounded addition.

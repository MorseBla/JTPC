JTPC profiling suite - plain-text instructions, not an executable shell script.
Start from the repository root. Do not run Thor commands on the development host.

Local verification (Python 3.10+; matplotlib for synthetic plot checks):
python3 -m compileall -q system_identification_2
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 -m unittest discover -s system_identification_2 -p 'test_*.py' -v
python3 system_identification_2/build_workers.py --dry-run
python3 system_identification_2/suite.py profile --dry-run
python3 system_identification_2/suite.py alpha --dry-run
python3 system_identification_2/suite.py validate --dry-run

On Jetson AGX Thor only: configure system_identification_2/config.json first.
Requires installed CUDA nvcc supporting sm_110, Python 3.10+, POSIX semaphores,
readable INA238 VIN and GPU temperature, writable GPU devfreq min/max.
Stop other controllers/test workloads yourself. No automatic power/fan changes.
Build persistent workers; this is the only required build step:
python3 system_identification_2/build_workers.py --cuda /usr/local/cuda/bin/nvcc

Read-only target hardware preflight; resolve any ambiguous paths in config:
python3 system_identification_2/suite.py preflight --target-thor

Capture standalone demand at common reference, then fixed-rate alpha, then steps:
sudo python3 system_identification_2/suite.py profile --target-thor
sudo python3 system_identification_2/suite.py alpha --target-thor
sudo python3 system_identification_2/suite.py validate --target-thor

Each capture prints its unique result directory. Replace the ACTUAL_* placeholders
with those printed paths. Postprocessing runs on any machine with Python and
matplotlib; no CUDA build is needed for analysis. The sudo prefix is for
sudo-owned target captures; omit it for local result copies owned by your user.
sudo python3 system_identification_2/suite.py analyze --run system_identification_2/results/ACTUAL_PROFILE_RUN
sudo python3 system_identification_2/suite.py analyze --run system_identification_2/results/ACTUAL_ALPHA_RUN
sudo python3 system_identification_2/suite.py analyze --run system_identification_2/results/ACTUAL_VALIDATE_RUN

Model construction is deliberately unresolved (B=null); read UNITS.md.
These commands cannot prove identification/validation without usable target data.

Manual reset on Thor after SIGKILL/power loss, once suite workers are stopped:
sudo python3 system_identification_2/suite.py reset --target-thor --run system_identification_2/results/ACTUAL_INTERRUPTED_RUN

Temperature preflight recovery (workers need no rebuild for this fix):
Update suite.py, then retry from the project root:
python3 system_identification_2/suite.py preflight --target-thor
If GPU sysfs returns ENODATA and tegrastats has no gpu@...C field, preflight now
reports temperature unavailable and capture_ready=false. cpu/tj/soc fields and
VDD_GPU power are not substituted as GPU temperature. No rebuild is needed.
Default capture remains blocked without GPU temperature. Only if you explicitly
accept missing thermal-drift/throttling assessment, use these capture commands:
sudo python3 system_identification_2/suite.py profile --target-thor --allow-missing-temperature
sudo python3 system_identification_2/suite.py alpha --target-thor --allow-missing-temperature
sudo python3 system_identification_2/suite.py validate --target-thor --allow-missing-temperature
The opt-out is saved and missing temperatures remain null. A numeric alpha fit
may be produced but is not thermally validated. B remains unresolved.

Offline diagnosis after a release-lateness/backlog abort (no build or sudo needed):
python3 system_identification_2/diagnose_backlog.py system_identification_2/results/20261031T001207Z_alpha_6be76db8
Use the actual run path for future failures. The report preserves execution vs
wall response and sampled load; it does not change rates, thresholds, or hardware.
Use complete profiles plus this report to choose fixed rates/frequency range
for a new run. Keep the same rates throughout alpha and validation.

Conservative fixed-rate retry after the supplied 1.06067 event-demand overload:
Copy updated suite.py and config.conservative.json; workers need no rebuild.
Start from the repository root. Rates become hist 3.125 Hz, stereo 6.25 Hz,
mm 8.333333333333334 Hz. Reference=846 MHz; sweep supported levels >=846 MHz
within existing clock bounds. This is a starting configuration, not validated
feasibility. Alpha requires at least two distinct achieved levels.
python3 system_identification_2/suite.py preflight --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py profile --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py alpha --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py validate --target-thor --config system_identification_2/config.conservative.json --allow-missing-temperature
Use this same fixed configuration throughout. Keep the lateness limit intact.

Alternative selected: reduce workload sizes while keeping original nominal rates.
Use config.json, not config.conservative.json. Edit task workload_parameters:
hist: num_elements and/or num_bins; stereo: width/height and/or disparity bounds;
mm: matrix_n. Leave rate_hz unchanged for this experiment. Choose sizes explicitly;
no sizes have been changed automatically. Rebuild after editing sizes:
python3 system_identification_2/build_workers.py --config system_identification_2/config.json --cuda /usr/local/cuda/bin/nvcc
python3 system_identification_2/suite.py preflight --target-thor --config system_identification_2/config.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py profile --target-thor --config system_identification_2/config.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py alpha --target-thor --config system_identification_2/config.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py validate --target-thor --config system_identification_2/config.json --allow-missing-temperature
Keep the same revised workload sizes throughout profiling, alpha and validation.
Old profiles/alpha belong to the old sizes; preserve them but do not reuse their
estimates for this workload. Original application sources stay unchanged.

Next sizing pass for the supplied revised-size 315 MHz overload:
Observed event demand: 0.49678 at requested 846 MHz; 1.33419 at requested 315 MHz.
Keep task rates fixed. As a starting heuristic, target about half the current
execution demand: hist num_elements *0.5; stereo width and height each *0.7071;
mm matrix_n *0.7937. Round to positive integers. Keep bins/disparity unchanged.
These factors do not guarantee proportional runtime or feasible scheduling.
Inspect the CURRENT TARGET config first (the revised sizes were not supplied):
python3 -c 'import json; c=json.load(open("system_identification_2/config.json")); print(json.dumps({t["name"]:t["workload_parameters"] for t in c["tasks"]}, indent=2))'
After editing workload_parameters, rebuild and collect fresh data from project root:
python3 system_identification_2/build_workers.py --config system_identification_2/config.json --cuda /usr/local/cuda/bin/nvcc
sudo python3 system_identification_2/suite.py profile --target-thor --config system_identification_2/config.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py alpha --target-thor --config system_identification_2/config.json --allow-missing-temperature
sudo python3 system_identification_2/suite.py validate --target-thor --config system_identification_2/config.json --allow-missing-temperature
Do not copy the local default config over your revised target sizes.

Offline copied-result review and system-validation plot, from project root:
No CUDA build, target access, or hardware execution is needed. Requires matplotlib.
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/plot_validation.py --results system_identification_2/system_identification_2/results
This prints partial B (?=unresolved), and C=I implied by y=x, not an identified C.
It writes a NEW review directory containing system_validation.png/pdf, detailed
per-task/input/profile/alpha plots, matrices.txt/json and review.md/json.
The existing completed review is system_identification_2/review_complete_20261031.
--output-dir PATH may choose a new folder; existing folders are never overwritten.
Raw captured data and root plot2.py are preserved. No empirical full-B refitting
is substituted for the unresolved analytical rate coefficients.

Periodic frequency staircase / trapezoid-shaped experiment, from project root:
Reproduce the historical CSV offline (numpy/matplotlib; no build):
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/plot_legacy_periodic.py
This uses archived measurements and same-data descriptive fits, not new Thor data.

New Thor periodic capture: copy config.periodic.json to the target. Its workload
sizes are hist4096000 / stereo640x480 / mm700, with original nominal rates.
No worker rebuild if these sizes still match your active binaries. Supported
levels315/531/747/954/1170/1386MHz;8seconds/hold;3cycles;256seconds plus overhead.
python3 system_identification_2/suite.py validate --config system_identification_2/config.periodic.json --dry-run
sudo python3 system_identification_2/suite.py validate --target-thor --config system_identification_2/config.periodic.json --allow-missing-temperature

After capture, use the real printed run directory and the saved model artifact:
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/periodic_validation.py plot --run system_identification_2/results/ACTUAL_PERIODIC_RUN --model system_identification_2/identification_model.json
The first reference hold is warmup; the next is a measured reference check.
All model coefficients and nominal offsets come unchanged from the saved artifact.
Plots print partial B and implied C without fitting or recalibrating on this run. Current captured validation was not
periodic and cannot be relabeled as this new experiment.

Use the PREVIOUS identification/analysis model unchanged for periodic plotting:
No build required. Requires Python, numpy, matplotlib. Keep these updated files
together: periodic_validation.py, frozen_model.py, validation_figures.py, and
identification_model.json. Set the actual periodic capture path below:
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/periodic_validation.py plot --run system_identification_2/results/ACTUAL_PERIODIC_RUN --model system_identification_2/identification_model.json
The old --alpha-run plotting option is replaced by --model. Coefficients, q0,
P0 and f0 are frozen from the prior review. New periodic measurements are NOT
used to refit or recalibrate. B remains partial; C=I is the implied output map.

Regenerate connected-line plots for the copied periodic capture (no build):
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/periodic_validation.py plot --run system_identification_2/results/20261031T193235Z_validate_9dd3dac8 --model system_identification_2/identification_model.json
Valid plotting vertices now connect across excluded transition bins. No samples
are inserted and no measurements/model/error calculations change. Actual missing
data and unresolved model effects remain gaps. A new plot folder is created.

Longer periodic power test (60-second frequency holds, about32minutes):
Copy config.periodic.long.json to Thor; active workload sizes/rates stay unchanged.
No worker rebuild needed. From the project root on Thor:
sudo python3 system_identification_2/suite.py validate --target-thor --config system_identification_2/config.periodic.long.json --allow-missing-temperature

After capture, plot10-second averages while retaining2-second native summaries:
MPLCONFIGDIR=/tmp/jtpc_si_mpl MPLBACKEND=Agg python3 system_identification_2/periodic_validation.py plot --run system_identification_2/results/ACTUAL_LONG_RUN --model system_identification_2/identification_model.json --plot-bin-seconds 10
This is display-only aggregation. Frozen model, controller interval, telemetry
and raw job records do not change. Missing/cross-transition bins remain excluded
from statistics.10-second bins require frequency holds of at least10seconds.
Longer averaging improves precision but cannot turn VIN into a GPU-only rail or
repair the broad-frequency error of a local linear response model.

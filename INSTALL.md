# Installation and Use

## Prepared local environment

The project `.venv` uses Python 3.9 with NumPy, Matplotlib, SciPy, pandas, and PyMuPDF. Exact versions are in `requirements-lock.txt`. This environment is isolated from system packages. Offline plotting needs neither the remote host nor the Windows volume.

```bash
cd /home/tiare/Desktop/JTPC
./experiment/run_allexperiments.sh
.venv/bin/python verify.py
```

Individual sections:

```bash
./experiment/6.1/run.sh
./experiment/6.2/run.sh
./experiment/6.3/run.sh
```

Original paper assets are in each section's `Figures/paper_original/`; regenerated figures are in `Figures/replotted/`. The authorized replacement for Figure 7(b) is `experiment/6.2/Figures/fig7b_power_RTR090.pdf`, which the top-level entry copies to `experiment/Figures/`. Plotting does not rewrite `logs/`.

## Another computer

Copy the project and recreate the environment instead of reusing the old `.venv`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
./experiment/run_allexperiments.sh
```

Use Python 3.9 or a compatible version. The original figures use Arial, which is available on this machine. Matplotlib falls back if Arial is missing; recheck layout on that machine. Select a different interpreter with `PYTHON=/path/to/python ./experiment/6.2/run.sh`.

## Hardware source

`/usr/local/cuda-12.6/bin/nvcc` is installed locally but is not on PATH. System Eigen development headers are absent. The controller and dispatcher were compiled using temporarily extracted Eigen headers. CUDA workload compilation on this x86_64 host stops at ARM assembly instructions; the complete Jetson build and actual hardware execution remain unverified.

**Collection still has reproduced issues:** standalone SP initialization, stale binaries after build-flag changes, FC initialization/source-version differences, and connecting new logs to plotting. Historical wrappers explicitly supply SP; Figure 7 was run in separate segments, so a missing unified sweep entry is not itself a missing-material issue. See the [chain review](docs/collection_to_plot_review.md) and [historical follow-up](docs/chain_review_20261029/fig8_historical/HISTORICAL_TRACE.md).

The original build commands on a Jetson matching the experiment environment are:

```bash
make -C Scheduler EXTRA_FLAGS=-DJetson
make -C application EXTRA_FLAGS=-DJetson
```

These commands are not an end-to-end acceptance result. Each section's `collection/` contains hardware scripts with relocated paths; new collection writes to `runs/`. They retain operations involving GPU settings, sudo, shared memory, and process cleanup. Offline `run.sh` does not call them. Before running, verify the device, sensor, clocks, task periods, and model version, then validate on hardware. Existing scripts are not automatically historical frozen sources.

`6.2/collection/history/` retains the historical helper whose name says 090 but whose contents set RTR=0.85 and refer to an old user directory. It is not a current ready-to-use entry.

## Thor target

See [Thor setup](docs/THOR.md) for INA238 VIN whole-system power, target build commands, tests, and remaining experiment-porting limits.

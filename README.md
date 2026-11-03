# JTPC Local Experiment Project

For GitHub setup, the two-machine Git workflow, and rsync transfers from
`thor2:~/JTPC`, see [run.txt](run.txt).

This project follows the official DySM organization: shared source code and experiments grouped by paper section. It corresponds to `JTPC_DAC_Detailed.pdf` and supports offline plotting from existing logs. The original algorithms, task sizes, periods, and multiprocess runtime are preserved. No hardware experiments were run during organization.

**Current status: existing logs reproduce Figures 4–9, but the full recollection-to-plot workflow is not yet validated.** See the [collection-to-plot review](docs/collection_to_plot_review.md) and its historical follow-up.

- [Project guide](PROJECT_GUIDE.md): structure, call chain, figure/data mapping, provenance, and limits.
- [Installation](INSTALL.md): offline plotting, verification, and hardware build information.
- [Experiment index](experiment/README.md): scripts, logs, and figures for Sections 6.1–6.3.
- [Collected paper figures](experiment/Figures/): Figures 1–9, with separate 7(a)/7(b), totaling 10 PDFs.

## Thor power measurement

See [Thor setup and limits](docs/THOR.md) for `bash scripts/get_power.sh thor` and the explicit `JPAP_POWER_BACKEND=thor` controller selector. This adapter does not by itself port the old closed-loop experiments.

## Quick start

```bash
cd /home/tiare/Desktop/JTPC
./experiment/run_allexperiments.sh
.venv/bin/python verify.py
```

The top-level entry only reads local logs and plots. It does not compile or launch Jetson tasks. Each section's `run.sh` can also be called from another working directory.

## Structure

```text
JTPC/
├── README.md / INSTALL.md / PROJECT_GUIDE.md
├── requirements.md / requirements.txt / requirements-lock.txt
├── Scheduler/                 # Controller, dispatcher, shared header, Makefile
├── application/               # CUDA workloads and Makefile
├── Common/jetson/             # Power measurement and hardware support
├── scripts/                   # GPU frequency and power helpers
├── system_identification/     # Model experiments, stability, Figures 1/2
├── experiment/
│   ├── run_allexperiments.sh   # Offline plotting entry
│   ├── 6.1/                   # Workload changes: Figures 4/5/6
│   ├── 6.2/                   # Setpoints and utility: Figures 7/8
│   ├── 6.3/                   # Task arrival: Figure 9
│   ├── notebooks/             # Original Windows plotting notebooks
│   └── Figures/               # Selected paper figures
├── pdf/                       # Supplied DAC paper PDF only
├── docs/                      # Provenance, checks, audits, and organization records
├── verify.py                  # Asset hashes, 15 Figure 7(b) groups, syntax
└── .venv/                     # Local plotting environment
```

## Data versions

Figure 7(b) uses 15 original logs at fixed RTR=0.90. The original statistical window is retained: `[100:-1]` when the series has more than 101 values, otherwise the full series. Error bars are population standard deviations over time samples, not confidence intervals over independent runs. The new figure is `experiment/Figures/fig7b_power_RTR090.pdf`; the old 0.70 figure is retained separately.

The Figure 7(a) axis range, Figures 8/9 initial periods, and stability content are unchanged. The supplied PDF was not recompiled or revised. Historical RTNS sources/ZIP and the duplicate architecture asset were moved outside the project to `../JTPC_sources_20261029/pdf_extras_before_20261029/`; `pdf/` contains only the supplied paper PDF. The new 7(b) figure still needs to be inserted into the final manuscript project.

Final Figures 1/2 and related model material are retained, but their exact original generation chains remain incomplete. Current remote source is not a frozen source snapshot for every historical experiment; recollection is not guaranteed to reproduce the published values.

Two full original directories are stored separately in [JTPC_sources_20261029](../JTPC_sources_20261029/): `remote_JPAP/` and `windows_JPAP_Project/`. Organized execution and plotting do not depend on these directories. English translations and comment-only changes are tracked in `docs/english_conversion.json`; pre-conversion files are backed up outside this project.

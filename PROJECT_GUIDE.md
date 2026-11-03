# JTPC Local Project Guide

Organization date: 2026-10-29.

## Two full copies

`../JTPC_sources_20261029/remote_JPAP/` is a full copy of remote `/home/yuanyang/JPAP`, including `.git` and the Scheduler symlink: 23,430 regular files.

`../JTPC_sources_20261029/windows_JPAP_Project/` is a full copy of the Windows desktop JPAP_Project directory: 55,818 regular files, including main, variants, analysis, archives, backups, supporting_projects, follow_up_projects, and environment files.

Both copy operations exited 0 and had no differences in rsync checksum dry runs. Evidence is `copy_verification.json` in the source-copy directory. Neither original source was deleted or rewritten. Other historical remote JPAP directories were not part of these full copies; related earlier audit material is in `docs/prior_audit/`.

## Source and version provenance

Active runtime source came from remote_JPAP/scheduler and application. Older Windows main/variant source was not mixed into active entries; it remains in the complete copy. Figure data uses numerically matched Windows logs, with remote historical correspondence recorded in `docs/prior_audit/`.

`docs/source_manifest.json` records each source, destination, original/current SHA256, and necessary modifications. Plot scripts were extracted from specific notebook cells; see `docs/plot_sources.json`. Notebooks retain their cells and outputs; English conversion changes comments only.

Current source is not a frozen snapshot for every historical run. Directory organization does not prove that recollection will reproduce old values. Algorithms, periods, task sizes, and sensor behavior were not changed. CUDA include paths were normalized to `Scheduler`; subsequent English conversion changes comments only.

## Relationship to official DySM

Template: https://github.com/srinivasans74/DySM at commit `fee7b4b718f92710ff43fae0353cef481a64de5d`.

The project adopts Scheduler/application/experiment and nearby section logs, plotting code, and figure outputs. JTPC-specific Common/jetson and scripts are retained. The unrelated libsmctrl SM-partitioning library is not added. Original system_identification remains an independent model-experiment area, analogous in responsibility to official microbenchmarks. Section numbering follows JTPC Section VI, not unrelated DySM experiments.

## Calls and state flow

Hardware collection shell → Makefiles for Scheduler/application → scheduler.cc fork/exec of controller and independent CUDA tasks → shared_header.hpp memory/signals carrying measurements and task periods → controller.cc power measurement and control updates to periods/GPU frequency → text logs.

Hardware support is in Common/jetson; some frequency commands use scripts. The original convention of starting from experiment as the working directory is retained. JTPC remains multiprocess, unlike DySM's single-process multithreaded runtime.

Offline run.sh → section plotting.py/plot_*.py → local logs → Figures. Offline and hardware entries are separate. Offline entries locate the project relative to the script itself after relocation.

## Figure mapping

| Figure | Content | Location and status |
|---|---|---|
| 1 | Frequency/period model relationships | system_identification; final figure found, exact generation chain incomplete |
| 2 | Model validation | system_identification; final figure found, exact script/data missing |
| 3 | System architecture | experiment/Figures; existing figure retained |
| 4–6 | Workload increase, three methods | experiment/6.1; logs matched; Figure 4 historical PDF remains a version candidate |
| 7(a) | RTR sweep at 11 W | experiment/6.2; original conditions and axis range retained |
| 7(b) | Power sweep at RTR=0.90 | experiment/6.2; authorized replacement using 0.90 data |
| 8 | Task utility | experiment/6.2; main_temp logs, original initial periods |
| 9 | New task arrival | experiment/6.3; UNKNOWN prefix and control-window power series retained |

experiment/Figures contains 10 PDFs. Original assets are under Figures/paper_original; regenerated outputs are under Figures/replotted so new layouts are not confused with historical exports. New Figure 7(b) is fig7b_power_RTR090.pdf; the old 0.70 asset is explicitly marked original.

## Requested changes and retained content

Only Figure 7(b)'s condition changed from 0.70 to 0.90, preserving the statistical window, population standard deviation, method order, and style. Three methods times five points use 15 finalpowervalues logs. No recollection or raw-log edits were performed. Independent statistics are in docs/verification.json.

Figure 7(a)'s clipping is retained; Figures 8/9 retain mm=60 ms; stability code and statements are retained pending discussion. These retention choices do not resolve historical scientific discrepancies.

The supplied DAC PDF remains in `pdf/`. The historical RTNS project/ZIP and the duplicate architecture asset were moved to `../JTPC_sources_20261029/pdf_extras_before_20261029/`; Figure 3 remains in `experiment/Figures/`. No synthetic final DAC LaTeX project was assembled and no manuscript was recompiled. The corrected 7(b) asset is available for insertion into the final manuscript.

## Verification limits

Both full copies passed checksum checks. verify.py checks source assets, independent Figure 7(b) means/population standard deviations, Python/Shell syntax, and 10 PDF assets. See docs/verification.json and docs/plot_run.log.

Offline plotting was executed locally. Initial organization did not build or run hardware source; the later chain review compiled the controller/dispatcher in temporary copies and documented remaining failures. Collection scripts retain hardware behavior, including sudo and cleanup; full hardware operability is not established.

See [figure QA](docs/qa/README.md) for seven regenerated figures, four multipanel alignment checks, font-size checks, and clipping-related false positives. See [chain review](docs/collection_to_plot_review.md) for the current end-to-end status.

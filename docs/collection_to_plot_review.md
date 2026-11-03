# Figures 3–9: Collection-to-Plot Chain Review (2026-10-29)

**Historical follow-up:** wrappers explicitly passing SP, old controllers supporting skipped initialization, and matching execution output have been found for Figure 8. Seven complete series and four second-half segments match. The user confirmed Figure 7 was run in separate segments; absence of a unified sweep script is not itself an issue. The initial findings below must be read with the [historical follow-up](chain_review_20261029/fig8_historical/HISTORICAL_TRACE.md).

**Conclusion: the offline existing-log-to-figure chain is complete. The full source-to-recollection-to-new-figure workflow is not yet validated. File organization and offline checks do not establish that all experiments can be rerun directly.**

During this review, controller/workload code, collection scripts, historical logs, paper, and figures were unchanged. Builds and isolated simulations used temporary copies. Existing logs were read and evidence archived. No hardware experiments, actual frequency changes, process cleanup, or shared-memory cleanup were performed. Subsequent English conversion changes documentation and comments only.

## Per-figure results

| Figure | Existing logs to plotting | Collection review |
|---|---|---|
| 3 | Architecture asset exists; not a measurement figure | Experimental logs not applicable; diagram not generated or modified |
| 4 / 5 / 6 | 16 / 16 / 11 input reads passed | Three interrupt scripts passed argument/path checks with the real dispatcher and substitute workloads; historical frozen-source identity and Jetson execution remain unverified |
| 7(a) | 45 input reads passed | Active collection lacks Full_* sweep entries; historical candidates archived, not activated or uniquely matched; segmented execution later confirmed by user |
| 7(b) | 15 input reads at RTR=0.90 passed | Same collection caveat; logs/statistics complete, recollection not validated |
| 8 | 45 input reads passed | FC/DFS standalone defaults fail; current FC initialization differs from historical logs; build-flag caching issue also present |
| 9 | 22 input reads passed | Real-dispatcher simulation passed four-task spawning and 120-second arrival argument; actual task-arrival behavior/hardware untested |

The 170 per-figure read records are not a count of unique files. Inputs exist, are nonempty, contain finite read values, and have SHA records. Original plotting data reads/statistics ran with savefig replaced by a no-op and outputs in temporary directories; paper figures were not overwritten. See chain_review_20261029/log_to_plot_inputs.json.

## Reproduced findings

1. **Figure 7 collection entries were absent from active collection.** experiment/6.2/collection/*main_temp.sh runs 120-second utility experiments, not the 240-second Full_* experiments. Historical JPAP 1 LQR1.sh, DFS.sh, and FC_GPU_adaptive.sh target Full_LQR, Full_DFS, and Full_FC_adaptive. Copies are in historical_candidates for provenance. Existing audits link historical FC logs to Windows Full_FC, but lack per-run source freezes. Do not mix controller versions blindly. The user's subsequent confirmation of segmented execution resolves the concern about a missing unified sweep entry, not the source-version uncertainty.
2. **Two Figure 8 standalone scripts fail without SP.** FC_GPU_main_temp.sh:43–46 and DFS_main_temp.sh:44–47 reference SP before assigning its default. With set -u, they exit 1 with `SP: unbound variable`. Explicit SP reaches the dispatcher. Historical wrappers were subsequently found to supply SP, so this is not evidence that historical runs failed.
3. **Build-flag changes do not trigger recompilation.** Scheduler/Makefile:22 tracks controller.cc but not EXTRA_FLAGS, shared headers, or linked Common sources. After building with -DJetson, adding -DCLAMP_PERIODS -DBOUND=50 still produces Nothing to be done. These macros affect period bounds, so methods can reuse another method's binary. A forced full CLAMP50 rebuild succeeded locally; the Makefile was not changed.
4. **Current FC initialization conflicts with historical utility/sweep logs.** FC_GPU_main_temp.sh:151–160 presets 1020 MHz and supplies JPAP_SKIP_INITIAL_GPU_LOCK=1. Current controller.cc:2765–2769 still initializes Jetson to 918 MHz unconditionally and ignores that variable. Historical Full_FC/main_temp FC logs record 1020 MHz. Figure 4 FC logs record 918 MHz, so do not generalize to all FC figures. The JPAP 1 controller supports the switch and has a 1020 initial value but differs elsewhere; it was not substituted. Follow-up shows the old script preserved existing governor/sysfs state rather than imposing the later fixed-frequency lock; a logged 1020 alone does not prove constant physical GPU frequency.
5. **New collection output is not connected to plotting.** Collection writes runs/ while plotting reads logs/, with no batch selector or import mapping. Section 6.2 also differs between runs/FC and logs/main_temp/FC. Existing run.sh replots old logs; it does not establish that a new plot uses a new capture.

Additional shared-memory concern: controller/tasks call ftok("shmfile",65), but that file is absent in the working directory and collection does not create it. A read-only ftok check returned -1/ENOENT, which source does not check. Subsequent participants might all use key -1, so this is not proof of inevitable startup failure; naming/isolation is still incorrect. No actual IPC object was created via shmget during this check.

## Verification scope

- Controller/dispatcher: ordinary -DJetson and forced CLAMP50 builds succeeded with temporarily extracted Eigen headers. No system package installation.
- CUDA: /usr/local/cuda-12.6/bin/nvcc exists but is outside PATH. ARM yield assembly blocks original-task compilation on this x86_64 host. This neither proves Jetson failure nor establishes successful compilation of all workloads. Source was not altered to bypass the architecture limit.
- Collection: nine isolated invocations used the real compiled dispatcher; controller, workers, make, sudo, and device operations were substitutes. Three Section 6.1 scripts, Section 6.2 LQR, and Section 6.3 passed defaults. Section 6.2 FC/DFS failed defaults and each passed with explicit SP. This checks call paths, arguments, and process spawning, not control or data capture.
- Historical source: shared header and particle match. hist/stereo/mm/mm_interrupt match after include-path case normalization. Controller logic differs; arrival-delay configuration in the dispatcher differs. CUDA hash differences alone do not imply changed task algorithms.
- verify.py checks asset integrity, 15 Figure 7(b) statistics, syntax, and PDF assets. It does not detect the runtime defects above, so PASS is not end-to-end acceptance.

Evidence in chain_review_20261029/ includes builds, nine mocked calls, 170 plotting reads, source comparisons, historical scripts, and SHA manifests. Diagnostic simulators reference the temporary build directory; they are evidence, not user collection entries.

## Remaining work

Confirm historical single-run entries/controller versions while retaining originals. Fix standalone SP initialization and build dependencies, establish FC initialization semantics and the shared-memory key file, and explicitly connect new batches to plotting. Then build and collect on the matching Jetson/sensor environment and verify the origin of new logs/figures.

This review archived evidence; runtime defects remain unresolved. Missing historical per-run source freezes cannot be manufactured retrospectively. Figures 1/2 were outside this review.

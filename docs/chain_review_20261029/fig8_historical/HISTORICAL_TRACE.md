# Figure 8: Historical Controller and Launch Provenance

Old-behavior controllers, launch scripts, and actual execution output were found. These are historical materials, not newly patched implementations. Per-run source/binary SHA freezes remain unavailable; no one complete controller.cc can be uniquely established as the generator of all Figure 8 data.

## Located files

- scheduler/controller.cc.bak_before_nosigma_20260526_215413: filename indicates 2026-05-26. Jetson initial values at lines 13/2557 are 1020 MHz; line 2561 reads JPAP_SKIP_INITIAL_GPU_LOCK. Its pre-translation SHA begins b5d4be387100 and matches before_nolog and full_sigma_backup copies. The date is a filename clue, not independent timestamp evidence.
- scheduler/controller.cc: another JPAP 1 version with 1020 initial values and the skip switch, plus later changes. It is not the same version as the preceding backup.
- motivation/FC_GPU_main_temp.sh: line 149 explicitly passes JPAP_SKIP_INITIAL_GPU_LOCK=1.
- motivation/run_main_temp_11w.sh, run_main_temp_block120.sh, run_main_temp_power_sweep090_120.sh: explicitly supply SP, POWER, and DURATION before invoking the single-run scripts. The missing-SP issue applies to standalone default invocation, not historical wrapper execution.
- Historical wrappers invoke unlock_gpu_adaptive.sh nvhost_podgov. The old FC script lacks the later forced-1020-MHz lock added in current remote_JPAP. Old behavior skips controller initialization and retains the existing governor/sysfs state. A logged value of 1020 alone does not establish constant physical GPU frequency.
- The existing helper named power_sweep090_120 has been edited to RTR=0.85, while historical stdout preserves actual 0.90 dispatcher commands. Filenames and present helper parameters are insufficient per-run historical configuration evidence.

## Numerical correspondence

Figure 8 uses three tasks' period and RTR files. They were compared point-by-point with historical stdout Pcur/RTR. Full matches require equal lengths for all six series and maximum absolute difference <=0.0011, allowing stdout rounding. Actual maximum difference among successful matches is <=0.0005000001. Complete sequences were checked, not just initial values or averages. DFS RTR was checked alongside constant periods to avoid false identification.

| Method | Full matches: power/mW | Second-half matches only | No complete match: power/mW |
|---|---|---|---|
| FC | 11000, 13000 | 11500: last 56 of 112 rows | 12000, 12500 |
| DFS | 11000, 12500, 13000 | 11500: last 55 of 110 rows | 12000 |
| JTPC | 11000, 13000 | 11500, 12500: last 55 of 110 rows each | 12000 |

Seven full matches, four second-half matches, four unmatched cases. A segment match does not establish full-run provenance; do not delete the first half or change plotting statistics. All 15 related stdout files are archived, including failures/truncation.

Fully matched FC 11000/13000 output prints `[GPU] Skip initial GPU lock; using existing governor/sysfs state.` Actual dispatcher commands specify RTR=0.90, duration=120 seconds, and periods=160/80/60 ms. Thus those historical executions used a controller supporting skipped initialization. The current controller ignoring that switch does not represent their behavior.

## Updates to the initial review

- Figure 7: user confirmed segmented execution. Missing a unified sweep entry alone is not missing experiment material. Retain historical single-run scripts/log mapping; assess source-version evidence separately.
- Figure 8 SP: wrappers explicitly supplying SP explain historical startup. Standalone default failure remains reproducible.
- Figure 8 frequency: old source supports skipped initialization and execution output confirms it. Do not restore old behavior by replacing it with the later forced-1020 lock.

This investigation only searched, compared, and archived. Active Scheduler/collection, logs, figures, and paper were not replaced; no hardware experiments ran. Finding historical source does not automatically fix build-flag caching or runs-to-logs routing. Subsequent language conversion translates comments without changing logic.

manifest.json records original paths and hashes, including pre-translation SHA where needed. jtpc_fig8_stdout_search.json records full-series comparisons; jtpc_fig8_stdout_segments.json records segment matches. Diagnostic scripts retain local audit paths and are evidence rather than formal capture entries.

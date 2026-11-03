# Setpoints and Task Utility: Figures 7/8

```bash
./run.sh
```

Figure 7(a): logs/Full_{LQR,FC,DFS}/hist_stereo_mm/setpoint_11000_SP_SP_SP, with SP=0.70/0.75/0.80/0.85/0.90. plot_rtr.py comes from bar_plots CELL13. It removes nonpositive/nonfinite RTR, discards the first min(20,n//5) points, truncates the three task series to equal length, and averages tasks equally. DFS axis clipping is retained as requested.

Figure 7(b): the same Full directories, setpoint_POWER_0.90_0.90_0.90, 11–13 W in 0.5 W steps. plot_power.py comes from CELL12; fixed RTR changes to 0.90 and directory matching is exact. Use [100:-1] for series longer than 101 values. Mean and population standard deviation are converted from mW to W. The 15 groups are in Figures/fig7b_statistics.json. Old 0.70 logs/figure are retained.

Figure 8: logs/main_temp/{JTPC,FC,DFS}, fixed RTR=0.90. plot_utility.py comes from CELL9, with initial periods 160/80/60 ms. Compute mean(initial/current) over the full valid series per task, then average tasks equally. Initial periods are unchanged as requested.

The main_temp collection scripts correspond to utility experiments; they are not confirmed exact frozen collection sources for the longer Full_* logs. Figure 7 was run in separate segments; lack of a unified sweep entry is not itself a missing-material issue.

Plotting only writes Figures; raw logs are unchanged. Historical hardware entries are in collection; new collection targets runs. No hardware collection was performed during organization. See the chain review for unresolved build, version, and new-log routing issues.

The active `collection/LQR_main_temp.sh`, `FC_GPU_main_temp.sh`, and
`DFS_main_temp.sh` default to `JPAP_POWER_BACKEND=thor`. They use the same
`scripts/get_power.sh thor` INA238 VIN reader as `system_identification_2`.
Readings and `POWER` are in **mW**, measuring module-plus-carrier input power.
An initial sensor check precedes cleanup/build/device actions; missing or invalid
readings abort launch. The backend selector is exported to the scheduler/controller
and explicitly preserved through LQR's `sudo env` launch. Controller builds use
`make -B` so each method gets its own Jetson build flags. Explicit backend
overrides remain supported. FC/DFS also initialize their default `SP` before use.

From the project root on Thor, check power without a build or CUDA workloads:

```bash
bash scripts/get_power.sh thor
```

After the remaining Thor GPU-actuation/model setup is ready, the collection
commands are:

```bash
bash experiment/6.2/collection/LQR_main_temp.sh
bash experiment/6.2/collection/FC_GPU_main_temp.sh
bash experiment/6.2/collection/DFS_main_temp.sh
```

Run the method needed, with g++, make, Eigen development headers and the target
CUDA compiler available. The wrappers build automatically. This power change does
not port GPU clock paths/tables or replace controller coefficients, and it does not
add `system_identification_2`'s structured temperature/frequency recorder. See
`docs/THOR.md` for the remaining platform limits. Historical scripts in `history/`
and `docs/chain_review_20261029/historical_candidates/` are unchanged.

# Runtime Workload Changes: Figures 4/5/6

```bash
./run.sh
```

Logs: logs/FC_interrupt, DFS_interrupt, LQR_interrupt; tasks hist/stereo/mm_test; initial periods 160/80/80 ms, RTR=0.90, power target 11 W.

Plots: plot_fc.py (original line_charts CELL9), plot_dfs.py (CELL10), plot_jtpc.py (Figure 6 portion of CELL17). The original first-100-control-record selection and event positions are retained. Sample alignment was not changed during organization.

Original traces were numerically matched against paper vector curves in the prior audit. The available historical Figure 4 PDF is a version candidate, not a confirmed exact match to the supplied DAC page. Regenerated output is retained separately.

Plotting only writes Figures; original logs are unchanged. Historical collection scripts are in collection and new collection targets runs. They were not executed on hardware during organization.

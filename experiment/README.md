# Experiment Index

| Directory | Experiment | Paper figures | Local entry |
|---|---|---|---|
| 6.1 | mm workload increase: FC-GPU/DFS/JTPC | 4, 5, 6 | `6.1/run.sh` |
| 6.2 | RTR sweep at 11 W; power sweep at RTR=0.90; utility | 7(a), 7(b), 8 | `6.2/run.sh` |
| 6.3 | particle task arrival | 9 | `6.3/run.sh` |

`run_allexperiments.sh` plots each section offline. `Figures/` collects 10 PDFs for Figures 1–9; Figures 1/2/3 are retained assets, not regenerated figures.

Each `logs/` contains original data, `Figures/paper_original/` contains historical paper assets, and `Figures/replotted/` contains locally generated figures. `collection/` contains separate hardware scripts.

Original notebook cells and outputs are retained in `notebooks/`, with Chinese comments translated to English. Extracted-cell provenance and changes are in `../docs/plot_sources.json`. Do not run the entire historical notebook indiscriminately: cells from different revisions may overwrite the same output and reference old Windows paths.

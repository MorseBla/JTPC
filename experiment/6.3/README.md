# New Task Arrival: Figure 9

```bash
./run.sh
```

Logs: logs/task_arrival_4task_test/hist_stereo_mm_particle/setpoint_11000_0.90_0.90_0.90_0.90.

plotting.py comes from line_charts CELL16. The UNKNOWN log prefix and UNKNOWN__powercontrolperiod.txt power series are retained. The first positive particle period occurs at index 57; the plotted detection position follows the original script.

Initial hist/stereo/mm periods are 160/80/60 ms. The original collection script delays particle arrival. mm is not changed to 80 ms, as requested.

Plotting only writes Figures; raw logs are unchanged. Historical hardware entries are in collection; new collection targets runs. No hardware collection was performed during organization.

The collection entry `collection/task_arrival_4task_test.sh` now defaults to
`JPAP_POWER_BACKEND=thor`, using the same `scripts/get_power.sh thor` INA238 VIN
reader as `system_identification_2`. This is module-plus-carrier input power,
not GPU-only power. Controller readings and `POWER` are in **mW**. The exported
selector reaches the controller through the scheduler. A sensor check runs before
old captures are removed or processes are cleaned up; invalid/missing sensor data
stops the script. The controller is forcibly rebuilt with `-DJetson` to avoid
reusing a binary built with different flags. An explicitly exported
`JPAP_POWER_BACKEND` can still select another existing controller backend.

From the project root on Thor, read power without building or starting workloads:

```bash
bash scripts/get_power.sh thor
```

This change fixes power-backend selection only. It does not add the
`system_identification_2` temperature/frequency recorder or complete the remaining
Thor GPU-actuation/model port described in `docs/THOR.md`. Once that port is ready,
the collection command is `bash experiment/6.3/collection/task_arrival_4task_test.sh`.

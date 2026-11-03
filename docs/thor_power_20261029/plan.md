# Thor Power Adapter and Deployment Plan

Goal: reuse scripts/get_power.sh for the new Thor's INA238 VIN whole-system input and deploy JTPC with English documentation to agx-thor@100.118.13.42:/home/agx-thor/JTPC.
User-selected approach: no Common/Thor module; a command-line sysfs read is sufficient. Keep Common backends unchanged.

- [x] Add tests first for INA238/VIN identification, hwmon renumbering, uW-to-mW conversion, missing/malformed/ambiguous sensors, legacy script output, and controller values above 20 W.
- [x] Extend get_power.sh with explicit thor mode (existing no-argument behavior retained). Read the driver's existing sysfs files only. No sensor configuration writes or component-power substitution.
- [x] Add JPAP_POWER_BACKEND=thor dispatch in returnpowerrtx, bypass the old 20 W rejection and synthetic power offset only for this backend, and fail clearly on read errors.
- [x] Run script and real-controller integration tests; build the unchanged legacy configuration plus the new dispatch.
- [x] Deploy code, logs, figures, paper and docs, excluding the x86 virtual environment and local build artifacts. Install only required missing build dependency on the target. Compile with the target CUDA toolchain.
- [x] Verify remote file hashes and real read-only power samples via both the script and controller function. No workloads, clock writes, power-mode changes, or closed-loop collection.

Known boundary: existing GPU frequency paths/tables, model gains, and experiment setpoints still target the old platform. Their adaptation/calibration is separate from this power adapter. Missing historical source freezes remain unresolved. Existing source-manifest hashes must retain original SHA alongside the adapted current SHA.

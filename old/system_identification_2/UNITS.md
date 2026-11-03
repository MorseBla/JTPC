# Model audit and measurement coordinates

B construction is **unresolved** for this checkout. No numeric B or successful
identification is asserted. The profiling and fixed-rate alpha measurements remain
usable independently. `analysis/model.json` contains `resolved: false`, `B: null`
and labeled inputs/outputs. A future model decision must precede coefficient
export and prediction-error claims; this suite does not replace analytical
coefficients with fitted response/rate slopes.

## Evidence in this checkout

* `pdf/JTPC_DAC_Detailed.pdf`, Section II: execution and period are described in
  milliseconds, task rates as normalized, but the rate normalization constant is
  not specified. Its Equation (3) reads
  `q_i = e_i + sum_{j != i} (e_j + theta_j) r_j`.
* That PDF's Equation (5) adds a measured `-beta_i f` term. Equation (17) uses
  `e_j + theta_j` for cross-rate entries and nonzero power/rate coefficients.
  This is a different model from the requested
  `e_i (e_j + theta_j) / f_0`, `-q_i,0 / f_0`, and zero power/rate entries.
  We retain the requested analytical-model goal; we do not import the PDF's
  empirical coefficients as a substitute.
* `Scheduler/controller.cc`: `innerloopduration = 0.500*2*2` is 2 seconds.
  `compute_LQR_gain` and `compute_LQR_gain_2` use A diagonals 0.95,
  placeholder period-to-response diagonals, and historical empirical constants.
  They do not implement the requested A=I analytical model. Their comments about
  W are not a reliable units contract: the actual Thor power function returns
  **mW**, the monitor averages it directly, and the control error subtracts it
  from the power setpoint without a W conversion.
* The control application updates `newtaskperiod = taskperiod_ms + delta`, then
  divides by 1000 for shared memory. `initial_rate` and the shell `default_rates`
  are misleading names: they supply **periods in seconds**, not Hz.
  `experiment/6.2/collection/LQR_main_temp.sh` gives hist/stereo/mm periods
  0.160/0.080/0.060 seconds. Those become 6.25/12.5/(1000/60) Hz here.
* `application/*_converted.cu`: two kernel passes per invocation; CUDA-event sums
  in ms, plus synthetic carry `max(0, previous_response_ms - period_s*1000)`.
  Events exclude semaphore acquisition. Thus the old logged response is not a
  full release-to-completion wall duration. Both measurements are retained here.

## Explicit variables and conversions

| Quantity | Stored physical unit and meaning | Conversion / limitation |
|---|---|---|
| `t_s`, release/start/end | CLOCK_MONOTONIC seconds on one host | Same epoch in Python and generated C++; UTC is provenance only |
| `execution_s` | sum of completed GPU event intervals, seconds | source CUDA milliseconds / 1000; excludes startup, initial transfers, lock wait, host dispatch; source per-pass work outside events remains excluded |
| `response_s` | source event sum plus source carry recurrence, seconds | recurrence only when a period is supplied; standalone carry is zero |
| `wall_response_s` | completion monotonic time minus scheduled release, seconds | includes host dispatch, semaphore contention, synchronization and backlog; startup excluded |
| `e_i` profile estimate | arithmetic mean `execution_s` at common reference | distribution retained; observed maximum is not proven WCET |
| `rate_hz` | physical releases per second | period_s=1/rate_hz; period_ms=1000/rate_hz |
| controller period increment | difference of physical periods, ms | exact delta=1000/r_new - 1000/r_old; local derivative dperiod_ms/drate_hz=-1000/rate_hz^2 |
| `frequency_hz`, `reference_hz` | supported GPC clock, cycles/s | MHz = Hz / 1e6; achieved clock may differ and is checked |
| `delta_f` | successive achieved frequency difference | physical Hz or MHz must be stated for each B column |
| power | raw helper mW and converted W | helper reads INA238 VIN uW / 1000 (integer truncation); W=helper_output*0.001 |
| alpha | W/MHz for this task set and fixed rates | W/Hz=alpha/1e6; controller mW/MHz=1000*alpha; raw-output power state sign is positive alpha, controller power-error state sign would be negative |
| theta | configurable assumed 0.00075 s | 750 microseconds is assumed, not measured; no established cycles scaling |
| q_i,0 | nominal average response in seconds/ms, observed in validation | Equation (3) is not used to fabricate a nominal point under unresolved normalization |
| paper normalized rate | unknown dimensionless coordinate | if r_norm=r_Hz/R_Hz, then dr_norm=dr_Hz/R_Hz; unknown R prevents coefficient conversion |
| requested x,u | x=[q_1,...,q_N,P]; u=[delta_r_1,...,delta_r_N,delta_f] | labels retained; A=I is the requested analytical model, not an edit to existing controller |

Equivalent frequency-scaled demand `C_i=e_i_seconds*f0_Hz` would have units of
cycles, but event time includes memory stalls and this alone does not establish
an invariant cycle demand. If both e and theta in the requested cross-rate
formula are cycles, division by a physical cycles/second frequency gives
cycles*seconds, which cannot multiply a physical Hz rate to produce seconds.
If both are seconds with physical Hz frequency, it is also inconsistent. A
relative-frequency coordinate and a time-based response model could produce a
different consistent formula, but selecting it would introduce an unsupported
model assumption. The reference frequency and raw SI demand are saved so such a
decision can be made later without recollection.

## Predictions and validation indexing

For a resolved future A=I model, an operating-point comparison uses
`x_step - x_nominal` versus `B*(v_step-v_nominal)`. Interval predictions use
`x[k+1] = x[k] + B*(v[k]-v[k-1])`, with x[k] measured over the preceding control
interval and v[k] applied at the next interval boundary. A held actuator has
zero increment on subsequent intervals; a constant step is never added again.
Do not compare an absolute rate/frequency vector with an increment B column.
Task samples are attributed by completion time for interval output aggregation;
settled comparisons require a release and completion wholly inside the steady
window. Empty task intervals are missing data, never zero response.

This suite preserves interval summaries and settled step deltas but deliberately
withholds B predictions while unresolved. Rate-only steps at fixed achieved
frequency can reveal the limitation of the assumed zero power/rate entries;
thermal drift and VIN's board components remain possible confounders. Alpha
fits neither establish those zero entries nor prove GPU-only power behavior.

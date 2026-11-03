# Standalone CUDA workers

`build_workers.py` transforms the existing `application/*_converted.cu` sources
into `generated/hist_worker.cu`, `generated/mm_worker.cu`, and
`generated/stereo_worker.cu`. It retains each service's kernel, constants,
allocation and initialization, launch geometry, two-job loop, CUDA-event timing,
and cleanup. The scheduler's shared-memory handshake and periodic release loop
are replaced by the stdin protocol below.

Each generated executable is a persistent process. It allocates and initializes
buffers once, prints `{"ready":true}`, then accepts:

```
run <CLOCK_MONOTONIC release timestamp in seconds> <period_s>
quit
```

Each `run` performs one non-overlapping invocation and returns JSON containing
`start_s`, `end_s`, `execution_s`, `response_s`, `wall_response_s`, `release_s`,
and `ok`. Execution time is the sum of the two completed CUDA event intervals.
`response_s` adds the original source carry recurrence
`max(0, previous_response_s - period_s)` when period_s > 0. The runner supplies
period_s=0 for standalone and the fixed task period for concurrent windows; `wall_response_s` includes host release lateness and waiting for a
suite-private POSIX semaphore. Set `JTPC_SI_SEMAPHORE` to a slash-prefixed name
shared by the workers in one experiment. This preserves the repository's
serialized GPU scheduling while avoiding the old `/gpu_global_lock` namespace.
No controller or unrelated workload is launched by the worker.

The generated source does not create scheduler log files or temporary workload
directories. Raw per-invocation records are emitted on stdout for the suite
runner to capture.

On Thor, build from the repository root after verifying CUDA and the target
architecture, for example:

```
python3 system_identification_2/build_workers.py --cuda /usr/local/cuda/bin/nvcc
```

This generates and compiles the three `sm_110` workers into
`system_identification_2/bin`. Use `--generate-only` for source-only target
inspection; use `--dry-run` to print commands without writing or compiling.
The development host must use only `--dry-run` or `--generate-only`; it has no
CUDA execution or hardware-control path.

Workload sizes come from each task's `workload_parameters` in config.json.
Defaults exactly match the original source. `--config PATH` selects an alternate
config for both generation/build and capture. Rebuild after changing parameters;
the build manifest prevents use of a mismatched built-in binary.

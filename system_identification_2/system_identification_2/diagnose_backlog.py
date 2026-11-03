"""Inspect recorded release lateness. Offline only; never changes capture settings."""
import argparse
import json
from pathlib import Path
import statistics


def read_rows(path):
    rows, errors = [], []
    if not path.exists():
        return rows, [str(path)+' missing']
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f'{path.name}:{number}: {exc}')
    return rows, errors


def diagnose(run):
    run = Path(run)
    config = json.loads((run/'config.json').read_text())
    windows = json.loads((run/'windows.json').read_text()) if (run/'windows.json').exists() else []
    jobs, parse_errors = read_rows(run/'jobs.jsonl')
    status = json.loads((run/'status.json').read_text()) if (run/'status.json').exists() else None
    results = []
    for window in windows:
        tasks, observed_load = {}, 0.0
        missing = []
        for task in config['tasks']:
            name = task['name']
            rate = window.get('rates_hz', {}).get(name)
            if rate is None:
                continue
            rows = [r for r in jobs if r.get('window_id') == window['id'] and r.get('task') == name
                    and r.get('ok') and all(k in r for k in ('release_s', 'start_s', 'end_s', 'execution_s'))]
            rows.sort(key=lambda r: r['release_s'])
            if not rows:
                tasks[name] = {'count': 0, 'requested_rate_hz': rate}
                missing.append(name)
                continue
            period = 1/rate
            wall = [r.get('wall_response_s', r['end_s']-r['release_s']) for r in rows]
            execution = [r['execution_s'] for r in rows]
            dispatch = [max(0., r['start_s']-r['release_s']) for r in rows]
            # Includes semaphore wait, resets and host synchronization; not a pure lock-wait measurement.
            residual = [max(0., w-e) for w, e in zip(wall, execution)]
            excess = [max(0., v-period) for v in wall]
            n = min(10, len(rows))
            threshold = period+config['safety']['max_lateness_s']
            load = statistics.fmean(execution)*rate
            observed_load += load
            tasks[name] = dict(count=len(rows), requested_rate_hz=rate, period_s=period,
                mean_execution_s=statistics.fmean(execution), max_execution_s=max(execution),
                mean_wall_response_s=statistics.fmean(wall), max_wall_response_s=max(wall),
                max_dispatch_lateness_s=max(dispatch),
                mean_wall_minus_execution_s=statistics.fmean(residual),
                first_up_to_10_mean_excess_past_period_s=statistics.fmean(excess[:n]),
                last_up_to_10_mean_excess_past_period_s=statistics.fmean(excess[-n:]),
                limit_wall_response_s=threshold, limit_crossings=sum(v>threshold for v in wall),
                event_time_demand_fraction=load,
                last_completed_job={k: rows[-1][k] for k in ('release_s', 'start_s', 'end_s', 'execution_s')})
        results.append(dict(window_id=window['id'], kind=window['kind'],
            requested_frequency_hz=window.get('requested_frequency_hz'),
            capture_complete=window.get('capture_complete', False), tasks=tasks,
            observed_event_time_demand_fraction_sum=observed_load,
            missing_tasks=missing,
            demand_interpretation=('Observed mean event demand exceeds serialized resource capacity at the requested rates.'
                                   if observed_load >= 1 else
                                   'Observed event demand alone does not establish feasibility: lock/reset/host overhead and transient delays remain.'),
            sampling_limitation='Partial/discard-window observations are diagnostic only; unsampled frequencies remain unverified.'))
    return dict(run=str(run), capture_status=status, parse_errors=parse_errors, windows=results,
                failed_records=[r for r in jobs if r.get('error') or r.get('ok') is False],
                conclusion='No rates or thresholds changed. A single limit crossing is not proof of accumulating backlog. Compare execution and wall times, counts, and beginning/end excess.',
                next_step='Use complete standalone profiles and a deliberately chosen fixed nominal rate set; retain those same rates across alpha and validation. Narrow the intended frequency range if low levels cannot sustain them. Do not silently change rates during a sweep.')


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.run), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

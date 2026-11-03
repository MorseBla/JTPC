"""Offline SI analysis. No hardware access, workload launch, or B refitting."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import statistics as st
import uuid


def _read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({'error': 'truncated or malformed JSONL record', 'raw': line})
    return rows


def _trap_mean(samples, key, start, end, max_gap_s=2.0):
    """Integrate exact boundaries using adjacent samples, never sample averaging."""
    out = dict(mean=None, coverage_s=0.0, max_gap_s=None, valid=False, n=0, reason='insufficient samples')
    if start is None or end is None or end <= start:
        return out
    raw = []
    for x in samples:
        if key not in x or 't_s' not in x:
            continue
        if x[key] is None:
            continue
        try:
            t, value = float(x['t_s']), float(x[key])
        except (TypeError, ValueError):
            return dict(out, reason='non-numeric telemetry')
        if not math.isfinite(t) or not math.isfinite(value):
            return dict(out, reason='nonfinite telemetry')
        raw.append((t, value))
    raw.sort()
    if len({t for t, _ in raw}) != len(raw):
        return dict(out, reason='duplicate timestamps')
    if len(raw) < 2:
        return out
    pts = [(t, v) for t, v in raw if start <= t <= end]
    boundary_gaps = []
    for boundary in (start, end):
        if any(t == boundary for t, _ in pts):
            continue
        before = [(t, v) for t, v in raw if t < boundary]
        after = [(t, v) for t, v in raw if t > boundary]
        if not before or not after:
            return dict(out, reason='missing boundary bracket')
        a, b = before[-1], after[0]
        boundary_gaps.append(b[0]-a[0])
        pts.append((boundary, a[1]+(b[1]-a[1])*(boundary-a[0])/(b[0]-a[0])))
    pts.sort()
    gaps = [b[0]-a[0] for a, b in zip(pts, pts[1:])] + boundary_gaps
    gap = max(gaps, default=math.inf)
    area = sum((b[0]-a[0])*(b[1]+a[1])/2 for a, b in zip(pts, pts[1:]))
    valid = gap <= max_gap_s
    return dict(mean=area/(end-start), coverage_s=end-start, max_gap_s=gap, valid=valid,
                n=len(pts), reason='ok' if valid else 'telemetry gap exceeds limit')


def rate_hz_to_period_ms(rate_hz):
    if not math.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError('rate must be finite and positive')
    return 1000.0/rate_hz


def period_ms_delta_from_rate_hz(old_rate_hz, new_rate_hz):
    return rate_hz_to_period_ms(new_rate_hz)-rate_hz_to_period_ms(old_rate_hz)


def input_coordinates(rates_hz, frequency_hz, task_order):
    """Suite physical coordinates [Hz..., MHz]; NOT legacy period coordinates."""
    return [float(rates_hz[name]) for name in task_order]+[float(frequency_hz)/1e6]


def successive_delta(previous, current):
    if len(previous) != len(current):
        raise ValueError('input dimensions differ')
    return [b-a for a, b in zip(previous, current)]


def predict_one_interval(previous_state, previous_input, current_input, B):
    """x[k+1]=x[k]+B*(v[k]-v[k-1]); held coordinates imply zero increment."""
    delta = successive_delta(previous_input, current_input)
    if len(B) != len(previous_state) or any(len(row) != len(delta) for row in B):
        raise ValueError('B dimensions do not match')
    return [x+sum(b*d for b, d in zip(row, delta)) for x, row in zip(previous_state, B)]


def linear_fit(x, y):
    xs, ys = list(map(float, x)), list(map(float, y))
    if len(xs) < 2 or len(xs) != len(ys) or not all(math.isfinite(v) for v in xs+ys):
        return dict(valid=False, reason='need >=2 finite trial points', n=len(xs))
    xm, ym = st.fmean(xs), st.fmean(ys)
    sxx = sum((v-xm)**2 for v in xs)
    if sxx <= 1e-12:
        return dict(valid=False, reason='fewer than two distinct achieved frequencies; alpha cannot be fitted', n=len(xs))
    slope = sum((a-xm)*(b-ym) for a, b in zip(xs, ys))/sxx
    intercept = ym-slope*xm
    residuals = [b-intercept-slope*a for a, b in zip(xs, ys)]
    sse, sst = sum(v*v for v in residuals), sum((v-ym)**2 for v in ys)
    se = math.sqrt(sse/(len(xs)-2)/sxx) if len(xs) > 2 else None
    return dict(valid=True, n=len(xs), slope_W_per_MHz=slope, intercept_W=intercept,
                r2=1-sse/sst if sst else None, sse=sse, slope_se=se,
                residuals_W=residuals, frequency_min_MHz=min(xs), frequency_max_MHz=max(xs))


def distribution(vals):
    vals = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
    if not vals:
        return dict(count=0, mean=None, median=None, stdev=None, p95=None, p99=None)
    ordered = sorted(vals)
    return dict(count=len(vals), mean=st.fmean(vals), median=st.median(vals), stdev=st.pstdev(vals),
                p95=ordered[math.ceil(.95*len(vals))-1], p99=ordered[math.ceil(.99*len(vals))-1])


def _profile_summary(rows, windows, config):
    result = {}
    for w in windows:
        if w.get('kind') != 'profile':
            continue
        selected = [r for r in rows if r.get('window_id') == w['id']]
        measured = [r for r in selected if not r.get('warmup', False) and r.get('ok') and 'execution_s' in r]
        values = [r['execution_s'] for r in measured]
        expected = config['profile']['measured']
        flags = []
        if len(values) != expected or not w.get('capture_complete', False):
            flags.append('incomplete_profile')
        if any(not r.get('ok', False) or r.get('error') for r in selected):
            flags.append('failed_invocations')
        if any(not math.isfinite(v) or v <= 0 for v in values):
            flags.append('invalid_execution_time')
        requested = w.get('requested_frequency_hz')
        if requested and any(abs(r.get('frequency_hz', requested)-requested)/requested > config.get('frequency', {}).get('tolerance_fraction', .02) for r in measured):
            flags.append('frequency_mismatch_or_throttling')
        warnings = []
        temperature_missing = any('temperature_C' in r for r in measured) and all(r.get('temperature_C') is None for r in measured)
        if temperature_missing:
            warnings.append('GPU temperature unavailable; thermal drift/throttling cannot be assessed')
            if not config.get('telemetry', {}).get('allow_missing_temperature', False):
                flags.append('temperature_telemetry_inadequate')
        stats = distribution([v for v in values if math.isfinite(v) and v > 0])
        result[w['task']] = dict(window_id=w['id'], task=w['task'], count=len(values), expected=expected,
            complete=not flags, flags=flags, warnings=warnings, execution_s=stats, mean_ms=stats['mean']*1000 if stats['mean'] is not None else None,
            median_ms=stats['median']*1000 if stats['median'] is not None else None,
            stdev_ms=stats['stdev']*1000 if stats['stdev'] is not None else None,
            p95_ms=stats['p95']*1000 if stats['p95'] is not None else None,
            p99_ms=stats['p99']*1000 if stats['p99'] is not None else None,
            warmup_count=sum(bool(r.get('warmup')) and bool(r.get('ok')) for r in selected),
            actual_frequency_hz=distribution(r['frequency_hz'] for r in measured if 'frequency_hz' in r),
            temperature_C=distribution(r.get('temperature_C') for r in measured
                                        if r.get('temperature_C') is not None),
            estimate_status='mean demand estimate; no WCET guarantee; unusable when incomplete')
    return result


def window_summary(w, rows, telemetry, config):
    start, end = w.get('start_s'), w.get('end_s')
    max_gap = config.get('telemetry', {}).get('max_gap_s', 1.0)
    signals = {name: _trap_mean(telemetry, key, start, end, max_gap) for name, key in
               [('power', 'power_W'), ('frequency', 'frequency_hz'), ('temperature', 'temperature_C')]}
    allow_missing_temperature = bool(config.get('telemetry', {}).get('allow_missing_temperature', False))
    temperature_missing = signals['temperature']['mean'] is None
    if temperature_missing and allow_missing_temperature:
        signals['temperature'] = dict(signals['temperature'], valid=False,
                                       reason='GPU temperature unavailable; thermal drift/throttling cannot be assessed')
    selected = [r for r in rows if r.get('window_id') == w['id']]
    # Settled comparisons: a complete invocation must lie within the steady window.
    steady = [r for r in selected if r.get('ok') and start is not None and end is not None
              and start <= r.get('release_s', -math.inf) and r.get('end_s', math.inf) <= end]
    flags = []
    if not w.get('capture_complete', False):
        flags.append('incomplete_capture')
    if any(r.get('error') or not r.get('ok', False) for r in selected):
        flags.append('task_failure')
    warnings = []
    for name, value in signals.items():
        if not value['valid']:
            if name == 'temperature' and allow_missing_temperature and temperature_missing:
                warnings.append('GPU temperature unavailable; thermal drift/throttling cannot be assessed')
            else:
                flags.append(name+'_telemetry_inadequate')
    if temperature_missing and allow_missing_temperature:
        warnings.append('GPU temperature unavailable; thermal drift/throttling cannot be assessed')
    inside = [r for r in telemetry if start is not None and end is not None and start <= r.get('t_s', -1) <= end]
    requested = w.get('requested_frequency_hz')
    tolerance = config.get('frequency', {}).get('tolerance_fraction', .02)
    if requested and any(abs(r['frequency_hz']-requested)/requested > tolerance for r in inside if 'frequency_hz' in r):
        flags.append('frequency_mismatch_or_throttling')
    temp_values = [r['temperature_C'] for r in inside if r.get('temperature_C') is not None
                   and math.isfinite(float(r['temperature_C']))]
    thermal_drift = bool(temp_values and max(temp_values)-min(temp_values) > config.get('telemetry', {}).get('thermal_drift_C', 5))
    if thermal_drift:
        flags.append('thermal_drift')
    tasks = {}
    duration = end-start if start is not None and end is not None else 0
    for t in config['tasks']:
        name = t['name']
        rr = [r for r in steady if r['task'] == name]
        rate = w.get('rates_hz', {}).get(name, t['rate_hz'])
        expected = max(0, duration*rate)
        min_jobs = config.get('alpha', {}).get('min_jobs', 10)
        adequate = len(rr) >= max(min_jobs, .8*expected)
        lateness = [max(0, r['start_s']-r['release_s']) for r in rr]
        wall = [r.get('wall_response_s', r['end_s']-r['release_s']) for r in rr]
        backlog = any(v > 1/rate+config.get('safety', {}).get('max_lateness_s', .5) for v in wall)
        if not adequate:
            flags.append(name+'_insufficient_invocations')
        if backlog:
            flags.append(name+'_backlog')
        response = distribution(r['response_s'] for r in rr)
        tasks[name] = dict(count=len(rr), expected_count=expected, adequate=adequate,
            achieved_rate_hz=len(rr)/duration if duration else None,
            nominal_requested_rate_hz=rate, response_s=response,
            execution_s=distribution(r['execution_s'] for r in rr), wall_response_s=distribution(wall),
            max_lateness_s=max(lateness, default=None), backlog=backlog,
            mean_response_ms=response['mean']*1000 if response['mean'] is not None else None)
    return dict(window_id=w['id'], kind=w['kind'], start_s=start, end_s=end,
                requested_frequency_hz=requested, requested_rates_hz=w.get('rates_hz'),
                **signals, tasks=tasks, flags=flags, warnings=sorted(set(warnings)),
                adequate=not flags,
                temperature_available=not temperature_missing,
                frequency_MHz=signals['frequency']['mean']/1e6 if signals['frequency']['mean'] is not None else None)


def _alpha_summary(rows, windows, telemetry, config):
    trials = [window_summary(w, rows, telemetry, config) for w in windows if w.get('kind') in ('alpha', 'drift_reference')]
    for t in trials:
        t['invocations'] = {k: v['count'] for k, v in t['tasks'].items()}
        t['expected_invocations'] = {k: v['expected_count'] for k, v in t['tasks'].items()}
    usable = [t for t in trials if t['adequate']]
    fit = linear_fit([t['frequency_MHz'] for t in usable], [t['power']['mean'] for t in usable])
    if len({t['requested_frequency_hz'] for t in usable}) < 2:
        fit = dict(valid=False, reason='Fewer than two supported requested/achieved operating levels; alpha cannot be fitted', n=len(usable))
    if any(not t.get('temperature_available', True) for t in trials):
        fit.setdefault('warnings', []).append(
            'GPU temperature unavailable; thermal drift/throttling cannot be assessed')
    if fit['valid']:
        slope = fit['slope_W_per_MHz']
        fit.update(slope_W_per_Hz=slope/1e6, slope_mW_per_MHz=slope*1000,
                   alpha_scope='this task set, fixed nominal rates, configured power channel and conditions',
                   intercept_status='fitted intercept; not measured physical idle power',
                   slope_uncertainty_units='W/MHz; OLS trial-level standard error, conditional on stationary independent trial residuals',
                   trial_ids=[t['window_id'] for t in usable], flags=[], warnings=[])
        missing_temperature = any(not t.get('temperature_available', True) for t in usable)
        if missing_temperature:
            fit['warnings'].append('GPU temperature unavailable; thermal drift/throttling cannot be assessed')
        if slope <= 0:
            fit['flags'].append('nonpositive_alpha')
        if fit['slope_se'] is None or abs(slope) <= 2*(fit['slope_se'] or 0):
            fit['flags'].append('slope_uncertain')
        if fit['r2'] is None or fit['r2'] < .8:
            fit['flags'].append('poor_linear_fit')
        distinct = {t['requested_frequency_hz'] for t in usable}
        if len(distinct) < 3:
            fit['flags'].append('fewer_than_three_levels_linearity_unchecked')
        groups = {}
        for t in usable:
            groups.setdefault(str(t['requested_frequency_hz']), []).append(t['power']['mean'])
        fit['repeat_power_stdev_W'] = {k: st.pstdev(v) if len(v)>1 else None for k, v in groups.items()}
        references = [t for t in usable if t['kind'] == 'drift_reference']
        fit['reference_power_range_W'] = max(t['power']['mean'] for t in references)-min(t['power']['mean'] for t in references) if references else None
        if len(references) > 1:
            reference_power_mean = st.fmean(t['power']['mean'] for t in references)
            if fit['reference_power_range_W'] > config.get('alpha', {}).get('reference_drift_fraction', .1)*abs(reference_power_mean):
                fit['flags'].append('substantial_reference_power_drift')
            reference_temps = [t['temperature']['mean'] for t in references if t['temperature']['mean'] is not None]
            fit['reference_temperature_range_C'] = max(reference_temps)-min(reference_temps) if reference_temps else None
            if reference_temps and fit['reference_temperature_range_C'] > config.get('telemetry', {}).get('thermal_drift_C', 5):
                fit['flags'].append('substantial_reference_thermal_drift')
        if any('thermal_drift' in t['flags'] for t in trials):
            fit['flags'].append('some_trials_rejected_for_thermal_drift')
        fit['reliable_without_review'] = False
    return dict(trials=trials, usable_trials=len(usable), fit=fit)


def build_unresolved_model(config, profiles, alpha):
    tasks = [t['name'] for t in config['tasks']]
    return dict(resolved=False, B=None, A='requested I; existing controller differs',
        state_order=[f'q_{t}' for t in tasks]+['P'], state_units=['seconds']*len(tasks)+['W'],
        input_order=[f'delta_r_{t}' for t in tasks]+['delta_f'],
        input_rate_units='physical Hz retained; paper normalized coordinate unresolved', frequency_coordinate='MHz',
        alpha=alpha['fit'], power_channel=config.get('power'), source_measurements=profiles,
        nominal_point=dict(rates_hz={t['name']:t['rate_hz'] for t in config['tasks']},
                           reference_hz=config.get('frequency', {}).get('reference_hz')),
        assumptions=dict(context_switch_overhead_s=config.get('assumed_context_switch_s', .00075),
                         overhead_status='assumed, not measured'),
        reason='B unresolved: supplied PDF Eq(5)/(17) differ from requested analytical expression; rate normalization, time-versus-cycle meaning and frequency normalization are unspecified. Current controller adjusts period ms with placeholder slopes. See UNITS.md; no empirical refitting substituted.')


def interval_summaries(windows, rows, telemetry, config):
    """Outputs in half-open completion bins; no invented zero for empty q bins."""
    bins = []
    interval = config.get('interval_s', 2.0)
    origin = next((w.get('settle_start_s') for w in windows if w.get('kind') == 'validation'), None)
    if origin is None:
        return bins
    end = max(w.get('end_s', origin) for w in windows if w.get('kind') == 'validation')
    start = origin
    while start+interval <= end+1e-9:
        finish = start+interval
        w = next((w for w in windows if w.get('kind') == 'validation' and w.get('settle_start_s', math.inf) <= start and finish <= w.get('end_s', -math.inf)), None)
        task_outputs = {}
        for task in config['tasks']:
            completed = [r for r in rows if r.get('ok') and r.get('task') == task['name'] and start <= r.get('end_s', -1) < finish]
            task_outputs[task['name']] = dict(response_s=distribution(r['response_s'] for r in completed),
                                             wall_response_s=distribution(r.get('wall_response_s', r['end_s']-r['release_s']) for r in completed))
        bins.append(dict(k=len(bins), start_s=start, end_s=finish, window_id=w['id'] if w else None,
                         straddles_transition=w is None,
                         power=_trap_mean(telemetry, 'power_W', start, finish, config.get('telemetry', {}).get('max_gap_s', 1)),
                         achieved_frequency=_trap_mean(telemetry, 'frequency_hz', start, finish, config.get('telemetry', {}).get('max_gap_s', 1)),
                         outputs=task_outputs, B_prediction=None,
                         prediction_status='unresolved B; no prediction asserted'))
        start = finish
    return bins


def _validation_summary(rows, windows, telemetry, config):
    results = [window_summary(w, rows, telemetry, config) for w in windows if w.get('kind') == 'validation']
    nominal = results[0] if results and results[0]['adequate'] else None
    previous = None
    order = [t['name'] for t in config['tasks']]
    for entry in results:
        if entry['frequency']['mean'] is not None:
            achieved_rates = {k: v['achieved_rate_hz'] for k, v in entry['tasks'].items()}
            entry['actual_input_coordinates_Hz_MHz'] = input_coordinates(achieved_rates, entry['frequency']['mean'], order)
            entry['requested_input_coordinates_Hz_MHz'] = input_coordinates(entry['requested_rates_hz'], entry['requested_frequency_hz'], order)
            entry['delta_from_previous_actual'] = successive_delta(previous['actual_input_coordinates_Hz_MHz'], entry['actual_input_coordinates_Hz_MHz']) if previous else None
            previous = entry
        if nominal and entry['adequate']:
            entry['delta_input_vs_nominal_actual'] = successive_delta(nominal['actual_input_coordinates_Hz_MHz'], entry['actual_input_coordinates_Hz_MHz'])
            entry['delta_power_W_vs_nominal'] = entry['power']['mean']-nominal['power']['mean']
            entry['delta_response_s_vs_nominal'] = {name: entry['tasks'][name]['response_s']['mean']-nominal['tasks'][name]['response_s']['mean'] for name in order}
            rates_changed = entry['requested_rates_hz'] != nominal['requested_rates_hz']
            same_requested = entry['requested_frequency_hz'] == nominal['requested_frequency_hz']
            tolerance = config.get('frequency', {}).get('tolerance_fraction', .02)
            same_achieved = abs(entry['frequency']['mean']-nominal['frequency']['mean']) <= tolerance*nominal['frequency']['mean']
            entry['zero_rate_power_discrepancy_W'] = entry['delta_power_W_vs_nominal'] if rates_changed and same_requested and same_achieved else None
            entry['B_prediction'] = None
    return dict(windows=results, nominal_window_id=nominal['window_id'] if nominal else None,
                intervals=interval_summaries(windows, rows, telemetry, config), B_predictions=None,
                prediction_status='unresolved B: settled differences and completion-binned interval outputs only; no validation verdict')


def plots(out, report, telemetry, jobs, windows, config):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        report['limitations'].append('matplotlib unavailable: plots omitted')
        return
    trials = report['alpha']['trials']
    fit = report['alpha']['fit']
    pts = [t for t in trials if t['adequate']]
    if pts:
        fig, ax = plt.subplots()
        x, y = [t['frequency_MHz'] for t in pts], [t['power']['mean'] for t in pts]
        ax.scatter(x, y, label='steady trial means')
        if fit['valid']:
            xx = [min(x), max(x)]
            ax.plot(xx, [fit['intercept_W']+fit['slope_W_per_MHz']*f for f in xx], label='free-intercept fit')
        ax.set(xlabel='Achieved GPC frequency (MHz)', ylabel='Configured channel power (W)')
        ax.legend(); fig.tight_layout(); fig.savefig(out/'alpha_power_vs_frequency.png'); plt.close(fig)
    valid_telemetry = [t for t in telemetry if all(k in t for k in ('t_s', 'power_W', 'frequency_hz', 'temperature_C'))]
    if valid_telemetry:
        fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
        origin = valid_telemetry[0]['t_s']
        for ax, key, scale, label in zip(axes, ('power_W', 'frequency_hz', 'temperature_C'), (1, 1e-6, 1), ('Power (W)', 'GPC frequency (MHz)', 'Temperature (C)')):
            points = [(t['t_s']-origin, t.get(key)) for t in valid_telemetry if t.get(key) is not None]
            if points:
                ax.plot([x for x, _ in points], [y*scale for _, y in points], linewidth=.7)
            else:
                ax.text(.5, .5, 'GPU temperature unavailable', transform=ax.transAxes,
                        ha='center', va='center')
            ax.set_ylabel(label)
            for w in windows:
                if w.get('settle_start_s') is not None:
                    ax.axvline(w['settle_start_s']-origin, color='grey', alpha=.2)
        axes[-1].set_xlabel('Monotonic elapsed time (s)'); fig.tight_layout(); fig.savefig(out/'telemetry_timeseries.png'); plt.close(fig)
    for task in config['tasks']:
        rr = [r for r in jobs if r.get('ok') and r.get('task') == task['name'] and 'end_s' in r]
        if rr:
            origin = rr[0]['release_s']
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.plot([r['end_s']-origin for r in rr], [r['response_s']*1000 for r in rr], '.', ms=2, label='source carry response')
            ax.plot([r['end_s']-origin for r in rr], [r.get('wall_response_s', r['end_s']-r['release_s'])*1000 for r in rr], '.', ms=2, alpha=.5, label='release-to-completion')
            ax.set(xlabel='Completion elapsed time (s)', ylabel=task['name']+' response (ms)')
            ax.legend(); fig.tight_layout(); fig.savefig(out/(task['name']+'_response_timeseries.png')); plt.close(fig)


def analyze(run_dir):
    run = Path(run_dir)
    config = json.loads((run/'config.json').read_text())
    status = json.loads((run/'status.json').read_text()) if (run/'status.json').exists() else {'complete': False, 'reason': 'status missing'}
    windows = json.loads((run/'windows.json').read_text()) if (run/'windows.json').exists() else []
    jobs, telemetry = _read_jsonl(run/'jobs.jsonl'), _read_jsonl(run/'telemetry.jsonl')
    profiles = _profile_summary(jobs, windows, config)
    alpha = _alpha_summary(jobs, windows, telemetry, config)
    validation = _validation_summary(jobs, windows, telemetry, config)
    model = build_unresolved_model(config, profiles, alpha)
    if (run/'preflight.json').exists():
        preflight = json.loads((run/'preflight.json').read_text())
        model['nominal_point']['reference_hz'] = preflight['reference_hz']
        model['source_preflight'] = preflight
    out = run/'analysis'
    if out.exists():
        out = run/('analysis_'+uuid.uuid4().hex[:8])
    out.mkdir()
    report = dict(status='complete' if status.get('complete') else 'incomplete', capture_status=status,
                  profiles=profiles, alpha=alpha, validation=validation, model=model, output_directory=str(out),
                  raw_errors=[r for r in jobs+telemetry if r.get('error')],
                  limitations=[model['reason'], 'Capture completeness is not model validity or hardware success.', 'Thermal drift/throttling flags are symptoms, not a calibrated thermal throttle diagnosis.'])
    plots(out, report, telemetry, jobs, windows, config)
    for filename, value in [('report.json', report), ('model.json', model), ('trials.json', alpha['trials']), ('intervals.json', validation['intervals'])]:
        (out/filename).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    lines = ['JTPC profiling and validation analysis', 'Capture status: '+report['status'],
             'B unresolved; no model validity claim. See UNITS.md.',
             'Power channel: '+str(config.get('power', {}).get('channel', 'unspecified'))]
    for name, profile in profiles.items():
        lines.append(f'{name}: n={profile["count"]}/{profile["expected"]}, mean={profile["mean_ms"]} ms, complete={profile["complete"]}, flags={profile["flags"]}')
    lines += ['Alpha fit: '+json.dumps(alpha['fit']),
              f'Usable steady trials: {alpha["usable_trials"]}/{len(alpha["trials"])}',
              f'Validation windows: {len(validation["windows"])}, interval bins: {len(validation["intervals"])}',
              'See report.json, trials.json and intervals.json for details.']
    (out/'report.txt').write_text('\n'.join(lines)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('run_dir')
    args = parser.parse_args()
    print(json.dumps(analyze(args.run_dir), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

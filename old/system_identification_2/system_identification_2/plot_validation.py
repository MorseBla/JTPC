"""Review recorded Thor runs, print partial B / implied C, and plot validation.

Offline only. No target binaries, hardware interfaces, or control scripts run.
Unknown analytical rate coefficients remain unknown; validation data are not fitted.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import statistics as st
import uuid

from analysis import (_read_jsonl, _profile_summary, _alpha_summary,
                      _validation_summary, linear_fit)
from validation_figures import render_validation

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_run(path):
    def read(name):
        return json.loads((path/name).read_text())
    return dict(path=str(path), config=read('config.json'), windows=read('windows.json'),
                status=read('status.json'), cleanup=read('cleanup.json'), preflight=read('preflight.json'),
                jobs=_read_jsonl(path/'jobs.jsonl'), telemetry=_read_jsonl(path/'telemetry.jsonl'),
                build=read('build_manifest.json'))


def raw_inventory(paths):
    return {str(p): digest(p) for root in paths for p in sorted(root.iterdir()) if p.is_file()}


def make_matrices(config, validation, alpha, profile, f0_hz):
    """Export resolvable frequency terms only; physical-rate cross terms stay null."""
    order = [t['name'] for t in config['tasks']]
    n = len(order)
    if not validation['windows'] or not validation['windows'][0]['adequate']:
        raise ValueError('A usable first nominal validation window is required')
    nominal = validation['windows'][0]
    q_ms = [nominal['tasks'][name]['response_s']['mean']*1000 for name in order]
    actual_f0 = nominal['frequency']['mean']/1e6
    if abs(actual_f0-f0_hz/1e6) > 1e-6:
        raise ValueError('Validation nominal frequency differs from profile reference')
    coefficient = alpha['fit'].get('slope_W_per_MHz') if alpha['fit'].get('valid') else None
    B = [[0.0 if i == j else None for j in range(n)]+[-q_ms[i]/actual_f0] for i in range(n)]
    B.append([0.0]*n+[coefficient])
    identity = [[float(i == j) for j in range(n+1)] for i in range(n+1)]
    return dict(B_full=None, B_partial=B, C=identity, A=identity,
        B_status='PARTIAL ONLY: cross-rate normalization/equations unresolved; no full-B prediction is asserted',
        C_status='No separate identified C found. This identity is the implied observation map for y=x in the stated units.',
        C_is_identified=False, state_order=['q_'+name for name in order]+['P_VIN'],
        row_units=['ms']*n+['W'], input_order=['delta_r_'+name for name in order]+['delta_f'],
        column_units=['Hz']*n+['MHz'],
        coefficient_units=[['ms/Hz']*n+['ms/MHz'] for _ in range(n)]+[['W/Hz']*n+['W/MHz']],
        nominal_q_ms=q_ms, nominal_power_W=nominal['power']['mean'], f0_MHz=actual_f0,
        alpha_W_per_MHz=coefficient, alpha_fit_quality=alpha['fit'],
        assumed_context_switch_s=config['assumed_context_switch_s'],
        assumptions=['Zero response diagonal and zero power/rate entries are analytical assumptions, not measured zeros.',
                     'Frequency response column -q0/f0 assumes local inverse-frequency scaling.',
                     'Unknown cross-rate entries are not set to zero and not empirically refitted.',
                     'A=I is the requested analytical difference model, not the existing controller implementation.',
                     'C=I applies to y=x=[q_ms..., VIN_W]; it does not describe an RTR output mapping.',
                     'Nominal state is measured in the first validation window; alpha is from the separate sweep.'],
        execution_estimates_ms={name: profile[name]['mean_ms'] for name in order})


def format_matrix(name, matrix, row_labels, column_labels):
    lines = [name, 'rows: '+', '.join(row_labels), 'cols: '+', '.join(column_labels)]
    for row in matrix:
        lines.append('  [ '+'  '.join(f'{value: .8g}' if value is not None else '      ?     ' for value in row)+' ]')
    return '\n'.join(lines)


def matrix_text(matrix):
    return (format_matrix('B (PARTIAL; ? = unresolved)', matrix['B_partial'], matrix['state_order'], matrix['input_order'])+
        '\nrow units: '+str(matrix['row_units'])+'; input increments: '+str(matrix['column_units'])+
        '\n'+matrix['B_status']+'\n\n'+
        format_matrix('C implied by y=x (not identified)', matrix['C'], matrix['state_order'], matrix['state_order'])+
        '\n'+matrix['C_status']+'\n')


def profile_diagnostics(run, profiles):
    result = {}
    for name, profile in profiles.items():
        rows = sorted((r for r in run['jobs'] if r.get('task') == name and r.get('ok') and not r.get('warmup')), key=lambda r:r['start_s'])
        values = [r['execution_s']*1000 for r in rows]
        count = min(50, len(values)//2)
        first = st.fmean(values[:count]) if count else None
        last = st.fmean(values[-count:]) if count else None
        change = (last/first-1)*100 if first else None
        result[name] = dict(first_n=count, first_mean_ms=first, last_mean_ms=last,
                            relative_change_percent=change,
                            nonstationarity_warning=bool(change is not None and abs(change)>10),
                            mean_kept_from_all_measured_samples_ms=profile['mean_ms'],
                            note='Descriptive first/last comparison; mean retained. This is not a formal change-point or WCET test.')
    return result


def bracketed_steps(validation):
    windows = validation['windows']
    rows = []
    for i in range(1, len(windows)-1, 2):
        a, step, b = windows[i-1:i+2]
        ta, ts, tb = [(r['start_s']+r['end_s'])/2 for r in (a, step, b)]
        weight = (ts-ta)/(tb-ta)
        baseline_power=a['power']['mean']+(b['power']['mean']-a['power']['mean'])*weight
        rates = step['requested_rates_hz']
        rows.append(dict(window_id=step['window_id'], rates_hz=rates, achieved_frequency_MHz=step['frequency_MHz'],
                         power_delta_vs_adjacent_nominals_W=step['power']['mean']-baseline_power,
                         response_delta_ms={name:(step['tasks'][name]['response_s']['mean']-
                             (a['tasks'][name]['response_s']['mean']+(b['tasks'][name]['response_s']['mean']-a['tasks'][name]['response_s']['mean'])*weight))*1000
                             for name in step['tasks']},
                         note='Descriptive local nominal interpolation; not an estimated B or independent repetition.'))
    return rows


def provenance_check(runs, experiment):
    binaries, generated = {}, {}
    for mode, run in runs.items():
        for name, record in run['build']['tasks'].items():
            b, g = experiment/'bin'/name, experiment/'generated'/(name+'_worker.cu')
            binaries[mode+'/'+name] = b.is_file() and digest(b)==record['binary_sha256']
            generated[mode+'/'+name] = g.is_file() and digest(g)==record['generated_sha256']
    return dict(saved_configs_identical=all(r['config']==runs['profile']['config'] for r in runs.values()),
                build_manifests_identical=all(r['build']==runs['profile']['build'] for r in runs.values()),
                copied_binary_hash_matches=binaries, copied_generated_source_hash_matches=generated,
                qualification='These checks establish file/manifest consistency, not independent proof of compiler provenance. Original target application sources are not included in this copy. Differences from the local reconstruction were reviewed separately.')


def extra_figures(out, runs, profiles, alpha):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3,1,figsize=(10,8),sharex=True)
    for ax, name in zip(axes, profiles):
        rows=[r for r in runs['profile']['jobs'] if r.get('task')==name and r.get('ok') and not r.get('warmup')]
        ax.plot(range(1,len(rows)+1),[r['execution_s']*1000 for r in rows],'.-',ms=2,lw=.5)
        ax.axhline(profiles[name]['mean_ms'],color='tab:red',ls='--',label='all-sample mean')
        ax.set_ylabel(name+' event time (ms)');ax.legend(frameon=False);ax.grid(alpha=.2)
    axes[-1].set_xlabel('Measured standalone invocation (warmups excluded)')
    fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('standalone_profiles.'+ext),dpi=180)
    plt.close(fig)
    ts=alpha['trials']; fit=alpha['fit']
    fig, axes=plt.subplots(2,1,figsize=(9,7),gridspec_kw={'height_ratios':[2,1]})
    for kind,label,color in [('alpha','sweep trials','tab:blue'),('drift_reference','reference returns','tab:orange')]:
        selected=[r for r in ts if r['kind']==kind]
        axes[0].scatter([r['frequency_MHz'] for r in selected],[r['power']['mean'] for r in selected],label=label,c=color)
    if fit.get('valid'):
        x=[fit['frequency_min_MHz'],fit['frequency_max_MHz']]
        axes[0].plot(x,[fit['intercept_W']+fit['slope_W_per_MHz']*v for v in x],color='black',label=f'all-trial fit, R²={fit["r2"]:.3f}')
    axes[0].set(xlabel='Achieved GPU frequency (MHz)',ylabel='Time-weighted INA238 VIN power (W)');axes[0].legend(frameon=False);axes[0].grid(alpha=.2)
    refs=[r for r in ts if r['kind']=='drift_reference']; origin=ts[0]['start_s']
    axes[1].plot([(r['start_s']-origin)/60 for r in refs],[r['power']['mean'] for r in refs],'o-')
    axes[1].set(xlabel='Elapsed sweep time (min)',ylabel='846 MHz VIN mean (W)');axes[1].grid(alpha=.2)
    fig.tight_layout()
    for ext in ('png','pdf'):fig.savefig(out/('alpha_fit_and_reference_drift.'+ext),dpi=180)
    plt.close(fig)


def write_report(out, result):
    profiles, alpha = result['profiles'], result['alpha']
    fit=alpha['fit']
    lines=['# Thor experiment review', '',
           'Raw copied captures were read offline. No workload or hardware control was executed locally.', '',
           '## Capture and provenance', '',
           '| Mode | Completed | Jobs | Telemetry | Cleanup errors |', '|---|---:|---:|---:|---:|']
    for mode, r in result['capture_summary'].items():
        lines.append(f'| {mode} | {r["complete"]} | {r["jobs"]} | {r["telemetry_samples"]} | {len(r["cleanup_errors"])} |')
    lines += ['', 'Saved configs/build manifests agree across all runs. Copied generated sources and binaries match their manifests; see review.json for every check.',
              'Actual GPU temperature was available despite the saved permission to run without it. It came from sysfs for profile/alpha and tegrastats for validation.',
              'VIN is module plus carrier input, not GPU-only power. Cooling snapshots recorded PWM=80 and pwm1_enable=1; the runtime fan policy was not independently verified. nvpmodel reported 120 W. Ambient was not recorded.', '',
              '## Standalone profiles at 846 MHz', '', '| Task | Measured count | Mean (ms) | SD (ms) | p95 (ms) |', '|---|---:|---:|---:|---:|']
    for name,p in profiles.items():lines.append(f'| {name} | {p["count"]} | {p["mean_ms"]:.6f} | {p["stdev_ms"]:.6f} | {p["p95_ms"]:.6f} |')
    lines += ['', 'There were exactly 20 warmup plus 300 measured invocations per task. All per-job recorded clocks were 846 MHz.',
              '**Histogram demand is nonstationary:** its first 50 measured samples average '+f'{result["profile_diagnostics"]["hist"]["first_mean_ms"]:.3f} ms, versus {result["profile_diagnostics"]["hist"]["last_mean_ms"]:.3f} ms for the last 50. '+
              'The all-sample mean is retained; it should not be treated as a stable operating-point estimate without reviewing/repeating the profile with longer settling/warmup. The recorded GPC clock alone does not explain the timing change. No cause is inferred.',
              '![Standalone traces](standalone_profiles.png)', '', '## Fixed-rate frequency sweep', '',
              f'All {len(alpha["trials"])} windows passed the existing data-quality checks: 15 sweep trials (three at each of five levels) plus seven reference windows. Every steady 60 s window contains 375/750/1000 completed hist/stereo/MM invocations.',
              f'Fit: `VIN_W = {fit["intercept_W"]:.6f} + {fit["slope_W_per_MHz"]:.9f} * achieved_MHz`.',
              f'Alpha = **{fit["slope_mW_per_MHz"]:.6f} mW/MHz**, OLS standard error **{fit["slope_se"]*1000:.6f} mW/MHz**, R² **{fit["r2"]:.6f}**, range **315–1386 MHz**.',
              'The standard error is conditional on stationary independent trial residuals; drift weakens that assumption. The freely fitted intercept is not physical idle power.',
              f'Reference trial means span **{fit["reference_power_range_W"]:.3f} W**; `poor_linear_fit` is retained. The 585 MHz mean is below the 315 MHz mean. A single slope is only a rough description of these board-level data.',
              'The separate 15-sweep-only sensitivity fit is stored in review.json; it does not replace the primary fit.',
              '![Alpha and drift](alpha_fit_and_reference_drift.png)', '', '## Independent validation', '',
              'All 13 windows passed the existing quality checks. The 846→837 MHz step raises event-response means by approximately 0.176/0.019/0.038 ms for hist/stereo/MM. These values are consistent with a small local inverse-frequency change.',
              'VIN power is much noisier than this 9 MHz step predicts: the separate alpha implies only about −0.0185 W; neighboring-baseline power differences are much larger. Single rate steps and drifting board-level baselines do not establish or reject true zero power/rate coefficients.',
              'Source response is event time plus synthetic carry; semaphore wait is omitted. Wall response is retained in raw/analysis files and should be reviewed for task contention.',
              'The plot is an operating-point comparison at two-second completion-bin resolution, not a full one-interval state prediction. Separate y-axis scales place RT in the upper band and VIN in the lower band without clipping observations. The plot follows root plot2.py styling, but does not fit response or power coefficients to validation samples. Response predictions use only the analytical frequency column, with unknown rate effects masked. Power predictions explicitly test the assumed zero rate-to-power entries.',
              '![System validation](system_validation.png)', '', '## B and C', '', '```text', matrix_text(result['matrices']).rstrip(), '```', '',
              'B is printed as a **partial** analytical matrix: unresolved cross-rate entries are `?`/JSON null, not zero. Known zeros remain model assumptions. Frequency columns use measured nominal q and explicit ms/MHz units. No full B validation is claimed.',
              'C is the implied identity observation map for y=x in matching units, not a newly identified or deployed controller matrix. See matrices.json for assumptions and provenance.', '',
              '## Remaining work', '',
              '- Repeat the histogram profile after longer settling/warmup; retain the complete distribution.',
              '- Resolve cross-rate equations/normalization before exporting a full numeric B.',
              '- Review the VIN channel boundary and repeatability before using alpha as a high-confidence controller parameter.',
              '- Preserve all raw captures; these offline figures do not constitute additional target experiments.', '']
    (out/'review.md').write_text('\n'.join(lines))


def review(results, output=None):
    paths=[p for p in sorted(Path(results).iterdir()) if p.is_dir() and (p/'status.json').exists()]
    runs={}
    for path in paths:
        run=load_run(path); mode=run['status']['mode']
        if mode not in ('profile','alpha','validate'):continue
        if mode in runs:raise ValueError('Expected one run per mode in --results; use a directory containing the chosen three captures')
        runs[mode]=run
    if set(runs) != {'profile','alpha','validate'}:raise ValueError('Need profile, alpha and validate captures')
    original=raw_inventory([Path(r['path']) for r in runs.values()])
    if not all(r['status'].get('complete') and not r['cleanup'].get('errors') for r in runs.values()):
        raise ValueError('This combined review requires complete captures with clean cleanup; use analysis.py for incomplete runs')
    config=runs['profile']['config']
    provenance=provenance_check(runs,Path(results).parent)
    if not provenance['saved_configs_identical'] or not provenance['build_manifests_identical']:
        raise ValueError('Captured configs/builds differ: cannot combine as one experiment')
    if not all(provenance['copied_binary_hash_matches'].values()) or not all(provenance['copied_generated_source_hash_matches'].values()):
        raise ValueError('Copied source/binary hashes do not match saved manifests')
    profiles=_profile_summary(runs['profile']['jobs'],runs['profile']['windows'],config)
    alpha=_alpha_summary(runs['alpha']['jobs'],runs['alpha']['windows'],runs['alpha']['telemetry'],config)
    validation=_validation_summary(runs['validate']['jobs'],runs['validate']['windows'],runs['validate']['telemetry'],config)
    matrices=make_matrices(config,validation,alpha,profiles,runs['profile']['preflight']['reference_hz'])
    sweep=[r for r in alpha['trials'] if r['kind']=='alpha' and r['adequate']]
    result=dict(profiles=profiles,profile_diagnostics=profile_diagnostics(runs['profile'],profiles),alpha=alpha,
                alpha_sweep_only_sensitivity=linear_fit([r['frequency_MHz'] for r in sweep],[r['power']['mean'] for r in sweep]),
                validation=validation, bracketed_validation_steps=bracketed_steps(validation),matrices=matrices, provenance=provenance,
                capture_summary={mode:dict(path=r['path'],complete=r['status']['complete'],jobs=len(r['jobs']),telemetry_samples=len(r['telemetry']),
                    cleanup_errors=r['cleanup']['errors'],temperature_source=r['preflight']['temperature_source'],
                    temperature_min_C=min(x['temperature_C'] for x in r['telemetry'] if x.get('temperature_C') is not None),
                    temperature_max_C=max(x['temperature_C'] for x in r['telemetry'] if x.get('temperature_C') is not None),
                    max_telemetry_gap_s=max(b['t_s']-a['t_s'] for a,b in zip(r['telemetry'],r['telemetry'][1:])),
                    raw_errors=sum(bool(x.get('error')) for x in r['jobs']+r['telemetry'])) for mode,r in runs.items()})
    out=Path(output) if output else HERE/('review_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(parents=True,exist_ok=False)
    (out/'matrices.json').write_text(json.dumps(matrices,indent=2,allow_nan=False)+'\n')
    (out/'matrices.txt').write_text(matrix_text(matrices))
    validation['alpha_W_per_MHz']=matrices['alpha_W_per_MHz']
    plot_names=render_validation(config,runs['validate']['windows'],runs['validate']['jobs'],runs['validate']['telemetry'],validation,matrices,out)
    extra_figures(out,runs,profiles,alpha)
    after=raw_inventory([Path(r['path']) for r in runs.values()])
    if after != original:raise RuntimeError('Input files changed during review')
    result['raw_files_unchanged']=True
    result['figure_files']=plot_names
    (out/'raw_sha256.json').write_text(json.dumps(original,indent=2)+'\n')
    (out/'review.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    write_report(out,result)
    print(matrix_text(matrices))
    print('Alpha W/MHz:',alpha['fit'].get('slope_W_per_MHz'),'R²:',alpha['fit'].get('r2'))
    print('Histogram first/last samples:',result['profile_diagnostics']['hist'])
    print('Saved review:',out)
    return out


def main():
    parser=argparse.ArgumentParser(__doc__)
    default=next((p for p in (HERE/'results',HERE/'system_identification_2/results') if p.is_dir()),HERE/'results')
    parser.add_argument('--results',type=Path,default=default,help='Folder containing chosen profile, alpha and validate captures')
    parser.add_argument('--output-dir',type=Path,help='New output directory; refuses overwrite')
    args=parser.parse_args()
    review(args.results,args.output_dir)


if __name__ == '__main__':
    main()

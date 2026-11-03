"""Plan a Thor periodic frequency staircase or plot its recorded capture.

All commands here are offline. Capture uses suite.py validate with the saved plan.
"""
import argparse
import datetime as dt
import json
import math
import hashlib
import statistics as st
from pathlib import Path
import uuid

from analysis import _read_jsonl, _validation_summary, interval_summaries, _profile_summary, _alpha_summary
from plot_validation import matrix_text, make_matrices
from frozen_model import load_model
from validation_figures import render_validation
from hold_figures import render_hold_means

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text())


def plan(source_run, output, cycles=3, level_count=6, hold_intervals=4, low_hz=None, high_hz=None, dry_run=False):
    source_run=Path(source_run)
    config=read(source_run/'config.json')
    info=read(source_run/'preflight.json')
    levels=sorted(set(info['intended_frequencies_hz']))
    if low_hz is not None:levels=[f for f in levels if f>=low_hz]
    if high_hz is not None:levels=[f for f in levels if f<=high_hz]
    if cycles<1 or level_count<2 or hold_intervals<2 or len(levels)<2:
        raise ValueError('Need >=2 legal levels, >=1 cycle, and >=2 intervals per hold')
    count=min(level_count,len(levels))
    selected=[levels[round(i*(len(levels)-1)/(count-1))] for i in range(count)]
    # Endpoints occur once per cycle; adjacent cycles supply the next low plateau.
    wave=selected+selected[-2:0:-1]
    rates={t['name']:t['rate_hz'] for t in config['tasks']}
    ref=info['reference_hz']
    # Warm up, then measure a reference check; plotting uses the frozen prior q0/P0.
    frequencies=[ref,ref]+wave*cycles
    config['frequency']['reference_hz']=ref
    config['validation']['sequence']=[dict(frequency_hz=f,rates_hz=dict(rates)) for f in frequencies]
    config['validation']['discard_s']=0.
    config['validation']['measure_s']=config['interval_s']*hold_intervals
    config['periodic_validation']={
        'source_run':str(source_run),'cycles':cycles,'selected_levels_hz':selected,
        'hold_intervals':hold_intervals,'hold_s':config['validation']['measure_s'],
        'initial_reference_hold':True,'warmup_windows':1,'nominal_window_index':1,'waveform':'ascending/descending discrete staircase with endpoint plateaus',
        'timing_note':'Requested hold duration excludes small runner transition/bracketing overhead; use recorded monotonic boundaries.',
        'purpose':'Independent frequency-only periodic excitation, fixed task rates; no rate coefficients refitted.',
        'legacy_reference':'JTPC_system_validation/validation_control_period.csv: six levels, four intervals per hold, three cycles',
        'limitations':'No dithering, target preflight revalidates every level; actual RT/power shape and feasibility require target capture.'}
    if not dry_run:
        with Path(output).open('x') as file:json.dump(config,file,indent=2);file.write('\n')
    print(json.dumps(config if dry_run else dict(saved=str(output),levels_hz=selected,windows=len(frequencies),nominal_duration_s=len(frequencies)*config['validation']['measure_s']),indent=2))
    return config


def plot(run, model_path, output=None, plot_bin_seconds=None):
    run=Path(run)
    config=read(run/'config.json')
    if not config.get('periodic_validation'):
        raise ValueError('Run config has no periodic_validation plan; do not relabel old data as a periodic capture')
    if not read(run/'status.json').get('complete'):
        raise ValueError('Periodic capture incomplete; use general analysis.py for diagnosis')
    matrix, model_provenance=load_model(model_path, config)
    windows=read(run/'windows.json')
    # Preserve raw windows; exclude the declared initial warmup hold only in this view.
    warmup=config['periodic_validation'].get('warmup_windows',0)
    windows=[dict(w,kind='periodic_warmup') if i<warmup else dict(w) for i,w in enumerate(windows)]
    jobs=_read_jsonl(run/'jobs.jsonl');telemetry=_read_jsonl(run/'telemetry.jsonl')
    summaries=_validation_summary(jobs,windows,telemetry,config)
    if not summaries['windows'] or not all(w['adequate'] for w in summaries['windows']):
        raise ValueError('Some periodic windows fail data-quality checks; inspect analysis.py before plotting as complete validation')
    frequencies=[r['frequency_hz']/1e6 for r in telemetry if r.get('frequency_hz') is not None
                 and any(w.get('kind')=='validation' and w['settle_start_s'] <= r['t_s'] <= w['end_s'] for w in windows)]
    matrix, model_provenance=load_model(model_path, config, frequencies)
    summaries['alpha_W_per_MHz']=matrix['alpha_W_per_MHz']
    display = summaries
    bin_seconds = config['interval_s'] if plot_bin_seconds is None else plot_bin_seconds
    hold = config['validation']['measure_s']
    if not math.isfinite(bin_seconds) or bin_seconds < config['interval_s'] or bin_seconds > hold:
        raise ValueError('Plot bins must be finite, >= the controller interval and <= the frequency hold duration')
    if bin_seconds != config['interval_s']:
        display_config = dict(config, interval_s=bin_seconds)
        display = dict(summaries, intervals=interval_summaries(windows,jobs,telemetry,display_config))
    display = dict(display, plot_interval_s=bin_seconds)
    out=Path(output) if output else HERE/('periodic_plot_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6])
    out.mkdir(parents=True,exist_ok=False)
    figures=render_validation(config,windows,jobs,telemetry,display,matrix,out)
    figures += render_hold_means(config,windows,telemetry,summaries,matrix,out)
    (out/'matrices.json').write_text(json.dumps(matrix,indent=2)+'\n')
    (out/'matrices.txt').write_text(matrix_text(matrix))
    (out/'model_provenance.json').write_text(json.dumps(dict(**model_provenance, recalibrated_on_periodic_data=False),indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(run=str(run),model=model_provenance,validation=summaries,figures=figures, plot_bin_seconds=bin_seconds, native_interval_seconds=config['interval_s'], model_recalibrated=False),indent=2,allow_nan=False)+'\n')
    print(matrix_text(matrix));print('Frozen model:', model_provenance);print('Saved periodic figures:',out)
    return out


def export_model(profile_run, alpha_run, output):
    profile_run,alpha_run=Path(profile_run),Path(alpha_run)
    pc,ac=read(profile_run/'config.json'),read(alpha_run/'config.json')
    for key in ('tasks','power','interval_s','conditions'):
        if pc[key] != ac[key]:raise ValueError('Profile/alpha settings differ: '+key)
    for run in (profile_run,alpha_run):
        if not read(run/'status.json').get('complete'):raise ValueError('Incomplete capture: '+str(run))
    profiles=_profile_summary(_read_jsonl(profile_run/'jobs.jsonl'),read(profile_run/'windows.json'),pc)
    if set(profiles)!={t['name'] for t in pc['tasks']} or not all(p['complete'] for p in profiles.values()):
        raise ValueError('Missing or incomplete standalone profiles')
    alpha=_alpha_summary(_read_jsonl(alpha_run/'jobs.jsonl'),read(alpha_run/'windows.json'),_read_jsonl(alpha_run/'telemetry.jsonl'),ac)
    if not alpha['fit'].get('valid'):raise ValueError('Alpha could not be fitted')
    ref=read(alpha_run/'preflight.json')['reference_hz']
    if read(profile_run/'preflight.json')['reference_hz']!=ref:raise ValueError('Reference frequencies differ')
    refs=[t for t in alpha['trials'] if t['adequate'] and t['kind']=='drift_reference' and t['requested_frequency_hz']==ref]
    if not refs:raise ValueError('No adequate nominal reference trials')
    nominal=dict(adequate=True,frequency={'mean':st.fmean(t['frequency']['mean'] for t in refs)},
                 power={'mean':st.fmean(t['power']['mean'] for t in refs)},
                 tasks={task['name']:{'response_s':{'mean':st.fmean(t['tasks'][task['name']]['response_s']['mean'] for t in refs)}} for task in ac['tasks']})
    matrix=make_matrices(ac,{'windows':[nominal]},alpha,profiles,ref)
    sources=[run/name for run in (profile_run,alpha_run) for name in ('config.json','windows.json','jobs.jsonl','telemetry.jsonl','status.json','preflight.json','build_manifest.json') if (run/name).exists()]
    bundle=dict(schema_version=1,matrix=matrix,training_config=ac,
                source_files_sha256={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                notes=['Fresh profile/alpha export. No periodic validation data used.',
                       'Nominal q/P are means over adequate reference trials in the identification sweep.',
                       'B remains partial; unresolved cross-rate entries are not fitted or set to zero.',
                       'Alpha quality flags and profile distributions are retained; export does not assert model validity.'])
    with Path(output).open('x') as file:json.dump(bundle,file,indent=2,allow_nan=False);file.write('\n')
    print(matrix_text(matrix));print('Saved model:',output)
    return bundle


def main():
    parser=argparse.ArgumentParser(__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('plan');p.add_argument('--source-run',type=Path,required=True);p.add_argument('--out',type=Path,default=HERE/'config.periodic.json')
    p.add_argument('--cycles',type=int,default=3);p.add_argument('--levels',type=int,default=6);p.add_argument('--hold-intervals',type=int,default=4)
    p.add_argument('--low-hz',type=int);p.add_argument('--high-hz',type=int);p.add_argument('--dry-run',action='store_true')
    p=sub.add_parser('plot');p.add_argument('--run',type=Path,required=True);p.add_argument('--model',type=Path,required=True,help='Frozen identification_model.json exported from the previous analysis');p.add_argument('--output-dir',type=Path);p.add_argument('--plot-bin-seconds',type=float,help='Display-only averaging; native capture/control interval and frozen model stay unchanged')
    p=sub.add_parser('export-model');p.add_argument('--profile-run',type=Path,required=True);p.add_argument('--alpha-run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.mode=='plan':plan(args.source_run,args.out,args.cycles,args.levels,args.hold_intervals,args.low_hz,args.high_hz,args.dry_run)
    elif args.mode=='export-model':export_model(args.profile_run,args.alpha_run,args.out)
    else:plot(args.run,args.model,args.output_dir,args.plot_bin_seconds)


if __name__=='__main__':main()

"""Whole-hold measured means and frozen-model comparisons, with temporal SD."""
import csv
import json
from pathlib import Path
from hold_statistics import time_weighted_stats
from validation_figures import partial_prediction, rounded_ticks
from matplotlib.ticker import FormatStrFormatter

def hold_rows(config, windows, telemetry, summaries, matrix):
    order=[t['name'] for t in config['tasks']]
    nominal_rates={t['name']:t['rate_hz'] for t in config['tasks']}
    by_id={r['window_id']:r for r in summaries.get('windows',[])}
    rows=[]
    for window in windows:
        if window.get('kind')!='validation':continue
        summary=by_id.get(window['id'])
        if not summary:continue
        start,end=window['start_s'],window['end_s']
        power=time_weighted_stats(telemetry,'power_W',start,end,config['telemetry']['max_gap_s'])
        frequency=time_weighted_stats(telemetry,'frequency_hz',start,end,config['telemetry']['max_gap_s'])
        valid=summary.get('adequate',False) and power['valid'] and frequency['valid']
        q=[summary['tasks'][task]['response_s']['mean']*1000
           if summary['tasks'][task]['response_s']['mean'] is not None else None for task in order]
        predicted=partial_prediction(matrix['B_partial'],matrix['nominal_q_ms'],matrix['nominal_power_W'],
                     matrix['alpha_W_per_MHz'],frequency['mean']/1e6,matrix['f0_MHz'],
                     window['rates_hz'],nominal_rates,order) if valid else None
        rows.append(dict(index=len(rows),window_id=window['id'],start_s=start,end_s=end,duration_s=end-start,
            requested_frequency_MHz=window['requested_frequency_hz']/1e6,
            achieved_frequency_MHz=frequency['mean']/1e6 if frequency['mean'] is not None else None,
            valid=valid,power=power,
            mean_q_ms=q,mean_average_q_ms=sum(q)/len(q) if all(v is not None for v in q) else None,
            predicted_q_ms=predicted['q_ms'] if predicted else None,
            predicted_average_q_ms=sum(predicted['q_ms'])/len(q) if predicted and all(v is not None for v in predicted['q_ms']) else None,
            predicted_power_W=predicted['power_W'] if predicted else None,
            task_counts={name:summary['tasks'][name]['count'] for name in order}))
    return rows


def render_hold_means(config,windows,telemetry,summaries,matrix,out_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=Path(out_dir)
    rows=hold_rows(config,windows,telemetry,summaries,matrix)
    if not rows:return []
    valid=[r for r in rows if r['valid']]
    if not valid:return []
    x=[r['index'] for r in rows]
    def values(key):return [r[key] if r['valid'] else None for r in rows]
    measured=values('mean_average_q_ms');predicted=values('predicted_average_q_ms')
    power=[r['power']['mean'] if r['valid'] else None for r in rows]
    power_prediction=values('predicted_power_W')
    vx=[r['index'] for r in valid];vp=[r['power']['mean'] for r in valid];sd=[r['power']['stdev'] for r in valid]
    durations={round(r['duration_s'],6) for r in valid}
    duration_label=f'{next(iter(durations)):g} s' if len(durations)==1 else 'recorded window'
    fig,rt=plt.subplots(figsize=(13,7));pw=rt.twinx()
    rt.plot(x,predicted,color=(0,.65,1,.5),lw=7,label='Estimated RT')
    rt.plot(x,measured,'ko-',ms=4,lw=1.3,label='Measured RT')
    pw.plot(x,power_prediction,color=(1,.2,.2,.5),lw=7,label='Estimated power')
    pw.plot(x,power,'ks-',ms=4,lw=1.2,label='Measured power')
    pw.errorbar(vx,vp,yerr=sd,fmt='none',ecolor='.55',elinewidth=1,capsize=3,
                zorder=0)
    rt.set(xlabel=f'Test period (one {duration_label} mean per point)',ylabel='Response Time (ms)')
    pw.set_ylabel('Power (W)')
    qv=[v for v in measured+predicted if v is not None];pv=[m+d for m,d in zip(vp,sd)]+[m-d for m,d in zip(vp,sd)]+[v for v in power_prediction if v is not None]
    lo,hi=min(qv),max(qv);span=max(hi-lo,.01);rt.set_ylim(lo-1.3*span,hi+.15*span)
    #rounded_ticks(rt,lo,hi)

    rt.set_yticks([5, 10, 15, 20])
    rt.yaxis.set_major_formatter(FormatStrFormatter('%.0f'))

    lo,hi=min(pv),max(pv);span=max(hi-lo,.01);pw.set_ylim(lo-.15*span,hi+1.3*span)
    #rounded_ticks(pw,lo,hi)

    # Leave enough space between the reference-sized tick labels.
    pw.set_yticks([18, 22, 26])
    pw.yaxis.set_major_formatter(FormatStrFormatter('%.0f'))

    for ax in (rt,pw):
        # Match reference/plot2.py so text remains readable at document width.
        ax.tick_params(labelsize=30);ax.spines['top'].set_visible(False)
        ax.xaxis.label.set(fontsize=30,fontweight='bold');ax.yaxis.label.set(fontsize=30,fontweight='bold')
        plt.setp(ax.get_xticklabels()+ax.get_yticklabels(),fontweight='bold')
    rt.grid(alpha=.2)
    pw.grid(alpha=.2)
    h,l=rt.get_legend_handles_labels();h2,l2=pw.get_legend_handles_labels()
    rt.legend(h+h2,l+l2,loc='lower center',bbox_to_anchor=(.5,1.02),ncol=2,frameon=False,fontsize=26)
    fig.tight_layout(rect=(0,.04,1,.91))
    names=[]
    for suffix in ('png','pdf'):
        filename='system_validation_hold_means.'+suffix;fig.savefig(out/filename,dpi=300,bbox_inches='tight');names.append(filename)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,5))
    ax.errorbar(vx,vp,yerr=sd,fmt='ko-',lw=1,capsize=3,ecolor='.65',label='Hold mean ± temporal SD (not CI)')
    ax.plot(x,power_prediction,color='tab:red',lw=2,label='Estimated power')
    ax.set(xlabel=f'Test period',ylabel='Power (W)',title='Power averaged over each actual frequency hold')
    ax.grid(alpha=.2);ax.legend(frameon=False);fig.tight_layout()
    for suffix in ('png','pdf'):
        filename='power_hold_means.'+suffix;fig.savefig(out/filename,dpi=180,bbox_inches='tight');names.append(filename)
    plt.close(fig)
    (out/'hold_means.json').write_text(json.dumps(dict(rows=rows,
        averaging='Timestamp-weighted mean of piecewise-linear telemetry over each exact recorded start/end window. Warmup windows excluded.',
        error_bars='Time-weighted population temporal standard deviation within each hold; not standard error or confidence interval.',
        model_recalibrated=False),indent=2,allow_nan=False)+'\n')
    with (out/'hold_means.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['index','window_id','start_s','end_s','duration_s','requested_frequency_MHz','achieved_frequency_MHz','valid','mean_power_W','temporal_sd_W','predicted_power_W','mean_average_q_ms','predicted_average_q_ms'])
        writer.writeheader()
        for r in rows:
            writer.writerow({**{k:r[k] for k in writer.fieldnames if k in r},'mean_power_W':r['power']['mean'],'temporal_sd_W':r['power']['stdev']})
    return names

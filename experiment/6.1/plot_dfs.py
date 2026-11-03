# Extracted from the archived notebook; cell number is recorded in docs/plot_sources.json.
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parent)
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
################ interrupt DFS
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib.lines import Line2D

plt.rcParams["font.family"] = "Arial"
plt.rcParams["font.weight"] = "normal"
plt.rcParams["font.weight"] = "normal"


# --------- CONFIG ----------
root = Path("logs/DFS_interrupt/hist_stereo_mm_test/")  
#root = Path("Proposed_bounds/histogram_converted_stereodisparity_converted_mm_converted/") 
#oot = Path("LQR/hist_stereo_mm/") 
setpoints = [0.90]
p_setpoint = [11000]
change_period = 54


warmup_skip = 0         
max_periods = 100  
save_path = Path("Figures/replotted")
task_names = ["hist", "stereo", "mm"]
task_colors = ['tab:blue', 'tab:orange', 'tab:red']

# Styling constants
FIGSIZE = (15, 4) # Slightly taller/wider to prevent overlap
FIGSIZE = (10, 8)
FIGSIZE = (8, 6)
LABEL_FONTSIZE = 16
TICK_FONTSIZE = 14

LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 16

LINEWIDTH = 2.0
# ---------------------------

def read_data(filepath: Path):
    if not filepath.exists(): return None
    vals = []
    with filepath.open("r") as f:
        for line in f:
            s = line.strip()
            if not s: continue
            try: vals.append(float(s))
            except ValueError: continue
    return vals if vals else None

def slice_idx(data, start, stop):
    if data is None: return None
    n = len(data)
    a = min(max(start, 0), n)
    b = min(max(stop, 0), n)
    return np.asarray(data[a:b], dtype=float)

plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial']})

for sp in setpoints:
    for power in p_setpoint:
        run_dir = root / f"setpoint_{sp:.2f}_{sp:.2f}_{sp:.2f}"
        if not run_dir.exists() or not any(run_dir.iterdir()):
            print(f'SKIP missing/empty: {run_dir}')
            continue
        #run_dir = root / f"setpoint_{sp:.2f}"
        if not run_dir.exists() or not any(run_dir.iterdir()):
            print(f'SKIP missing/empty: {run_dir}')
            continue
        print(run_dir)
        data = {name: {} for name in task_names}
        for i, name in enumerate(task_names, 1):
            t_id = f"t{i}"
            data[name]['rtr'] = slice_idx(read_data(run_dir / f"DFS_{t_id}_rtr.txt"), warmup_skip, max_periods)
            data[name]['dl']  = slice_idx(read_data(run_dir / f"DFS_{t_id}_deadline.txt"), warmup_skip, max_periods)
            data[name]['per'] = slice_idx(read_data(run_dir / f"DFS_{t_id}_period.txt"), warmup_skip, max_periods)
            data[name]['low'] = slice_idx(read_data(run_dir / f"DFS_{t_id}_lowerperiodbound.txt"), warmup_skip, max_periods)
            data[name]['high']= slice_idx(read_data(run_dir / f"DFS_{t_id}_higherperiodbound.txt"), warmup_skip, max_periods)

        pwrs = slice_idx(read_data(run_dir / "DFS_finalpowervalues.txt"), warmup_skip, max_periods)

        fig, axs = plt.subplots(2, 2, figsize=FIGSIZE)
        axs = axs.flatten()
        
        # (1) RTR
        ax = axs[0]
        ax.axhline(y=sp, color='black', linestyle='--', linewidth=1.5, label="Set point")
        for name, color in zip(task_names, task_colors):
            if data[name]['rtr'] is not None:
                ax.plot(data[name]['rtr'], linewidth=LINEWIDTH, label=name, color=color)
        ax.set_ylabel("RTR", fontsize=LABEL_FONTSIZE, fontweight='bold')
        ax.set_xlabel("Control Period \n(a)", fontsize=LABEL_FONTSIZE, fontweight='bold')
        ax.set_ylim(0.5, 1.1)

        # (2) Deadline
        ax = axs[1]
        for name, color in zip(task_names, task_colors):
            if data[name]['dl'] is not None:
                ax.plot(data[name]['dl'], linewidth=LINEWIDTH, color=color)
        ax.set_ylabel("DMR (%)", fontsize=LABEL_FONTSIZE, fontweight='bold')
        ax.set_xlabel("Control Period \n(b)", fontsize=LABEL_FONTSIZE, fontweight='bold')

        ax = axs[2]
        for name, color in zip(task_names, task_colors):
            if data[name]['per'] is not None:
                ax.plot(data[name]['per'], linewidth=LINEWIDTH, color=color)
            if data[name]['low'] is not None:
                #ax.plot(data[name]['low'], ':', alpha=0.6, linewidth=1.2, color=color)
                pass
            if data[name]['high'] is not None:
                #ax.plot(data[name]['high'], ':', alpha=0.6, linewidth=1.2, color=color)
                pass
        ax.set_ylabel("Period (ms)", fontsize=LABEL_FONTSIZE, fontweight='bold')
        ax.set_xlabel("Control Period \n(c)", fontsize=LABEL_FONTSIZE, fontweight='bold')

        # (4) Power
        ax = axs[3]
        if pwrs is not None:
            ax.plot(pwrs, linewidth=LINEWIDTH, color='tab:green', label='Power')
        print(np.mean(pwrs))
        ax.set_ylabel("Power (mW)", fontsize=LABEL_FONTSIZE, fontweight='bold')
        ax.set_xlabel("Control Period \n(d)", fontsize=LABEL_FONTSIZE, fontweight='bold')
        ax.set_ylim([9000,16000])
        ax.axhline(y=power, color='black', linestyle='--', linewidth=1.5, label="Set point")
        


        # Global Styling
        for ax in axs:
            ax.axvline(x=change_period, color='black', linestyle=':', linewidth=1.5)
            ax.tick_params(axis='both', labelsize=TICK_FONTSIZE)
            for tick in ax.get_xticklabels(): tick.set_fontweight("bold")
            for tick in ax.get_yticklabels(): tick.set_fontweight("bold")
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(True, alpha=0.2)
            ax.set_xlim([0,100])


        handles, labels = axs[0].get_legend_handles_labels() # Tasks + Setpoint
        power_handle = Line2D([0], [0], color='tab:green', linewidth=LINEWIDTH)
        handles.append(power_handle)
        labels.append("Power")
#         bound_handle = Line2D([0], [0], color='gray', linestyle=':', linewidth=1.2, alpha=0.8)
#         handles.append(bound_handle)
#         labels.append("Bounds")

        fig.legend(
            handles, 
            labels, 
            loc='upper center', 
            bbox_to_anchor=(0.5, 0.97),  
            #ncol=len(labels), 
            ncol=3, 
            frameon=False, 
            prop={ 'size': LEGEND_FONTSIZE} 
        )   
        plt.tight_layout(rect=[0, 0, 1, 0.85]) 

        fig_path = Path("Figures/replotted")
        fig_path.mkdir(parents=True, exist_ok=True)
        save_path.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path /f"mm_interrupt_DFS_{power}_{sp:.2f}.pdf", bbox_inches='tight')
        plt.close("all")

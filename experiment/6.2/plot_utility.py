# Extracted from the archived notebook; cell number is recorded in docs/plot_sources.json.
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parent)
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
# JTPC vs FC-GPU vs DFS Task Utility Barplot
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# ---------- FONT / STYLE ----------
plt.rcParams.update({
    "font.family": "Arial",
    "font.weight": "normal",
    "axes.labelweight": "bold",
    "axes.titleweight": "bold",
    "axes.titlesize": 16,
    "legend.fontsize": 12,
    "axes.labelsize": 16,
    "xtick.labelsize": 16,
    "ytick.labelsize": 16,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

# ---------------- CONFIG ----------------
LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 12

root = Path("logs/main_temp")

f_root = root / "FC" / "hist_stereo_mm"
l_root = root / "JTPC" / "hist_stereo_mm"
d_root = root / "DFS" / "hist_stereo_mm"

power = [11000, 11500, 12000, 12500, 13000]
rtr = 0.90

save_path = Path("Figures/replotted")

# Initial periods in ms for hist, stereo, mm
initial_periods = {
    1: 160.0,
    2: 80.0,
    3: 60.0,
}

colors = ["black", "#4E79A7", "#F28E2B", "#59A14F"]
hatches = ["", "//", "oo", "**"]
names = ["Initial rate", "JTPC", "FC-GPU", "DFS-only"]

# ---------------- HELPERS ----------------
def read_data(filepath: Path):
    if not filepath.exists():
        print(f"Missing: {filepath}")
        return np.array([])
    try:
        return np.loadtxt(filepath)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return np.array([])


def find_setpoint_dir(root_dir: Path, p_sp: int, rtr_sp: float):
    candidates = [
        root_dir / f"setpoint_{p_sp}_{rtr_sp:.2f}_{rtr_sp:.2f}_{rtr_sp:.2f}",
        root_dir / f"setpoint_{p_sp}_0.90_0.90_0.90",
    ]

    for c in candidates:
        if c.exists():
            return c

    print(f"No directory found for {root_dir}, power={p_sp}, rtr={rtr_sp:.2f}")
    return None


def task_utility_for_case(root_dir: Path, prefix: str, p_sp: int, rtr_sp: float):
    run_dir = find_setpoint_dir(root_dir, p_sp, rtr_sp)

    if run_dir is None:
        return np.nan

    task_means = []

    for task_id, init_period in initial_periods.items():
        period_file = run_dir / f"{prefix}_t{task_id}_period.txt"
        period = read_data(period_file)

        if period.size == 0:
            continue

        period = period[np.isfinite(period)]
        period = period[period > 0]

        if period.size == 0:
            continue

        # Normalized task utility / rate:
        # init_period / current_period
        util = init_period / period
        task_means.append(float(np.mean(util)))

    if len(task_means) == 0:
        return np.nan

    return float(np.mean(task_means))


# ---------------- COLLECT ----------------
lqr_group_means = []
fc_group_means = []
dfs_group_means = []
initial_group_means = []

for p_sp in power:
    print("Power:", p_sp)

    l_mean = task_utility_for_case(l_root, "LQR", p_sp, rtr)
    f_mean = task_utility_for_case(f_root, "FC_GPU", p_sp, rtr)
    d_mean = task_utility_for_case(d_root, "DFS", p_sp, rtr)

    lqr_group_means.append(l_mean)
    fc_group_means.append(f_mean)
    dfs_group_means.append(d_mean)
    initial_group_means.append(1.0)

    print(f"  JTPC    task utility={l_mean:.3f}")
    print(f"  FC-GPU  task utility={f_mean:.3f}")
    print(f"  DFS     task utility={d_mean:.3f}")

lqr_group_means = np.array(lqr_group_means)
fc_group_means = np.array(fc_group_means)
dfs_group_means = np.array(dfs_group_means)
initial_group_means = np.array(initial_group_means)

power_w = [p / 1000.0 for p in power]

# ---------------- PLOT ----------------
fig, ax = plt.subplots(figsize=(4, 3))

x = np.arange(len(power_w)) * 0.82
bar_width = 0.15

all_means = [
    initial_group_means,
    lqr_group_means,
    fc_group_means,
    dfs_group_means,
]

for i in range(4):
    ax.bar(
        x + (i - 1.5) * bar_width,
        all_means[i],
        bar_width,
        color=colors[i],
        hatch=hatches[i],
        edgecolor="black",
        linewidth=0.5,
        label=names[i],
    )

ax.set_xlabel("Power Set point (W)", fontsize=LABEL_FONTSIZE, fontweight="bold")
ax.set_ylabel("Task Utility", fontsize=LABEL_FONTSIZE, fontweight="bold")

ax.set_xticks(x)
ax.set_xticklabels([f"{p:g}" for p in power_w], fontweight="bold")

ax.grid(axis="y", linestyle="--", alpha=0.45)

ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

ax.spines["left"].set_color("gray")
ax.spines["left"].set_linewidth(0.6)

ax.spines["bottom"].set_color("gray")
ax.spines["bottom"].set_linewidth(0.6)

handles, labels = ax.get_legend_handles_labels()

fig.legend(
    handles,
    labels,
    loc="upper center",
    bbox_to_anchor=(0.5, 1.03),
    ncol=4,
    frameon=False,
    prop={"size": LEGEND_FONTSIZE},
    columnspacing=0.7,
    handlelength=1.1,
    handletextpad=0.35,
    borderaxespad=0.0,
)

ax.set_ylim([0.5, 1.4])
ax.set_yticks([0.6,0.8,1.0, 1.2, 1.4])

plt.xticks(fontsize=TICK_FONTSIZE, fontweight="bold")
plt.yticks(fontsize=TICK_FONTSIZE, fontweight="bold")

plt.tight_layout(rect=[0, 0, 1, 0.93])

save_path.mkdir(parents=True, exist_ok=True)

out_pdf = save_path / "jetson_task_utility_barplot.pdf"
out_png = save_path / "jetson_task_utility_barplot.png"

plt.savefig(
    out_pdf,
    dpi=300,
    bbox_inches="tight",
    format="pdf",
)

plt.savefig(
    out_png,
    dpi=300,
    bbox_inches="tight",
    format="png",
)

plt.close("all")

print("Saved plot to:", out_pdf)
print("Saved plot to:", out_png)

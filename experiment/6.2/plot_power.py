# Extracted from the archived notebook; cell number is recorded in docs/plot_sources.json.
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parent)
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
# LQR vs FC vs DFS Power Revision
# Single-degree-of-freedom slice:
# Fixed RTR setpoint = 0.90, sweep power setpoint.

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
    "svg.fonttype": "none",
    "ps.fonttype": 42,
})

# ---------------- CONFIG ----------------
LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 12

# Use adaptive FC-GPU log.
l_root = Path("logs/Full_LQR/hist_stereo_mm/")
f_root = Path("logs/Full_FC/hist_stereo_mm/")
d_root = Path("logs/Full_DFS/hist_stereo_mm/")

power = [11000, 11500, 12000, 12500, 13000]

# Fixed RTR point for power sweep.
FIXED_RTR = 0.90

save_path = Path("Figures")

colors = ["black", "#4E79A7", "#F28E2B", "#59A14F"]
hatches = ["", "//", "oo", "**"]
names = ["Set point", "JTPC", "FC-GPU", "DFS-only"]

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


def safe_slice(arr):
    if arr.size == 0:
        return arr
    return arr[100:-1] if arr.size > 101 else arr


def find_setpoint_dir(root: Path, rtr_sp: float, power_sp: int):
    run_dir = root / f"setpoint_{power_sp}_{rtr_sp:.2f}_{rtr_sp:.2f}_{rtr_sp:.2f}"
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    return run_dir



def avg_power_for_case(root: Path, prefix: str, rtr_sp: float, power_sp: int):
    run_dir = find_setpoint_dir(root, rtr_sp, power_sp)

    if run_dir is None:
        return np.nan, np.nan

    power_reading = read_data(run_dir / f"{prefix}_finalpowervalues.txt")
    power_reading = safe_slice(power_reading)

    if power_reading.size == 0:
        return np.nan, np.nan

    return float(np.mean(power_reading)), float(np.std(power_reading))


# ---------------- COLLECT ----------------
lqr_group_means = []
lqr_group_stds = []

fc_group_means = []
fc_group_stds = []

dfs_group_means = []
dfs_group_stds = []

setpoint_group_means = []
setpoint_group_stds = []

for p_sp in power:
    print(f"Power setpoint: {p_sp / 1000:.1f}W, fixed RTR: {FIXED_RTR:.2f}")

    l_mean, l_std = avg_power_for_case(l_root, "LQR", FIXED_RTR, p_sp)
    f_mean, f_std = avg_power_for_case(f_root, "FC_GPU", FIXED_RTR, p_sp)
    d_mean, d_std = avg_power_for_case(d_root, "DFS", FIXED_RTR, p_sp)

    lqr_group_means.append(l_mean)
    lqr_group_stds.append(l_std)

    fc_group_means.append(f_mean)
    fc_group_stds.append(f_std)

    dfs_group_means.append(d_mean)
    dfs_group_stds.append(d_std)

    setpoint_group_means.append(float(p_sp))
    setpoint_group_stds.append(0.0)

    print("  JTPC:", l_mean)
    print("  FC-GPU:", f_mean)
    print("  DFS-only:", d_mean)

lqr_group_means = np.array(lqr_group_means)
lqr_group_stds = np.array(lqr_group_stds)

fc_group_means = np.array(fc_group_means)
fc_group_stds = np.array(fc_group_stds)

dfs_group_means = np.array(dfs_group_means)
dfs_group_stds = np.array(dfs_group_stds)

setpoint_group_means = np.array(setpoint_group_means)
setpoint_group_stds = np.array(setpoint_group_stds)

# ---------------- CONVERT mW TO W ----------------
lqr_group_means = lqr_group_means / 1000.0
lqr_group_stds = lqr_group_stds / 1000.0

fc_group_means = fc_group_means / 1000.0
fc_group_stds = fc_group_stds / 1000.0

dfs_group_means = dfs_group_means / 1000.0
dfs_group_stds = dfs_group_stds / 1000.0

setpoint_group_means = setpoint_group_means / 1000.0
setpoint_group_stds = setpoint_group_stds / 1000.0

power_w = [p / 1000.0 for p in power]

# ---------------- PLOT ----------------
fig, ax = plt.subplots(figsize=(4, 3))

x = np.arange(len(power_w)) * 0.82
bar_width = 0.15

all_means = [
    setpoint_group_means,
    lqr_group_means,
    fc_group_means,
    dfs_group_means,
]

all_stds = [
    setpoint_group_stds,
    lqr_group_stds,
    fc_group_stds,
    dfs_group_stds,
]

for i in range(4):
    ax.bar(
        x + (i - 1.5) * bar_width,
        all_means[i],
        bar_width,
        yerr=all_stds[i],
        color=colors[i],
        hatch=hatches[i],
        edgecolor="black",
        linewidth=0.5,
        label=names[i],
        error_kw=dict(
            elinewidth=0.8,
            capsize=2,
            capthick=0.8,
        ),
    )

ax.set_xlabel("Power Set point (W)", fontsize=LABEL_FONTSIZE, fontweight="bold")
ax.set_ylabel("Average Power (W)", fontsize=LABEL_FONTSIZE, fontweight="bold")

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

ax.set_ylim([9.5, 13.3])
ax.set_yticks([10, 11, 12, 13])

plt.xticks(fontsize=TICK_FONTSIZE, fontweight="bold")
plt.yticks(fontsize=TICK_FONTSIZE, fontweight="bold")

plt.tight_layout(rect=[0, 0, 1, 0.93])

save_path.mkdir(parents=True, exist_ok=True)

out_pdf = save_path / "fig7b_power_RTR090.pdf"
out_png = save_path / "fig7b_power_RTR090.png"

plt.savefig(out_pdf, dpi=600, bbox_inches="tight", format="pdf")
plt.savefig(out_png, dpi=600, bbox_inches="tight", format="png")

plt.savefig(out_pdf.with_suffix(".svg"), bbox_inches="tight", format="svg")
plt.close("all")

print("Saved plot to:", out_pdf)
print("Saved plot to:", out_png)
import json
statistics = {"fixed_rtr": FIXED_RTR, "power_mw": power,
              "window": "arr[100:-1] if size>101 else all", "std_ddof": 0,
              "JTPC": {"mean_w": lqr_group_means.tolist(), "std_w": lqr_group_stds.tolist()},
              "FC-GPU": {"mean_w": fc_group_means.tolist(), "std_w": fc_group_stds.tolist()},
              "DFS-only": {"mean_w": dfs_group_means.tolist(), "std_w": dfs_group_stds.tolist()}}
(save_path / "fig7b_statistics.json").write_text(json.dumps(statistics, indent=2))


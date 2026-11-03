# Extracted from the archived notebook; cell number is recorded in docs/plot_sources.json.
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parent)
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
# LQR vs FC vs DFS RTR Revision
# Single-degree-of-freedom slice:
# Fixed power setpoint = 11W, sweep RTR setpoint.

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

l_root = Path("logs/Full_LQR/hist_stereo_mm/")
f_root = Path("logs/Full_FC/hist_stereo_mm/")
d_root = Path("logs/Full_DFS/hist_stereo_mm/")

setpoints = [0.70, 0.75, 0.80, 0.85, 0.90]

# Fixed power point for RTR sweep.
FIXED_POWER = 11000  # 11W

save_path = Path("Figures/replotted")

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
    """
    Remove invalid zero padding/shutdown tail, then remove a small early transient.
    This avoids the old arr[100:-1] behavior, which can accidentally keep only zeros.
    """
    if arr.size == 0:
        return arr

    arr = arr[np.isfinite(arr)]
    arr = arr[arr > 0]

    if arr.size == 0:
        return arr

    # Drop early transient conservatively.
    start = min(20, max(0, arr.size // 5))
    return arr[start:]


def find_setpoint_dir(root: Path, rtr_sp: float, power_sp: int):
    candidates = [
        root / f"setpoint_{power_sp}_{rtr_sp:.2f}_{rtr_sp:.2f}_{rtr_sp:.2f}",
        root / f"setpoint_{rtr_sp:.2f}",
    ]

    for c in candidates:
        if c.exists():
            return c

    print(f"No directory found for {root}, RTR={rtr_sp:.2f}, power={power_sp}")
    return None


def avg_rtr_for_case(root: Path, prefix: str, rtr_sp: float, power_sp: int):
    run_dir = find_setpoint_dir(root, rtr_sp, power_sp)

    if run_dir is None:
        return np.nan, np.nan

    t1 = safe_slice(read_data(run_dir / f"{prefix}_t1_rtr.txt"))
    t2 = safe_slice(read_data(run_dir / f"{prefix}_t2_rtr.txt"))
    t3 = safe_slice(read_data(run_dir / f"{prefix}_t3_rtr.txt"))

    n = min(len(t1), len(t2), len(t3))

    if n == 0:
        return np.nan, np.nan

    avg_trace = (t1[:n] + t2[:n] + t3[:n]) / 3.0

    return float(np.mean(avg_trace)), float(np.std(avg_trace))


# ---------------- COLLECT ----------------
setpoint_group_means = []
setpoint_group_stds = []

lqr_group_means = []
lqr_group_stds = []

fc_group_means = []
fc_group_stds = []

dfs_group_means = []
dfs_group_stds = []

for rtr_sp in setpoints:
    print(f"RTR setpoint: {rtr_sp:.2f}, fixed power: {FIXED_POWER / 1000:.1f}W")

    l_mean, l_std = avg_rtr_for_case(l_root, "LQR", rtr_sp, FIXED_POWER)
    f_mean, f_std = avg_rtr_for_case(f_root, "FC_GPU", rtr_sp, FIXED_POWER)
    d_mean, d_std = avg_rtr_for_case(d_root, "DFS", rtr_sp, FIXED_POWER)

    setpoint_group_means.append(rtr_sp)
    setpoint_group_stds.append(0.0)

    lqr_group_means.append(l_mean)
    lqr_group_stds.append(l_std)

    fc_group_means.append(f_mean)
    fc_group_stds.append(f_std)

    dfs_group_means.append(d_mean)
    dfs_group_stds.append(d_std)

    print("  JTPC:", l_mean)
    print("  FC-GPU:", f_mean)
    print("  DFS-only:", d_mean)

setpoint_group_means = np.array(setpoint_group_means)
setpoint_group_stds = np.array(setpoint_group_stds)

lqr_group_means = np.array(lqr_group_means)
lqr_group_stds = np.array(lqr_group_stds)

fc_group_means = np.array(fc_group_means)
fc_group_stds = np.array(fc_group_stds)

dfs_group_means = np.array(dfs_group_means)
dfs_group_stds = np.array(dfs_group_stds)

# ---------------- PLOT ----------------
fig, ax = plt.subplots(figsize=(4, 3))

x = np.arange(len(setpoints)) * 0.82
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

ax.set_xlabel("RTR Set point", fontsize=LABEL_FONTSIZE, fontweight="bold")
ax.set_ylabel("Average RTR", fontsize=LABEL_FONTSIZE, fontweight="bold")

ax.set_xticks(x)
ax.set_xticklabels([f"{sp:.2f}" for sp in setpoints], fontweight="bold")

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

# Diagnostic mode for 11W:
# If DFS explodes, this lets you see the real value instead of silently clipping it.
valid_means = np.concatenate([
    lqr_group_means[np.isfinite(lqr_group_means)],
    fc_group_means[np.isfinite(fc_group_means)],
    dfs_group_means[np.isfinite(dfs_group_means)],
    setpoint_group_means[np.isfinite(setpoint_group_means)],
])

if valid_means.size > 0:
    ymax = max(1.0, float(np.max(valid_means)) * 1.10)
    ax.set_ylim([0.5, 1])
else:
    ax.set_ylim([0.5, 1.0])

plt.xticks(fontsize=TICK_FONTSIZE, fontweight="bold")
plt.yticks(fontsize=TICK_FONTSIZE, fontweight="bold")

plt.tight_layout(rect=[0, 0, 1, 0.93])

save_path.mkdir(parents=True, exist_ok=True)

out_pdf = save_path / "jetson_rtr_barplot_11W.pdf"
out_png = save_path / "jetson_rtr_barplot_11W.png"

plt.savefig(out_pdf, dpi=300, bbox_inches="tight", format="pdf")
plt.savefig(out_png, dpi=300, bbox_inches="tight", format="png")

plt.close("all")

print("Saved plot to:", out_pdf)
print("Saved plot to:", out_png)

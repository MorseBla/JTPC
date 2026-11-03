# Extracted from the archived notebook; cell number is recorded in docs/plot_sources.json.
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parent)
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib import font_manager
from matplotlib.lines import Line2D
import os

# =========================================================
# FONT
# =========================================================
arial_paths = [
    "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

for fp in arial_paths:
    if os.path.exists(fp):
        try:
            font_manager.fontManager.addfont(fp)
        except Exception:
            pass

plt.rcParams.update({
    "font.family": "Arial",
    "font.weight": "normal",
    "axes.labelweight": "bold",
    "axes.titleweight": "bold",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

# =========================================================
# CONFIG
# =========================================================
SAVE_DIR = Path("Figures/replotted")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

RTR_SETPOINT = 0.90
POWER_SETPOINT = 11000

ROOT = Path(
    "logs/task_arrival_4task_test/"
    "hist_stereo_mm_particle/"
    "setpoint_11000_0.90_0.90_0.90_0.90"
)

PREFIX = "UNKNOWN"
SAVE_NAME = "task_arrival_4task_test.pdf"

WARMUP_SKIP = 0
MAX_PERIODS = 120

TASK_NAMES = ["hist", "stereo", "mm", "particle"]
TASK_COLORS = ["tab:blue", "tab:orange", "tab:red", "tab:brown"]

FIGSIZE_2X2 = (8, 6)

DPI = 300
LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 14
LINEWIDTH = 2.0

# =========================================================
# HELPERS
# =========================================================
def read_data(filepath: Path):
    if not filepath.exists():
        print(f"Missing: {filepath}")
        return None

    vals = []
    with filepath.open("r", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                vals.append(float(s.split()[0]))
            except ValueError:
                continue

    if not vals:
        return None

    arr = np.asarray(vals, dtype=float)
    return arr[WARMUP_SKIP:WARMUP_SKIP + MAX_PERIODS]


def clean_positive(arr):
    if arr is None:
        return None
    arr = arr.astype(float).copy()
    arr[arr <= 0] = np.nan
    return arr


def load_run(root: Path, prefix: str):
    data = {name: {} for name in TASK_NAMES}

    for i, name in enumerate(TASK_NAMES, start=1):
        tid = f"t{i}"

        data[name]["rtr"] = clean_positive(
            read_data(root / f"{prefix}_{tid}_rtr.txt")
        )

        data[name]["dmr"] = read_data(
            root / f"{prefix}_{tid}_deadline.txt"
        )

        data[name]["period"] = clean_positive(
            read_data(root / f"{prefix}_{tid}_period.txt")
        )

        data[name]["exec"] = clean_positive(
            read_data(root / f"{prefix}_{tid}_exec.txt")
        )

        data[name]["response"] = clean_positive(
            read_data(root / f"{prefix}_{tid}_response.txt")
        )

    power = clean_positive(
        read_data(root / f"{prefix}__powercontrolperiod.txt")
    )

    if power is None:
        power = clean_positive(
            read_data(root / f"{prefix}_finalpowervalues.txt")
        )

    freq = clean_positive(
        read_data(root / f"{prefix}_finalfreqvalsvalues.txt")
    )

    return data, power, freq


def detect_task_arrival(data):
    y = data["particle"]["rtr"]
    if y is None:
        return 0

    valid = np.where(np.isfinite(y) & (y > 0))[0]
    if len(valid) == 0:
        return 0

    return int(valid[0])


def style_ax(ax, change_period):
    ax.axvline(
        x=change_period,
        color="gray",
        linestyle=":",
        linewidth=1.5,
    )

    ax.tick_params(axis="both", labelsize=TICK_FONTSIZE)

    for tick in ax.get_xticklabels():
        tick.set_fontweight("bold")

    for tick in ax.get_yticklabels():
        tick.set_fontweight("bold")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(True, alpha=0.2)
    ax.set_xlim([0, MAX_PERIODS])


def plot_rtr(ax, data, panel, change_period):
    ax.axhline(
        y=RTR_SETPOINT,
        color="black",
        linestyle="--",
        linewidth=1.5,
        label="Set point",
    )

    for name, color in zip(TASK_NAMES, TASK_COLORS):
        y = data[name]["rtr"]
        if y is None:
            continue

        if name == "particle":
            x = np.arange(len(y))
            mask = x >= change_period
            ax.plot(
                x[mask],
                y[mask],
                linewidth=LINEWIDTH,
                label=name,
                color=color,
            )
        else:
            ax.plot(
                y,
                linewidth=LINEWIDTH,
                label=name,
                color=color,
            )

    ax.set_ylabel("RTR", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel(f"Control Period \n({panel})", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_ylim(0.5, 1.2)


def plot_dmr(ax, data, panel, change_period):
    for name, color in zip(TASK_NAMES, TASK_COLORS):
        y = data[name]["dmr"]
        if y is None:
            continue

        if name == "particle":
            x = np.arange(len(y))
            mask = x >= change_period
            ax.plot(
                x[mask],
                y[mask],
                linewidth=LINEWIDTH,
                color=color,
            )
        else:
            ax.plot(
                y,
                linewidth=LINEWIDTH,
                color=color,
            )

    ax.set_ylabel("DMR (%)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel(f"Control Period \n({panel})", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_ylim(-5, 105)


def plot_period_and_frequency(ax, data, freq, panel, change_period):
    # Left y-axis: Period
    for name, color in zip(TASK_NAMES, TASK_COLORS):
        y = data[name]["period"]
        if y is None:
            continue

        if name == "particle":
            x = np.arange(len(y))
            mask = x >= change_period
            ax.plot(
                x[mask],
                y[mask],
                linewidth=LINEWIDTH,
                color=color,
            )
        else:
            ax.plot(
                y,
                linewidth=LINEWIDTH,
                color=color,
            )

    ax.set_ylabel("Period (ms)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel(f"Control Period \n({panel})", fontsize=LABEL_FONTSIZE, fontweight="bold")

    # Right y-axis: Frequency
    ax2 = ax.twinx()

    if freq is not None:
        ax2.plot(
            freq,
            linewidth=LINEWIDTH,
            color="tab:purple",
            marker="o",
            markersize=3,
            markevery=8,
            label="Frequency",
        )

    ax2.set_ylabel(
        "Frequency (MHz)",
        fontsize=LABEL_FONTSIZE,
        fontweight="bold",
        color="tab:purple",
    )

    ax2.tick_params(axis="y", labelsize=TICK_FONTSIZE, colors="tab:purple")

    for tick in ax2.get_yticklabels():
        tick.set_fontweight("bold")

    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("tab:purple")

    return ax2


def plot_power(ax, power, panel):
    if power is not None:
        ax.plot(
            power,
            linewidth=LINEWIDTH,
            color="tab:green",
            label="Power",
        )

    ax.axhline(
        y=POWER_SETPOINT,
        color="black",
        linestyle="--",
        linewidth=1.5,
        label="Set point",
    )

    ax.set_ylabel("Power (mW)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel(f"Control Period \n({panel})", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_ylim([9000, 16000])


def global_legend(fig, axs):
    handles, labels = axs[0].get_legend_handles_labels()

    freq_handle = Line2D(
        [0], [0],
        color="tab:purple",
        linewidth=LINEWIDTH,
        marker="o",
        markersize=5,
    )
    handles.append(freq_handle)
    labels.append("Frequency")

    power_handle = Line2D([0], [0], color="tab:green", linewidth=LINEWIDTH)
    handles.append(power_handle)
    labels.append("Power")

    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.97),
        ncol=4,
        frameon=False,
        prop={"size": LEGEND_FONTSIZE},
        columnspacing=1.4,
        handlelength=2.0,
        handletextpad=0.5,
    )


def save_fig(fig, save_path: Path):
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
    png_path = save_path.with_suffix(".png")
    fig.savefig(png_path, dpi=DPI, bbox_inches="tight")
    plt.close("all")
    plt.close(fig)

    print(f"Saved plot to: {save_path}")
    print(f"Saved plot to: {png_path}")


# =========================================================
# MAIN PLOT
# =========================================================
print("Root:", ROOT)

if not ROOT.exists():
    raise FileNotFoundError(f"Missing log root: {ROOT.resolve()}")

data, power, freq = load_run(ROOT, PREFIX)
CHANGE_PERIOD = detect_task_arrival(data)

print("Detected task arrival control period:", CHANGE_PERIOD)

fig, axs = plt.subplots(2, 2, figsize=FIGSIZE_2X2)
axs = axs.flatten()

plot_rtr(axs[0], data, "a", CHANGE_PERIOD)
plot_dmr(axs[1], data, "b", CHANGE_PERIOD)
plot_period_and_frequency(axs[2], data, freq, "c", CHANGE_PERIOD)
plot_power(axs[3], power, "d")

for ax in axs:
    style_ax(ax, CHANGE_PERIOD)

global_legend(fig, axs)

plt.tight_layout(rect=[0, 0, 1, 0.85])
save_fig(fig, SAVE_DIR / SAVE_NAME)

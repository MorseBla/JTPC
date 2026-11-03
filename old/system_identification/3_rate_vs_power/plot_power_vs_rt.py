import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ---------- FONT ----------
font_path = "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"
font_manager.fontManager.addfont(font_path)
plt.rcParams["font.family"] = "Arial"
plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial']})

# ---------- CONFIG ----------
FIGSIZE = (15, 4)
LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LINEWIDTH = 2.0
MARKERSIZE = 7

task_names = ["hist", "mm", "particle", "quasi", "stereo"]


def main():
    parser = argparse.ArgumentParser(
        description="Plot power vs response time for all workloads."
    )
    parser.add_argument(
        "--csv",
        default="power_vs_rt.csv",
        help="Input CSV file"
    )
    parser.add_argument(
        "--out",
        default="figures/power_vs_rt.pdf",
        help="Output figure path"
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv)

    required_cols = {"workload", "response_ms", "power_w"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    fig, ax = plt.subplots(1, 1, figsize=FIGSIZE)

    for task in task_names:
        sub = df[df["workload"] == task].copy()

        if sub.empty:
            continue

        sub = sub.sort_values("response_ms")

        x = sub["response_ms"].to_numpy(dtype=float)
        y = sub["power_w"].to_numpy(dtype=float) * 1000.0

        ax.plot(
            x,
            y,
            marker="o",
            markersize=MARKERSIZE,
            linewidth=LINEWIDTH,
            label=task
        )

    ax.set_ylabel("Power (mW)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel("Response Time (ms)", fontsize=LABEL_FONTSIZE, fontweight="bold")

    ax.tick_params(axis="both", labelsize=TICK_FONTSIZE)

    for tick in ax.get_xticklabels():
        tick.set_fontweight("bold")
    for tick in ax.get_yticklabels():
        tick.set_fontweight("bold")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.2)

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        ncol=5,
        frameon=False,
        prop={"weight": "bold", "size": 14}
    )

    plt.tight_layout(rect=[0, 0, 1, 0.88])

    out_file = Path(args.out)
    out_file.parent.mkdir(exist_ok=True)

    plt.savefig(out_file, bbox_inches="tight")
    plt.show()

    print(f"Saved plot to: {out_file}")


if __name__ == "__main__":
    main()

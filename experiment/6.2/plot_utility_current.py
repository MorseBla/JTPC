"""Plot task utility from the current Section 6.2 telemetry.

The data discovery and aggregation live in ``current_barplot_data`` so this
plot keeps the archived utility figure's visual treatment while accepting the
current run layout and an arbitrary set of power/RTR points.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42

import matplotlib.pyplot as plt
import numpy as np

from current_barplot_data import prepare_plot, write_statistics


plt.rcParams.update(
    {
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
    }
)

LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 12
BAR_WIDTH = 0.15
X_SPACING = 0.82


def main(argv=None):
    data = prepare_plot("utility", argv)
    series = list(data["series"])
    if not series:
        raise ValueError("No utility series were returned by current_barplot_data")

    x_labels = [str(label) for label in data["x_labels"]]
    x = np.arange(len(x_labels), dtype=float) * X_SPACING
    offsets = (np.arange(len(series), dtype=float) - (len(series) - 1) / 2.0) * BAR_WIDTH

    fig, ax = plt.subplots(figsize=(4, 3))
    for offset, item in zip(offsets, series):
        means = np.asarray(item["means"], dtype=float)
        if means.size != x.size:
            raise ValueError(
                f"Series {item.get('label', item.get('key', '?'))!r} has "
                f"{means.size} values for {x.size} x labels"
            )
        # Utility bars intentionally have no error bars, matching the archived
        # figure.  The statistics record the three per-task means instead.
        ax.bar(
            x + offset,
            means,
            BAR_WIDTH,
            color=item["color"],
            hatch=item["hatch"],
            edgecolor="black",
            linewidth=0.5,
            label=item["label"],
        )

    ax.set_xlabel(data["xlabel"], fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_ylabel(data["ylabel"], fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontweight="bold")
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

    ylim = tuple(data["ylim"])
    if len(ylim) != 2 or not all(np.isfinite(ylim)) or ylim[0] >= ylim[1]:
        raise ValueError(f"Invalid utility y limits: {ylim!r}")
    ax.set_ylim(ylim)
    if ylim == (0.5, 1.4):
        ax.set_yticks([0.6, 0.8, 1.0, 1.2, 1.4])
    # Let Matplotlib choose ticks when a current run extends beyond the
    # archived 0.5--1.4 window; fixed old ticks would clip or misrepresent it.
    plt.xticks(fontsize=TICK_FONTSIZE, fontweight="bold")
    plt.yticks(fontsize=TICK_FONTSIZE, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])

    output_stem = Path(data["output_stem"])
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    out_pdf = Path(f"{output_stem}.pdf")
    out_png = Path(f"{output_stem}.png")
    fig.savefig(out_pdf, dpi=300, bbox_inches="tight", format="pdf")
    fig.savefig(out_png, dpi=300, bbox_inches="tight", format="png")
    plt.close(fig)

    write_statistics(data, [out_pdf, out_png])
    print("Saved plot to:", out_pdf)
    print("Saved plot to:", out_png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

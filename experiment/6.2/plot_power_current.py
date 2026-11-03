"""Current-telemetry adaptation of the archived ``plot_power.py`` figure.

The data discovery and statistics are intentionally kept in
``current_barplot_data`` so this module only owns the presentation layer.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42

import matplotlib.pyplot as plt
import numpy as np

from current_barplot_data import prepare_plot, write_statistics


# Match the typography and visual treatment of plot_power.py.
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

LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 12


def main(argv=None):
    """Prepare and save the current power bar plot."""
    data = prepare_plot("power", argv)
    series = data["series"]
    x_labels = list(data["x_labels"])
    n_series = len(series)
    n_points = len(x_labels)

    fig, ax = plt.subplots(figsize=(4, 3))

    # The original uses 0.82 between group centers and 0.15 bars.  Center the
    # selected subset around each group so --solutions remains readable.
    x = np.arange(n_points) * 0.82
    bar_width = 0.15
    center = (n_series - 1) / 2.0
    for index, item in enumerate(series):
        means = np.asarray(item["means"], dtype=float)
        stds = np.asarray(item["stds"], dtype=float)
        ax.bar(
            x + (index - center) * bar_width,
            means,
            bar_width,
            yerr=stds,
            color=item["color"],
            hatch=item["hatch"],
            edgecolor="black",
            linewidth=0.5,
            label=item["label"],
            error_kw=dict(elinewidth=0.8, capsize=2, capthick=0.8),
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
        ncol=max(1, n_series),
        frameon=False,
        prop={"size": LEGEND_FONTSIZE},
        columnspacing=0.7,
        handlelength=1.1,
        handletextpad=0.35,
        borderaxespad=0.0,
    )

    lower, upper = data["ylim"]
    ax.set_ylim(lower, upper)
    if (lower, upper) == (9.5, 13.3):
        ax.set_yticks([10, 11, 12, 13])
    plt.xticks(fontsize=TICK_FONTSIZE, fontweight="bold")
    plt.yticks(fontsize=TICK_FONTSIZE, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])

    output_stem = Path(data["output_stem"])
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    outputs = [
        output_stem.with_suffix(".pdf"),
        output_stem.with_suffix(".png"),
        output_stem.with_suffix(".svg"),
    ]
    plt.savefig(outputs[0], dpi=600, bbox_inches="tight", format="pdf")
    plt.savefig(outputs[1], dpi=600, bbox_inches="tight", format="png")
    plt.savefig(outputs[2], dpi=600, bbox_inches="tight", format="svg")
    plt.close(fig)
    write_statistics(data, outputs)

    for output in outputs:
        print(f"Saved plot to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

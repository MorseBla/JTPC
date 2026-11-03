"""Current-telemetry adaptation of :mod:`plot_rtr.py`.

The data-discovery and aggregation logic lives in ``current_barplot_data`` so
this module remains a plotting-only duplicate of the archived figure.  The
original ``plot_rtr.py`` is intentionally left unchanged.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42

import matplotlib.pyplot as plt
import numpy as np

from current_barplot_data import prepare_plot, write_statistics


# ---------- FONT / STYLE (copied from plot_rtr.py) ----------
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


def main(argv=None):
    """Build and save the RTR bar plot for the current telemetry captures."""

    data = prepare_plot("rtr", argv)
    series = data["series"]
    x_labels = list(data["x_labels"])

    fig, ax = plt.subplots(figsize=(4, 3))

    x = np.arange(len(x_labels), dtype=float) * 0.82
    bar_width = 0.15
    n_series = len(series)
    offsets = (np.arange(n_series, dtype=float) - (n_series - 1) / 2.0) * bar_width

    for offset, item in zip(offsets, series):
        ax.bar(
            x + offset,
            np.asarray(item["means"], dtype=float),
            bar_width,
            yerr=np.asarray(item["stds"], dtype=float),
            color=item["color"],
            hatch=item["hatch"],
            edgecolor="black",
            linewidth=0.5,
            label=item["label"],
            error_kw=dict(
                elinewidth=0.8,
                capsize=2,
                capthick=0.8,
            ),
        )

    ax.set_xlabel(data["xlabel"], fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_ylabel(data["ylabel"], fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontweight="bold")
    ax.set_ylim(0,2.0)

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

    plt.xticks(fontsize=TICK_FONTSIZE, fontweight="bold")
    plt.yticks(fontsize=TICK_FONTSIZE, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])

    output_stem = Path(data["output_stem"])
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    out_pdf = Path(str(output_stem) + ".pdf")
    out_png = Path(str(output_stem) + ".png")
    fig.savefig(out_pdf, dpi=300, bbox_inches="tight", format="pdf")
    fig.savefig(out_png, dpi=300, bbox_inches="tight", format="png")
    write_statistics(data, [out_pdf, out_png])
    plt.close(fig)

    print("Saved plot to:", out_pdf)
    print("Saved plot to:", out_png)
    return data


if __name__ == "__main__":
    main()

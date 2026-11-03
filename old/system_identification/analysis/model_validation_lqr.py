from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ---------------- FONT ----------------
try:
    font_path = "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"
    font_manager.fontManager.addfont(font_path)
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

# ---------------- CONFIG ----------------
ROOT = Path("02_regular_tests/logs/Full_LQR/hist_stereo_mm/setpoint_11000_0.90_0.90_0.90")
PREFIX = "LQR"

SAVE_DIR = Path("figures/model_validation")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

MAX_PERIODS = 100
POWER_SETPOINT = 11000.0
RTR_SETPOINT = 0.90

# Srini requested validation for 2 tasks.
# Internally, prediction still uses all 3 task periods + GPU frequency.
PLOT_TASKS = [
    ("hist", 0),
    ("stereo", 1),
]

TASK_COLORS = {
    "hist": "tab:blue",
    "stereo": "tab:green",
    "mm": "tab:purple",
}

# Template style requirements
FIGSIZE = (8, 6)
DPI = 300

LABEL_FONTSIZE = 16
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 14
LINEWIDTH = 2.0
GRID_ALPHA = 0.2

# Same A/B model as controller.cc for 3 tasks + power.
# State/error order:
#   [hist RT error, stereo RT error, mm RT error, power error]
# Input order:
#   [hist period, stereo period, mm period, GPU frequency]
A = 0.95 * np.eye(4)

B = np.array([
    [1.0,         0.0,         0.0,         0.06238100],
    [0.0,         1.0,         0.0,         0.06804800],
    [0.0,         0.0,         1.0,         0.07260400],
    [0.022207533, 0.011072230, 0.028522303, -0.00116413],
], dtype=float)


def read_data(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    vals = []
    for line in path.read_text().splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        try:
            vals.append(float(parts[0]))
        except ValueError:
            pass

    return np.asarray(vals, dtype=float)


def cut(x: np.ndarray) -> np.ndarray:
    return x[:MAX_PERIODS]


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)))


def mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def style_axis(ax):
    ax.tick_params(axis="both", labelsize=TICK_FONTSIZE)

    for tick in ax.get_xticklabels():
        tick.set_fontweight("bold")
    for tick in ax.get_yticklabels():
        tick.set_fontweight("bold")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.grid(True, alpha=GRID_ALPHA)


def add_global_legend(fig, handles, labels):
    # Remove duplicate labels while preserving order.
    seen = set()
    clean_handles = []
    clean_labels = []

    for h, l in zip(handles, labels):
        if l not in seen:
            clean_handles.append(h)
            clean_labels.append(l)
            seen.add(l)

    fig.legend(
        clean_handles,
        clean_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.985),
        ncol=4,
        frameon=False,
        prop={"size": LEGEND_FONTSIZE},
        columnspacing=0.9,
        handlelength=1.8,
        handletextpad=0.5,
        borderaxespad=0.0,
    )


def main():
    print("Using validation trace:", ROOT)

    # ---------------- Read measured response time ----------------
    resp1 = cut(read_data(ROOT / f"{PREFIX}_t1_response.txt"))
    resp2 = cut(read_data(ROOT / f"{PREFIX}_t2_response.txt"))
    resp3 = cut(read_data(ROOT / f"{PREFIX}_t3_response.txt"))

    # ---------------- Read measured period ----------------
    per1 = cut(read_data(ROOT / f"{PREFIX}_t1_period.txt"))
    per2 = cut(read_data(ROOT / f"{PREFIX}_t2_period.txt"))
    per3 = cut(read_data(ROOT / f"{PREFIX}_t3_period.txt"))

    # ---------------- Read measured power and frequency ----------------
    power = cut(read_data(ROOT / f"{PREFIX}_finalpowervalues.txt"))
    freq = cut(read_data(ROOT / f"{PREFIX}_finalfreqvalsvalues.txt"))

    n = min(
        len(resp1), len(resp2), len(resp3),
        len(per1), len(per2), len(per3),
        len(power), len(freq),
    )

    resp1, resp2, resp3 = resp1[:n], resp2[:n], resp3[:n]
    per1, per2, per3 = per1[:n], per2[:n], per3[:n]
    power, freq = power[:n], freq[:n]

    # =========================================================
    # Controller error definition:
    #   RT error = desired response time - measured response time
    #   Power error = power setpoint - measured power
    # =========================================================
    e1 = RTR_SETPOINT * per1 - resp1
    e2 = RTR_SETPOINT * per2 - resp2
    e3 = RTR_SETPOINT * per3 - resp3
    ep = POWER_SETPOINT - power

    E_meas = np.column_stack([e1, e2, e3, ep])

    # Input vector:
    #   [hist period, stereo period, mm period, GPU freq]
    U = np.column_stack([per1, per2, per3, freq])

    # =========================================================
    # One-step-ahead prediction in error space:
    #   e_pred(k+1) = A e_meas(k) + B Δu(k)
    # =========================================================
    E_pred = np.full_like(E_meas, np.nan, dtype=float)
    E_pred[0] = E_meas[0]

    for k in range(n - 1):
        du = U[k + 1] - U[k]
        E_pred[k + 1] = A @ E_meas[k] + B @ du

    # =========================================================
    # Convert predicted error back to response time / power.
    #
    #   error = desired_response - response
    #   response = desired_response - error
    #
    #   power_error = power_setpoint - power
    #   power = power_setpoint - power_error
    # =========================================================
    resp_meas = np.column_stack([resp1, resp2, resp3])

    resp_pred = np.column_stack([
        RTR_SETPOINT * per1 - E_pred[:, 0],
        RTR_SETPOINT * per2 - E_pred[:, 1],
        RTR_SETPOINT * per3 - E_pred[:, 2],
    ])

    power_meas = power
    power_pred = POWER_SETPOINT - E_pred[:, 3]

    x = np.arange(n)

    # ---------------- Print metrics ----------------
    print("\nValidation metrics, converted back to response time / power:")
    task_names = ["hist", "stereo", "mm"]

    for i, name in enumerate(task_names):
        print(
            f"{name:8s} response RMSE={rmse(resp_meas[1:, i], resp_pred[1:, i]):.4f} ms, "
            f"MAE={mae(resp_meas[1:, i], resp_pred[1:, i]):.4f} ms"
        )

    print(
        f"power    RMSE={rmse(power_meas[1:], power_pred[1:]):.4f} mW, "
        f"MAE={mae(power_meas[1:], power_pred[1:]):.4f} mW"
    )

    # ---------------- Plot: 2x2 template style ----------------
    fig, axs = plt.subplots(2, 2, figsize=FIGSIZE)
    axs = axs.flatten()

    # =========================================================
    # (a) Response Time measured vs predicted, 2 tasks only
    # =========================================================
    ax = axs[0]

    for task_label, idx in PLOT_TASKS:
        ax.plot(
            x,
            resp_meas[:, idx],
            linewidth=LINEWIDTH,
            color=TASK_COLORS[task_label],
            linestyle="-",
            label=f"{task_label} measured",
        )

        ax.plot(
            x,
            resp_pred[:, idx],
            linewidth=LINEWIDTH,
            color=TASK_COLORS[task_label],
            linestyle="--",
            label=f"{task_label} predicted",
        )

    ax.set_ylabel("Response Time (ms)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel("Control Period \n(a)", fontsize=LABEL_FONTSIZE, fontweight="bold")

    # =========================================================
    # (b) Power measured vs predicted
    # =========================================================
    ax = axs[1]

    ax.plot(
        x,
        power_meas,
        linewidth=LINEWIDTH,
        color="tab:blue",
        linestyle="-",
        label="Power measured",
    )

    ax.plot(
        x,
        power_pred,
        linewidth=LINEWIDTH,
        color="tab:orange",
        linestyle="--",
        label="Power predicted",
    )

    ax.set_ylabel("Power (mW)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel("Control Period \n(b)", fontsize=LABEL_FONTSIZE, fontweight="bold")

    # =========================================================
    # (c) GPU Frequency
    # =========================================================
    ax = axs[2]

    ax.plot(
        x,
        freq,
        linewidth=LINEWIDTH,
        color="tab:blue",
        linestyle="-",
        label="GPU freq",
    )

    ax.set_ylabel("Frequency (MHz)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel("Control Period \n(c)", fontsize=LABEL_FONTSIZE, fontweight="bold")

    # =========================================================
    # (d) Period, 2 tasks only
    # =========================================================
    ax = axs[3]

    period_map = {
        "hist": per1,
        "stereo": per2,
        "mm": per3,
    }

    for task_label, idx in PLOT_TASKS:
        ax.plot(
            x,
            period_map[task_label],
            linewidth=LINEWIDTH,
            color=TASK_COLORS[task_label],
            linestyle="-",
            label=f"{task_label} period",
        )

    ax.set_ylabel("Period (ms)", fontsize=LABEL_FONTSIZE, fontweight="bold")
    ax.set_xlabel("Control Period \n(d)", fontsize=LABEL_FONTSIZE, fontweight="bold")

    # ---------------- Global styling ----------------
    for ax in axs:
        style_axis(ax)
        ax.set_xlim([0, MAX_PERIODS])

    # ---------------- Global legend ----------------
    handles, labels = [], []
    for ax in axs:
        h, l = ax.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)

    add_global_legend(fig, handles, labels)

    # More top space for smaller but multi-column legend.
    plt.tight_layout(rect=[0, 0, 1, 0.78])

    out_pdf = SAVE_DIR / "lqr_model_validation_response_power_2tasks.pdf"
    out_png = SAVE_DIR / "lqr_model_validation_response_power_2tasks.png"

    fig.savefig(out_pdf, dpi=DPI, bbox_inches="tight")
    fig.savefig(out_png, dpi=DPI, bbox_inches="tight")

    print("\nSaved:", out_pdf.resolve())
    print("Saved:", out_png.resolve())


if __name__ == "__main__":
    main()
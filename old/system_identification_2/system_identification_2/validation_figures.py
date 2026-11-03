"""Validation figures for measured JTPC outputs and a partial analytical model.

The plotted model uses only the supplied frequency column and alpha.  Unknown
rate columns are masked; this module never estimates or invents them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import math
import json
import statistics as st


TASKS = ("hist", "stereo", "mm")


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _mean(value):
    if isinstance(value, dict):
        return _finite(value.get("mean"))
    return _finite(value)


def _numeric_column(matrix, row, col):
    try:
        value = matrix[row][col]
    except (IndexError, KeyError, TypeError):
        return None
    return _finite(value)


def partial_prediction(matrix, nominal_q_ms, nominal_power_w, alpha_w_per_mhz,
                       frequency_mhz, f0_mhz, rates, nominal_rates, task_order=TASKS):
    """Return q/P predictions using only frequency columns.

    ``B_partial`` response entries are interpreted as response-units per input
    coordinate (the frequency column is ms/MHz in this plotting adapter). A
    changed rate masks only outputs whose corresponding B entry is unresolved;
    known entries, including known zero diagonal entries, are retained.
    """
    df = float(frequency_mhz) - float(f0_mhz)
    deltas = [float(rates.get(task, nominal_rates.get(task, 0))) -
              float(nominal_rates.get(task, 0)) for task in task_order] + [df]
    q, masked = [], set()
    for i, task in enumerate(task_order):
        value = float(nominal_q_ms[i])
        for j, delta in enumerate(deltas):
            if abs(delta) < 1e-12:
                continue
            coeff = _numeric_column(matrix, i, j) if matrix is not None else None
            if coeff is None:
                masked.add(task)
                value = None
                break
            value += coeff * delta
        q.append(value)
    power = None
    if _finite(nominal_power_w) is not None and _finite(alpha_w_per_mhz) is not None:
        power = float(nominal_power_w) + float(alpha_w_per_mhz) * df
    return {"q_ms": q, "power_W": power, "delta_f_MHz": df,
            "masked_rate_tasks": sorted(masked)}


def _window_rows(windows, summaries, matrix, task_order, frozen=None):
    validation = summaries.get("windows", summaries) if isinstance(summaries, dict) else summaries
    validation = {row.get("window_id"): row for row in validation if row.get("window_id")}
    rows = []
    nominal = summaries.get("nominal_window_id") if isinstance(summaries, dict) else None
    nominal_row = validation.get(nominal) if nominal else None
    if nominal_row is None:
        return rows
    nominal_freq = _mean(nominal_row.get("frequency"))
    nominal_power = _mean(nominal_row.get("power"))
    nominal_rates = nominal_row.get("requested_rates_hz") or {}
    nominal_q = [_mean(nominal_row.get("tasks", {}).get(task, {}).get("response_s")) * 1000
                 if _mean(nominal_row.get("tasks", {}).get(task, {}).get("response_s")) is not None else None
                 for task in task_order]
    if nominal_freq is None or nominal_power is None or any(x is None for x in nominal_q):
        return rows
    f0 = nominal_freq / 1e6
    alpha = summaries.get("alpha_W_per_MHz") if isinstance(summaries, dict) else None
    if frozen:
        # Use the previous analysis artifact, never recalibrate to this run.
        nominal_q = frozen.get('nominal_q_ms', nominal_q)
        nominal_power = frozen.get('nominal_power_W', nominal_power)
        f0 = frozen.get('f0_MHz', f0)
        alpha = frozen.get('alpha_W_per_MHz', alpha)
    for index, window in enumerate(windows):
        if window.get("kind") != "validation":
            continue
        row = validation.get(window.get("id"), {})
        freq = _mean(row.get("frequency"))
        if freq is None:
            continue
        measured_q = [_mean(row.get("tasks", {}).get(task, {}).get("response_s")) * 1000
                      if _mean(row.get("tasks", {}).get(task, {}).get("response_s")) is not None else None
                      for task in task_order]
        pred = partial_prediction(matrix, nominal_q, nominal_power, alpha, freq / 1e6, f0,
                                  window.get("rates_hz") or {}, nominal_rates, task_order)
        rows.append(dict(index=index, window_id=window.get("id"),
                         elapsed_s=float(window.get("start_s", 0)) - float(windows[0].get("start_s", 0)),
                         frequency_mhz=freq / 1e6, rates_hz=window.get("rates_hz") or {},
                         measured_q_ms=measured_q, predicted_q_ms=pred["q_ms"],
                         measured_power_w=_mean(row.get("power")), predicted_power_w=pred["power_W"],
                         masked_rate_tasks=pred["masked_rate_tasks"]))
    return rows


def _interval_rows(summaries, task_order, matrix=None, nominal=None, origin=0.0,
                   window_by_id=None):
    rows = []
    for row in (summaries.get("intervals", []) if isinstance(summaries, dict) else []):
        outputs = row.get("outputs", {})
        frequency_stats = row.get("achieved_frequency")
        freq = _mean(frequency_stats)
        if isinstance(frequency_stats, dict) and not frequency_stats.get("valid", True):
            freq = None
        window_rates = row.get("rates_hz") or {}
        if not window_rates and window_by_id:
            window_rates = (window_by_id.get(row.get("window_id"), {}).get("rates_hz") or {})
        pred = None
        if nominal and freq is not None and window_rates:
            pred = partial_prediction(matrix, nominal["q_ms"], nominal["power_W"], nominal["alpha"],
                                      freq / 1e6, nominal["f0_mhz"], window_rates, nominal["rates_hz"], task_order)
        rows.append(dict(elapsed_s=(_finite(row.get("start_s")) or 0) - origin,
                         frequency_mhz=freq / 1e6 if freq is not None else None,
                         q_ms=[_mean(outputs.get(task, {}).get("response_s")) * 1000
                               if _mean(outputs.get(task, {}).get("response_s")) is not None else None
                               for task in task_order],
                         power_w=_mean(row.get("power")) if not isinstance(row.get("power"), dict) or row["power"].get("valid", True) else None,
                         predicted_q_ms=pred["q_ms"] if pred else [None] * len(task_order),
                         predicted_power_w=pred["power_W"] if pred else None,
                         transition_gap=bool(row.get("straddles_transition")) and freq is not None
                             and bool(outputs) and all(_mean(outputs.get(task, {}).get("response_s")) is not None for task in task_order)
                             and _mean(row.get("power")) is not None and row.get("power", {}).get("valid", True),
                         invalid=bool(row.get("straddles_transition")) or freq is None or not outputs,
                         masked_rate_tasks=pred["masked_rate_tasks"] if pred else list(task_order)))
    return rows


def _style(ax, ylabel, xlabel=None):
    ax.set_ylabel(ylabel, fontweight="bold")
    if xlabel:
        ax.set_xlabel(xlabel, fontweight="bold")
    ax.grid(True, alpha=.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def connected_points(x, y, transition_gaps):
    """Join endpoints over excluded transition bins; preserve other missing values.

    This only selects plotting vertices. It never inserts values into the data
    or the model/error calculations, and never bridges unresolved-rate gaps.
    """
    vertices = [(a, b) for i, (a, b) in enumerate(zip(x, y))
                if not (i in transition_gaps and b is None)]
    return [a for a, _ in vertices], [b for _, b in vertices]


def _connected_plot(ax, x, y, transition_gaps, *args, **kwargs):
    px, py = connected_points(x, y, transition_gaps)
    return ax.plot(px, py, *args, **kwargs)


def _render_system_validation(intervals, out, bin_seconds=2.0, native_seconds=2.0):
    """Reference-style dual-axis interval summary, without validation refitting."""
    import matplotlib.pyplot as plt
    if not intervals:
        return []
    x = list(range(len(intervals)))
    bridges = {i for i,r in enumerate(intervals) if r.get("transition_gap")}
    measured_rt = [None if r.get("invalid") or any(v is None for v in r.get("q_ms", []))
                   else sum(r["q_ms"]) / len(r["q_ms"]) for r in intervals]
    predicted_rt = [None if r.get("invalid") or any(v is None for v in r.get("predicted_q_ms", []))
                    else sum(r["predicted_q_ms"]) / len(r["predicted_q_ms"])
                    for r in intervals]
    measured_power = [None if r.get("invalid") else r.get("power_w") for r in intervals]
    predicted_power = [None if r.get("invalid") else r.get("predicted_power_w") for r in intervals]
    fig, ax = plt.subplots(figsize=(13, 7))
    power_ax = ax.twinx()
    _connected_plot(ax, x, predicted_rt, bridges, color=(0.0, .65, 1.0, .5), linewidth=7,
            label="Frequency-only analytical RT (partial B)", zorder=1)
    _connected_plot(ax, x, measured_rt, bridges, color="black", marker="o", markersize=3, linewidth=.9,
            label="Measured average RT", zorder=2)
    _connected_plot(power_ax, x, predicted_power, bridges, color=(1.0, .2, .2, .45), linewidth=7,
                  label="Nominal-anchored VIN estimate (zero rate-power)", zorder=1)
    _connected_plot(power_ax, x, measured_power, bridges, color="black", linestyle="-", marker="s",
                  markersize=3, linewidth=.8, fillstyle="none", label="Measured VIN power", zorder=2)
    axis_label = (f"Control period ({bin_seconds:g} s completion-bin index)" if bin_seconds == native_seconds else f"Plot interval ({bin_seconds:g} s average; {native_seconds:g} s native control)")
    ax.set_xlabel(axis_label, fontweight="bold", fontsize=16)
    ax.set_ylabel("Average response time (ms)", fontweight="bold", fontsize=16)
    power_ax.set_ylabel("VIN power (W)", fontweight="bold", fontsize=16)
    # Match the reference's upper RT / lower power bands, while retaining EVERY
    # finite point and adapting bounds to these measurements instead of clipping.
    rt_values = [v for v in measured_rt+predicted_rt if v is not None]
    p_values = [v for v in measured_power+predicted_power if v is not None]
    if rt_values:
        low, high = min(rt_values), max(rt_values)
        span = max(high-low, abs(high)*.005, .001)
        ax.set_ylim(low-1.3*span, high+.15*span)
        ax.set_yticks([low+(high-low)*i/3 for i in range(4)] if high>low else [low])
    if p_values:
        low, high = min(p_values), max(p_values)
        span = max(high-low, abs(high)*.005, .001)
        power_ax.set_ylim(low-.15*span, high+1.3*span)
        power_ax.set_yticks([low+(high-low)*i/3 for i in range(4)] if high>low else [low])
    ax.tick_params(labelsize=13)
    power_ax.tick_params(labelsize=13)
    ax.grid(True, alpha=.2)
    ax.spines["top"].set_visible(False)
    power_ax.spines["top"].set_visible(False)
    handles, labels = ax.get_legend_handles_labels()
    h2, l2 = power_ax.get_legend_handles_labels()
    ax.legend(handles + h2, labels + l2, loc="upper center", bbox_to_anchor=(.5, 1.13),
              ncol=2, frameon=False, fontsize=12)
    fig.suptitle("JTPC validation: measured versus partial analytical model", fontweight="bold")
    fig.text(.5, .01, "Lines connect across excluded transition bins; no samples filled. Separate y scales. Full B unresolved.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .92))
    names = []
    for suffix in ("png", "pdf"):
        name = f"system_validation.{suffix}"
        fig.savefig(out / name, bbox_inches="tight")
        names.append(name)
    plt.close(fig)
    return names


def render_validation(config, windows, jobs, telemetry, summaries, matrix, out_dir):
    """Render combined and per-output validation figures; return relative names."""
    del jobs, telemetry  # summaries already contain settled and interval aggregates.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    task_order = tuple(config.get("validation_tasks") or [t.get("name") for t in config.get("tasks", [])] or TASKS)
    matrix = matrix or {}
    bpartial = matrix.get("B_partial")
    rows = _window_rows(windows, summaries, bpartial, task_order, matrix)
    nominal = None
    if rows:
        nominal_row = next((r for r in rows if r["index"] == 0), rows[0])
        nominal = dict(q_ms=matrix.get("nominal_q_ms") or nominal_row["measured_q_ms"],
                       power_W=matrix.get("nominal_power_W", nominal_row["measured_power_w"]),
                       f0_mhz=matrix.get("f0_MHz", nominal_row["frequency_mhz"]),
                       rates_hz=nominal_row["rates_hz"],
                       alpha=matrix.get("alpha_W_per_MHz", summaries.get("alpha_W_per_MHz")))
    origin = min((float(w.get("settle_start_s", w.get("start_s", 0))) for w in windows if w.get("kind") == "validation"), default=0.0)
    window_by_id = {w.get("id"): w for w in windows}
    intervals = _interval_rows(summaries, task_order, bpartial, nominal, origin, window_by_id)
    metrics = {}
    for i, task in enumerate(task_order):
        errors = [r['q_ms'][i]-r['predicted_q_ms'][i] for r in intervals
                  if not r['invalid'] and r['q_ms'][i] is not None and r['predicted_q_ms'][i] is not None]
        metrics[task] = dict(units='ms', count=len(errors), bias=st.fmean(errors) if errors else None,
                            rmse=math.sqrt(st.fmean(e*e for e in errors)) if errors else None)
    errors = [r['power_w']-r['predicted_power_w'] for r in intervals
              if not r['invalid'] and r['power_w'] is not None and r['predicted_power_w'] is not None]
    metrics['VIN'] = dict(units='W', count=len(errors), bias=st.fmean(errors) if errors else None,
                          rmse=math.sqrt(st.fmean(e*e for e in errors)) if errors else None)
    (out/'validation_plot_data.json').write_text(json.dumps(dict(intervals=intervals, plot_interval_s=summaries.get('plot_interval_s',config.get('interval_s',2)), native_controller_interval_s=config.get('interval_s',2), operating_point_errors=metrics,
        line_display='Adjacent valid vertices are connected across excluded transition bins only; no data values filled. Real missing/unresolved predictions remain gaps.',
        interpretation='Nominal-anchored first-order operating-point comparison at completion-bin resolution. Not a full B validation or interval state-prediction score; unknown cross-rate effects are masked.'), indent=2, allow_nan=False)+'\n')
    names = []
    labels = ["hist response (ms)", "stereo response (ms)", "mm response (ms)",
              "VIN power (W)"]
    fig, axes = plt.subplots(4, 1, figsize=(8, 10), sharex=True)
    colors = ["tab:blue", "tab:orange", "tab:green"]
    # Completion-bin rows are the primary validation view.  Invalid bins remain
    # NaN gaps; window means are only a fallback for old summaries without bins.
    plot_rows = intervals or [dict(elapsed_s=r["elapsed_s"], q_ms=r["measured_q_ms"],
                                   predicted_q_ms=r["predicted_q_ms"],
                                   power_w=r["measured_power_w"],
                                   predicted_power_w=r["predicted_power_w"], invalid=False)
                              for r in rows]
    x = [r["elapsed_s"] for r in plot_rows]
    bridges = {i for i,r in enumerate(plot_rows) if r.get("transition_gap")}
    def valid_values(key, i=None):
        out_values = []
        for r in plot_rows:
            if r.get("invalid"):
                out_values.append(None)
            else:
                value = r.get(key)
                if i is not None:
                    value = value[i] if value is not None and i < len(value) else None
                out_values.append(value)
        return out_values
    for i, (task, label, color) in enumerate(zip(task_order, labels, colors)):
        measured = valid_values("q_ms" if intervals else "measured_q_ms", i)
        predicted = valid_values("predicted_q_ms", i)
        _connected_plot(axes[i], x, measured, bridges, "o-", color=color, label="measured event+carry")
        _connected_plot(axes[i], x, predicted, bridges, "-", color="tab:red", label="frequency-only partial model")
        _style(axes[i], label)
    _connected_plot(axes[3], x, valid_values("power_w" if intervals else "measured_power_w"), bridges, "o-", color="tab:blue", label="measured VIN")
    _connected_plot(axes[3], x, valid_values("predicted_power_w"), bridges, "-", color="tab:red",
                 label="P0 + alpha delta-f; zero rate-power assumption")
    _style(axes[3], "VIN power (W)", "elapsed time (s)")
    for window in windows:
        if window.get("kind") != "validation":
            continue
        t = float(window.get("settle_start_s", window.get("start_s", origin))) - origin
        for ax in axes:
            ax.axvline(t, color="grey", alpha=.10, linewidth=.7)
        if window.get("start_s", origin) > window.get("settle_start_s", window.get("start_s", origin)):
            axv = float(window["start_s"]-window["settle_start_s"])
            for ax in axes:
                ax.axvspan(t, t + axv, color="grey", alpha=.05)
    axes[0].legend(loc="lower center", bbox_to_anchor=(.5, 1.18), ncol=2, frameon=False)
    axes[3].legend(loc="lower center", bbox_to_anchor=(.5, 1.18), ncol=2, frameon=False)
    fig.suptitle("Measured validation and frequency-only partial model", fontweight="bold")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        name = f"validation_measured_vs_partial.{suffix}"
        fig.savefig(out / name, bbox_inches="tight")
        names.append(name)
    plt.close(fig)

    for i, task in enumerate(task_order):
        fig, ax = plt.subplots(figsize=(7, 4))
        _connected_plot(ax, x, valid_values("q_ms" if intervals else "measured_q_ms", i), bridges, "o-", label="measured event+carry")
        _connected_plot(ax, x, valid_values("predicted_q_ms", i), bridges, "-", label="frequency-only partial model")
        for window in windows:
            if window.get("kind") == "validation":
                ax.axvline(float(window.get("start_s", origin))-origin, color="grey", alpha=.12)
        _style(ax, f"{task} response (ms)", "elapsed time (s)")
        ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.14), ncol=2, frameon=False)
        fig.tight_layout()
        for suffix in ("png", "pdf"):
            name = f"validation_{task}_partial.{suffix}"
            fig.savefig(out / name, bbox_inches="tight")
            names.append(name)
        plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    ix = [r["elapsed_s"] for r in intervals]
    interval_bridges = {i for i,r in enumerate(intervals) if r.get("transition_gap")}
    for i, task in enumerate(task_order):
        _connected_plot(axes[0], ix, [None if r["invalid"] else r["q_ms"][i] for r in intervals], interval_bridges, ".-", label=task)
        _connected_plot(axes[0], ix, [None if r["invalid"] or r["predicted_q_ms"][i] is None else r["predicted_q_ms"][i] for r in intervals], interval_bridges, "-", alpha=.65)
    axes[0].set_ylabel("completed response (ms)", fontweight="bold")
    axes[0].legend(loc="lower center", bbox_to_anchor=(.5, 1.14), ncol=3, frameon=False)
    _connected_plot(axes[1], ix, [None if r["invalid"] else r["frequency_mhz"] for r in intervals], interval_bridges, ".-", label="achieved frequency")
    axes[1].set_ylabel("frequency (MHz)", fontweight="bold")
    _style(axes[1], "frequency (MHz)", "elapsed time (s)")
    fig.suptitle(f"{summaries.get('plot_interval_s', config.get('interval_s', 2)):g}-second completion bins", fontweight="bold")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        name = f"validation_interval_bins.{suffix}"
        fig.savefig(out / name, bbox_inches="tight")
        names.append(name)
    plt.close(fig)

    names.extend(_render_system_validation(intervals, out, summaries.get('plot_interval_s',config.get('interval_s',2)), config.get('interval_s',2)))

    # Keep VIN separate for reports that crop individual outputs.
    fig, ax = plt.subplots(figsize=(7, 4))
    _connected_plot(ax, x, valid_values("power_w" if intervals else "measured_power_w"), bridges, "o-", label="measured VIN")
    _connected_plot(ax, x, valid_values("predicted_power_w"), bridges, "-", label="P0 + alpha delta-f; zero rate-power assumption")
    _style(ax, "VIN power (W)", "elapsed time (s)")
    ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.14), ncol=2, frameon=False)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        name = f"validation_power_partial.{suffix}"; fig.savefig(out / name, bbox_inches="tight"); names.append(name)
    plt.close(fig)

    names.extend(render_input_steps(config, windows, out_dir))

    return names


def render_input_steps(config, windows, out_dir):
    """Render requested task rates and requested frequency on aligned axes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tasks = tuple(config.get("validation_tasks") or [t.get("name") for t in config.get("tasks", [])] or TASKS)
    origin = min((float(w.get("settle_start_s", w.get("start_s", 0))) for w in windows if w.get("kind") == "validation"), default=0.0)
    rows = [w for w in windows if w.get("kind") == "validation"]
    x = [float(w.get("settle_start_s", w.get("start_s", origin)))-origin for w in rows]
    fig, axes = plt.subplots(len(tasks)+1, 1, figsize=(8, 2.4*(len(tasks)+1)), sharex=True)
    if len(tasks) == 0: axes = [axes]
    for i, task in enumerate(tasks):
        axes[i].step(x, [w.get("rates_hz", {}).get(task) for w in rows], where="post", label=task)
        _style(axes[i], f"{task} rate (Hz)")
        axes[i].legend(loc="lower center", bbox_to_anchor=(.5, 1.08), frameon=False)
    axes[-1].step(x, [float(w.get("requested_frequency_hz"))/1e6 for w in rows], where="post", label="requested frequency")
    _style(axes[-1], "frequency (MHz)", "elapsed time (s)")
    axes[-1].legend(loc="lower center", bbox_to_anchor=(.5, 1.08), frameon=False)
    fig.suptitle("Validation input steps", fontweight="bold"); fig.tight_layout()
    names=[]
    for suffix in ("png", "pdf"):
        name=f"validation_input_steps.{suffix}"; fig.savefig(out/name, bbox_inches="tight"); names.append(name)
    plt.close(fig)
    return names

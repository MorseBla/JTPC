#!/usr/bin/env python3
"""Reproduce the archived periodic JTPC validation figure offline.

This consumes the recovered CSV only. It does not launch workloads, inspect
hardware, or claim that the descriptive fits identify the analytical JTPC B/C.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE.parent / "JTPC_system_validation" / "validation_control_period.csv"


def fit_line(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 2 or np.ptp(x[valid]) == 0:
        return {"valid": False, "slope": None, "intercept": None, "r2": None, "n": int(valid.sum())}
    slope, intercept = np.polyfit(x[valid], y[valid], 1)
    pred = slope * x[valid] + intercept
    residual = y[valid] - pred
    sse = float(np.sum(residual ** 2))
    sst = float(np.sum((y[valid] - np.mean(y[valid])) ** 2))
    return {"valid": True, "slope": float(slope), "intercept": float(intercept),
            "r2": float(1 - sse / sst) if sst else None, "n": int(valid.sum())}


def load_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")
        headers = [str(c).strip() for c in reader.fieldnames]
        rows = [{str(k).strip(): v for k, v in row.items()} for row in reader]
    df = {name: np.asarray([_number(row.get(name, "")) for row in rows], dtype=float)
          for name in headers}
    required = {"control_period", "measured_freq_mhz", "measured_power"}
    rt_cols = sorted(c for c in df if c.startswith("task") and c.endswith("_rt_ms"))
    missing = sorted(required - set(df))
    if missing or not rt_cols:
        raise ValueError(f"CSV needs {sorted(required)} and task*_rt_ms columns; missing={missing}")
    df["average_rt_ms"] = np.nanmean(np.vstack([df[c] for c in rt_cols]), axis=0)
    df["power_w"] = df["measured_power"] / 1000.0
    return df, rt_cols


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def render(df, rt_cols, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = np.asarray(df["control_period"], dtype=float)
    freq = np.asarray(df["measured_freq_mhz"], dtype=float)
    rt = np.asarray(df["average_rt_ms"], dtype=float)
    power = np.asarray(df["power_w"], dtype=float)
    rt_fit = fit_line(freq, rt)
    power_fit = fit_line(freq, power)
    rt_pred = rt_fit["slope"] * freq + rt_fit["intercept"] if rt_fit["valid"] else np.full_like(freq, np.nan)
    power_pred = power_fit["slope"] * freq + power_fit["intercept"] if power_fit["valid"] else np.full_like(freq, np.nan)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.weight": "normal"})
    fig, ax = plt.subplots(figsize=(13, 7))
    power_ax = ax.twinx()
    ax.plot(x, rt_pred, color=(0.0, .65, 1.0, .45), linewidth=7,
            solid_capstyle="round", label="Descriptive RT fit")
    ax.plot(x, rt, color="black", marker="o", markersize=3, linewidth=1,
            label="Measured average RT")
    power_ax.plot(x, power_pred, color=(1.0, .2, .2, .45), linewidth=7,
                  solid_capstyle="round", label="Descriptive power fit")
    power_ax.plot(x, power, color="black", linestyle="--", marker="s", markersize=3,
                  linewidth=1, fillstyle="none", label="Measured power")
    ax.set_xlabel("Control period", fontsize=18, fontweight="bold")
    ax.set_ylabel("Average Response Time (ms)", fontsize=18, fontweight="bold")
    power_ax.set_ylabel("Power (W)", fontsize=18, fontweight="bold")
    ax.grid(True, alpha=.25)
    ax.spines["top"].set_visible(False)
    power_ax.spines["top"].set_visible(False)
    handles, labels = ax.get_legend_handles_labels()
    ph, pl = power_ax.get_legend_handles_labels()
    ax.legend(handles + ph, labels + pl, loc="upper center", bbox_to_anchor=(.5, 1.15),
              ncol=2, frameon=False, fontsize=13)
    ax.tick_params(labelsize=13)
    power_ax.tick_params(labelsize=13)
    rt_values = np.r_[rt[np.isfinite(rt)], rt_pred[np.isfinite(rt_pred)]]
    p_values = np.r_[power[np.isfinite(power)], power_pred[np.isfinite(power_pred)]]
    if len(rt_values):
        span = max(float(np.ptp(rt_values)), .01)
        ax.set_ylim(float(rt_values.min()) - 1.3 * span, float(rt_values.max()) + .15 * span)
        ax.set_yticks(np.linspace(float(rt_values.min()), float(rt_values.max()), 4))
    if len(p_values):
        span = max(float(np.ptp(p_values)), .01)
        power_ax.set_ylim(float(p_values.min()) - .15 * span, float(p_values.max()) + 1.3 * span)
        power_ax.set_yticks(np.linspace(float(p_values.min()), float(p_values.max()), 4))
    fig.text(.5,.01,"Archived measurements; same-data descriptive fits. Separate RT and power y-axis bands.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .93))
    names = []
    for suffix in ("png", "pdf"):
        name = f"legacy_periodic_system_validation.{suffix}"
        fig.savefig(out / name, dpi=300, bbox_inches="tight")
        names.append(name)
    plt.close(fig)
    return rt_fit, power_fit, names


def reproduce(csv_path=DEFAULT_CSV, output_dir=None):
    csv_path = Path(csv_path).resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = HERE / f"legacy_periodic_reproduction_{stamp}"
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {out}")
    out.mkdir(parents=True)
    before = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    df, rt_cols = load_csv(csv_path)
    rt_fit, power_fit, names = render(df, rt_cols, out)
    after = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError("Input CSV changed while plotting")
    frequencies = np.asarray(df["measured_freq_mhz"], dtype=float)
    steps = np.diff(frequencies, prepend=frequencies[0])
    metrics = {
        "source_csv": str(csv_path), "source_sha256": before, "source_unchanged": True,
        "rows": int(len(frequencies)), "task_rt_columns": rt_cols,
        "frequency_levels_mhz": sorted(np.unique(frequencies[np.isfinite(frequencies)]).tolist()),
        "periodic_step_count": int((steps != 0).sum()),
        "rt_fit": rt_fit, "power_fit": power_fit,
        "power_unit": "W; source measured_power divided by 1000, original rail boundary not specified",
        "B": None, "C": None,
        "matrix_status": "Unavailable: aggregate periodic CSV has no state/input identification matrix; fits are descriptive only.",
        "figure_files": names,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (out / "README.txt").write_text(
        "Recovered periodic validation reproduction.\n"
        "The repeated frequency stair steps create the trapezoid-like response/power trace.\n"
        "Fits use the same CSV points and are descriptive; they do not identify JTPC B or C.\n"
        f"Source SHA256: {before}\n")
    print(json.dumps(metrics, indent=2))
    print(f"Saved periodic figure review to: {out}")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    reproduce(args.csv, args.output_dir)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Plot fresh Section 6.2 LQR captures.

The x axis is the retained control-sample index.  No time axis is inferred from
the controller period, and each series keeps its original sample positions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


TASKS = ("hist", "stereo", "mm")
# Task order matches collection/LQR_main_temp.sh.
RTR_FILES = dict(zip(TASKS, ("LQR_t1_rtr.txt", "LQR_t2_rtr.txt", "LQR_t3_rtr.txt")))
SETPOINT_RE = re.compile(
    r"^setpoint_(?P<power>[0-9]+)_(?P<rtr>[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))_"
    r"(?P<rtr2>[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))_"
    r"(?P<rtr3>[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))$"
)


def read_series(path: Path, discard: int) -> np.ndarray:
    try:
        raw = np.loadtxt(path, ndmin=1)
    except Exception as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    if raw.ndim != 1:
        raise RuntimeError(f"{path} must contain one numeric value per record")
    values = np.asarray(raw, dtype=float)
    if discard:
        values = values[discard:]
    if values.size == 0:
        raise RuntimeError(f"{path} has no samples after discard={discard}")
    return values


def valid_with_positions(values: np.ndarray, path: Path) -> tuple[np.ndarray, np.ndarray]:
    valid = np.isfinite(values) & (values > 0)
    if not np.any(valid):
        raise RuntimeError(f"{path} has no positive finite samples")
    if np.any(~valid):
        print(f"warning: {path} contains invalid samples; preserving their positions", file=sys.stderr)
    plotted = values.astype(float, copy=True)
    plotted[~valid] = np.nan
    return np.arange(values.size), plotted


def discover_cases(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        raise RuntimeError(f"runs directory does not exist: {runs_dir}")
    if runs_dir.is_dir() and SETPOINT_RE.match(runs_dir.name):
        return [runs_dir]
    return sorted(path for path in runs_dir.rglob("setpoint_*") if path.is_dir() and SETPOINT_RE.match(path.name))


def parse_case(case_dir: Path, discard: int) -> dict:
    case_dir = case_dir.resolve()
    match = SETPOINT_RE.match(case_dir.name)
    if not match:
        raise RuntimeError(f"invalid LQR setpoint directory name: {case_dir}")
    power_mw = int(match.group("power"))
    if power_mw <= 0:
        raise RuntimeError(f"power target must be positive in {case_dir}")
    rtr_targets = [float(match.group(key)) for key in ("rtr", "rtr2", "rtr3")]
    if any(not np.isfinite(value) or value < 0 for value in rtr_targets):
        raise RuntimeError(f"invalid RTR target in {case_dir}")

    files: dict[str, str] = {}
    power_candidates = [case_dir / "LQR__powercontrolperiod.txt", case_dir / "LQR_finalpowervalues.txt"]
    power_path = next((path for path in power_candidates if path.is_file()), None)
    if power_path is None:
        raise RuntimeError(f"missing LQR power file in {case_dir}: expected {power_candidates[0].name} or {power_candidates[1].name}")
    power = read_series(power_path, discard)
    power_x, power_plot = valid_with_positions(power, power_path)
    power_x += discard
    files["power"] = str(power_path)

    rtr_data = []
    for task in TASKS:
        path = case_dir / RTR_FILES[task]
        if not path.is_file():
            raise RuntimeError(f"missing LQR RTR file for {task}: expected {path}")
        values = read_series(path, discard)
        x, plotted = valid_with_positions(values, path)
        x += discard
        rtr_data.append({"task": task, "path": str(path), "x": x, "values": plotted})
        files[task] = str(path)

    return {
        "case_dir": case_dir,
        "workload_dir": case_dir.parent,
        "name": case_dir.name,
        "power_mw": power_mw,
        "rtr_targets": rtr_targets,
        "power": {"x": power_x, "values": power_plot, "path": power_path},
        "rtr": rtr_data,
        "files": files,
        "discard": discard,
    }


def finite_stats(values: np.ndarray) -> dict:
    finite = values[np.isfinite(values)]
    return {"valid_samples": int(finite.size), "mean": float(np.mean(finite)), "population_std": float(np.std(finite))}


def plot_case(case: dict, output_dir: Path) -> dict:
    case_output = output_dir / case.get("output_subdir", case["workload_dir"].name)
    case_output.mkdir(parents=True, exist_ok=True)
    # Do not use Path.with_suffix here: a setpoint such as ``_.70`` ends in a
    # dot-containing token that would otherwise be mistaken for a file suffix.
    stem = case_output / f"LQR_{case['name']}"
    png_path = Path(str(stem) + ".png")
    pdf_path = Path(str(stem) + ".pdf")
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=False, constrained_layout=True)

    power_w = case["power"]["values"] / 1000.0
    axes[0].plot(
        case["power"]["x"], power_w, color="tab:green", label="Measured power",
        marker="o" if np.count_nonzero(np.isfinite(power_w)) == 1 else None,
    )
    axes[0].axhline(case["power_mw"] / 1000.0, color="black", linestyle="--", label="Set point")
    axes[0].set_ylabel("Power (W)")
    axes[0].set_xlabel("Control sample index (per series)")
    axes[0].set_title(f"LQR {case['name']} — power")
    axes[0].grid(alpha=0.25)
    axes[0].legend()

    rtr_stats = {}
    for item, target, color in zip(case["rtr"], case["rtr_targets"], ("tab:blue", "tab:orange", "tab:red")):
        axes[1].plot(
            item["x"], item["values"], color=color, label=f"{item['task']} measured",
            marker="o" if np.count_nonzero(np.isfinite(item["values"])) == 1 else None,
        )
        axes[1].axhline(target, color=color, linestyle="--", alpha=0.55, label=f"{item['task']} target")
        rtr_stats[item["task"]] = finite_stats(item["values"])
    axes[1].set_xlabel("Control sample index (per series)")
    axes[1].set_ylabel("RTR")
    axes[1].set_title("Response-to-period ratio")
    axes[1].grid(alpha=0.25)
    axes[1].legend(ncol=2, fontsize=8)

    fig.savefig(png_path, dpi=160)
    fig.savefig(pdf_path)
    plt.close(fig)
    return {
        "case_directory": str(case["case_dir"]),
        "source_files": case["files"],
        "power_target_mW": case["power_mw"],
        "rtr_targets": dict(zip(TASKS, case["rtr_targets"])),
        "discard_samples": case["discard"],
        "power_W_full_retained_window": finite_stats(power_w),
        "rtr_full_retained_window": rtr_stats,
        "outputs": [str(png_path), str(pdf_path)],
        "note": "Means and population standard deviations summarize the retained sample window; they are not independent-run validation.",
    }


def main(argv: list[str] | None = None) -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=script_dir / "runs" / "JTPC")
    parser.add_argument("--output-dir", type=Path, default=script_dir / "Figures" / "lqr_runs")
    parser.add_argument("--discard", type=int, default=0, help="discard this many initial samples (sample index, not seconds)")
    args = parser.parse_args(argv)
    if args.discard < 0:
        parser.error("--discard must be nonnegative")
    args.runs_dir = args.runs_dir.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    try:
        cases = discover_cases(args.runs_dir)
        if not cases:
            raise RuntimeError(f"no LQR setpoint directories found under {args.runs_dir}; expected runs/JTPC/.../setpoint_POWER_SP_SP_SP")
        # Load every case before creating output so one malformed capture cannot
        # leave a misleading partial set of plots behind.
        loaded_cases = [parse_case(case, args.discard) for case in cases]
        for case in loaded_cases:
            # Preserve batch/workload ancestry when several captures share a
            # setpoint name. A single-case invocation retains its workload name.
            case["output_subdir"] = (
                Path(case["workload_dir"].name)
                if case["case_dir"] == args.runs_dir
                else case["workload_dir"].relative_to(args.runs_dir)
            )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        summary = {"runs_dir": str(args.runs_dir), "output_dir": str(args.output_dir), "cases": [plot_case(case, args.output_dir) for case in loaded_cases]}
        (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"wrote {len(cases)} LQR case plots to {args.output_dir}")
        return 0
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

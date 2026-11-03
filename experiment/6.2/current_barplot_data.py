"""Current-run input adapter for copies of the three original Section 6.2 bars.

Aggregation/window rules follow plot_rtr.py, plot_power.py and plot_utility.py.
Only explicitly selected current solutions are read; archived logs are never
substituted for missing captures. No hardware or collection code is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
METHODS = {
    "JTPC": {"directory": "JTPC", "prefix": "LQR", "label": "JTPC", "color": "#4E79A7", "hatch": "//"},
    "FC": {"directory": "FC", "prefix": "FC_GPU", "label": "FC-GPU", "color": "#F28E2B", "hatch": "oo"},
    "DFS": {"directory": "DFS", "prefix": "DFS", "label": "DFS-only", "color": "#59A14F", "hatch": "**"},
}


def _number(value: float) -> float:
    if not np.isfinite(value) or value < 0:
        raise ValueError(f"RTR targets must be finite and nonnegative: {value}")
    return round(float(value), 12)


def _index(root: Path, solution: str, workload: str) -> tuple[dict, list]:
    folder = root / METHODS[solution]["directory"] / workload
    if not folder.is_dir():
        raise ValueError(
            f"missing current {solution} captures: {folder}. "
            "For LQR-only data, explicitly select --solutions JTPC."
        )
    cases, ignored = {}, []
    for path in sorted(folder.glob("setpoint_*")):
        if not path.is_dir():
            continue
        fields = path.name.removeprefix("setpoint_").split("_")
        if len(fields) != 4:
            raise ValueError(f"expected power and three RTR values in {path}")
        try:
            power = int(fields[0])
            rtrs = tuple(_number(float(value)) for value in fields[1:])
        except ValueError as exc:
            raise ValueError(f"invalid setpoint directory {path}: {exc}") from exc
        if power <= 0:
            raise ValueError(f"power must be positive integer mW in {path}")
        if len(set(rtrs)) != 1:
            ignored.append(str(path))
            print(f"warning: excluding nonuniform task RTR targets from the single-RTR slice: {path}", file=sys.stderr)
            continue
        key = (power, rtrs[0])
        if key in cases:
            raise ValueError(f"duplicate numerical setpoint cases: {cases[key]} and {path}")
        cases[key] = path
    return cases, ignored


def _read(path: Path) -> np.ndarray:
    if not path.is_file():
        raise ValueError(f"missing current telemetry file: {path}")
    try:
        values = np.loadtxt(path, ndmin=1)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if values.ndim != 1 or values.size == 0:
        raise ValueError(f"expected a nonempty, one-value-per-line series: {path}")
    return values


def _source(path: Path, raw: np.ndarray, used: int) -> dict:
    return {
        "file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "raw_samples": int(raw.size), "used_samples": int(used),
    }


def _rtr(case: Path, prefix: str) -> dict:
    streams, sources = [], []
    for task in range(1, 4):
        path = case / f"{prefix}_t{task}_rtr.txt"
        raw = _read(path)
        valid = raw[np.isfinite(raw) & (raw > 0)]
        skip = min(20, valid.size // 5)
        kept = valid[skip:]
        if kept.size == 0:
            raise ValueError(f"no valid RTR samples after the original trimming rule: {path}")
        streams.append(kept)
        source = _source(path, raw, kept.size)
        source.update(valid_samples_before_trim=int(valid.size), initial_valid_samples_discarded=int(skip))
        sources.append(source)
    count = min(stream.size for stream in streams)
    trace = sum(stream[:count] for stream in streams) / 3.0
    return {"mean": float(np.mean(trace)), "std": float(np.std(trace)),
            "aligned_samples": int(count), "sources": sources}


def _power(case: Path, prefix: str) -> dict:
    # Match the original measured series first. The current control-period
    # stream is accepted only when that original file is absent, and recorded.
    candidates = [case / f"{prefix}_finalpowervalues.txt", case / f"{prefix}__powercontrolperiod.txt"]
    path = next((path for path in candidates if path.is_file()), None)
    if path is None:
        raise ValueError(f"missing power telemetry: {candidates[0]} (or {candidates[1].name})")
    raw = _read(path)
    kept = raw[100:-1] if raw.size > 101 else raw
    if not np.all(np.isfinite(kept) & (kept > 0)):
        raise ValueError(f"invalid power in the selected legacy window: {path}; not plotting fabricated/zero power")
    watts = kept / 1000.0
    return {"mean": float(np.mean(watts)), "std": float(np.std(watts)),
            "window": "[100:-1]" if raw.size > 101 else "all",
            "sources": [_source(path, raw, kept.size)]}


def _utility(case: Path, prefix: str, initial_periods: list[float]) -> dict:
    means, sources = [], []
    for task, initial in enumerate(initial_periods, 1):
        path = case / f"{prefix}_t{task}_period.txt"
        raw = _read(path)
        kept = raw[np.isfinite(raw) & (raw > 0)]
        if kept.size == 0:
            raise ValueError(f"no positive period samples: {path}")
        mean = float(np.mean(initial / kept))
        means.append(mean)
        source = _source(path, raw, kept.size)
        source.update(initial_period_ms=float(initial), task_utility=mean)
        sources.append(source)
    return {"mean": float(np.mean(means)), "std": None, "task_means": means, "sources": sources}


def _limits(metric: str, series: list[dict]) -> tuple[float, float]:
    legacy = {"rtr": (0.5, 1.0), "power": (9.5, 13.3), "utility": (0.5, 1.4)}[metric]
    lower = min(float(np.min(item["means"] - item["stds"])) for item in series)
    upper = max(float(np.max(item["means"] + item["stds"])) for item in series)
    if legacy[0] <= lower and upper <= legacy[1]:
        return legacy
    margin = max((upper - lower) * 0.06, 0.05 if metric != "power" else 0.5)
    return min(legacy[0], lower - margin), max(legacy[1], upper + margin)


def prepare_plot(metric: str, argv: list[str] | None = None) -> dict:
    if metric not in ("rtr", "power", "utility"):
        raise ValueError(f"unknown metric: {metric}")
    parser = argparse.ArgumentParser(description=f"Original-style {metric} bars from current Section 6.2 captures")
    parser.add_argument("--runs-dir", type=Path, default=HERE / "runs", help="root containing JTPC/, FC/, DFS/")
    parser.add_argument("--output-dir", type=Path, default=HERE / "Figures" / "current")
    parser.add_argument("--workload", default="hist_stereo_mm")
    parser.add_argument("--solutions", nargs="+", choices=list(METHODS), default=list(METHODS))
    if metric == "rtr":
        parser.add_argument("--power-mw", type=int, default=30000, help="fixed power for the RTR sweep, in mW")
        parser.add_argument("--rtr-setpoints", type=float, nargs="+", help="ordered targets; default discovers all at the fixed power")
    else:
        parser.add_argument("--rtr", type=float, default=0.90, help="common task RTR target for the power sweep")
        parser.add_argument("--power-setpoints", type=int, nargs="+", help="ordered power targets in mW; default discovers all at the fixed RTR")
    if metric == "utility":
        parser.add_argument("--initial-periods-ms", type=float, nargs=3, default=[160.0, 80.0, 60.0],
                            metavar=("HIST", "STEREO", "MM"))
    args = parser.parse_args(argv)
    root = args.runs_dir.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    try:
        if len(set(args.solutions)) != len(args.solutions):
            raise ValueError("--solutions contains duplicates")
        indices, ignored = {}, {}
        for solution in args.solutions:
            indices[solution], ignored[solution] = _index(root, solution, args.workload)
        if metric == "rtr":
            if args.power_mw <= 0:
                raise ValueError("--power-mw must be positive")
            points = ([_number(value) for value in args.rtr_setpoints] if args.rtr_setpoints is not None
                      else sorted({rtr for index in indices.values() for power, rtr in index if power == args.power_mw}))
            keys = [(args.power_mw, point) for point in points]
            reference = np.array(points, dtype=float)
            x_labels = [f"{point:.2f}" for point in points]
            stem = f"rtr_barplot_power_{args.power_mw}mW"
            fixed = {"power_mw": args.power_mw}
        else:
            rtr = _number(args.rtr)
            points = (list(args.power_setpoints) if args.power_setpoints is not None
                      else sorted({power for index in indices.values() for power, point in index if point == rtr}))
            if any(power <= 0 for power in points):
                raise ValueError("power setpoints must be positive integer mW")
            keys = [(point, rtr) for point in points]
            reference = np.array(points, dtype=float) / 1000.0
            x_labels = [f"{point / 1000:g}" for point in points]
            tag = f"{rtr:.6f}".rstrip("0").rstrip(".").replace(".", "p")
            stem = f"{metric}_barplot_RTR_{tag}"
            fixed = {"rtr": rtr}
        if not points:
            raise ValueError(f"no matching {metric} slice found under {root}; check the fixed target and requested solutions")
        if len(set(points)) != len(points):
            raise ValueError("duplicate plotted setpoints")
        if args.solutions != list(METHODS):
            stem += "_" + "_".join(args.solutions)
        initial = getattr(args, "initial_periods_ms", [160.0, 80.0, 60.0])
        if not all(np.isfinite(value) and value > 0 for value in initial):
            raise ValueError("initial periods must be finite positive milliseconds")

        baseline = np.ones(len(points)) if metric == "utility" else reference
        series = [{"key": "reference", "label": "Initial rate" if metric == "utility" else "Set point",
                   "color": "black", "hatch": "", "means": baseline, "stds": np.zeros(len(points))}]
        records = []
        for solution in args.solutions:
            method, rows = METHODS[solution], []
            for key in keys:
                if key not in indices[solution]:
                    raise ValueError(f"missing current {solution} case at power={key[0]} mW, RTR={key[1]:g}, workload={args.workload}")
                case = indices[solution][key]
                row = (_rtr(case, method["prefix"]) if metric == "rtr" else
                       _power(case, method["prefix"]) if metric == "power" else
                       _utility(case, method["prefix"], initial))
                row.update(solution=solution, case_directory=str(case), power_mw=key[0], rtr=key[1])
                rows.append(row)
                records.append(row)
            series.append({"key": solution, "label": method["label"], "color": method["color"], "hatch": method["hatch"],
                           "means": np.array([row["mean"] for row in rows]),
                           "stds": np.array([row["std"] if row["std"] is not None else 0.0 for row in rows])})
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    processing = {
        "rtr": "Per task: retain finite positive RTR; discard first min(20,n//5); truncate three tasks to equal length; mean and population std of the equally averaged trace.",
        "power": "Original power file preferred; use [100:-1] if length>101, otherwise all; mean/population std in mW converted to W. Invalid selected power samples are errors.",
        "utility": "Per task: retain finite positive period-ms; mean(initial_period_ms/current_period_ms); equally average three task means. No error bars, matching the original.",
    }[metric]
    statistics = {
        "metric": metric, "original_script": str(HERE / f"plot_{metric}.py"),
        "runs_root": str(root), "workload": args.workload, "solutions": args.solutions,
        "fixed": fixed, "setpoints": points, "processing": processing,
        "std_ddof": 0 if metric != "utility" else None,
        "uncertainty_note": "Population deviations over retained time samples are not independent-run confidence intervals.",
        "initial_periods_ms": initial if metric == "utility" else None,
        "ignored_nonuniform_rtr_cases": ignored, "cases": records,
        "series": [{"key": item["key"], "label": item["label"], "means": item["means"].tolist(),
                    "stds": item["stds"].tolist() if metric != "utility" else None} for item in series],
        "units": "W" if metric == "power" else "ratio",
    }
    return {"series": series, "x_labels": x_labels,
            "xlabel": "RTR Set point" if metric == "rtr" else "Power Set point (W)",
            "ylabel": {"rtr": "Average RTR", "power": "Average Power (W)", "utility": "Task Utility"}[metric],
            "ylim": _limits(metric, series), "output_stem": output / stem, "statistics": statistics}


def write_statistics(data: dict, outputs: list[Path]) -> Path:
    path = Path(str(data["output_stem"]) + "_statistics.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    statistics = dict(data["statistics"])
    statistics["figure_outputs"] = [str(output.resolve()) for output in outputs]
    path.write_text(json.dumps(statistics, indent=2, allow_nan=False) + "\n")
    print("Saved statistics to:", path)
    return path

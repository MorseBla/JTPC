"""Time-weighted statistics for held telemetry traces.

The standard deviation returned here is a population *temporal SD*: it is the
standard deviation of the piecewise-linear signal over time, not a confidence
interval and not a sample standard deviation of telemetry records.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

try:  # package import
    from .analysis import _trap_mean
except ImportError:  # direct execution / unittest discovery from this folder
    from analysis import _trap_mean


def _points(samples: Iterable[dict[str, Any]], key: str,
            start: float, end: float) -> tuple[list[tuple[float, float]], str | None]:
    """Build the same boundary-bracketed points used by ``_trap_mean``."""
    raw: list[tuple[float, float]] = []
    for row in samples:
        if "t_s" not in row:
            continue
        try:
            t = float(row["t_s"])
        except (TypeError, ValueError):
            return [], "non-numeric timestamp"
        if not math.isfinite(t):
            return [], "nonfinite timestamp"
        if start <= t <= end and (key not in row or row[key] is None):
            return [], "missing/None telemetry in interval"
        if key not in row or row[key] is None:
            continue
        try:
            value = float(row[key])
        except (TypeError, ValueError):
            return [], "non-numeric telemetry"
        if not math.isfinite(value):
            return [], "nonfinite telemetry"
        raw.append((t, value))
    raw.sort()
    if len({t for t, _ in raw}) != len(raw):
        return [], "duplicate timestamps"
    if len(raw) < 2:
        return [], "insufficient samples"

    pts = [(t, v) for t, v in raw if start <= t <= end]
    for boundary in (start, end):
        if any(t == boundary for t, _ in pts):
            continue
        before = [(t, v) for t, v in raw if t < boundary]
        after = [(t, v) for t, v in raw if t > boundary]
        if not before or not after:
            return [], "missing boundary bracket"
        a, b = before[-1], after[0]
        if b[0] <= a[0]:
            return [], "invalid boundary bracket"
        value = a[1] + (b[1] - a[1]) * (boundary - a[0]) / (b[0] - a[0])
        pts.append((boundary, value))
    pts.sort()
    return pts, None


def time_weighted_stats(samples: Iterable[dict[str, Any]], key: str,
                        start_s: float, end_s: float,
                        max_gap_s: float = 1.0) -> dict[str, Any]:
    """Return exact time-weighted mean and population temporal SD.

    Values between timestamps are treated as piecewise linear.  Boundary
    values are interpolated only when bracketed by recorded samples.  A gap
    larger than ``max_gap_s`` makes the result invalid; no values are invented
    to fill it.
    """
    out: dict[str, Any] = {
        "mean": None, "stdev": None, "valid": False, "coverage_s": 0.0,
        "max_gap_s": None, "n": 0, "reason": "invalid interval",
        "stdev_kind": "population temporalSD (not CI)",
    }
    try:
        start, end, limit = float(start_s), float(end_s), float(max_gap_s)
    except (TypeError, ValueError):
        return out
    if not all(math.isfinite(v) for v in (start, end, limit)) or end <= start or limit < 0:
        return out
    out["coverage_s"] = end - start

    samples = list(samples)
    # Delegate the basic interval/gap validation and mean semantics to the
    # shared analysis helper, then use the same bracketed points for moments.
    trap = _trap_mean(samples, key, start, end, limit)
    pts, reason = _points(samples, key, start, end)
    if reason:
        out["reason"] = reason
        return out
    if not trap["valid"]:
        out.update({"max_gap_s": trap["max_gap_s"], "n": len(pts), "reason": trap["reason"]})
        return out
    gaps = [b[0] - a[0] for a, b in zip(pts, pts[1:])]
    gap = max(gaps, default=math.inf)
    if gap > limit:
        out.update({"max_gap_s": gap, "n": len(pts), "reason": "telemetry gap exceeds limit"})
        return out

    duration = end - start
    integral = 0.0
    square_integral = 0.0
    for (t0, a), (t1, b) in zip(pts, pts[1:]):
        dt = t1 - t0
        integral += dt * (a + b) / 2.0
        square_integral += dt * (a * a + a * b + b * b) / 3.0
    mean = integral / duration
    variance = max(0.0, square_integral / duration - mean * mean)
    out.update(mean=mean, stdev=math.sqrt(variance), valid=True,
               max_gap_s=gap, n=len(pts), reason="ok")
    return out

"""Load and validate an immutable system-identification model artifact.

The periodic validation experiment is deliberately a consumer of a model that
was fitted by the identification workflow.  This module does not fit, update,
or infer any matrix entries.  It only validates the artifact's recorded
training contract against the capture configuration and returns a deep copy of
the saved matrix.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
_COMPATIBILITY_FIELDS = ("tasks", "power", "interval_s", "conditions")
_FREQUENCY_TOLERANCE_MHZ = 1e-6  # approximately one Hz


class ModelValidationError(ValueError):
    """Raised when a model artifact is not safe for the requested capture."""


def _fail(message: str) -> None:
    raise ModelValidationError(message)


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be numeric and finite")
    result = float(value)
    if not math.isfinite(result):
        _fail(f"{label} must be numeric and finite")
    return result


def _finite_matrix(value: Any, rows: int, cols: int, label: str, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, list) or len(value) != rows:
        _fail(f"{label} must have {rows} rows")
    for i, row in enumerate(value):
        if not isinstance(row, list) or len(row) != cols:
            _fail(f"{label}[{i}] must have {cols} columns")
        for j, item in enumerate(row):
            if item is None and allow_none:
                continue
            _finite(item, f"{label}[{i}][{j}]")


def _finite_vector(value: Any, length: int, label: str) -> None:
    if not isinstance(value, list) or len(value) != length:
        _fail(f"{label} must have length {length}")
    for i, item in enumerate(value):
        _finite(item, f"{label}[{i}]")


def _same_json(left: Any, right: Any) -> bool:
    """Compare configuration values without allowing representation drift."""
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _validate_configuration(training: Mapping[str, Any], capture: Mapping[str, Any]) -> None:
    for field in _COMPATIBILITY_FIELDS:
        if field not in training:
            _fail(f"training_config is missing compatibility field {field!r}")
        if field not in capture:
            _fail(f"capture_config is missing compatibility field {field!r}")
        if not _same_json(training[field], capture[field]):
            _fail(f"capture configuration is incompatible with trained model: {field}")


def _validate_matrix(matrix: Mapping[str, Any], tasks: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(tasks, list) or not tasks:
        _fail("tasks must be a non-empty list")
    n = len(tasks)
    if any(not isinstance(task, Mapping) for task in tasks):
        _fail("tasks must contain objects")
    names = [task.get("name") for task in tasks]
    if any(not isinstance(name, str) or not name for name in names):
        _fail("tasks must contain non-empty names")
    expected_state = [f"q_{name}" for name in names] + ["P_VIN"]
    expected_input = [f"delta_r_{name}" for name in names] + ["delta_f"]
    expected_row_units = ["ms"] * n + ["W"]
    expected_column_units = ["Hz"] * n + ["MHz"]

    for key, expected, label in (
        ("state_order", expected_state, "state_order"),
        ("input_order", expected_input, "input_order"),
        ("row_units", expected_row_units, "row_units"),
        ("column_units", expected_column_units, "column_units"),
    ):
        if matrix.get(key) != expected:
            _fail(f"{label} does not match capture task order/units")

    size = n + 1
    b_partial = matrix.get("B_partial")
    if b_partial is None:
        _fail("B_partial is required; use null entries for unresolved coefficients")
    _finite_matrix(b_partial, size, size, "B_partial", allow_none=True)
    # B_full is optional: a partial analytical model must remain partial.  If
    # an artifact supplies it, validate it without synthesizing or modifying it.
    if matrix.get("B_full") is not None:
        _finite_matrix(matrix["B_full"], size, size, "B_full")
    _finite_matrix(matrix.get("C"), size, size, "C")
    if "A" in matrix:
        _finite_matrix(matrix.get("A"), size, size, "A")
    identity = [[float(i == j) for j in range(size)] for i in range(size)]
    if matrix['C'] != identity or ('A' in matrix and matrix['A'] != identity):
        _fail('This plotting adapter supports only the saved direct-state C=I and increment model A=I')
    _finite_vector(matrix.get("nominal_q_ms"), n, "nominal_q_ms")
    _finite(matrix.get("nominal_power_W"), "nominal_power_W")
    f0 = _finite(matrix.get("f0_MHz"), "f0_MHz")
    if f0 <= 0:
        _fail("f0_MHz must be positive")
    _finite(matrix.get("alpha_W_per_MHz"), "alpha_W_per_MHz")

    fit = matrix.get("alpha_fit_quality")
    if fit is not None:
        if not isinstance(fit, Mapping):
            _fail("alpha_fit_quality must be an object or null")
        for key in ("frequency_min_MHz", "frequency_max_MHz"):
            if key in fit:
                _finite(fit[key], f"alpha_fit_quality.{key}")
        if "frequency_min_MHz" in fit and "frequency_max_MHz" in fit:
            if float(fit["frequency_min_MHz"]) > float(fit["frequency_max_MHz"]):
                _fail("alpha_fit_quality frequency range is reversed")


def _validate_achieved_frequencies(matrix: Mapping[str, Any], values: Sequence[float] | None) -> None:
    if values is None:
        return
    fit = matrix.get("alpha_fit_quality")
    if not isinstance(fit, Mapping) or "frequency_min_MHz" not in fit or "frequency_max_MHz" not in fit:
        _fail("achieved frequencies require alpha_fit_quality frequency bounds")
    low = float(fit["frequency_min_MHz"]) - _FREQUENCY_TOLERANCE_MHZ
    high = float(fit["frequency_max_MHz"]) + _FREQUENCY_TOLERANCE_MHZ
    for index, value in enumerate(values):
        frequency = _finite(value, f"achieved_frequencies_mhz[{index}]")
        if frequency < low or frequency > high:
            _fail(
                f"achieved frequency {frequency:g} MHz is outside trained alpha range "
                f"[{float(fit['frequency_min_MHz']):g}, {float(fit['frequency_max_MHz']):g}] MHz"
            )


def load_model(
    path: str | Path,
    capture_config: Mapping[str, Any],
    achieved_frequencies_mhz: Sequence[float] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a frozen model and return ``(matrix_copy, provenance)``.

    ``capture_config`` is compared only on the four training-contract fields.
    Validation schedules, telemetry options such as ``allow_missing_temperature``,
    and other capture-only settings may therefore differ.  Source checksums in
    the bundle are provenance metadata; their paths are intentionally not
    dereferenced, keeping the artifact portable.
    """
    if not isinstance(capture_config, Mapping):
        _fail("capture_config must be a mapping")
    model_path = Path(path)
    try:
        raw = model_path.read_bytes()
    except OSError as exc:
        _fail(f"cannot read model artifact {model_path}: {exc}")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"invalid model artifact JSON: {exc}")
    if not isinstance(bundle, Mapping):
        _fail("model artifact root must be an object")
    if bundle.get("schema_version") != SCHEMA_VERSION:
        _fail(f"unsupported model schema_version {bundle.get('schema_version')!r}")
    training = bundle.get("training_config")
    matrix = bundle.get("matrix")
    if not isinstance(training, Mapping):
        _fail("model artifact training_config must be an object")
    if not isinstance(matrix, Mapping):
        _fail("model artifact matrix must be an object")
    _validate_configuration(training, capture_config)
    _validate_matrix(matrix, capture_config["tasks"])
    _validate_achieved_frequencies(matrix, achieved_frequencies_mhz)

    provenance = {
        "model_file": str(model_path.resolve()),
        "model_sha256": digest,
        "schema_version": SCHEMA_VERSION,
        "source_files_sha256": copy.deepcopy(bundle.get("source_files_sha256", {})),
        "notes": copy.deepcopy(bundle.get("notes")),
    }
    return copy.deepcopy(dict(matrix)), provenance


__all__ = ["ModelValidationError", "SCHEMA_VERSION", "load_model"]

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from frozen_model import ModelValidationError, load_model


def _config():
    return {
        "tasks": [
            {"name": "hist", "rate_hz": 6.25, "workload_parameters": {"num_elements": 100}},
            {"name": "stereo", "rate_hz": 12.5, "workload_parameters": {"width": 64}},
        ],
        "power": {"channel": "VIN", "scale_to_W": 0.001},
        "interval_s": 2.0,
        "conditions": {"cooling": "unchanged", "resources": "all"},
        "validation": {"sequence": [{"delta_f_MHz": 10}]},
        "telemetry": {"allow_missing_temperature": False},
    }


def _matrix():
    return {
        "B_full": None,
        "B_partial": [[0.0, None, -0.01], [None, 0.0, -0.02], [0.0, 0.0, 0.003]],
        "C": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "state_order": ["q_hist", "q_stereo", "P_VIN"],
        "input_order": ["delta_r_hist", "delta_r_stereo", "delta_f"],
        "row_units": ["ms", "ms", "W"],
        "column_units": ["Hz", "Hz", "MHz"],
        "nominal_q_ms": [1.25, 2.5],
        "nominal_power_W": 12.5,
        "f0_MHz": 846.0,
        "alpha_W_per_MHz": 0.002,
        "alpha_fit_quality": {"frequency_min_MHz": 315.0, "frequency_max_MHz": 1386.0},
    }


def _artifact(tmp_path):
    bundle = {
        "schema_version": 1,
        "matrix": _matrix(),
        "training_config": _config(),
        "source_files_sha256": {"missing/source.json": "abc"},
        "notes": "portable test artifact",
    }
    path = tmp_path / "model_bundle.json"
    path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return path, bundle


class FrozenModelTests(unittest.TestCase):
  def setUp(self):
    self.tempdir = tempfile.TemporaryDirectory()
    self.addCleanup(self.tempdir.cleanup)
    self.tmp_path = Path(self.tempdir.name)

  def test_load_preserves_matrix_and_records_digest(self):
    path, bundle = _artifact(self.tmp_path)
    original = path.read_bytes()
    matrix, provenance = load_model(path, _config(), [315.0, 846.0, 1386.0000005])
    self.assertEqual(matrix, bundle["matrix"])
    self.assertEqual(provenance["model_file"], str(path.resolve()))
    self.assertEqual(provenance["model_sha256"], hashlib.sha256(original).hexdigest())
    self.assertEqual(provenance["source_files_sha256"], {"missing/source.json": "abc"})
    self.assertEqual(path.read_bytes(), original)


  def test_validation_schedule_and_missing_temperature_are_not_training_contract(self):
    path, _ = _artifact(self.tmp_path)
    capture = copy.deepcopy(_config())
    capture["validation"] = {"sequence": [{"delta_rate_fraction": 0.1}, {"delta_f_MHz": -2}]}
    capture["telemetry"]["allow_missing_temperature"] = True
    load_model(path, capture)


  def test_training_contract_changes_are_rejected(self):
    changes = [
        ("tasks", lambda c: c["tasks"][0]["workload_parameters"].update(num_elements=101)),
        ("tasks", lambda c: c["tasks"][0].update(rate_hz=7.0)),
        ("power", lambda c: c["power"].update(channel="GPU")),
        ("interval_s", lambda c: c.update(interval_s=1.0)),
        ("conditions", lambda c: c["conditions"].update(cooling="fixed-fan")),
    ]
    path, _ = _artifact(self.tmp_path)
    for field, mutator in changes:
      with self.subTest(field=field):
        capture = copy.deepcopy(_config())
        mutator(capture)
        with self.assertRaisesRegex(ModelValidationError, field):
          load_model(path, capture)


  def test_task_order_and_units_are_rejected(self):
    path, bundle = _artifact(self.tmp_path)
    capture = _config()
    for key, value in (
        ("state_order", ["q_stereo", "q_hist", "P_VIN"]),
        ("input_order", ["delta_r_stereo", "delta_r_hist", "delta_f"]),
        ("row_units", ["s", "ms", "W"]),
        ("column_units", ["Hz", "MHz", "MHz"]),
    ):
        changed = copy.deepcopy(bundle)
        changed["matrix"][key] = value
        path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ModelValidationError):
          load_model(path, capture)


  def test_bad_dimensions_and_nonfinite_values_are_rejected(self):
    changes = [
        lambda m: m["B_partial"].pop(),
        lambda m: m["C"].append([0.0, 0.0, 0.0]),
        lambda m: m.update(nominal_q_ms=[1.0]),
        lambda m: m.update(nominal_power_W=float("nan")),
        lambda m: m.update(f0_MHz=0.0),
        lambda m: m.update(alpha_W_per_MHz=float("inf")),
    ]
    for change in changes:
      with self.subTest(change=change):
        path, bundle = _artifact(self.tmp_path)
        changed = copy.deepcopy(bundle)
        change(changed["matrix"])
        path.write_text(json.dumps(changed, allow_nan=True), encoding="utf-8")
        with self.assertRaises(ModelValidationError):
          load_model(path, _config())


  def test_achieved_frequency_must_be_inside_alpha_training_range(self):
    path, _ = _artifact(self.tmp_path)
    with self.assertRaisesRegex(ModelValidationError, "outside trained alpha range"):
      load_model(path, _config(), [314.9])
    with self.assertRaisesRegex(ModelValidationError, "finite"):
      load_model(path, _config(), [float("nan")])


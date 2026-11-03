import json
import tempfile
import unittest
from pathlib import Path

try:
    from .plot_legacy_periodic import fit_line, load_csv, reproduce
except ImportError:  # Direct execution from system_identification_2.
    from plot_legacy_periodic import fit_line, load_csv, reproduce


class LegacyPeriodicTests(unittest.TestCase):
    def test_fit_and_csv_shape(self):
        root = Path(__file__).resolve().parents[1]
        df, cols = load_csv(root / "JTPC_system_validation/validation_control_period.csv")
        self.assertEqual(len(df["control_period"]), 120)
        self.assertEqual(cols, ["task0_rt_ms", "task1_rt_ms"])
        import numpy as np
        self.assertEqual(int((np.diff(df["measured_freq_mhz"], prepend=df["measured_freq_mhz"][0]) != 0).sum()), 29)
        fit = fit_line([1, 2, 3], [2, 4, 6])
        self.assertAlmostEqual(fit["slope"], 2)
        self.assertAlmostEqual(fit["r2"], 1)

    def test_reproduce_writes_artifacts_and_preserves_input(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "JTPC_system_validation/validation_control_period.csv"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix="jtpc_legacy_periodic_") as tmp:
            out = reproduce(source, Path(tmp) / "review")
            self.assertTrue((out / "legacy_periodic_system_validation.png").is_file())
            self.assertTrue((out / "legacy_periodic_system_validation.pdf").is_file())
            metrics = json.loads((out / "metrics.json").read_text())
            self.assertIsNone(metrics["B"])
            self.assertIsNone(metrics["C"])
            self.assertTrue(metrics["source_unchanged"])
            with self.assertRaises(FileExistsError):
                reproduce(source, out)
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

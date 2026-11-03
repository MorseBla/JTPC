"""Synthetic record diagnostics, no hardware or processes."""
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_backlog import diagnose


class DiagnosticTests(unittest.TestCase):
    def fixture(self, root, duration):
        (root/'config.json').write_text(json.dumps({'tasks': [{'name': 'mm'}], 'safety': {'max_lateness_s': .5}}))
        (root/'windows.json').write_text(json.dumps([{'id': 'trial', 'kind': 'alpha', 'rates_hz': {'mm': 10}, 'requested_frequency_hz': 500000000}]))
        rows = [dict(window_id='trial', task='mm', ok=True, release_s=float(i), start_s=float(i),
                     end_s=i+duration, execution_s=.11) for i in range(3)]
        (root/'jobs.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))

    def test_distinguishes_execution_demand_and_wall_delay(self):
        with tempfile.TemporaryDirectory(prefix='jtpc_SYNTHETIC_') as tmp:
            root = Path(tmp)
            self.fixture(root, .8)
            report = diagnose(root)
            task = report['windows'][0]['tasks']['mm']
            self.assertEqual(task['limit_crossings'], 3)
            self.assertAlmostEqual(task['mean_wall_minus_execution_s'], .69)
            self.assertAlmostEqual(report['windows'][0]['observed_event_time_demand_fraction_sum'], 1.1)
            self.assertFalse(report['windows'][0]['capture_complete'])
            self.assertIn('not proof', report['conclusion'])

    def test_partial_line_is_reported(self):
        with tempfile.TemporaryDirectory(prefix='jtpc_SYNTHETIC_') as tmp:
            root = Path(tmp)
            self.fixture(root, .12)
            with (root/'jobs.jsonl').open('a') as file:
                file.write('\n{"truncated":')
            report = diagnose(root)
            self.assertEqual(len(report['parse_errors']), 1)
            self.assertEqual(report['windows'][0]['tasks']['mm']['limit_crossings'], 0)


if __name__ == '__main__':
    unittest.main()

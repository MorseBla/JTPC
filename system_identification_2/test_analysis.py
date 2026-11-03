"""Synthetic fixtures only; no experimental results or hardware interfaces."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis import (analyze, input_coordinates, linear_fit, period_ms_delta_from_rate_hz,
                      predict_one_interval, rate_hz_to_period_ms, _trap_mean, _profile_summary,
                      _alpha_summary, _validation_summary, interval_summaries)


def fixture():
    c = {'tasks': [{'name': 'a', 'rate_hz': 10}], 'profile': {'measured': 2},
         'interval_s': 1, 'alpha': {'min_jobs': 5}, 'telemetry': {'max_gap_s': .3},
         'frequency': {'tolerance_fraction': .02}, 'assumed_context_switch_s': .0008}
    windows, jobs, telemetry = [], [], []
    # Separated steady windows with boundary brackets; discarded transients differ.
    for i, frequency in enumerate([500e6, 700e6, 900e6]):
        start, end = i*5+1., i*5+4.
        w = dict(id=str(i), kind='alpha', start_s=start, end_s=end, settle_start_s=i*5.,
                 requested_frequency_hz=frequency, rates_hz={'a': 10}, capture_complete=True)
        windows.append(w)
        for j in range(31):
            t = start+j*.1
            jobs.append(dict(window_id=str(i), task='a', release_s=t, start_s=t+.001,
                             end_s=t+.01, execution_s=.008, response_s=.008, wall_response_s=.01, ok=True))
        for j in range(36):
            t = start-.2+j*.1
            telemetry.append(dict(t_s=t, frequency_hz=frequency, power_W=2+frequency/1e8, temperature_C=35.))
    return c, windows, jobs, telemetry


class AnalysisTests(unittest.TestCase):
    def test_units_order_alignment(self):
        self.assertEqual(rate_hz_to_period_ms(10), 100)
        self.assertEqual(period_ms_delta_from_rate_hz(10, 20), -50)
        self.assertEqual(input_coordinates({'b': 20, 'a': 10}, 800e6, ['a', 'b']), [10, 20, 800])
        x = predict_one_interval([10, 20], [1, 100], [2, 100], [[2, 0], [0, 3]])
        self.assertEqual(x, [12, 20])
        self.assertEqual(predict_one_interval(x, [2, 100], [2, 100], [[2, 0], [0, 3]]), x)

    def test_fits(self):
        result = linear_fit([500, 700, 900], [7, 9, 11])
        self.assertAlmostEqual(result['slope_W_per_MHz'], .01)
        self.assertAlmostEqual(result['intercept_W'], 2)
        self.assertFalse(linear_fit([500, 500], [7, 8])['valid'])
        self.assertLess(linear_fit([500, 700, 900], [11, 9, 7])['slope_W_per_MHz'], 0)
        self.assertIsNone(linear_fit([500, 700], [7, 9])['slope_se'])

    def test_time_weighting_and_invalid_telemetry(self):
        # Mean of sample values is 2/3; integrated linear signal mean is 1.
        samples = [{'t_s': t, 'p': t} for t in (0, .1, 2)]
        self.assertAlmostEqual(_trap_mean(samples, 'p', 0, 2, 3)['mean'], 1)
        self.assertAlmostEqual(_trap_mean(samples, 'p', .2, 1.8, 3)['mean'], 1)
        self.assertFalse(_trap_mean(samples, 'p', 0, 2, 1)['valid'])
        self.assertFalse(_trap_mean(samples, 'p', -1, 2, 3)['valid'])
        self.assertFalse(_trap_mean(samples+[samples[0]], 'p', 0, 2, 3)['valid'])
        self.assertFalse(_trap_mean([{'t_s': 0, 'p': float('nan')}], 'p', 0, 2, 3)['valid'])

    def test_profile_demand_warmup_and_failure(self):
        c, _, _, _ = fixture()
        w = dict(id='p', kind='profile', task='a', capture_complete=True)
        rows = [dict(task='a', window_id='p', execution_s=x, response_s=99., ok=True, warmup=warm)
                for x, warm in [(10., True), (.01, False), (.02, False)]]
        result = _profile_summary(rows, [w], c)['a']
        self.assertTrue(result['complete'])
        self.assertAlmostEqual(result['mean_ms'], 15.)
        self.assertFalse(_profile_summary(rows[:-1], [w], c)['a']['complete'])
        self.assertFalse(_profile_summary(rows+[dict(window_id='p', ok=False)], [w], c)['a']['complete'])

    def test_alpha_window_quality(self):
        c, w, jobs, telemetry = fixture()
        result = _alpha_summary(jobs, w, telemetry, c)
        self.assertTrue(result['fit']['valid'])
        self.assertEqual(result['usable_trials'], 3)
        self.assertAlmostEqual(result['fit']['slope_W_per_MHz'], .01)
        # Discarded transient samples do not affect fit.
        telemetry += [dict(t_s=0, power_W=9999, frequency_hz=1, temperature_C=99)]
        self.assertAlmostEqual(_alpha_summary(jobs, w, telemetry, c)['fit']['slope_W_per_MHz'], .01)
        bad = copy.deepcopy(w)
        bad[0]['requested_frequency_hz'] *= 2
        self.assertFalse(_alpha_summary(jobs, bad, telemetry, c)['trials'][0]['adequate'])
        fewer = [r for r in jobs if r['window_id'] != '0']
        self.assertFalse(_alpha_summary(fewer, w, telemetry, c)['trials'][0]['adequate'])

    def test_missing_temperature_requires_explicit_opt_out(self):
        c, w, jobs, telemetry = fixture()
        telemetry = [dict(row, temperature_C=None) for row in telemetry]
        strict = _alpha_summary(jobs, w, telemetry, c)
        self.assertEqual(strict['usable_trials'], 0)
        self.assertFalse(strict['fit']['valid'])
        c['telemetry']['allow_missing_temperature'] = True
        permitted = _alpha_summary(jobs, w, telemetry, c)
        self.assertEqual(permitted['usable_trials'], 3)
        self.assertTrue(permitted['fit']['valid'])
        self.assertFalse(permitted['trials'][0]['temperature']['valid'])
        self.assertIsNone(permitted['trials'][0]['temperature']['mean'])
        self.assertIn('GPU temperature unavailable', ' '.join(permitted['fit']['warnings']))
        self.assertFalse(permitted['fit']['reliable_without_review'])

    def test_missing_temperature_plot_is_safe(self):
        c, w, jobs, telemetry = fixture()
        telemetry = [dict(row, temperature_C=None) for row in telemetry]
        c['telemetry']['allow_missing_temperature'] = True
        with tempfile.TemporaryDirectory(prefix='jtpc_NO_TEMP_') as td:
            root = Path(td)
            for name, value in [('config.json', c), ('windows.json', w), ('status.json', {'complete': True})]:
                (root/name).write_text(json.dumps(value))
            (root/'jobs.jsonl').write_text('\n'.join(json.dumps(v) for v in jobs))
            (root/'telemetry.jsonl').write_text('\n'.join(json.dumps(v) for v in telemetry))
            report = analyze(root)
            self.assertTrue(report['alpha']['fit']['valid'])
            self.assertTrue((root/'analysis'/'telemetry_timeseries.png').exists())

    def test_validation_and_completion_indexing(self):
        c, w, jobs, telemetry = fixture()
        for window in w:
            window['kind'] = 'validation'
        w[1]['rates_hz'] = {'a': 11}
        summary = _validation_summary(jobs, w, telemetry, c)
        self.assertIsNone(summary['B_predictions'])
        # Frequency changed: this must not be labeled a zero-rate-power discrepancy.
        self.assertIsNone(summary['windows'][1]['zero_rate_power_discrepancy_W'])
        # A rate-only step at the same achieved frequency exposes the assumed zero.
        w[1]['requested_frequency_hz'] = 500e6
        for sample in telemetry:
            if 5 <= sample['t_s'] < 10:
                sample['frequency_hz'] = 500e6
        rate_only = _validation_summary(jobs, w, telemetry, c)
        self.assertAlmostEqual(rate_only['windows'][1]['zero_rate_power_discrepancy_W'], 2.)
        # Boundary-completed jobs belong to the next half-open interval only.
        boundary_job = dict(task='a', ok=True, end_s=1., release_s=.9, response_s=.1)
        bins = interval_summaries(w, [boundary_job], telemetry, c)
        self.assertEqual(bins[0]['outputs']['a']['response_s']['count'], 0)
        self.assertEqual(bins[1]['outputs']['a']['response_s']['count'], 1)

    def test_synthetic_end_to_end_and_no_overwrite(self):
        c, w, jobs, telemetry = fixture()
        with tempfile.TemporaryDirectory(prefix='jtpc_SYNTHETIC_') as td:
            root = Path(td)
            for name, value in [('config.json', c), ('windows.json', w), ('status.json', {'complete': True})]:
                (root/name).write_text(json.dumps(value))
            for name, value in [('jobs.jsonl', jobs), ('telemetry.jsonl', telemetry)]:
                (root/name).write_text('\n'.join(json.dumps(v) for v in value))
            report = analyze(root)
            self.assertTrue(report['alpha']['fit']['valid'])
            self.assertIsNone(report['model']['B'])
            self.assertEqual(report['model']['assumptions']['context_switch_overhead_s'], .0008)
            self.assertTrue((root/'analysis/model.json').exists())
            self.assertNotEqual(analyze(root)['output_directory'], report['output_directory'])


if __name__ == '__main__':
    unittest.main()

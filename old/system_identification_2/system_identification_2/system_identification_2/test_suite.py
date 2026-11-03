"""Hardware-free orchestration checks; mocks must reject every hardware operation."""
import contextlib
import errno
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('si_suite', HERE / 'suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.c = suite.load_config(HERE / 'config.json')

    def test_temperature_discovery_skips_enodata_gpu_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, kind, value in [('thermal_zone0', 'gpu', 'bad'),
                                      ('thermal_zone1', 'gpu-aux', '41000'),
                                      ('thermal_zone2', 'cpu', '65000')]:
                zone = root/name
                zone.mkdir()
                (zone/'type').write_text(kind)
                (zone/'temp').write_text(value)
            original = suite.textfile
            def read(path):
                if Path(path) == root/'thermal_zone0/temp':
                    raise OSError(errno.ENODATA, 'No data available')
                return original(path)
            with patch.object(suite, 'textfile', side_effect=read):
                source, value, diagnostics = suite.discover_temperature(self.c, root)
            self.assertEqual(source['path'], str(root/'thermal_zone1/temp'))
            self.assertEqual(value, 41)
            self.assertFalse(diagnostics[0]['readable'])
            self.assertIn('No data available', diagnostics[0]['error'])

    def test_temperature_fallback_uses_only_gpu_tegrastats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zone = root/'thermal_zone0'
            zone.mkdir()
            (zone/'type').write_text('gpu')
            (zone/'temp').write_text('unavailable')
            fake = SimpleNamespace(read=lambda: 42.5)
            class Reader:
                def __init__(self, source):
                    self.source = source
                def __enter__(self):
                    return fake
                def __exit__(self, *exc):
                    pass
            with patch.object(suite, 'TemperatureReader', Reader):
                source, value, diagnostics = suite.discover_temperature(self.c, root)
            self.assertEqual(source['backend'], 'tegrastats')
            self.assertEqual(value, 42.5)
            self.assertFalse(diagnostics[0]['readable'])
        self.assertEqual(suite.TemperatureReader.parse('cpu@80C gpu@42.5C soc@65C'), 42.5)
        self.assertIsNone(suite.TemperatureReader.parse('cpu@80C soc@65C'))
        self.assertIsNone(suite.TemperatureReader.parse('notgpu@42C'))

    def test_explicit_temperature_does_not_silently_fallback(self):
        self.c['telemetry']['temperature_path'] = '/fake/gpu/temp'
        with patch.object(suite, 'textfile', side_effect=OSError(errno.ENODATA, 'No data available')), \
             patch.object(suite, 'TemperatureReader', side_effect=AssertionError('must not fallback')):
            with self.assertRaisesRegex(RuntimeError, 'No data available'):
                suite.discover_temperature(self.c)

    def test_temperature_cache_rejects_stale_and_exited_process(self):
        reader = suite.TemperatureReader.__new__(suite.TemperatureReader)
        reader.source = dict(backend='tegrastats', max_age_s=2)
        reader.lock = suite.threading.Lock()
        reader.process = SimpleNamespace(poll=lambda: None)
        reader.last = (time.monotonic(), 42.)
        self.assertEqual(reader.read(), 42.)
        reader.last = (time.monotonic()-3, 42.)
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            reader.read()
        reader.error = 'permission denied'
        reader.process = SimpleNamespace(poll=lambda: 1)
        with self.assertRaisesRegex(RuntimeError, 'exited'):
            reader.read()

    def test_real_thor_line_does_not_imply_gpu_temperature(self):
        line = ('10-30-2026 20:01:07 RAM 4549/125809MB CPU [0%@972] '
                'cpu@33.468C/33.562C tj@34.218C/34.312C '
                'soc012@34.218C/34.312C soc345@33.218C/33.218C '
                'VDD_GPU 0mW/0mW/0mW VIN 14320mW/12726mW/14976mW')
        self.assertIsNone(suite.TemperatureReader.parse(line))
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(suite, 'TemperatureReader', side_effect=RuntimeError('No gpu@...C: '+line)):
            source, value, diagnostics = suite.discover_temperature(self.c, Path(tmp))
        self.assertEqual(source['backend'], 'unavailable')
        self.assertIsNone(value)
        self.assertIn(line, source['reason'])
        info = dict(temperature_source=source)
        with self.assertRaisesRegex(RuntimeError, '--allow-missing-temperature'):
            suite.require_capture_temperature(self.c, info)
        self.c['telemetry']['allow_missing_temperature'] = True
        suite.require_capture_temperature(self.c, info)

    def test_unavailable_temperature_reader_launches_nothing(self):
        with patch.object(suite.subprocess, 'Popen', side_effect=AssertionError('no monitor launch')):
            with suite.TemperatureReader({'backend': 'unavailable'}) as reader:
                self.assertIsNone(reader.read())

    def test_preflight_reports_missing_temperature_as_not_capture_ready(self):
        # Every path is an ordinary fixture; all /sys inventories are mocked out.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for key, value in dict(available_frequencies='100 200 300', min_freq='100',
                                   max_freq='300', cur_freq='200', governor='fixture').items():
                (root/key).write_text(value)
            self.c['frequency']['devfreq_path'] = tmp
            with patch.object(suite.Path, 'glob', return_value=[]), \
                 patch.object(suite, 'discover_temperature', return_value=({'backend': 'unavailable', 'reason': 'no GPU field'}, None, [])), \
                 patch('shutil.which', return_value=None), \
                 patch.object(suite.subprocess, 'check_output', return_value='14000'):
                info = suite.inspect_target(self.c)
            self.assertFalse(info['capture_ready'])
            self.assertFalse(info['gpu_temperature_available'])
            self.assertIsNone(info['temperature_C'])
            self.assertEqual(info['power_W'], 14.)

    def test_frequency_selection(self):
        ref, sweep, _ = suite.select_frequencies([100, 200, 400, 500, 900, 1000], {})
        self.assertEqual(ref, 500)
        self.assertEqual(len(sweep), 5)
        self.assertEqual(suite.select_frequencies([720000000], {})[:2], (720000000, [720000000]))
        with self.assertRaises(ValueError):
            suite.select_frequencies([100, 200], {'reference_hz': 150})
        with self.assertRaises(ValueError):
            suite.select_frequencies([100], {'levels_hz': [200]})
        self.assertEqual(suite.select_frequencies([100, 200, 300], {'range_hz': [150, 350]})[0], 200)

    def test_sequences(self):
        info = {'reference_hz': 500, 'sweep_hz': [400, 500, 600], 'intended_frequencies_hz': [400, 500, 600]}
        seq = suite.make_sequence(self.c, info, 'alpha')
        self.assertEqual(seq, suite.make_sequence(self.c, info, 'alpha'))
        alpha = [w for w in seq if w['kind'] == 'alpha']
        self.assertEqual(len(alpha), 9)
        self.assertTrue(all(w['rates_hz'] == seq[0]['rates_hz'] for w in seq))
        validation = suite.make_sequence(self.c, info, 'validate')
        self.assertTrue(all(w['kind'] == 'validation' for w in validation))
        self.assertEqual(validation[0]['rates_hz'], validation[-1]['rates_hz'])
        self.c['validation']['rate_fraction'] = 10
        with self.assertRaises(ValueError):
            suite.make_sequence(self.c, info, 'validate')

    def test_dry_run_has_no_hardware_or_launch_path(self):
        for mode in ('profile', 'alpha', 'validate', 'preflight', 'reset', 'analyze'):
            with patch.object(suite, 'target_guard', side_effect=AssertionError('hardware')), \
                 patch.object(suite, 'inspect_target', side_effect=AssertionError('sysfs')), \
                 patch.object(suite.subprocess, 'Popen', side_effect=AssertionError('launch')), \
                 patch.object(suite.os, 'killpg', side_effect=AssertionError('signal')), \
                 patch.object(suite.sys, 'argv', ['suite.py', mode, '--dry-run']), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                suite.main()
                result = json.loads(output.getvalue())
                self.assertTrue(result['dry_run'])
                self.assertFalse(result['writes_or_launches_performed'])

    def test_clock_bound_order_and_restore(self):
        # Only ordinary temporary files, never real sysfs.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for name, value in {'min_freq': '100', 'max_freq': '500', 'governor': 'example'}.items():
                (p / name).write_text(value)
            c = suite.Clock({'devfreq_path': tmp, 'clock_snapshot': {'min_freq': '100', 'max_freq': '500'}})
            c.set(700)
            self.assertEqual((p / 'min_freq').read_text(), '700')
            c.set(200)
            self.assertEqual((p / 'max_freq').read_text(), '200')
            c.restore()
            self.assertEqual((p / 'min_freq').read_text(), '100')
            self.assertEqual((p / 'max_freq').read_text(), '500')
            self.assertEqual((p / 'governor').read_text(), 'example')

    def test_synthetic_capture_restores_clocks_and_ends_windows(self):
        # Fake protocol workers and ordinary files only. No processes or sysfs.
        c = self.c
        c['tasks'] = [dict(c['tasks'][0], rate_hz=100)]
        c['alpha'].update(discard_s=.01, measure_s=.02, repeats=1, reference_every=5)
        c['telemetry']['period_s'] = .005
        events, closed = [], []
        class FakeWorker:
            def __init__(self, task, env, logfile, timeout):
                self.task = task
                self.p = SimpleNamespace(pid=99999999)
            def read(self, timeout=None):
                return {'ready': True}
            def job(self, release, period=0):
                now = time.monotonic()
                return dict(task=self.task['name'], release_s=release, start_s=now,
                            end_s=now, execution_s=.001, response_s=.001, ok=True)
            def close(self):
                closed.append(self.task['name'])
        class FakeClock:
            def __init__(self, info):
                self.path = Path(info['devfreq_path'])
            def set(self, f):
                events.append(time.monotonic())
            def restore(self):
                events.append('restored')
        with tempfile.TemporaryDirectory(prefix='jtpc_SYNTHETIC_') as tmp:
            out = Path(tmp)
            (out/'cur_freq').write_text('500')
            (out/'temp').write_text('35000')
            info = dict(devfreq_path=tmp, temperature_path=str(out/'temp'), reference_hz=500,
                        sweep_hz=[500], intended_frequencies_hz=[500])
            with patch.object(suite, 'Worker', FakeWorker), patch.object(suite, 'Clock', FakeClock), \
                 patch.object(suite.subprocess, 'check_output', return_value='10000'), \
                 patch.object(suite.ctypes, 'CDLL', return_value=SimpleNamespace(sem_unlink=lambda _: 0)):
                suite.capture(c, info, 'alpha', out)
            windows = json.loads((out/'windows.json').read_text())
            self.assertTrue(all(w['capture_complete'] for w in windows))
            # Each frequency hold covers the FULL requested measurement window.
            for before, next_change in zip(windows, events[1:-1]):
                self.assertGreaterEqual(next_change, before['end_s'])
            self.assertEqual(events[-1], 'restored')
            self.assertTrue(closed)
            self.assertTrue(json.loads((out/'cleanup.json').read_text())['clock_bounds_restored'])

    def test_synthetic_capture_failure_restores_clock(self):
        class BrokenWorker:
            def __init__(self, *args):
                self.p = SimpleNamespace(pid=99999999)
            def read(self, timeout=None):
                return {'ready': True}
            def job(self, *args):
                raise RuntimeError('synthetic job failure')
            def close(self):
                pass
        restored = []
        class FakeClock:
            def __init__(self, info):
                self.path = Path(info['devfreq_path'])
            def set(self, f):
                pass
            def restore(self):
                restored.append(True)
        self.c['tasks'] = [self.c['tasks'][0]]
        with tempfile.TemporaryDirectory(prefix='jtpc_SYNTHETIC_') as tmp:
            out = Path(tmp)
            (out/'cur_freq').write_text('500')
            (out/'temp').write_text('35000')
            info = dict(devfreq_path=tmp, temperature_path=str(out/'temp'), reference_hz=500, sweep_hz=[500])
            with patch.object(suite, 'Worker', BrokenWorker), patch.object(suite, 'Clock', FakeClock), \
                 patch.object(suite.subprocess, 'check_output', return_value='10000'), \
                 patch.object(suite.ctypes, 'CDLL', return_value=SimpleNamespace(sem_unlink=lambda _: 0)):
                with self.assertRaisesRegex(RuntimeError, 'synthetic job failure'):
                    suite.capture(self.c, info, 'profile', out)
            self.assertEqual(restored, [True])
            self.assertIn('synthetic job failure', (out/'jobs.jsonl').read_text())


if __name__ == '__main__':
    unittest.main()

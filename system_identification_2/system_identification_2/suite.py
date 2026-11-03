"""Isolated, controller-free JTPC capture. Hardware access requires --target-thor."""
import argparse
import ctypes
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent


def save(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def load_config(path):
    c = json.loads(Path(path).read_text())
    names = [t['name'] for t in c['tasks']]
    if any(not name or any(not (ch.isalnum() or ch in '_-') for ch in name) for name in names):
        raise ValueError('Task names must contain only letters, numbers, underscores or hyphens')
    if not names or len(names) != len(set(names)):
        raise ValueError('Task names must be nonempty and unique')
    for t in c['tasks']:
        if not all(math.isfinite(t[k]) for k in ('min_rate_hz', 'rate_hz', 'max_rate_hz')) or not (0 < t['min_rate_hz'] <= t['rate_hz'] <= t['max_rate_hz']):
            raise ValueError('Invalid rate bounds: ' + t['name'])
        if not t['command'] or not all(isinstance(s, str) for s in t['command']):
            raise ValueError('Commands must be argv arrays')
    for v in (c['interval_s'], c['telemetry']['period_s'], c['alpha']['measure_s'],
              c['validation']['measure_s'], c['safety']['job_timeout_s']):
        if not math.isfinite(v) or v <= 0:
            raise ValueError('Timing values must be finite and positive')
    if any(type(c['profile'][k]) is not int for k in ('warmup', 'measured')):
        raise ValueError('Profile invocation counts must be integers')
    if not math.isfinite(c['assumed_context_switch_s']) or c['assumed_context_switch_s'] < 0:
        raise ValueError('Assumed context overhead must be finite and nonnegative')
    if not math.isfinite(c['power']['scale_to_W']) or c['power']['scale_to_W'] <= 0:
        raise ValueError('Power scale must be finite and positive')
    if c['profile']['warmup'] < 0 or c['profile']['measured'] < 2:
        raise ValueError('Need >=2 measured profile invocations')
    if c['alpha']['repeats'] < 1 or c['alpha']['reference_every'] < 1:
        raise ValueError('Invalid repeat/reference count')
    for part in ('alpha', 'validation'):
        if c[part]['discard_s'] < 0:
            raise ValueError('Negative settling duration')
    return c


def target_guard(enabled):
    if not enabled:
        raise RuntimeError('Hardware modes require --target-thor on the Jetson AGX Thor')
    model = Path('/proc/device-tree/model').read_bytes().decode(errors='replace').strip('\0')
    if 'thor' not in model.lower():
        raise RuntimeError('Target device-tree model does not identify Thor: ' + model)
    return model


def select_frequencies(levels, config):
    levels = sorted(set(int(x) for x in levels if int(x) > 0))
    if config.get('range_hz'):
        low, high = config['range_hz']
        levels = [x for x in levels if low <= x <= high]
    if not levels:
        raise ValueError('No available levels in intended range')
    ref = config.get('reference_hz')
    if ref is None:
        interior = levels[1:-1] or levels
        ref = min(interior, key=lambda x: (abs(x - (levels[0] + levels[-1]) / 2), x))
    if ref not in levels:
        raise ValueError('Reference must be an available level in intended range')
    if config.get('levels_hz'):
        sweep = config['levels_hz']
    elif len(levels) == 1:
        sweep = levels
    else:
        count = min(5, len(levels))
        sweep = [levels[round(i * (len(levels)-1) / (count-1))] for i in range(count)]
    if not set(sweep).issubset(levels):
        raise ValueError('Sweep contains unsupported/out-of-range frequencies')
    return ref, sorted(set(sweep)), levels


def textfile(path):
    return Path(path).read_text().strip()


def sysfs_temperature(path):
    try:
        value = float(textfile(path)) / 1000
        if not math.isfinite(value) or not -273.15 <= value <= 300:
            raise ValueError('invalid millidegree-Celsius value')
        return value
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Cannot read temperature {path}: {exc}') from exc


def discover_temperature(c, thermal_root=Path('/sys/class/thermal')):
    """Select a functioning GPU sensor; never substitute CPU/SoC temperature."""
    settings = c['telemetry']
    backend = settings.get('temperature_backend', 'auto')
    if backend not in ('auto', 'sysfs', 'tegrastats'):
        raise ValueError('temperature_backend must be auto, sysfs or tegrastats')
    explicit = settings.get('temperature_path')
    if explicit and backend == 'tegrastats':
        raise ValueError('Clear temperature_path when selecting tegrastats')
    if explicit:
        value = sysfs_temperature(explicit)  # Explicit selections fail closed.
        return dict(backend='sysfs', path=str(explicit)), value, []
    candidates, diagnostics = [], []
    if backend != 'tegrastats':
        for zone in sorted(Path(thermal_root).glob('thermal_zone*')):
            try:
                label = textfile(zone / 'type')
            except OSError as exc:
                diagnostics.append(dict(path=str(zone), error=str(exc)))
                continue
            if 'gpu' not in label.lower():
                continue
            path = zone / 'temp'
            try:
                value = sysfs_temperature(path)
                candidates.append((path, value, label))
                diagnostics.append(dict(path=str(path), type=label, readable=True, temperature_C=value))
            except RuntimeError as exc:
                diagnostics.append(dict(path=str(path), type=label, readable=False, error=str(exc)))
        if len(candidates) == 1:
            path, value, label = candidates[0]
            return dict(backend='sysfs', path=str(path), type=label), value, diagnostics
        if len(candidates) > 1:
            raise RuntimeError('Set telemetry.temperature_path to one readable GPU sensor. Inspection: '+json.dumps(diagnostics))
        if backend == 'sysfs':
            return dict(backend='unavailable', reason='No readable GPU thermal node'), None, diagnostics
    # ENODATA nodes do not imply a usable reading, nor permit a CPU substitute.
    source = dict(backend='tegrastats', command=['tegrastats', '--interval', str(max(100, round(settings['period_s']*1000)))],
                  field='gpu@...C', max_age_s=settings.get('temperature_max_age_s', 2.0))
    try:
        with TemperatureReader(source) as reader:
            value = reader.read()
    except (OSError, RuntimeError) as exc:
        return dict(backend='unavailable', reason=str(exc), attempted_source=source), None, diagnostics
    return source, value, diagnostics


class TemperatureReader:
    """Own one telemetry-only tegrastats process; cache fresh GPU readings."""
    def __init__(self, source, raw_path=None):
        self.source = source
        self.process = None
        self.thread = None
        self.raw_file = None
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.last = None
        self.error = None
        if source['backend'] in ('sysfs', 'unavailable'):
            return
        try:
            self.raw_file = open(raw_path, 'w', buffering=1) if raw_path else None
            self.process = subprocess.Popen(source['command'], cwd=ROOT, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                                            start_new_session=True)
            self.thread = threading.Thread(target=self._consume, daemon=True)
            self.thread.start()
            if not self.ready.wait(source.get('startup_timeout_s', 5.0)):
                raise RuntimeError('No gpu@...C temperature observed in tegrastats; CPU/tj/SoC readings are not GPU substitutes. Last output: '+str(self.error or 'timeout'))
            self.read()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def parse(line):
        match = re.search(r'(?<![A-Za-z0-9_])gpu@(-?\d+(?:\.\d+)?)C\b', line, re.IGNORECASE)
        if not match:
            return None
        value = float(match.group(1))
        return value if math.isfinite(value) and -273.15 <= value <= 300 else None

    def _consume(self):
        try:
            for line in self.process.stdout:
                now = time.monotonic()
                if self.raw_file:
                    self.raw_file.write(json.dumps(dict(t_s=now, raw=line.rstrip()))+'\n')
                value = self.parse(line)
                with self.lock:
                    if value is not None:
                        self.last = (now, value)
                        self.ready.set()
                    else:
                        self.error = line.strip()
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    def read(self):
        if self.source['backend'] == 'unavailable':
            return None
        if self.source['backend'] == 'sysfs':
            return sysfs_temperature(self.source['path'])
        with self.lock:
            last = self.last
        if self.process.poll() is not None:
            raise RuntimeError('Owned tegrastats process exited: '+str(self.error))
        if last is None or time.monotonic()-last[0] > self.source.get('max_age_s', 2.0):
            raise RuntimeError('GPU temperature is missing/stale; no replacement temperature used')
        return last[1]

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.thread:
                self.thread.join(timeout=2)
            self.process.stdout.close()
        if self.raw_file:
            self.raw_file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def inspect_target(c):
    candidates = sorted(p for p in Path('/sys/class/devfreq').glob('*')
                        if 'gpu' in p.name.lower() or 'gpu' in str(p.resolve()).lower())
    requested = c['frequency']['devfreq_path']
    if requested:
        candidates = [Path(requested)]
    # Never guess which GPU clock domain is the actuator.
    preferred = [p for p in candidates if p.name == 'gpu-gpc-0']
    if not requested and len(preferred) == 1:
        candidates = preferred
    if len(candidates) != 1:
        raise RuntimeError('Set frequency.devfreq_path from target GPU candidates: ' + str(candidates))
    p = candidates[0]
    levels = [int(x) for x in textfile(p / 'available_frequencies').split()]
    original_low, original_high = int(textfile(p / 'min_freq')), int(textfile(p / 'max_freq'))
    allowed = [f for f in levels if original_low <= f <= original_high]
    ref, sweep, intended = select_frequencies(allowed, c['frequency'])
    temperature_source, temperature_C, temperature_diagnostics = discover_temperature(c)
    sensors = {}
    for node in Path('/sys/class/hwmon').glob('hwmon*'):
        for f in list(node.glob('pwm*')) + list(node.glob('fan*_input')):
            if f.is_file():
                try:
                    sensors[str(f)] = textfile(f)
                except OSError:
                    pass
    mode = subprocess.run(['nvpmodel', '-q'], capture_output=True, text=True, timeout=10) if __import__('shutil').which('nvpmodel') else None
    power = subprocess.check_output(c['power']['command'], cwd=ROOT, text=True, timeout=5)
    if not math.isfinite(float(power)) or float(power) <= 0:
        raise RuntimeError('Invalid configured power signal')
    return {'devfreq_path': str(p), 'available_frequencies_hz': levels,
            'intended_frequencies_hz': intended, 'reference_hz': ref, 'sweep_hz': sweep,
            'clock_snapshot': {k: textfile(p / k) for k in ('governor', 'min_freq', 'max_freq', 'cur_freq')},
            'temperature_path': temperature_source.get('path'), 'temperature_C': temperature_C,
            'temperature_source': temperature_source, 'temperature_inspection': temperature_diagnostics,
            'gpu_temperature_available': temperature_C is not None,
            'capture_ready': temperature_C is not None or c['telemetry'].get('allow_missing_temperature', False),
            'temperature_limitation': None if temperature_C is not None else 'GPU temperature unavailable: thermal drift/throttling cannot be assessed; capture requires --allow-missing-temperature',
            'power_W': float(power) * c['power']['scale_to_W'], 'power_channel': c['power'],
            'fan_snapshot': sensors, 'nvpmodel_query': None if mode is None else {'stdout': mode.stdout, 'stderr': mode.stderr, 'returncode': mode.returncode},
            'alpha_possible': len(set(sweep)) >= 2,
            'mps_environment': {k: v for k, v in os.environ.items() if k.startswith('CUDA_MPS')},
            'conditions': c['conditions']}


def require_capture_temperature(c, info):
    """Preflight may report missing sensors; capture requires an explicit opt-out."""
    if info.get('temperature_source', {}).get('backend') == 'unavailable' and not c['telemetry'].get('allow_missing_temperature', False):
        raise RuntimeError('GPU temperature is unavailable. Preflight is read-only and completed, but capture is blocked before workloads or clock changes. '+
                           'Supply a functioning GPU sensor, or explicitly pass --allow-missing-temperature to capture without GPU temperature. '+
                           'This records null temperatures and cannot assess thermal drift/throttling. Source diagnostic: '+info['temperature_source'].get('reason', 'unavailable'))


class Clock:
    """Thor path adaptation of scripts/set_gpu_freq.sh min/max locking.

    Keep current governor and thermal protection; order bounds safely. The old
    script's hard-coded path and userspace governor cannot be reused on Thor.
    """
    def __init__(self, info):
        self.path = Path(info['devfreq_path'])
        self.snapshot = info['clock_snapshot']

    def bounds(self, low, high):
        current_high = int(textfile(self.path / 'max_freq'))
        if low > current_high:
            (self.path / 'max_freq').write_text(str(high))
        (self.path / 'min_freq').write_text(str(low))
        (self.path / 'max_freq').write_text(str(high))

    def set(self, frequency):
        self.bounds(frequency, frequency)

    def restore(self):
        self.bounds(int(self.snapshot['min_freq']), int(self.snapshot['max_freq']))
        # Governor was never modified, so restoring it is neither needed nor safe.


def conflicts(c):
    found = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            argv = (p / 'cmdline').read_bytes().split(b'\0')
            if argv and Path(os.fsdecode(argv[0])).name in c['safety']['conflict_names']:
                found.append({'pid': int(p.name), 'argv': [os.fsdecode(x) for x in argv if x]})
        except (OSError, ValueError):
            pass
    if found:
        raise RuntimeError('Stop existing controller/test tasks manually before capture: ' + json.dumps(found))


class Worker:
    def __init__(self, task, env, logfile, timeout):
        self.task = task
        self.log = open(logfile, 'w')
        self.p = subprocess.Popen(task['command'], cwd=ROOT, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=self.log, text=True,
                                  bufsize=1, env=env, start_new_session=True)
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.p.stdout, selectors.EVENT_READ)
        self.timeout = timeout

    def read(self, timeout=None):
        if not self.sel.select(self.timeout if timeout is None else timeout):
            raise RuntimeError('Worker timeout: ' + self.task['name'])
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError('Worker exited: ' + self.task['name'])
        result = json.loads(line)
        if result.get('ok') is False:
            raise RuntimeError('Worker failure: ' + str(result))
        return result

    def job(self, release, period=0.0):
        self.p.stdin.write(f'run {release:.9f} {period:.12f}\n')
        self.p.stdin.flush()
        row = self.read()
        for key in ('start_s', 'end_s', 'execution_s', 'response_s'):
            if key not in row or not math.isfinite(row[key]):
                raise RuntimeError('Invalid worker response: ' + str(row))
        if row['end_s'] < row['start_s'] or row['execution_s'] <= 0:
            raise RuntimeError('Invalid completed-work timing')
        row['release_s'] = release
        row['task'] = self.task['name']
        row['ok'] = True
        return row

    def close(self):
        try:
            if self.p.poll() is None:
                self.p.stdin.write('quit\n')
                self.p.stdin.flush()
                self.p.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if self.p.poll() is None:
            os.killpg(self.p.pid, signal.SIGTERM)
            try:
                self.p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.p.pid, signal.SIGKILL)
                self.p.wait()
        self.sel.close()
        for f in (self.p.stdin, self.p.stdout, self.log):
            f.close()


def make_sequence(c, info, mode):
    ref, levels = info['reference_hz'], info['sweep_hz']
    rates = {t['name']: t['rate_hz'] for t in c['tasks']}
    if mode == 'profile':
        return [dict(id=f'profile_{t["name"]}', kind='profile', task=t['name'], requested_frequency_hz=ref, rates_hz={t['name']: t['rate_hz']}) for t in c['tasks']]
    rows = []
    if mode == 'alpha':
        rng = random.Random(c['alpha']['seed'])
        order = []
        for _ in range(c['alpha']['repeats']):
            copy = list(levels)
            rng.shuffle(copy)
            order.extend(copy)
        rows.append(('drift_reference', ref, rates))
        for i, f in enumerate(order):
            rows.append(('alpha', f, rates))
            if (i + 1) % c['alpha']['reference_every'] == 0:
                rows.append(('drift_reference', ref, rates))
        rows.append(('drift_reference', ref, rates))
    else:
        custom = c['validation']['sequence']
        if custom:
            rows = [('validation', x['frequency_hz'], x['rates_hz']) for x in custom]
        else:
            # Return to nominal between steps; frequency step is one available OPP.
            nearby = sorted(info['intended_frequencies_hz'], key=lambda f: (abs(f-ref), f))
            other = next((f for f in nearby if f != ref), ref)
            fraction = c['validation']['rate_fraction']
            rows = [('validation', ref, rates)]
            if other != ref:
                rows += [('validation', other, rates), ('validation', ref, rates)]
            for task in c['tasks']:
                changed = dict(rates)
                changed[task['name']] *= 1 + fraction
                rows += [('validation', ref, changed), ('validation', ref, rates)]
            combined = {k: v * (1 + fraction) for k, v in rates.items()}
            rows += [('validation', other, combined), ('validation', ref, rates),
                     ('validation', ref, {k: v * (1-fraction) for k, v in rates.items()}), ('validation', ref, rates)]
        for _, f, r in rows:
            if f not in info['intended_frequencies_hz'] or set(r) != set(rates):
                raise ValueError('Validation step has unsupported frequency/task set')
            for t in c['tasks']:
                if not t['min_rate_hz'] <= r[t['name']] <= t['max_rate_hz']:
                    raise ValueError('Validation rate step out of bounds')
    for i, (kind, f, r) in enumerate(rows):
        rows[i] = dict(id=f'{i:03d}_{kind}', kind=kind, requested_frequency_hz=f, rates_hz=r)
    return rows


def capture(c, info, mode, out):
    stop = threading.Event()
    errors = []
    lock = threading.Lock()
    workers = {}
    windows = []
    clock = Clock(info)
    sem_name = '/jtpc_si_' + uuid.uuid4().hex
    jobs = open(out / 'jobs.jsonl', 'w', buffering=1)
    telem = open(out / 'telemetry.jsonl', 'w', buffering=1)
    old_handlers = {}

    def interrupt(signum, frame):
        stop.set()
        raise KeyboardInterrupt('signal ' + str(signum))

    def emit(file, row):
        with lock:
            file.write(json.dumps(row, allow_nan=False) + '\n')

    def telemetry():
        while not stop.is_set():
            before = time.monotonic()
            try:
                raw = subprocess.check_output(c['power']['command'], cwd=ROOT, text=True, timeout=5)
                after = time.monotonic()
                power = float(raw) * c['power']['scale_to_W']
                if not math.isfinite(power) or power <= 0:
                    raise ValueError('Invalid power sample')
                emit(telem, dict(t_s=(before + after)/2, read_duration_s=after-before,
                                 power_raw=raw.strip(), power_W=power,
                                 frequency_hz=int(textfile(clock.path / 'cur_freq')),
                                 temperature_C=temperature.read()))
            except Exception as exc:
                emit(telem, dict(t_s=time.monotonic(), error=str(exc)))
                errors.append('Telemetry: ' + str(exc))
                stop.set()
            stop.wait(max(0, c['telemetry']['period_s'] - (time.monotonic()-before)))

    thread = None
    temperature = None
    try:
        temperature = TemperatureReader(info.get('temperature_source', {'backend': 'sysfs', 'path': info['temperature_path']}),
                                        out / 'temperature_tegrastats.jsonl')
        if temperature.process:
            save(out / 'temperature_process.json', {'pid': temperature.process.pid, 'command': temperature.source['command'], 'started_s': time.monotonic()})
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, interrupt)
        thread = threading.Thread(target=telemetry)
        thread.start()
        sequence = make_sequence(c, info, mode)
        save(out / 'plan.json', sequence)
        for window in sequence:
            if stop.is_set():
                raise RuntimeError('Capture stopped: ' + str(errors))
            clock.set(window['requested_frequency_hz'])
            needed = [t for t in c['tasks'] if t['name'] in window['rates_hz']]
            for name in list(workers):
                if name not in window['rates_hz']:
                    workers.pop(name).close()
            for t in needed:
                if t['name'] not in workers:
                    env = dict(os.environ, JTPC_SI_SEMAPHORE=sem_name,
                               JTPC_SI_TASK_INDEX=str([x['name'] for x in c['tasks']].index(t['name'])))
                    w = Worker(t, env, out / (window['id'] + '_' + t['name'] + '.stderr'), c['safety']['job_timeout_s'])
                    workers[t['name']] = w
                    with open(out / 'processes.jsonl', 'a') as process_log:
                        process_log.write(json.dumps({'pid': w.p.pid, 'process_group': w.p.pid, 'task': t['name'], 'command': t['command'], 'semaphore': sem_name, 'started_s': time.monotonic()}) + '\n')
                    ready = w.read(c['safety']['ready_timeout_s'])
                    save(out / (window['id'] + '_' + t['name'] + '_ready.json'), ready)
                    if not ready.get('ready'):
                        raise RuntimeError('Missing worker READY')
            if mode == 'profile':
                # Both warmup and measurement are isolated, back-to-back completed jobs.
                window['settle_start_s'] = time.monotonic()
                window['start_s'] = None
                windows.append(window)
                save(out / 'windows.json', windows)
                for i in range(c['profile']['warmup'] + c['profile']['measured']):
                    if stop.is_set():
                        raise RuntimeError('Profile interrupted')
                    if i == c['profile']['warmup']:
                        window['start_s'] = time.monotonic()
                    try:
                        row = workers[window['task']].job(time.monotonic())
                    except Exception as exc:
                        emit(jobs, {'task': window['task'], 'window_id': window['id'], 'ok': False,
                                    'error': str(exc), 't_s': time.monotonic(), 'invocation': i})
                        raise
                    row.update(frequency_hz=int(textfile(clock.path / 'cur_freq')),
                               temperature_C=temperature.read(),
                               requested_frequency_hz=window['requested_frequency_hz'])
                    row.update(window_id=window['id'], warmup=i < c['profile']['warmup'], invocation=i)
                    emit(jobs, row)
                window['end_s'] = time.monotonic()
            else:
                settings = c['alpha'] if mode == 'alpha' else c['validation']
                origin = time.monotonic() + 0.1
                window.update(settle_start_s=origin, start_s=origin + settings['discard_s'],
                              end_s=origin + settings['discard_s'] + settings['measure_s'])
                windows.append(window)
                save(out / 'windows.json', windows)

                def periodic(t):
                    period = 1 / window['rates_hz'][t['name']]
                    release = origin
                    try:
                        while release < window['end_s'] and not stop.is_set():
                            if stop.wait(max(0, release - time.monotonic())):
                                break
                            row = workers[t['name']].job(release, period)
                            row.update(window_id=window['id'])
                            emit(jobs, row)
                            # Bound release lateness; preserve timings to distinguish transient delay from overload.
                            wall_response = row['end_s'] - release
                            limit = period + c['safety']['max_lateness_s']
                            if wall_response > limit:
                                diagnostic = dict(task=t['name'], window_id=window['id'],
                                    requested_frequency_hz=window['requested_frequency_hz'],
                                    rate_hz=window['rates_hz'][t['name']], period_s=period,
                                    wall_response_s=wall_response, execution_s=row['execution_s'],
                                    dispatch_lateness_s=max(0., row['start_s']-release),
                                    excess_past_period_s=wall_response-period,
                                    allowed_excess_s=c['safety']['max_lateness_s'], limit_wall_response_s=limit)
                                emit(jobs, dict(diagnostic, ok=False, error='Release lateness limit exceeded', t_s=time.monotonic()))
                                raise RuntimeError('Release lateness limit exceeded: '+json.dumps(diagnostic))
                            release += period
                    except Exception as exc:
                        errors.append(str(exc))
                        emit(jobs, {'task': t['name'], 'window_id': window['id'], 'ok': False, 'error': str(exc), 't_s': time.monotonic()})
                        stop.set()
                running = [threading.Thread(target=periodic, args=(t,)) for t in needed]
                for task_thread in running:
                    task_thread.start()
                try:
                    while any(x.is_alive() for x in running):
                        for task_thread in running:
                            task_thread.join(timeout=0.1)
                finally:
                    stop_on_error = bool(errors) or sys.exc_info()[0] is not None
                    if stop_on_error:
                        stop.set()
                    for task_thread in running:
                        task_thread.join()
                if errors:
                    raise RuntimeError('; '.join(errors))
                # Last job can finish before the requested steady window ends.
                # Keep the operating point through its endpoint and one telemetry bracket.
                stop.wait(max(0, window['end_s']-time.monotonic()) + c['telemetry']['period_s'])
                if stop.is_set():
                    raise RuntimeError('Window interrupted: '+str(errors))
            window['capture_complete'] = True
            save(out / 'windows.json', windows)
        # A final telemetry point brackets the last measurement endpoint.
        stop.wait(c['telemetry']['period_s'] * 2)
        if errors:
            raise RuntimeError('; '.join(errors))
    finally:
        stop.set()
        for sig in old_handlers:
            signal.signal(sig, signal.SIG_IGN)
        cleanup_errors = []
        for w in workers.values():
            try:
                w.close()
            except Exception as exc:
                cleanup_errors.append(str(exc))
        if thread:
            thread.join()
        if temperature:
            try:
                temperature.close()
            except Exception as exc:
                cleanup_errors.append('Temperature reader cleanup: '+str(exc))
        try:
            clock.restore()
        except Exception as exc:
            cleanup_errors.append('CLOCK RESTORE FAILED: ' + str(exc))
        libc = ctypes.CDLL(None, use_errno=True)
        libc.sem_unlink(sem_name.encode())
        save(out / 'cleanup.json', {'errors': cleanup_errors, 'clock_bounds_restored': not any('CLOCK' in x for x in cleanup_errors)})
        jobs.close()
        telem.close()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        if cleanup_errors:
            raise RuntimeError('; '.join(cleanup_errors))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('mode', choices=['preflight', 'profile', 'alpha', 'validate', 'analyze', 'reset'])
    parser.add_argument('--config', default=str(HERE / 'config.json'))
    parser.add_argument('--target-thor', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--allow-missing-temperature', action='store_true', help='Explicitly permit capture with unavailable GPU temperature; thermal assessment remains unavailable')
    parser.add_argument('--run', type=Path, help='Recorded run for analyze/reset')
    args = parser.parse_args()
    c = load_config(args.config)
    if args.allow_missing_temperature:
        c['telemetry']['allow_missing_temperature'] = True
    if args.dry_run:
        # Deliberately return before target checks, /proc, sysfs, mkdir, or subprocess.
        print(json.dumps({'dry_run': True, 'mode': args.mode, 'config': c,
                          'planned_build': 'python3 system_identification_2/build_workers.py',
                          'frequency_selection': 'target-only: supported interior point nearest range midpoint; 3-5 supported levels when available',
                          'worker_protocol': 'persistent READY; run <monotonic release>; completed JSON; quit',
                          'hardware_operations': ['snapshot bounds', 'lock min=max per window', 'restore original bounds'],
                          'controller': 'never launched', 'writes_or_launches_performed': False}, indent=2))
        return
    if args.mode == 'analyze':
        if args.run is None:
            parser.error('--run required')
        from analysis import analyze
        report = analyze(args.run)
        print(json.dumps({'output_directory': report['output_directory'], 'capture_status': report['status'], 'alpha_fit': report['alpha']['fit'], 'B_resolved': report['model']['resolved']}, indent=2))
        return
    model = target_guard(args.target_thor)
    # One suite per machine. Lock lives under suite, never modify another run.
    with open(HERE / '.target.lock', 'w') as target_lock:
        fcntl.flock(target_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        conflicts(c)
        if args.mode == 'reset':
            if args.run is None:
                parser.error('--run required')
            Clock(json.loads((args.run / 'preflight.json').read_text())).restore()
            print('Restored saved min/max bounds; no processes signaled')
            return
        build = None
        if args.mode != 'preflight':
            default_tasks = [t for t in c['tasks'] if t['command'][0].startswith('system_identification_2/bin/')]
            if default_tasks:
                build = json.loads((HERE / 'build_manifest.json').read_text())
                for t in default_tasks:
                    entry = build['tasks'][t['name']]
                    binary = ROOT / t['command'][0]
                    if entry['workload_parameters'] != t.get('workload_parameters', {}) or entry['binary_sha256'] != hashlib.sha256(binary.read_bytes()).hexdigest():
                        raise RuntimeError('Worker build/config mismatch: rebuild workers using the capture config')
        info = inspect_target(c)
        if args.mode == 'preflight':
            print(json.dumps(dict(device_model=model, **info), indent=2))
            return
        require_capture_temperature(c, info)
        root = Path(c['output_root'])
        if not root.is_absolute():
            root = ROOT / root
        if not root.resolve().is_relative_to(HERE):
            raise ValueError('output_root must stay under system_identification_2')
        root.mkdir(parents=True, exist_ok=True)
        out = root / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + args.mode + '_' + uuid.uuid4().hex[:8])
        out.mkdir()
        print(out, flush=True)
        save(out / 'config.json', c)
        if build:
            save(out / 'build_manifest.json', build)
        save(out / 'preflight.json', info)
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
        hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [*HERE.glob('*.py'), HERE / 'config.json', *ROOT.glob('application/*.cu'), ROOT / 'Scheduler/shared_header.hpp', ROOT / 'scripts/get_power.sh', *HERE.glob('bin/*')] if p.is_file()}
        save(out / 'provenance.json', {'device_model': model, 'started_UTC': dt.datetime.now(dt.timezone.utc).isoformat(), 'monotonic_s': time.monotonic(), 'revision': revision.stdout.strip() if revision.returncode == 0 else None, 'sha256': hashes, 'argv': sys.argv, 'python': sys.version, 'timing': 'CLOCK_MONOTONIC seconds; CUDA events converted ms to s'})
        save(out / 'status.json', {'complete': False, 'mode': args.mode, 'reason': 'capture in progress'})
        try:
            capture(c, info, args.mode, out)
        except BaseException as exc:
            save(out / 'status.json', {'complete': False, 'mode': args.mode, 'reason': str(exc) or type(exc).__name__})
            raise
        else:
            save(out / 'status.json', {'complete': True, 'mode': args.mode, 'note': 'Capture completed; analysis may reject measurement quality. B remains unresolved.'})


if __name__ == '__main__':
    main()

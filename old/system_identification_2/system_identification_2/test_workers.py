#!/usr/bin/env python3
"""Hardware-independent checks for the worker source transformation."""
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_workers


class WorkerTransformTests(unittest.TestCase):
    def test_all_sources_preserve_workload_anchors(self):
        for name in build_workers.SOURCES:
            text = build_workers.transform(name)
            self.assertIn("int jobs = 2;", text)
            self.assertIn("float service::kernellaunch", text)
            self.assertIn('std::cout << "{\\"ready\\":true}"', text)
            self.assertNotIn("cudaEventQuery(stopEv)", text)
            self.assertNotIn("std::future<float> asyncJob;", text)
            self.assertNotIn("shmget(", text)
            self.assertNotIn("kill(pids", text)
            self.assertNotIn("create_directories(", text)

    def test_configurable_sizes_only_change_generated_constants(self):
        original = build_workers.SOURCES['mm'].read_bytes()
        text = build_workers.transform('mm', {'matrix_n': 1000})
        self.assertIn('static int N = 1000;', text)
        self.assertEqual(build_workers.SOURCES['mm'].read_bytes(), original)
        with self.assertRaises(ValueError):
            build_workers.transform('mm', {'matrix_n': -1})
        with self.assertRaises(ValueError):
            build_workers.transform('stereo', {'min_disparity': 4, 'max_disparity': 0})

    def test_source_setup_and_kernel_launch_are_preserved(self):
        for name, path in build_workers.SOURCES.items():
            original = path.read_text()
            generated = build_workers.transform(name)
            start = original.index('void service::runService()')
            setup = original[original.index('print_cuda_versions_or_exit();', start):original.index('gotSIGHUP = 0;', start)]
            self.assertIn(setup, generated)
            self.assertNotIn('append_locked(', generated)
            self.assertIn('#include <vector>', generated)
            self.assertNotIn('static void\n    if', generated)
            # Exact source launch expression and per-invocation count survive.
            for line in original.splitlines():
                if '<<<' in line:
                    self.assertIn(line, generated)

    def test_dry_run_does_not_generate_or_compile(self):
        generated = HERE / "generated"
        before = {p: p.stat().st_mtime_ns for p in generated.glob("*_worker.cu")} if generated.exists() else {}
        result = subprocess.run([sys.executable, str(HERE / "build_workers.py"), "--dry-run"], capture_output=True, text=True, check=True)
        self.assertIn("nvcc", result.stdout)
        after = {p: p.stat().st_mtime_ns for p in generated.glob("*_worker.cu")} if generated.exists() else {}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

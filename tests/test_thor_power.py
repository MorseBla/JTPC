"""Read-only Thor power tests; fake sysfs data never touches device controls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('JTPC_TEST_ROOT', str(ROOT)))

class ThorPowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.build.name) / 'controller_power_test'
        harness = Path(cls.build.name) / 'test.cc'
        harness.write_text('#define main jtpc_controller_main\n#include ' + json.dumps(str(ROOT/'Scheduler/controller.cc')) + '\n#undef main\n' + r'''
int main(int argc, char** argv) {
    g_power_backend = "thor";
    try {
        if (argc > 1 && std::string(argv[1]) == "window") {
            innerloopduration = 0.15f;
            std::thread sampling(monitorpower);
            std::this_thread::sleep_for(std::chrono::milliseconds(250));
            monitorthread = false;
            sampling.join();
            if (finalpowervalues.empty()) return 3;
            for (float value : finalpowervalues) {
                if (std::abs(value - (argc > 2 ? std::atof(argv[2]) : 125000.0)) > 0.01f) return 4;
            }
            return 0;
        }
        if (argc > 1 && std::string(argv[1]) == "cache") {
            if (returnpowerrtx() != 125000) return 5;
            std::ofstream(std::string(std::getenv("THOR_HWMON_ROOT")) + "/hwmon37/power1_input") << "126000000\n";
            if (returnpowerrtx() != 125000) return 6;
            std::this_thread::sleep_for(std::chrono::milliseconds(110));
            return returnpowerrtx() == 126000 ? 0 : 7;
        }
        std::cout << returnpowerrtx() << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << "\n";
        return 2;
    }
}
''')
        common=ROOT/'Common/jetson'
        sources=[common/name for name in ['jetson_power_monitor.cpp','ina260_reader.cpp','jtop_reader.cpp','tegrastats_monitor.cpp','time_utils.cpp']]
        subprocess.run(['g++','-std=c++17','-DJetson','-pthread','-I'+str(ROOT/'Common'),'-I'+os.environ.get('EIGEN_INCLUDE','/usr/include/eigen3'),str(harness),*map(str,sources),'-o',str(cls.binary)],check=True,capture_output=True,text=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.hwmon=self.base/'hwmon';self.hwmon.mkdir()
        self.work=self.base/'experiment';self.work.mkdir()
        (self.base/'scripts').symlink_to(ROOT/'scripts',target_is_directory=True)
        self.fakebin=self.base/'bin';self.fakebin.mkdir()
        # These prevent fallback paths in the old implementation from touching hardware.
        for name,body in {'sudo':'exec "$@"','tegrastats':"printf 'VDD_IN 9999mW/9999mW VDD_CPU_GPU_CV 4567mW/4567mW\\n'"}.items():
            p=self.fakebin/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
        self.env=dict(os.environ,THOR_HWMON_ROOT=str(self.hwmon),PATH=str(self.fakebin)+':'+os.environ['PATH'])
        self.env.pop('GPU_SHELL_EQUIV_POWER_MW',None)

    def sensor(self,name='hwmon37',chip='ina238',label='VIN',raw='125000999'):
        p=self.hwmon/name;p.mkdir()
        for f,value in [('name',chip),('label',label),('power1_input',raw)]: (p/f).write_text(value+'\n')
        return p

    def run_script(self,*args):
        return subprocess.run(['bash',str(ROOT/'scripts/get_power.sh'),*args],env=self.env,cwd=self.work,capture_output=True,text=True,timeout=5)

    def test_thor_units_and_hwmon_renumbering(self):
        self.sensor();r=self.run_script('thor');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'125000\n')

    def test_missing_sensor_has_no_numeric_fallback(self):
        r=self.run_script('thor');self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,'')

    def test_wrong_sensor_or_rail_is_rejected(self):
        self.sensor(chip='ina3221');r=self.run_script('thor');self.assertNotEqual(r.returncode,0)
        (self.hwmon/'hwmon37/name').write_text('ina238\n');(self.hwmon/'hwmon37/label').write_text('VDD_GPU\n')
        self.assertNotEqual(self.run_script('thor').returncode,0)

    def test_duplicate_sensors_are_rejected(self):
        self.sensor();self.sensor(name='hwmon99');self.assertNotEqual(self.run_script('thor').returncode,0)

    def test_malformed_or_missing_power_is_rejected(self):
        p=self.sensor(raw='bad')
        for raw in ['bad','-1000','0','123abc','1\n2000']:
            (p/'power1_input').write_text(raw+'\n');r=self.run_script('thor');self.assertNotEqual(r.returncode,0,raw);self.assertEqual(r.stdout,'')
        (p/'power1_input').unlink();self.assertNotEqual(self.run_script('thor').returncode,0)

    def test_legacy_script_output_is_preserved(self):
        r=self.run_script();self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'4567\n')

    def test_legacy_streaming_tegrastats_keeps_first_sample(self):
        (self.fakebin/'tegrastats').write_text("#!/usr/bin/env python3\nimport os\nwhile True: os.write(1, b'VDD_CPU_GPU_CV 4567mW/4567mW\\n' * 1000)\n")
        r=self.run_script();self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'4567\n')

    def test_unknown_mode_fails(self):
        self.assertNotEqual(self.run_script('bad').returncode,0)

    def test_controller_reads_script_in_mw(self):
        self.sensor();r=subprocess.run([str(self.binary)],env=self.env,cwd=self.work,capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'125000')

    def test_controller_rejects_sensor_failure(self):
        r=subprocess.run([str(self.binary)],env=self.env,cwd=self.work,capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,'')

    def test_sampling_accepts_above_20w_without_offset(self):
        self.sensor();self.env['GPU_SHELL_EQUIV_POWER_MW']='999'
        r=subprocess.run([str(self.binary),'window'],env=self.env,cwd=self.work,capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)

    def test_sampling_below_20w_has_no_synthetic_offset(self):
        self.sensor(raw='16500000');self.env['GPU_SHELL_EQUIV_POWER_MW']='999'
        r=subprocess.run([str(self.binary),'window','16500'],env=self.env,cwd=self.work,capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)

    def test_controller_shares_a_10hz_cached_read(self):
        self.sensor()
        r=subprocess.run([str(self.binary),'cache'],env=self.env,cwd=self.work,capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)

if __name__=='__main__':unittest.main()

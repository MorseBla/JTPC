"""Hardware-independent periodic schedule tests."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from periodic_validation import plan, plot
from suite import make_sequence


class PeriodicTests(unittest.TestCase):
    def source(self,root):
        config=json.loads((Path(__file__).resolve().parent/'config.json').read_text())
        config['tasks'][0]['workload_parameters']['num_elements']=4096000
        (root/'config.json').write_text(json.dumps(config))
        (root/'preflight.json').write_text(json.dumps(dict(reference_hz=300,intended_frequencies_hz=[100,200,300,400,500,600])))
        return config

    def test_cycles_quantization_fixed_rates_and_preserved_sizes(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);original=self.source(root);output=root/'periodic.json'
            c=plan(root,output,cycles=2,level_count=3,hold_intervals=4)
            levels=c['periodic_validation']['selected_levels_hz']
            self.assertEqual(levels,[100,300,600])
            seq=[r['frequency_hz'] for r in c['validation']['sequence']]
            self.assertEqual(seq,[300,300]+[100,300,600,300]*2)
            self.assertEqual(c['validation']['measure_s'],8)
            self.assertEqual(c['periodic_validation']['warmup_windows'],1)
            self.assertEqual(c['tasks'],original['tasks'])
            self.assertEqual(json.loads((root/'config.json').read_text()),original)
            self.assertTrue(all(w['rates_hz']==c['validation']['sequence'][0]['rates_hz'] for w in c['validation']['sequence']))
            info=dict(reference_hz=300,sweep_hz=levels,intended_frequencies_hz=[100,200,300,400,500,600])
            self.assertEqual(len(make_sequence(c,info,'validate')),10)
            with self.assertRaises(FileExistsError):plan(root,output)

    def test_dry_run_and_insufficient_frequencies(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);self.source(root);output=root/'not_written.json'
            plan(root,output,dry_run=True)
            self.assertFalse(output.exists())
            with self.assertRaises(ValueError):plan(root,output,low_hz=600)
            with self.assertRaises(ValueError):plan(root,output,hold_intervals=1)

    def test_long_config_changes_holds_only(self):
        here=Path(__file__).resolve().parent
        short=json.loads((here/'config.periodic.json').read_text())
        long=json.loads((here/'config.periodic.long.json').read_text())
        self.assertEqual(short['tasks'],long['tasks'])
        self.assertEqual(long['interval_s'],2)
        self.assertEqual(short['validation']['sequence'],long['validation']['sequence'])
        self.assertEqual(long['validation']['measure_s'],60)
        self.assertEqual(len(long['validation']['sequence'])*60,1920)

    def test_plot_uses_previous_model_even_if_new_baseline_differs(self):
        here=Path(__file__).resolve().parent
        model_path=here/'identification_model.json'
        artifact=json.loads(model_path.read_text())
        c=artifact['training_config']
        c['periodic_validation']={'warmup_windows':0}
        original=model_path.read_bytes()
        with tempfile.TemporaryDirectory(prefix='jtpc_SYNTHETIC_frozen_') as tmp, contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp);run=root/'run';run.mkdir()
            for filename,value in [('config.json',c),('status.json',{'complete':True}),
                ('windows.json',[dict(id='n',kind='validation',settle_start_s=0,start_s=0,end_s=2,rates_hz={t['name']:t['rate_hz'] for t in c['tasks']})])]:
                (run/filename).write_text(json.dumps(value))
            (run/'jobs.jsonl').write_text('')
            (run/'telemetry.jsonl').write_text(json.dumps(dict(t_s=1,frequency_hz=846e6)))
            summary={'windows':[dict(window_id='n',adequate=True,power={'mean':999})], 'intervals':[]}
            with patch('periodic_validation._validation_summary',return_value=summary), \
                 patch('periodic_validation.render_validation',return_value=[]) as renderer:
                out=plot(run,model_path,root/'out')
            passed=renderer.call_args.args[5]
            self.assertEqual(passed,artifact['matrix'])
            self.assertNotEqual(passed['nominal_power_W'],999)
            self.assertEqual(json.loads((out/'matrices.json').read_text()),artifact['matrix'])
            self.assertFalse(json.loads((out/'summary.json').read_text())['model_recalibrated'])
            self.assertEqual(model_path.read_bytes(),original)
            with patch('periodic_validation._validation_summary',return_value=summary), \
                 patch('periodic_validation.interval_summaries',return_value=[]) as binner, \
                 patch('periodic_validation.render_validation',return_value=[]) as renderer:
                averaged=plot(run,model_path,root/'averaged',plot_bin_seconds=10)
            self.assertEqual(binner.call_args.args[3]['interval_s'],10)
            self.assertEqual(renderer.call_args.args[0]['interval_s'],2)
            self.assertEqual(renderer.call_args.args[4]['plot_interval_s'],10)
            self.assertEqual(renderer.call_args.args[5],artifact['matrix'])
            self.assertEqual(json.loads((averaged/'summary.json').read_text())['native_interval_seconds'],2)
            self.assertEqual(model_path.read_bytes(),original)


if __name__=='__main__':unittest.main()

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_figures import partial_prediction, render_validation, _interval_rows, _window_rows, connected_points


class ValidationFigureTests(unittest.TestCase):
    def fixture(self):
        windows = [
            dict(id="n", kind="validation", start_s=1000, settle_start_s=999, end_s=1002, rates_hz=dict(hist=1, stereo=2, mm=3), requested_frequency_hz=800e6),
            dict(id="f", kind="validation", start_s=1003, end_s=1005, rates_hz=dict(hist=1, stereo=2, mm=3), requested_frequency_hz=900e6),
            dict(id="r", kind="validation", start_s=1006, end_s=1008, rates_hz=dict(hist=1, stereo=2.1, mm=3), requested_frequency_hz=800e6),
        ]
        rows = []
        for w in windows:
            rows.append(dict(window_id=w["id"], power=dict(mean=10), frequency=dict(mean=w["requested_frequency_hz"]),
                             tasks={t: dict(response_s=dict(mean=(i+1)*.001)) for i, t in enumerate(("hist", "stereo", "mm"))}))
        summary = dict(windows=rows, nominal_window_id="n", alpha_W_per_MHz=.01,
                       intervals=[dict(start_s=1000, achieved_frequency=dict(mean=800e6), power=dict(mean=10),
                                       outputs={t: dict(response_s=dict(mean=.001)) for t in ("hist", "stereo", "mm")})])
        return windows, summary

    def test_partial_masks_rate_step_and_holds_frequency(self):
        pred = partial_prediction([[0, None, None, 1], [None, 0, None, 2], [None, None, 0, 3], [None, None, None, .01]],
                                   [1, 2, 3], 10, .01, 800, 800,
                                   dict(hist=1, stereo=2.1, mm=3), dict(hist=1, stereo=2, mm=3))
        self.assertEqual(pred["q_ms"], [None, 2, None])
        self.assertAlmostEqual(pred["power_W"], 10)
        held = partial_prediction([[None, 1]], [1], 10, .01, 800, 800, dict(hist=1), dict(hist=1), ("hist",))
        self.assertEqual(held["q_ms"], [1])

    def test_absolute_time_frequency_units_and_invalid_bins(self):
        summary = {'intervals': [
            dict(start_s=1002., window_id='f', straddles_transition=False,
                 achieved_frequency={'mean':900e6, 'valid':True}, power={'mean':11., 'valid':True},
                 outputs={'hist': {'response_s': {'mean':.002}}}),
            dict(start_s=1004., window_id=None, straddles_transition=True,
                 achieved_frequency={'mean':850e6, 'valid':True}, power={'mean':10., 'valid':True}, outputs={})]}
        nominal = dict(q_ms=[1.], power_W=10., alpha=.01, f0_mhz=800., rates_hz={'hist':1.})
        rows = _interval_rows(summary, ('hist',), [[0.,.01],[0.,.01]], nominal, 1000., {'f':{'rates_hz':{'hist':1.}}})
        self.assertEqual(rows[0]['elapsed_s'], 2.)
        self.assertEqual(rows[0]['frequency_mhz'], 900.)
        self.assertEqual(rows[0]['q_ms'], [2.])
        self.assertEqual(rows[0]['predicted_q_ms'], [2.])
        self.assertTrue(rows[1]['invalid'])
        self.assertIsNone(rows[1]['q_ms'][0])

    def test_held_nonzero_step_is_not_added_again(self):
        kwargs = dict(matrix=[[0.,.01],[0.,.01]], nominal_q_ms=[1.], nominal_power_w=10.,
                      alpha_w_per_mhz=.01, frequency_mhz=900., f0_mhz=800.,
                      rates={'hist':1.}, nominal_rates={'hist':1.}, task_order=('hist',))
        self.assertEqual(partial_prediction(**kwargs)['q_ms'], [2.])
        self.assertEqual(partial_prediction(**kwargs)['q_ms'], [2.])
        kwargs['matrix'] = [[0.,None],[0.,.01]]
        self.assertIsNone(partial_prediction(**kwargs)['q_ms'][0])

    def test_settled_predictions_keep_frozen_offsets(self):
        windows, summary=self.fixture()
        summary['windows'][0]['requested_rates_hz']=windows[0]['rates_hz']
        frozen=dict(nominal_q_ms=[10.,20.,30.],nominal_power_W=40.,f0_MHz=800.,alpha_W_per_MHz=.01)
        B=[[0.,None,None,-.01],[None,0.,None,-.02],[None,None,0.,-.03],[0.,0.,0.,.01]]
        before=_window_rows(windows,summary,B,('hist','stereo','mm'),frozen)
        summary['windows'][0]['power']['mean']=999.
        for task in summary['windows'][0]['tasks'].values():
            task['response_s']['mean']=99.
        after=_window_rows(windows,summary,B,('hist','stereo','mm'),frozen)
        self.assertEqual(before[1]['predicted_q_ms'], after[1]['predicted_q_ms'])
        self.assertEqual(after[1]['predicted_q_ms'], [9.,18.,27.])
        self.assertEqual(after[1]['predicted_power_w'], 41.)

    def test_connects_transition_vertices_but_keeps_real_missing_values(self):
        x=[0,1,2,3,4,5]
        y=[10,None,20,None,None,30]
        before=list(y)
        px,py=connected_points(x,y,{1,4})
        self.assertEqual(px,[0,2,3,5])
        self.assertEqual(py,[10,20,None,30])
        self.assertEqual(y,before)  # only display vertices change

    def test_render_missing_interval_and_outputs(self):
        windows, summary = self.fixture()
        with tempfile.TemporaryDirectory(prefix="jtpc_validation_figures_") as td:
            names = render_validation(dict(validation_tasks=["hist", "stereo", "mm"]), windows, [], [], summary,
                                       dict(B_partial=[[0, None, None, .01], [None, 0, None, .02],
                                                       [None, None, 0, .03], [None, None, None, .01]],
                                            f0_MHz=800, alpha_W_per_MHz=.01), Path(td))
            self.assertEqual(len(names), 16)
            self.assertTrue(all((Path(td)/name).is_file() for name in names))
            self.assertGreater((Path(td)/"validation_measured_vs_partial.png").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()

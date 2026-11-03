"""Matrix units/order checks; no hardware or fabricated target coefficients."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_validation import make_matrices, matrix_text


class MatrixExportTests(unittest.TestCase):
    def test_partial_matrix_and_implied_observation_units(self):
        config = dict(tasks=[{'name':'second'}, {'name':'first'}], assumed_context_switch_s=.00075)
        nominal = dict(adequate=True, frequency={'mean':800e6}, power={'mean':20},
                       tasks={'second': {'response_s': {'mean': .02}}, 'first': {'response_s': {'mean': .01}}})
        alpha = {'fit': {'valid':True, 'slope_W_per_MHz':.003}}
        profiles = {'second': {'mean_ms':19}, 'first': {'mean_ms':9}}
        matrix = make_matrices(config, {'windows':[nominal]}, alpha, profiles, 800e6)
        self.assertEqual(matrix['state_order'], ['q_second','q_first','P_VIN'])
        self.assertEqual(matrix['B_partial'], [[0.,None,-.025], [None,0.,-.0125], [0.,0.,.003]])
        self.assertIsNone(matrix['B_full'])
        self.assertEqual(matrix['C'], [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        self.assertFalse(matrix['C_is_identified'])
        self.assertIn('?', matrix_text(matrix))
        self.assertEqual(matrix['column_units'], ['Hz','Hz','MHz'])
        nominal['frequency']['mean']=700e6
        with self.assertRaises(ValueError):
            make_matrices(config, {'windows':[nominal]}, alpha, profiles,800e6)


if __name__ == '__main__':
    unittest.main()

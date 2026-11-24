"""Build G (rulings 49 and 51): fixes to analysis3.

G3  a scored analysis refuses another resample count or seed, and a manifest whose pilot flag is not the mode's, before it
    writes the run record; the record names the count and the seed
G4  the kept-late repeats of the primary intervals are real bounds, one pair of fills for each contrast

The gate's real pilot fixture is used where the gate runs; hand-made snapshots elsewhere. No model, simulator or network.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import analysis3 as A
from protocol import contract3 as C
from protocol import test_gate_e1_3 as E
from protocol import test_protocol3 as T
from protocol import test_analysis_e2_3 as E2


def setUpModule():
    T.setUpModule()


def tearDownModule():
    T.tearDownModule()



def nine(result):
    return {**result['secondary_intervals'], **result['primary']}


class ScoredSettings(unittest.TestCase):
    """G3."""

    def root(self):
        root, gate = E.fresh(self)
        return root, gate

    def passing_gate(self):
        """The gate and the analysis stand-in pass, so that only the settings check can refuse."""
        stack = unittest.mock.patch('protocol.validate3.load_run', return_value=({'ok': True}, {'input_sha256': {}}))
        return stack

    def test_a_resample_count_that_is_not_the_protocols_is_refused_and_leaves_no_record(self):
        root, gate = self.root()
        for n in (50, C.BOOT_N - 1, C.BOOT_N + 1, 0, True, None, float(C.BOOT_N)):
            with self.subTest(n=n), self.passing_gate(), mock.patch.object(A, 'analyse_snapshot', return_value={}), \
                    self.assertRaises(ValueError):
                A.analyse(root, n_boot=n, out=root.parent / 'out')
            self.assertFalse((root / A.RUN_RECORD).exists())

    def test_a_seed_that_is_not_the_protocols_is_refused_and_leaves_no_record(self):
        root, gate = self.root()
        for seed in (1, C.BOOT_SEED + 1, None, True):
            with self.subTest(seed=seed), self.passing_gate(), mock.patch.object(A, 'analyse_snapshot', return_value={}), \
                    self.assertRaises(ValueError):
                A.analyse(root, boot_seed=seed, out=root.parent / 'out')
            self.assertFalse((root / A.RUN_RECORD).exists())

    def test_a_manifest_whose_pilot_flag_is_not_the_modes_is_refused_and_leaves_no_record(self):
        root, gate = self.root()
        # a pilot run asked for as a scored run: the gate refuses before the record
        with self.assertRaises(ValueError):
            A.analyse(root, pilot=False, out=root.parent / 'out', seed_path=gate['seed_path'], protocol_path=gate['protocol_path'])
        self.assertFalse((root / A.RUN_RECORD).exists())
        # a run whose manifests say it is not a pilot, asked for as a pilot
        for manifest in root.glob('*/manifest.json'):
            m = json.loads(manifest.read_text())
            m['pilot'] = False
            T.write_json(manifest, m)
        with self.assertRaisesRegex(ValueError, 'cohort'):
            A.analyse(root, n_boot=30, **gate)

    def test_the_record_names_the_count_and_the_seed(self):
        root, gate = self.root()
        out = root.parent / 'out'
        with mock.patch('protocol.validate3.load_run', return_value=({'ok': True}, {'input_sha256': {}})), \
                mock.patch.object(A, 'analyse_snapshot', return_value={}) as snap:
            A.analyse(root, out=out)
        record = json.loads((root / A.RUN_RECORD).read_text())
        self.assertEqual((record['resamples'], record['seed']), (C.BOOT_N, C.BOOT_SEED))
        self.assertEqual(snap.call_args.kwargs, {'n_boot': C.BOOT_N, 'boot_seed': C.BOOT_SEED})
        self.assertEqual(set(record), {'time', 'analysis_sources_sha256', 'output_folder', 'resamples', 'seed'})

    def test_a_pilot_is_not_limited_and_writes_no_record(self):
        root, gate = self.root()
        result = A.analyse(root, n_boot=30, boot_seed=5, **gate)
        self.assertEqual(result['bootstrap'], {**result['bootstrap'], 'seed': 5, 'replicates': 30})
        self.assertFalse((root / A.RUN_RECORD).exists())

    def test_the_command_line_still_works(self):
        from protocol import validate3
        root, gate = self.root()
        out = root.parent / 'cli-out'
        real = validate3.load_run
        # the command line passes no seed book or protocol, so the fixture's own are given to the gate here
        with mock.patch.object(sys, 'argv', ['analysis3.py', str(root), '--out', str(out), '--pilot']), \
                mock.patch.object(A, 'analyse', wraps=A.analyse) as wrapped, \
                mock.patch('protocol.validate3.load_run', lambda r, **kw: real(r, **{**kw, **gate})):
            A.main()
        self.assertEqual(wrapped.call_args.kwargs, {'pilot': True, 'out': out})
        self.assertTrue((out / 'analysis.json').exists() and (out / 'report.md').exists())


class KeptLateBounds(unittest.TestCase):
    """G4."""
    ADOPT = staticmethod(lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'})
    CLOSE = [0, 1]          # the close scenarios are the first two of six (two for each band)

    def probe(self, **kw):
        return E2.make(blocks=3, adopt=self.ADOPT, **kw)

    def source(self, snap, cid, block):
        return snap['learning']['reach'][block]['candidates'][cid]['source_sha256']

    def test_with_no_kept_late_flight_both_fills_equal_the_primary_intervals_for_all_nine(self):
        result = E2.run(self.probe())
        k = result['kept_late_evaluation']
        every = nine(result)
        self.assertEqual(len(every), 9)
        for label in ('primary_under_lower_fill', 'primary_under_upper_fill'):
            self.assertEqual(list(k[label]), list(every))
            for key, row in every.items():
                self.assertEqual((k[label][key]['estimate'], k[label][key]['ci95'], k[label][key]['classification']),
                                 (row['estimate'], row['ci95'], row['classification']), key)
        for old in ('primary_with_kept_late_as_0', 'primary_with_kept_late_as_1'):
            self.assertNotIn(old, k)       # nothing is left that suggests an all-0 or all-1 repeat bounds anything

    def two_sided(self):
        """A flies c0's source and D flies c1's. A's cell 0 and D's cell 1 are kept late, in every block of reach. A's cells
        are all failures and D's all successes."""
        cells = lambda task, block, name: [0] * 6 if name == 'c0' else [1] * 6
        probe = self.probe(cells=cells)
        late = {('threat3', 'reach', b, self.source(probe, 'c0', b)): [C.evaluation_cases(probe['seeds'], 'reach', True)[0].episode_id] for b in range(3)}
        late.update({('threat3', 'reach', b, self.source(probe, 'c1', b)): [C.evaluation_cases(probe['seeds'], 'reach', True)[1].episode_id] for b in range(3)})
        return self.probe(cells=cells, kept_late=late)

    def test_both_arms_with_kept_late_cells_the_old_pair_misses_the_extremes_and_the_new_fills_reach_them(self):
        snap = self.two_sided()
        result = E2.run(snap)
        k = result['kept_late_evaluation']
        y, cases = E2.rebuild_y(snap, 'reach')

        def d_minus_a(a_cell0, d_cell1):
            z = y.copy()
            z[0, :, 0], z[3, :, 1] = a_cell0, d_cell1
            return z[3][:, self.CLOSE].mean() - z[0][:, self.CLOSE].mean()
        # by hand: A's close cells are [x, 0] and D's are [1, y]
        self.assertAlmostEqual(d_minus_a(0, 1), 1.0)                        # as kept
        old_all_0, old_all_1 = d_minus_a(0, 0), d_minus_a(1, 1)             # the repeats that were replaced
        self.assertEqual((old_all_0, old_all_1), (0.5, 0.5))
        lower, upper = d_minus_a(1, 0), d_minus_a(0, 1)                     # A high and D low; A low and D high
        self.assertEqual((lower, upper), (0.0, 1.0))
        got_lower = k['primary_under_lower_fill']['reach:D-A:close']['estimate']
        got_upper = k['primary_under_upper_fill']['reach:D-A:close']['estimate']
        self.assertAlmostEqual(got_lower, lower, places=9)
        self.assertAlmostEqual(got_upper, upper, places=9)
        self.assertLess(got_lower, min(old_all_0, old_all_1))
        self.assertEqual(nine(result)['reach:D-A:close']['estimate'], upper)
        # the other tasks have nothing kept late, so the six D - A rows of those tasks do not move
        for key in ('reach3d:D-A:close', 'land:D-A:middle-wide'):
            self.assertEqual(k['primary_under_lower_fill'][key]['estimate'], nine(result)[key]['estimate'])

    def test_the_six_d_minus_a_rows_share_one_pair_and_each_pooled_step_has_its_own(self):
        k = E2.run(self.two_sided())['kept_late_evaluation']
        self.assertEqual(set(k['fills']), {'D-A', 'B-A', 'C-B', 'D-C'})
        self.assertEqual(A.contrast_group('reach3d:D-A:middle-wide'), 'D-A')
        self.assertEqual({A.contrast_group(key) for key in k['primary_under_lower_fill'] if key.startswith('pooled:')},
                         {'B-A', 'C-B', 'D-C'})
        # D - C pooled: D has cells kept late (c1) and C has cells kept late (c0): lower takes D's as 0 and C's as 1
        y, cases = E2.rebuild_y(self.two_sided(), 'reach')
        z = y.copy()
        z[3, :, 1], z[2, :, 0] = 0, 1
        reach_close_all = (z[3].mean() - z[2].mean())            # all bands weighted equally: every band has 2 scenarios
        other = [E2.rebuild_y(self.two_sided(), t) for t in ('reach3d', 'land')]
        want = np.mean([reach_close_all] + [yy[3].mean() - yy[2].mean() for yy, _ in other])
        self.assertAlmostEqual(k['primary_under_lower_fill']['pooled:D-C']['estimate'], want, places=9)

    def test_a_flight_both_arms_share_cancels_in_their_contrast(self):
        # A, B and C fly c0's source, so a kept-late flight there is one flight in all three arms
        cells = lambda task, block, name: [1, 0, 1, 0, 1, 0]
        probe = self.probe(cells=cells)
        ids = [c.episode_id for c in C.evaluation_cases(probe['seeds'], 'reach', True)][:2]
        late = {('threat3', 'reach', b, self.source(probe, 'c0', b)): ids for b in range(3)}
        result = E2.run(self.probe(cells=cells, kept_late=late))
        k = result['kept_late_evaluation']
        for key in ('pooled:B-A', 'pooled:C-B'):
            for label in ('primary_under_lower_fill', 'primary_under_upper_fill'):
                self.assertEqual(k[label][key]['estimate'], nine(result)[key]['estimate'], key)
                self.assertEqual(k[label][key]['ci95'], nine(result)[key]['ci95'], key)
        # D flies another source, so D - C and D - A do depend on the fill
        self.assertNotEqual(k['primary_under_lower_fill']['reach:D-A:close']['estimate'],
                            k['primary_under_upper_fill']['reach:D-A:close']['estimate'])

    def test_the_report_shows_both_fills_and_says_when_a_name_differs(self):
        text = '\n'.join(A.report_lines(E2.run(self.two_sided())))
        self.assertIn('| Contrast | Designation | As kept | Lower fill | Upper fill |', text)
        self.assertNotIn('Kept late as 0', text)
        self.assertIn('The name differs from the as-kept name under one or both fills for:', text)
        clean = '\n'.join(A.report_lines(E2.run(self.probe())))
        self.assertIn('No evaluation flight was kept late.', clean)


if __name__ == '__main__':
    unittest.main()

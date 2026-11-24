"""Build I1 (ruling 55, point 3): the descriptive counts analysis3 adds to analysis.json and report.md. A hand-made snapshot of the
shape validate3.load_run returns stands in for the gate's (the E2 fixture). No flight, model or network. Seeds 7100 and up."""
import json
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import analysis3 as A
from protocol import contract3 as C
from protocol import test_analysis_e2_3 as E
from protocol import test_split3 as S

def setUpModule():
    S.setUpModule()


def tearDownModule():
    S.tearDownModule()


# Each block, each arm's adopted candidate. Block 2 adopts nothing in any arm. In block 1 the E2 fixture gives f1 the source of
# c0, so arm A's f1 flies the cells named 'c0' there.
ADOPT = {0: {'A': None, 'B': 'c0', 'C': 'rC1', 'D': 'c1'},
         1: {'A': 'f1', 'B': None, 'C': 'c0', 'D': 'rD1'},
         2: {'A': None, 'B': None, 'C': None, 'D': None},
         3: {'A': 'c0', 'B': 'f1', 'C': 'rC2', 'D': 'c1'}}
# The six scenarios of a task are close, close, middle, middle, wide, wide.
CELLS = {(0, 'c0'): [1, 1, 0, 0, 0, 0], (0, 'c1'): [1, 1, 1, 0, 0, 0], (0, 'rC1'): [1, 0, 1, 1, 0, 0],
         (1, 'c0'): [0, 1, 1, 1, 1, 1], (1, 'rD1'): [1, 1, 1, 1, 0, 0],
         (3, 'c0'): [1, 1, 1, 1, 1, 1], (3, 'f1'): [0, 0, 0, 0, 0, 1], (3, 'rC2'): [1, 1, 0, 0, 1, 1], (3, 'c1'): [0, 1, 0, 1, 0, 1]}


def cells(task, block, name):
    row = CELLS.get((block, name), [0] * 6)
    if task == 'land':
        return row[::-1]           # close and wide change places
    if task == 'reach3d':
        return [1 - v for v in row]
    return row


def fixture():
    return E.make(blocks=4, per_band=2, adopt=lambda task, b: ADOPT[b], cells=cells)


def row(blocks, successes, possible, adopting, a_succ, a_possible, a_mean, close, middle, wide):
    return {'blocks': blocks, 'successes': successes, 'flights_possible': possible, 'adopting_blocks': adopting,
            'adopting_blocks_successes': a_succ, 'adopting_blocks_flights_possible': a_possible, 'adopting_blocks_mean': a_mean,
            'mean_by_band': {'close': close, 'middle': middle, 'wide': wide},
            'flights_possible_by_band': {'close': 8, 'middle': 8, 'wide': 8}}


def r12(x):
    return round(x, 12)


# By hand. Four blocks of six flights: 24 possible. Reach, arm A: block 1 adopted (cells 0,1,1,1,1,1: 5) and block 3 (6 of 6).
REACH = {'A': row(4, 11, 24, 2, 11, 12, r12(11 / 12), 3 / 8, 4 / 8, 4 / 8),
         'B': row(4, 3, 24, 2, 3, 12, 0.25, 2 / 8, 0.0, 1 / 8),
         'C': row(4, 12, 24, 3, 12, 18, r12(12 / 18), 4 / 8, 4 / 8, 4 / 8),
         'D': row(4, 10, 24, 3, 10, 18, r12(10 / 18), 5 / 8, 4 / 8, 1 / 8)}
# Land flies the same cells in the reverse order, so close and wide change places; every total stays.
LAND = {a: {**r, 'mean_by_band': {'close': r['mean_by_band']['wide'], 'middle': r['mean_by_band']['middle'], 'wide': r['mean_by_band']['close']}}
        for a, r in REACH.items()}
# Reach3d flies one minus each cell, in the blocks that adopted; a block that adopted nothing stays 0.
REACH3D = {'A': row(4, 1, 24, 2, 1, 12, r12(1 / 12), 1 / 8, 0.0, 0.0),
           'B': row(4, 9, 24, 2, 9, 12, 0.75, 2 / 8, 4 / 8, 3 / 8),
           'C': row(4, 6, 24, 3, 6, 18, r12(6 / 18), 2 / 8, 2 / 8, 2 / 8),
           'D': row(4, 8, 24, 3, 8, 18, r12(8 / 18), 1 / 8, 2 / 8, 5 / 8)}


def rounded(table):
    return {a: {k: ({b: r12(x) for b, x in v.items()} if k == 'mean_by_band' else v) for k, v in r.items()} for a, r in table.items()}


GOLD_A = '80cccb88ed3fafc89139d8e63a877398311de29d99ad75853cc8abb5a1295802'      # whole result before this build, by json sha256
# The two report hashes were re-pinned by build N (ruling 88): the report now has a primary and a secondary table and a designation
# column in the kept-late table. The result digests above did not change, so no interval's value moved.
GOLD_A_REPORT = '20b51a7d4c36fe882d602e40f274abaf5fd13a3e60f63f8a4381ef4b46ac88c2'
GOLD_B = '359b492c439f5a14a0125ba48f03f461886c9860da65740c44538b68f74aa121'
GOLD_B_REPORT = '3b1c6cce8628da5cb44ed17a8e7be23f974be05a02d94437c240b62c3648a077'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def old_report(result):
    """The report as it was before this build: the new section is taken out."""
    lines = A.report_lines(result)
    first = lines.index('## Descriptive counts (no interval)')
    last = lines.index('No scored conclusion may be drawn from a development/pilot analysis.')
    return '\n'.join(lines[:first - 1] + lines[last:])


def old_result(result):
    """The result as it was before build N: the nine intervals under 'primary' (build N, ruling 88, files the six D - A intervals
    under 'secondary_intervals' and adds a designation to the kept-late block; the values are the same)."""
    out = {k: v for k, v in result.items() if k not in ('descriptive_counts', 'secondary_intervals')}
    out['primary'] = {**result['secondary_intervals'], **result['primary']}
    out['kept_late_evaluation'] = {k: v for k, v in result['kept_late_evaluation'].items() if k != 'designation'}
    return out


class ByHand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = A.analyse_snapshot(fixture(), n_boot=60)

    def test_each_number_for_each_task_and_arm(self):
        by_task = self.result['descriptive_counts']['by_task']
        self.assertEqual(list(by_task), list(C.TASKS))
        for task, want in (('reach', REACH), ('reach3d', REACH3D), ('land', LAND)):
            for arm in C.ARMS:
                self.assertEqual(by_task[task][arm], rounded(want)[arm], (task, arm))

    def test_the_adopting_blocks_agree_with_the_adoption_field_and_the_totals_with_the_arm_means(self):
        for task in C.TASKS:
            for arm in C.ARMS:
                d = self.result['descriptive_counts']['by_task'][task][arm]
                self.assertEqual(d['adopting_blocks'], self.result['tasks'][task]['adoption'][arm]['adopted'])
                # the bands are the same size, so the arm's mean is its successes over the flights possible
                self.assertAlmostEqual(d['successes'] / d['flights_possible'], self.result['tasks'][task]['arm_means'][arm], places=9)
                self.assertAlmostEqual(sum(d['mean_by_band'].values()) / 3, self.result['tasks'][task]['arm_means'][arm], places=9)

    def test_a_block_that_adopted_nothing_counts_as_zero_in_all_but_the_adopting_fields(self):
        d = self.result['descriptive_counts']['by_task']['reach']['A']
        self.assertEqual((d['blocks'], d['adopting_blocks'], d['flights_possible'], d['adopting_blocks_flights_possible']), (4, 2, 24, 12))

    def test_no_arm_that_adopted_nothing_has_a_mean_among_adopting_blocks(self):
        snap = E.make(blocks=3, per_band=2, adopt=lambda t, b: {'A': None, 'B': None, 'C': None, 'D': 'c1'}, cells=lambda t, b, n: [1] * 6)
        d = A.analyse_snapshot(snap, n_boot=30)['descriptive_counts']['by_task']['reach']
        self.assertEqual(d['A']['adopting_blocks'], 0)
        self.assertIsNone(d['A']['adopting_blocks_mean'])
        self.assertEqual((d['A']['successes'], d['A']['adopting_blocks_successes']), (0, 0))
        self.assertEqual((d['D']['successes'], d['D']['adopting_blocks_mean']), (18, 1.0))
        self.assertIn('none', '\n'.join(A.descriptive_lines(A.analyse_snapshot(snap, n_boot=30))))

    def test_the_report_lists_the_fields_and_prints_each_count_with_no_interval(self):
        text = '\n'.join(A.report_lines(self.result))
        self.assertIn('## Descriptive counts (no interval)', text)
        for name in ('successes', 'flights_possible', 'adopting_blocks', 'adopting_blocks_successes', 'adopting_blocks_flights_possible',
                     'adopting_blocks_mean', 'mean_by_band', 'flights_possible_by_band'):
            self.assertIn(name, text)
        self.assertIn('| reach | A | 11 of 24 | 2 of 4 | 11 of 12 | 0.9167 | 0.3750 | 0.5000 | 0.5000 |', text)
        self.assertIn('| land | D | 10 of 24 | 3 of 4 | 10 of 18 | 0.5556 | 0.1250 | 0.5000 | 0.6250 |', text)
        section = text.split('## Descriptive counts (no interval)')[1].split('No scored conclusion')[0]
        self.assertNotIn('interval', section.replace('no interval', '').replace('Counts and means', '').replace('and no resampling', '')
                         .replace('with no ', ''))

    def test_the_numbers_do_not_depend_on_the_resamples(self):
        other = A.analyse_snapshot(fixture(), n_boot=90)
        self.assertEqual(json.dumps(other['descriptive_counts'], sort_keys=True), json.dumps(self.result['descriptive_counts'], sort_keys=True))

    def test_the_function_draws_nothing(self):
        y = np.ones((4, 2, 6))
        with mock.patch.object(np.random, 'default_rng', side_effect=AssertionError('drew')), \
                mock.patch.object(np.random, 'RandomState', side_effect=AssertionError('drew')):
            out = A.descriptive_counts(y, ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2, np.ones((4, 2), dtype=bool))
        self.assertEqual(out['A']['successes'], 12)


class ExistingFieldsUnchanged(unittest.TestCase):
    def test_every_other_field_and_the_report_around_the_new_section_are_byte_identical_to_before(self):
        for snap, n, gold, gold_report in ((E.make(blocks=6, seed=11, invalid_c0=(0,)), 200, GOLD_A, GOLD_A_REPORT),
                                           (E.make(blocks=4, seed=5), 200, GOLD_B, GOLD_B_REPORT)):
            result = A.analyse_snapshot(snap, n_boot=n)
            self.assertEqual(digest(old_result(result)), gold)
            self.assertEqual(hashlib.sha256(old_report(result).encode()).hexdigest(), gold_report)

    def test_the_nine_primary_intervals_are_those_of_the_e2_pins(self):
        got = E.estimates(E.run(E.make(blocks=6, seed=11, invalid_c0=(0,)), n_boot=200))
        for key, want in E.GOLD.items():
            self.assertEqual(got[key], want, key)


class SplitRun(S.Split):
    """Three roots of one task each and one root of three tasks give the same descriptive numbers. The inherited tests are not run
    again here."""

    def test_the_descriptive_numbers_are_the_same_from_one_root_and_from_three_roots(self):
        root, kw = self.whole()
        one = A.analyse(root, pilot=True, n_boot=40, **{k: v for k, v in kw.items() if k != 'pilot'})
        three = A.analyse(self.three, pilot=True, n_boot=40, **{k: v for k, v in self.kw.items() if k != 'pilot'})
        self.assertEqual(list(three['descriptive_counts']['by_task']), list(C.TASKS))
        self.assertEqual(json.dumps(three['descriptive_counts'], sort_keys=True), json.dumps(one['descriptive_counts'], sort_keys=True))
        self.assertGreater(three['descriptive_counts']['by_task']['reach']['A']['flights_possible'], 0)


for _name in [n for n in dir(S.Split) if n.startswith('test_')]:
    setattr(SplitRun, _name, None)


if __name__ == '__main__':
    unittest.main()

"""Tests of analysis3.py for build E2 (rulings 38 and 39). A hand-made snapshot of the shape validate3.load_run returns
stands in for the gate's; no flight, model or network is involved. Seeds used are 7100 and up, never the scoring seeds."""
import contextlib
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import analysis3 as A
from protocol import contract3 as C


BAND_SEEDS = {'close': 7100, 'middle': 7200, 'wide': 7300}
SEQUENCE = {'A': ['c0', 'f1', 'f2'], 'B': ['c0', 'f1', 'f2'], 'C': ['c0', 'rC1', 'rC2'], 'D': ['c1', 'rD1', 'rD2']}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def seeds_for(per_band=2):
    """Seeds 7100 and up. Never the scoring seeds 5000 to 5099."""
    return {'pilot': {
        'threat_evaluation': {t: {b: [BAND_SEEDS[b] + 100 * i + j for j in range(per_band)] for b in C.BANDS}
                              for i, t in enumerate(C.TASKS)},
        'heldout': {t: {'calm': [7500 + i], 'wind': [7600 + i]} for i, t in enumerate(C.TASKS)}}}


def steps(lags=(0.001, 0.002), own=(0.0, 0.0), n=None):
    return [{'t': i + 1, 'decision_lag_s': lags[i % len(lags)], 'observation_lag_s': own[i % len(own)],
             'command_lag_s': 0.3, 'north_m': 0.0, 'east_m': 0.0, 'alt_m': 10.0} for i in range(n or len(lags))]


def flight(ok, **extra):
    o = {'goal_met': bool(ok), 'end_reason': 'reached' if ok else 'timed_out', 'native_steps': steps(),
         'command_delay_s': 0.3, '_call_wall_s': {'procedure': [0.04, 0.05], 'guard': [0.04, 0.045]}}
    o.update(extra)
    return o


def make(blocks=6, seed=3, invalid_c0=(), adopt=None, cells=None, kept_late=None, extra=None, per_band=2, timing=None):
    """adopt(task, block) -> {arm: candidate id or None}; cells(task, block, source_name) -> list of 0/1 for the
    scenarios (default: random). Returns the snapshot."""
    rng = np.random.default_rng(seed)
    seeds = seeds_for(per_band)
    snap = {'seeds': seeds, 'pilot': True, 'learning': {t: {} for t in C.TASKS}, 'hazard': {}, 'retention': {},
            'input_sha256': {}, 'unique_flights': 0, 'requested_models': ['synthetic'],
            'kept_late_eval': kept_late or {}, 'evaluation_attempts': [], 'set_aside_learning': [],
            'gate': {'repeated_message_ids': 0, 'message_ids_seen': 0, 'rows_logged_as_copied': 0, 'copies_caught': 0,
                     'message_ids_in_file_with_no_row': 0,
                     'session_spend_stops': [], 'sessions_with_other_spend_stop': [], 'spend_stop_in_protocol_usd': 60.0}}
    for task in C.TASKS:
        ecases = C.evaluation_cases(seeds, task, True)
        rcases = C.retention_cases(seeds, task, True)
        for b in range(blocks):
            names = ['c0', 'c1', 'f1', 'f2', 'rC1', 'rC2', 'rD1', 'rD2']
            cands = {}
            for n in names:
                valid = not (n == 'c0' and b in invalid_c0)
                cands[n] = {'candidate_id': n, 'format_valid': valid,
                            'source_sha256': sha(f'{task}-{b}-{n}') if valid else None,
                            'call_ids': [f'{task}{b}{n}-1'] + ([f'{task}{b}{n}-2'] if n == 'f2' else []), 'parent': None}
            # a fresh candidate that copies c0's source, in block 1
            if b == 1:
                cands['f1']['source_sha256'] = cands['c0']['source_sha256']
            choice = adopt(task, b) if adopt else {a: [None, SEQUENCE[a][0], SEQUENCE[a][1]][int(rng.integers(3))] for a in C.ARMS}
            arms, usage = {}, []
            for arm in C.ARMS:
                want = choice[arm]
                seq = SEQUENCE[arm]
                if want is not None and (not cands[want]['format_valid']):
                    want = None
                upto = len(seq) if want is None else seq.index(want) + 1
                trials = []
                for cid in seq[:upto]:
                    trials.append({'candidate_id': cid, 'trial_list': 'matched' if arm == 'A' else 'threat',
                                   'passed': cid == want, 'flight_dir': f'flights/trial/{cid}/{arm}' if cands[cid]['format_valid'] else None,
                                   'outcomes': [{'episode_id': 'x'}] * (3 if cands[cid]['format_valid'] else 0)})
                row = {'adopted': want is not None, 'candidate_id': want,
                       'source_sha256': cands[want]['source_sha256'] if want else None, 'trials': trials,
                       'call_ids': [k for t in trials for k in cands[t['candidate_id']]['call_ids']]}
                arms[arm] = row
            c0_ok = cands['c0']['format_valid']
            qualified = True if choice['B'] == 'c0' else (c0_ok and bool(rng.integers(2)))
            allcalls = sorted({k for c in cands.values() for k in c['call_ids']})
            for k in allcalls:
                usage.append({'call_id': k, 'list_cost_usd': 0.01, 'input_tokens': 10, 'output_tokens': 5,
                              'served_by': 'synthetic', 'real_model_call': False})
            trial_flights = {t['flight_dir']: {f'x{n}': flight(1) for n in range(3)}
                             for row in arms.values() for t in row['trials'] if t['flight_dir']}
            snap['learning'][task][b] = {
                'arms_record': {'c0_zone_qualified': bool(qualified), 'arms': arms},
                'candidates': cands, 'usage': usage, 'timing': timing(task, b) if timing else None,
                'flights': trial_flights}
            sources = {row['source_sha256']: arm for arm, row in arms.items() if row['adopted']}
            if c0_ok:
                sources.setdefault(cands['c0']['source_sha256'], 'c0')
            for h in sources:
                name = next((n for n, c in cands.items() if c['source_sha256'] == h), 'c0')
                vals = cells(task, b, name) if cells else rng.integers(2, size=len(ecases))
                snap['hazard'][(task, b, h)] = {c.episode_id: flight(v) for c, v in zip(ecases, vals)}
                if h != cands['c0']['source_sha256'] or any(r['source_sha256'] == h for r in arms.values()):
                    snap['retention'][(task, b, h)] = {c.episode_id: flight(1) for c in rcases}
    if extra:
        extra(snap)
    return snap


ALL_ADOPT_C0 = {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'}
N_BOOT = 100


def run(snapshot, n_boot=N_BOOT):
    return A.analyse_snapshot(snapshot, n_boot=n_boot)



def nine(result):
    """The nine intervals in the order they were always made: the six D - A (secondary since ruling 88), then the pooled steps."""
    return {**result['secondary_intervals'], **result['primary']}


class LadderSimulationCallers(unittest.TestCase):
    """protocol/ladder_pooled3.py calls comparisons and pooled_comparisons with no cells, and reads the pooled rows. A task
    whose two arms have equal cells has a renamed per-task row; the pooled rule must still read its section 6.4 direction."""

    def test_pooled_comparisons_without_cells_reads_the_kept_direction_of_renamed_rows(self):
        rng = np.random.default_rng(1)
        bands = ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2
        y = {t: np.zeros((4, 6, 6)) for t in C.TASKS}
        y['reach'][1, :, :] = 1                      # B above A in reach: a gain
        y['reach3d'][0, :, :] = 1                    # A above B in reach3d: a loss
        # land: every arm 0 in every cell, so land's rows are renamed 'no success in either arm'
        steps, points, draws = {}, {}, {}
        for t in C.TASKS:
            steps[t], points[t], draws[t] = A.comparisons(y[t], bands, rng, 80)
        self.assertEqual(steps['land']['B-A']['classification']['class'], A.NO_SUCCESS)
        self.assertNotIn('direction', steps['land']['B-A']['classification'])
        pooled = A.pooled_comparisons(points, draws, steps)
        self.assertTrue(pooled['B-A']['task_dependent'])
        self.assertEqual(pooled['B-A']['classification'], {'class': 'task_dependent'})
        self.assertNotIn('answer', pooled['B-A'])       # no cells given, so no answer and no renaming of the pooled row


class NothingToCompare(unittest.TestCase):
    """Ruling 38, point 2: decided on the two arms' cells, never on the interval's width."""

    def names(self, result):
        return {k: v['classification']['class'] for k, v in nine(result).items()}

    def test_nothing_to_compare_function(self):
        zeros, ones = np.zeros((3, 4)), np.ones((3, 4))
        mixed = np.array([[0, 1, 0, 1]] * 3)
        self.assertEqual(A.nothing_to_compare(zeros, zeros, 3)['class'], A.NO_SUCCESS)
        self.assertEqual(A.nothing_to_compare(ones, ones, 3)['class'], A.EVERY_SUCCESS)
        same = A.nothing_to_compare(mixed, mixed.copy(), 3)
        self.assertEqual(same['class'], A.IDENTICAL)
        self.assertEqual(same['name'], 'identical outcomes in all 3 blocks')
        self.assertEqual(same['blocks'], 3)
        # one arm succeeding everywhere and the other nowhere differs in every cell: nothing replaces its name
        self.assertIsNone(A.nothing_to_compare(zeros, ones, 3))
        self.assertIsNone(A.nothing_to_compare(mixed, 1 - mixed, 3))
        self.assertIsNone(A.nothing_to_compare(zeros, mixed, 3))

    def test_one_block_is_worded_as_one_block(self):
        mixed = np.array([[0, 1]])
        self.assertEqual(A.nothing_to_compare(mixed, mixed, 1)['name'], 'identical outcomes in the 1 block')
        self.assertEqual(A.nothing_to_compare(mixed, mixed, 1)['one_sided_95_bound_on_share_of_blocks_differing'], 0.95)

    def test_bound_on_identical_outcomes(self):
        self.assertAlmostEqual(A.identical_bound(32), 1 - 0.05 ** (1 / 32), places=12)
        self.assertEqual(round(A.identical_bound(32), 3), 0.089)
        mixed = np.array([[0, 1]] * 32)
        self.assertEqual(A.nothing_to_compare(mixed, mixed, 32)['one_sided_95_bound_on_share_of_blocks_differing'],
                         A.identical_bound(32))
        self.assertNotIn('one_sided_95_bound_on_share_of_blocks_differing', A.nothing_to_compare(np.zeros((2, 2)), np.zeros((2, 2)), 2))

    def test_all_zero_in_every_cell(self):
        result = run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: [0] * 6))
        for key, row in nine(result).items():
            self.assertEqual(row['classification']['class'], A.NO_SUCCESS, key)
            self.assertEqual(row['classification']['name'], 'no success in either arm')
            self.assertEqual(row['underlying_classification']['class'], 'equivalent_not_different', key)
        for task in C.TASKS:
            for step in result['tasks'][task]['all_band_steps'].values():
                self.assertEqual(step['classification']['class'], A.NO_SUCCESS)
                self.assertEqual(step['sensitivity_margin_0_10']['class'], A.NO_SUCCESS)

    def test_all_one_in_every_cell(self):
        result = run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: [1] * 6))
        for key, row in nine(result).items():
            self.assertEqual(row['classification']['class'], A.EVERY_SUCCESS, key)
            self.assertEqual(row['classification']['name'], 'every flight succeeded in both arms')

    def test_identical_cell_for_cell(self):
        pattern = {0: [0, 1, 0, 1, 1, 0], 1: [1, 1, 0, 0, 1, 0], 2: [0, 0, 0, 1, 1, 1], 3: [1, 0, 1, 0, 0, 1]}
        result = run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: pattern[b]))
        for key, row in nine(result).items():
            c = row['classification']
            self.assertEqual(c['class'], A.IDENTICAL, key)
            self.assertEqual(c['name'], f"identical outcomes in all {c['blocks']} blocks")
            self.assertAlmostEqual(c['one_sided_95_bound_on_share_of_blocks_differing'], 1 - 0.05 ** (1 / c['blocks']))
        self.assertEqual(nine(result)['reach:D-A:close']['classification']['blocks'], 4)
        # a pooled step counts the blocks of the three tasks together
        self.assertEqual(nine(result)['pooled:C-B']['classification']['blocks'], 12)

    def test_one_arm_all_one_and_the_other_all_zero_keeps_its_name(self):
        # the ruling's own example: the interval has no width, but the arms differ in every cell
        adopt = {'A': None, 'B': None, 'C': None, 'D': 'c1'}
        result = run(make(blocks=4, adopt=lambda t, b: adopt, cells=lambda t, b, n: [1] * 6))
        row = nine(result)['reach:D-A:close']
        self.assertEqual(row['estimate'], 1.0)
        self.assertTrue(row['zero_width_bootstrap'])
        self.assertEqual(row['classification']['class'], 'different_not_equivalent')
        self.assertNotIn('underlying_classification', row)

    def test_pooled_step_is_tested_on_the_three_tasks_together(self):
        # reach: no success; reach3d: success everywhere; land: a pattern equal in both arms. Each task is named by its own
        # cells, and the pooled step has nothing to compare because no task has a cell where the arms differ.
        def cells(task, block, name):
            return {'reach': [0] * 6, 'reach3d': [1] * 6, 'land': [1, 0, 1, 0, 0, 1]}[task]
        result = run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=cells))
        pooled = result['pooled_ladder_steps']['C-B']
        self.assertEqual(pooled['classification']['class'], A.IDENTICAL)
        self.assertEqual({t: r['classification']['class'] for t, r in pooled['per_task'].items()},
                         {'reach': A.NO_SUCCESS, 'reach3d': A.EVERY_SUCCESS, 'land': A.IDENTICAL})
        # not the pooled name of section 6.4, and not task-dependent
        self.assertFalse(pooled['task_dependent'])

    def test_pooled_step_with_one_differing_cell_keeps_a_section_6_4_name(self):
        def adopt(task, block):
            return {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'}
        def cells(task, block, name):
            return [1, 1, 1, 1, 1, 1] if not (task == 'land' and block == 0 and name == 'c1') else [1, 1, 1, 1, 1, 0]
        result = run(make(blocks=4, adopt=adopt, cells=cells))
        # D differs from C in one cell of land, so D-C is not empty even pooled; C-B has identical cells everywhere
        self.assertNotIn(result['pooled_ladder_steps']['D-C']['classification']['class'], A.NOTHING_TO_COMPARE)
        self.assertEqual(result['pooled_ladder_steps']['C-B']['classification']['class'], A.EVERY_SUCCESS)

    def test_secondary_intervals_are_named_too(self):
        result = run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: [0] * 6))
        for task in C.TASKS:
            for band, steps in result['tasks'][task]['steps_by_band'].items():
                for step in steps.values():
                    self.assertEqual(step['classification']['class'], A.NO_SUCCESS, (task, band))

    def test_the_report_gives_the_plain_name_and_the_bound(self):
        pattern = {0: [0, 1, 0, 1, 1, 0], 1: [1, 1, 0, 0, 1, 0], 2: [0, 0, 0, 1, 1, 1], 3: [1, 0, 1, 0, 0, 1]}
        result = run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: pattern[b]))
        text = '\n'.join(A.report_lines(result))
        self.assertIn('identical outcomes in all 4 blocks', text)
        self.assertIn('identical outcomes in all 12 blocks', text)
        self.assertIn('one-sided 95% bound on the share of blocks in which the arms would differ: 52.7%', text)
        zero = '\n'.join(A.report_lines(run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: [0] * 6))))
        self.assertIn('no success in either arm', zero)
        self.assertNotIn('no gain or loss as large as the margin', zero)

    def test_analysis_json_can_be_written(self):
        result = run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: [0] * 6))
        self.assertIn(A.NO_SUCCESS, json.dumps(result, allow_nan=False))


def task_row(estimate, name='unresolved', direction='not_detected', ci=(-0.5, 0.5)):
    return {'estimate': estimate, 'ci95': list(ci), 'classification': {'class': name, 'direction': direction}}


def pooled_row(name, direction='not_detected', **extra):
    return {'classification': {'class': name, 'direction': direction, **extra}}


class RQ1Answer(unittest.TestCase):
    """Ruling 38, point 3: each cell of the table is one branch of A.answer."""

    GAIN = task_row(0.3, 'different_not_equivalent', 'gain', (0.1, 0.5))
    LOSS = task_row(-0.3, 'different_not_equivalent', 'loss', (-0.5, -0.1))
    FLAT = task_row(0.0)

    def per_task(self, *rows):
        return dict(zip(C.TASKS, rows))

    def test_signs_and_zero(self):
        self.assertEqual([A.sign_of(x) for x in (0.2, -0.2, 0.0)], ['+', '-', '0'])
        out = A.answer(pooled_row('unresolved'), self.per_task(task_row(0.1), task_row(0.0), task_row(0.2)))
        self.assertFalse(out['signs_differ'])
        out = A.answer(pooled_row('unresolved'), self.per_task(task_row(0.1), task_row(0.0), task_row(-0.2)))
        self.assertTrue(out['signs_differ'])
        self.assertFalse(A.answer(pooled_row('unresolved'), self.per_task(*[task_row(0.0)] * 3))['signs_differ'])

    def test_task_dependent_with_differing_signs(self):
        out = A.answer(pooled_row('task_dependent'), self.per_task(self.GAIN, self.LOSS, self.FLAT))
        self.assertEqual(out['status'], 'answered')
        self.assertEqual((out['raised_on'], out['lowered_on']), (['reach'], ['reach3d']))
        self.assertIn('raised success on reach and lowered it on reach3d', out['text'])

    def test_task_dependent_with_signs_that_do_not_differ_cannot_occur(self):
        with self.assertRaises(ValueError):
            A.answer(pooled_row('task_dependent'), self.per_task(self.GAIN, task_row(0.01, 'different_not_equivalent', 'loss'), self.FLAT))

    def test_a_gain_or_loss_with_signs_that_do_not_differ(self):
        for name in ('different_not_equivalent', 'different_and_equivalent'):
            out = A.answer(pooled_row(name, 'gain'), self.per_task(self.GAIN, self.FLAT, task_row(0.1)))
            self.assertEqual(out['status'], 'answered')
            self.assertEqual(out['text'], 'A pooled gain over these three tasks.')
            self.assertNotIn('other_sign_tasks', out)
            self.assertEqual(A.answer(pooled_row(name, 'loss'), self.per_task(self.LOSS, self.FLAT, task_row(-0.1)))['text'],
                             'A pooled loss over these three tasks.')

    def test_a_gain_or_loss_with_signs_that_differ_names_the_other_task_with_its_interval(self):
        out = A.answer(pooled_row('different_not_equivalent', 'gain'), self.per_task(self.GAIN, task_row(-0.05, ci=(-0.2, 0.1)), self.FLAT))
        self.assertEqual([t['task'] for t in out['other_sign_tasks']], ['reach3d'])
        self.assertEqual(out['other_sign_tasks'][0]['ci95'], [-0.2, 0.1])
        self.assertIn('reach3d -0.0500 (-0.2000, +0.1000)', out['text'])
        out = A.answer(pooled_row('different_not_equivalent', 'loss'), self.per_task(task_row(0.1), task_row(0.2), self.LOSS))
        self.assertEqual([t['task'] for t in out['other_sign_tasks']], ['reach', 'reach3d'])   # two tasks carry the other sign

    def test_no_pooled_gain_or_loss_as_large_as_the_margin(self):
        out = A.answer(pooled_row('equivalent_not_different'), self.per_task(task_row(0.01), self.FLAT, task_row(0.02)))
        self.assertEqual((out['status'], out['text']), ('answered', 'No pooled gain or loss as large as the margin over these three tasks.'))
        out = A.answer(pooled_row('equivalent_not_different'), self.per_task(task_row(0.2), task_row(-0.2), task_row(0.0)))
        self.assertEqual(out['status'], 'not_settled')
        self.assertIn("The average is near zero while the tasks' estimates point in opposite directions", out['text'])
        self.assertIn('Each is given with its interval. This does not show that the step made no difference.', out['text'])

    def test_unresolved(self):
        out = A.answer(pooled_row('unresolved'), self.per_task(task_row(0.1), task_row(0.2), task_row(0.0)))
        self.assertEqual(out['status'], 'unresolved')
        out = A.answer(pooled_row('unresolved'), self.per_task(task_row(0.1), task_row(-0.2), task_row(0.0)))
        self.assertEqual(out['status'], 'unresolved')
        self.assertIn('reach +, reach3d -, land 0', out['text'])

    def test_the_three_names_of_point_2(self):
        for key in A.NOTHING_TO_COMPARE:
            row = {'classification': {'class': key, 'name': 'identical outcomes in all 12 blocks' if key == A.IDENTICAL else A.NAMES[key]}}
            out = A.answer(row, self.per_task(*[task_row(0.0)] * 3))
            self.assertEqual(out['status'], 'answered')
            self.assertEqual(out['text'].lower(), row['classification']['name'] + '.')
            with self.assertRaises(ValueError):          # such a result cannot have per-task signs that differ
                A.answer(row, self.per_task(task_row(0.1), task_row(-0.1), task_row(0.0)))

    def test_the_report_words_an_answer_and_a_case_that_is_not_settled_differently(self):
        answered = '\n'.join(A.report_lines(run(make(blocks=4, adopt=lambda t, b: ALL_ADOPT_C0, cells=lambda t, b, n: [0] * 6))))
        self.assertIn('Answer: No success in either arm.', answered)
        self.assertNotIn('Answer (answered)', answered)
        unsettled = '\n'.join(A.report_lines(run(make(blocks=6, seed=5))))
        self.assertIn('Answer (not settled): Not settled.', unsettled)

    def test_every_pooled_step_carries_its_answer_and_the_report_prints_it(self):
        result = run(make(blocks=6, seed=5))
        for key, row in result['pooled_ladder_steps'].items():
            self.assertIn(row['answer']['status'], ('answered', 'not_settled', 'unresolved'), key)
            self.assertEqual(set(row['answer']['signs']), set(C.TASKS))
        text = '\n'.join(A.report_lines(result))
        self.assertIn('## RQ1: the answer for each pooled step', text)
        for key in ('C-B', 'B-A', 'D-C'):
            self.assertIn(f'### {key}', text)
        self.assertTrue('Answer: ' in text or 'Answer (' in text)
        json.dumps(result, allow_nan=False)


# Estimates and intervals that analysis3.py gives for make(blocks=6, seed=11, invalid_c0=(0,)) with 200 resamples: [estimate, 95%
# interval, 90% interval], for the nine primary intervals and for every task's steps over all bands and in each band. Build E3.7
# (ruling 46, point 1) gave each task's primary draws a generator of its own, [BOOT_SEED, 0, the task's index], and removed the
# draw that was made and thrown away; these numbers were computed once with that code and written in. They replace the numbers of
# the build before (head 9ffe6a36), 36 of whose 57 values differ.
GOLD = json.loads('{"reach:D-A:close":[0.0,[-0.5,0.5],[-0.333333333333,0.5]],"reach:D-A:middle-wide":[0.041666666667,[-0.25,0.333333333333],[-0.16875,0.291666666667]],"reach3d:D-A:close":[0.0,[-0.5,0.333333333333],[-0.333333333333,0.333333333333]],"reach3d:D-A:middle-wide":[0.208333333333,[-0.166666666667,0.542708333333],[-0.083333333333,0.5]],"land:D-A:close":[0.166666666667,[-0.170833333333,0.666666666667],[-0.008333333333,0.420833333333]],"land:D-A:middle-wide":[-0.125,[-0.5,0.125],[-0.375,0.083333333333]],"pooled:C-B":[-0.027777777778,[-0.222453703704,0.194444444444],[-0.194444444444,0.157407407407]],"pooled:B-A":[0.0,[-0.166898148148,0.129861111111],[-0.138888888889,0.12037037037]],"pooled:D-C":[0.074074074074,[-0.092824074074,0.250231481481],[-0.046759259259,0.231481481481]],"reach:all:C-B":[-0.083333333333,[-0.334027777778,0.194444444444],[-0.333333333333,0.166666666667]],"reach:all:B-A":[0.111111111111,[-0.166666666667,0.388888888889],[-0.111111111111,0.334722222222]],"reach:all:D-C":[0.0,[-0.334027777778,0.334722222222],[-0.277777777778,0.277777777778]],"reach:all:D-A":[0.027777777778,[-0.334027777778,0.361111111111],[-0.305555555556,0.305555555556]],"reach:close:C-B":[0.166666666667,[-0.335416666667,0.666666666667],[-0.170833333333,0.5875]],"reach:close:B-A":[0.0,[-0.333333333333,0.5],[-0.333333333333,0.420833333333]],"reach:close:D-C":[-0.166666666667,[-0.666666666667,0.41875],[-0.5,0.333333333333]],"reach:close:D-A":[0.0,[-0.5,0.5],[-0.333333333333,0.5]],"reach:middle:C-B":[-0.166666666667,[-0.666666666667,0.25],[-0.5,0.166666666667]],"reach:middle:B-A":[0.166666666667,[0.0,0.666666666667],[0.0,0.5]],"reach:middle:D-C":[0.166666666667,[-0.333333333333,0.666666666667],[-0.333333333333,0.5]],"reach:middle:D-A":[0.166666666667,[-0.3375,0.666666666667],[-0.333333333333,0.5]],"reach:wide:C-B":[-0.25,[-0.670833333333,0.0],[-0.666666666667,0.0]],"reach:wide:B-A":[0.166666666667,[-0.166666666667,0.5],[-0.166666666667,0.5]],"reach:wide:D-C":[0.0,[-0.5,0.5],[-0.5,0.333333333333]],"reach:wide:D-A":[-0.083333333333,[-0.333333333333,0.333333333333],[-0.333333333333,0.25]],"reach3d:all:C-B":[-0.111111111111,[-0.555555555556,0.250694444444],[-0.5,0.166666666667]],"reach3d:all:B-A":[0.138888888889,[0.0,0.416666666667],[0.0,0.388888888889]],"reach3d:all:D-C":[0.111111111111,[-0.139583333333,0.388888888889],[-0.055555555556,0.333333333333]],"reach3d:all:D-A":[0.138888888889,[-0.166666666667,0.446527777778],[-0.083333333333,0.444444444444]],"reach3d:close:C-B":[-0.25,[-0.833333333333,0.166666666667],[-0.666666666667,0.166666666667]],"reach3d:close:B-A":[0.083333333333,[0.0,0.3375],[0.0,0.333333333333]],"reach3d:close:D-C":[0.166666666667,[0.0,0.504166666667],[0.0,0.5]],"reach3d:close:D-A":[0.0,[-0.5,0.333333333333],[-0.333333333333,0.333333333333]],"reach3d:middle:C-B":[-0.25,[-0.66875,0.166666666667],[-0.666666666667,0.166666666667]],"reach3d:middle:B-A":[0.25,[0.0,0.666666666667],[0.0,0.5]],"reach3d:middle:D-C":[0.333333333333,[-0.166666666667,0.833333333333],[-0.008333333333,0.833333333333]],"reach3d:middle:D-A":[0.333333333333,[-0.166666666667,0.833333333333],[-0.083333333333,0.833333333333]],"reach3d:wide:C-B":[0.166666666667,[-0.333333333333,0.666666666667],[-0.25,0.666666666667]],"reach3d:wide:B-A":[0.083333333333,[0.0,0.333333333333],[0.0,0.254166666667]],"reach3d:wide:D-C":[-0.166666666667,[-0.66875,0.3375],[-0.666666666667,0.333333333333]],"reach3d:wide:D-A":[0.083333333333,[-0.333333333333,0.5],[-0.333333333333,0.5]],"land:all:C-B":[0.111111111111,[-0.277777777778,0.555555555556],[-0.225,0.444444444444]],"land:all:B-A":[-0.25,[-0.638888888889,0.111805555556],[-0.583333333333,0.055555555556]],"land:all:D-C":[0.111111111111,[-0.166666666667,0.416666666667],[-0.083333333333,0.361111111111]],"land:all:D-A":[-0.027777777778,[-0.277777777778,0.139583333333],[-0.223611111111,0.111111111111]],"land:close:C-B":[0.0,[-0.5,0.5],[-0.420833333333,0.5]],"land:close:B-A":[-0.166666666667,[-0.666666666667,0.333333333333],[-0.504166666667,0.170833333333]],"land:close:D-C":[0.333333333333,[-0.166666666667,0.833333333333],[-0.166666666667,0.666666666667]],"land:close:D-A":[0.166666666667,[-0.170833333333,0.666666666667],[-0.008333333333,0.420833333333]],"land:middle:C-B":[0.333333333333,[0.0,0.666666666667],[0.0,0.666666666667]],"land:middle:B-A":[-0.416666666667,[-0.833333333333,-0.083333333333],[-0.75,-0.1625]],"land:middle:D-C":[-0.083333333333,[-0.335416666667,0.333333333333],[-0.333333333333,0.170833333333]],"land:middle:D-A":[-0.166666666667,[-0.66875,0.333333333333],[-0.583333333333,0.166666666667]],"land:wide:C-B":[0.0,[-0.5,0.5],[-0.5,0.3375]],"land:wide:B-A":[-0.166666666667,[-0.5,0.252083333333],[-0.5,0.166666666667]],"land:wide:D-C":[0.083333333333,[-0.5,0.666666666667],[-0.333333333333,0.583333333333]],"land:wide:D-A":[-0.083333333333,[-0.5,0.41875],[-0.5,0.333333333333]]}')


def legacy_bootstrap(y, bands, rng, n_boot):
    """bootstrap() as it stood at d56b03d4."""
    y = np.asarray(y, dtype=float)
    nb, ns = y.shape[1:]
    groups = [np.flatnonzero(np.asarray(bands) == b) for b in dict.fromkeys(bands)]
    block_draw = rng.integers(nb, size=(n_boot, nb))
    wb = np.zeros((n_boot, nb))
    np.add.at(wb, (np.repeat(np.arange(n_boot), nb), block_draw.ravel()), 1 / nb)
    ws = np.zeros((n_boot, ns))
    for ids in groups:
        sampled = rng.choice(ids, size=(n_boot, len(ids)))
        np.add.at(ws, (np.repeat(np.arange(n_boot), len(ids)), sampled.ravel()), 1 / ns)
    return np.einsum('rb,abs,rs->ar', wb, y, ws, optimize=True)


def estimates(result):
    out = {k: [v['estimate'], v['ci95'], v['ci90']] for k, v in nine(result).items()}
    for t in C.TASKS:
        for sk, v in result['tasks'][t]['all_band_steps'].items():
            out[f'{t}:all:{sk}'] = [v['estimate'], v['ci95'], v['ci90']]
        for b, steps in result['tasks'][t]['steps_by_band'].items():
            for sk, v in steps.items():
                out[f'{t}:{b}:{sk}'] = [v['estimate'], v['ci95'], v['ci90']]
    return out


class PrimaryIntervalsUnchanged(unittest.TestCase):
    # Ruling 46, point 1: each task's primary draws come from a generator of its own, [BOOT_SEED, 0, the task's index], so no
    # task's primary intervals depend on another task's data or on a secondary. The numbers below are pinned.

    def test_numbers_are_those_pinned_for_the_per_task_generators(self):
        got = estimates(run(make(blocks=6, seed=11, invalid_c0=(0,)), n_boot=200))
        self.assertEqual(set(got), set(GOLD))
        for key, want in GOLD.items():
            self.assertEqual(got[key], want, key)

    def snapshot_result(self, **patches):
        from unittest import mock
        with contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(A, name, value))
            return run(make(blocks=6, seed=11, invalid_c0=(0,)), n_boot=200)

    def test_removing_a_secondary_leaves_every_primary_interval_equal(self):
        whole = run(make(blocks=6, seed=11, invalid_c0=(0,)), n_boot=200)
        without_rq4 = self.snapshot_result(close_minus_distant=lambda y, bands, rng, n: {'estimate': 0.0, 'ci95': [0, 0], 'ci90': [0, 0]})
        self.assertEqual(nine(without_rq4), nine(whole))

    def test_a_secondary_that_uses_many_more_draws_leaves_every_primary_interval_equal(self):
        whole = run(make(blocks=6, seed=11, invalid_c0=(0,)), n_boot=200)
        real = A.close_minus_distant

        def greedy(y, bands, rng, n):
            rng.random(10_000)             # a secondary that draws far more numbers than before
            return real(y, bands, rng, n)
        greedy_result = self.snapshot_result(close_minus_distant=greedy)
        self.assertEqual(nine(greedy_result), nine(whole))
        self.assertNotEqual(greedy_result['rq4_close_minus_distant'], whole['rq4_close_minus_distant'])      # the secondary did move

    def test_a_task_s_primary_intervals_do_not_depend_on_the_other_tasks_or_their_order(self):
        rng = np.random.default_rng(3)
        bands = ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2
        data = {t: {'y': rng.integers(2, size=(4, 5, 6)).astype(float), 'bands': bands, 'unqualified': [0, 2] if t == 'reach' else []}
                for t in C.TASKS}
        whole = A.primary_pass(data, 17, 200)
        for dropped in C.TASKS:
            rest = {t: d for t, d in data.items() if t != dropped}
            part = A.primary_pass(rest, 17, 200)['intervals']
            for key, row in part.items():
                if not key.startswith('pooled:'):
                    self.assertEqual(row, whole['intervals'][key], (dropped, key))
        reordered = A.primary_pass({t: data[t] for t in reversed(C.TASKS)}, 17, 200)
        for key, row in reordered['intervals'].items():
            if not key.startswith('pooled:'):
                self.assertEqual(row, whole['intervals'][key], key)
        # nor on which blocks have c0 unqualified, which used to move every later task's draws
        data['reach']['unqualified'] = []
        again = A.primary_pass(data, 17, 200)['intervals']
        self.assertEqual(again, whole['intervals'])

    def test_each_task_s_draws_come_from_the_generator_seeded_with_its_index(self):
        y = np.random.default_rng(5).integers(2, size=(4, 5, 6)).astype(float)
        bands = ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2
        data = {'land': {'y': y, 'bands': bands, 'unqualified': []}}
        got = A.primary_pass(data, 23, 150)
        rng = np.random.default_rng([23, 0, C.TASKS.index('land')])
        steps = A.comparisons(y, bands, rng, 150)[0]
        close = A.comparisons(y[:, :, :2], ['close'] * 2, rng, 150)[0]
        self.assertEqual(got['tasks']['land']['steps'], steps)
        self.assertEqual(got['intervals']['land:D-A:close'], close['D-A'])

    def test_bootstrap_is_the_old_function(self):
        y = np.random.default_rng(2).integers(2, size=(4, 5, 6)).astype(float)
        bands = ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2
        self.assertTrue(np.array_equal(A.bootstrap(y, bands, np.random.default_rng(9), 300),
                                       legacy_bootstrap(y, bands, np.random.default_rng(9), 300)))


class CloseMinusDistant(unittest.TestCase):
    """Ruling 38, point 4: RQ4, from the same resamples."""
    BANDS = ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2

    def y(self, seed=4):
        return np.random.default_rng(seed).integers(2, size=(4, 7, 6)).astype(float)

    def test_the_band_arrays_come_from_one_draw_with_the_all_band_draw(self):
        y = self.y()
        by_band = A.bootstrap_by_band(y, self.BANDS, np.random.default_rng(5), 300)
        whole = A.bootstrap(y, self.BANDS, np.random.default_rng(5), 300)
        self.assertEqual(list(by_band), ['close', 'middle', 'wide'])
        np.testing.assert_allclose(np.mean(list(by_band.values()), axis=0), whole, atol=1e-12)

    def test_each_band_is_weighted_by_its_own_cells(self):
        # the close band's cells are all 1 for arm 0 and the others' all 0: its mean is 1 in every replicate, not 1/3
        y = np.zeros((4, 5, 6))
        y[0, :, :2] = 1
        by_band = A.bootstrap_by_band(y, self.BANDS, np.random.default_rng(5), 200)
        np.testing.assert_allclose(by_band['close'][0], 1.0)
        np.testing.assert_allclose(by_band['middle'][0], 0.0)

    def test_estimate_is_close_minus_the_distant_primaries_estimate(self):
        result = run(make(blocks=6, seed=11), n_boot=300)
        for task in C.TASKS:
            row = result['rq4_close_minus_distant'][task]
            close = nine(result)[task + ':D-A:close']['estimate']
            distant = nine(result)[task + ':D-A:middle-wide']['estimate']
            self.assertAlmostEqual(row['estimate'], close - distant, places=9)
            self.assertAlmostEqual(row['d_minus_a_close']['estimate'], close, places=9)
            self.assertAlmostEqual(row['d_minus_a_distant']['estimate'], distant, places=9)
            self.assertIsNone(row['section_6_4_name'])
            self.assertTrue(row['descriptive'])
            self.assertNotIn('classification', row)
            self.assertLessEqual(row['ci95'][0], row['ci90'][0])
            self.assertLessEqual(row['ci90'][1], row['ci95'][1])

    def test_interval_is_from_the_same_resamples_for_both_parts(self):
        y = self.y(8)
        row = A.close_minus_distant(y, self.BANDS, np.random.default_rng(3), 400)
        by_band = A.bootstrap_by_band(y, self.BANDS, np.random.default_rng(3), 400)
        d, a = 3, 0
        diff = (by_band['close'][d] - by_band['close'][a]) - ((by_band['middle'][d] + by_band['wide'][d]) / 2
                                                              - (by_band['middle'][a] + by_band['wide'][a]) / 2)
        self.assertEqual(row['ci95'], A.interval(diff))
        self.assertEqual(row['ci90'], A.interval(diff, .90))

    def test_a_task_where_close_and_distant_differ(self):
        y = np.zeros((4, 8, 6))
        y[3, :, :2] = 1            # D succeeds on close targets only
        row = A.close_minus_distant(y, self.BANDS, np.random.default_rng(1), 200)
        self.assertEqual(row['estimate'], 1.0)
        self.assertNotIn('nothing_to_compare', row)

    def test_d_equal_to_a_has_nothing_to_compare(self):
        y = self.y()
        y[3] = y[0]
        row = A.close_minus_distant(y, self.BANDS, np.random.default_rng(1), 200)
        self.assertEqual(row['estimate'], 0.0)
        self.assertEqual(row['nothing_to_compare']['class'], A.IDENTICAL)
        self.assertNotIn('classification', row)

    def test_the_report_has_a_section_for_it(self):
        text = '\n'.join(A.report_lines(run(make(blocks=6, seed=11))))
        self.assertIn('## RQ4: D - A on close targets minus D - A on distant targets (descriptive, no section 6.4 name)', text)
        self.assertIn('These resamples are not the ones that made the primary intervals', text)
        for task in C.TASKS:
            self.assertIn(f'| {task} |', text)


def only(task_to_blocks, key, value):
    """An `extra` hook for make(): set a field of each listed block's record."""
    def hook(snap):
        for task, blocks in task_to_blocks.items():
            for b in blocks:
                key(snap['learning'][task][b], value)
    return hook


def set_qualified(flags):
    """flags[b] is c0_zone_qualified of block b, in every task."""
    def hook(snap):
        for task in C.TASKS:
            for b, flag in enumerate(flags):
                snap['learning'][task][b]['arms_record']['c0_zone_qualified'] = flag
    return hook


class SecondaryCounts(unittest.TestCase):
    """Ruling 38, point 5: counts and shares."""

    def adopt(self, task, b):
        return {'A': 'f1' if b % 2 else None, 'B': 'c0', 'C': 'rC2' if b == 0 else 'c0', 'D': 'c1'}

    def test_candidate_at_which_each_arm_adopted_and_how_often_nothing(self):
        sec = run(make(blocks=4, adopt=self.adopt))['secondary']['adoption_by_candidate']
        self.assertEqual(sec['A'], {'f1': 6, 'nothing': 6})
        self.assertEqual(sec['B'], {'c0': 12})
        self.assertEqual(sec['C'], {'rC2': 3, 'c0': 9})
        self.assertEqual(sec['D'], {'c1': 12})

    def test_share_of_fresh_candidates_equal_to_c0(self):
        # make() copies c0's source into f1 of block 1: one in each task, three in all, of 4 * 2 * 3 fresh slots
        f = run(make(blocks=4, adopt=self.adopt))['secondary']['fresh_candidates_equal_to_c0']
        self.assertEqual((f['candidates'], f['valid'], f['same_source_as_c0']), (24, 24, 3))
        self.assertEqual(f['share_of_fresh_candidates'], 3 / 24)

    def test_a_fresh_slot_that_is_not_valid_is_never_equal_to_a_c0_that_is_not_valid(self):
        def hook(snap):
            for task in C.TASKS:
                cands = snap['learning'][task][1]['candidates']
                cands['c0'].update(format_valid=False, source_sha256=None)
                cands['f1'].update(format_valid=False, source_sha256=None)
        f = run(make(blocks=4, adopt=lambda t, b: {'A': None, 'B': None, 'C': None, 'D': 'c1'}, extra=hook))['secondary']['fresh_candidates_equal_to_c0']
        self.assertEqual(f['same_source_as_c0'], 0)
        self.assertEqual((f['candidates'], f['valid']), (24, 21))      # the three f1 slots of block 1 are not valid

    def test_slots_by_kind_and_state(self):
        # make(): c0 valid except in block 0 (not valid), f2 has two calls, every other slot one call and valid
        sec = run(make(blocks=4, invalid_c0=(0,), adopt=lambda t, b: {'A': None, 'B': None, 'C': None, 'D': 'c1'}))['secondary']['slots_by_kind']
        self.assertEqual(sec['c0'], {'valid_at_first_call': 9, 'valid_after_format_repair': 0, 'not_valid': 3})
        self.assertEqual(sec['c1'], {'valid_at_first_call': 12, 'valid_after_format_repair': 0, 'not_valid': 0})
        self.assertEqual(sec['fresh'], {'valid_at_first_call': 12, 'valid_after_format_repair': 12, 'not_valid': 0})
        self.assertEqual(sec['repair'], {'valid_at_first_call': 48, 'valid_after_format_repair': 0, 'not_valid': 0})

    def test_message_ids_come_from_the_gate_report(self):
        def hook(snap):
            snap['gate'].update(repeated_message_ids=2, message_ids_seen=40, copies_caught=3, message_ids_in_file_with_no_row=1)
        result = run(make(blocks=3, extra=hook))
        m = result['secondary']['message_ids_that_appear_more_than_once']
        self.assertEqual(m, {'count': 2, 'message_ids_seen': 40, 'gate_requires': 0, 'copies_caught': 3,
                             'message_ids_in_file_with_no_row': 1,      # G6 and G7 add the next two fields; none in a hand-made snapshot
                             'message_id_file_fragments': 0,
                             'provider_rows_with_no_spending_row': {'count': 0, 'list_cost_usd': 0.0, 'charged_usd': 0.0, 'rows_with_charge': 0,
                                                                  'rows_without_list_cost': 0}})
        text = '\n'.join(A.report_lines(result))
        self.assertIn('Copies caught', text)
        self.assertIn(': 3.', text)
        self.assertIn('with no provider row (a process killed between the claim and the row): 1.', text)


class ConditionalCMinusB(unittest.TestCase):
    """Ruling 38, point 5: C - B where c0 was valid and failed; blocks where c0 was not valid are counted and left out."""
    FLAGS = [False, False, True, False, True, False]

    # In the blocks where c0 is unqualified, B adopts nothing and C adopts its first repair, which succeeds more in blocks 0
    # and 3 (c0 not valid) than in blocks 1 and 5 (c0 valid and failed). The blocks left out therefore change C - B.
    RC1 = {0: [1] * 6, 1: [1, 1, 0, 0, 0, 0], 3: [1] * 6, 5: [1, 0, 0, 0, 0, 0]}

    def build(self):
        def adopt(task, b):
            return {'A': None, 'B': 'c0' if self.FLAGS[b] else None, 'C': 'c0' if self.FLAGS[b] else 'rC1', 'D': 'c1'}

        def cells(task, b, name):
            return self.RC1[b] if name == 'rC1' else [0] * 6
        return make(blocks=6, seed=21, invalid_c0=(0, 3), extra=set_qualified(self.FLAGS), adopt=adopt, cells=cells)

    def test_blocks_with_c0_not_valid_are_counted_and_left_out(self):
        result = run(self.build())
        for task in C.TASKS:
            c = result['tasks'][task]['conditional_first_qualification_failure']
            # unqualified: blocks 0, 1, 3, 5. Valid and failed: 1 and 5. Not valid: 0 and 3.
            self.assertEqual((c['blocks'], c['c0_not_valid_blocks_left_out']), (2, 2))

    def test_the_interval_is_c_minus_b_on_those_blocks_only(self):
        snap = self.build()
        result = run(snap)
        for task in C.TASKS:
            y = np.zeros((4, 6, 6))
            cases = C.evaluation_cases(snap['seeds'], task, True)
            for j in range(6):
                row = snap['learning'][task][j]['arms_record']['arms']
                for i, arm in enumerate(C.ARMS):
                    if row[arm]['adopted']:
                        fl = snap['hazard'][(task, j, row[arm]['source_sha256'])]
                        y[i, j] = [fl[c.episode_id]['goal_met'] for c in cases]
            bands = ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2
            want = A.comparisons(y[:, [1, 5], :], bands, np.random.default_rng([C.BOOT_SEED, 1, C.TASKS.index(task)]), N_BOOT)[0]['C-B']
            got = result['tasks'][task]['conditional_first_qualification_failure']['C-B']
            self.assertEqual((got['estimate'], got['ci95']), (want['estimate'], want['ci95']))

    def test_no_block_where_c0_was_valid_and_failed(self):
        snap = make(blocks=3, invalid_c0=(0,), extra=set_qualified([False, True, True]),
                    adopt=lambda t, b: {'A': None, 'B': 'c0' if b else None, 'C': 'c0' if b else None, 'D': 'c1'})
        c = run(snap)['tasks']['reach']['conditional_first_qualification_failure']
        self.assertEqual((c['blocks'], c['c0_not_valid_blocks_left_out'], c['C-B']), (0, 1, None))


class C0OnEvaluation(unittest.TestCase):
    def test_not_valid_c0_counts_as_zero_and_the_blocks_are_counted(self):
        def cells(task, b, name):
            return [1, 1, 1, 0, 0, 0]
        snap = make(blocks=4, invalid_c0=(0, 2), cells=cells, adopt=lambda t, b: {'A': None, 'B': None, 'C': None, 'D': 'c1'})
        result = run(snap)
        for task in C.TASKS:
            o = result['tasks'][task]['c0_one_shot']
            self.assertEqual((o['blocks'], o['blocks_c0_not_valid'], o['not_valid_c0_counted_as']), (4, 2, 0))
            self.assertAlmostEqual(o['mean'], 0.25)                       # two blocks at 1/2, two at 0
            self.assertAlmostEqual(o['mean_over_blocks_with_valid_c0'], 0.5)
            self.assertEqual(o['scheduled_outcomes'], 24)
        c0 = result['secondary']['c0_one_shot']
        self.assertEqual((c0['blocks'], c0['blocks_c0_not_valid']), (12, 6))
        self.assertIn('Blocks whose c0 was not valid: 6 of 12', '\n'.join(A.report_lines(result)))


def lagged(decision, observation, **extra):
    """An outcome whose steps carry these lags (command lag on the deadline); extra fields are added to it."""
    o = flight(1, **extra)
    o['native_steps'] = [{'t': i + 1, 'decision_lag_s': d, 'observation_lag_s': ob, 'command_lag_s': 0.3,
                          'north_m': 30.0, 'east_m': 40.0, 'alt_m': 10.0} for i, (d, ob) in enumerate(zip(decision, observation))]
    return o


class TimingByArm(unittest.TestCase):
    def build(self):
        def hook(snap):
            # D's source is its own; give every one of D's hazard flights the same lags, zone and call times
            for task in C.TASKS:
                for b in range(3):
                    h = snap['learning'][task][b]['arms_record']['arms']['D']['source_sha256']
                    for ep, o in snap['hazard'][(task, b, h)].items():
                        o.update(lagged([0.0, 0.1, 0.35], [0.0, 0.1, 0.0]))
                        o.update(events=[['threat', 0, 0, 0.0, 0.0, 10.0]], event_starts={'0': 1},
                                 _call_wall_s={'procedure': [0.04, 0.06, 0.05], 'guard': [0.02, 0.03]})
        return make(blocks=3, extra=hook, adopt=lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'})

    def test_the_figures_of_an_arms_hazard_flights(self):
        g = run(self.build())['secondary']['timing_by_arm']['D']['evaluation_hazard']
        self.assertEqual(g['flights'], 54)                   # 3 tasks * 3 blocks * 6 scenarios
        self.assertEqual(g['decisions'], 162)
        self.assertEqual(g['median_recorded_lag_s'], 0.1)
        self.assertEqual(g['max_recorded_lag_s'], 0.35)
        self.assertAlmostEqual(g['share_of_decisions_at_least_0_1s_late'], 2 / 3, places=5)
        self.assertEqual(g['max_own_lag_s'], 0.35)
        self.assertEqual(g['observations_read_a_step_or_more_late'], 54)       # one a step late in each flight
        self.assertEqual(g['missed_deadlines'], 54)                            # one in each flight: an own lag of 3 steps
        self.assertEqual(g['late_flights'], 54)
        self.assertEqual(g['first_sight_m'], {'zone_flights': 54, 'median': 40.0, 'min': 40.0})
        self.assertEqual(g['procedure_call_s'], {'n': 162, 'median': 0.05, 'p99': 0.06, 'max': 0.06})
        self.assertEqual(g['guard_call_s']['n'], 108)
        self.assertEqual(g['flights_without_call_times'], 0)

    def test_other_arms_are_not_touched(self):
        g = run(self.build())['secondary']['timing_by_arm']['A']['evaluation_hazard']
        self.assertEqual((g['missed_deadlines'], g['late_flights']), (0, 0))
        self.assertEqual(g['median_recorded_lag_s'], 0.0015)

    def test_a_flight_without_the_fields_is_counted_and_not_guessed(self):
        def hook(snap):
            for flights in snap['hazard'].values():
                for o in flights.values():
                    o.pop('_call_wall_s', None)
        g = run(make(blocks=2, extra=hook))['secondary']['timing_by_arm']['A']['evaluation_hazard']
        self.assertEqual(g['flights_without_call_times'], g['flights'])
        self.assertIsNone(g['procedure_call_s'])
        self.assertEqual(g['first_sight_m'], {'zone_flights': 0, 'median': None, 'min': None})

    def test_learning_trial_flights_belong_to_the_arm_that_flew_the_trial(self):
        r = run(make(blocks=2, adopt=lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'}))
        g = r['secondary']['timing_by_arm']
        # each arm adopted at its first slot: one trial of three flights per block and task
        self.assertEqual([g[a]['learning_trials']['flights'] for a in C.ARMS], [18, 18, 18, 18])

    def test_first_sight_function(self):
        o = lagged([0.0, 0.0], [0.0, 0.0], events=[['threat', 0, 0, 3.0, 4.0, 1.0]], event_starts={'0': 1})
        o['native_steps'][1].update(north_m=0.0, east_m=0.0)
        self.assertEqual(A.first_sight_m(o), 4.0)
        self.assertIsNone(A.first_sight_m({'native_steps': []}))
        self.assertIsNone(A.first_sight_m(lagged([0.0], [0.0], events=[['threat', 0, 0, 3.0, 4.0, 1.0]])))


class CallsFlownAgain(unittest.TestCase):
    ROWS = [
        {'flight': 'flights/first/P0/matched-close-1', 'attempt': 3, 'kept_late': True},
        {'flight': 'late/flights/first/P0/attempt-1/matched-close-1', 'set_aside_from': 'flights/first/P0/matched-close-1', 'attempt': 1},
        {'flight': 'late/flights/first/P0/attempt-1/matched-wide-2', 'set_aside_from': 'flights/first/P0/matched-wide-2', 'attempt': 1},
        {'flight': 'late/flights/first/P0/attempt-2/matched-close-1', 'set_aside_from': 'flights/first/P0/matched-close-1', 'attempt': 2},
        {'flight': 'late/flights/trial/rC1/C/attempt-1/threat-close-1', 'set_aside_from': 'flights/trial/rC1/C/threat-close-1', 'attempt': 1},
        {'flight': 'flights/trial/rC1/C/threat-close-1', 'attempt': 2, 'late': False},
    ]

    def test_attributed_to_the_arms_that_flew_the_call(self):
        adopt = lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'rC1', 'D': 'c1'}      # noqa: E731
        rows = lambda t, b: list(self.ROWS) if (t, b) == ('reach', 0) else None   # noqa: E731
        r = run(make(blocks=2, adopt=adopt, timing=rows))['secondary']
        # P0 is flown by A, B and C: 2 attempts set aside for one call and 1 for another; the trial of rC1 by C alone
        a = r['calls_flown_again_by_arm']
        # calls are the folders: flights/first/P0 (one call, two set-aside attempts), flights/trial/rC1/C
        self.assertEqual(a['A'], {'calls_flown_again': 1, 'attempts_set_aside': 2, 'flights_kept_late': 0 + 1})
        self.assertEqual(a['B'], a['A'])
        self.assertEqual(a['D'], {'calls_flown_again': 0, 'attempts_set_aside': 0, 'flights_kept_late': 0})
        self.assertEqual(a['C'], {'calls_flown_again': 2, 'attempts_set_aside': 3, 'flights_kept_late': 1})
        self.assertEqual(r['calls_flown_again_in_the_run'],
                         {'calls_flown_again': 2, 'attempts_set_aside': 3, 'flights_kept_late': 1, 'blocks_without_timing_rows': 5})

    def test_a_kept_late_trial_flight_counts_for_its_arm(self):
        rows = [{'flight': 'flights/trial/c1/D/threat-close-1', 'attempt': 3, 'kept_late': True}]
        r = run(make(blocks=1, adopt=lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'},
                     timing=lambda t, b: rows if t == 'land' else None))['secondary']['calls_flown_again_by_arm']
        self.assertEqual([r[a]['flights_kept_late'] for a in C.ARMS], [0, 0, 0, 1])


class SpendOfBlocksSetAside(unittest.TestCase):
    def test_set_aside_blocks_beside_the_unique_spend(self):
        def hook(snap):
            usage = [{'call_id': f'x{n}', 'list_cost_usd': 0.5, 'input_tokens': 1, 'output_tokens': 1, 'served_by': 'm'} for n in range(3)]
            provider = [{'request_id': f'x{n}', 'charged_usd': 0.55 if n else None, 'cost_usd': 0.5} for n in range(3)]
            snap['set_aside_learning'].append({'phase': 'learn3-reach-b0', 'attempt': 1, 'reason': 'crashed',
                                               'crash_evidence_kind': 'failed_exit', 'usage': usage, 'provider': provider})
        r = run(make(blocks=2, extra=hook))['secondary']['spend']
        self.assertEqual(r['unique']['calls'], 54)
        self.assertAlmostEqual(r['unique']['list_cost_usd'], 0.54)
        aside = r['learning_blocks_set_aside']
        self.assertEqual((aside['blocks'], aside['usage']['calls']), (1, 3))
        self.assertAlmostEqual(aside['usage']['list_cost_usd'], 1.5)
        self.assertEqual(aside['provider_charge'], {'rows': 3, 'rows_with_charge': 2, 'charged_usd_known_subtotal': 1.1})
        self.assertAlmostEqual(r['unique_plus_set_aside_list_cost_usd'], 2.04)
        text = '\n'.join(A.report_lines(run(make(blocks=2, extra=hook))))
        self.assertIn('Blocks set aside: 1, 3 calls, US$1.5000', text)
        self.assertNotIn('US$none', text)


def rebuild_y(snap, task, flip=None):
    """The arms-by-blocks-by-scenarios cells of a task, read from the snapshot. flip maps (arm index, block) to a value that
    replaces the cells of the scenarios in the kept-late set."""
    cases = C.evaluation_cases(snap['seeds'], task, True)
    blocks = sorted(snap['learning'][task])
    y = np.zeros((4, len(blocks), len(cases)))
    for j in blocks:
        row = snap['learning'][task][j]['arms_record']['arms']
        for i, arm in enumerate(C.ARMS):
            if row[arm]['adopted']:
                fl = snap['hazard'][(task, j, row[arm]['source_sha256'])]
                y[i, j] = [fl[c.episode_id]['goal_met'] for c in cases]
    return y, cases


class KeptLateEvaluation(unittest.TestCase):
    """Ruling 39, point 2."""
    ADOPT = staticmethod(lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'})

    def snap(self, **kw):
        # A, B and C fly c0's source; D flies c1's
        return make(blocks=5, seed=7, adopt=self.ADOPT, **kw)

    def c0_source(self, snap, task='reach', block=0):
        return snap['learning'][task][block]['candidates']['c0']['source_sha256']

    def test_with_nothing_kept_late_both_fills_are_the_primary_intervals(self):
        k = run(self.snap())['kept_late_evaluation']
        result = run(self.snap())
        self.assertEqual(k['flights_in_all'], 0)
        self.assertEqual(k['primary_cells_set'], 0)
        for label in ('primary_under_lower_fill', 'primary_under_upper_fill'):
            self.assertEqual(set(k[label]), set(nine(result)))
            for key, row in nine(result).items():
                self.assertEqual(k[label][key]['estimate'], row['estimate'], key)
                self.assertEqual(k[label][key]['ci95'], row['ci95'], key)
                self.assertEqual(k[label][key]['classification'], row['classification'], key)
        self.assertEqual(k['names_change'], {})

    def test_kept_late_flights_by_arm_and_both_bounds(self):
        probe = self.snap()
        h = self.c0_source(probe)
        close = [c.episode_id for c in C.evaluation_cases(probe['seeds'], 'reach', True)][:2]     # the two close scenarios
        snap = self.snap(kept_late={('threat3', 'reach', 0, h): close})
        result = run(snap)
        k = result['kept_late_evaluation']
        self.assertEqual(k['flights_by_phase'], {'threat3': 2})
        # A, B and C fly c0's source: two cells each. D flies another source.
        self.assertEqual({a: c['hazard_cells'] for a, c in k['cells_by_arm'].items()}, {'A': 2, 'B': 2, 'C': 2, 'D': 0})
        self.assertEqual(k['primary_cells_set'], 6)
        y, cases = rebuild_y(snap, 'reach')
        # D - A: D has no kept-late cell, A has two. The lower bound takes A's as 1, the upper bound as 0 (G4).
        for label, value in (('lower', 1), ('upper', 0)):
            z = y.copy()
            z[0, 0, :2] = value
            close_cols = [i for i, c in enumerate(cases) if 'close' in c.episode_id]
            want = z[3][:, close_cols].mean() - z[0][:, close_cols].mean()
            got = k[f'primary_under_{label}_fill']['reach:D-A:close']['estimate']
            self.assertAlmostEqual(got, want, places=9)
        # the as-kept numbers are the primaries
        self.assertAlmostEqual(nine(result)['reach:D-A:close']['estimate'],
                               y[3][:, :2].mean() - y[0][:, :2].mean(), places=9)
        # a task with nothing kept late is not changed
        for key in ('reach3d:D-A:close', 'land:D-A:middle-wide'):
            self.assertEqual(k['primary_under_lower_fill'][key]['estimate'], nine(result)[key]['estimate'])

    def test_a_retention_flight_kept_late_is_counted_but_not_flipped(self):
        probe = self.snap()
        h = self.c0_source(probe)
        ids = [c.episode_id for c in C.retention_cases(probe['seeds'], 'reach', True)][:1]
        result = run(self.snap(kept_late={('retain3', 'reach', 0, h): ids}))
        k = result['kept_late_evaluation']
        self.assertEqual(k['flights_by_phase'], {'retain3': 1})
        self.assertEqual({a: c['retention_cells'] for a, c in k['cells_by_arm'].items()}, {'A': 1, 'B': 1, 'C': 1, 'D': 0})
        self.assertEqual(k['primary_cells_set'], 0)
        for key, row in nine(result).items():
            self.assertEqual(k['primary_under_upper_fill'][key]['estimate'], row['estimate'])

    def test_a_kept_late_flight_of_c0_alone_is_in_no_arms_cells(self):
        probe = make(blocks=3, adopt=lambda t, b: {'A': None, 'B': None, 'C': None, 'D': 'c1'})
        h = self.c0_source(probe)
        ids = [c.episode_id for c in C.evaluation_cases(probe['seeds'], 'reach', True)][:1]
        k = run(make(blocks=3, adopt=lambda t, b: {'A': None, 'B': None, 'C': None, 'D': 'c1'},
                     kept_late={('threat3', 'reach', 0, h): ids}))['kept_late_evaluation']
        self.assertEqual(k['flights_in_all'], 1)
        self.assertEqual(k['primary_cells_set'], 0)

    def test_the_name_may_change_between_the_bounds_and_the_report_says_so(self):
        # B and A fly the same source with two cells kept late; D is all 1. Set to 0 they are all 0 for A: D - A differs more
        def cells(task, block, name):
            return [1] * 6
        probe = make(blocks=3, adopt=self.ADOPT, cells=cells)
        h = self.c0_source(probe)
        ids = [c.episode_id for c in C.evaluation_cases(probe['seeds'], 'reach', True)]
        snap = make(blocks=3, adopt=self.ADOPT, cells=cells, kept_late={('threat3', 'reach', b, self.c0_source(probe, 'reach', b)): ids for b in range(3)})
        result = run(snap)
        k = result['kept_late_evaluation']
        # D - A: A is the arm with the kept-late cells; the lower bound takes them as 1, so A and D are all 1
        self.assertEqual(k['primary_under_lower_fill']['reach:D-A:close']['classification']['class'], A.EVERY_SUCCESS)
        self.assertNotEqual(k['primary_under_upper_fill']['reach:D-A:close']['classification']['class'], A.EVERY_SUCCESS)
        self.assertIn('reach:D-A:close', k['names_change'])
        text = '\n'.join(A.report_lines(result))
        self.assertIn('## Evaluation flights kept late and evaluation phases flown again', text)
        self.assertIn('| Contrast | Designation | As kept | Lower fill | Upper fill |', text)
        self.assertIn('The name differs from the as-kept name under one or both fills for:', text)
        self.assertIn('reach:D-A:close', text.split('The name differs from the as-kept name under one or both fills for:')[1])

    def test_report_with_nothing_kept_late_says_so(self):
        text = '\n'.join(A.report_lines(run(self.snap())))
        self.assertIn('No evaluation flight was kept late.', text)


class AttemptsFlownAgain(unittest.TestCase):
    def snap(self, attempts):
        probe = make(blocks=2, adopt=lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'})
        h = probe['learning']['reach'][0]['candidates']['c0']['source_sha256']
        ids = [c.episode_id for c in C.evaluation_cases(probe['seeds'], 'reach', True)]
        kept = probe['hazard'][('reach', 0, h)]
        rows = []
        for n, (reason, flips, missing) in enumerate(attempts, 1):
            cells = {ep: (not kept[ep]['goal_met'] if i in flips else kept[ep]['goal_met']) for i, ep in enumerate(ids)}
            for i in missing:
                cells[ids[i]] = None
            rows.append({'phase': 'threat3', 'task': 'reach', 'block': 0, 'source': h, 'attempt': n, 'reason': reason, 'cells': cells})
        return make(blocks=2, adopt=lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'},
                    extra=lambda s: s['evaluation_attempts'].extend(rows)), h

    def test_cells_that_differ_from_the_attempt_kept_are_counted_for_each_attempt(self):
        snap, h = self.snap([('late', {0, 3}, ()), ('late', set(), ()), ('crashed', {1}, {4, 5})])
        again = run(snap)['evaluation_phases_flown_again']
        name = f'threat3-reach-b0-{h}'
        self.assertEqual(again['phases_flown_again'], 1)
        self.assertEqual(again['attempts_set_aside'], 3)
        got = [(a['attempt'], a['reason'], a['cells_differing_from_the_attempt_kept'], a['cells_without_an_outcome'])
               for a in again['phases'][name]]
        self.assertEqual(got, [(1, 'late', 2, 0), (2, 'late', 0, 0), (3, 'crashed', 1, 2)])
        self.assertEqual((again['cells_compared'], again['cells_differing']), (6 + 6 + 4, 3))
        text = '\n'.join(A.report_lines(run(snap)))
        self.assertIn(f'| {name} | 1 | late | 6 | 2 | 0 |', text)
        self.assertIn(f'| {name} | 3 | crashed | 6 | 1 | 2 |', text)

    def test_a_retention_phase_is_compared_with_the_retention_cells(self):
        probe = make(blocks=2, adopt=lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'})
        h = probe['learning']['reach'][0]['candidates']['c0']['source_sha256']
        ids = [c.episode_id for c in C.retention_cases(probe['seeds'], 'reach', True)]
        row = {'phase': 'retain3', 'task': 'reach', 'block': 0, 'source': h, 'attempt': 1, 'reason': 'late',
               'cells': {ids[0]: False, ids[1]: True}}       # the fixture's retention flights all succeed
        snap = make(blocks=2, adopt=lambda t, b: {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'}, extra=lambda s: s['evaluation_attempts'].append(row))
        again = run(snap)['evaluation_phases_flown_again']
        self.assertEqual(again['cells_differing'], 1)

    def test_no_phase_flown_again(self):
        again = run(make(blocks=2))['evaluation_phases_flown_again']
        self.assertEqual((again['phases_flown_again'], again['attempts_set_aside'], again['cells_compared']), (0, 0, 0))
        json.dumps(run(make(blocks=2)), allow_nan=False)


SESSIONS = [{'event': 'start', 'time': '2026-11-20 09:00:00', 'spend_limit_usd': 60.0, 'spend_limit_from_flag': False},
            {'event': 'resume', 'time': '2026-11-21 10:00:00', 'spend_limit_usd': 60.0, 'spend_limit_from_flag': False}]
RAISED = {'event': 'resume', 'time': '2026-11-22 11:00:00', 'spend_limit_usd': 90.0, 'spend_limit_from_flag': True}


def stops_snapshot(sessions, other, pilot=True):
    snap = make(blocks=2)
    snap['pilot'] = pilot
    snap['gate'].update(session_spend_stops=sessions, sessions_with_other_spend_stop=other)
    return snap


class SpendingStops(unittest.TestCase):
    """Ruling 39, point 3."""

    def test_every_session_with_the_protocols_stop(self):
        out = A.spend_stops(stops_snapshot(SESSIONS, [], pilot=False))
        self.assertEqual(out['sessions'], SESSIONS)
        self.assertEqual(out['statement'], "Every one of the 2 sessions had the protocol's spending stop of US$60.")

    def test_a_session_with_another_stop_is_said_plainly(self):
        out = A.spend_stops(stops_snapshot(SESSIONS + [RAISED], [RAISED], pilot=False))
        self.assertIn("In 1 of 3 sessions the spending stop was not the protocol's US$60", out['statement'])
        self.assertIn('the resume at 2026-11-22 11:00:00 had US$90 (set by the --spend-limit flag)', out['statement'])
        self.assertIn('The paper says so.', out['statement'])
        self.assertEqual(out['sessions_with_other_stop'], [RAISED])

    def test_a_pilot_is_not_judged_and_a_scored_run_with_no_record_says_so(self):
        self.assertIn('This is a pilot.', A.spend_stops(stops_snapshot(SESSIONS + [RAISED], [], pilot=True))['statement'])
        self.assertIn('no session record', A.spend_stops(stops_snapshot([], [], pilot=False))['statement'])

    def test_the_figure_is_the_gates_and_not_a_second_copy(self):
        snap = stops_snapshot(SESSIONS, [], pilot=False)
        snap['gate']['spend_stop_in_protocol_usd'] = 75.0
        self.assertIn('US$75', A.spend_stops(snap)['statement'])

    def test_the_report_lists_each_session(self):
        text = '\n'.join(A.report_lines(run(stops_snapshot(SESSIONS + [RAISED], [RAISED]))))
        self.assertIn('## The spending stop of each session, and learning blocks set aside', text)
        self.assertIn('| resume | 2026-11-22 11:00:00 | 90.0 | True |', text)
        self.assertIn('Blocks already running go on spending after it trips', text)


def aside(phase, attempt, reason, provider, kind='failed_exit'):
    return {'phase': phase, 'attempt': attempt, 'reason': reason, 'crash_evidence_kind': kind if reason == 'crashed' else None,
            'usage': [], 'provider': provider}


OK_ROW = {'request_id': 'a', 'status': 'end_turn', 'message_id': 'm'}


class BlocksSetAside(unittest.TestCase):
    """Ruling 39, points 3 and 4."""

    def test_fault_of_reads_the_rows_as_the_driver_does(self):
        fail = {'status': 'failed', 'error': 'APIStatusError', 'http_status': 529}
        self.assertEqual(A.fault_of([OK_ROW, fail]), ('APIStatusError', 529))
        self.assertEqual(A.fault_of([OK_ROW, {'status': 'timed_out'}]), ('timed_out', None))
        self.assertEqual(A.fault_of([{'status': 'copied', 'message_id': 'm'}]), ('RepeatedMessageId', None))
        self.assertEqual(A.fault_of([{'status': 'failed', 'error': 'APIConnectionError', 'http_status': None}]), ('APIConnectionError', None))
        # an empty reply or a refusal is a used slot, not a fault
        self.assertIsNone(A.fault_of([{'status': 'failed', 'stop_reason': 'refusal'}, {'status': 'refusal'}, {'status': 'max_tokens'}]))
        self.assertIsNone(A.fault_of([]))
        # the last fault row decides
        self.assertEqual(A.fault_of([fail, {'status': 'timed_out'}, OK_ROW]), ('timed_out', None))

    def snap(self):
        def hook(s):
            s['set_aside_learning'] += [
                aside('learn3-reach-b0', 1, 'crashed', [OK_ROW, {'status': 'failed', 'error': 'APIStatusError', 'http_status': 529}]),
                aside('learn3-reach-b1', 1, 'crashed', [{'status': 'failed', 'error': 'APIStatusError', 'http_status': 529}]),
                aside('learn3-land-b2', 1, 'crashed', [{'status': 'failed', 'error': 'APIStatusError', 'http_status': 500}]),
                aside('learn3-land-b3', 1, 'crashed', [{'status': 'timed_out'}]),
                aside('learn3-reach3d-b0', 1, 'crashed', [OK_ROW], kind='no_scheduler_no_end'),
                aside('learn3-reach3d-b0', 2, 'late', [OK_ROW]),
            ]
        return make(blocks=2, extra=hook)

    def test_counts_by_reason_kind_and_http_status(self):
        r = run(self.snap())['learning_blocks_set_aside']
        self.assertEqual(r['blocks'], 6)
        self.assertEqual(r['by_reason'], {'crashed': 5, 'late': 1})
        self.assertEqual(r['by_crash_evidence'], {'failed_exit': 4, 'no_scheduler_no_end': 1})
        self.assertEqual(r['stopped_by_a_fault'], {'blocks': 4, 'by_kind_and_http_status': {
            'APIStatusError, HTTP 529': 2, 'APIStatusError, HTTP 500': 1, 'timed_out, no HTTP status in the record': 1}})
        self.assertEqual(r['without_a_fault_in_the_provider_log'], 2)
        self.assertEqual(r['list'][4], {'phase': 'learn3-reach3d-b0', 'attempt': 1, 'reason': 'crashed', 'fault': None})

    def test_a_cost_that_is_not_known_is_said_so(self):
        def hook(snap):
            for learn in snap['learning']['reach'].values():
                learn['usage'][0]['list_cost_usd'] = None
        text = '\n'.join(A.report_lines(run(make(blocks=2, extra=hook))))
        self.assertIn('calls, not known.', text)
        self.assertNotIn('US$none', text)

    def test_none_set_aside(self):
        r = run(make(blocks=2))['learning_blocks_set_aside']
        self.assertEqual((r['blocks'], r['stopped_by_a_fault']['blocks']), (0, 0))
        self.assertIn('Learning blocks set aside and flown again: 0.', '\n'.join(A.report_lines(run(make(blocks=2)))))

    def test_the_report_gives_the_counts(self):
        text = '\n'.join(A.report_lines(run(self.snap())))
        self.assertIn('Learning blocks set aside and flown again: 6 (crashed 5, late 1).', text)
        self.assertIn('- APIStatusError, HTTP 529: 2', text)
        self.assertIn('Stopped by a fault of the model service (the provider\'s log ends in one): 4.', text)
        json.dumps(run(self.snap()), allow_nan=False)


def scored_snapshot():
    """A snapshot that says it is not a pilot, with the seeds in the shape of the scored book."""
    snap = make(blocks=2)
    snap['pilot'] = False
    snap['seeds'] = snap['seeds']['pilot']
    return snap


class RunOnce(unittest.TestCase):
    """Ruling 39, point 5."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'run'
        self.root.mkdir()
        self.out = Path(self.temp.name) / 'analysis'

    def gate(self, ok=True):
        from unittest import mock
        report = {'ok': ok, 'errors': [] if ok else ['broken'], 'pilot': False}
        return mock.patch('protocol.validate3.load_run', lambda *a, **k: (report, scored_snapshot() if ok else None))

    def test_the_record_holds_time_hashes_and_output_folder(self):
        path = A.write_run_record(self.root, self.out, C.BOOT_N, C.BOOT_SEED)
        self.assertEqual(path, self.root / A.RUN_RECORD)
        record = json.loads(path.read_text())
        self.assertEqual(set(record), {'time', 'analysis_sources_sha256', 'output_folder', 'resamples', 'seed'})
        self.assertEqual((record['resamples'], record['seed']), (C.BOOT_N, C.BOOT_SEED))       # G3
        self.assertEqual(record['analysis_sources_sha256'], A.analysis_sources_sha256())
        self.assertEqual(set(record['analysis_sources_sha256']), {'analysis3.py', 'validate3.py', 'contract3.py'})
        self.assertEqual(record['output_folder'], str(self.out.resolve()))
        self.assertRegex(record['time'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d')

    def test_a_second_record_is_refused_and_the_first_is_kept(self):
        A.write_run_record(self.root, self.out)
        first = (self.root / A.RUN_RECORD).read_text()
        with self.assertRaises(FileExistsError):
            A.write_run_record(self.root, Path(self.temp.name) / 'another')
        self.assertEqual((self.root / A.RUN_RECORD).read_text(), first)

    def test_a_scored_run_is_analysed_once(self):
        with self.gate():
            result = A.analyse(self.root, pilot=False, out=self.out)
            self.assertEqual(result['status'], 'protocol3 scored analysis')
            self.assertTrue((self.root / A.RUN_RECORD).is_file())
            self.assertEqual(json.loads((self.root / A.RUN_RECORD).read_text())['analysis_sources_sha256'], result['analysis_sources_sha256'])
            with self.assertRaises(FileExistsError) as caught:
                A.analyse(self.root, pilot=False, out=Path(self.temp.name) / 'second')
            self.assertIn('analysed once', str(caught.exception))

    def test_the_refusal_comes_before_the_gate_opens_anything(self):
        A.write_run_record(self.root, self.out)
        from unittest import mock
        with mock.patch('protocol.validate3.load_run') as gate:
            with self.assertRaises(FileExistsError):
                A.analyse(self.root, pilot=False, out=self.out)
            gate.assert_not_called()

    def test_a_gate_that_refuses_writes_no_record(self):
        with self.gate(ok=False):
            with self.assertRaises(ValueError):
                A.analyse(self.root, pilot=False, out=self.out)
        self.assertFalse((self.root / A.RUN_RECORD).exists())

    def test_a_scored_analysis_needs_its_output_folder(self):
        with self.gate():
            with self.assertRaises(ValueError):
                A.analyse(self.root, pilot=False)
        self.assertFalse((self.root / A.RUN_RECORD).exists())

    def test_a_pilot_is_not_limited_and_writes_no_record(self):
        from unittest import mock
        report = {'ok': True, 'errors': [], 'pilot': True}
        with mock.patch('protocol.validate3.load_run', lambda *a, **k: (report, make(blocks=2))):
            for _ in range(2):
                A.analyse(self.root, pilot=True, n_boot=30)
            (self.root / A.RUN_RECORD).write_text('{}')          # even a record from elsewhere does not stop a pilot
            A.analyse(self.root, pilot=True, n_boot=30)
        self.assertEqual((self.root / A.RUN_RECORD).read_text(), '{}')

    def test_the_command_line_runs_once_and_writes_its_files(self):
        from unittest import mock
        with self.gate(), mock.patch('sys.argv', ['analysis3.py', str(self.root), '--out', str(self.out)]):
            A.main()
            self.assertTrue((self.out / 'report.md').is_file())
            json.loads((self.out / 'analysis.json').read_text())
            with self.assertRaises(FileExistsError):
                A.main()             # the output folder exists
            with mock.patch('sys.argv', ['analysis3.py', str(self.root), '--out', str(Path(self.temp.name) / 'again')]):
                with self.assertRaises(FileExistsError) as caught:
                    A.main()
            self.assertIn('analysed once', str(caught.exception))


if __name__ == '__main__':
    unittest.main()

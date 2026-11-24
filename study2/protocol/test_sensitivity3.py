"""Tests of sensitivity3.py (rulings 78, 80 and 81). Hand-made snapshots of the shape validate3.load_run returns, built by
test_analysis_e2_3.make, stand in for the gate's; no flight, model or network is involved. Seeds used are 7100 and up."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import analysis3 as A
from protocol import contract3 as C
from protocol import sensitivity3 as S
from protocol import test_analysis_e2_3 as E2

N = 40
ADOPT = {'A': 'c0', 'B': 'c0', 'C': 'c0', 'D': 'c1'}      # A, B and C fly c0's source, D flies c1's


def adopt(t, b):
    return ADOPT


def row(flight, kept=True, attempt=3):
    return {'flight': flight, 'attempt': attempt, 'kept_late': kept}


def off_steps(lag=0.2):
    """Two steps whose command went out at other than the third telemetry stamp: two off-stamp commands."""
    return [{**s, 'command_lag_s': lag} for s in E2.steps(n=2)]


def make(blocks=3, timing=None, extra=None, **kw):
    return E2.make(blocks=blocks, seed=5, adopt=adopt, timing=timing, extra=extra, **kw)


def c0_source(snap, task='reach', block=0):
    return snap['learning'][task][block]['candidates']['c0']['source_sha256']


def c1_source(snap, task='reach', block=0):
    return snap['learning'][task][block]['candidates']['c1']['source_sha256']


def only_timing(task, block, rows):
    return lambda t, b: list(rows) if (t, b) == (task, block) else None


def aside(phase, attempt, reason, kind, candidates=(), provider=()):
    """A set-aside learning attempt as the gate hands it over. It carries nothing but the receipt's reason and crash
    evidence and the call records: a read of any other field raises KeyError."""
    return {'phase': phase, 'attempt': attempt, 'reason': reason, 'crash_evidence_kind': kind,
            'usage': [{'call_id': f'{phase}-{c}', 'candidate_id': c} for c in candidates],
            'provider': [{'request_id': json.dumps(['ardupilot-x', f"{phase.split('learn3-')[1]}-{c}", 'gem', 'm', 'build/attempt1', 1]),
                          'status': 'end_turn'} for c in provider]}


class Empty(unittest.TestCase):
    def setUp(self):
        self.snap = make()
        self.result = S.sensitivity(self.snap, n_boot=N)

    def test_every_list_is_empty_and_nothing_is_computed(self):
        r = self.result
        self.assertTrue(r['kept_late_learning']['list']['empty'])
        self.assertTrue(r['reflown_learning_blocks']['list']['empty'])
        self.assertIsNone(r['kept_late_learning']['fills'])
        self.assertIsNone(r['reflown_learning_blocks']['fills'])
        self.assertNotIn('primary_as_recorded', r)
        self.assertIn('empty', r['kept_late_learning']['statement'])
        self.assertEqual(r['reflown_learning_blocks']['list']['set_aside_attempts'], 0)

    def test_every_off_stamp_count_is_zero_and_the_rule_holds(self):
        off = self.result['off_stamp_commands']
        self.assertEqual(off['breach_count'], 0)
        self.assertEqual(off['flights_kept_late_in_the_arm_groups'], 0)
        for arm in C.ARMS:
            for g in S.GROUPS:
                self.assertEqual(off['by_arm'][arm][g]['off_deadline_commands'], 0)
        self.assertGreater(off['flights_checked_for_zero_off_stamp_commands'], 0)

    def test_the_report_says_so(self):
        text = '\n'.join(S.report_lines(self.result))
        self.assertIn('The list is empty and nothing is computed.', text)
        self.assertIn('The rule held in all of them.', text)

    def test_the_cells_are_the_analysis_cells(self):
        task_data, source, order = S.cell_data(self.snap)
        mine = A.primary_pass(task_data, C.BOOT_SEED, N)['primary']
        theirs = A.analyse_snapshot(self.snap, n_boot=N)['primary']
        self.assertEqual(set(mine), set(theirs))
        for k in theirs:
            self.assertEqual(mine[k]['estimate'], theirs[k]['estimate'], k)
            self.assertEqual(mine[k]['ci95'], theirs[k]['ci95'], k)
            self.assertEqual(mine[k]['classification'], theirs[k]['classification'], k)


class OffStamp(unittest.TestCase):
    def test_a_kept_late_zone_flight_with_off_stamp_commands_is_summed_for_the_arm_that_flew_it(self):
        probe = make()
        h = c1_source(probe)
        cases = [c.episode_id for c in C.evaluation_cases(probe['seeds'], 'reach', True)][:2]

        def extra(snap):
            for e in cases:
                snap['hazard'][('reach', 0, h)][e]['native_steps'] = off_steps()
        snap = make(extra=extra, kept_late={('threat3', 'reach', 0, h): cases})
        off = S.sensitivity(snap, n_boot=N)['off_stamp_commands']
        d = off['by_arm']['D']['evaluation_hazard']
        self.assertEqual((d['flights_kept_late'], d['off_deadline_commands']), (2, 4))
        for arm in 'ABC':
            self.assertEqual(off['by_arm'][arm]['evaluation_hazard']['off_deadline_commands'], 0)
        self.assertEqual(off['breach_count'], 0)

    def test_an_off_stamp_command_in_a_flight_not_kept_late_is_a_breach(self):
        probe = make()
        h = c0_source(probe)
        e = C.evaluation_cases(probe['seeds'], 'reach', True)[0].episode_id

        def extra(snap):
            snap['hazard'][('reach', 0, h)][e]['native_steps'] = off_steps()
        result = S.sensitivity(make(extra=extra), n_boot=N)
        off = result['off_stamp_commands']
        self.assertEqual(off['breach_count'], 1)
        self.assertEqual(off['breaches'][0]['flight'], e)
        self.assertEqual(off['breaches'][0]['off_deadline_commands'], 2)
        self.assertEqual(off['breaches'][0]['group'], 'evaluation_hazard')
        self.assertIn('BROKEN', '\n'.join(S.report_lines(result)))
        # nothing was kept late, so the by-arm sums are still zero
        self.assertEqual(off['totals_by_group']['evaluation_hazard']['off_deadline_commands'], 0)

    def test_learning_trial_and_retention_flights_and_the_first_round_lists(self):
        probe = make()
        h = c1_source(probe)
        r = C.retention_cases(probe['seeds'], 'reach', True)[0].episode_id

        def extra(snap):
            snap['learning']['reach'][0]['flights']['flights/trial/c1/D']['x0']['native_steps'] = off_steps()
            snap['retention'][('reach', 0, h)][r]['native_steps'] = off_steps()
            snap['learning']['reach'][0]['flights']['flights/first/P1'] = {'p0': E2.flight(1, native_steps=off_steps())}
        snap = make(extra=extra, kept_late={('retain3', 'reach', 0, h): [r]},
                    timing=only_timing('reach', 0, [row('flights/trial/c1/D/x0'), row('flights/first/P1/p0')]))
        off = S.sensitivity(snap, n_boot=N)['off_stamp_commands']
        self.assertEqual(off['by_arm']['D']['learning_trials']['off_deadline_commands'], 2)
        self.assertEqual(off['by_arm']['D']['evaluation_retention']['off_deadline_commands'], 2)
        self.assertEqual(off['first_round_flights_outside_the_arm_groups']['off_deadline_commands'], 2)
        self.assertEqual(off['breach_count'], 0)


class KeptLateLearning(unittest.TestCase):
    def test_a_trial_that_decided_an_adoption_lists_its_arm_block(self):
        snap = make(timing=only_timing('reach', 1, [row('flights/trial/c1/D/x0')]))
        r = S.sensitivity(snap, n_boot=N)
        calls = r['kept_late_learning']['list']['calls_kept_late']
        self.assertEqual(len(calls), 1)
        self.assertEqual({k: calls[0][k] for k in ('task', 'block', 'arm', 'call', 'candidate_id')},
                         {'task': 'reach', 'block': 1, 'arm': 'D', 'call': 'flights/trial/c1/D', 'candidate_id': 'c1'})
        self.assertIn('adoption', calls[0]['role'])
        self.assertEqual(r['kept_late_learning']['list']['arm_blocks'], [{'task': 'reach', 'block': 1, 'arm': 'D'}])
        self.assertIsNone(r['reflown_learning_blocks']['fills'])
        self.assertIsNotNone(r['kept_late_learning']['fills'])

    def test_a_first_round_call_kept_late_touches_a_b_and_c_for_p0_and_d_for_p1(self):
        for call, arms in (('flights/first/P0', ['A', 'B', 'C']), ('flights/first/P1', ['D'])):
            with self.subTest(call=call):
                snap = make(timing=only_timing('land', 0, [row(call + '/x0')]))
                calls = S.learning_list(snap)['calls_kept_late']
                self.assertEqual([c['arm'] for c in calls], arms)
                self.assertEqual({(c['task'], c['block'], c['call']) for c in calls}, {('land', 0, call)})
                self.assertIn('first-round', calls[0]['role'])

    def test_a_trial_two_arms_share_touches_both(self):
        def extra(snap):
            for t in C.TASKS:
                for b, learn in snap['learning'][t].items():
                    arms = learn['arms_record']['arms']
                    arms['C']['trials'][0]['flight_dir'] = arms['B']['trials'][0]['flight_dir']
        snap = make(extra=extra, timing=only_timing('reach', 0, [row('flights/trial/c0/B/x0')]))
        self.assertEqual([c['arm'] for c in S.learning_list(snap)['calls_kept_late']], ['B', 'C'])

    def test_a_call_set_aside_and_replaced_on_time_is_not_listed(self):
        rows = [{'flight': 'late/flights/first/P0/attempt-1/x0', 'set_aside_from': 'flights/first/P0/x0', 'attempt': 1},
                {'flight': 'flights/first/P0/x0', 'attempt': 2, 'late': False}]
        self.assertTrue(S.learning_list(make(timing=only_timing('reach', 0, rows)))['empty'])

    def test_a_fill_moves_a_contrast_in_the_stated_direction_and_leaves_shared_sources_unchanged(self):
        # D (c1's source) is touched in reach block 1. The cells in every block are random but fixed by the seed.
        snap = make(blocks=4, timing=only_timing('reach', 1, [row('flights/trial/c1/D/x0')]))
        f = S.sensitivity(snap, n_boot=N)
        done, recorded = f['kept_late_learning']['fills'], f['primary_as_recorded']
        for key in ('reach:D-A:close', 'reach:D-A:middle-wide', 'pooled:D-C'):
            lo, hi, rec = (done['primary_under_lower_fill'][key]['estimate'], done['primary_under_upper_fill'][key]['estimate'],
                           recorded[key]['estimate'])
            self.assertLessEqual(lo, rec + 1e-12, key)
            self.assertGreaterEqual(hi, rec - 1e-12, key)
        # the upper fill sets all six of D's cells in reach block 1 to 1, the lower fill to 0
        y, cases = E2.rebuild_y(snap, 'reach')
        z = y.copy()
        z[3, 1, :] = 1
        close = [i for i, c in enumerate(cases) if 'close' in c.episode_id]
        self.assertAlmostEqual(done['primary_under_upper_fill']['reach:D-A:close']['estimate'],
                               z[3][:, close].mean() - z[0][:, close].mean(), places=9)
        z[3, 1, :] = 0
        self.assertAlmostEqual(done['primary_under_lower_fill']['reach:D-A:close']['estimate'],
                               z[3][:, close].mean() - z[0][:, close].mean(), places=9)
        # contrasts that do not read D, and tasks that nothing touched, are as recorded
        for key in ('pooled:B-A', 'pooled:C-B'):
            for label in ('primary_under_lower_fill', 'primary_under_upper_fill'):
                self.assertEqual(done[label][key]['estimate'], recorded[key]['estimate'], key)
        for key in ('reach3d:D-A:close', 'land:D-A:middle-wide'):
            self.assertEqual(done['primary_under_upper_fill'][key]['estimate'], recorded[key]['estimate'], key)

    def test_arms_sharing_a_source_in_the_block_are_each_filled_on_their_own(self):
        # P0 is flown by A, B and C, which all adopted c0's source in the block. A listed block's learning might have gone
        # otherwise, so the three are not cancelled against each other: B - A and C - B move under the fills, in the
        # stated direction, and the lower fill of B - A sets B's cells in the block to 0 and A's to 1.
        snap = make(blocks=4, timing=only_timing('reach', 2, [row('flights/first/P0/x0')]))
        f = S.sensitivity(snap, n_boot=N)
        done, recorded = f['kept_late_learning']['fills'], f['primary_as_recorded']
        for key in ('pooled:B-A', 'pooled:C-B'):
            lo, hi, rec = (done['primary_under_lower_fill'][key]['estimate'], done['primary_under_upper_fill'][key]['estimate'],
                           recorded[key]['estimate'])
            self.assertLess(lo, rec, key)
            self.assertGreater(hi, rec, key)
        task_data, source, order = S.cell_data(snap)
        self.assertEqual(source['reach'][1][order['reach'].index(2)], source['reach'][0][order['reach'].index(2)])
        self.assertEqual(done['cells_set'], 3 * 6)        # A, B and C in reach block 2, 6 scenarios each
        # D - C still moves: C is touched and D is not
        self.assertLess(done['primary_under_lower_fill']['pooled:D-C']['estimate'], recorded['pooled:D-C']['estimate'])
        self.assertGreater(done['primary_under_upper_fill']['pooled:D-C']['estimate'], recorded['pooled:D-C']['estimate'])

    def test_the_six_d_minus_a_primaries_share_one_pair_of_fills(self):
        snap = make(blocks=4, timing=only_timing('reach', 1, [row('flights/trial/c1/D/x0')]))
        done = S.sensitivity(snap, n_boot=N)['kept_late_learning']['fills']
        self.assertEqual(done['cells_set'], 6)         # 6 scenarios of reach's block 1 for arm D
        self.assertEqual(len([k for k in done['primary_under_lower_fill'] if ':D-A:' in k]), 6)

    def test_a_contrast_that_does_not_read_the_touched_arm_keeps_its_interval(self):
        # D is touched in land block 0; C - B does not read D
        snap = make(blocks=3, timing=only_timing('land', 0, [row('flights/trial/c1/D/x0')]))
        f = S.sensitivity(snap, n_boot=N)
        for label in ('primary_under_lower_fill', 'primary_under_upper_fill'):
            self.assertEqual(f['kept_late_learning']['fills'][label]['pooled:C-B']['ci95'], f['primary_as_recorded']['pooled:C-B']['ci95'])


class ReflownBlocks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'run'

    def folders(self, items, slots=None, missing=()):
        """The set-aside folders beside the run root: one candidates/ folder for each attempt, holding a slot folder with a
        request.json for each name in slots[(phase, attempt)]. An attempt in `missing` has no folder at all."""
        for it in items:
            key = (it['phase'], it['attempt'])
            if key in missing:
                continue
            c = self.root.parent / f'{self.root.name}.set-aside' / f"{it['phase']}-attempt{it['attempt']}" / 'candidates'
            c.mkdir(parents=True, exist_ok=True)
            for name in (slots or {}).get(key, ()):
                (c / name).mkdir(exist_ok=True)
                (c / name / 'request.json').write_text('{}')

    def snap(self, items, slots=None, missing=(), **kw):
        self.folders(items, slots, missing)
        return make(blocks=3, extra=lambda s: s.update(set_aside_learning=items, root=str(self.root)), **kw)

    def test_a_block_set_aside_for_a_fault_after_a_fresh_draw_request_is_listed(self):
        r = S.sensitivity(self.snap([aside('learn3-reach-b0', 1, 'crashed', 'failed_exit', candidates=['c0', 'c1', 'f1'])]), n_boot=N)
        lst = r['reflown_learning_blocks']['list']
        self.assertFalse(lst['empty'])
        self.assertEqual([(b['task'], b['block']) for b in lst['affected_blocks']], [('reach', 0)])
        self.assertEqual(lst['affected_blocks'][0]['attempts'][0]['cause'], 'fault')
        self.assertEqual(lst['affected_blocks'][0]['attempts'][0]['fresh_or_repair_requests'], ['f1'])
        self.assertEqual(lst['set_aside_attempts_by_reason'], {'crashed': 1})
        self.assertEqual(lst['set_aside_attempts_by_cause'], {'fault': 1})
        self.assertIsNone(r['kept_late_learning']['fills'])
        done = r['reflown_learning_blocks']['fills']
        self.assertEqual(done['cells_set'], 4 * 6)      # all four arms of the block
        # the lists are never combined: nothing is in the other list's fills
        self.assertTrue(r['kept_late_learning']['list']['empty'])

    def test_a_block_set_aside_before_any_such_request_is_counted_but_not_listed(self):
        r = S.sensitivity(self.snap([aside('learn3-reach-b0', 1, 'crashed', 'failed_exit', candidates=['c0', 'c1']),
                                     aside('learn3-land-b1', 1, 'crashed', 'no_scheduler_no_end', candidates=[])]), n_boot=N)
        lst = r['reflown_learning_blocks']['list']
        self.assertTrue(lst['empty'])
        self.assertEqual(lst['set_aside_attempts'], 2)
        self.assertEqual(lst['set_aside_attempts_by_cause'], {'fault': 1, 'dead job': 1})
        self.assertIsNone(r['reflown_learning_blocks']['fills'])
        self.assertEqual(lst['attempts_with_no_call_records'], 1)

    def test_a_block_lost_with_a_dead_job_is_listed_from_the_provider_rows_alone(self):
        # the request for the repair is in the provider's log only: the driver's row was never written
        r = S.sensitivity(self.snap([aside('learn3-land-b2', 1, 'crashed', 'no_scheduler_no_end', candidates=['c0'],
                                           provider=['c0', 'c1', 'rC1'])]), n_boot=N)
        lst = r['reflown_learning_blocks']['list']
        self.assertEqual([(b['task'], b['block']) for b in lst['affected_blocks']], [('land', 2)])
        a = lst['affected_blocks'][0]['attempts'][0]
        self.assertEqual((a['cause'], a['fresh_or_repair_requests']), ('dead job', ['rC1']))

    def test_two_attempts_of_one_block_are_one_affected_block_and_a_format_repair_is_not_a_fresh_request(self):
        r = S.reflown_list(self.snap([aside('learn3-reach-b1', 1, 'crashed', 'failed_exit', candidates=['c0', 'c0', 'c1']),
                                      aside('learn3-reach-b1', 2, 'crashed', 'failed_exit', candidates=['c0', 'rD1'])]))
        self.assertEqual([(b['block'], [a['attempt'] for a in b['attempts']]) for b in r['affected_blocks']], [(1, [2])])
        self.assertEqual(r['set_aside_attempts'], 2)

    def test_two_attempts_of_one_block_are_two_attempts_and_one_block(self):
        r = S.reflown_list(self.snap([aside('learn3-reach-b1', 1, 'crashed', 'failed_exit', candidates=['c0', 'f1']),
                                      aside('learn3-reach-b1', 2, 'crashed', 'failed_exit', candidates=['c0', 'rC1']),
                                      aside('learn3-land-b0', 1, 'late', None, candidates=['c0'])]))
        self.assertEqual(r['set_aside_attempts'], 3)
        self.assertEqual(r['distinct_blocks_with_any_set_aside_attempt'], 2)
        self.assertEqual(r['distinct_listed_blocks'], 1)
        self.assertEqual(r['listed_attempts_by_status'][S.STATUS_SENT], 2)

    def test_a_job_killed_during_a_fresh_request_leaves_a_request_file_and_no_row(self):
        items = [aside('learn3-reach-b0', 1, 'crashed', 'no_scheduler_no_end', candidates=['c0', 'c1'])]
        snap = self.snap(items, slots={('learn3-reach-b0', 1): ['c0', 'c1', 'f1']})
        r = S.sensitivity(snap, n_boot=N)
        lst = r['reflown_learning_blocks']['list']
        self.assertFalse(lst['empty'])
        a = lst['affected_blocks'][0]['attempts'][0]
        self.assertEqual((a['status'], a['request_files_with_no_row'], a['fresh_or_repair_requests']), (S.STATUS_NOT_ESTABLISHED, ['f1'], []))
        self.assertEqual(lst['listed_attempts_by_status'][S.STATUS_NOT_ESTABLISHED], 1)
        self.assertEqual(r['reflown_learning_blocks']['fills']['cells_set'], 4 * 6)
        text = '\n'.join(S.report_lines(r))
        self.assertIn('sending not established', text)
        self.assertNotIn('The list is empty', text.split('## Learning blocks set aside')[1])

    def test_a_job_killed_during_a_repair_request_is_the_same(self):
        items = [aside('learn3-land-b2', 1, 'crashed', 'failed_exit', candidates=['c0', 'c1', 'f1'], provider=['c0'])]
        # f1 has its row; the repair slot rC1 has a request file and no row
        r = S.reflown_list(self.snap(items, slots={('learn3-land-b2', 1): ['c0', 'c1', 'f1', 'rC1']}))
        a = r['affected_blocks'][0]['attempts'][0]
        self.assertEqual((a['status'], a['request_files_with_no_row']), (S.STATUS_SENT, ['rC1']))
        only = [aside('learn3-land-b2', 2, 'crashed', 'failed_exit', candidates=['c0', 'c1'])]
        r = S.reflown_list(self.snap(only, slots={('learn3-land-b2', 2): ['c0', 'c1', 'rD1']}))
        a = r['affected_blocks'][0]['attempts'][0]
        self.assertEqual((a['status'], a['request_files_with_no_row']), (S.STATUS_NOT_ESTABLISHED, ['rD1']))

    def test_no_request_file_for_a_fresh_or_repair_slot_means_not_listed(self):
        items = [aside('learn3-reach-b0', 1, 'crashed', 'failed_exit', candidates=['c0', 'c1'])]
        r = S.reflown_list(self.snap(items, slots={('learn3-reach-b0', 1): ['c0', 'c1']}))
        self.assertTrue(r['empty'])
        self.assertTrue(r['complete'])

    def test_request_files_are_never_opened(self):
        items = [aside('learn3-reach-b0', 1, 'crashed', 'failed_exit', candidates=['c0'])]
        snap = self.snap(items, slots={('learn3-reach-b0', 1): ['f1']})
        opened = []
        real = Path.open
        with mock.patch.object(Path, 'open', lambda self, *a, **k: (opened.append(str(self)), real(self, *a, **k))[1]), \
                mock.patch.object(Path, 'read_text', lambda self, *a, **k: opened.append(str(self))), \
                mock.patch.object(Path, 'read_bytes', lambda self, *a, **k: opened.append(str(self))):
            S.reflown_list(snap)
        self.assertEqual(opened, [])

    def test_an_attempt_whose_candidate_folders_are_missing_is_listed_for_all_four_arms_as_not_determinable(self):
        items = [aside('learn3-reach-b1', 1, 'crashed', 'no_scheduler_no_end', candidates=['c0'])]
        snap = self.snap(items, missing=[('learn3-reach-b1', 1)])
        r = S.sensitivity(snap, n_boot=N)
        lst = r['reflown_learning_blocks']['list']
        b = lst['affected_blocks'][0]
        self.assertEqual((b['task'], b['block'], b['arms'], b['attempts'][0]['status']), ('reach', 1, list(C.ARMS), S.STATUS_NOT_DETERMINABLE))
        self.assertFalse(b['attempts'][0]['candidate_folders_kept'])
        self.assertEqual(lst['listed_attempts_by_status'][S.STATUS_NOT_DETERMINABLE], 1)
        self.assertEqual(r['reflown_learning_blocks']['fills']['cells_set'], 4 * 6)

    def test_a_late_attempt_with_missing_folders_is_not_listed(self):
        items = [aside('learn3-reach-b1', 1, 'late', None, candidates=['c0'])]
        self.assertTrue(S.reflown_list(self.snap(items, missing=[('learn3-reach-b1', 1)]))['empty'])

    def test_an_attempt_that_cannot_be_placed_makes_the_list_incomplete_and_never_empty(self):
        items = [aside('learn3-reach-b9', 1, 'crashed', 'failed_exit', candidates=['c0']),
                 aside('learn3-nowhere-b0', 2, 'crashed', 'failed_exit', candidates=['c0', 'f1'])]
        r = S.sensitivity(self.snap(items), n_boot=N)
        lst = r['reflown_learning_blocks']['list']
        self.assertFalse(lst['complete'])
        self.assertFalse(lst['empty'])
        self.assertEqual([(u['phase'], u['attempt']) for u in lst['unplaced_attempts']], [('learn3-nowhere-b0', 2), ('learn3-reach-b9', 1)][::-1])
        self.assertFalse(r['reflown_learning_blocks']['complete'])
        self.assertNotIn('The list is empty', r['reflown_learning_blocks']['statement'])
        self.assertIn('INCOMPLETE', r['reflown_learning_blocks']['statement'])
        text = '\n'.join(S.report_lines(r))
        self.assertIn('INCOMPLETE', text)
        self.assertIn('learn3-reach-b9 attempt 1', text)
        self.assertNotIn('The list is empty', text.split('## Learning blocks set aside')[1])

    def test_an_unattributed_kept_late_call_makes_that_list_incomplete_and_never_empty(self):
        snap = make(blocks=3, timing=only_timing('reach', 0, [row('flights/trial/zz/D/x0')]))
        r = S.sensitivity(snap, n_boot=N)
        k = r['kept_late_learning']
        self.assertEqual([u['call'] for u in k['list']['unattributed_calls']], ['flights/trial/zz/D'])
        self.assertFalse(k['list']['complete'])
        self.assertFalse(k['list']['empty'])
        self.assertNotIn('The list is empty', k['statement'])
        self.assertIn('INCOMPLETE', k['statement'])
        text = '\n'.join(S.report_lines(r))
        self.assertIn('INCOMPLETE', text)
        self.assertIn('flights/trial/zz/D', text)
        self.assertNotIn('The list is empty', text.split('## Learning calls kept late')[1].split('## Learning blocks')[0])

    def test_a_complete_empty_list_may_say_it_is_empty(self):
        r = S.sensitivity(make(blocks=2), n_boot=N)
        self.assertTrue(r['kept_late_learning']['list']['complete'] and r['reflown_learning_blocks']['list']['complete'])

    def test_a_learning_block_set_aside_as_late_is_counted_and_not_listed(self):
        r = S.reflown_list(self.snap([aside('learn3-reach-b1', 1, 'late', None, candidates=['c0', 'f1'])]))
        self.assertTrue(r['empty'])
        self.assertEqual(r['set_aside_attempts_by_reason'], {'late': 1})

    def test_the_candidate_kinds(self):
        self.assertEqual([A.candidate_kind(c) for c in ('c0', 'c1', 'f1', 'rC1', 'rD2')], ['c0', 'c1', 'fresh', 'repair', 'repair'])
        self.assertEqual(S.candidate_of_request_id(json.dumps(['a', 'land-b0-f1', 'c'])), 'f1')
        self.assertIsNone(S.candidate_of_request_id('not json'))

    def test_the_two_lists_are_reported_separately(self):
        snap = make(blocks=3, timing=only_timing('reach', 1, [row('flights/trial/c1/D/x0')]),
                    extra=lambda s: s.update(set_aside_learning=[aside('learn3-land-b0', 1, 'crashed', 'failed_exit', candidates=['f2'])]))
        r = S.sensitivity(snap, n_boot=N)
        self.assertEqual(r['kept_late_learning']['fills']['cells_set'], 6)
        self.assertEqual(r['reflown_learning_blocks']['fills']['cells_set'], 24)
        text = '\n'.join(S.report_lines(r))
        self.assertIn('never combined', text)


class CommandLine(unittest.TestCase):
    def snapshot(self):
        return make(blocks=2)

    def run_main(self, out, args=('--pilot', '--n-boot', str(N))):
        with mock.patch('protocol.validate3.load_runs', return_value=({'ok': True, 'errors': []}, self.snapshot())), \
                mock.patch.object(sys, 'argv', ['sensitivity3.py', '/nowhere', '--out', str(out), *args]), \
                mock.patch('builtins.print'):
            S.main()

    def test_it_writes_one_json_file_and_one_table_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out'
            self.run_main(out)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ['sensitivity.json', 'sensitivity.md'])
            data = json.loads((out / 'sensitivity.json').read_text())
            self.assertEqual(data['bootstrap'], {'seed': C.BOOT_SEED, 'replicates': N})
            with self.assertRaises(FileExistsError):
                self.run_main(out)

    def test_a_scored_run_must_use_the_protocols_count_and_seed(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            self.run_main(Path(d) / 'out', args=('--n-boot', str(N)))
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            self.run_main(Path(d) / 'out', args=('--boot-seed', '1'))

    def test_a_failed_gate_gives_nothing(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch('protocol.validate3.load_runs', return_value=({'ok': False, 'errors': ['bad']}, None)):
            with self.assertRaisesRegex(ValueError, 'gate failed'):
                S.run(Path(d), pilot=True, n_boot=N)


if __name__ == '__main__':
    unittest.main()

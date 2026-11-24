"""Build E2: what the gate now hands to the analysis in its snapshot (nothing here loosens a check).

E2.4  call times, the learning flights read, timing.json rows, set-aside learning blocks, the gate's own report fields
E2.5  kept-late evaluation flights, and what each set-aside attempt of an evaluation phase flew

All records are synthetic pilot fixtures from test_protocol3.fixture and test_gate_e1_3's helpers. No model, simulator or
network is used.
"""
import json
import shutil
import unittest

from protocol import contract3 as C
from protocol import run_scored3 as R3
from protocol import test_gate_e1_3 as E1
from protocol import test_protocol3 as T
from protocol import validate3 as V


def setUpModule():
    T.setUpModule()


def tearDownModule():
    T.tearDownModule()


def load(root, kw):
    report, snapshot = V.load_run(root, **kw)
    return report, snapshot


class CallTimes(unittest.TestCase):
    def test_procedure_and_guard_wall_seconds_as_read_calls_reads_them(self):
        payloads = [{'kind': 'anchor'},
                    {'kind': 'decision', 'tried': [{'status': 'ok', 'wall_seconds': 0.04,
                                                    'checks': [{'wall_seconds': 0.02}, {'wall_seconds': 0.03}]}]},
                    {'kind': 'decision', 'tried': [{'wall_seconds': 0.05, 'checks': []}, {'wall_seconds': None}]},
                    {'kind': 'decision'}, {'kind': 'episode_end'}]
        self.assertEqual(V.call_times(payloads), {'procedure': [0.04, 0.05], 'guard': [0.02, 0.03]})

    def test_records_without_numbers_are_skipped_and_never_refused(self):
        junk = [{'kind': 'decision', 'tried': ['x', {'wall_seconds': True, 'checks': ['y', {'wall_seconds': 'a'}]}]},
                {'kind': 'decision', 'tried': None}, 'not a dict']
        self.assertEqual(V.call_times(junk), {'procedure': [], 'guard': []})


class SnapshotContents(unittest.TestCase):
    def test_every_flight_carries_call_times_and_the_learning_flights_are_kept(self):
        root, kw = E1.fresh(self)
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        for flights in list(snap['hazard'].values()) + list(snap['retention'].values()):
            for o in flights.values():
                self.assertEqual(o['_call_wall_s'], {'procedure': [], 'guard': []})   # the fixture's decisions have no `tried`
        for task, blocks in snap['learning'].items():
            learn = blocks[0]
            self.assertIn('flights/first/P0', learn['flights'])
            self.assertIn('flights/first/P1', learn['flights'])
            for row in learn['arms_record']['arms'].values():
                for trial in row['trials']:
                    if trial['flight_dir']:
                        self.assertEqual(set(learn['flights'][trial['flight_dir']]),
                                         {c.episode_id for c in C.learning_cases(snap['seeds'], task, 0, True, threat=trial['trial_list'] == 'threat')})
            self.assertIsNone(learn['timing'])

    def test_call_times_from_a_flights_decision_log_reach_the_snapshot(self):
        root, kw = E1.fresh(self)
        folder = sorted(root.glob('threat3-reach-b0-*'))[0]
        log = sorted((folder / 'flights').glob('*/episode.log'))[0]
        payloads = [json.loads(line)['payload'] for line in log.read_bytes().splitlines()][1:]   # without the anchor
        payloads.insert(0, {'kind': 'decision', 'tried': [{'wall_seconds': 0.041, 'checks': [{'wall_seconds': 0.039}]}]})
        T.protected_log(log, payloads)
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        source = folder.name.split('-')[-1]
        flights = snap['hazard'][('reach', 0, source)]
        self.assertEqual(flights[log.parent.name]['_call_wall_s'], {'procedure': [0.041], 'guard': [0.039]})
        self.assertTrue(all(o['_call_wall_s'] == {'procedure': [], 'guard': []} for k, o in flights.items() if k != log.parent.name))

    def test_timing_rows_of_a_block_are_kept(self):
        root, kw = E1.fresh(self)
        rows = [{'flight': 'flights/first/P0/matched-close-1', 'attempt': 1, 'late': False}]
        T.write_json(root / 'learn3-reach-b0' / 'timing.json', rows)
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(snap['learning']['reach'][0]['timing'], rows)
        self.assertIsNone(snap['learning']['land'][0]['timing'])

    def test_the_gates_own_report_fields_ride_in_the_snapshot(self):
        root, kw = E1.fresh(self)
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        g = snap['gate']
        self.assertEqual((g['repeated_message_ids'], g['rows_logged_as_copied']), (0, 0))
        self.assertEqual(g['spend_stop_in_protocol_usd'], R3.SPEND_LIMIT_USD_3)
        self.assertEqual(report['spend_stop_in_protocol_usd'], R3.SPEND_LIMIT_USD_3)
        self.assertIn('session_spend_stops', g)
        self.assertIn('kept_late_evaluation_flights', g)

    def test_a_refusal_still_gives_no_snapshot(self):
        root, kw = E1.fresh(self)
        (root / 'learn3-reach-b0' / 'arms.json').unlink()
        report, snap = load(root, kw)
        self.assertFalse(report['ok'])
        self.assertIsNone(snap)


class SetAsideLearningBlocks(unittest.TestCase):
    def aside(self, root, n, reason, rows, receipt=True, provider=True):
        from protocol.set_aside3 import set_aside_dir
        attempt = set_aside_dir(root) / f'learn3-reach-b0-attempt{n}'
        block = attempt / 'learn3-reach-b0'
        block.mkdir(parents=True)
        (block / 'usage.jsonl').write_text(''.join(json.dumps({'call_id': r['request_id'], 'list_cost_usd': 0.25}) + '\n' for r in rows))
        if provider:
            (block / 'claude-usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        if receipt:
            T.write_json(attempt / 'receipt.json', {'phase': 'learn3-reach-b0', 'attempt': n, 'reason': reason,
                                                    'crash_evidence': {'kind': 'failed_exit', 'log_lines': []}})
        return attempt

    def test_set_aside_learning_blocks_are_read_with_their_rows(self):
        root, kw = E1.fresh(self)
        failed = {'request_id': 'a1', 'status': 'failed', 'error': 'APIStatusError', 'http_status': 529}
        ok = {'request_id': 'a2', 'status': 'end_turn', 'message_id': 'msg_a2', 'charged_usd': 0.3}
        self.aside(root, 1, 'crashed', [ok, failed])
        self.aside(root, 2, 'late', [{'request_id': 'b1', 'status': 'end_turn', 'message_id': 'msg_b1'}])
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        a, b = snap['set_aside_learning']
        self.assertEqual((a['phase'], a['attempt'], a['reason'], a['crash_evidence_kind']), ('learn3-reach-b0', 1, 'crashed', 'failed_exit'))
        self.assertEqual(a['provider'], [ok, failed])
        self.assertEqual([r['list_cost_usd'] for r in a['usage']], [0.25, 0.25])
        self.assertEqual((b['attempt'], b['reason']), (2, 'late'))

    def test_a_receipt_that_cannot_be_read_gives_no_reason_and_no_refusal(self):
        root, kw = E1.fresh(self)
        attempt = self.aside(root, 1, 'crashed', [{'request_id': 'a1', 'status': 'end_turn', 'message_id': 'm1'}])
        (attempt / 'receipt.json').write_text('{not json')
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertIsNone(snap['set_aside_learning'][0]['reason'])

    def test_a_run_with_no_set_aside_folder_has_none(self):
        root, kw = E1.fresh(self)
        report, snap = load(root, kw)
        self.assertEqual(snap['set_aside_learning'], [])

    def test_the_same_repeated_message_id_check_still_covers_set_aside_blocks(self):
        root, kw = E1.fresh(self)
        E1.provider_log(root, via='anthropic')
        row = json.loads((root / 'learn3-reach-b0' / 'claude-usage.jsonl').read_text().splitlines()[0])
        self.aside(root, 1, 'crashed', [{**row, 'request_id': 'another call'}])
        report, snap = load(root, kw)
        self.assertFalse(report['ok'])
        self.assertEqual(report['repeated_message_ids'], 1)


class KeptLateAndSetAsideEvaluation(unittest.TestCase):
    """E2.5."""

    def test_a_phase_kept_late_is_in_the_snapshot_with_its_flights(self):
        root, kw = E1.fresh(self)
        folder, source, late = E1.keep_late(root, 'threat3')
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(snap['kept_late_eval'], {('threat3', 'reach', 0, source): [late]})

    def test_a_retention_phase_kept_late_is_under_retain3(self):
        root, kw = E1.fresh(self)
        folder, source, late = E1.keep_late(root, 'retain3')
        report, snap = load(root, kw)
        self.assertEqual(snap['kept_late_eval'], {('retain3', 'reach', 0, source): [late]})

    def test_nothing_kept_late_and_nothing_set_aside(self):
        root, kw = E1.fresh(self)
        report, snap = load(root, kw)
        self.assertEqual((snap['kept_late_eval'], snap['evaluation_attempts']), ({}, []))

    def test_every_set_aside_attempt_of_a_phase_is_read_with_its_cells(self):
        root, kw = E1.fresh(self)
        folder, source, late = E1.keep_late(root, 'threat3', attempts=2, crashed=1)
        from protocol.set_aside3 import set_aside_dir
        # attempt 1 flew one cell the other way
        flipped = sorted((set_aside_dir(root) / f'{folder.name}-attempt1' / folder.name / 'flights').glob('*/outcome.json'))[1]
        from protocol.test_gate_g_3 import set_ending
        set_ending(flipped, not json.loads(flipped.read_text())['goal_met'])       # the log's ending changed to match (G2)
        # attempt 3 (crashed) has only some of its flights
        gone = sorted((set_aside_dir(root) / f'{folder.name}-attempt3' / folder.name / 'flights').glob('*/outcome.json'))[:2]
        for path in gone:
            path.unlink()
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        attempts = [a for a in snap['evaluation_attempts'] if a['source'] == source and a['phase'] == 'threat3']
        self.assertEqual([(a['attempt'], a['reason']) for a in attempts], [(1, 'late'), (2, 'late'), (3, 'crashed')])
        kept = snap['hazard'][('reach', 0, source)]
        differ = [ep for ep, v in attempts[0]['cells'].items() if v is not None and v != kept[ep]['goal_met']]
        self.assertEqual(differ, [flipped.parent.name])
        self.assertTrue(all(v == kept[ep]['goal_met'] for ep, v in attempts[1]['cells'].items()))
        self.assertEqual(sorted(ep for ep, v in attempts[2]['cells'].items() if v is None), sorted(p.parent.name for p in gone))
        self.assertEqual(set(attempts[0]['cells']), set(kept))

    def test_a_phase_set_aside_and_flown_again_on_time_is_read_too(self):
        # the gate looks in the set-aside folder only for a phase with kept-late.json; this one has none
        root, kw = E1.fresh(self)
        folder = sorted(root.glob('threat3-reach-b0-*'))[0]
        E1.set_aside_attempt(root, folder.name, 1, reason='late', late=True)
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        (a,) = [a for a in snap['evaluation_attempts'] if a['source'] == folder.name.split('-')[-1] and a['phase'] == 'threat3']
        self.assertEqual((a['attempt'], a['reason'], snap['kept_late_eval']), (1, 'late', {}))

    def test_an_unreadable_receipt_or_outcome_is_shown_as_unread_and_not_refused(self):
        root, kw = E1.fresh(self)
        folder = sorted(root.glob('threat3-reach-b0-*'))[0]
        attempt = E1.set_aside_attempt(root, folder.name, 1, reason='late', late=True)
        (attempt / 'receipt.json').write_text('{not json')
        next(iter(sorted((attempt / folder.name / 'flights').glob('*/outcome.json')))).write_text('{not json')
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        (a,) = [a for a in snap['evaluation_attempts'] if a['source'] == folder.name.split('-')[-1] and a['phase'] == 'threat3']
        self.assertIsNone(a['reason'])
        self.assertEqual(sum(v is None for v in a['cells'].values()), 1)

    def test_the_snapshot_runs_through_the_analysis(self):
        from protocol import analysis3 as A
        root, kw = E1.fresh(self)
        folder, source, late = E1.keep_late(root, 'threat3')
        report, snap = load(root, kw)
        result = A.analyse_snapshot(snap, n_boot=50)
        self.assertEqual(result['kept_late_evaluation']['flights_by_phase'], {'threat3': 1})
        self.assertEqual(result['evaluation_phases_flown_again']['phases_flown_again'], 1)
        self.assertEqual(result['evaluation_phases_flown_again']['attempts_set_aside'], 2)
        json.dumps(result, allow_nan=False)


class StopsThroughTheGate(unittest.TestCase):
    """E2.6: the gate's session records reach the analysis."""

    def test_the_sessions_and_set_aside_faults_of_a_pilot_reach_the_report(self):
        from protocol import analysis3 as A
        root, kw = E1.fresh(self)
        T.write_json(root / 'logs' / 'schedule.json', {'pilot': True, 'learning': [[f'learn3-{t}-b0', []] for t in C.TASKS]})
        (root / 'logs' / 'pauses.jsonl').write_text(json.dumps(
            {'event': 'start', 'time': '2026-11-20 09:00:00', 'spend_limit_usd': 60.0, 'spend_limit_from_flag': False}) + '\n')
        SetAsideLearningBlocks().aside(root, 1, 'crashed', [{'request_id': 'a1', 'status': 'failed', 'error': 'APIStatusError', 'http_status': 529}])
        report, snap = load(root, kw)
        self.assertTrue(report['ok'], report['errors'])
        result = A.analyse_snapshot(snap, n_boot=50)
        self.assertEqual(result['spend_stops']['sessions'][0]['spend_limit_usd'], 60.0)
        self.assertIn('This is a pilot.', result['spend_stops']['statement'])
        self.assertEqual(result['learning_blocks_set_aside']['stopped_by_a_fault']['by_kind_and_http_status'], {'APIStatusError, HTTP 529': 1})
        self.assertIn('- APIStatusError, HTTP 529: 1', '\n'.join(A.report_lines(result)))


class RunRecordAndTheGate(unittest.TestCase):
    """E2.7: the record the analysis writes into the run root does not trouble the gate."""

    def test_the_gate_passes_with_the_record_present_and_a_pilot_analysis_writes_none(self):
        from protocol import analysis3 as A
        root, kw = E1.fresh(self)
        (root / A.RUN_RECORD).write_text(json.dumps({'time': 'x', 'analysis_sources_sha256': {}, 'output_folder': 'y'}))
        report = V.validate(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        before = sorted(p.name for p in root.iterdir())
        result = A.analyse(root, n_boot=30, **kw)
        self.assertEqual(sorted(p.name for p in root.iterdir()), before)
        self.assertEqual((len(result['primary']), len(result['secondary_intervals'])), (3, 6))


if __name__ == '__main__':
    unittest.main()

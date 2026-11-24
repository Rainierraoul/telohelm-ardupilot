"""Build G (rulings 49 to 51): fixes to the gate, found by the reviews of parts E1, E2, E3 and F.

G1  a kept-late marker and late timing rows name only scheduled cases; a set-aside attempt counts only for its scheduled flights
G2  every file the gate reads is in its record of input hashes; set-aside outcomes are checked against their episode logs
G6  provider rows and spending rows are paired across the run and the set-aside attempts
G7  a fragment in the run's file of message ids is skipped and counted

They use the gate's real fixture and the helpers of test_gate_e1_3. No model, simulator or network is used.
"""
import builtins
import io
import json
from pathlib import Path
import shutil
import unittest
from unittest import mock

from protocol import contract3 as C
from protocol import test_protocol3 as T
from protocol import test_gate_e1_3 as E
from protocol import validate3 as V
from protocol.set_aside3 import set_aside_dir


def setUpModule():
    T.setUpModule()


def tearDownModule():
    T.tearDownModule()


def set_ending(outcome_path, goal_met, outcome=True, log=True):
    """Change the goal_met of a flight's outcome and, as asked, of the episode_end in its protected log (the log is written
    again with its heads, as the fixture writes it)."""
    outcome_path = Path(outcome_path)
    if outcome:
        o = json.loads(outcome_path.read_text())
        o['goal_met'] = goal_met
        T.write_json(outcome_path, o)
    if log:
        path = outcome_path.parent / 'episode.log'
        payloads = [json.loads(line)['payload'] for line in path.read_text().splitlines()][1:]     # the first is the anchor
        for p in payloads:
            if p.get('kind') == 'episode_end':
                p['goal_met'] = goal_met
        T.protected_log(path, payloads)


class ScheduledLateFlights(unittest.TestCase):
    """G1."""

    def kept(self, **kw):
        root, gate = E.fresh(self)
        folder, source, late = E.keep_late(root, **kw)
        return root, gate, folder, late

    def refused(self, root, gate, text):
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'], 'the gate accepted it')
        self.assertIn(text, report['errors'][0])

    def test_the_existing_acceptance_is_unchanged(self):
        root, gate, folder, late = self.kept()
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['kept_late_evaluation_flights']['by_phase'], {'threat3': 1})

    def test_an_unscheduled_id_in_the_marker_and_the_timing_rows_is_refused(self):
        root, gate, folder, late = self.kept()
        rows = json.loads((folder / 'timing.json').read_text())
        T.write_json(folder / 'timing.json', rows + [{'flight': 'reach-not-scheduled-1', 'late': True, 'kept_late': True}])
        record = json.loads((folder / 'kept-late.json').read_text())
        record['kept_late_flights'].append('reach-not-scheduled-1')
        T.write_json(folder / 'kept-late.json', record)
        self.refused(root, gate, 'does not schedule')

    def test_an_unscheduled_id_in_the_timing_rows_alone_or_the_marker_alone_is_refused(self):
        root, gate, folder, late = self.kept()
        rows = json.loads((folder / 'timing.json').read_text())
        T.write_json(folder / 'timing.json', rows + [{'flight': 'reach-not-scheduled-1', 'late': True, 'kept_late': True}])
        self.refused(root, gate, 'does not schedule')
        root, gate, folder, late = self.kept()
        record = json.loads((folder / 'kept-late.json').read_text())
        record['kept_late_flights'].append('reach-not-scheduled-1')
        T.write_json(folder / 'kept-late.json', record)
        self.refused(root, gate, 'does not schedule')

    def test_a_late_row_that_is_not_marked_kept_late_and_is_unscheduled_is_refused_too(self):
        root, gate, folder, late = self.kept()
        rows = json.loads((folder / 'timing.json').read_text())
        T.write_json(folder / 'timing.json', rows + [{'flight': 'reach-not-scheduled-1', 'late': True}])
        self.refused(root, gate, 'does not schedule')

    def test_an_attempt_whose_late_flight_is_not_a_scheduled_case_is_not_counted(self):
        root, gate, folder, late = self.kept()
        flights = set_aside_dir(root) / f'{folder.name}-attempt1' / folder.name / 'flights'
        (flights / late).rename(flights / 'reach-not-scheduled-1')
        self.refused(root, gate, 'not 2')       # the phase was kept too early: one counted attempt, not two


class EveryReadIsHashed(unittest.TestCase):
    """G2."""

    def aside_run(self):
        root, gate = E.fresh(self)
        folder = sorted(root.glob('threat3-reach-b0-*'))[0]
        attempt = E.set_aside_attempt(root, folder.name, 1, reason='late', late=True)
        flights = sorted((attempt / folder.name / 'flights').glob('*/outcome.json'))
        return root, gate, folder, attempt, flights

    def test_a_changed_boolean_in_a_set_aside_outcome_is_refused_and_a_matching_log_changes_the_record(self):
        root, gate, folder, attempt, flights = self.aside_run()
        report, before = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        victim = flights[1]
        was = json.loads(victim.read_text())['goal_met']
        set_ending(victim, not was, log=False)
        report, _ = V.load_run(root, **gate)
        self.assertFalse(report['ok'])
        self.assertIn('disagrees with its protected episode ending', report['errors'][0])
        set_ending(victim, not was, outcome=False)       # the log changed to match
        report, after = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        key = f'run.set-aside/{attempt.name}/{folder.name}/flights/{victim.parent.name}/outcome.json'
        self.assertIn(key, before['input_sha256'])
        self.assertNotEqual(before['input_sha256'][key], after['input_sha256'][key])
        self.assertNotEqual(before['input_sha256'], after['input_sha256'])

    def test_the_same_check_covers_an_attempt_read_for_the_kept_late_rule(self):
        root, gate = E.fresh(self)
        folder, source, late = E.keep_late(root)
        victim = sorted((set_aside_dir(root) / f'{folder.name}-attempt1' / folder.name / 'flights').glob('*/outcome.json'))[1]
        set_ending(victim, not json.loads(victim.read_text())['goal_met'], log=False)
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'])
        self.assertIn('disagrees with its protected episode ending', report['errors'][0])

    def test_an_absent_or_unreadable_set_aside_outcome_stays_missing_and_is_counted_apart(self):
        from protocol import analysis3 as A
        root, gate, folder, attempt, flights = self.aside_run()
        flights[0].unlink()
        flights[1].write_text('{not json')
        report, snap = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        (a,) = [x for x in snap['evaluation_attempts'] if x['phase'] == 'threat3' and x['source'] == folder.name.split('-')[-1]]
        self.assertEqual(sum(v is None for v in a['cells'].values()), 2)
        counted = A.attempts_flown_again(snap)
        self.assertEqual(sum(v['cells_without_an_outcome'] for item in counted['phases'].values() for v in item), 2)

    def test_every_file_the_gate_opens_in_a_run_is_in_the_record_of_input_hashes(self):
        root, gate, folder, attempt, flights = self.aside_run()
        # a spending ledger, a provider ledger and a set-aside block with a receipt, a session record and a pause log
        E.provider_log(root, via='anthropic')
        T.write_json(root / 'logs' / 'schedule.json', {'pilot': True, 'learning': [[f'learn3-{t}-b0', []] for t in C.TASKS]})
        (root / 'logs' / 'pauses.jsonl').write_text(json.dumps(
            {'event': 'start', 'time': '2026-11-20 09:00:00', 'spend_limit_usd': 60.0, 'spend_limit_from_flag': False}) + '\n')
        learn = E.learn_folders(root)[0]
        block = set_aside_dir(root) / f'{learn.name}-attempt1'
        shutil.copytree(learn, block / learn.name)
        T.write_json(block / 'receipt.json', {'phase': learn.name, 'attempt': 1, 'reason': 'crashed'})
        opened = set()
        real = io.open
        def spy(file, mode='r', *a, **k):
            if isinstance(file, (str, Path)) and 'r' in mode and '+' not in mode:
                opened.add(Path(file).resolve())
            return real(file, mode, *a, **k)
        with mock.patch.object(io, 'open', spy), mock.patch.object(builtins, 'open', spy):
            report, snap = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        base, aside = root.resolve(), set_aside_dir(root).resolve()
        inside = {p for p in opened if p.is_file() and (p.is_relative_to(base) or p.is_relative_to(aside))}
        recorded = {(base / k) if not k.startswith('run.set-aside/') else (aside / k.split('/', 1)[1]) for k in snap['input_sha256']
                    if not k.startswith('@')}
        self.assertTrue(inside, 'the spy saw no file')
        self.assertEqual(sorted(str(p) for p in inside - recorded), [])
        for name in ('receipt.json', 'usage.jsonl', 'claude-usage.jsonl', 'schedule.json', 'pauses.jsonl'):
            self.assertTrue(any(k.endswith(name) for k in snap['input_sha256']), name)


class LedgerPairing(unittest.TestCase):
    """G6."""

    def aside_provider_rows(self, root, rows, attempt=1):
        learn = E.learn_folders(root)[0]
        folder = set_aside_dir(root) / f'{learn.name}-attempt{attempt}' / learn.name
        folder.mkdir(parents=True)
        (folder / 'claude-usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        return folder

    def row(self, n, **more):
        return {'request_id': f'killed-{n}', 'via': 'anthropic', 'model': 'synthetic-fixture', 'status': 'end_turn', 'cost_usd': 0.002,
                'message_id': f'msg_killed_{n}', 'charged_usd': None, **more}

    def test_ordinary_blocks_are_unaffected_and_report_none(self):
        root, gate = E.fresh(self)
        E.provider_log(root, via='anthropic')
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['provider_rows_with_no_spending_row'],
                         {'count': 0, 'list_cost_usd': 0.0, 'charged_usd': 0.0, 'rows_with_charge': 0, 'rows_without_list_cost': 0})

    def test_a_provider_row_with_no_spending_row_in_a_set_aside_attempt_is_counted_and_costed(self):
        root, gate = E.fresh(self)
        E.provider_log(root, via='anthropic')
        self.aside_provider_rows(root, [self.row(1), self.row(2, charged_usd=0.003)])
        report, snap = V.load_run(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['provider_rows_with_no_spending_row'],
                         {'count': 2, 'list_cost_usd': 0.004, 'charged_usd': 0.003, 'rows_with_charge': 1,
                          'rows_without_list_cost': 0})
        self.assertEqual(snap['gate']['provider_rows_with_no_spending_row']['count'], 2)

    def test_the_analysis_prints_the_count_and_adds_the_cost_to_the_set_aside_spend(self):
        from protocol import analysis3 as A
        root, gate = E.fresh(self)
        E.provider_log(root, via='anthropic')
        self.aside_provider_rows(root, [self.row(1), self.row(2)])
        report, snap = V.load_run(root, **gate)
        for tasks in snap['learning'].values():
            for learn in tasks.values():
                for usage_row in learn['usage']:
                    usage_row['list_cost_usd'] = 0.001            # the fixture's scripted calls have no price
        result = A.analyse_snapshot(snap, n_boot=30)
        spend = result['secondary']['spend']
        self.assertEqual(spend['learning_blocks_set_aside']['provider_rows_with_no_spending_row']['count'], 2)
        self.assertIsNotNone(spend['unique']['list_cost_usd'])
        self.assertAlmostEqual(spend['unique_plus_set_aside_list_cost_usd'], spend['unique']['list_cost_usd'] + 0.004, places=9)
        self.assertEqual(result['secondary']['message_ids_that_appear_more_than_once']['provider_rows_with_no_spending_row']['count'], 2)
        text = '\n'.join(A.report_lines(result))
        self.assertIn('Provider rows with no spending row', text)
        self.assertIn('2, list cost US$0.0040', text)

    def test_a_provider_row_with_no_spending_row_in_a_kept_block_is_refused(self):
        root, gate = E.fresh(self)
        E.provider_log(root, via='anthropic')
        learn = E.learn_folders(root)[0]
        with open(learn / 'claude-usage.jsonl', 'a') as f:
            f.write(json.dumps(self.row(1)) + '\n')
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'])
        self.assertIn('in a kept block have no spending row', report['errors'][0])

    def test_a_gateway_spending_row_with_no_provider_row_is_refused(self):
        root, gate = E.fresh(self)
        E.provider_log(root, via='gem')
        E.name_gateway(root)
        learn = E.learn_folders(root)[0]
        path = learn / 'usage.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0][C.SETTINGS_FIELD] = {'model': 'synthetic-fixture', 'via': 'gem'}
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.assertTrue(V.validate(root, **gate)['ok'])          # with its provider row, it is accepted
        E.rewrite_rows(learn, lambda provider: provider.pop(0))
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'])
        self.assertIn('on the gateway route have no provider row', report['errors'][0])
        self.assertEqual(report['provider_rows_with_no_spending_row']['count'], 0)       # reported even when it refuses

    def test_a_spending_row_on_the_direct_route_with_no_provider_row_is_not_refused(self):
        root, gate = E.fresh(self)
        E.provider_log(root, via='anthropic')
        E.rewrite_rows(E.learn_folders(root)[0], lambda provider: provider.pop(0))
        self.assertTrue(V.validate(root, **gate)['ok'])


class MessageIdFragments(unittest.TestCase):
    """G7. The finished-line and final-fragment test of E3.8 is replaced by these."""

    def gateway_run(self):
        root, gate = E.fresh(self)
        E.provider_log(root, via='gem')
        E.name_gateway(root)
        return root, gate

    def test_a_fragment_in_the_middle_of_the_file_is_counted_and_the_run_is_accepted(self):
        root, gate = self.gateway_run()
        path = root / 'message-ids.jsonl'
        lines = path.read_text().splitlines(keepends=True)
        # as claim() leaves it after a crash: a cut line, then the next claim on a new line
        path.write_text(''.join(lines[:2]) + '{"message_id": "msg_9999", "blo\n' + ''.join(lines[2:]))
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['message_id_file_fragments'], 1)

    def test_every_line_that_does_not_parse_is_counted_whether_in_the_middle_or_last(self):
        root, gate = self.gateway_run()
        path = root / 'message-ids.jsonl'
        good = path.read_text()
        path.write_text('not json\n' + good + '\n' + '{"message_id": "msg_9999", "blo')       # a first line, a blank line, a last fragment
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['message_id_file_fragments'], 3)
        path.write_text(good)
        self.assertEqual(V.validate(root, **gate)['message_id_file_fragments'], 0)

    def test_a_parsed_line_with_an_extra_key_or_the_wrong_shape_is_still_refused(self):
        root, gate = self.gateway_run()
        path = root / 'message-ids.jsonl'
        good = path.read_text().splitlines(keepends=True)
        first = json.loads(good[0])
        for bad in ({**first, 'extra': 1}, {'message_id': first['message_id']}, [first], {**first, 'message_id': 5}):
            with self.subTest(bad=bad):
                path.write_text(json.dumps(bad) + '\n' + ''.join(good[1:]))
                report = V.validate(root, **gate)
                self.assertFalse(report['ok'])
                self.assertIn('message-ids.jsonl', report['errors'][0])

    def test_an_id_on_two_lines_is_still_refused_even_beside_a_fragment(self):
        root, gate = self.gateway_run()
        path = root / 'message-ids.jsonl'
        text = path.read_text()
        path.write_text(text + '{"message_id": "ms\n' + text.splitlines()[0] + '\n')
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'])
        self.assertIn('more than once', report['errors'][0])

    def test_the_analysis_prints_the_count(self):
        from protocol import analysis3 as A
        root, gate = self.gateway_run()
        with open(root / 'message-ids.jsonl', 'a') as f:
            f.write('{"message_id": "msg_9')
        report, snap = V.load_run(root, **gate)
        result = A.analyse_snapshot(snap, n_boot=30)
        self.assertEqual(result['secondary']['message_ids_that_appear_more_than_once']['message_id_file_fragments'], 1)
        self.assertIn('cut short by a crash and skipped: 1.', '\n'.join(A.report_lines(result)))


if __name__ == '__main__':
    unittest.main()

"""Build E1 (ruling 37, point 9, and ruling 39, points 2 to 5): the gate's new checks.

E1.1  retention roles as the scheduler plans them and the driver records them
E1.2  a message id that appears twice, and a reply the provider logged as copied
E1.3  the gateway's settings and charge
E1.4  an evaluation phase kept late on its third attempt
E1.5  each session's spending stop
E1.6  the frozen values

All records are synthetic pilot fixtures from test_protocol3.fixture. No model, simulator or network is used.
"""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from protocol import contract3 as C
from protocol import freeze3 as F
from protocol import run_scored3 as R3
from protocol import test_protocol3 as T
from protocol import validate3 as V


def setUpModule():
    T.setUpModule()


def tearDownModule():
    T.tearDownModule()


def fresh(case, **kw):
    """A pilot fixture in a temporary folder, with the gate's arguments. Returns (root, kwargs)."""
    case.temp = tempfile.TemporaryDirectory(prefix='p3-e1-', dir='/private/tmp' if Path('/private/tmp').is_dir() else None)
    case.addCleanup(case.temp.cleanup)
    root = Path(case.temp.name) / 'run'
    return root, T.fixture(root, **kw)


class RetentionRoles(unittest.TestCase):
    """E1.1."""

    def test_a_block_where_arms_adopt_c0_passes_with_includes_c0_in_both_phases(self):
        root, kw = fresh(self)
        report = V.validate(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        for phase in ('threat3', 'retain3'):
            seen = []
            for folder in sorted(root.glob(f'{phase}-reach-b0-*')):
                a = json.loads((folder / 'manifest.json').read_text())['args']
                seen.append((a['arms'], a['includes_c0']))
            self.assertIn((['A', 'B', 'C'], True), seen, phase)
            self.assertIn((['D'], False), seen, phase)

    def test_the_old_expectation_for_a_retention_phase_of_c0_is_refused(self):
        root, kw = fresh(self)
        c0 = json.loads((root / 'learn3-reach-b0' / 'candidates' / 'c0' / 'candidate.json').read_text())['source_sha256']
        path = root / C.phase_name('retain3', 'reach', 0, c0) / 'manifest.json'
        m = json.loads(path.read_text())
        self.assertTrue(m['args']['includes_c0'])
        m['args']['includes_c0'] = False        # what the gate used to expect, and the driver never records
        T.write_json(path, m)
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])
        self.assertIn('wrong source, roles or evaluation schedule', report['errors'][0])

    def test_a_block_where_no_arm_adopts_has_threat3_for_c0_and_no_retain3(self):
        root, kw = fresh(self, nonadopt=True)
        report = V.validate(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(len(list(root.glob('retain3-*'))), 0)
        threat = sorted(root.glob('threat3-reach-b0-*'))
        self.assertEqual(len(threat), 1)
        args = json.loads((threat[0] / 'manifest.json').read_text())['args']
        self.assertEqual((args['arms'], args['includes_c0']), ([], True))

    def structures(self):
        """Arms and candidates of a block, as arms.json and candidate.json hold them: c0 valid or not."""
        h = lambda c: c * 64        # noqa: E731
        arm = lambda adopted, c: {'adopted': adopted, 'source_sha256': h(c) if adopted else None}      # noqa: E731
        def block(c0, a, b, c, d, c0_valid=True):
            return ({'A': a, 'B': b, 'C': c, 'D': d},
                    {'c0': {'format_valid': c0_valid, 'source_sha256': h(c0) if c0_valid else None}})
        return {
            'arms adopt c0': block('a', arm(True, 'a'), arm(True, 'a'), arm(False, 'a'), arm(True, 'b')),
            'no arm adopts': block('a', arm(False, 'a'), arm(False, 'a'), arm(False, 'a'), arm(False, 'a')),
            'only another source': block('a', arm(True, 'b'), arm(True, 'b'), arm(True, 'c'), arm(False, 'a')),
            'c0 not valid': block('a', arm(True, 'b'), arm(False, 'a'), arm(False, 'a'), arm(True, 'b'), c0_valid=False),
        }

    def test_the_gate_plans_the_phases_the_scheduler_does(self):
        for label, (arms, candidates) in self.structures().items():
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                learn = Path(tmp) / 'learn3-reach-b0'
                for name, record in candidates.items():
                    (learn / 'candidates' / name).mkdir(parents=True)
                    (learn / 'candidates' / name / 'candidate.json').write_text(json.dumps(record))
                (learn / 'arms.json').write_text(json.dumps({'task': 'reach', 'block': 0, 'arms': arms}))
                jobs = R3.evaluation_jobs(Path(tmp), [learn])
                plan = V.evaluation_plan(arms, candidates)
                gate = {C.phase_name(phase, 'reach', 0, h) for phase, sources in plan.items() for h in sources}
                self.assertEqual(gate, {name for name, _ in jobs})
                for phase, sources in plan.items():            # the roles the driver would record
                    for h, roles in sources.items():
                        c0 = candidates['c0']['source_sha256']
                        self.assertEqual(roles['includes_c0'], c0 == h)
                        self.assertEqual(roles['arms'], sorted(k for k, r in arms.items() if r['adopted'] and r['source_sha256'] == h))
                self.assertTrue(all(r['arms'] for r in plan['retain3'].values()))


CACHE = 'no-cache,no-store'


def learn_folders(root):
    return sorted(root.glob('learn3-*-b0'))


def provider_log(root, *, via='gem', charged=True, ids=None, folders=None, ids_file=True):
    """A provider log (claude-usage.jsonl) beside each block's usage.jsonl, one row for each of its calls, with message ids
    that differ unless ids names them. Returns the rows by block name."""
    made, n = {}, 0
    for learn in (folders or learn_folders(root)):
        rows = []
        for line in (learn / 'usage.jsonl').read_text().splitlines():
            call = json.loads(line)['call_id']
            n += 1
            row = {'request_id': call, 'via': via, 'model': 'synthetic-fixture', 'status': 'end_turn', 'cost_usd': 0.001,
                   'message_id': f'msg_{n:04d}', 'charged_usd': 0.0011 if charged and n % 2 else None}
            if via == 'gem':
                row['gateway_cache'] = CACHE
            rows.append(row)
        if ids:
            for row, mid in zip(rows, ids.get(learn.name, [])):
                row['message_id'] = mid
        (learn / 'claude-usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        made[learn.name] = rows
    if via == 'gem' and ids_file:     # E3.8: on the gateway route the provider's file of ids names every reply's id
        write_ids_file(root, made)
    return made


def write_ids_file(root, made):
    """ROOT/message-ids.jsonl as the provider writes it: one {message_id, block} line for each distinct id of the rows."""
    seen, lines = set(), []
    for block, rows in made.items():
        for row in rows:
            if row.get('message_id') is not None and row['message_id'] not in seen:
                seen.add(row['message_id'])
                lines.append(json.dumps({'message_id': row['message_id'], 'block': block}) + '\n')
    (root / 'message-ids.jsonl').write_text(''.join(lines))


def rewrite_rows(learn, change):
    path = learn / 'claude-usage.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    change(rows)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def name_gateway(root, **extra):
    """The requested settings of every call say the gateway route, as the driver writes them on it."""
    settings = {'model': 'synthetic-fixture', 'max_tokens': 64, 'via': 'gem', 'gateway_cache': CACHE, **extra}
    settings = {k: v for k, v in settings.items() if v is not None}
    for learn in learn_folders(root):
        for path in list((learn / 'candidates').glob('*/request.json')) + list((learn / 'candidates').glob('*/calls/*.json')):
            record = json.loads(path.read_text())
            record[C.SETTINGS_FIELD] = settings
            T.write_json(path, record)


class RepeatedMessageIds(unittest.TestCase):
    """E1.2."""

    def test_distinct_ids_pass_and_the_count_is_zero(self):
        root, kw = fresh(self)
        provider_log(root, via='anthropic')
        report = V.validate(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['repeated_message_ids'], 0)
        self.assertEqual(report['rows_logged_as_copied'], 0)

    def test_a_run_with_no_provider_log_has_no_repeats(self):
        root, kw = fresh(self)
        report = V.validate(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['repeated_message_ids'], 0)

    def test_an_id_that_two_blocks_share_is_refused(self):
        root, kw = fresh(self)
        first, second = learn_folders(root)[:2]
        provider_log(root, via='anthropic', ids={second.name: ['msg_0001']})
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])
        self.assertEqual(report['repeated_message_ids'], 1)
        self.assertIn('message ids appear for more than one call', report['errors'][0])

    def test_an_id_that_a_block_uses_twice_is_refused(self):
        root, kw = fresh(self)
        learn = learn_folders(root)[0]
        provider_log(root, via='anthropic')
        rewrite_rows(learn, lambda rows: rows[1].update(message_id=rows[0]['message_id']))
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])
        self.assertEqual(report['repeated_message_ids'], 1)

    def test_an_id_in_the_set_aside_folder_counts_with_the_run_root(self):
        root, kw = fresh(self)
        provider_log(root, via='anthropic')
        learn = learn_folders(root)[0]
        aside = root.parent / 'run.set-aside' / f'{learn.name}-attempt1' / learn.name
        aside.mkdir(parents=True)
        row = json.loads((learn / 'claude-usage.jsonl').read_text().splitlines()[0])
        row['request_id'] = 'an earlier attempt'
        (aside / 'claude-usage.jsonl').write_text(json.dumps(row) + '\n')
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])
        self.assertEqual(report['repeated_message_ids'], 1)
        # A different id in the set-aside folder is fine.
        row['message_id'] = 'msg_other'
        (aside / 'claude-usage.jsonl').write_text(json.dumps(row) + '\n')
        self.assertTrue(V.validate(root, **kw)['ok'])

    def test_the_runs_file_of_message_ids_in_the_run_root_does_not_trip_the_gate(self):
        """Build F1. The provider's file of message ids sits in the run root. The gate's sweeps of the run root (manifests,
        outcomes, requests, usage files, call receipts, protected logs) find nothing in it, and it is not a usage ledger."""
        root, kw = fresh(self)
        provider_log(root, via='anthropic')
        before = V.validate(root, **kw)
        (root / 'message-ids.jsonl').write_text(
            ''.join(json.dumps({'message_id': f'msg_{i:04d}', 'block': learn.name}) + '\n'
                    for i, learn in enumerate(learn_folders(root))))
        after = V.validate(root, **kw)
        self.assertTrue(after['ok'], after['errors'])
        self.assertEqual(after['repeated_message_ids'], before['repeated_message_ids'])
        self.assertEqual(after['message_ids_seen'], before['message_ids_seen'])

    def test_a_row_logged_as_copied_is_refused_even_when_its_id_is_new(self):
        root, kw = fresh(self)
        provider_log(root, via='anthropic')
        rewrite_rows(learn_folders(root)[0], lambda rows: rows[0].update(status='copied'))
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])
        self.assertEqual(report['rows_logged_as_copied'], 1)
        self.assertIn('logged as copied', report['errors'][0])
        self.assertEqual(report['repeated_message_ids'], 0)


class MessageIdFile(unittest.TestCase):
    """E3.8 (ruling 47, point 2): a copy that was caught is accepted in a set-aside learning attempt and counted; the provider's
    file of message ids is checked against the provider rows; the direct route has no file."""

    def gateway_run(self, **kw):
        root, gate = fresh(self, **kw)
        provider_log(root, via='gem')
        name_gateway(root)
        return root, gate

    def aside_attempt(self, root, rows, n=1, learn=None):
        learn = learn or learn_folders(root)[0]
        folder = root.parent / 'run.set-aside' / f'{learn.name}-attempt{n}' / learn.name
        folder.mkdir(parents=True)
        (folder / 'claude-usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        return folder

    def copy_of(self, root, status='copied', request_id='the copy'):
        first = json.loads((learn_folders(root)[0] / 'claude-usage.jsonl').read_text().splitlines()[0])
        return {**first, 'request_id': request_id, 'status': status}

    def refused(self, root, gate, text):
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'], 'the gate accepted it')
        self.assertIn(text, report['errors'][0])
        return report

    def test_a_sound_gateway_run_passes_and_reports_no_copies_and_no_unmatched_ids(self):
        root, gate = self.gateway_run()
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual((report['copies_caught'], report['message_ids_in_file_with_no_row'], report['repeated_message_ids']), (0, 0, 0))
        self.assertEqual(report['message_ids_seen'], 6)

    def test_a_caught_copy_in_a_set_aside_attempt_is_accepted_and_counted(self):
        root, gate = self.gateway_run()
        self.aside_attempt(root, [self.copy_of(root)])
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['copies_caught'], 1)
        self.assertEqual(report['repeated_message_ids'], 0)       # the copy shares an id with an answer, and is not counted as a repeat
        self.assertEqual(report['rows_logged_as_copied'], 1)

    def test_a_copy_is_counted_for_each_set_aside_attempt_it_is_in(self):
        root, gate = self.gateway_run()
        self.aside_attempt(root, [self.copy_of(root, request_id='a'), self.copy_of(root, request_id='b')])
        self.aside_attempt(root, [self.copy_of(root, request_id='c')], n=2)
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['copies_caught'], 3)

    def test_a_copied_row_in_a_kept_block_is_refused(self):
        root, gate = self.gateway_run()
        rewrite_rows(learn_folders(root)[0], lambda rows: rows[0].update(status='copied'))
        report = self.refused(root, gate, 'in the kept run are logged as copied')
        self.assertEqual((report['rows_logged_as_copied'], report['copies_caught']), (1, 0))

    def test_an_answered_row_in_a_set_aside_attempt_that_shares_an_id_is_still_refused(self):
        root, gate = self.gateway_run()
        self.aside_attempt(root, [self.copy_of(root, status='end_turn')])
        report = self.refused(root, gate, 'message ids appear for more than one call')
        self.assertEqual(report['repeated_message_ids'], 1)

    def test_two_answered_rows_sharing_an_id_are_refused(self):
        root, gate = self.gateway_run()
        learn = learn_folders(root)[0]
        rewrite_rows(learn, lambda rows: rows[1].update(message_id=rows[0]['message_id']))
        report = self.refused(root, gate, 'message ids appear for more than one call')
        self.assertEqual(report['repeated_message_ids'], 1)

    def test_a_provider_row_whose_id_is_not_in_the_file_is_refused(self):
        root, gate = self.gateway_run()
        path = root / 'message-ids.jsonl'
        lines = path.read_text().splitlines(keepends=True)
        path.write_text(''.join(lines[1:]))
        self.refused(root, gate, 'is not in message-ids.jsonl')
        path.unlink()
        self.refused(root, gate, 'is not in message-ids.jsonl')            # no file at all on the gateway route

    def test_a_line_of_the_file_with_an_extra_or_a_missing_key_or_not_text_is_refused(self):
        root, gate = self.gateway_run()
        path = root / 'message-ids.jsonl'
        good = path.read_text().splitlines(keepends=True)
        first = json.loads(good[0])
        for bad in ({**first, 'extra': 1}, {'message_id': first['message_id']}, {'block': 'x'}, [first], {**first, 'message_id': 5},
                    {**first, 'block': None}, {**first, 'message_id': ''}):
            with self.subTest(bad=bad):
                path.write_text(json.dumps(bad) + '\n' + ''.join(good[1:]))
                report = V.validate(root, **gate)
                self.assertFalse(report['ok'])
                self.assertIn('message-ids.jsonl', report['errors'][0])

    def test_an_id_twice_in_the_file_is_refused(self):
        root, gate = self.gateway_run()
        path = root / 'message-ids.jsonl'
        text = path.read_text()
        path.write_text(text + text.splitlines()[0] + '\n')
        self.refused(root, gate, 'more than once')

    def test_an_id_in_the_file_with_no_provider_row_is_counted_and_not_refused(self):
        root, gate = self.gateway_run()
        with open(root / 'message-ids.jsonl', 'a') as f:
            f.write(json.dumps({'message_id': 'msg_killed', 'block': 'learn3-reach-b0'}) + '\n')
            f.write(json.dumps({'message_id': 'msg_killed_too', 'block': 'learn3-land-b0'}) + '\n')
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['message_ids_in_file_with_no_row'], 2)

    def test_the_direct_route_with_no_file_is_unaffected_and_its_file_is_not_read(self):
        root, gate = fresh(self)
        provider_log(root, via='anthropic')
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual((report['copies_caught'], report['message_ids_in_file_with_no_row']), (0, 0))
        (root / 'message-ids.jsonl').write_text('not even json\n')              # not the gateway route: not read
        self.assertTrue(V.validate(root, **gate)['ok'])

    def test_a_copy_caught_in_a_set_aside_attempt_still_needs_its_id_in_the_file_on_the_gateway_route(self):
        root, gate = self.gateway_run()
        row = self.copy_of(root)
        row['message_id'] = 'msg_not_claimed'
        self.aside_attempt(root, [row])
        self.refused(root, gate, 'is not in message-ids.jsonl')

    def test_the_gates_name_for_the_file_is_the_providers(self):
        from ardupilot import claude_provider
        self.assertEqual(V.RUN_MESSAGE_IDS, claude_provider.RUN_MESSAGE_IDS)


class GatewaySettings(unittest.TestCase):
    """E1.3."""

    def gateway_run(self):
        root, kw = fresh(self)
        name_gateway(root)
        provider_log(root)
        return root, kw

    def test_a_sound_gateway_run_passes_and_reports_the_charge(self):
        root, kw = self.gateway_run()
        report = V.validate(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        g = report['gateway_charge']
        self.assertEqual(g['reply_rows'], 6)
        self.assertEqual((g['rows_with_charge'], g['rows_without_charge']), (3, 3))
        self.assertAlmostEqual(g['charged_usd_sum'], 3 * 0.0011)
        self.assertAlmostEqual(g['list_usd_sum_all_replies'], 6 * 0.001)
        self.assertAlmostEqual(g['list_usd_sum_where_charged'], 3 * 0.001)

    def test_settings_without_the_cache_switch_are_refused(self):
        root, kw = fresh(self)
        name_gateway(root, gateway_cache=None)
        provider_log(root)
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])
        self.assertIn('gateway_cache', report['errors'][0])

    def test_a_row_without_the_cache_switch_or_with_another_value_is_refused(self):
        for change in (lambda rows: rows[0].pop('gateway_cache'), lambda rows: rows[0].update(gateway_cache='store')):
            with self.subTest():
                root, kw = self.gateway_run()
                rewrite_rows(learn_folders(root)[1], change)
                report = V.validate(root, **kw)
                self.assertFalse(report['ok'])
                self.assertIn('without gateway_cache', report['errors'][0])

    def test_a_charge_that_is_not_a_number_or_null_is_refused_and_a_missing_one_too(self):
        for label, change in (('text', lambda rows: rows[0].update(charged_usd='0.01')),
                              ('negative', lambda rows: rows[0].update(charged_usd=-1.0)),
                              ('true', lambda rows: rows[0].update(charged_usd=True)),
                              ('absent', lambda rows: rows[0].pop('charged_usd'))):
            with self.subTest(label):
                root, kw = self.gateway_run()
                rewrite_rows(learn_folders(root)[0], change)
                report = V.validate(root, **kw)
                self.assertFalse(report['ok'])
                self.assertIn('charged_usd', report['errors'][0])

    def test_a_run_on_the_direct_route_is_not_asked_for_the_gateway_fields(self):
        root, kw = fresh(self)
        provider_log(root, via='anthropic')
        rewrite_rows(learn_folders(root)[0], lambda rows: rows[0].pop('charged_usd'))
        report = V.validate(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertNotIn('gateway_charge', report)

    def test_a_refusal_for_repeated_ids_still_reports_the_charge_fields_it_reached(self):
        root, kw = self.gateway_run()
        rewrite_rows(learn_folders(root)[0], lambda rows: rows[1].update(message_id=rows[0]['message_id']))
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])
        self.assertEqual(report['repeated_message_ids'], 1)


def make_late(outcome_path):
    """Make a flight late by the driver's rule: every decision a whole second behind."""
    o = json.loads(outcome_path.read_text())
    for step in o['native_steps']:
        step['decision_lag_s'] = 1.0
    T.write_json(outcome_path, o)


def first_flight(folder):
    return sorted((folder / 'flights').glob('*/outcome.json'))[0]


def set_aside_attempt(root, phase, n, reason='late', late=True, receipt=True):
    """What set_aside3.py leaves for a phase: ROOT.set-aside/PHASE-attemptN with a receipt and the phase folder, copied here
    from the phase as flown, with its first flight late (or not)."""
    from protocol.set_aside3 import set_aside_dir
    attempt = set_aside_dir(root) / f'{phase}-attempt{n}'
    shutil.copytree(root / phase, attempt / phase)
    if late:
        make_late(first_flight(attempt / phase))
    if receipt:
        T.write_json(attempt / 'receipt.json', {'phase': phase, 'attempt': n, 'reason': reason})
    return attempt


def keep_late(root, kind='threat3', *, attempts=2, crashed=0):
    """Make one evaluation phase of the fixture a phase kept late on its third attempt: its first flight late, marked in
    timing.json, kept-late.json, and set-aside attempts as given. Returns (phase folder, source, late flight id)."""
    folder = sorted(root.glob(f'{kind}-reach-b0-*'))[0]
    source = folder.name.split('-')[-1]
    for n in range(1, attempts + 1):
        set_aside_attempt(root, folder.name, n)
    for n in range(attempts + 1, attempts + crashed + 1):
        set_aside_attempt(root, folder.name, n, reason='crashed', late=False)
    make_late(first_flight(folder))
    flights = sorted(p.parent.name for p in (folder / 'flights').glob('*/outcome.json'))
    late = first_flight(folder).parent.name
    T.write_json(folder / 'timing.json', [{'flight': f, 'late': f == late, **({'kept_late': True} if f == late else {})}
                                          for f in flights])
    T.write_json(folder / 'kept-late.json', {'late_attempts_set_aside': attempts,
                                             'attempt_folders': [f'{folder.name}-attempt{n}' for n in range(1, attempts + 1)],
                                             'kept_late_flights': [late]})
    return folder, source, late


class KeptLateEvaluation(unittest.TestCase):
    """E1.4."""

    def run_kept(self, kind='threat3', **kw):
        root, gate = fresh(self)
        folder, source, late = keep_late(root, kind, **kw)
        return root, gate, folder, source, late

    def refused(self, root, gate, text):
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'], 'the gate accepted it')
        self.assertIn(text, report['errors'][0])

    def test_a_threat3_phase_kept_late_on_its_third_attempt_passes_and_is_counted(self):
        root, gate, folder, source, late = self.run_kept()
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['kept_late_evaluation_flights'], {'by_phase': {'threat3': 1}, 'by_source': {source: 1}})
        self.assertEqual(report['checked']['evaluation phases kept late on the third attempt'], 1)

    def test_a_retain3_phase_kept_late_passes_and_is_counted_under_retain3(self):
        root, gate, folder, source, late = self.run_kept('retain3')
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['kept_late_evaluation_flights']['by_phase'], {'retain3': 1})

    def test_a_run_with_nothing_late_reports_no_kept_late_flights(self):
        root, gate = fresh(self)
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['kept_late_evaluation_flights'], {'by_phase': {}, 'by_source': {}})

    def test_further_attempts_set_aside_as_crashed_are_allowed_and_do_not_count(self):
        root, gate, *_ = self.run_kept(crashed=2)
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])

    def test_a_late_flight_with_no_kept_late_record_is_refused_as_before(self):
        root, gate, folder, source, late = self.run_kept()
        (folder / 'kept-late.json').unlink()
        self.refused(root, gate, 'no kept-late.json')
        # and with the marks gone too, the late flight itself is refused
        rows = json.loads((folder / 'timing.json').read_text())
        T.write_json(folder / 'timing.json', [{k: v for k, v in r.items() if k != 'kept_late'} for r in rows])
        self.refused(root, gate, 'infrastructure timing fault')

    def test_a_late_flight_in_a_phase_with_no_set_aside_attempts_is_refused(self):
        root, gate = fresh(self)
        folder = sorted(root.glob('threat3-reach-b0-*'))[0]
        make_late(first_flight(folder))
        self.refused(root, gate, 'infrastructure timing fault')

    def test_one_or_three_late_attempts_are_refused(self):
        root, gate, folder, source, late = self.run_kept(attempts=1)
        self.refused(root, gate, 'not 2')
        root, gate, folder, source, late = self.run_kept()
        set_aside_attempt(root, folder.name, 3)
        T.write_json(folder / 'kept-late.json', {'late_attempts_set_aside': 3, 'attempt_folders':
                     [f'{folder.name}-attempt{n}' for n in (1, 2, 3)], 'kept_late_flights': [late]})
        self.refused(root, gate, 'not 2')

    def test_an_attempt_whose_receipt_does_not_say_late_does_not_count(self):
        root, gate, folder, source, late = self.run_kept()
        from protocol.set_aside3 import set_aside_dir
        T.write_json(set_aside_dir(root) / f'{folder.name}-attempt2' / 'receipt.json',
                     {'phase': folder.name, 'attempt': 2, 'reason': 'crashed'})
        self.refused(root, gate, 'not 2')
        root, gate, folder, source, late = self.run_kept()
        T.write_json(set_aside_dir(root) / f'{folder.name}-attempt2' / 'receipt.json',
                     {'phase': 'threat3-reach-b0-' + '0' * 64, 'attempt': 2, 'reason': 'late'})
        self.refused(root, gate, 'its receipt does not name this phase')

    def test_a_late_attempt_with_no_late_flight_in_its_own_outcomes_is_refused(self):
        root, gate, folder, source, late = self.run_kept()
        from protocol.set_aside3 import set_aside_dir
        for outcome in (set_aside_dir(root) / f'{folder.name}-attempt1' / folder.name / 'flights').glob('*/outcome.json'):
            o = json.loads(outcome.read_text())
            for step in o['native_steps']:
                step['decision_lag_s'] = .001
            T.write_json(outcome, o)
        self.refused(root, gate, 'no flight in it is late')

    def test_an_attempt_with_no_flights_or_an_unreadable_receipt_is_refused(self):
        root, gate, folder, source, late = self.run_kept()
        from protocol.set_aside3 import set_aside_dir
        shutil.rmtree(set_aside_dir(root) / f'{folder.name}-attempt1' / folder.name / 'flights')
        self.refused(root, gate, 'no flights to read again')
        root, gate, folder, source, late = self.run_kept()
        (set_aside_dir(root) / f'{folder.name}-attempt2' / 'receipt.json').write_text('{not json')
        self.refused(root, gate, 'cannot be read')

    def test_the_record_must_match_the_attempts(self):
        for label, change in (('count', {'late_attempts_set_aside': 3}),
                              ('names', {'attempt_folders': ['x-attempt1', 'x-attempt2']}),
                              ('order', {'attempt_folders': 'swap'}),
                              ('flights', {'kept_late_flights': ['reach-calm-1']}),
                              ('extra key', {'note': 'x'})):
            with self.subTest(label):
                root, gate, folder, source, late = self.run_kept()
                record = json.loads((folder / 'kept-late.json').read_text())
                if change.get('attempt_folders') == 'swap':
                    change = {'attempt_folders': record['attempt_folders'][::-1]}
                T.write_json(folder / 'kept-late.json', {**record, **change})
                report = V.validate(root, **gate)
                self.assertFalse(report['ok'])

    def test_the_marked_flights_must_be_exactly_the_late_ones(self):
        # A second flight marked kept late although it flew on time.
        root, gate, folder, source, late = self.run_kept()
        rows = json.loads((folder / 'timing.json').read_text())
        other = next(r for r in rows if not r['late'])
        other['kept_late'] = True
        T.write_json(folder / 'timing.json', rows)
        T.write_json(folder / 'kept-late.json', {**json.loads((folder / 'kept-late.json').read_text()),
                                                 'kept_late_flights': [late, other['flight']]})
        self.refused(root, gate, 'marked kept late but flown on time')
        # The late flight not marked.
        root, gate, folder, source, late = self.run_kept()
        rows = json.loads((folder / 'timing.json').read_text())
        for r in rows:
            r.pop('kept_late', None)
        T.write_json(folder / 'timing.json', rows)
        self.refused(root, gate, 'without timing rows that mark a kept late flight')
        # The marked flight is not the late one: the late one is another flight.
        root, gate, folder, source, late = self.run_kept()
        rows = json.loads((folder / 'timing.json').read_text())
        swap = next(r for r in rows if not r['late'])
        for r in rows:
            r.pop('kept_late', None)
        swap['kept_late'] = True
        T.write_json(folder / 'timing.json', rows)
        T.write_json(folder / 'kept-late.json', {**json.loads((folder / 'kept-late.json').read_text()),
                                                 'kept_late_flights': [swap['flight']]})
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'])

    def test_a_mark_without_a_kept_late_record_is_refused_even_when_nothing_is_late(self):
        root, gate = fresh(self)
        folder = sorted(root.glob('threat3-reach-b0-*'))[0]
        flights = sorted(p.parent.name for p in (folder / 'flights').glob('*/outcome.json'))
        T.write_json(folder / 'timing.json', [{'flight': f, 'late': False, **({'kept_late': True} if i == 0 else {})}
                                              for i, f in enumerate(flights)])
        self.refused(root, gate, 'no kept-late.json')

    def test_kept_late_json_without_timing_rows_is_refused(self):
        root, gate, folder, source, late = self.run_kept()
        (folder / 'timing.json').unlink()
        self.refused(root, gate, 'without timing rows')


def write_events(root, rows):
    (root / 'logs').mkdir(parents=True, exist_ok=True)
    (root / 'logs' / 'pauses.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))


def event(kind, stop=R3.SPEND_LIMIT_USD_3, flag=False, **more):
    return {'time': '2026-11-18 09:00:00', 'event': kind, 'reason': None, 'spend_limit_usd': stop,
            'spend_limit_from_flag': flag, **more}


class SpendStops(unittest.TestCase):
    """E1.5. The scored branch is tested on session_stops directly, since a scored gate run needs the real seed book."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_every_start_and_resume_is_reported_and_stops_at_the_protocols_figure_pass(self):
        write_events(self.root, [event('start'), {'event': 'pause_asked', 'time': 't'}, event('resume'), event('resume')])
        got = V.session_stops(self.root, False)
        self.assertEqual([e['event'] for e in got['sessions']], ['start', 'resume', 'resume'])
        self.assertEqual(got['other'], [])
        self.assertEqual(R3.SPEND_LIMIT_USD_3, 60.0)

    def test_a_session_with_another_stop_is_reported_under_its_own_field_and_not_refused(self):
        write_events(self.root, [event('start'), event('resume', 80.0, True), event('resume', 60, False)])
        got = V.session_stops(self.root, False)
        self.assertEqual(len(got['sessions']), 3)
        self.assertEqual([(e['spend_limit_usd'], e['spend_limit_from_flag']) for e in got['other']], [(80.0, True)])
        # A flag that was given and set the protocol's own figure is not "other".
        write_events(self.root, [event('start', 60.0, True)])
        self.assertEqual(V.session_stops(self.root, False)['other'], [])

    def test_a_scored_run_refuses_an_event_without_the_two_fields_or_with_bad_ones(self):
        for label, row in (('no stop', {k: v for k, v in event('start').items() if k != 'spend_limit_usd'}),
                           ('no flag', {k: v for k, v in event('start').items() if k != 'spend_limit_from_flag'}),
                           ('text stop', event('start', '60')), ('negative', event('start', -1)),
                           ('bool stop', event('start', True)), ('flag as number', event('start', 60.0, 1)),
                           ('nan', event('start', float('nan')))):
            with self.subTest(label):
                write_events(self.root, [event('start'), row])
                with self.assertRaises(V.InvalidEvidence):
                    V.session_stops(self.root, False)
        write_events(self.root, [event('start'), {'event': 'resume', 'time': 't', 'reason': 'x'}])
        with self.assertRaisesRegex(V.InvalidEvidence, 'has no spend_limit_usd'):
            V.session_stops(self.root, False)

    def test_a_scored_run_with_no_start_event_or_no_log_is_refused(self):
        with self.assertRaisesRegex(V.InvalidEvidence, 'no start event'):
            V.session_stops(self.root, False)
        write_events(self.root, [event('resume')])
        with self.assertRaisesRegex(V.InvalidEvidence, 'no start event'):
            V.session_stops(self.root, False)
        (self.root / 'logs' / 'pauses.jsonl').write_text('{not json\n')
        with self.assertRaisesRegex(V.InvalidEvidence, 'does not parse'):
            V.session_stops(self.root, False)

    def test_a_pilot_reports_missing_fields_as_unknown_and_still_refuses_bad_ones(self):
        write_events(self.root, [{'event': 'start', 'time': 't', 'reason': None}, event('resume', 8.0, True)])
        got = V.session_stops(self.root, True)
        self.assertEqual((got['sessions'][0]['spend_limit_usd'], got['sessions'][0]['spend_limit_from_flag']), ('unknown', 'unknown'))
        self.assertEqual(got['sessions'][1]['spend_limit_usd'], 8.0)
        self.assertEqual(got['other'], [])
        write_events(self.root, [event('start', 'lots')])
        with self.assertRaises(V.InvalidEvidence):
            V.session_stops(self.root, True)
        (self.root / 'logs' / 'pauses.jsonl').unlink()
        self.assertEqual(V.session_stops(self.root, True), {'sessions': [], 'other': []})

    def test_the_gate_puts_the_sessions_in_a_pilot_report(self):
        root, gate = fresh(self)
        write_events(root, [event('start', 5.0, True), event('resume', 8.0, True)])
        report = V.validate(root, **gate)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual([(e['spend_limit_usd'], e['spend_limit_from_flag']) for e in report['session_spend_stops']],
                         [(5.0, True), (8.0, True)])
        self.assertEqual(report['sessions_with_other_spend_stop'], [])
        write_events(root, [event('start', 'lots')])
        report = V.validate(root, **gate)
        self.assertFalse(report['ok'])
        self.assertIn('spend_limit_usd', report['errors'][0])


PLATFORM = {'platform': 'cluster', 'node': 'l40s-f-02', 'slurm_job_id': '1', 'slurm_job_partition': 'gpu',
            'cpu_model': 'Intel(R) Xeon(R) Gold 6448Y', 'cores_allowed': 16, 'load_1min_at_start': 1.0}


class Freeze(unittest.TestCase):
    """E1.6, the tool."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        for name, text in (('seeds.json', 's'), ('protocol.md', 'p'), ('delay.json', 'd'), ('adopt.json', 'a'), ('wheel.whl', 'w')):
            (self.dir / name).write_text(text)
        self.manifest = self.dir / 'manifest.json'
        self.manifest.write_text(json.dumps({'platform': PLATFORM}))
        self.out = self.dir / 'FROZEN-3.json'

    def paths(self, **more):
        return {'manifest': self.manifest, 'out': self.out, 'fingerprint': {'sha256': 'a' * 64, 'files': 86},
                'wheel': self.dir / 'wheel.whl', 'seeds': self.dir / 'seeds.json', 'protocol': self.dir / 'protocol.md',
                'delay_expected': self.dir / 'delay.json', 'pilot_adoption': self.dir / 'adopt.json', **more}

    def test_it_writes_every_value_once(self):
        F.freeze(**self.paths())
        got = json.loads(self.out.read_text())
        sha = lambda text: __import__('hashlib').sha256(text.encode()).hexdigest()      # noqa: E731
        self.assertEqual(got['source_fingerprint'], {'sha256': 'a' * 64, 'files': 86})
        self.assertEqual((got['wheel_sha256'], got['seeds_sha256'], got['protocol_sha256'], got['delay_check_expected_sha256'],
                          got['pilot_adoption_sha256']), (sha('w'), sha('s'), sha('p'), sha('d'), sha('a')))
        self.assertEqual((got['platform']['partition'], got['platform']['node_type'], got['platform']['cpu_model']),
                         ('gpu', 'l40s-f', 'Intel(R) Xeon(R) Gold 6448Y'))
        self.assertEqual(got['platform']['taken_from']['fields']['partition'], 'platform.slurm_job_partition')
        self.assertEqual(set(F.KEYS) - set(got), set())

    def test_it_refuses_to_overwrite(self):
        F.freeze(**self.paths())
        before = self.out.read_bytes()
        (self.dir / 'seeds.json').write_text('changed')
        with self.assertRaisesRegex(SystemExit, 'written once'):
            F.freeze(**self.paths())
        self.assertEqual(self.out.read_bytes(), before)

    def test_it_refuses_without_the_protocol_text_or_another_file_and_writes_nothing(self):
        for name, key in (('protocol.md', 'protocol'), ('seeds.json', 'seeds'), ('delay.json', 'delay_expected'),
                          ('adopt.json', 'pilot_adoption')):
            with self.subTest(name):
                (self.dir / name).rename(self.dir / (name + '.gone'))
                with self.assertRaisesRegex(SystemExit, 'absent'):
                    F.freeze(**self.paths())
                self.assertFalse(self.out.exists())
                (self.dir / (name + '.gone')).rename(self.dir / name)

    def test_it_refuses_a_manifest_that_is_not_a_cluster_one_or_lacks_a_field(self):
        for label, record in (('mac', {'platform': 'mac'}), ('none', None),
                              ('no cpu', {**PLATFORM, 'cpu_model': ''}), ('no node', {k: v for k, v in PLATFORM.items() if k != 'node'}),
                              ('no partition', {**PLATFORM, 'slurm_job_partition': None})):
            with self.subTest(label):
                self.manifest.write_text(json.dumps({'platform': record} if record is not None else {}))
                with self.assertRaises(SystemExit):
                    F.freeze(**self.paths())
                self.assertFalse(self.out.exists())

    def test_the_repository_holds_no_frozen_file_yet(self):
        self.assertFalse(F.FROZEN_PATH.exists(), 'the freeze comes later; this file must not be committed before it')

    def test_the_node_type_is_the_name_without_its_number(self):
        self.assertEqual([F.node_type(n) for n in ('l40s-f-02', 'v100-f-13', 'epyc-1', 'plain')],
                         ['l40s-f', 'v100-f', 'epyc', 'plain'])


class FrozenGate(unittest.TestCase):
    """E1.6, the gate. A scored gate run needs the real seed book, so a pilot fixture is judged with judge_frozen=True."""

    def setUp(self):
        from ardupilot import scored as S
        self.root, self.kw = fresh(self)
        with mock.patch.dict(os.environ, {'PAPER3_PLATFORM': 'cluster'}), \
                mock.patch.object(S.os, 'getloadavg', return_value=(1.0, 1.0, 1.0)):
            load, plat, prio = S.load_check(pilot=False), S.platform_record(), S.power_and_priority()
        self.plat = {**plat, 'node': 'l40s-f-03', 'slurm_job_partition': 'gpu', 'cpu_model': 'Intel Test'}
        for path in sorted(self.root.glob('*/manifest.json')):
            m = json.loads(path.read_text())
            m['machine'] = {'concurrent_sitl_instances': [], 'parallel_limit': 4, 'load': load, **prio, 'nice': 0}
            m['platform'] = self.plat
            T.set_route(path, m)
            T.write_json(path, m)
        self.dir = Path(tempfile.mkdtemp(dir=self.temp.name))
        for name in ('delay.json', 'adopt.json'):
            (self.dir / name).write_text(name)
        self.patches = [mock.patch.object(F, 'DELAY_EXPECTED', self.dir / 'delay.json'),
                        mock.patch.object(F, 'PILOT_ADOPTION', self.dir / 'adopt.json')]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        from ardupilot import scored as S
        manifest = self.dir / 'manifest.json'
        manifest.write_text(json.dumps({'platform': {**self.plat, 'node': 'l40s-f-01'}}))   # another node of the same type
        self.frozen = self.dir / 'FROZEN-3.json'
        F.freeze(manifest=manifest, out=self.frozen, fingerprint={'sha256': 'e' * 64, 'files': 99}, wheel=S.WHEEL,
                 seeds=self.kw['seed_path'], protocol=self.kw['protocol_path'], delay_expected=self.dir / 'delay.json',
                 pilot_adoption=self.dir / 'adopt.json')

    def judge(self, frozen=None):
        return V.load_run(self.root, **self.kw, frozen_path=frozen or self.frozen, judge_frozen=True)[0]

    def edit(self, key, value, sub=None):
        record = json.loads(self.frozen.read_text())
        if sub:
            record[key][sub] = value
        else:
            record[key] = value
        self.frozen.write_text(json.dumps(record))

    def test_a_run_that_matches_passes_whatever_node_of_the_type_it_ran_on(self):
        report = self.judge()
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['frozen_values']['differences'], [])

    def test_a_pilot_is_not_judged_by_default(self):
        report = V.load_run(self.root, **self.kw, frozen_path=self.dir / 'absent.json')[0]
        self.assertTrue(report['ok'], report['errors'])
        self.assertNotIn('frozen_values', report)

    def test_a_missing_file_is_refused(self):
        report = self.judge(self.dir / 'absent.json')
        self.assertFalse(report['ok'])
        self.assertIn('is absent', report['errors'][0])

    def test_each_value_that_differs_is_refused_by_name(self):
        cases = (('source_fingerprint', 'f' * 64, 'sha256', 'source_fingerprint'),
                 ('source_fingerprint', 98, 'files', 'source_fingerprint'),
                 ('wheel_sha256', '0' * 64, None, 'wheel_sha256'), ('seeds_sha256', '0' * 64, None, 'seeds_sha256'),
                 ('protocol_sha256', '0' * 64, None, 'protocol_sha256'),
                 ('delay_check_expected_sha256', '0' * 64, None, 'delay_check_expected_sha256'),
                 ('pilot_adoption_sha256', '0' * 64, None, 'pilot_adoption_sha256'),
                 ('platform', 'cpu', 'cpu_model', 'platform'), ('platform', 'cpu', 'partition', 'platform'),
                 ('platform', 'v100-f', 'node_type', 'platform'))
        for key, value, sub, word in cases:
            with self.subTest(key=key, sub=sub):
                self.setUp()
                self.edit(key, value, sub)
                report = self.judge()
                self.assertFalse(report['ok'])
                self.assertIn(word, report['errors'][0])
                self.assertEqual(len(report['frozen_values']['differences']), 1)

    def test_a_key_missing_from_the_file_or_an_edited_expectation_file_is_refused(self):
        record = json.loads(self.frozen.read_text())
        del record['platform']
        self.frozen.write_text(json.dumps(record))
        self.assertIn('platform is missing', self.judge()['errors'][0])
        self.setUp()
        (self.dir / 'adopt.json').write_text('changed after the freeze')
        self.assertIn('pilot_adoption_sha256', self.judge()['errors'][0])


if __name__ == '__main__':
    unittest.main()

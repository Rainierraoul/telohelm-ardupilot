"""Offline schedule, inference and evidence-gate controls for protocol 3.

Synthetic records are explicitly pilot fixtures; nothing calls a model or SITL.
"""
import contextlib
import copy
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from protocol import contract3 as C
from protocol.make_seeds_3 import build, seed_numbers, validate
from protocol import analysis3 as A
from protocol import validate3 as V
from ardupilot.ladder import COMMAND_DELAY_PERIODS, COMMAND_DELAY_S
from ardupilot.test_ladder import delay_fixture, with_delay

_SAVED_PLATFORM = os.environ.get('PAPER3_PLATFORM')


_ROUTE = []


def _route_patches():
    from unittest import mock
    return (mock.patch('telohelm.runtime.sandbox.start_route', lambda: {'route': 'sandbox-exec'}),
            mock.patch('telohelm.runtime.sandbox.route_state', lambda: {'route': 'sandbox-exec'}))


def setUpModule():
    """These tests state the Mac's rules, so they run with the platform pinned to 'mac' whatever the environment says;
    the cluster's rules are tested in test_cluster_platform.py and in the cluster tests of this file."""
    os.environ['PAPER3_PLATFORM'] = 'mac'
    # The Mac's rules on whatever machine runs them include the Mac's sandbox route; on Linux the package would name its
    # own (round five, B2). The Linux route is shown in test_route3.py and on the nodes.
    for patch in _route_patches():
        patch.start()
        _ROUTE.append(patch)


def tearDownModule():
    while _ROUTE:
        _ROUTE.pop().stop()
    if _SAVED_PLATFORM is None:
        os.environ.pop('PAPER3_PLATFORM', None)
    else:
        os.environ['PAPER3_PLATFORM'] = _SAVED_PLATFORM



def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def set_route(path, manifest):
    """The sandbox record that a manifest of its platform carries and, on the cluster, the sandbox-end.json beside it
    (round five, B2). For the tests that change a manifest's platform."""
    from ardupilot import scored as S
    cluster = (manifest.get('platform') or {}).get('platform') == 'cluster'
    route = S.EXPECTED_ROUTE['cluster' if cluster else 'mac']
    manifest['sandbox'] = {'route': route, **({'kernel': '5.15.0-test'} if cluster else {})}
    if cluster:
        write_json(Path(path).parent / 'sandbox-end.json', {'route': route, 'calls': 1, 'replacements': []})


def protected_log(path, payloads):
    lines, heads, previous = [], [], '0' * 64
    for i, payload in enumerate([{'kind': 'anchor', 'run_id': 'synthetic-fixture'}, *payloads], 1):
        line = C.canonical({'seq': i, 'prev': previous, 'payload': payload})
        previous = hashlib.sha256(line).hexdigest()
        head = {'count': i, 'head': previous}
        if i == 1:
            head['anchor'] = previous
        lines.append(line)
        heads.append(C.canonical(head))
    path.write_bytes(b'\n'.join(lines) + b'\n')
    path.with_suffix('.heads').write_bytes(b'\n'.join(heads) + b'\n')


def fixture(root, *, nonadopt=False, formatted=False, whole_book=False, tasks=C.TASKS, seed_book=None):
    """Synthetic pilot evidence only. No flight, request or source is executed. With whole_book the development book
    keeps all its blocks although only block 0 is written, as in a pilot flown with --blocks 1."""
    from ardupilot import pack as P
    root.mkdir()
    # seed_book: the path of an earlier fixture's seed book, so that several roots of one run hold the same book (build() does
    # not draw the same book twice)
    seeds = build() if seed_book is None else json.loads(Path(seed_book).read_text())
    seeds['design'].update(pilot_evaluation_per_band=1, pilot_retention_per_task=2)
    if not whole_book:
        seeds['design'].update(pilot_blocks_per_task=1)
    for task in C.TASKS:
        if not whole_book:
            seeds['pilot']['blocks'][task] = seeds['pilot']['blocks'][task][:1]
        seeds['pilot']['threat_evaluation'][task] = {b: v[:1] for b, v in seeds['pilot']['threat_evaluation'][task].items()}
        seeds['pilot']['heldout'][task] = {f: v[:1] for f, v in seeds['pilot']['heldout'][task].items()}
    seed_path, proto = root / 'seed-book.json', root / 'PROTOCOL-3-DRAFT.md'
    write_json(seed_path, seeds)
    proto.write_text('Synthetic schema-control fixture. Not a scientific experiment.\n')
    (root / 'logs').mkdir()
    wheel = V.S.WHEEL                  # the Paper 3 build of the wheel, which the gate hashes
    seed_hash, protocol_hash, wheel_hash = C.sha(seed_path), C.sha(proto), C.sha(wheel)

    def manifest(phase, task, h=None, roles=None, cases=None):
        name = C.phase_name(phase, task, 0, h)
        folder = root / name
        args = {'task': task, 'block': 0}
        if h:
            args.update(source_sha256=h, **roles, cases=[c.episode_id for c in cases], learning=str(root / C.phase_name('learn3', task, 0)),
                        flight_order=[c.episode_id for c in cases])     # instance 10 flies the listed order
        write_json(folder / 'manifest.json', {
            'protocol_version': 3, 'phase': phase, 'pilot': True, 'synthetic': True,
            'args': args, 'instance': 10, 'seeds_sha256': seed_hash,
            'protocol': proto.name, 'protocol_sha256': protocol_hash,
            'core': {'ok': True, 'wheel_sha256': wheel_hash}, 'sandbox': {'route': 'sandbox-exec'},
            'git': {'source': {'sha256': 'e' * 64, 'files': 99}, 'uncommitted_paper3': []},
            'at_once': 4,
            'machine': {'concurrent_sitl_instances': [], 'parallel_limit': 4,
                        'load': {'load_average_1_5_15': [.1, .1, .1], 'limit_1min': 1.0, 'cores': 1,
                                 'limit_status': 'synthetic fixture'}}})
        (root / 'logs' / (name + '.done')).write_text('synthetic completed fixture\n')
        return folder

    def flights(folder, cases, source=None, passed=True):
        write_json(folder / 'run-config.json', {'task': cases[0].task, 'speedup': 1.0,
                   'command_delay_periods': COMMAND_DELAY_PERIODS,
                   'source': source if source else [], 'scenarios': [asdict(c) for c in cases]})
        rows, outcomes = [], []
        # A flown candidate sits alone in the folder's library, as battle.run leaves it, and a passing flight carries
        # one decision record for every step, issued by it, so that pack.component_trial passes on the log.
        sha = None
        if source:
            from telohelm.runtime.library import Library
            library = Library(folder / 'library', pack=P.PACKS[cases[0].task].public)
            sha = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': source,
                               'origin': {'imported_from': 'synthetic fixture'}})
            library.set_status(sha, 'adopted', 'synthetic fixture')
        for case in cases:
            d = folder / case.episode_id
            ending = P.TASKS[case.task].success if passed else 'timed_out'
            goal = P.TASKS[case.task].goal(dict(case.params))
            n = int(goal.get('hold_s', 1)) if passed else 1
            position = {'north_m': goal['target_north_m'] if passed else 0.0,
                        'east_m': goal['target_east_m'] if passed else 0.0,
                        'alt_m': (goal.get('target_alt_m', 10.0) if case.task != 'land' else goal['ground_alt_m']) if passed else 10.0}
            o = {'task': case.task, 'goal_met': passed, 'end_reason': ending, 'settled': True,
                 'model_calls': 0, 'goal': goal, 'events': list(case.events), 'action_steps': n,
                 'native_steps': [{'t': i + 1, 'decision_lag_s': .001, 'observation_lag_s': 0.0,
                                   'command_lag_s': COMMAND_DELAY_S, **position,
                                   'true_vd_ms': 0.0, 'truth_age_s': 0.0} for i in range(n)],
                 'command_delay_s': COMMAND_DELAY_S}
            write_json(d / 'outcome.json', o)
            zero = {f: 0.0 for f in P.TASKS[case.task].fields}
            decisions = [{'kind': 'decision', 'decision': 'control', 'method': sha, 'goal_version': 1, 't': i,
                          'part': dict(zero)} for i in range(n)] if sha and passed else []
            protected_log(d / 'episode.log', [*decisions, {'kind': 'episode_end', 'goal_met': passed, 'end_reason': ending}])
            protected_log(d / 'broker.log', [])
            family, seed = case.episode_id.rsplit('-', 1)
            rows.append({'family': family, 'seed': int(seed), 'goal_met': passed, 'end_reason': ending})
            outcomes.append({'episode_id': case.episode_id, 'goal_met': passed, 'end_reason': ending,
                             'trial_passed': passed})
        (folder / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        return outcomes

    if tuple(tasks) != tuple(C.TASKS):
        write_json(root / 'logs' / 'schedule.json', {'pilot': True, 'at_once': 4, 'tasks': list(tasks),
                                                    'learning': [[C.phase_name('learn3', task, 0), []] for task in tasks]})
    for task in tasks:
        learn = manifest('learn3', task)
        initial = {}
        for label, threat in (('P0', False), ('P1', True)):
            cases = C.learning_cases(seeds, task, 0, True, threat=threat)
            d = learn / 'flights/first' / label
            flights(d, cases, passed=False)
            initial[label] = [str((d / c.episode_id).relative_to(learn)) for c in cases]
        sequences = {'A': ['c0', 'f1', 'f2'], 'B': ['c0', 'f1', 'f2'],
                     'C': ['c0', 'rC1', 'rC2'], 'D': ['c1', 'rD1', 'rD2']}
        candidates, sources, trial_records, call_rows, arms = {}, {}, {}, [], {}
        for arm in C.ARMS:
            seq = sequences[arm] if nonadopt else sequences[arm][:1]
            arm_trials, arm_calls, previous = [], [], None
            for cid in seq:
                if cid not in candidates:
                    parent = previous if cid.startswith('r') else None
                    context = list(initial['P1' if cid == 'c1' or cid.startswith('rD') else 'P0'])
                    shown = list(context)
                    if parent:
                        # A repair shows the trial flights of the candidate it repairs and no first-round flight.
                        shown = [str((learn / f'flights/trial/{parent}/threat' / c.episode_id).relative_to(learn))
                                 for c in C.learning_cases(seeds, task, 0, True)]
                        context += shown
                    # The driver's layout: the payload is a list of (role, text) messages, request_id names the
                    # candidate's request and each API call has its own receipt under calls/.
                    # No folder path or case name: a real request names flights by alias, and the gate refuses any
                    # learning seed in the text (13 November 2026).
                    messages = [['system', 'synthetic fixture'], ['user', f'task {task}; evidence from {len(context)} flights; {cid}']]
                    if cid in ('f1', 'f2'):
                        messages = json.loads(json.loads((learn / 'candidates/c0/request.json').read_text())['model_payload_json'])
                    raw = json.dumps(messages)
                    callid = task + '-' + cid + '-call-1'
                    settings = {'model': 'synthetic-fixture', 'max_tokens': 64}
                    req = {'candidate_id': cid, 'request_id': task + '-b0-' + cid, 'parent': parent,
                           'context_flights': context, 'shown_flights': shown, 'model_payload_json': raw,
                           'request_sha256': hashlib.sha256(raw.encode()).hexdigest(), C.SETTINGS_FIELD: settings}
                    source = f'# synthetic {task}/{cid}; never executed\ndef decide(ctx):\n    return {{"vn": 0.0, "ve": 0.0}}\n'
                    h = hashlib.sha256(source.encode()).hexdigest()
                    d = learn / 'candidates' / cid
                    write_json(d / 'request.json', req)
                    calls = [callid]
                    call_rows.append({'call_id': callid, 'candidate_id': cid, 'request_sha256': req['request_sha256'],
                                      'input_tokens': 100, 'output_tokens': 10, 'list_cost_usd': .001,
                                      'served_by': 'synthetic-fixture', 'real_model_call': False})
                    write_json(d / 'calls/1.json', {**call_rows[-1], 'call': 1, 'shown_flights': shown, 'model_payload_json': raw,
                                                    'reply_text': 'invalid format' if formatted and cid == 'c0' else '',
                                                    C.SETTINGS_FIELD: settings})
                    if formatted and cid == 'c0':
                        fmt_raw = json.dumps(messages + [['assistant', 'invalid format'],
                                                         ['user', 'return the required procedure format']])
                        calls.append(callid[:-1] + '2')
                        call_rows.append({**call_rows[-1], 'call_id': calls[-1],
                                          'request_sha256': hashlib.sha256(fmt_raw.encode()).hexdigest()})
                        write_json(d / 'calls/2.json', {**call_rows[-1], 'call': 2, 'shown_flights': shown, 'model_payload_json': fmt_raw,
                                                        'reply_text': '', C.SETTINGS_FIELD: settings})
                    meta = {'candidate_id': cid, 'format_valid': True, 'source_sha256': h, 'parent': parent, 'call_ids': calls}
                    write_json(d / 'candidate.json', meta)
                    (d / 'source.py').write_text(source)
                    candidates[cid], sources[h] = meta, source
                meta = candidates[cid]
                family = 'matched' if arm == 'A' else 'threat'
                key = (cid, family)
                if key not in trial_records:
                    d = learn / f'flights/trial/{cid}/{family}'
                    cases = C.learning_cases(seeds, task, 0, True, threat=arm != 'A')
                    outcomes = flights(d, cases, source=sources[meta['source_sha256']], passed=not nonadopt)
                    trial_records[key] = {'candidate_id': cid, 'trial_list': family, 'passed': not nonadopt,
                                          'flight_dir': str(d.relative_to(learn)), 'outcomes': outcomes}
                arm_trials.append(copy.deepcopy(trial_records[key]))
                arm_calls += meta['call_ids']
                previous = cid
            arms[arm] = {'adopted': not nonadopt, 'candidate_id': seq[-1] if not nonadopt else None,
                         'source_sha256': candidates[seq[-1]]['source_sha256'] if not nonadopt else None,
                         'trials': arm_trials, 'call_ids': list(dict.fromkeys(arm_calls))}
        write_json(learn / 'arms.json', {'schema_version': 1, 'task': task, 'block': 0,
                                       'c0_zone_qualified': not nonadopt, 'arms': arms})
        (learn / 'usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in call_rows))
        # The roles the driver records (scored._evaluated_source): the same for both phases, and retain3 only for a source
        # some arm adopted.
        for phase, get_cases in (('threat3', C.evaluation_cases), ('retain3', C.retention_cases)):
            cases = get_cases(seeds, task, True)
            for h, roles in V.evaluation_plan(arms, candidates)[phase].items():
                d = manifest(phase, task, h, roles, cases)
                flights(d / 'flights', cases, source=sources[h])
    return {'pilot': True, 'seed_path': seed_path, 'protocol_path': proto}


class SeedTests(unittest.TestCase):
    def test_disjoint_tasks_bands_roles_and_cohorts(self):
        seeds = build()
        checked = validate(seeds, scan_runs=False)
        self.assertEqual(checked['reserved_numbers'], 528)
        self.assertEqual(len(set(seed_numbers(seeds))), 528)
        for task in C.TASKS:
            first = C.learning_cases(seeds, task, 0)
            matched = C.learning_cases(seeds, task, 0, threat=False)
            self.assertEqual(len(first), 3)
            self.assertEqual([s.params for s in first], [s.params for s in matched])
            self.assertTrue(all(not s.events for s in matched))
            self.assertEqual(len(C.evaluation_cases(seeds, task)), 24)
            self.assertEqual(len(C.retention_cases(seeds, task)), 10)
            self.assertEqual(len(C.evaluation_cases(seeds, task, True)), 6)

    def test_overlap_and_missing_band_are_refused(self):
        seeds = build()
        seeds['blocks']['reach'][0]['middle'] = seeds['blocks']['reach'][0]['close']
        with self.assertRaises(ValueError):
            validate(seeds, scan_runs=False)
        seeds = build()
        del seeds['threat_evaluation']['land']['wide']
        with self.assertRaises(ValueError):
            validate(seeds, scan_runs=False)

    def test_historical_reservation_is_refused(self):
        seeds = build()
        seeds['blocks']['reach'][0]['close'] = 44001
        with self.assertRaises(ValueError):
            validate(seeds, scan_runs=False)

    def test_phase_identity_does_not_allow_partial_or_ambiguous_source(self):
        self.assertEqual(C.phase_name('learn3', 'reach', 2), 'learn3-reach-b2')
        h = 'a' * 64
        self.assertEqual(C.phase_name('threat3', 'land', 0, h), 'threat3-land-b0-' + h)
        for args in [('threat3', 'reach', 0, None), ('learn3', 'reach', 0, h),
                     ('retain3', 'land', 0, '../x'), ('learn3', 'orbit', 0, None)]:
            with self.assertRaises(ValueError):
                C.phase_name(*args)


class InferenceTests(unittest.TestCase):
    def test_direction_and_equivalence_are_separate(self):
        small = A.classify(.04, [.01, .07], [.02, .06])
        self.assertEqual(small['class'], 'different_and_equivalent')
        self.assertEqual(small['direction'], 'gain')
        self.assertFalse(small['useful_gain'])
        null = A.classify(0, [-.12, .12], [-.09, .09], .10)
        self.assertEqual(null['class'], 'equivalent_not_different')
        unknown = A.classify(0, [-.4, .4], [-.3, .3])
        self.assertEqual(unknown['class'], 'unresolved')
        large = A.classify(.5, [.3, .7], [.35, .65])
        self.assertTrue(large['useful_gain'])
        with self.assertRaises(ValueError):
            A.classify(0, [-.1, .1], [-.2, .2])

    def test_arms_share_draws_and_strata_keep_their_weights(self):
        y = np.zeros((4, 10, 6))
        y[1, :, :2] = y[2, :, :2] = 1
        rows, _, _ = A.comparisons(y, ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2,
                                  np.random.default_rng(5), 200)
        self.assertEqual(rows['C-B']['ci95'], [0, 0])
        self.assertEqual(rows['B-A']['ci95'], [round(1 / 3, 12)] * 2)

    def test_common_scenarios_do_not_become_independent_per_library(self):
        sd = []
        for blocks in (2, 64):
            y = np.zeros((4, blocks, 6))
            y[1, :, 0] = 1
            draw = A.bootstrap(y, ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2,
                               np.random.default_rng(7), 2000)
            sd.append(float(np.std(draw[1] - draw[0])))
        self.assertGreater(sd[1] / sd[0], .8)
        self.assertLess(sd[1] / sd[0], 1.2)

    def test_negative_repair_and_unknown_cost_are_retained(self):
        y = np.zeros((4, 3, 3)); y[1] = 1
        rows, _, _ = A.comparisons(y, list(C.BANDS), np.random.default_rng(8), 100)
        self.assertEqual(rows['C-B']['estimate'], -1)
        self.assertTrue(rows['C-B']['classification']['useful_loss'])
        cost = A.usage([{'input_tokens': 10, 'output_tokens': 2, 'list_cost_usd': .01},
                        {'input_tokens': None, 'output_tokens': 3, 'list_cost_usd': None}])
        self.assertIsNone(cost['list_cost_usd'])
        self.assertEqual(cost['list_cost_usd_known_subtotal'], .01)
        y[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            A.bootstrap(y, list(C.BANDS), np.random.default_rng(1), 10)

    def test_task_cancellation_does_not_become_a_pooled_null_claim(self):
        points = {'reach': np.array([0., 0., 1., 1.]),
                  'reach3d': np.array([1., 1., 0., 0.]), 'land': np.zeros(4)}
        draws = {t: np.repeat(v[:, None], 100, axis=1) for t, v in points.items()}
        steps = {t: {key: A.estimate_record(v[C.ARMS.index(a)] - v[C.ARMS.index(b)],
                                            draws[t][C.ARMS.index(a)] - draws[t][C.ARMS.index(b)])
                     for key, (a, b) in C.STEPS.items()} for t, v in points.items()}
        pooled = A.pooled_comparisons(points, draws, steps)
        self.assertEqual(pooled['C-B']['estimate'], 0)
        self.assertEqual(pooled['C-B']['classification']['class'], 'task_dependent')
        self.assertFalse(pooled['C-B']['pooled_class_used'])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p3-contract-', dir='/private/tmp' if Path('/private/tmp').is_dir() else None)
        self.root = Path(self.temp.name) / 'run'
        self.kw = fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def report(self):
        return V.validate(self.root, **self.kw)

    def evaluation(self):
        return next(self.root.glob('threat3-*'))

    def test_complete_fixture_and_snapshot_analysis(self):
        report, snapshot = V.load_run(self.root, **self.kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['checked']['learning blocks'], 3)
        result = A.analyse_snapshot(snapshot, n_boot=100)
        self.assertEqual((len(result['primary']), len(result['secondary_intervals'])), (3, 6))
        self.assertEqual(result['unique_experiment_usage']['calls'], 6)
        self.assertAlmostEqual(result['unique_experiment_usage']['list_cost_usd'], .006)
        standalone = sum(task['standalone_usage'][arm]['list_cost_usd'] for task in result['tasks'].values() for arm in C.ARMS)
        self.assertAlmostEqual(standalone, .012)
        self.assertIn('development', result['status'])
        # Analysis consumes the validated snapshot, not a fresh reading of files.
        shutil.rmtree(self.root)
        self.assertEqual(A.analyse_snapshot(snapshot, n_boot=100), result)

    def late_copy(self, block, k, late=True):
        """Copy the block's kept first-round call P0 to late/flights/first/P0/attempt-k, as the driver leaves an attempt
        it set aside (round two, ruling 3), with its first flight late or not."""
        kept = block / 'flights/first/P0'
        aside = block / 'late/flights/first/P0' / f'attempt-{k}'
        shutil.copytree(kept, aside)
        if late:
            first = sorted(aside.glob('*/outcome.json'))[0]
            o = json.loads(first.read_text())
            for st in o['native_steps']:
                st['decision_lag_s'] = 1.0
            write_json(first, o)
        return kept

    def test_a_call_set_aside_as_late_and_flown_again_passes_and_is_not_counted(self):
        before, _ = V.load_run(self.root, **self.kw)
        self.assertTrue(before['ok'], before['errors'])
        block = next(self.root.glob('learn3-*'))
        self.late_copy(block, 1)
        after, snapshot = V.load_run(self.root, **self.kw)
        self.assertTrue(after['ok'], after['errors'])
        self.assertEqual(after['checked'].pop('learning calls set aside as late and flown again'), 1)
        self.assertEqual(after['checked'], before['checked'])
        self.assertEqual(snapshot['unique_flights'], before['checked']['unique flights'])
        self.assertTrue(V.in_late(self.root, block / 'late' / 'x' / 'outcome.json'))
        self.assertFalse(V.in_late(self.root, self.evaluation() / 'late' / 'x' / 'outcome.json'))

    def test_a_set_aside_attempt_needs_a_late_flight_and_numbering_from_one(self):
        block = next(self.root.glob('learn3-*'))
        self.late_copy(block, 1, late=False)
        self.assertFalse(self.report()['ok'])
        shutil.rmtree(block / 'late')
        self.late_copy(block, 2)
        self.assertFalse(self.report()['ok'])
        shutil.rmtree(block / 'late')
        for k in (1, 2, 3):
            self.late_copy(block, k)
        self.assertFalse(self.report()['ok'])           # more than two flights again
        shutil.rmtree(block / 'late')
        self.late_copy(block, 1)
        stray = block / 'late' / 'flights' / 'first' / 'P0' / 'matched-close-0'
        stray.mkdir(parents=True)
        write_json(stray / 'outcome.json', {'native_steps': []})
        self.assertFalse(self.report()['ok'])           # a flight under late/ that is in no attempt

    def test_a_late_flight_is_kept_only_after_two_set_aside_attempts(self):
        block = next(self.root.glob('learn3-*'))
        kept = block / 'flights/first/P0'
        first = sorted(kept.glob('*/outcome.json'))[0]
        o = json.loads(first.read_text())
        for st in o['native_steps']:
            st['decision_lag_s'] = 1.0
        write_json(first, o)
        self.assertFalse(self.report()['ok'])           # late with no attempt set aside
        self.late_copy(block, 1)
        self.assertFalse(self.report()['ok'])           # one attempt set aside is not enough
        self.late_copy(block, 2)
        report = self.report()
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['checked']['learning flights kept late after two flights again'], 1)

    def test_a_warmup_folder_in_any_phase_is_not_counted_matched_or_verified(self):
        """ruling 6: a warm-up flight leaves an outcome, a manifest, hash-chained logs, a request and a usage file.
        Here every one is junk, and the complete run still passes, with the same counts as without it."""
        before, _ = V.load_run(self.root, **self.kw)
        self.assertTrue(before['ok'], before['errors'])
        phases = [p.parent for p in self.root.glob('*/manifest.json')]
        self.assertTrue(phases)
        for phase in phases:
            warm = phase / 'warmup' / 'calm-4200001'
            warm.mkdir(parents=True)
            write_json(warm / 'outcome.json', {'native_steps': []})
            for name in ('episode.log', 'episode.heads', 'broker.log', 'log', 'x-request.json', 'usage.jsonl'):
                (warm / name).write_text('not a valid record\n')
            write_json(phase / 'warmup' / 'manifest.json', {'junk': True})
        after, snapshot = V.load_run(self.root, **self.kw)
        self.assertTrue(after['ok'], after['errors'])
        self.assertEqual(after['checked'], before['checked'])
        self.assertEqual(after['scheduled_phases'], before['scheduled_phases'])
        self.assertEqual(snapshot['unique_flights'], before['checked']['unique flights'])
        # A flight outside a warmup folder is still counted: the same junk in a flights folder is refused.
        junk = phases[0] / 'flights' / 'calm-4200001'
        junk.mkdir(parents=True)
        write_json(junk / 'outcome.json', {'native_steps': []})
        self.assertFalse(self.report()['ok'])
        self.assertTrue(V.in_warmup(self.root, self.root / 'p' / 'warmup' / 'f' / 'outcome.json'))
        self.assertFalse(V.in_warmup(self.root, self.root / 'warmup' / 'manifest.json'))

    def test_empty_and_scored_substitution_are_not_zeros(self):
        empty = Path(self.temp.name) / 'empty'; empty.mkdir()
        self.assertFalse(V.validate(empty, **self.kw)['ok'])
        self.assertFalse(V.validate(self.root, pilot=False, seed_path=self.kw['seed_path'])['ok'])

    def test_missing_and_duplicate_evaluation_cases_are_refused(self):
        p = self.evaluation() / 'flights/results.jsonl'
        text = p.read_text(); p.write_text(text + text.splitlines()[0] + '\n')
        self.assertFalse(self.report()['ok'])
        p.write_text(text)
        next((self.evaluation() / 'flights').glob('*/outcome.json')).unlink()
        self.assertFalse(self.report()['ok'])

    def test_outcome_and_row_cannot_be_changed_together(self):
        d = self.evaluation() / 'flights'
        rows = [json.loads(line) for line in (d / 'results.jsonl').read_text().splitlines()]
        first = rows[0]
        p = d / (first['family'] + '-' + str(first['seed'])) / 'outcome.json'
        o = json.loads(p.read_text()); o.update(goal_met=False, end_reason='timed_out'); write_json(p, o)
        first.update(goal_met=False, end_reason='timed_out')
        (d / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        report = self.report()
        self.assertFalse(report['ok'])
        self.assertIn('protected', report['errors'][0])

    def test_missing_heads_and_changed_source_are_refused(self):
        p = next(self.evaluation().glob('flights/*/broker.heads'))
        original = p.read_bytes(); p.unlink()
        self.assertFalse(self.report()['ok'])
        p.write_bytes(original)
        source = self.root / 'learn3-reach-b0/candidates/c0/source.py'
        source.write_text(source.read_text() + '# changed\n')
        self.assertFalse(self.report()['ok'])

    def test_timing_and_incomplete_truth_stop_analysis(self):
        p = next(self.evaluation().glob('flights/*/outcome.json'))
        o = json.loads(p.read_text())
        for step in o['native_steps']:
            step['decision_lag_s'] = .1             # a step after its observation: in time under the fixed delay
        write_json(p, o)
        self.assertTrue(self.report()['ok'])
        for step in o['native_steps']:
            step['decision_lag_s'] = COMMAND_DELAY_S    # ready after the deadline's stamp: a missed deadline
        write_json(p, o)
        report = self.report(); self.assertFalse(report['ok']); self.assertIn('timing', report['errors'][0])
        for step in o['native_steps']:
            step['decision_lag_s'] = .001
        del o['native_steps'][0]['true_vd_ms']; write_json(p, o)
        self.assertFalse(self.report()['ok'])

    def test_the_gate_judges_lateness_with_the_drivers_function(self):
        """The gate calls ladder.timing, so the two cannot disagree. A flight that function calls late is refused
        although its lags are ordinary."""
        from unittest import mock
        self.assertTrue(self.report()['ok'])
        with mock.patch.object(V, 'timing', lambda outcome: {'late': True}):
            report = self.report()
        self.assertFalse(report['ok']); self.assertIn('timing', report['errors'][0])

    def test_one_decision_a_whole_period_late_is_late(self):
        """A decision 1 s after its observation misses the fixed delay's deadline (round four, ruling 2), so the gate
        refuses the flight. Until 13 November 2026 this was the 1 s clause of the rule of that time."""
        p = next(self.evaluation().glob('flights/*/outcome.json'))
        o = json.loads(p.read_text())
        o['native_steps'][-1]['decision_lag_s'] = 1.001
        write_json(p, o)
        report = self.report()
        self.assertFalse(report['ok'])
        self.assertIn('timing', report['errors'][0])

    def test_land_success_cannot_use_estimated_instead_of_true_speed(self):
        p = next(self.root.glob('threat3-land-*/flights/*/outcome.json'))
        o = json.loads(p.read_text())
        o['native_steps'][-1].update(true_vd_ms=2.0, vd_ms=0.0)
        write_json(p, o)
        report = self.report()
        self.assertFalse(report['ok']); self.assertIn('landing success contradicts', report['errors'][0])

    def test_rehashed_prompt_cannot_leak_a_reserved_seed(self):
        d = self.root / 'learn3-reach-b0'
        p = d / 'candidates/c0/request.json'
        req = json.loads(p.read_text()); payload = json.loads(req['model_payload_json'])
        seed = json.loads(self.kw['seed_path'].read_text())['threat_evaluation']['reach']['close'][0]
        payload[1][1] += f' reserved evaluation seed {seed}'
        req['model_payload_json'] = json.dumps(payload)
        req['request_sha256'] = hashlib.sha256(req['model_payload_json'].encode()).hexdigest(); write_json(p, req)
        receipt = json.loads((d / 'candidates/c0/calls/1.json').read_text())
        receipt.update(model_payload_json=req['model_payload_json'], request_sha256=req['request_sha256'])
        write_json(d / 'candidates/c0/calls/1.json', receipt)
        usage = [json.loads(line) for line in (d / 'usage.jsonl').read_text().splitlines()]
        usage[0]['request_sha256'] = req['request_sha256']
        (d / 'usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in usage))
        report = self.report(); self.assertFalse(report['ok']); self.assertIn('leak', report['errors'][0])

    def test_a_learning_seed_in_a_request_is_refused(self):
        """Leak inspection, finding 1 (13 November 2026): a request names a learning layout by alias only, so the run's
        own learning seeds are forbidden in request text as well as the evaluation and held-out seeds."""
        d = self.root / 'learn3-reach-b0'
        p = d / 'candidates/c0/request.json'
        req = json.loads(p.read_text()); payload = json.loads(req['model_payload_json'])
        seeds = json.loads(self.kw['seed_path'].read_text())
        seed = next(iter(seeds['blocks'].values()))[0]
        seed = next(iter(seed.values()))
        payload[1][1] += f' trial episode matched-close-{seed}'
        req['model_payload_json'] = json.dumps(payload)
        req['request_sha256'] = hashlib.sha256(req['model_payload_json'].encode()).hexdigest(); write_json(p, req)
        receipt = json.loads((d / 'candidates/c0/calls/1.json').read_text())
        receipt.update(model_payload_json=req['model_payload_json'], request_sha256=req['request_sha256'])
        write_json(d / 'candidates/c0/calls/1.json', receipt)
        usage = [json.loads(line) for line in (d / 'usage.jsonl').read_text().splitlines()]
        usage[0]['request_sha256'] = req['request_sha256']
        (d / 'usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in usage))
        report = self.report(); self.assertFalse(report['ok']); self.assertIn('leak', report['errors'][0])

    def test_nonadoption_keeps_all_planned_zeros(self):
        root = Path(self.temp.name) / 'nonadopt'
        kw = fixture(root, nonadopt=True)
        report, snapshot = V.load_run(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        result = A.analyse_snapshot(snapshot, n_boot=100)
        for task in result['tasks'].values():
            self.assertEqual(task['planned_arm_outcomes'], 12)
            self.assertEqual(set(task['arm_means'].values()), {0})
            self.assertEqual(task['c0_one_shot']['mean'], 1)
        p = root / 'learn3-reach-b0/arms.json'; arms = json.loads(p.read_text())
        arms['arms']['A']['trials'] = arms['arms']['A']['trials'][:2]
        arms['arms']['A']['call_ids'] = arms['arms']['A']['call_ids'][:2]
        write_json(p, arms)
        report = V.validate(root, **kw)
        self.assertFalse(report['ok']); self.assertIn('incomplete run', report['errors'][0])

    def test_extra_phase_and_mixed_source_are_refused(self):
        p = self.evaluation() / 'manifest.json'
        m = json.loads(p.read_text()); m['git']['source']['sha256'] = 'f' * 64; write_json(p, m)
        self.assertFalse(self.report()['ok'])
        m['git']['source']['sha256'] = 'e' * 64; write_json(p, m)
        write_json(self.root / 'extra/manifest.json', m)
        self.assertFalse(self.report()['ok'])

    def test_gate_reads_the_load_record_the_phase_guard_writes(self):
        """The manifest comes from the phase guard (ardupilot/scored.py), so the gate must accept the guard's own
        load record and still refuse a phase above the limit or without a calibrated one. The numbers are synthetic."""
        from unittest import mock
        from ardupilot import scored as S
        with mock.patch.object(S, 'LOAD_LIMIT_1MIN', 6.0), \
                mock.patch.object(S.os, 'getloadavg', return_value=(1.5, 2.0, 2.5)):
            record = S.load_check(pilot=True)
        paths = sorted(self.root.glob('*/manifest.json'))
        self.assertTrue(paths)

        def write(load):
            for p in paths:
                m = json.loads(p.read_text())
                m['machine'] = {'concurrent_sitl_instances': [], 'parallel_limit': 4, 'load': load}
                write_json(p, m)
        write(record)
        report = self.report(); self.assertTrue(report['ok'], report['errors'])
        write({**record, 'load_average_1_5_15': [6.5, 2.0, 2.5]})
        report = self.report(); self.assertFalse(report['ok']); self.assertIn('load', report['errors'][0])
        with mock.patch.object(S, 'LOAD_LIMIT_1MIN', None):
            write(S.load_check(pilot=True))
        report = self.report(); self.assertFalse(report['ok']); self.assertIn('load', report['errors'][0])

    def test_gate_on_a_cluster_manifest(self):
        """Round four, ruling 7: on the cluster the load limit is not applied, and the gate asks instead for the node's
        name, at least 3 allowed cores and a recorded nice value of 0. A Mac manifest with nice 5 is refused too; a Mac
        manifest with no nice recorded still reads."""
        from unittest import mock
        from ardupilot import scored as S
        with mock.patch.dict(os.environ, {'PAPER3_PLATFORM': 'cluster'}), \
                mock.patch.object(S.os, 'getloadavg', return_value=(80.0, 70.0, 60.0)):
            load = S.load_check(pilot=False)
            plat = S.platform_record()
            prio = S.power_and_priority()
        paths = sorted(self.root.glob('*/manifest.json'))

        def write(platform=plat, nice=0, load=load, drop_nice=False):
            for p in paths:
                m = json.loads(p.read_text())
                machine = {'concurrent_sitl_instances': [], 'parallel_limit': 4, 'load': load, **prio, 'nice': nice}
                if drop_nice:
                    del machine['nice']
                m['machine'] = machine
                if platform is None:
                    m.pop('platform', None)
                else:
                    m['platform'] = platform
                set_route(p, m)
                write_json(p, m)

        def refused(word):
            report = self.report()
            self.assertFalse(report['ok'])
            self.assertIn(word, ' '.join(report['errors']))
        write(); report = self.report(); self.assertTrue(report['ok'], report['errors'])
        write(platform={**plat, 'node': ''}); refused('node')
        write(platform={**plat, 'cores_allowed': 2}); refused('cores')
        write(nice=5); refused('nice')
        write(drop_nice=True); refused('nice')
        write(load={**load, 'limit_1min': 4.89}); refused('load')
        write(platform=None); refused('load')       # no platform record reads as 'mac', whose load rule then fails
        mac_load = {'load_average_1_5_15': [.1, .1, .1], 'limit_1min': 1.0, 'cores': 1}
        write(platform=None, load=mac_load, drop_nice=True)
        report = self.report(); self.assertTrue(report['ok'], report['errors'])
        write(platform=None, load=mac_load, nice=5); refused('nice')

    def test_a_flight_without_the_command_delay_is_refused_even_when_kept_late(self):
        """Round four, ruling 2: a protocol 3 flight flew with the fixed delay. The gate checks it for every flight it
        counts or keeps, and a kept-late flight is not excused from it."""
        p = next(self.evaluation().glob('flights/*/outcome.json'))
        o = json.loads(p.read_text())
        del o['command_delay_s']
        write_json(p, o)
        report = self.report()
        self.assertFalse(report['ok'])
        self.assertIn('command delay', report['errors'][0])
        # a learning flight kept late after two set-aside attempts, with no delay recorded
        block = next(self.root.glob('learn3-*'))
        first = sorted((block / 'flights/first/P0').glob('*/outcome.json'))[0]
        o = json.loads(first.read_text())
        for st in o['native_steps']:
            st['decision_lag_s'] = 1.0
        del o['command_delay_s']
        write_json(first, o)
        self.late_copy(block, 1)
        self.late_copy(block, 2)
        report = self.report()
        self.assertFalse(report['ok'])
        self.assertIn('command delay', report['errors'][0])

    def test_a_run_configuration_without_the_delay_periods_is_refused(self):
        p = next(self.evaluation().glob('flights/run-config.json'))
        c = json.loads(p.read_text())
        del c['command_delay_periods']
        write_json(p, c)
        report = self.report()
        self.assertFalse(report['ok'])
        self.assertIn('command delay', report['errors'][0])

    def test_one_run_root_is_one_platform(self):
        """Round four, ruling 7: the manifests of a root name one platform, and on the cluster one partition and one
        CPU model. The node's name may differ, and is reported."""
        from unittest import mock
        from ardupilot import scored as S
        with mock.patch.dict(os.environ, {'PAPER3_PLATFORM': 'cluster'}), \
                mock.patch.object(S.os, 'getloadavg', return_value=(80.0, 70.0, 60.0)):
            load, plat, prio = S.load_check(pilot=False), S.platform_record(), S.power_and_priority()
        plat = {**plat, 'node': 'a1', 'slurm_job_partition': 'cpu', 'cpu_model': 'X'}
        paths = sorted(self.root.glob('*/manifest.json'))
        self.assertGreater(len(paths), 1)

        def write(**change):
            for i, p in enumerate(paths):
                m = json.loads(p.read_text())
                m['machine'] = {'concurrent_sitl_instances': [], 'parallel_limit': 4, 'load': load, **prio}
                m['platform'] = {**plat, 'node': f'a{i}'}
                if i == 0:
                    m['platform'].update(change)
                set_route(p, m)
                write_json(p, m)
        write()
        report = self.report(); self.assertTrue(report['ok'], report['errors'])
        self.assertGreater(len(report['nodes']), 1)           # differing nodes are fine and reported
        write(slurm_job_partition='gpu')
        report = self.report(); self.assertFalse(report['ok'])
        self.assertIn("partition 'gpu'", report['errors'][0]); self.assertIn("partition 'cpu'", report['errors'][0])
        write(cpu_model='Y')
        report = self.report(); self.assertFalse(report['ok']); self.assertIn("CPU 'Y'", report['errors'][0])
        # a Mac manifest among cluster ones
        m = json.loads(paths[0].read_text())
        m['platform'] = {'platform': 'mac'}; m['machine']['load'] = {'load_average_1_5_15': [.1, .1, .1], 'limit_1min': 1.0}
        set_route(paths[0], m)
        write_json(paths[0], m)
        report = self.report(); self.assertFalse(report['ok']); self.assertIn('platforms', report['errors'][0])

    def test_the_gate_checks_at_once(self):
        """Every manifest has at_once as an int from 1 to 4, the same in the whole root; the machine record lists at
        most at_once - 1 other simulators and a parallel_limit equal to at_once."""
        paths = sorted(self.root.glob('*/manifest.json'))
        self.assertGreater(len(paths), 1)

        def write(first=None, drop=False, others=(), limit=None, all_values=None):
            for i, p in enumerate(paths):
                m = json.loads(p.read_text())
                n = all_values if all_values is not None else 4
                if i == 0 and first is not None:
                    n = first
                m['at_once'] = n
                if drop and i == 0:
                    del m['at_once']
                m['machine'] = {**m['machine'], 'concurrent_sitl_instances': list(others),
                                'parallel_limit': limit if limit is not None else n}
                write_json(p, m)

        def refused(word):
            report = self.report(); self.assertFalse(report['ok']); self.assertIn(word, ' '.join(report['errors']))
        write(); report = self.report(); self.assertTrue(report['ok'], report['errors'])
        write(all_values=1); report = self.report(); self.assertTrue(report['ok'], report['errors'])
        write(first=2); refused('Mixed at_once')
        write(drop=True); refused('at_once')
        write(all_values=0); refused('at_once')
        write(all_values=5); refused('at_once')
        write(all_values=True); refused('at_once')
        write(all_values=1, others=(11,)); refused('may')
        write(all_values=2, others=(11, 12)); refused('may')
        write(all_values=2, limit=4); refused('parallel_limit')

    def test_the_phase_guard_waits_for_the_load_and_does_not_refuse(self):
        """Round three, ruling 6 (13 November 2026): above the limit a phase waits a minute at a time, as the check
        before each flight does, and records the wait. The loads are synthetic."""
        from unittest import mock
        from ardupilot import scored as S
        loads = iter([(7.0, 5.0, 4.0), (5.2, 5.0, 4.0), (4.1, 5.0, 4.0)])
        pauses = []
        with mock.patch.object(S, 'LOAD_LIMIT_1MIN', 4.89), mock.patch.object(S, '_pause', pauses.append), \
                mock.patch.object(S.os, 'getloadavg', lambda: next(loads)):
            record = S.load_check(pilot=False)
        self.assertEqual(pauses, [S.FLIGHT_LOAD_WAIT_S] * 2)
        self.assertEqual(record['waited_s'], 2 * S.FLIGHT_LOAD_WAIT_S)
        self.assertEqual(record['load_average_1_5_15'][0], 4.1)
        self.assertEqual(record['limit_status'], 'calibrated')

    def test_a_pilot_may_fly_the_leading_blocks_the_scheduler_recorded(self):
        # run_scored3.py --pilot --blocks 1 flies block 0 of each task. The development book holds 4.
        root = Path(self.temp.name) / 'short'
        kw = fixture(root, whole_book=True)
        report = V.validate(root, **kw)
        self.assertFalse(report['ok'])                      # with no schedule on file, the whole book is expected
        names = [C.phase_name('learn3', task, 0) for task in C.TASKS]
        schedule = root / 'logs' / 'schedule.json'
        write_json(schedule, {'pilot': True, 'learning': [[n, []] for n in names]})
        report, snapshot = V.load_run(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['checked']['learning blocks'], 3)
        self.assertEqual(len(A.analyse_snapshot(snapshot, n_boot=100)['primary']), 3)
        # Blocks must be the leading ones, the same number for every task, and no more than the book holds.
        write_json(schedule, {'pilot': True, 'learning': [[n, []] for n in names[:2]] + [['learn3-land-b1', []]]})
        self.assertFalse(V.validate(root, **kw)['ok'])
        write_json(schedule, {'pilot': True, 'learning': [[n, []] for n in names[:2]]})
        self.assertFalse(V.validate(root, **kw)['ok'])
        write_json(schedule, {'pilot': False, 'learning': [[n, []] for n in names]})
        self.assertFalse(V.validate(root, **kw)['ok'])

    def test_format_repair_is_an_accounted_separate_call(self):
        root = Path(self.temp.name) / 'format'
        kw = fixture(root, formatted=True)
        report, snapshot = V.load_run(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(A.analyse_snapshot(snapshot, n_boot=100)['unique_experiment_usage']['calls'], 9)
        next(root.glob('learn3-*/candidates/c0/calls/2.json')).unlink()
        self.assertFalse(V.validate(root, **kw)['ok'])

    def test_an_empty_reply_uses_its_slot_with_one_call_and_never_gets_a_repair(self):
        """Round three, ruling 8 (13 November 2026). A format-repaired candidate whose first reply was empty is refused;
        a failed slot with one call is accepted only if that reply was empty."""
        root = Path(self.temp.name) / 'empty'
        kw = fixture(root, formatted=True)
        self.assertTrue(V.validate(root, **kw)['ok'])
        p = next(root.glob('learn3-*/candidates/c0/calls/1.json'))
        receipt = json.loads(p.read_text()); receipt['reply_text'] = '  '; write_json(p, receipt)
        report = V.validate(root, **kw)
        self.assertFalse(report['ok']); self.assertIn('format repair after an empty reply', ' '.join(report['errors']))
        # One call, format failed: the reply must have been empty.
        root = Path(self.temp.name) / 'one'
        kw = fixture(root)
        d = root / 'learn3-reach-b0/candidates/c1'
        meta = json.loads((d / 'candidate.json').read_text())
        meta.update(format_valid=False, source_sha256=None)
        receipt = json.loads((d / 'calls/1.json').read_text()); receipt['reply_text'] = 'not the format'
        write_json(d / 'calls/1.json', receipt); write_json(d / 'candidate.json', meta); (d / 'source.py').unlink()
        report = V.validate(root, **kw)
        self.assertIn('got no repair call', ' '.join(report['errors']))

    def test_the_gate_recomputes_each_layouts_trial_verdict_from_the_decision_log(self):
        """The fixture's passing flights carry a decision by their candidate at every step, so Telohelm's trial rule
        passes on them. A block that records one layout as failed while the log passes it (and the trial as failed to
        match) is refused, and so is one whose log does not support a recorded pass."""
        self.assertEqual(V.validate(self.root, **self.kw)['ok'], True)
        path = self.root / 'learn3-reach-b0' / 'arms.json'
        data = json.loads(path.read_text())
        trial = data['arms']['D']['trials'][0]
        self.assertTrue(trial['passed'])
        trial['outcomes'][0]['trial_passed'], trial['passed'] = False, False
        data['arms']['D'].update(adopted=False, candidate_id=None, source_sha256=None)
        write_json(path, data)
        report = V.validate(self.root, **self.kw)
        self.assertFalse(report['ok'])
        self.assertIn("trial rule's verdict on its decision log", ' '.join(report['errors']))

    def test_a_missing_trial_library_is_refused_and_not_created(self):
        # Opening an absent library would create one. The gate changes no record.
        store = next(self.root.glob('learn3-reach-b0/flights/trial/*/*/library'))
        self.assertTrue((store / 'events.log').is_file())
        shutil.rmtree(store)
        report = V.validate(self.root, **self.kw)
        self.assertFalse(report['ok'])
        self.assertIn('trial library is missing', ' '.join(report['errors']))
        self.assertFalse(store.exists())
        # A store with its contract removed is refused too, and the contract is not written back.
        other = next(p for p in self.root.glob('learn3-land-b0/flights/trial/*/*/library'))
        (other / 'contract.json').unlink()
        self.assertFalse(V.validate(self.root, **self.kw)['ok'])
        self.assertFalse((other / 'contract.json').exists())


class DriverBlockTests(unittest.TestCase):
    """A block written by the driver itself, with its offline controls, read by the gate's learning check.

    The flights are the six recorded guard-only flights the driver's own tests use (ardupilot/testdata), copied in
    place of simulator flights, so no simulator and no model is involved. The scripted replies are the driver's pilot
    stub. The seeds are the development cohort of seeds-3.json, which no scored run uses."""

    @classmethod
    def setUpClass(cls):
        import zipfile
        cls.fixture_zip = V.ROOT / 'ardupilot/testdata/ladder-first-round.zip'
        if not cls.fixture_zip.exists():
            raise unittest.SkipTest('the driver test fixture is missing')
        cls.tmp = Path(tempfile.mkdtemp(prefix='p3-driver-block-'))
        with zipfile.ZipFile(cls.fixture_zip) as z:
            z.extractall(cls.tmp / 'fixture')
        delay_fixture(cls.tmp / 'fixture')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fake_fly(self, late=(), lag_s=.001):
        """Block.fly without a simulator. It copies the recorded cases for the list's family, writes the
        run-config.json and results.jsonl that battle.run writes, and sets every decision lag to lag_s (the recorded
        matched-close flight has one 1.001 s lag, which the 1 s rule would call late), except the cases in late."""
        from ardupilot import ladder as L, pack as P
        fixture = self.tmp / 'fixture'

        def fly(block, rel, sources, cases):
            from telohelm.runtime.library import Library
            out = block.root / rel
            out.mkdir(parents=True)
            family = 'P0' if cases[0].episode_id.startswith('matched') else 'P1'
            write_json(out / 'run-config.json', {'task': block.task, 'origin': rel, 'source': list(sources),
                                                 'speedup': block.speedup, 'command_delay_periods': COMMAND_DELAY_PERIODS,
                                                 'scenarios': [asdict(c) for c in cases]})
            library = Library(out / 'library', pack=P.PACKS[block.task].public)
            for code in sources:
                sha = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': code,
                                   'origin': {'imported_from': rel}})
                library.set_status(sha, 'adopted', 'test')
            outcomes, rows = {}, []
            for c in cases:
                shutil.copytree(fixture / family / c.episode_id, out / c.episode_id)
                o = json.loads((out / c.episode_id / 'outcome.json').read_text())
                for s in o['native_steps']:
                    s['decision_lag_s'] = 1.0 if c.episode_id in late else lag_s
                (out / c.episode_id / 'outcome.json').write_text(json.dumps(o))
                t = L.timing(o)
                block.timing.append({'flight': f'{rel}/{c.episode_id}', **t})
                if t['late'] and block.late_flights == 'stop':
                    raise L.InfrastructureFault(f'{rel}/{c.episode_id}: late')
                outcomes[c.episode_id] = o
                family_name, seed = c.episode_id.rsplit('-', 1)
                rows.append({'family': family_name, 'seed': int(seed), 'goal_met': o['goal_met'],
                             'end_reason': o['end_reason']})
            (out / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            return outcomes
        return fly

    def build(self, name, *, stub='pilot', **fly):
        """Run phase_learn3 for the development reach block 0 under the guard, as the scheduler would."""
        import argparse
        from unittest import mock
        from ardupilot import ladder as L, scored as S
        root = self.tmp / name
        (root / 'logs').mkdir(parents=True)
        S.use_protocol(3)
        self.addCleanup(S.use_protocol, 1)
        args = argparse.Namespace(task='reach', block=0, out=root / 'learn3-reach-b0', speedup=1.0, instance=10,
                                  pilot=True, stub=stub, record_late_flights=False)
        self.warmups, self.events = [], []

        def fake_warmup(folder, task, case, *, speedup, instance):
            """The warm-up flight without a simulator: a folder of the shape a flight leaves, with files the gate
            would refuse if it read them."""
            self.warmups.append((Path(folder), task, case.episode_id, speedup, instance))
            self.events.append('warmup')
            self.plant_warmup(Path(folder) / L.WARMUP_DIR, case.episode_id)
            return {}
        patches = [mock.patch.object(L.Block, 'fly', lambda b, rel, sources, cases: self.fake_fly(**fly)(b, rel, sources, cases)),
                   mock.patch.object(L, 'fly_warmup', fake_warmup),
                   mock.patch.object(S, 'machine_check', lambda *a: {'concurrent_sitl_instances': [], 'parallel_limit': 4}),
                   # A synthetic limit, high enough that the test host's load never matters. It measures nothing.
                   mock.patch.object(S, 'LOAD_LIMIT_1MIN', 1e6)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(S.phase_learn3(args), 0)
        (root / 'logs' / 'learn3-reach-b0.done').write_text('test\n')
        return root

    def plant_warmup(self, folder, episode_id):
        """What a warm-up flight leaves, with content the gate would reject if it opened any of it."""
        (folder / episode_id).mkdir(parents=True)
        write_json(folder / episode_id / 'outcome.json', {'native_steps': []})
        for name in ('episode.log', 'broker.log', 'episode.heads', 'x-request.json', 'usage.jsonl'):
            (folder / episode_id / name).write_text('not a valid record\n')
        write_json(folder / 'manifest.json', {'junk': True})
        write_json(folder / 'warmup.json', {'warmup': True, 'case': episode_id})

    def gate(self, root):
        seed_path = V.C.SEED_PATH
        seeds = json.loads(seed_path.read_bytes())
        seeds['_sha256'], seeds['_path'] = C.sha(seed_path), str(seed_path)
        return V.Run(root.resolve(), seeds, True, V.ROOT / 'PROTOCOL-3-DRAFT.md')

    def block_dir(self, root):
        return root / 'learn3-reach-b0'

    def edit(self, path, change):
        value = json.loads(path.read_text())
        change(value)
        write_json(path, value)

    def refused(self, root, text):
        with self.assertRaises(V.InvalidEvidence) as caught:
            self.gate(root).learn('reach', 0)
        self.assertIn(text, str(caught.exception))

    def test_driver_block_passes_the_learning_check(self):
        root = self.build('ok')
        block = self.block_dir(root)
        learn = self.gate(root).learn('reach', 0)
        self.assertEqual(set(learn['arms_record']['arms']), set(C.ARMS))
        # The cases the note lists, each present in what the driver wrote: a request identity that is not a call
        # identity, call receipts for the format repair, a list payload, scripted rows with no real call or served
        # label, and no format-request.json.
        f1 = json.loads((block / 'candidates/f1/request.json').read_text())
        meta = json.loads((block / 'candidates/f1/candidate.json').read_text())
        self.assertNotEqual(f1['request_id'], meta['call_ids'][0])
        self.assertEqual(len(meta['call_ids']), 2)
        self.assertTrue((block / 'candidates/f1/calls/2.json').exists())
        self.assertFalse(list(block.rglob('format-request.json')))
        self.assertIsInstance(json.loads(f1['model_payload_json']), list)
        usage = [json.loads(line) for line in (block / 'usage.jsonl').read_text().splitlines()]
        self.assertTrue(all(row['real_model_call'] is False and row['served_by'] == 'scripted' for row in usage))
        self.assertTrue(all(row['requested_settings']['model'] is None for row in usage))
        # A repair after a lost slot shows the flights of the last candidate that flew, and its own arm's earlier ones.
        rc2 = json.loads((block / 'candidates/rC2/request.json').read_text())['context_flights']
        self.assertTrue(any('flights/trial/c0/threat/' in f for f in rc2))

    def test_the_manifest_the_guard_wrote_binds_the_gate(self):
        root = self.build('manifest')
        manifest = json.loads((self.block_dir(root) / 'manifest.json').read_text())
        self.assertEqual(manifest['args']['task'], 'reach')
        self.assertTrue(manifest['pilot'])
        self.assertEqual(manifest['machine']['load']['limit_status'], 'calibrated')

    def test_call_receipts_must_match_the_candidates_calls(self):
        root = self.build('receipts')
        calls = self.block_dir(root) / 'candidates/f1/calls'
        original = (calls / '2.json').read_bytes()
        (calls / '2.json').unlink()
        self.refused(root, 'call receipts')
        (calls / '2.json').write_bytes(original)
        write_json(calls / '3.json', {})
        self.refused(root, 'call receipts')
        (calls / '3.json').unlink()
        self.edit(calls / '1.json', lambda r: r.update(call_id='another'))
        self.refused(root, 'receipt does not match')

    def test_request_identity_is_not_the_call_identity_but_must_be_unique(self):
        root = self.build('identity')
        path = self.block_dir(root) / 'candidates/f1/request.json'
        self.edit(path, lambda r: r.update(request_id='reach-b0-c0'))
        self.refused(root, 'request identity')

    def test_a_scored_row_needs_a_real_call_and_a_served_label(self):
        root = self.build('usage')
        path = self.block_dir(root) / 'usage.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['real_model_call'], rows[0]['served_by'] = True, None
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.refused(root, 'served-model label')
        rows[0]['served_by'] = 'a-served-model'
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.gate(root).learn('reach', 0)
        # A scored run refuses the scripted rows the pilot accepts.
        run = self.gate(root)
        run.pilot = False
        rows[0]['real_model_call'] = False
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        with self.assertRaises(V.InvalidEvidence):
            run.learn('reach', 0)

    def test_settings_come_from_the_receipts_and_a_scored_run_needs_them(self):
        root = self.build('settings')
        run = self.gate(root)
        run.learn('reach', 0)
        self.assertEqual(run.settings, set())
        run.pilot = False
        with self.assertRaises(V.InvalidEvidence) as caught:
            run.requested_settings(self.block_dir(root), {}, None)
        self.assertIn('settings are missing', str(caught.exception))
        settings = {'model': 'a-model', 'max_tokens': 8}
        self.assertEqual(json.loads(run.requested_settings(self.block_dir(root), {C.SETTINGS_FIELD: settings}, None)), settings)
        with self.assertRaises(V.InvalidEvidence):
            run.requested_settings(self.block_dir(root), {C.SETTINGS_FIELD: {'max_tokens': 8}}, None)
        with self.assertRaises(V.InvalidEvidence):
            run.requested_settings(self.block_dir(root), {C.SETTINGS_FIELD: settings}, {C.SETTINGS_FIELD: {'model': 'b'}})
        # A scripted reply's settings name no model. A pilot takes them as no settings, and a scored run refuses them.
        scripted = {C.SETTINGS_FIELD: {'provider': 'scripted', 'model': None}, 'real_model_call': False}
        with self.assertRaises(V.InvalidEvidence):
            run.requested_settings(self.block_dir(root), scripted, None)
        run.pilot = True
        self.assertIsNone(run.requested_settings(self.block_dir(root), scripted, None))

    def test_a_repair_may_show_its_arms_earlier_trial_flights_and_must_show_the_previous_ones(self):
        root = self.build('context')
        block = self.block_dir(root)
        self.gate(root).learn('reach', 0)
        path = block / 'candidates/rD2/request.json'
        original = json.loads(path.read_text())['context_flights']
        earlier = [f for f in original if 'flights/trial/c1/' in f]
        previous = [f for f in original if 'flights/trial/rD1/' in f]
        self.assertTrue(earlier and previous)
        # The driver's own request shows the first-round flights, c1's trial flights and rD1's. These edits change what
        # the learner had seen; what the text showed is kept to the flights that are still in its context.
        shown_before = json.loads((block / 'candidates/rD2/request.json').read_text())['shown_flights']

        def set_context(flights):
            for name in ('request.json', 'calls/1.json'):
                self.edit(block / 'candidates/rD2' / name, lambda r: r.update(
                    context_flights=flights if name == 'request.json' else r.get('context_flights'),
                    shown_flights=[f for f in shown_before if f in flights]))
        set_context([f for f in original if f not in previous])
        self.refused(root, 'omits its trial evidence')
        set_context([f for f in original if f not in earlier])
        self.gate(root).learn('reach', 0)
        foreign = [f for f in json.loads((block / 'candidates/rC1/request.json').read_text())['context_flights']]
        set_context(original + foreign)
        self.refused(root, 'foreign trial')
        set_context(original + ['flights/first/P0/matched-close-4000001'])
        self.refused(root, 'foreign trial')

    def set_shown(self, cid, change):
        """Change shown_flights in a candidate's request and in its first call's receipt, which must agree."""
        for name in ('request.json', 'calls/1.json'):
            self.edit(self.block_dir(self.root_for_shown) / 'candidates' / cid / name,
                      lambda r: r.update(shown_flights=change(list(r['shown_flights']))))

    def test_the_gate_checks_which_flights_a_request_shows(self):
        root = self.root_for_shown = self.build('shown')
        block = self.block_dir(root)
        self.gate(root).learn('reach', 0)
        self.original = {cid: block / f'candidates/{cid}/request.json' for cid in ('c0', 'c1', 'rD2')}
        saved = {cid: (p.read_bytes(), (p.parent / 'calls/1.json').read_bytes()) for cid, p in self.original.items()}
        shown = lambda cid: json.loads((block / f'candidates/{cid}/request.json').read_text())['shown_flights']
        # The driver's own record: a repair shows trial flights only, and a first or fresh request first-round flights.
        self.assertTrue(all('flights/trial/' in f for f in shown('rD2')))
        self.assertTrue(all('flights/first/P1/' in f for f in shown('c1')))
        foreign = next(f for f in shown('c0'))                       # a matched first-round flight
        trial = next(f for f in shown('rD1'))                        # a trial flight of arm D (and C's, for c1)
        rd2_first = next(f for f in json.loads((block / 'candidates/rD2/request.json').read_text())['context_flights']
                         if 'flights/first/P1/' in f)
        for cid, change, text in (
                # A first request showing a trial flight, or a flight of the other list, is refused.
                ('c1', lambda s: s + [foreign], 'shows a flight its learner never saw'),
                ('c0', lambda s: s + [trial], 'shows a flight its learner never saw'),
                # A repair showing a first-round flight again is refused, even one in its own context.
                ('rD2', lambda s: s + [rd2_first], 'foreign or first-round flights'),
                # A repair must show something from the trial just flown.
                ('rD2', lambda s: [f for f in s if 'flights/trial/rD1/' not in f], 'nothing from the trial just flown'),
                ('rD2', lambda s: s + s[:1], 'not a list of distinct folders')):
            with self.subTest(candidate=cid, text=text):
                self.set_shown(cid, change)
                self.refused(root, text)
                self.original[cid].write_bytes(saved[cid][0])
                (self.original[cid].parent / 'calls/1.json').write_bytes(saved[cid][1])
                self.gate(root).learn('reach', 0)

    def test_a_receipt_may_not_disagree_with_its_request_about_what_was_shown(self):
        root = self.root_for_shown = self.build('shown-receipt')
        path = self.block_dir(root) / 'candidates/rD2/calls/1.json'
        self.edit(path, lambda r: r.update(shown_flights=r['shown_flights'][:-1]))
        self.refused(root, 'disagree on shown_flights')
        self.edit(path, lambda r: r.pop('shown_flights'))
        self.refused(root, 'shown_flights is missing')

    def test_a_trial_passes_when_every_layout_passed_the_trial_rule(self):
        root = self.build('verdict')
        path = self.block_dir(root) / 'arms.json'
        # The driver records the trial rule's verdict for each layout, and the recorded block passes.
        arms = json.loads(path.read_text())['arms']
        self.assertIn('trial_passed', arms['D']['trials'][0]['outcomes'][0])
        self.gate(root).learn('reach', 0)
        self.edit(path, lambda a: a['arms']['D']['trials'][0].update(passed=True))
        self.refused(root, 'trial/adoption evidence')

    def test_the_trial_rule_is_telohelms_and_not_the_goal_alone(self):
        """The owner's ruling: a trial passes by Telohelm's component_trial, as in scored-2. It also asks that every
        step was flown under the candidate, that no command was refused and that no help was requested. So a layout
        can meet its goal and fail the trial. The gate takes the driver's verdict for that layout and counts it, and
        refuses a verdict of passed that the flight's own record contradicts."""
        from ardupilot import pack as P
        run = self.gate(self.build('definitions'))
        ids = ['a', 'b', 'c']
        success = P.TASKS['reach'].success
        wanted = [{'episode_id': i, 'goal_met': True, 'end_reason': success} for i in ids]
        clean = {i: {'goal_met': True, 'end_reason': success, 'refusals': [], 'help_requests': []} for i in ids}

        def trial(verdicts, passed):
            return {'passed': passed, 'outcomes': [{**w, 'trial_passed': v} for w, v in zip(wanted, verdicts)]}
        run.check_trial('x', trial([True] * 3, True), wanted, clean, 'reach')
        # Every goal met, one layout failed the rule: the trial fails, and the gate counts the layout.
        before = run.checked['trial layouts failed with the goal met']
        run.check_trial('x', trial([True, True, False], False), wanted, clean, 'reach')
        self.assertEqual(run.checked['trial layouts failed with the goal met'], before + 1)
        with self.assertRaises(V.InvalidEvidence):
            run.check_trial('x', trial([True, True, False], True), wanted, clean, 'reach')
        # A layout recorded as passed against a refused command, a help request or an unmet goal is refused.
        for change in ({'refusals': [{'t': 3}]}, {'help_requests': [{'t': 2}]}, {'end_reason': 'timed_out'}):
            with self.assertRaises(V.InvalidEvidence):
                run.check_trial('x', trial([True] * 3, True), wanted, {**clean, 'b': {**clean['b'], **change}}, 'reach')
        unmet = [dict(w) for w in wanted]
        unmet[1]['goal_met'] = False
        with self.assertRaises(V.InvalidEvidence):
            run.check_trial('x', {'passed': True, 'outcomes': [{**w, 'trial_passed': True} for w in unmet]}, unmet)
        # The verdict is required.
        with self.assertRaises(V.InvalidEvidence):
            run.check_trial('x', {'passed': True, 'outcomes': [dict(w) for w in wanted]}, wanted, clean, 'reach')

    def evaluate(self, root, phase, *, lag_s=.001, late=(), instance=10):
        """phase_eval3 for c0's source with the simulator replaced, as the scheduler would call it."""
        import argparse
        from unittest import mock
        from ardupilot import battle, scored as S
        block = self.block_dir(root)
        h = json.loads((block / 'candidates/c0/candidate.json').read_text())['source_sha256']
        out = root / C.phase_name(phase, 'reach', 0, h)

        def fly(target, task, source, origin, cases, speedup, instance, before_flight=None,
                command_delay_periods=None):
            for c in cases:
                step = {'t': 1, 'decision_lag_s': 1.0 if c.episode_id in late else lag_s}
                write_json(target / c.episode_id / 'outcome.json',
                           with_delay({'native_steps': [dict(step) for _ in range(3)]}))
        args = argparse.Namespace(phase=phase, task='reach', block=0, learning=block, source=h, out=out, speedup=1.0,
                                  instance=instance, pilot=True)
        self.eval_calls = calls = []

        def recording_fly(target, task, source, origin, cases, speedup, instance, before_flight=None,
                          command_delay_periods=None):
            self.before_flight = before_flight
            self.delays = getattr(self, 'delays', []) + [command_delay_periods]
            calls.append((Path(target), [c.episode_id for c in cases]))
            self.events.append('flights')
            fly(target, task, source, origin, cases, speedup, instance)
        with mock.patch.object(battle, 'run', recording_fly), mock.patch.object(S, 'machine_check', lambda *a: {'concurrent_sitl_instances': [], 'parallel_limit': 4}), \
                mock.patch.object(S, 'LOAD_LIMIT_1MIN', 1e6), contextlib.redirect_stdout(io.StringIO()):
            code = S.phase_eval3(args)
        (root / 'logs' / (out.name + '.done')).write_text('test\n')
        return code, out, h

    def test_an_evaluation_manifest_names_its_learning_block_as_the_driver_writes_it(self):
        root = self.build('eval')
        code, out, h = self.evaluate(root, 'threat3')
        self.assertEqual(code, 0)
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertIn('learning', manifest['args'])
        self.assertNotIn('learn3', manifest['args'])
        arms = json.loads((self.block_dir(root) / 'arms.json').read_text())['arms']
        learn = self.gate(root).learn('reach', 0)
        roles = C.source_roles(arms, learn['candidates'], include_c0=True)
        run = self.gate(root)
        folder, cases = run.evaluation('threat3', 'reach', 0, h, roles[h], C.evaluation_cases)
        self.assertEqual(folder.resolve(), out.resolve())
        self.assertEqual(len(cases), 6)
        # The gate still refuses a manifest that names another block.
        self.edit(out / 'manifest.json', lambda m: m['args'].update(learning=str(root / 'learn3-reach-b1')))
        with self.assertRaises(V.InvalidEvidence):
            self.gate(root).evaluation('threat3', 'reach', 0, h, roles[h], C.evaluation_cases)

    def test_an_evaluation_phase_with_a_late_flight_exits_with_a_failure(self):
        root = self.build('eval-late')
        late = C.evaluation_cases(json.loads(V.C.SEED_PATH.read_text()), 'reach', True)[1].episode_id
        code, out, h = self.evaluate(root, 'threat3', late={late})
        self.assertEqual(code, 1)
        rows = json.loads((out / 'timing.json').read_text())
        self.assertEqual([r['flight'] for r in rows if r['late']], [late])

    # -- the warm-up flight (notes/TAKEOVER-20261111.md, 12 November 2026, 9:25 am, ruling 6) ----------------------

    def test_a_learning_block_flies_one_warmup_first_from_the_development_book_and_the_gate_ignores_it(self):
        root = self.build('warm-learn')
        block = self.block_dir(root)
        folder, task, case, speedup, instance = self.warmups[0]
        self.assertEqual(len(self.warmups), 1)
        self.assertEqual((folder, task, speedup, instance), (block, 'reach', 1.0, 10))
        seeds = json.loads(V.C.SEED_PATH.read_text())
        self.assertEqual(case, seeds['pilot']['heldout']['reach']['calm'][0] and f"calm-{seeds['pilot']['heldout']['reach']['calm'][0]}")
        from protocol import timing_preflight3 as T
        self.assertNotIn(int(case.rsplit('-', 1)[1]), T.reserved_seeds(seeds))
        # Its folder is there, and in no timing row and no flight of the block.
        self.assertTrue((block / 'warmup' / case / 'outcome.json').exists())
        self.assertEqual(self.events, ['warmup'])       # flown once, and before the block's own flights (which are faked)
        # The gate passes the block with the junk folder in place, and reads the same flights as without it.
        learn = self.gate(root).learn('reach', 0)
        self.assertTrue(learn['candidates'])
        shutil.rmtree(block / 'warmup')
        self.assertEqual(self.gate(root).learn('reach', 0)['candidates'].keys(), learn['candidates'].keys())

    def test_an_evaluation_phase_flies_the_warmup_before_its_own_flights_and_changes_nothing_else(self):
        root = self.build('warm-eval')
        self.events.clear()         # the learning block's own warm-up is not this phase's
        code, out, h = self.evaluate(root, 'threat3')
        self.assertEqual(code, 0)
        seeds = json.loads(V.C.SEED_PATH.read_text())
        own = [c.episode_id for c in C.evaluation_cases(seeds, 'reach', True)]
        calm = f"calm-{seeds['pilot']['heldout']['reach']['calm'][0]}"
        # The first flight of the process is the warm-up, then the phase's own flights in their own order.
        self.assertEqual(self.events, ['warmup', 'flights'])
        self.assertEqual(self.warmups[-1][:3], (out, 'reach', calm))
        self.assertEqual(self.eval_calls, [(out / 'flights', own)])
        # Its timing is in its own record and in no row of timing.json.
        record = json.loads((out / 'warmup' / 'warmup.json').read_text())
        self.assertEqual((record['warmup'], record['case']), (True, calm))
        self.assertTrue((out / 'warmup' / calm / 'outcome.json').exists())
        self.assertEqual([r['flight'] for r in json.loads((out / 'timing.json').read_text())], own)
        # The manifest names the phase's own cases only.
        self.assertEqual(json.loads((out / 'manifest.json').read_text())['args']['cases'], own)
        # The gate takes the phase with the warm-up folder in it.
        arms = json.loads((self.block_dir(root) / 'arms.json').read_text())['arms']
        learn = self.gate(root).learn('reach', 0)
        roles = C.source_roles(arms, learn['candidates'], include_c0=True)
        folder, cases = self.gate(root).evaluation('threat3', 'reach', 0, h, roles[h], C.evaluation_cases)
        self.assertEqual([c.episode_id for c in cases], own)


    def test_an_evaluation_phase_flies_in_its_instances_order_and_the_gate_checks_it(self):
        """Round two, ruling 2: simulator k of the four starts k quarters of the way down the list."""
        root = self.build('order')
        code, out, h = self.evaluate(root, 'threat3', instance=12)
        self.assertEqual(code, 0)
        seeds = json.loads(V.C.SEED_PATH.read_text())
        own = [c.episode_id for c in C.evaluation_cases(seeds, 'reach', True)]
        half = len(own) // 2
        flown = own[half:] + own[:half]
        self.assertEqual(self.eval_calls, [(out / 'flights', flown)])
        self.assertTrue(callable(self.before_flight))
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertEqual((manifest['args']['cases'], manifest['args']['flight_order']), (own, flown))
        arms = json.loads((self.block_dir(root) / 'arms.json').read_text())['arms']
        learn = self.gate(root).learn('reach', 0)
        roles = C.source_roles(arms, learn['candidates'], include_c0=True)
        folder, cases = self.gate(root).evaluation('threat3', 'reach', 0, h, roles[h], C.evaluation_cases)
        self.assertEqual([c.episode_id for c in cases], flown)
        self.edit(out / 'manifest.json', lambda m: m['args'].update(flight_order=own))
        with self.assertRaises(V.InvalidEvidence):
            self.gate(root).evaluation('threat3', 'reach', 0, h, roles[h], C.evaluation_cases)


class FlightOrder(unittest.TestCase):
    def test_the_preflight_and_the_scored_run_share_one_order(self):
        from protocol import timing_preflight3 as T
        self.assertEqual(C.FLIGHT_INSTANCES, T.INSTANCES)
        for n in (6, 10, 24):
            for instance in C.FLIGHT_INSTANCES:
                self.assertEqual(C.flight_order(n, instance), T.case_order(n, instance, T.FOUR_AT_ONCE))
                self.assertEqual(sorted(C.flight_order(n, instance)), list(range(n)))
        self.assertEqual(C.flight_order(10, 10), list(range(10)))
        self.assertEqual(C.flight_order(24, 11)[0], 6)
        self.assertEqual(C.flight_order(10, 13)[:2], [7, 8])     # the preflight's order: start 3 * 10 // 4 = 7
        self.assertEqual(C.flight_order(5, 99), list(range(5)))   # a development instance flies the listed order


class FlightGate(unittest.TestCase):
    """Round two, ruling 2: the load is checked before every counted flight, and a phase that waited is released
    through a shared lock a quarter of a second after the last release."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / 'run'
        (self.root / 'logs').mkdir(parents=True)

    def test_spacing_is_the_preflights(self):
        from ardupilot import scored as S
        from protocol import timing_preflight3 as T
        self.assertEqual(S.RELEASE_SPACING_S, T.DECISION_PERIOD_S / len(T.INSTANCES))

    def test_a_release_right_after_another_waits_the_rest_of_the_spacing(self):
        from unittest import mock
        from ardupilot import scored as S
        waits = []
        lock = self.root / 'logs' / S.FLIGHT_RELEASE_FILE
        with mock.patch.object(S, '_pause', waits.append):
            self.assertEqual(S.release_spaced(lock), 0.0)       # nothing released before
            second = S.release_spaced(lock)
        self.assertTrue(0.2 < second <= S.RELEASE_SPACING_S, second)
        self.assertEqual(waits, [second])

    def test_the_gate_waits_while_the_load_is_high_and_then_releases_through_the_lock(self):
        from unittest import mock
        import os
        from ardupilot import scored as S
        loads = iter([(9.0,) * 3, (9.0,) * 3, (0.5,) * 3, (0.5,) * 3])
        pauses = []
        out = self.root / 'threat3-x'
        out.mkdir()
        with mock.patch.object(S, 'LOAD_LIMIT_1MIN', 1.0), mock.patch.object(os, 'getloadavg', lambda: next(loads)), \
                mock.patch.object(S, '_pause', pauses.append):
            record = S.flight_gate(out)(None)
        self.assertEqual(record['waited_s'], 2 * S.FLIGHT_LOAD_WAIT_S)
        self.assertEqual(pauses[:2], [S.FLIGHT_LOAD_WAIT_S] * 2)
        self.assertTrue((self.root / 'logs' / S.FLIGHT_RELEASE_FILE).exists())
        self.assertEqual((record['load_1min'], record['limit_1min']), (0.5, 1.0))

    def test_no_wait_no_lock(self):
        from unittest import mock
        from ardupilot import scored as S
        out = self.root / 'threat3-y'
        out.mkdir()
        with mock.patch.object(S, 'LOAD_LIMIT_1MIN', 1e6):
            record = S.flight_gate(out)(None)
        self.assertEqual((record['waited_s'], record['release_spacing_wait_s']), (0, 0.0))
        self.assertFalse((self.root / 'logs' / S.FLIGHT_RELEASE_FILE).exists())

    def test_each_release_records_the_local_time(self):
        """Round three, ruling 5: a flight flown after a late wake can be found from its own record."""
        import datetime
        from unittest import mock
        from ardupilot import scored as S
        out = self.root / 'threat3-z'
        out.mkdir()
        with mock.patch.object(S, 'LOAD_LIMIT_1MIN', 1e6):
            record = S.flight_gate(out)(None)
        when = datetime.datetime.fromisoformat(record['time'])
        self.assertIsNotNone(when.tzinfo)
        self.assertLess(abs((datetime.datetime.now().astimezone() - when).total_seconds()), 5)

    def test_power_and_priority_are_read_without_failing(self):
        from ardupilot import scored as S
        record = S.power_and_priority()
        self.assertEqual(set(record), {'power_source', 'nice'})
        self.assertIsInstance(record['nice'], int)

if __name__ == '__main__':
    unittest.main()

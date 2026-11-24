"""Build H7 (rulings 52 and 53): the scored run flown as three runs of one task each. The gate takes the three roots as one run
and the analysis computes the nine intervals once over them.

The gate's own synthetic pilot fixture is used: one root with the three tasks, and three roots with one task each, made by the
same code. No model, simulator or network."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import analysis3 as A
from protocol import contract3 as C
from protocol import test_protocol3 as T
from protocol import validate3 as V


def setUpModule():
    T.setUpModule()


def tearDownModule():
    T.tearDownModule()


class Split(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p3-h7-', dir='/private/tmp' if Path('/private/tmp').is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.roots = {}
        self.kw = None
        book = None
        for task in C.TASKS:
            self.roots[task] = self.base / f'scored-run-{task}'
            self.kw = T.fixture(self.roots[task], tasks=(task,), seed_book=book)
            book = book or self.kw['seed_path']
            self.kw = {**self.kw, 'seed_path': book, 'protocol_path': self.kw['protocol_path']}
        self.book = book
        self.three = [self.roots[t] for t in C.TASKS]

    def whole(self):
        root = self.base / 'one-root'
        kw = T.fixture(root, seed_book=self.book)
        return root, kw

    def load(self, roots=None, **more):
        return V.load_runs(roots or self.three, **{**self.kw, **more})

    def refused(self, roots, text):
        report, snapshot = self.load(roots)
        self.assertFalse(report['ok'], report)
        self.assertIsNone(snapshot)
        self.assertIn(text, ' | '.join(report['errors']))

    # ---- the gate
    def test_three_one_task_roots_are_accepted_as_one_run_and_the_record_lists_them_with_their_input_hashes(self):
        report, snapshot = self.load()
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual([r['task'] for r in report['roots']], list(C.TASKS))
        for r, root in zip(report['roots'], self.three):
            self.assertEqual(r['root'], str(root))
            self.assertTrue(r['input_sha256'])
            self.assertEqual(len(r['inputs_aggregate_sha256']), 64)
        self.assertEqual(report['checked']['learning blocks'], 3)
        self.assertEqual(sorted(snapshot['learning']), sorted(C.TASKS))
        self.assertTrue(all(len(k.split(':')) >= 2 for k in snapshot['input_sha256']))

    def test_one_root_flying_all_three_tasks_is_accepted_as_before(self):
        root, kw = self.whole()
        report, snapshot = V.load_runs(root, **kw)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual(report['tasks'], list(C.TASKS))
        self.assertTrue(V.validate(root, **kw)['ok'])

    def test_one_root_of_one_task_alone_is_refused(self):
        report = V.validate(self.roots['reach'], **self.kw)
        self.assertFalse(report['ok'])
        self.assertIn('flies only', ' '.join(report['errors']))

    def test_two_roots_of_the_same_task_are_refused(self):
        again = self.base / 'scored-run-reach-again'
        T.fixture(again, tasks=('reach',), seed_book=self.book)
        self.refused([self.roots['reach'], again, self.roots['reach3d']], 'must fly')

    def test_a_missing_task_is_refused(self):
        self.refused(self.three[:2], 'three different run roots')
        self.refused([self.three[0], self.three[0], self.three[1]], 'three different run roots')

    def test_a_root_whose_schedule_names_two_tasks_is_refused(self):
        T.write_json(self.roots['land'] / 'logs' / 'schedule.json', {'pilot': True, 'at_once': 4, 'tasks': ['reach3d', 'land'],
                                                                      'learning': [[C.phase_name('learn3', 'land', 0), []]]})
        self.refused(self.three, '')

    def test_a_root_with_no_schedule_on_file_is_refused(self):
        (self.roots['land'] / 'logs' / 'schedule.json').unlink()
        report, _ = self.load()
        self.assertFalse(report['ok'])

    def test_roots_with_different_source_fingerprints_are_refused(self):
        for manifest in self.roots['land'].glob('*/manifest.json'):
            m = json.loads(manifest.read_text())
            m['git']['source'] = {'sha256': 'f' * 64, 'files': 99}
            T.write_json(manifest, m)
        self.refused(self.three, 'source_fingerprints')

    def test_roots_in_different_modes_or_routes_are_refused(self):
        for manifest in self.roots['land'].glob('*/manifest.json'):
            m = json.loads(manifest.read_text())
            m['sandbox'] = {'route': 'another-route'}
            T.write_json(manifest, m)
        report, _ = self.load()
        self.assertFalse(report['ok'])

    def share_a_message_id(self):
        for task in ('reach', 'land'):
            usage = self.roots[task] / C.phase_name('learn3', task, 0) / 'usage.jsonl'
            rows = [json.loads(line) for line in usage.read_text().splitlines()]
            rows[0]['message_id'] = 'msg_shared_between_two_roots'
            usage.write_text(''.join(json.dumps(r) + '\n' for r in rows))

    def test_a_message_id_in_two_roots_is_refused_though_each_root_passes_alone(self):
        self.share_a_message_id()
        for task in ('reach', 'land'):
            self.assertTrue(V.validate(self.roots[task], allow_partial=True, **self.kw)['ok'])
        self.refused(self.three, 'message ids are in both')

    def test_a_root_that_fails_alone_fails_the_three_and_says_which(self):
        folder = next(self.roots['reach3d'].glob('threat3-*'))
        shutil.rmtree(folder)
        report, snapshot = self.load()
        self.assertFalse(report['ok'])
        self.assertTrue(any(str(self.roots['reach3d']) in e for e in report['errors']), report['errors'])

    def parts(self):
        out = []
        for root in self.three:
            rep, snap = V.load_run(root, allow_partial=True, **self.kw)
            self.assertTrue(rep['ok'], rep['errors'])
            out.append((root, rep, snap))
        return out

    def test_in_a_scored_run_every_stop_must_come_from_the_flag_and_be_at_most_20(self):
        def with_stops(*stops):
            parts = self.parts()
            for (root, rep, snap), stop in zip(parts, stops):
                rep['session_spend_stops'] = [{'event': 'start', 'time': 't', 'spend_limit_usd': stop[0], 'spend_limit_from_flag': stop[1]}]
            return parts
        report, snapshot = V.combine_roots(with_stops((20, True), (20, True), (19.5, True)), False)
        self.assertTrue(report['ok'])
        for bad in ((20.01, True), (60, True), (20, False), (None, True)):
            with self.subTest(bad=bad), self.assertRaises(V.InvalidEvidence):
                V.combine_roots(with_stops((20, True), bad, (20, True)), False)
        V.combine_roots(with_stops((60, False), (60, False), (60, False)), True)       # a pilot's stops are not judged

    def test_a_session_event_that_names_other_tasks_than_the_schedule_is_refused(self):
        rows = [{'time': 't', 'event': 'start', 'reason': None, 'spend_limit_usd': 20, 'spend_limit_from_flag': True, 'tasks': ['reach', 'land']}]
        T.write_json(self.roots['reach'] / 'logs' / 'pauses.jsonl', rows[0])           # one object per line
        (self.roots['reach'] / 'logs' / 'pauses.jsonl').write_text(json.dumps(rows[0]) + '\n')
        report, _ = V.load_run(self.roots['reach'], allow_partial=True, **self.kw)
        self.assertFalse(report['ok'])
        self.assertIn('flew the tasks', ' '.join(report['errors']))

    # ---- the analysis
    def test_the_nine_intervals_are_the_same_from_one_root_of_three_tasks_and_from_three_roots(self):
        root, kw = self.whole()
        one = A.analyse(root, pilot=True, n_boot=100, **{k: v for k, v in kw.items() if k != 'pilot'})
        three = A.analyse(self.three, pilot=True, n_boot=100, **{k: v for k, v in self.kw.items() if k != 'pilot'})
        self.assertEqual((len(three['primary']), len(three['secondary_intervals'])), (3, 6))
        for part in ('primary', 'secondary_intervals'):
            self.assertEqual(json.dumps(three[part], sort_keys=True), json.dumps(one[part], sort_keys=True))
        for key in ('tasks', 'pooled_ladder_steps', 'rq4_close_minus_distant', 'secondary', 'kept_late_evaluation',
                    'evaluation_phases_flown_again', 'learning_blocks_set_aside', 'unique_experiment_usage', 'unique_hazard_flights',
                    'unique_retention_flights', 'unique_experiment_flights', 'unique_learning_flights', 'requested_models', 'bootstrap'):
            self.assertEqual(json.dumps(three[key], sort_keys=True), json.dumps(one[key], sort_keys=True), key)
        names = lambda r: {k: v['classification'] for k, v in {**r['secondary_intervals'], **r['primary']}.items()}
        self.assertEqual(names(three), names(one))
        self.assertEqual(A.report_lines(three)[:14], A.report_lines(one)[:14])

    def test_the_spend_is_reported_for_each_root_and_in_total(self):
        three = A.analyse(self.three, pilot=True, n_boot=50, **{k: v for k, v in self.kw.items() if k != 'pilot'})
        sb = three['spend_by_root']
        self.assertEqual([r['task'] for r in sb['roots']], list(C.TASKS))
        total = sum(sb['list_cost_usd_by_root'].values())
        self.assertAlmostEqual(sb['list_cost_usd_total'], total, places=6)
        self.assertGreater(sb['list_cost_usd_total'], 0)
        root, kw = self.whole()
        one = A.analyse(root, pilot=True, n_boot=50, **{k: v for k, v in kw.items() if k != 'pilot'})
        self.assertEqual(len(one['spend_by_root']['roots']), 1)
        self.assertAlmostEqual(one['spend_by_root']['list_cost_usd_total'], sb['list_cost_usd_total'], places=6)
        self.assertIn('Spend by run root', '\n'.join(A.report_lines(three)))
        self.assertEqual(three['roots'][0]['task'], 'reach')

    def test_the_run_once_record_is_written_into_each_root_naming_all_three_and_refused_if_any_has_one(self):
        out = self.base / 'out'
        paths = A.write_run_record(self.three, out, C.BOOT_N, C.BOOT_SEED)
        self.assertEqual(len(paths), 3)
        records = [json.loads((r / A.RUN_RECORD).read_text()) for r in self.three]
        self.assertTrue(all(rec == records[0] for rec in records))
        self.assertEqual(records[0]['roots'], [str(r.resolve()) for r in self.three])
        with self.assertRaises(FileExistsError):
            A.check_not_run_before(self.three)
        for keep in range(3):                          # any one of the three having a record refuses all
            for r in self.three:
                (r / A.RUN_RECORD).unlink(missing_ok=True)
            (self.three[keep] / A.RUN_RECORD).write_text('{}\n')
            with self.assertRaises(FileExistsError):
                A.check_not_run_before(self.three)
            with self.assertRaises(FileExistsError):
                A.write_run_record(self.three, out, C.BOOT_N, C.BOOT_SEED)
            self.assertEqual(sorted(p.parent.name for p in self.base.glob('*/' + A.RUN_RECORD)), [self.three[keep].name])   # no partial record left

    def test_a_scored_analysis_of_three_roots_refuses_if_any_has_a_record_before_the_gate_runs(self):
        (self.three[1] / A.RUN_RECORD).write_text('{}\n')
        with self.assertRaises(FileExistsError):
            A.analyse(self.three, out=self.base / 'out')


if __name__ == '__main__':
    unittest.main()

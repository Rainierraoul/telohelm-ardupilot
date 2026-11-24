"""Build I3 (ruling 57, point 5; finding 5 of the review of fix H0): tests only. They cover what the review found nobody tested
in set_aside3's evaluation rule and run_scored3's task subset. No code under test is changed."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from protocol import contract3 as C
from protocol import run_scored3 as RS
from protocol import set_aside3 as SA
from protocol import test_fix_h3 as H

EVAL_RETAIN = 'retain3-reach-b4-' + '0' * 64
EVAL_THREAT = H.EVAL
ALL_THREE = list(C.TASKS)


class IsEvaluation(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(SA, 'processes_naming', return_value=[])
        p.start()
        self.addCleanup(p.stop)

    def test_both_evaluation_kinds_are_evaluation_and_a_learning_block_is_not(self):
        self.assertTrue(SA.is_evaluation(EVAL_THREAT))
        self.assertTrue(SA.is_evaluation(EVAL_RETAIN))
        self.assertFalse(SA.is_evaluation(H.LEARN))

    def test_a_retention_phase_with_a_late_row_is_not_a_crash(self):
        root = H.root_with(EVAL_RETAIN, [H.LATE_ROW])
        with self.assertRaisesRegex(SystemExit, 'use --reason late'):
            SA.set_aside(root, EVAL_RETAIN, 'crashed')

    def test_a_retention_phase_late_is_set_aside_as_late(self):
        root = H.root_with(EVAL_RETAIN, [H.LATE_ROW])
        dest = SA.set_aside(root, EVAL_RETAIN, 'late')
        self.assertEqual(json.loads((dest / 'receipt.json').read_text())['reason'], 'late')


class KeptLateWithoutTheFalseMark(unittest.TestCase):
    """The driver writes `kept_late` only on the rows it keeps late. The on-time row of a kept-late attempt has no such field."""
    def setUp(self):
        p = mock.patch.object(SA, 'processes_naming', return_value=[])
        p.start()
        self.addCleanup(p.stop)

    def test_the_on_time_row_has_no_kept_late_field_and_the_phase_killed_afterwards_is_a_crash(self):
        for phase in (EVAL_THREAT, EVAL_RETAIN):
            with self.subTest(phase=phase):
                rows = [{**H.LATE_ROW, 'kept_late': True}, dict(H.ON_TIME)]
                self.assertNotIn('kept_late', rows[1])
                root = H.root_with(phase, rows, failed=False)
                with mock.patch.object(SA, 'scheduler_alive', return_value=False):
                    dest = SA.set_aside(root, phase, 'crashed')
                self.assertEqual(json.loads((dest / 'receipt.json').read_text())['reason'], 'crashed')

    def test_a_late_row_with_no_kept_late_field_is_still_late(self):
        root = H.root_with(EVAL_THREAT, [dict(H.LATE_ROW), dict(H.ON_TIME)])
        with self.assertRaisesRegex(SystemExit, 'use --reason late'):
            SA.set_aside(root, EVAL_THREAT, 'crashed')


class OldRootsAndEvents(unittest.TestCase):
    """A root made before --tasks existed has no `tasks` in its schedule.json. The scheduler reads that as all three. Every session
    writes the tasks it flies into its start or resume event."""

    class Stop(Exception):
        pass

    def setUp(self):
        temp = Path(tempfile.mkdtemp(prefix='p3-i3-'))
        self.addCleanup(shutil.rmtree, temp, True)
        self.root = temp / 'run'
        for p in (mock.patch.object(RS.S, 'start_refusal', return_value=None),
                  mock.patch.object(RS.Runner3, 'pool', side_effect=self.Stop)):
            p.start()
            self.addCleanup(p.stop)

    def session(self, *flags, reason=None):
        argv = ['run', str(self.root), '--pilot', '--blocks', '2', *flags] + (['--reason', reason] if reason else [])
        try:
            with contextlib.redirect_stdout(io.StringIO()):          # the scheduler prints its notes
                return RS.main(argv)
        except self.Stop:
            return 'flying'            # the check passed and the first pool was reached

    def events(self):
        return [json.loads(l) for l in (self.root / 'logs' / 'pauses.jsonl').read_text().splitlines()]

    def schedule_path(self):
        return self.root / 'logs' / 'schedule.json'

    def test_the_start_and_the_resume_event_each_name_the_tasks_flown(self):
        self.assertEqual(self.session('--tasks', 'land,reach'), 'flying')
        self.assertEqual(self.session('--tasks', 'land,reach', reason='again'), 'flying')
        first, second = self.events()
        self.assertEqual((first['event'], second['event']), ('start', 'resume'))
        self.assertEqual(first['tasks'], ['reach', 'land'])         # in the contract's order, whatever order was typed
        self.assertEqual(second['tasks'], ['reach', 'land'])

    def test_a_session_of_all_three_names_all_three(self):
        self.assertEqual(self.session(), 'flying')
        self.assertEqual(self.events()[0]['tasks'], ALL_THREE)

    def test_a_schedule_with_no_tasks_is_read_as_all_three_and_resumes(self):
        self.assertEqual(self.session(), 'flying')
        schedule = json.loads(self.schedule_path().read_text())
        del schedule['tasks']
        self.schedule_path().write_text(json.dumps(schedule, indent=1) + '\n')
        self.assertEqual(self.session(reason='again'), 'flying')
        self.assertEqual(self.events()[-1]['tasks'], ALL_THREE)

    def test_a_schedule_with_no_tasks_is_not_resumed_for_one_task(self):
        self.assertEqual(self.session(), 'flying')
        schedule = json.loads(self.schedule_path().read_text())
        del schedule['tasks']
        self.schedule_path().write_text(json.dumps(schedule, indent=1) + '\n')
        before = self.schedule_path().read_text()
        self.assertEqual(self.session('--tasks', 'reach', reason='again'), 3)       # refused: the root's schedule is all three
        self.assertEqual(self.schedule_path().read_text(), before)
        self.assertEqual(len(self.events()), 1)


class SubsetOrder(unittest.TestCase):
    OUT = Path('/tmp/none')

    def names(self, jobs):
        return [n for n, _ in jobs]

    def task_of(self, job):
        args = job[1]
        return args[args.index('--task') + 1]

    def test_every_two_task_subset_is_the_full_list_filtered_to_those_tasks(self):
        everything = RS.learning_jobs(self.OUT, range(8))
        for pair in (('reach', 'land'), ('reach', 'reach3d'), ('reach3d', 'land'), ('land', 'reach')):
            with self.subTest(pair=pair):
                got = RS.learning_jobs(self.OUT, range(8), tasks=list(pair))
                self.assertEqual(self.names(got), [n for n, args in everything if args[args.index('--task') + 1] in pair])
                self.assertEqual(len(got), 16)
                self.assertEqual({self.task_of(j) for j in got}, set(pair))

    def test_a_subset_keeps_each_jobs_name_and_arguments(self):
        everything = dict(RS.learning_jobs(self.OUT, range(8)))
        for name, args in RS.learning_jobs(self.OUT, range(8), tasks=['reach3d', 'land']):
            self.assertEqual(args, everything[name])


class TheJointOrder(unittest.TestCase):
    """The order task_order draws for each block of the joint run, pinned. A one-task root takes its blocks in this order, so the
    scored run's three roots and the one-root run fly each task's blocks the same way."""
    PINNED = {0: ['reach', 'reach3d', 'land'], 1: ['reach', 'land', 'reach3d'], 2: ['reach', 'land', 'reach3d'],
              3: ['land', 'reach3d', 'reach'], 4: ['reach', 'reach3d', 'land'], 5: ['reach3d', 'reach', 'land'],
              6: ['reach3d', 'reach', 'land'], 7: ['reach3d', 'reach', 'land']}

    def test_block_0_and_the_blocks_where_it_differs_from_the_contracts_order(self):
        self.assertEqual(RS.task_order(0), ALL_THREE)
        for block in (1, 3, 5):
            self.assertNotEqual(RS.task_order(block), ALL_THREE)
        for block, want in self.PINNED.items():
            self.assertEqual(RS.task_order(block), want, block)

    def test_the_order_comes_from_the_seed_and_the_block_only(self):
        self.assertEqual(RS.ORDER_SEED, 20261113)
        self.assertEqual([RS.task_order(b) for b in range(8)], [self.PINNED[b] for b in range(8)])
        self.assertEqual(RS.task_order(3), RS.task_order(3))
        self.assertEqual(sorted(RS.task_order(3)), sorted(ALL_THREE))

    def test_the_joint_job_list_follows_it_and_a_one_task_list_is_that_task_in_block_order(self):
        jobs = RS.learning_jobs(Path('/tmp/none'), range(4))
        want = [f'learn3-{t}-b{b}' for b in range(4) for t in self.PINNED[b]]
        self.assertEqual([n for n, _ in jobs], want)
        for task in ALL_THREE:
            self.assertEqual([n for n, _ in RS.learning_jobs(Path('/tmp/none'), range(4), tasks=[task])], [f'learn3-{task}-b{b}' for b in range(4)])
        got = RS.learning_jobs(Path('/tmp/none'), range(4), tasks=['land', 'reach'])
        self.assertEqual([n for n, _ in got], [n for n in want if '-reach3d-' not in n])


if __name__ == '__main__':
    unittest.main()

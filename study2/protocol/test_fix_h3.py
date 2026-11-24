"""Ruling 52: the late rule of set_aside3 applies to evaluation phases only, and the scheduler flies a subset of tasks."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from protocol import run_scored3 as RS
from protocol import set_aside3 as SA

LEARN = 'learn3-reach-b4'
EVAL = 'threat3-reach-b4-' + '0' * 64


def root_with(phase: str, rows: list, failed: bool = True) -> Path:
    root = Path(tempfile.mkdtemp()) / 'run'
    (root / 'logs').mkdir(parents=True)
    (root / phase).mkdir()
    (root / phase / 'timing.json').write_text(json.dumps(rows))
    log = f'2026-11-18 10:00:00 start {phase} on instance 10\n'
    if failed:
        log += f'2026-11-18 10:30:00 FAILED {phase} on instance 10 (exit 1)\n'
    (root / 'logs' / 'scheduler.log').write_text(log)
    return root


LATE_ROW = {'flight': 'x/1', 'late': True, 'attempt': 1}
ON_TIME = {'flight': 'x/1', 'late': False, 'attempt': 2}


class LateRule(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(SA, 'processes_naming', return_value=[])
        p.start()
        self.addCleanup(p.stop)

    def test_learning_block_with_a_late_call_flown_again_is_a_crash(self):
        root = root_with(LEARN, [LATE_ROW, ON_TIME])
        dest = SA.set_aside(root, LEARN, 'crashed')
        self.assertEqual(json.loads((dest / 'receipt.json').read_text())['reason'], 'crashed')

    def test_evaluation_phase_with_a_late_row_is_not_a_crash(self):
        root = root_with(EVAL, [LATE_ROW])
        with self.assertRaisesRegex(SystemExit, 'use --reason late'):
            SA.set_aside(root, EVAL, 'crashed')

    def test_evaluation_phase_kept_late_and_then_killed_is_a_crash(self):
        rows = [{**LATE_ROW, 'kept_late': True}, {**ON_TIME, 'kept_late': False}]
        root = root_with(EVAL, rows, failed=False)
        with mock.patch.object(SA, 'scheduler_alive', return_value=False):
            dest = SA.set_aside(root, EVAL, 'crashed')
        self.assertEqual(json.loads((dest / 'receipt.json').read_text())['reason'], 'crashed')

    def test_evaluation_phase_late_is_still_set_aside_as_late(self):
        root = root_with(EVAL, [LATE_ROW])
        dest = SA.set_aside(root, EVAL, 'late')
        self.assertEqual(json.loads((dest / 'receipt.json').read_text())['reason'], 'late')


class Tasks(unittest.TestCase):
    def test_a_subset_keeps_the_order_drawn_for_all_three(self):
        out = Path('/tmp/none')
        everything = RS.learning_jobs(out, range(6))
        reach = RS.learning_jobs(out, range(6), tasks=['reach'])
        self.assertEqual([n for n, _ in reach], [n for n, _ in everything if n.startswith('learn3-reach-')])
        self.assertEqual(len(reach), 6)

    def test_plan_with_tasks_lists_only_that_task(self):
        with mock.patch('builtins.print') as out:
            self.assertEqual(RS.main(['plan', '/tmp/p3-plan-h', '--pilot', '--blocks', '2', '--tasks', 'land']), 0)
        printed = ' '.join(' '.join(map(str, c.args)) for c in out.call_args_list)
        self.assertIn('learning: 2 phases', printed)
        self.assertNotIn('learn3-reach-', printed)
        self.assertIn('learn3-land-b1', printed)

    def test_a_bad_task_list_is_refused(self):
        for bad in ('reach,reach', 'fly', ''):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                RS.main(['plan', '/tmp/p3-plan-h', '--pilot', '--blocks', '1', '--tasks', bad])


if __name__ == '__main__':
    unittest.main()

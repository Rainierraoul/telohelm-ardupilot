"""Tests for the planning simulation (job 1, 11 November 2026). Offline and fast.

Run from paper3/:  .venv/bin/python -B -m unittest protocol.test_ladder_sim3
The two tests that read scored-2 need its folder: they use the LADDER_RUNS environment
variable, else the main checkout's copy, and are skipped (and say so) when it is absent."""
import hashlib
import inspect
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from protocol import analysis3 as A
from protocol import ladder_pooled3 as P
from protocol import ladder_sim3 as L

RUNS = Path(os.environ.get('LADDER_RUNS', '/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-2'))
AUDIT = Path(__file__).resolve().parents[2] / L.AUDIT


def fake_runs(root, adopted_at):
    """Write 24 fake summaries and a matching audit file. adopted_at: list of (adopted, attempts)."""
    hashes = {}
    for i, (ad, k) in enumerate(adopted_at):
        rel = f'learn-x-b{i}-threat/run/summary.json'
        raw = json.dumps({'checks': {'candidate_passed_trial_and_adopted': ad}, 'learning_attempts': k}).encode()
        p = root / rel
        p.parent.mkdir(parents=True)
        p.write_bytes(raw)
        hashes['paper3/runs/scored-2/' + rel] = hashlib.sha256(raw).hexdigest()
    audit = root / 'audit.json'
    audit.write_text(json.dumps({'input_sha256': hashes}))
    return audit


PATTERN = [(True, 1)] * 16 + [(True, 2)] * 5 + [(True, 3)] + [(False, 3)] * 2


class Counts(unittest.TestCase):
    def test_counts_from_summaries_and_hash_check(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            audit = fake_runs(root, PATTERN)
            self.assertEqual(L.read_learning_counts(root, audit)[:4], (16, 24, 6, 8))
            victim = next(root.glob('learn-x-b3-threat/run/summary.json'))
            victim.write_text(victim.read_text() + ' ')
            with self.assertRaises(ValueError):
                L.read_learning_counts(root, audit)

    def test_wrong_number_of_files_stops(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            audit = fake_runs(root, PATTERN[:23])
            with self.assertRaises(ValueError):
                L.read_learning_counts(root, audit)

    @unittest.skipUnless(RUNS.exists(), 'scored-2 folder not present')
    def test_real_summaries_give_16_of_24_and_6_of_8(self):
        first, n, rescued, failures, detail = L.read_learning_counts(RUNS, AUDIT)
        self.assertEqual((first, n, rescued, failures), (16, 24, 6, 8))
        self.assertEqual(detail, {'adopted at attempt 1': 16, 'adopted at attempt 2': 5,
                                  'adopted at attempt 3': 1, 'not adopted at attempt 3': 2})

    @unittest.skipUnless(RUNS.exists(), 'scored-2 folder not present')
    def test_fit_uses_the_counts_read(self):
        raw, counts, q, rd, tp, m0 = P.setup(RUNS, AUDIT)
        self.assertEqual((counts['first_adoptions'], counts['runs'], counts['rescued'], counts['initial_failures']), (16, 24, 6, 8))
        self.assertAlmostEqual(q, (16 / 24 - m0) / (tp - m0))
        self.assertAlmostEqual(rd, ((1 - 0.25 ** 0.5) - m0) / (tp - m0))

    def test_fit_formula_on_fixed_pools(self):
        pools = [(np.array([0.3, 0.4]), np.array([0.7, 0.8]))]
        q, rho, t, m = L.fit_q_rho(pools, 9, 24, 2, 8)
        self.assertAlmostEqual(q, (9 / 24 - m) / (t - m))
        self.assertAlmostEqual(rho, ((1 - 0.75 ** 0.5) - m) / (t - m))
        self.assertTrue(0 < q < 1 and 0 < rho < 1)


class Classifier(unittest.TestCase):
    def test_agrees_with_analysis3_on_fixed_cases(self):
        cases = [  # (ci95, ci90, expected class) at margin 0.20
            ((0.05, 0.18), (0.06, 0.17), 'different_and_equivalent'),
            ((0.05, 0.40), (0.08, 0.35), 'different_not_equivalent'),
            ((-0.15, 0.15), (-0.10, 0.10), 'equivalent_not_different'),
            ((-0.30, 0.30), (-0.25, 0.25), 'unresolved'),
            ((-0.30, -0.05), (-0.25, -0.08), 'different_not_equivalent'),
        ]
        for ci95, ci90, want in cases:
            self.assertEqual(A.classify(0.0, ci95, ci90)['class'], want)

    def test_classify_draws_uses_both_intervals_and_nests(self):
        rng = np.random.default_rng(5)
        for centre, spread in ((0.05, 0.05), (0.0, 0.1), (0.3, 0.05), (-0.1, 0.2)):
            draws = rng.normal(centre, spread, 2000)
            ci95, ci90 = A.interval(draws), A.interval(draws, 0.90)
            self.assertTrue(ci95[0] <= ci90[0] <= ci90[1] <= ci95[1])
            for m in (0.20, 0.10):
                self.assertEqual(L.classify_draws(centre, draws, m), A.classify(centre, ci95, ci90, m)['class'])

    def test_no_second_copy_of_the_rule(self):
        for mod in (L, P):
            src = inspect.getsource(mod)
            self.assertNotIn('def classify(', src)
            self.assertNotIn('def classify_margin', src)

    def test_pooled_rule_is_analysis3s(self):
        # one task wholly above 0 and one wholly below: the pooled class is withheld
        rng = np.random.default_rng(1)
        pts = {t: np.zeros(4) for t in A.C.TASKS}
        drs = {t: rng.normal(0, 0.01, (4, 500)) for t in A.C.TASKS}
        y = np.zeros((4, 8, 6)); y[1, :4] = 1  # reach: B above A; the others flat
        steps = {}
        for t in A.C.TASKS:
            yy = y if t == 'reach' else (1 - y if t == 'land' else np.zeros((4, 8, 6)))
            steps[t], pts[t], drs[t] = A.comparisons(yy, ['close'] * 2 + ['middle'] * 2 + ['wide'] * 2, rng, 500)
        out = A.pooled_comparisons(pts, drs, steps)
        self.assertEqual(out['B-A']['task_dependent'], out['B-A']['classification']['class'] == 'task_dependent')


class Determinism(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        P.G.clear()
        P.G.update(raw={t: (rng.uniform(0, 0.3, 8), rng.uniform(0.3, 0.9, 6)) for t in A.C.TASKS}, q=0.5, rd=0.4)

    def cell(self, d, seed, name, sims=3):
        part = Path(d) / name
        ss = np.random.SeedSequence(seed).spawn(1)[0]
        P.cell_worker((0, (0.5, 0.0, 24), ss, sims, 50, part, None))
        return part.read_bytes()

    def test_same_seed_same_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            a = self.cell(d, 20261114, 'a.json')
            b = self.cell(d, 20261114, 'b.json')
            c = self.cell(d, 20261115, 'c.json')
            self.assertEqual(a, b)
            self.assertNotEqual(a, c)

    def test_worker_count_does_not_change_bytes(self):
        import multiprocessing as mp
        ctx = mp.get_context('fork')
        ss = np.random.SeedSequence(7).spawn(2)
        with tempfile.TemporaryDirectory() as d:
            outs = []
            for w in (1, 2):
                jobs = [(i, (0.5, 0.0, 24), ss[i], 2, 40, Path(d) / f'w{w}-{i}.json', None) for i in range(2)]
                with ctx.Pool(w) as pool:
                    list(pool.imap_unordered(P.cell_worker, jobs))
                outs.append([(Path(d) / f'w{w}-{i}.json').read_bytes() for i in range(2)])
            self.assertEqual(outs[0], outs[1])

    def test_dev_mode_is_reproducible(self):
        job = (0, (0.5, 0.0), np.random.SeedSequence(3).spawn(1)[0], 5, 4)
        self.assertEqual(json.dumps(P.dev_worker(job)), json.dumps(P.dev_worker(job)))


class Model(unittest.TestCase):
    def test_simulate_task_shapes(self):
        rng = np.random.default_rng(2)
        P0 = L.widen(np.array([0.1, 0.2, 0.0]), 0.5); P1 = L.widen(np.array([0.7, 0.9]), 0.5)
        Y, info = L.simulate_task(rng, 10, P0, P1, 0.6, 0.0, 0.4, 0.5)
        self.assertEqual(Y.shape, (4, 10, 24))
        self.assertTrue(np.isin(Y, [0, 1]).all())
        self.assertEqual(info['adopted'][0], 10)  # A adopts c0
        self.assertTrue((info['adopted'] <= 10).all())


# ---- the corrected model of 19 November (ruling 72) ----

POOLS_JSON = Path(__file__).resolve().parents[1] / 'reproduction' / 'ladder-pooled3-20261111.json'


def blocks(kinds, n, P0, P1, seed=1, q=0.5, rho_c=0.0, rho_d=0.5):
    rng = np.random.default_rng(seed)
    tally = {'weighted': 0, 'unweighted': 0}
    rows = [L.simulate_block_kinds(rng, P0, P1, q, rho_c, rho_d, kinds, tally) for _ in range(n)]
    return rows, tally


GOOD0 = np.array([[0.5, 0.5, 0.5], [0.6, 0.6, 0.6]])
GOOD1 = np.array([[0.7, 0.7, 0.7], [0.8, 0.8, 0.8]])


class Interval(unittest.TestCase):
    def test_known_values(self):
        lo, hi = L.clopper_pearson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 1 - 0.025 ** 0.1, places=9)  # exact for k = 0
        lo, hi = L.clopper_pearson(5, 10)
        self.assertAlmostEqual(lo, 0.1870860, places=6)  # textbook table
        self.assertAlmostEqual(hi, 0.8129140, places=6)
        lo, hi = L.clopper_pearson(10, 10)
        self.assertEqual(hi, 1.0)
        self.assertAlmostEqual(lo, 0.025 ** 0.1, places=9)

    def test_bisection_agrees_with_the_library_route(self):
        for k, n in ((2, 44), (17, 34), (9, 12), (5, 10)):
            a, b = L.clopper_pearson(k, n), L.clopper_pearson_bisect(k, n)
            self.assertAlmostEqual(a[0], b[0], places=9)
            self.assertAlmostEqual(a[1], b[1], places=9)

    def test_the_nine_values(self):
        v = L.kind_values()
        for name, (k, n) in L.KIND_COUNTS.items():
            lo, sh, hi = v[name]
            self.assertEqual(sh, k / n)
            self.assertTrue(0 < lo < sh < hi < 1)
        combos = L.kind_combinations()
        self.assertEqual(len(combos), 27)
        self.assertEqual(len(set(combos)), 27)


class KindRates(unittest.TestCase):
    def test_kind_rates_by_seeded_frequency(self):
        pf, pr, pa = 0.5, 0.9, 0.6
        n = 20000
        rows, _ = blocks((pf, pr, pa), n, GOOD0, GOOD1, seed=11, rho_c=0.2)
        c0 = np.mean([r[4] for r in rows])
        d_first = np.mean([r[5] for r in rows])
        fail = [r for r in rows if not r[4]]
        b = np.mean([r[1][1] >= 0 for r in fail]); c = np.mean([r[1][2] >= 0 for r in fail])
        d_all = np.mean([r[1][3] >= 0 for r in rows])
        a_all = np.mean([r[1][0] >= 0 for r in rows])

        def se(p, m):
            return 5 * math.sqrt(p * (1 - p) / m)
        self.assertAlmostEqual(c0, pf, delta=se(pf, n))
        self.assertAlmostEqual(d_first, pf, delta=se(pf, n))
        self.assertAlmostEqual(b, 1 - (1 - pf) ** 2, delta=se(0.75, len(fail)))  # fresh candidates: pi_f
        self.assertAlmostEqual(c, 1 - (1 - pr) ** 2, delta=se(0.99, len(fail)) + 0.002)  # repairs: pi_r
        self.assertAlmostEqual(d_all, pf + (1 - pf) * (1 - (1 - pr) ** 2), delta=se(0.995, n) + 0.002)
        self.assertAlmostEqual(a_all, 1 - (1 - pa) ** 3, delta=se(0.936, n))  # all three of A's slots use pi_A

    def test_extreme_rates_are_deterministic(self):
        rows, _ = blocks((0.0, 1.0, 0.0), 50, GOOD0, GOOD1)
        for procs, (a, b, c, d), f, calls, c0_ok, d_first in rows:
            self.assertFalse(c0_ok); self.assertFalse(d_first)
            self.assertEqual((a, b), (-1, -1))   # nothing passes at pi_f = 0 and pi_A = 0
            self.assertGreaterEqual(c, 0); self.assertGreaterEqual(d, 0)  # a repair always passes at pi_r = 1
        rows, _ = blocks((1.0, 0.0, 1.0), 50, GOOD0, GOOD1)
        for procs, (a, b, c, d), f, calls, c0_ok, d_first in rows:
            self.assertTrue(c0_ok); self.assertTrue(d_first)
            self.assertTrue(a == b == c >= 0 and d >= 0)  # c0 shared by A, B and C

    def test_repair_that_keeps_c0_is_a_copy_of_c0(self):
        rows, _ = blocks((0.0, 1.0, 1.0), 200, GOOD0, GOOD1, rho_c=-1.0)
        for procs, (a, b, c, d), *_ in rows:
            self.assertEqual(procs[a].tolist(), procs[c].tolist())  # A adopted c0, C's repair keeps it
            self.assertNotEqual(a, c)


class ArmAFallback(unittest.TestCase):
    def test_a_adopts_c0_when_its_zone_free_trial_passes(self):
        rows, _ = blocks((0.0, 0.5, 1.0), 100, GOOD0, GOOD1)
        for procs, (a, b, c, d), f, calls, *_ in rows:
            self.assertGreaterEqual(a, 0); self.assertEqual(b, -1)

    def test_a_slots_all_use_pi_a_not_pi_f(self):
        rows, _ = blocks((1.0, 0.5, 0.0), 40, GOOD0, GOOD1)  # pi_A = 0, pi_f = 1
        self.assertEqual(sum(r[1][0] >= 0 for r in rows), 0)  # A adopts in 0 of 40 blocks
        rows, _ = blocks((0.0, 0.5, 1.0), 40, GOOD0, GOOD1)  # pi_A = 1, pi_f = 0
        self.assertEqual(sum(r[1][0] >= 0 for r in rows), 40)

    def test_a_falls_back_to_the_fresh_candidates_with_pi_a(self):
        n = 20000
        rows, _ = blocks((0.0, 0.5, 0.5), n, GOOD0, GOOD1, seed=3)
        got = np.mean([r[1][0] >= 0 for r in rows])
        self.assertAlmostEqual(got, 1 - 0.5 ** 3, delta=5 * math.sqrt(0.875 * 0.125 / n))  # c0, f1, f2

    def test_a_adopts_nothing_when_all_three_candidates_fail(self):
        rows, _ = blocks((1.0, 0.5, 0.0), 100, GOOD0, GOOD1)
        self.assertTrue(all(r[1][0] == -1 for r in rows))


class SharedFreshStream(unittest.TestCase):
    def test_one_call_and_one_candidate_per_fresh_slot(self):
        rows, _ = blocks((0.0, 0.0, 0.0), 20, GOOD0, GOOD1)  # every trial fails
        for r in rows:
            # calls: c0 and c1 (ruling 85: c1 is one call), two shared fresh slots, two C repairs, two D repairs
            self.assertEqual(r[3], 2 + 2 + 2 + 2)
            # flights: first round 6, c0 on two trials 6, each fresh slot on two trials 12, repairs 6, c1 3 + 6
            self.assertEqual(r[2], 6 + 6 + 12 + 6 + 3 + 6)

    def test_slot_is_generated_for_one_arm_alone_and_costs_one_trial(self):
        rows, _ = blocks((0.0, 0.0, 0.0), 5, GOOD0, GOOD1)
        a_only, _ = blocks((1.0, 0.0, 0.0), 5, GOOD0, GOOD1)  # c0 passes the zone trial: only A needs fresh slots
        self.assertEqual(a_only[0][3], 2 + 2)
        self.assertEqual(a_only[0][2], 6 + 6 + 6 + 3)

    def test_both_arms_can_adopt_the_same_fresh_candidate(self):
        rows, _ = blocks((0.5, 0.5, 0.5), 4000, GOOD0, GOOD1, seed=7)
        shared = [r for r in rows if not r[4] and r[1][0] >= 0 and r[1][0] == r[1][1]]
        self.assertGreater(len(shared), 100)
        for procs, (a, b, c, d), *_ in rows:
            if a >= 0 and a == b:
                self.assertLess(a, len(procs))

    def test_candidate_a_and_b_both_adopt_is_weighted(self):
        P0 = np.array([[0.0, 0.0, 0.0], [0.9, 0.9, 0.9]])
        rows, _ = blocks((0.5, 0.5, 0.5), 3000, P0, P0, q=0.0, seed=2)
        shared = [r for r in rows if not r[4] and r[1][0] >= 0 and r[1][0] == r[1][1]]
        self.assertGreater(len(shared), 50)
        for procs, (a, *_rest), *_ in shared:
            self.assertEqual(procs[a].tolist(), [0.9, 0.9, 0.9])  # B passed a zone trial: weighted

    def test_vector_adopted_by_a_alone_is_uniform(self):
        P0 = np.array([[0.0, 0.0, 0.0], [0.9, 0.9, 0.9]])
        rows, tally = blocks((0.0, 0.0, 1.0), 400, P0, P0, q=0.0, seed=4)
        seen = {tuple(r[0][r[1][0]].tolist()) for r in rows}
        self.assertEqual(seen, {(0.0, 0.0, 0.0), (0.9, 0.9, 0.9)})  # no zone trial passed: drawn uniformly
        self.assertEqual(tally['unweighted'], 0)  # a uniform draw is not a fall-back

    def test_fresh_candidate_adopted_by_a_alone_is_uniform_too(self):
        P0 = np.array([[0.0, 0.0, 0.0], [0.9, 0.9, 0.9]])
        rows, tally = blocks((0.0, 0.0, 0.5), 600, P0, P0, q=0.0, seed=6)  # no zone trial can pass: only A adopts
        self.assertEqual(tally['weighted'], 0)
        self.assertGreater(len(rows), 0)
        seen = {tuple(r[0][r[1][0]].tolist()) for r in rows if r[1][0] >= 0}
        self.assertEqual(seen, {(0.0, 0.0, 0.0), (0.9, 0.9, 0.9)})


class WeightedDraw(unittest.TestCase):
    def test_adopted_vectors_are_weighted_by_the_old_trial_pass_probability(self):
        P0 = np.array([[0.0, 0.0, 0.0], [0.9, 0.9, 0.9]])
        rows, tally = blocks((1.0, 1.0, 0.0), 300, P0, P0, q=0.0)
        for procs, picks, *_ in rows:
            for i in picks:
                if i >= 0:
                    self.assertEqual(procs[i].tolist(), [0.9, 0.9, 0.9])  # weight of the zero vector is 0
        self.assertGreater(tally['weighted'], 0)
        self.assertEqual(tally['unweighted'], 0)

    def test_weights_are_proportional(self):
        P0 = np.array([[0.5, 0.5, 0.5], [1.0, 1.0, 1.0]])  # weights 0.125 and 1
        rows, _ = blocks((1.0, 1.0, 1.0), 6000, P0, P0, q=0.0, seed=5)
        picks = [r[0][r[1][1]] for r in rows]  # arm B adopts c0, drawn weighted
        share = np.mean([p[0] == 0.5 for p in picks])
        self.assertAlmostEqual(share, 0.125 / 1.125, delta=0.015)

    def test_all_zero_weights_fall_back_to_unweighted_and_are_counted(self):
        P0 = np.array([[0.0, 0.5, 0.5], [0.4, 0.0, 0.4]])  # every product is 0
        rows, tally = blocks((1.0, 1.0, 1.0), 40, P0, P0, q=0.0)
        self.assertEqual(tally['weighted'], 0)
        adopted = sum(len(set(i for i in r[1] if i >= 0)) for r in rows)
        self.assertGreater(tally['unweighted'], 0)
        self.assertEqual(tally['unweighted'], sum(len(r[0]) for r in rows))  # every vector drawn was a fallback draw
        for procs, picks, *_ in rows:
            for i in picks:
                if i >= 0:
                    self.assertIn(procs[i].tolist(), P0.tolist())

    def test_the_count_reaches_the_task_summary(self):
        rng = np.random.default_rng(0)
        P0 = np.array([[0.0, 0.5, 0.5]]); P1 = np.array([[0.4, 0.0, 0.4]])
        Y, info = L.simulate_task(rng, 6, P0, P1, 0.5, 0.0, 0.5, 0.5, (1.0, 1.0, 1.0))
        self.assertGreater(info['draws']['unweighted'], 0)
        self.assertEqual(info['draws']['weighted'], 0)
        Y2, info2 = L.simulate_task(np.random.default_rng(0), 6, GOOD0, GOOD1, 0.5, 0.0, 0.5, 0.5)
        self.assertNotIn('draws', info2)


class OldModelUnchanged(unittest.TestCase):
    """Golden hashes made with the 11 November code (head 6a72706c) before the option was added."""
    CELL = '806f0c1ec370bebf5239c3a0ce912ede0787e51b31092db928b3a40ce98107a9'
    DEV = 'c53a964653ad2a6de1110115bd86824c71bbff61b63aae81fef07e21d413c463'
    TASK = '0b29d99391766e6d22586d1f45e44b7d719a15b7f509a136b1efe7214e6e6208'

    def setUp(self):
        rng = np.random.default_rng(0)
        P.G.clear()
        P.G.update(raw={t: (rng.uniform(0, 0.3, 8), rng.uniform(0.3, 0.9, 6)) for t in A.C.TASKS}, q=0.5, rd=0.4)

    def test_cell_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            part = Path(d) / 'a.json'
            P.cell_worker((0, (0.5, 0.0, 24), np.random.SeedSequence(20261114).spawn(1)[0], 3, 50, part, None))
            self.assertEqual(hashlib.sha256(part.read_bytes()).hexdigest(), self.CELL)

    def test_dev_bytes(self):
        job = (0, (0.5, 0.0), np.random.SeedSequence(3).spawn(1)[0], 5, 4)
        self.assertEqual(hashlib.sha256(json.dumps(P.dev_worker(job)).encode()).hexdigest(), self.DEV)

    def test_task_bytes(self):
        P0 = L.widen(np.array([0.1, 0.2, 0.0]), 0.5); P1 = L.widen(np.array([0.7, 0.9]), 0.5)
        Y, info = L.simulate_task(np.random.default_rng(2), 10, P0, P1, 0.6, -0.3, 0.4, 0.5)
        h = hashlib.sha256(Y.tobytes() + json.dumps({k: np.asarray(v).tolist() for k, v in info.items()}).encode()).hexdigest()
        self.assertEqual(h, self.TASK)


class CorrectedGrid(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        P.G.clear()
        P.G.update(raw={t: (rng.uniform(0, 0.3, 8), rng.uniform(0.3, 0.9, 6)) for t in A.C.TASKS}, q=0.5, rd=0.4)

    def test_grid_has_972_cells_in_a_fixed_order(self):
        g = P.grid_kinds(0.389)
        self.assertEqual(len(g), 27 * 12 * 3)
        self.assertEqual(sorted({c[2] for c in g}), [32, 40, 48])
        self.assertEqual(len({c[3] for c in g}), 27)
        self.assertEqual(g, P.grid_kinds(0.389))

    def test_corrected_cell_is_reproducible_and_differs_from_the_old_model(self):
        kinds = (0.05, 0.5, 0.75)
        with tempfile.TemporaryDirectory() as d:
            def run(name, seed, k):
                part = Path(d) / name
                P.cell_worker((0, (0.5, 0.0, 24), np.random.SeedSequence(seed).spawn(1)[0], 2, 40, part, None, k))
                return part.read_bytes()
            a, b = run('a.json', 9, kinds), run('b.json', 9, kinds)
            self.assertEqual(a, b)
            self.assertNotEqual(a, run('c.json', 9, None))
            cell = json.loads(a)
            self.assertEqual(cell['kinds'], {'pi_f': 0.05, 'pi_r': 0.5, 'pi_A': 0.75})
            self.assertEqual(set(cell['vector_draws']), set(A.C.TASKS))
            self.assertNotIn('kinds', json.loads(run('d.json', 9, None)))


class SectionSixPointSixRule(unittest.TestCase):
    def test_task_dependent_runs_count_as_resolved(self):
        row = {'p_resolved': {'margin 0.20': 0.7}, 'p_resolved_strict_margin_0_20': 0.5, 'p_task_dependent': 0.4}
        self.assertAlmostEqual(P.resolved_66(row), 0.9)
        per_task = {'p_resolved': {'margin 0.20': 0.7}}
        self.assertEqual(P.resolved_66(per_task), 0.7)  # a per-task interval is unchanged

    def test_the_80_percent_test_is_made_in_integers(self):
        row = {'p_resolved': {'margin 0.20': 0.7}, 'p_resolved_strict_margin_0_20': 0.729, 'p_task_dependent': 0.071}
        self.assertLess(P.resolved_66(row), 0.8)  # the float sum is 0.7999999999999999
        self.assertEqual(P.resolved_count(row, 1000), 800)
        self.assertTrue(P.meets_80(row, 1000))
        row['p_task_dependent'] = 0.070
        self.assertFalse(P.meets_80(row, 1000))

    def test_report_uses_the_rule(self):
        import contextlib, io
        names = P.primary_names()

        def iv(name):
            if name in P.POOLED:
                return {'p_resolved': {'margin 0.20': 0.5, 'margin 0.10': 0.5}, 'p_resolved_strict_margin_0_20': 0.5, 'p_task_dependent': 0.45}
            return {'p_resolved': {'margin 0.20': 0.95, 'margin 0.10': 0.9}}
        cell = lambda N: {'N': N, 'lam': 0.5, 'rho_c': 0.0, 'kinds': {'pi_f': .2, 'pi_r': .2, 'pi_A': .2}, 'intervals': {n: iv(n) for n in names},
                          'vector_draws': {t: {'weighted': 1, 'unweighted': 0} for t in A.C.TASKS}}
        new = {'sims': 1000, 'cells': [cell(N) for N in P.NS_KINDS], 'kind_values': {k: [0.1, 0.2, 0.3] for k in L.KIND_COUNTS}, 'kind_counts': {k: list(v) for k, v in L.KIND_COUNTS.items()}}
        old = {'cells': [cell(32)]}
        dev = {'cells': [], 'sims': 1, 'dev_blocks': 4}
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, obj in (('n', new), ('o', old), ('d', dev), ('c', {'rows': []})):
                paths.append(Path(d) / name); paths[-1].write_text(json.dumps(obj))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                P.report_corrected(*paths)
        out = buf.getvalue()
        self.assertIn('Lowest at N = 32: 95.0%', out)  # pooled steps stand at 0.5 + 0.45
        self.assertIn('the smallest N that meets it is 32', out)


class Ruling85(unittest.TestCase):
    def test_a_repair_that_keeps_c0_has_c0s_vector_drawn_weighted(self):
        P0 = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        rows, tally = blocks((0.0, 1.0, 0.0), 2000, P0, P0, q=0.0, rho_c=-1.0, seed=3)  # C always adopts the repair that keeps c0
        got = [tuple(r[0][r[1][2]].tolist()) for r in rows]
        self.assertEqual(set(got), {(1.0, 1.0, 1.0)})  # never the zero vector: a zone trial was passed

    def test_pool_and_vector_are_drawn_together_for_c1(self):
        P0 = np.array([[0.5, 0.5, 0.5]]); P1 = np.array([[1.0, 1.0, 1.0]])
        rows, _ = blocks((1.0, 1.0, 1.0), 12000, P0, P1, q=0.5, seed=4)
        share = np.mean([np.allclose(r[0][r[1][3]], 1.0) for r in rows])
        want = 0.5 * 1.0 / (0.5 * 1.0 + 0.5 * 0.125)  # P(P1 | pass), about 0.889
        self.assertAlmostEqual(share, want, delta=5 * math.sqrt(want * (1 - want) / 12000))

    def test_pool_and_vector_are_drawn_together_for_repairs(self):
        P0 = np.array([[0.5, 0.5, 0.5]]); P1 = np.array([[1.0, 1.0, 1.0]])
        want = 0.5 / (0.5 + 0.5 * 0.125)
        tol = 5 * math.sqrt(want * (1 - want) / 8000)
        rows, _ = blocks((0.0, 1.0, 0.0), 8000, P0, P1, q=0.0, rho_c=0.5, rho_d=0.5, seed=5)  # c1 fails, repairs pass
        self.assertAlmostEqual(np.mean([np.allclose(r[0][r[1][3]], 1.0) for r in rows]), want, delta=tol)  # D's repair
        self.assertAlmostEqual(np.mean([np.allclose(r[0][r[1][2]], 1.0) for r in rows]), want, delta=tol)  # C's repair

    def test_mixture_fallback_when_every_weight_is_0_keeps_the_pool_shares_and_is_counted(self):
        P0 = np.array([[0.0, 0.5, 0.5]]); P1 = np.array([[0.4, 0.0, 0.4]])  # every product is 0
        rows, tally = blocks((1.0, 1.0, 1.0), 4000, P0, P1, q=0.25, seed=6)
        self.assertEqual(tally['weighted'], 0)
        share = np.mean([np.allclose(r[0][r[1][3]], P1[0]) for r in rows])
        self.assertAlmostEqual(share, 0.25, delta=5 * math.sqrt(0.25 * 0.75 / 4000))
        self.assertEqual(tally['unweighted'], sum(len(r[0]) for r in rows))

    def test_c1_is_one_model_call(self):
        rows, _ = blocks((1.0, 1.0, 1.0), 20, GOOD0, GOOD1)  # everything passes the first time
        for r in rows:
            self.assertEqual(r[3], 2)  # c0 and c1
        old = L.simulate_block(np.random.default_rng(1), GOOD0, GOOD1, 0.5, 0.0, 0.5)
        self.assertGreaterEqual(old[3], 3)  # the 11 November path keeps its count


class PartCheck(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        P.G.clear()
        P.G.update(raw={t: (rng.uniform(0, 0.3, 8), rng.uniform(0.3, 0.9, 6)) for t in A.C.TASKS}, q=0.5, rd=0.4)
        self.rd, self.seed = 0.4, 11

    def make(self, d, mutate=None, ns=(32, 40)):
        exp = P.grid_kinds(self.rd, ns)
        seeds = np.random.SeedSequence(self.seed).spawn(len(exp))
        for i, (lam, rc, N, k) in enumerate(exp):
            cell = {'N': N, 'lam': lam, 'rho_c': round(rc, 4), 'sims': 2000, 'boot': 2000, 'kinds': {'pi_f': k[0], 'pi_r': k[1], 'pi_A': k[2]},
                    'seed_entropy': seeds[i].entropy, 'seed_spawn_key': list(seeds[i].spawn_key)}
            if mutate and mutate[0] == i:
                cell.update(mutate[1])
            (Path(d) / P.part_name(i, lam, rc, N)).write_text(json.dumps(cell))
        return ns

    def test_good_parts_pass(self):
        with tempfile.TemporaryDirectory() as d:
            ns = self.make(d)
            self.assertEqual(len(P.check_parts(d, self.rd, 2000, 2000, self.seed, ns)), 27 * 12 * 2)

    def test_each_wrong_property_is_refused(self):
        for bad in ({'sims': 1000}, {'boot': 500}, {'N': 48}, {'lam': 0.25}, {'rho_c': 0.1}, {'kinds': {'pi_f': 0.5, 'pi_r': 0.5, 'pi_A': 0.5}}, {'seed_spawn_key': [999]}):
            with tempfile.TemporaryDirectory() as d:
                ns = self.make(d, (5, bad))
                with self.assertRaises(ValueError, msg=str(bad)):
                    P.check_parts(d, self.rd, 2000, 2000, self.seed, ns)

    def test_wrong_seed_missing_and_extra_parts_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ns = self.make(d)
            with self.assertRaises(ValueError):
                P.check_parts(d, self.rd, 2000, 2000, self.seed + 1, ns)
            next(Path(d).glob('*.json')).unlink()
            with self.assertRaises(ValueError):
                P.check_parts(d, self.rd, 2000, 2000, self.seed, ns)
        with tempfile.TemporaryDirectory() as d:
            ns = self.make(d)
            (Path(d) / 'cell-999-timing.json').write_text('{}')
            with self.assertRaises(ValueError):
                P.check_parts(d, self.rd, 2000, 2000, self.seed, ns)

    def test_a_real_part_carries_what_the_check_reads(self):
        exp = P.grid_kinds(self.rd, (24,))[0]
        ss = np.random.SeedSequence(self.seed).spawn(1)[0]
        with tempfile.TemporaryDirectory() as d:
            part = Path(d) / 'p.json'
            P.cell_worker((0, exp[:3], ss, 2, 40, part, None, exp[3]))
            self.assertEqual(P.cell_problems(json.loads(part.read_text()), 0, exp, 2, 40, self.seed), [])
            self.assertNotEqual(P.cell_problems(json.loads(part.read_text()), 0, exp, 3, 40, self.seed), [])

    def test_report_refuses_bad_parts_and_builds_from_good_ones(self):
        import contextlib, io
        with tempfile.TemporaryDirectory() as d:
            ns = self.make(d)
            cells = [json.loads(x.read_text()) for x in sorted(Path(d).glob('*.json'))]
            new = {'sims': 2000, 'fitted': {'rho_d': self.rd}, 'cells': cells, 'kind_values': {k: [0.1, 0.2, 0.3] for k in L.KIND_COUNTS}}
            paths = []
            for name, obj in (('n', new), ('o', {'cells': []}), ('d', {'cells': [], 'sims': 1, 'dev_blocks': 4}), ('c', {'rows': []})):
                paths.append(Path(d).parent / f'x-{name}-{os.getpid()}.json'); paths[-1].write_text(json.dumps(obj))
            try:
                with self.assertRaises(ValueError):
                    with contextlib.redirect_stdout(io.StringIO()):
                        P.report_corrected(*paths, parts=d, sims=1000, boot=2000, seed=self.seed)
            finally:
                for x in paths:
                    x.unlink()


class Acceptance(unittest.TestCase):
    def test_exit_status_follows_the_full_range(self):
        import subprocess, sys
        stat = lambda lo, hi: {'min': lo, 'max': hi, 'p2_5': lo, 'p97_5': hi}
        dev = {'cells': [{'stats': {'x': stat(0, 4), 'y': stat(2, 3)}}]}
        for vals, code in (((1, 3), 0), ((1, 5), 1), ((5, 3), 1)):
            chk = {'rows': [{'statistic': 'x', 'value': vals[0]}, {'statistic': 'y', 'value': vals[1]}]}
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / 'd.json').write_text(json.dumps(dev)); (Path(d) / 'c.json').write_text(json.dumps(chk))
                r = subprocess.run([sys.executable, '-B', '-W', 'ignore', str(Path(P.__file__)), '--acceptance', f'{d}/d.json', f'{d}/c.json'], capture_output=True, text=True)
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        lines, outside = P.acceptance(dev, {'rows': [{'statistic': 'x', 'value': 9}]})
        self.assertEqual(outside, ['x'])


class ReportColumns(unittest.TestCase):
    def test_columns_and_forecast(self):
        import contextlib, io
        names = P.primary_names()
        mk = lambda N, k, share: {'N': N, 'lam': 0.5, 'rho_c': 0.0, 'kinds': {'pi_f': k, 'pi_r': k, 'pi_A': k},
                                  'intervals': {n: {'p_resolved': {'margin 0.20': share, 'margin 0.10': share}} for n in names},
                                  'vector_draws': {t: {'weighted': 1, 'unweighted': 0} for t in A.C.TASKS}}
        cells = [mk(N, k, 0.9 if k == 0.2 else 0.5) for N in (64, 96) for k in (0.1, 0.2, 0.3)]
        new = {'sims': 1000, 'cells': cells, 'kind_values': {k: [0.1, 0.2, 0.3] for k in L.KIND_COUNTS}, 'kind_counts': {k: list(v) for k, v in L.KIND_COUNTS.items()}}
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, obj in (('n', new), ('o', {'cells': []}), ('d', {'cells': [], 'sims': 1, 'dev_blocks': 4}), ('c', {'rows': []})):
                paths.append(Path(d) / name); paths[-1].write_text(json.dumps(obj))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                P.report_corrected(*paths)
        out = buf.getvalue()
        self.assertIn('| D-A reach 3m | 64 | 50.0 | (0.1000, 0.1000, 0.1000, 0.5, 0.0) | 90.0 | 1 of 3 | not run |', out)
        self.assertIn('| 64 | 56 | 47 |', out)  # 0.29 * 3 * 64 = 55.7; 0.73 * 64 = 46.7
        self.assertIn('| 96 | 84 | 70 |', out)


@unittest.skipUnless(RUNS.exists() and POOLS_JSON.exists(), 'scored-2 folder or the 11 November file not present')
class PoolsOption(unittest.TestCase):
    def test_pools_file_gives_the_values_the_records_give(self):
        raw, counts, q, rd, tp, m0 = P.setup(RUNS, AUDIT)
        raw2, counts2, q2, rd2, tp2, m02 = P.setup_from_json(POOLS_JSON)
        for t in A.C.TASKS:
            np.testing.assert_array_equal(raw[t][0], raw2[t][0]); np.testing.assert_array_equal(raw[t][1], raw2[t][1])
        self.assertEqual((counts, q, rd, tp, m0), (counts2, q2, rd2, tp2, m02))

    def test_one_small_combination_gives_the_same_cell(self):
        outs = []
        for src in ('records', 'file'):
            P.G.clear()
            raw, counts, q, rd, tp, m0 = P.setup(RUNS, AUDIT) if src == 'records' else P.setup_from_json(POOLS_JSON)
            P.G.update(raw=raw, q=q, rd=rd)
            with tempfile.TemporaryDirectory() as d:
                part = Path(d) / 'x.json'
                P.cell_worker((0, (0.5, rd, 24), np.random.SeedSequence(4).spawn(1)[0], 2, 40, part, None, (0.05, 0.5, 0.75)))
                outs.append(part.read_bytes())
        self.assertEqual(outs[0], outs[1])


if __name__ == '__main__':
    unittest.main()

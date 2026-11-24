"""Prospective sample-size simulation for the protocol-3 ladder (C3 working script).

Reads only scored-2's archived outcome.json and summary.json files. Writes a JSON
result to --out. Nothing here is scored evidence.

Model
-----
A procedure is a vector of success probabilities for the 3 m, 10 m and 20 m
bands. Two empirical pools per task come from scored-2's fresh threat-zone
flights: P0 (the eight procedures learned without the zone) and P1 (the adopted
procedures learned with it). scored-2 observed the 3 m band only, so the 10 m and
20 m rates are a swept assumption: p_wide = p3 + lam * (1 - p3).

A trial is one learning layout per band; a candidate passes when it meets the
goal in all three. A adopts c0 (24 of 24 matched runs adopted the first
candidate on zone-free trials). B, C share c0 and its zone trial. On failure, B
draws a fresh P0 candidate, C a repair: from P1 with probability rho_c, else from
P0 (rho_c < 0: with probability -rho_c the repair keeps c0's behaviour, which
makes repair worse than regeneration). D starts from c1, which is P1-type with
probability q, else P0-type, and
repairs with rho_d. q and rho_d are fitted to scored-2's learning record
using its close-gap trials. The counts (first candidate adopted, runs, rescued,
initial failures) are read from the 24 learning summaries by read_learning_counts();
they are 16 of 24 and 6 of 8. The 9 November version used 15 of 24 and 7 of 9.
Classes come from analysis3.classify, with a 95% interval for direction and a 90%
interval for equivalence (revision of 11 November). At most three candidates; non-adoption scores 0.

Corrected model of 19 November (ruling 72), behind the option kinds=(pi_f, pi_r, pi_A);
without it nothing above changes. A candidate passes its zone trial with a probability set by
its kind: pi_f for a first or fresh candidate (c0, c1, fresh), pi_r for a repair. Arm A's c0
passes its zone-free trial with probability pi_A, and so do A's two fresh candidates
(all three of A's slots use pi_A). Arms A and B share one stream of fresh candidates: a slot is
one model call, tested on A's zone-free trial and on B's zone trial separately, and an
adopted candidate is one procedure for every arm that adopts it (ruling 77, clarifying ruling
72). Only an adopted candidate gets an evaluation vector, drawn once. It comes from the pool
the old model would draw it from. It is weighted by prod(vector), the old model's chance of
passing the trial, if any arm adopted it after a zone trial (B, C or D); if only A adopted it,
after a zone-free trial, it is drawn uniformly, as the old model drew A's c0. If every weight
in the pool is 0 the weighted draw is unweighted and counted.

Evaluation: 24 scenarios, 8 per band. Scenario difficulty is shared across
procedures through a Gaussian copula with weight alpha. Arms that adopt the same
procedure share its flights. Inference is the crossed bootstrap in the design:
blocks resampled jointly across arms, scenarios resampled within band with one
draw shared everywhere, equal band weights, pointwise percentile intervals.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import analysis3 as A  # the classifier and the interval rule the analysis will use

TASKS = ('reach', 'reach3d', 'land')
ARMS = ('A', 'B', 'C', 'D')
STEPS = {'B-A': (1, 0), 'C-B': (2, 1), 'D-C': (3, 2), 'D-A': (3, 0)}
ND = NormalDist()


def gap_m(o):
    _k, _t, _s, n, e, r = o['events'][0][:6]
    g = o['goal']
    return math.hypot(g['target_north_m'] - n, g['target_east_m'] - e) - r


def pools(runs, task):
    out = {}
    for arm in ('matched', 'threat'):
        rates = []
        for b in range(8):
            d = runs / f'threat-{task}-b{b}-{arm}'
            if not d.exists():
                continue  # non-adoption: not a procedure
            os_ = [json.loads(p.read_text()) for p in sorted(d.glob('flights/threat-440*/outcome.json'))]
            close = [o['goal_met'] for o in os_ if gap_m(o) <= 4.0]
            rates.append(sum(close) / len(close))
        out[arm] = np.array(rates)
    return out['matched'], out['threat']


def clopper_pearson_bisect(k, n, conf=0.95):
    """Two-sided Clopper-Pearson interval by bisection on the binomial distribution."""
    from math import comb
    a = (1 - conf) / 2

    def cdf(x, p):  # P(X <= x)
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))

    def solve(f):  # f decreasing in p, returns p with f(p) = 0
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: a - (1 - cdf(k - 1, p)))  # P(X >= k) rises with p
    upper = 1.0 if k == n else solve(lambda p: cdf(k, p) - a)  # P(X <= k) falls with p
    return lower, upper


def clopper_pearson(k, n, conf=0.95):
    """Two-sided Clopper-Pearson interval: scipy's beta quantiles when scipy is present,
    else bisection on the binomial distribution."""
    try:
        from scipy.stats import beta
    except ImportError:
        return clopper_pearson_bisect(k, n, conf)
    a = (1 - conf) / 2
    return (0.0 if k == 0 else float(beta.ppf(a, k, n - k + 1)),
            1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k)))


# ruling 72 point 3: counts read from the sample's blocks (zone-trial slots passed, of slots)
KIND_COUNTS = {'pi_f': (2, 44), 'pi_r': (17, 34), 'pi_A': (9, 12)}


def kind_values():
    """For each of pi_f, pi_r, pi_A: (lower end, share, upper end)."""
    out = {}
    for name, (k, n) in KIND_COUNTS.items():
        lo, hi = clopper_pearson(k, n)
        out[name] = (lo, k / n, hi)
    return out


def kind_combinations():
    """The 27 (pi_f, pi_r, pi_A) combinations in a fixed order."""
    v = kind_values()
    return [(f, r, a) for f in v['pi_f'] for r in v['pi_r'] for a in v['pi_A']]


def widen(p3, lam):
    pw = p3 + lam * (1 - p3)
    return np.stack([p3, pw, pw], axis=-1)


AUDIT = 'paper3/reproduction/ladder-planning-audit-d3-20261109.json'


def read_learning_counts(runs, audit_path):
    """Read the learning counts from the 24 scored-2 learning summaries.

    Each summary is hashed and compared with the audit file before it is read;
    any mismatch, missing file or unexpected count of files raises. Returns
    (first_adoptions, runs, rescued, initial_failures, detail)."""
    audit = json.loads(Path(audit_path).read_text())
    prefix = 'paper3/runs/scored-2/'
    hashes = audit['input_sha256']
    if len(hashes) != 24:
        raise ValueError(f'audit lists {len(hashes)} summaries, expected 24')
    tally = {}
    for key, want in sorted(hashes.items()):
        if not key.startswith(prefix):
            raise ValueError(f'unexpected audit path {key}')
        p = Path(runs) / key[len(prefix):]
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != want:
            raise ValueError(f'hash mismatch for {key}')
        s = json.loads(raw)
        row = (bool(s['checks']['candidate_passed_trial_and_adopted']), int(s['learning_attempts']))
        tally[row] = tally.get(row, 0) + 1
    n = sum(tally.values())
    first = tally.get((True, 1), 0)
    failures = n - first
    rescued = sum(v for (ad, k), v in tally.items() if ad and k > 1)
    detail = {f"{'adopted' if ad else 'not adopted'} at attempt {k}": v for (ad, k), v in sorted(tally.items())}
    return first, n, rescued, failures, detail


def fit_q_rho(all_pools, first, runs, rescued, failures):
    """Fit q (c1 is P1-type) and rho_d (repair is P1-type) to scored-2's D record
    under its trial design: three layouts at the close gap."""
    t_pass = np.mean(np.concatenate([np.clip(t, 0, 1) ** 3 for _m, t in all_pools]))
    m_pass = np.mean(np.concatenate([np.clip(m, 0, 1) ** 3 for m, _t in all_pools]))
    q = (first / runs - m_pass) / (t_pass - m_pass)
    # rescue within two repairs: 1 - (1 - s)^2 = rescued / failures, s = rho*t + (1-rho)*m
    s = 1 - math.sqrt(1 - rescued / failures)
    rho = (s - m_pass) / (t_pass - m_pass)
    return float(np.clip(q, 0, 1)), float(np.clip(rho, 0, 1)), float(t_pass), float(m_pass)


def simulate_block(rng, P0, P1, q, rho_c, rho_d):
    """Return per-arm procedure index into a per-block list of procedures, plus
    learning flights, model calls, whether c0 passed the zone trial and whether
    D's first candidate passed. Procedure -1 is non-adoption."""
    procs = []

    def draw(pool):
        procs.append(pool[rng.integers(len(pool))])
        return len(procs) - 1

    def passes(i):
        return bool(np.all(rng.random(3) < procs[i]))

    flights = 3 + 3  # first-round flights for P0 and P1
    calls = 2
    c0 = draw(P0)
    a = c0
    flights += 3  # c0 on A's zone-free trial (passes: 24/24 in scored-2)
    flights += 3  # c0 on the shared zone trial
    c0_ok = passes(c0)
    if c0_ok:
        b = c = c0
    else:
        b = c = -1
        for _ in range(2):  # B: fresh candidates
            i = draw(P0); flights += 3; calls += 1
            if passes(i):
                b = i; break
        for _ in range(2):  # C: repairs
            if rho_c < 0 and rng.random() < -rho_c:
                procs.append(procs[c0]); i = len(procs) - 1  # repair keeps c0's behaviour
            else:
                i = draw(P1 if rng.random() < max(rho_c, 0.0) else P0)
            flights += 3; calls += 1
            if passes(i):
                c = i; break
    c1 = draw(P1 if rng.random() < q else P0); calls += 1; flights += 3
    d = -1
    d_first = passes(c1)
    if d_first:
        d = c1
    else:
        for _ in range(2):
            i = draw(P1 if rng.random() < rho_d else P0); flights += 3; calls += 1
            if passes(i):
                d = i; break
    return procs, (a, b, c, d), flights, calls, c0_ok, d_first


def simulate_block_kinds(rng, P0, P1, q, rho_c, rho_d, kinds, tally):
    """The corrected block (ruling 72 and its clarifications, ruling 77). Same return as
    simulate_block. tally is a dict with 'weighted' and 'unweighted' counters of vector draws.

    First the pass or fail of every trial is decided, and only then is an evaluation vector
    drawn, once per candidate that any arm adopted. Arms A and B share one stream of fresh
    candidates f1, f2: a slot is generated (one model call) when either arm still needs it,
    and A tests it on its zone-free trial (pi_A), B on its zone trial (pi_f). A candidate
    adopted by any arm after a zone trial (B, C or D) has its vector drawn weighted by
    prod(vector); one adopted only by A, after a zone-free trial, is drawn uniformly.

    Ruling 85. For c1 and for every repair the pool and the vector are drawn together:
    P(pool, v | pass) is proportional to P(pool) P(v | pool) prod(v), P(pool) being q,
    max(rho_C, 0) or rho_D for P1. A repair that keeps c0's behaviour is a copy of c0, so c0's
    vector counts as adopted after a zone trial and is drawn weighted. c1 is one model call."""
    pf, pr, pa = kinds
    cands = []  # [pool or 'copy of c0', zone-trial candidate?, needed?]

    def new(pool):
        cands.append([pool, False, False])
        return len(cands) - 1

    flights = 3 + 3
    calls = 2
    flights += 3  # c0 on A's zone-free trial
    flights += 3  # c0 on the shared zone trial
    c0 = new(P0)
    c0_ok = bool(rng.random() < pf)
    a_ok = bool(rng.random() < pa)
    a = c0 if a_ok else -1
    if a >= 0:
        cands[c0][2] = True
    if c0_ok:
        b = c = c0
        cands[c0][1] = cands[c0][2] = True
    else:
        b = c = -1
    for _ in range(2):  # fresh slots shared by A and B
        a_need = a < 0
        b_need = (not c0_ok) and b < 0
        if not (a_need or b_need):
            break
        calls += 1
        f = new(P0)
        if a_need:
            flights += 3
            if rng.random() < pa:
                a = f; cands[f][2] = True
        if b_need:
            flights += 3
            if rng.random() < pf:
                b = f; cands[f][1] = cands[f][2] = True
    if not c0_ok:
        for _ in range(2):  # C: repairs
            keep = rho_c < 0 and rng.random() < -rho_c
            flights += 3; calls += 1
            if rng.random() < pr:
                if keep:
                    c = new('copy'); cands[c][2] = True  # repair keeps c0's behaviour: c0's vector, adopted after a zone trial
                    cands[c0][1] = cands[c0][2] = True
                else:
                    c = new(('mix', max(rho_c, 0.0))); cands[c][1] = cands[c][2] = True
                break
    flights += 3  # c1's call is already in the two first calls
    d = -1
    d_first = bool(rng.random() < pf)
    if d_first:
        d = new(('mix', q)); cands[d][1] = cands[d][2] = True
    else:
        for _ in range(2):
            flights += 3; calls += 1
            if rng.random() < pr:
                d = new(('mix', rho_d)); cands[d][1] = cands[d][2] = True
                break

    def pick(pool, weighted):
        if weighted:
            w = np.prod(pool, axis=1)
            tot = w.sum()
            if tot > 0:
                tally['weighted'] += 1
                i = int(np.searchsorted(np.cumsum(w) / tot, rng.random(), side='right'))
                return pool[min(i, len(pool) - 1)]
            tally['unweighted'] += 1
        return pool[rng.integers(len(pool))]

    ALL = np.concatenate([P1, P0])

    def pick_mix(p1_share, weighted):
        """One draw of (pool, vector) together. The prior weight of a vector is its pool's share
        divided by the pool's size; with a trial passed it is multiplied by prod(vector)."""
        w = np.concatenate([np.full(len(P1), p1_share / len(P1)), np.full(len(P0), (1 - p1_share) / len(P0))])
        if weighted:
            ww = w * np.prod(ALL, axis=1)
            if ww.sum() > 0:
                w = ww; tally['weighted'] += 1
            else:
                tally['unweighted'] += 1
        i = int(np.searchsorted(np.cumsum(w) / w.sum(), rng.random(), side='right'))
        return ALL[min(i, len(ALL) - 1)]

    procs, index, vec = [], {}, {}
    for k, (pool, zone, needed) in enumerate(cands):
        if not needed:
            continue
        if isinstance(pool, str):
            v = vec[c0]
        elif isinstance(pool, tuple):
            v = pick_mix(pool[1], zone)
        else:
            v = pick(pool, zone)
        vec[k] = v
        if k in (a, b, c, d):
            index[k] = len(procs); procs.append(v)
    picks = tuple(index[x] if x >= 0 else -1 for x in (a, b, c, d))
    return procs, picks, flights, calls, c0_ok, d_first


def simulate_task(rng, N, P0, P1, q, rho_c, rho_d, alpha, kinds=None):
    """Simulate N blocks of one task. Returns outcomes Y (arm, block, scenario)
    and per-block counts. No inference is done here."""
    S = 24
    band = np.repeat(np.arange(3), 8)
    zs = rng.standard_normal(S)  # shared scenario difficulty
    Y = np.zeros((4, N, S))
    info = {'flights': 0, 'calls': 0, 'c0_pass': 0, 'd_first': 0, 'adopted': np.zeros(4)}
    if kinds is not None:
        info['draws'] = {'weighted': 0, 'unweighted': 0}
    for blk in range(N):
        if kinds is None:
            procs, picks, f, c, ok, d_first = simulate_block(rng, P0, P1, q, rho_c, rho_d)
        else:
            procs, picks, f, c, ok, d_first = simulate_block_kinds(rng, P0, P1, q, rho_c, rho_d, kinds, info['draws'])
        info['calls'] += c; info['c0_pass'] += int(ok); info['d_first'] += int(d_first)
        outcomes = {}
        for k, i in enumerate(picks):
            if i < 0:
                continue
            info['adopted'][k] += 1
            if i not in outcomes:
                p = procs[i][band]
                z = math.sqrt(alpha) * zs + math.sqrt(1 - alpha) * rng.standard_normal(S)
                thr = np.array([-np.inf if x <= 0 else np.inf if x >= 1 else ND.inv_cdf(x) for x in p])
                outcomes[i] = (z < thr).astype(float)
            Y[k, blk] = outcomes[i]
        info['flights'] += f + len(outcomes) * (24 + 10)
    return Y, info


def classify_draws(point, draws, margin=0.20):
    """Class from analysis3.classify itself: 95% interval for direction, 90% for
    equivalence, both from the same bootstrap draws. There is no second copy of the rule."""
    ci95, ci90 = A.interval(draws), A.interval(draws, 0.90)
    return A.classify(point, ci95, ci90, margin)['class']


def run_once(rng, N, P0, P1, q, rho_c, rho_d, alpha, R):
    """One simulated run of one task with the per-task crossed bootstrap."""
    Y, info = simulate_task(rng, N, P0, P1, q, rho_c, rho_d, alpha)
    bands = ['close'] * 8 + ['middle'] * 8 + ['wide'] * 8
    draws = A.bootstrap(Y, bands, rng, R)
    point = Y.mean(axis=(1, 2))
    res = {}
    for name, (i, j) in STEPS.items():
        d = draws[i] - draws[j]
        res[name] = (float(point[i] - point[j]), d)
    close = np.arange(24) < 8
    dc = A.bootstrap(Y[:, :, close], ['close'] * 8, rng, R)
    res['D-A 3m'] = (float(Y[3][:, close].mean() - Y[0][:, close].mean()), dc[3] - dc[0])
    return res, info['flights'] / N, info['calls'] / N, 1 - info['c0_pass'] / N, 1 - info['adopted'] / N


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=Path, required=True)
    ap.add_argument('--audit', type=Path, default=ROOT.parent / AUDIT)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--sims', type=int, default=1000)
    ap.add_argument('--boot', type=int, default=500)
    ap.add_argument('--seed', type=int, default=20261116)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    raw = {t: pools(a.runs, t) for t in TASKS}
    first, n, rescued, failures, detail = read_learning_counts(a.runs, a.audit)
    q, rho_d, t_pass, m_pass = fit_q_rho(list(raw.values()), first, n, rescued, failures)
    print(f'counts {first}/{n} first, {rescued}/{failures} rescued; fitted q={q:.3f} rho_d={rho_d:.3f} (P1 close pass {t_pass:.3f}, P0 close pass {m_pass:.3f})')
    out = {'counts': {'first_adoptions': first, 'runs': n, 'rescued': rescued, 'initial_failures': failures, 'detail': detail},
           'fitted': {'q': q, 'rho_d': rho_d}, 'seed': a.seed, 'sims': a.sims, 'boot': a.boot,
           'pools': {t: {'P0_close': raw[t][0].tolist(), 'P1_close': raw[t][1].tolist()} for t in TASKS}, 'cells': []}
    for task in TASKS:
        for lam in (0.0, 0.5, 1.0):
            P0 = widen(raw[task][0], lam); P1 = widen(raw[task][1], lam)
            for rho_c in (-0.5, 0.0, rho_d, 0.9):
                for N in (16, 24, 32, 40, 48):
                    for alpha in ((0.5,) if (N, rho_c) != (32, rho_d) else (0.0, 0.5, 0.9)):
                        rows = [run_once(rng, N, P0, P1, q, rho_c, rho_d, alpha, a.boot) for _ in range(a.sims)]
                        cell = {'task': task, 'lam': lam, 'rho_c': round(rho_c, 3), 'N': N, 'alpha': alpha,
                                'flights_per_block': float(np.mean([r[1] for r in rows])),
                                'calls_per_block': float(np.mean([r[2] for r in rows])),
                                'fork_rate': float(np.mean([r[3] for r in rows])),
                                'nonadoption': dict(zip(ARMS, np.mean([r[4] for r in rows], axis=0).round(3).tolist())),
                                'steps': {}}
                        for name in list(STEPS) + ['D-A 3m']:
                            vals = [r[0][name] for r in rows]
                            hw = np.array([(np.quantile(d, .975) - np.quantile(d, .025)) / 2 for _e, d in vals])
                            cls = {m: [classify_draws(e, d, m) for e, d in vals] for m in (0.20, 0.10)}
                            cell['steps'][name] = {
                                'mean_estimate': float(np.mean([v[0] for v in vals])),
                                'median_half_width': float(np.median(hw)),
                                'p_half_width_le_015': float(np.mean(hw <= 0.15)),
                                'classes_margin_0_20': {k: cls[0.20].count(k) / a.sims for k in ('different_not_equivalent', 'different_and_equivalent', 'equivalent_not_different', 'unresolved')},
                                'p_resolved': {f'margin {m:.2f}': 1 - cls[m].count('unresolved') / a.sims for m in (0.20, 0.10)},
                            }
                        out['cells'].append(cell)
                        print(task, lam, round(rho_c, 3), N, alpha, flush=True)
    a.out.write_text(json.dumps(out, indent=1) + '\n')


if __name__ == '__main__':
    main()

"""Ladder steps pooled over the three tasks with equal weights, rerun of 11 November 2026.

Reuses ladder_sim3's model. Each simulated run flies all three tasks at the same N and
the three tasks are independent. Everything that classifies or draws a bootstrap goes
through analysis3 itself: A.bootstrap, A.interval, A.classify, A.estimate_record and
A.pooled_comparisons (which holds the task-dependent rule). Nothing here is scored evidence.

Modes
-----
  (default)  the nine intervals (three primary, six secondary since ruling 88) over the grid of lam, rho_c and N
  --dev      what a development sample of 4 blocks per task may show (written before it is read)
  --kinds    the corrected model of 19 November (ruling 72): 27 (pi_f, pi_r, pi_A) combinations
             crossed with the 12 (lambda, rho_c) combinations, at N of 32, 40 and 48; combines
             with --dev. Without it every 11 November output is unchanged.
  --ns       with --kinds: the N values of the grid (default 32 40 48); a part records its runs, resamples
             and seed, and the output is refused unless every cell matches what its index gives (ruling 85)
  --check-parts DIR   with --report-corrected: the same check on a parts folder, before any table is built
  --acceptance DEV CHECK   exit 1 if a row of the development check is outside the table's full range
  --pools    read the pools and fitted counts from an earlier output file instead of scored-2

The grid is run cell by cell, and each cell has its own seed derived from --seed and the
cell's position in a fixed order, so the bytes do not depend on how many workers ran or in
what order. Each finished cell is saved to --parts, so a stopped run resumes where it ended.
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import analysis3 as A
from protocol import contract3 as C
from protocol import ladder_sim3 as L

LAMS = (0.0, 0.5, 1.0)
NS = (24, 32, 40)
NS_KINDS = (32, 40, 48)
POOLED = ('B-A', 'C-B', 'D-C')
CLASSES = ('different_not_equivalent', 'different_and_equivalent', 'equivalent_not_different', 'unresolved')
BANDS24 = ['close'] * 8 + ['middle'] * 8 + ['wide'] * 8
CLOSE = np.array([b == 'close' for b in BANDS24])


def blob_hash(path):
    """git's blob hash of a file, so the owner of analysis3 can compare."""
    raw = Path(path).read_bytes()
    return hashlib.sha1(b'blob %d\0' % len(raw) + raw).hexdigest()


def primary_names():
    return [f'D-A {t} 3m' for t in C.TASKS] + [f'D-A {t} 10-20m' for t in C.TASKS] + list(POOLED)


def one_run(rng, N, pools, q, rc, rd, R, alpha=0.5, kinds=None):
    """One simulated run of all three tasks. Returns the compact record of the run."""
    pts, drs, steps, prim, nonad, draws = {}, {}, {}, {}, {}, {}
    for t in C.TASKS:
        P0, P1 = pools[t]
        Y, info = L.simulate_task(rng, N, P0, P1, q, rc, rd, alpha, kinds)
        if kinds is not None:
            draws[t] = (info['draws']['weighted'], info['draws']['unweighted'])
        nonad[t] = (1 - info['adopted'] / N).tolist()
        steps[t], pts[t], drs[t] = A.comparisons(Y, BANDS24, rng, R)
        for key, mask in (('close', CLOSE), ('wide', ~CLOSE)):
            ys = Y[:, :, mask]
            d = A.bootstrap(ys, [b for b, m in zip(BANDS24, mask) if m], rng, R)
            p = ys.mean(axis=(1, 2))
            prim[f'D-A {t} ' + ('3m' if key == 'close' else '10-20m')] = A.estimate_record(p[3] - p[0], d[3] - d[0])
    pooled = A.pooled_comparisons(pts, drs, steps)
    rec = {'nonadoption': nonad, 'prim': {}, 'pooled': {}}
    if kinds is not None:
        rec['draws'] = draws
    for name, row in prim.items():
        rec['prim'][name] = {'class': {m: (row['classification'] if m == 0.20 else row['sensitivity_margin_0_10'])['class'] for m in (0.20, 0.10)},
                             'est': row['estimate'], 'hw': (row['ci95'][1] - row['ci95'][0]) / 2}
    for key in POOLED:
        row = pooled[key]
        under = row.get('underlying_classification', row['classification'])['class']
        under10 = row['sensitivity_margin_0_10']['class']
        ai, bi = (C.ARMS.index(x) for x in C.STEPS[key])
        per = {t: float(pts[t][ai] - pts[t][bi]) for t in C.TASKS}
        # a rule on the difference between two tasks: the 95% interval of the difference
        # (task draws are independent) excludes 0
        pair_any = pair_signed = False
        for t1, t2 in combinations(C.TASKS, 2):
            lo, hi = A.interval((drs[t1][ai] - drs[t1][bi]) - (drs[t2][ai] - drs[t2][bi]))
            if lo > 0 or hi < 0:
                pair_any = True
                if per[t1] * per[t2] < 0:
                    pair_signed = True
        rec['pooled'][key] = {
            'class': {0.20: under, 0.10: under10}, 'est': row['estimate'], 'hw': (row['ci95'][1] - row['ci95'][0]) / 2,
            'task_dependent': bool(row['task_dependent']), 'pair_any': pair_any, 'pair_signed': pair_signed,
            'per_task': per}
    return rec


def summarise(recs, N, lam, rc, kinds=None):
    n = len(recs)
    cell = {'lam': lam, 'rho_c': rc, 'N': N, 'sims': n, 'intervals': {}, 'opposite': {}, 'nonadoption': {}}
    if kinds is not None:
        cell['kinds'] = {'pi_f': kinds[0], 'pi_r': kinds[1], 'pi_A': kinds[2]}
        cell['vector_draws'] = {t: {'weighted': sum(r['draws'][t][0] for r in recs), 'unweighted': sum(r['draws'][t][1] for r in recs)} for t in C.TASKS}
    for t in C.TASKS:
        cell['nonadoption'][t] = dict(zip(L.ARMS, np.mean([r['nonadoption'][t] for r in recs], axis=0).round(4).tolist()))
    for name in primary_names():
        rows = [r['prim'][name] if name in r['prim'] else r['pooled'][name] for r in recs]
        pooled = name in POOLED
        out = {'mean_estimate': float(np.mean([x['est'] for x in rows])), 'median_half_width': float(np.median([x['hw'] for x in rows])),
               'classes_margin_0_20': {k: sum(x['class'][0.20] == k for x in rows) / n for k in CLASSES},
               'p_resolved': {f'margin {m:.2f}': sum(x['class'][m] != 'unresolved' for x in rows) / n for m in (0.20, 0.10)}}
        if pooled:
            out['p_task_dependent'] = sum(x['task_dependent'] for x in rows) / n
            # strict: a run whose pooled class is withheld as task-dependent is not counted as resolved
            out['p_resolved_strict_margin_0_20'] = sum(x['class'][0.20] != 'unresolved' and not x['task_dependent'] for x in rows) / n
            cell['opposite'][name] = {
                'mean_per_task_estimate': {t: float(np.mean([x['per_task'][t] for x in rows])) for t in C.TASKS},
                'p_rule_task_dependent': out['p_task_dependent'],
                'p_rule_pair_difference_signed': sum(x['pair_signed'] for x in rows) / n,
                'p_rule_pair_difference_any_sign': sum(x['pair_any'] for x in rows) / n,
                'pooled_class_under_present_rule': {k: sum((not x['task_dependent']) and x['class'][0.20] == k for x in rows) / n for k in CLASSES} | {'task_dependent': out['p_task_dependent']},
                'pooled_class_under_pair_rule': {k: sum((not x['pair_signed']) and x['class'][0.20] == k for x in rows) / n for k in CLASSES} | {'task_dependent': sum(x['pair_signed'] for x in rows) / n}}
        cell['intervals'][name] = out
    return cell


def setup_from_json(path):
    """The same values as setup(), read from the meta of an earlier output file (pools and
    fitted counts), so that a run needs no scored-2 files."""
    m = json.loads(Path(path).read_text())
    raw = {t: (np.array(m['pools'][t]['P0_close']), np.array(m['pools'][t]['P1_close'])) for t in C.TASKS}
    f = m['fitted']
    return raw, m['counts'], f['q'], f['rho_d'], f['p1_close_pass'], f['p0_close_pass']


def setup(runs, audit):
    raw = {t: L.pools(runs, t) for t in C.TASKS}
    first, n, rescued, failures, detail = L.read_learning_counts(runs, audit)
    q, rd, tp, mp_ = L.fit_q_rho(list(raw.values()), first, n, rescued, failures)
    counts = {'first_adoptions': first, 'runs': n, 'rescued': rescued, 'initial_failures': failures, 'detail': detail}
    return raw, counts, q, rd, tp, mp_


def grid(rd):
    """Fixed order, which fixes each cell's seed."""
    return [(lam, rc, N) for lam in LAMS for rc in (-0.5, 0.0, rd, 0.9) for N in NS]


def grid_kinds(rd, ns=NS_KINDS):
    """The corrected model's grid: (lam, rho_c, N, kinds), fixed order. 27 x 12 x len(ns) cells."""
    return [(lam, rc, N, k) for k in L.kind_combinations() for lam in LAMS for rc in (-0.5, 0.0, rd, 0.9) for N in ns]


def part_name(i, lam, rc, N, kinds=True):
    return (f'cell-{i:03d}' if kinds else f'cell-{i:02d}') + f'-lam{lam}-rc{rc:.4f}-N{N}.json'


def cell_problems(cell, i, expected, sims, boot, seed):
    """What differs between a stored cell and the cell its index gives. expected is the
    (lam, rho_c, N, kinds) of cell i. Empty list when it is the right one."""
    lam, rc, N, k = expected
    spawn = np.random.SeedSequence(seed).spawn(i + 1)[i]
    want = {'sims': sims, 'boot': boot, 'N': N, 'lam': lam, 'rho_c': round(rc, 4),
            'kinds': {'pi_f': k[0], 'pi_r': k[1], 'pi_A': k[2]},
            'seed_entropy': spawn.entropy, 'seed_spawn_key': list(spawn.spawn_key)}
    return [f'cell {i}: {key} is {cell.get(key)!r}, expected {v!r}' for key, v in want.items() if cell.get(key) != v]


def check_cells(cells, rd, sims, boot, seed, ns):
    """Raise ValueError unless cells is the grid's cells in order, each with the runs, resamples,
    seed, N, rates and settings that its index gives."""
    exp = grid_kinds(rd, ns)
    if len(cells) != len(exp):
        raise ValueError(f'{len(cells)} cells, expected {len(exp)}')
    problems = []
    for i, (cell, e) in enumerate(zip(cells, exp)):
        problems += cell_problems(cell, i, e, sims, boot, seed)
    if problems:
        raise ValueError('cells do not match the grid: ' + '; '.join(problems[:10]) + (f' (and {len(problems) - 10} more)' if len(problems) > 10 else ''))


def check_parts(parts, rd, sims, boot, seed, ns):
    """Raise ValueError unless the folder holds exactly one part for each cell of the grid and
    every part passes check_cells. Returns the cells in order."""
    parts = Path(parts)
    exp = grid_kinds(rd, ns)
    names = {part_name(i, e[0], e[1], e[2]) for i, e in enumerate(exp)}
    have = {x.name for x in parts.glob('*.json')}
    if have != names:
        raise ValueError(f'parts folder differs from the grid: {len(names - have)} missing, {len(have - names)} unexpected')
    cells = [json.loads((parts / part_name(i, e[0], e[1], e[2])).read_text()) for i, e in enumerate(exp)]
    check_cells(cells, rd, sims, boot, seed, ns)
    return cells


G = {}


def pools_for(lam):
    return {t: (L.widen(G['raw'][t][0], lam), L.widen(G['raw'][t][1], lam)) for t in C.TASKS}


def cell_worker(job):
    idx, (lam, rc, N), seed_state, a_sims, a_boot, part, stop_after, *rest = job
    kinds = rest[0] if rest else None
    if part.exists():
        return idx, json.loads(part.read_text())
    if stop_after is not None and time.time() > stop_after:
        return idx, None  # deadline: not started
    rng = np.random.default_rng(seed_state)
    pools = pools_for(lam)
    recs = [one_run(rng, N, pools, G['q'], rc, G['rd'], a_boot, 0.5, kinds) for _ in range(a_sims)]
    cell = summarise(recs, N, lam, round(rc, 4), kinds)
    if kinds is not None:
        cell.update(boot=a_boot, seed_entropy=seed_state.entropy, seed_spawn_key=list(seed_state.spawn_key))
    part.write_text(json.dumps(cell, indent=1) + '\n')
    return idx, cell


def dev_worker(job):
    """Development sample: 4 blocks per task, many replicates, for one (lam, rho_c) cell."""
    idx, (lam, rc), seed_state, reps, blocks, *rest = job
    kinds = rest[0] if rest else None
    drawn = {t: [0, 0] for t in C.TASKS}
    rng = np.random.default_rng(seed_state)
    pools = pools_for(lam)
    rows = {}
    for _ in range(reps):
        stat = {}
        tot_flights = tot_calls = 0
        Ys = []
        for t in C.TASKS:
            P0, P1 = pools[t]
            Y, info = L.simulate_task(rng, blocks, P0, P1, G['q'], rc, G['rd'], 0.5, kinds)
            Ys.append(Y)
            if kinds is not None:
                drawn[t][0] += info['draws']['weighted']; drawn[t][1] += info['draws']['unweighted']
            stat[f'{t}: c0 passes zone trial'] = info['c0_pass']
            stat[f'{t}: D first candidate adopted'] = info['d_first']
            for k, arm in enumerate(L.ARMS):
                stat[f'{t}: arm {arm} adopts'] = int(info['adopted'][k])
            tot_flights += info['flights']; tot_calls += info['calls']
        stat['all tasks: c0 passes zone trial'] = sum(stat[f'{t}: c0 passes zone trial'] for t in C.TASKS)
        stat['all tasks: D first candidate adopted'] = sum(stat[f'{t}: D first candidate adopted'] for t in C.TASKS)
        for arm in L.ARMS:
            stat[f'all tasks: arm {arm} adopts'] = sum(stat[f'{t}: arm {arm} adopts'] for t in C.TASKS)
        stat['all tasks: flights per block'] = tot_flights / (3 * blocks)
        stat['all tasks: model calls per block'] = tot_calls / (3 * blocks)
        Y = np.concatenate(Ys, axis=1)
        for k, arm in enumerate(('A', 'D')):
            ia = 0 if arm == 'A' else 3
            stat[f'all tasks: arm {arm} success at 3 m'] = float(Y[ia][:, CLOSE].mean())
            stat[f'all tasks: arm {arm} success at 10-20 m'] = float(Y[ia][:, ~CLOSE].mean())
        for k, v in stat.items():
            rows.setdefault(k, []).append(v)
    out = {}
    for k, v in rows.items():
        v = np.asarray(v, dtype=float)
        out[k] = {'min': float(v.min()), 'max': float(v.max()), 'p2_5': float(np.quantile(v, .025)), 'p97_5': float(np.quantile(v, .975))}
    res = {'lam': lam, 'rho_c': round(rc, 4), 'stats': out}
    if kinds is not None:
        res['kinds'] = {'pi_f': kinds[0], 'pi_r': kinds[1], 'pi_A': kinds[2]}
        res['vector_draws'] = {t: {'weighted': drawn[t][0], 'unweighted': drawn[t][1]} for t in C.TASKS}
    return idx, res


def old_resolution(old, name, N, lam, rc_index, new_rhos):
    """The 9 November p_resolved for the same cell, from ladder-pooled3-c3-20261109.json.
    The cells are matched by lambda, N and the rank of rho_C. The fitted rho_C is 0.444 in the
    old file and a different value in the new one, and it is the third of the four values in both."""
    old_rhos = sorted({c['rho_c'] for c in old['cells']})
    rc = old_rhos[rc_index]
    for c in old['cells']:
        if c['lam'] == lam and c['N'] == N and abs(c['rho_c'] - rc) < 1e-9:
            if name in c['pooled']:
                return c['pooled'][name]['p_resolved']
            t, band = name[4:].split(' ', 1)
            return c['band_D_minus_A'][f'{t} {band}']['p_resolved']
    raise KeyError((name, N, lam, rc))


def report(new, old, dev):
    """Print the tables of notes/SAMPLE-SIZE-RERUN-20261111.md as markdown."""
    cells = new['cells']
    new_rhos = sorted({c['rho_c'] for c in cells})
    out = []
    pct = lambda x: f'{100 * x:.1f}'
    out.append('### Table 1: worst resolution of each primary interval over the 12 (lambda, rho_C) combinations\n')
    out.append('Each entry is the lowest percentage of runs, over the 12 combinations, in which the interval is not unresolved at margin 0.20. "9 Nov" is the lowest for the same interval and N in `ladder-pooled3-c3-20261109.json`. The combination that gives the new minimum is in brackets as (lambda, rho_C).\n')
    out.append('| Interval | N | New worst | Combination | 9 Nov worst | New worst at margin 0.10 | New worst, task-dependent runs not counted |')
    out.append('|---|---|---|---|---|---|---|')
    summary = {}
    for name in primary_names():
        for N in NS:
            cs = [c for c in cells if c['N'] == N]
            w = min(cs, key=lambda c: (c['intervals'][name]['p_resolved']['margin 0.20'], c['lam'], c['rho_c']))
            r = w['intervals'][name]['p_resolved']['margin 0.20']
            o = min(old_resolution(old, name, N, c['lam'], new_rhos.index(c['rho_c']), new_rhos) for c in cs)
            r10 = min(c['intervals'][name]['p_resolved']['margin 0.10'] for c in cs)
            strict = min(c['intervals'][name].get('p_resolved_strict_margin_0_20', c['intervals'][name]['p_resolved']['margin 0.20']) for c in cs)
            summary[(name, N)] = (r, w['lam'], w['rho_c'])
            out.append(f"| {name} | {N} | {pct(r)} | ({w['lam']}, {w['rho_c']}) | {pct(o)} | {pct(r10)} | {pct(strict) if name in POOLED else 'same'} |")
    out.append('')
    for N in NS:
        m = min((v[0], k) for k, v in summary.items() if k[1] == N)
        out.append(f'Lowest at N = {N}: {pct(m[0])}% for {m[1][0]}.')
    out.append('')
    out.append('### Table 2: runs in which the three tasks point in opposite directions\n')
    out.append('A combination is marked "opposite" when its mean per-task estimates (over the simulated runs) include a positive and a negative value. This is the only definition used, and it has no size threshold. The first table lists the combinations at N = 32 that are marked opposite; the second gives the range over every N. Columns give the share of runs in which each rule fires, and the share of runs whose pooled class is "equivalent and not different" (no gain as large as the margin) when the rule does not fire. "Present rule": one task interval wholly above 0 and another wholly below. "Pair rule": for some pair of tasks the 95% interval of the difference between their step estimates excludes 0 and the two estimates have opposite signs. "Pair, any sign": the same without the sign condition.\n')
    out.append('| Step | N | lambda | rho_C | Mean estimate by task (reach, reach3d, land) | Opposite | Present rule fires | Pair rule fires | Pair, any sign | No gain class, present rule | No gain class, pair rule |')
    out.append('|---|---|---|---|---|---|---|---|---|---|---|')
    fire = {}
    for key in POOLED:
        for c in cells:
            o = c['opposite'][key]
            est = [o['mean_per_task_estimate'][t] for t in C.TASKS]
            opp = min(est) < 0 < max(est)
            fire.setdefault((key, opp), []).append((o['p_rule_task_dependent'], o['p_rule_pair_difference_signed'], o['p_rule_pair_difference_any_sign']))
            if opp and c['N'] == 32:
                out.append(f"| {key} | {c['N']} | {c['lam']} | {c['rho_c']} | {', '.join(f'{x:+.2f}' for x in est)} | yes | {pct(o['p_rule_task_dependent'])} | {pct(o['p_rule_pair_difference_signed'])} | {pct(o['p_rule_pair_difference_any_sign'])} | {pct(o['pooled_class_under_present_rule']['equivalent_not_different'])} | {pct(o['pooled_class_under_pair_rule']['equivalent_not_different'])} |")
    out.append('')
    out.append('Rates over combinations where the three mean estimates agree in sign (the cost of a rule firing when it should not), lowest to highest over combinations and N:\n')
    out.append('| Step | Combinations | Present rule | Pair rule | Pair, any sign |')
    out.append('|---|---|---|---|---|')
    for key in POOLED:
        for opp in (False, True):
            rows = fire.get((key, opp))
            if rows:
                f = lambda i: f'{pct(min(r[i] for r in rows))} to {pct(max(r[i] for r in rows))}'
                out.append(f"| {key} | {'opposite' if opp else 'same sign'} ({len(rows)} cells) | {f(0)} | {f(1)} | {f(2)} |")
    out.append('')
    out.append('### Table 3: arm B adopts nothing\n')
    out.append('Share of simulated blocks in which arm B adopts no procedure, lowest to highest over the cells with that lambda (all rho_C and N). Arm B does not depend on rho_C.\n')
    out.append('| Task | lambda = 0 | lambda = 0.5 | lambda = 1 | All cells |')
    out.append('|---|---|---|---|---|')
    for t in C.TASKS:
        cols = []
        allv = []
        for lam in LAMS:
            v = [c['nonadoption'][t]['B'] for c in cells if c['lam'] == lam]
            allv += v
            cols.append(f'{pct(min(v))} to {pct(max(v))}')
        out.append(f"| {t} | {' | '.join(cols)} | {pct(min(allv))} to {pct(max(allv))} |")
    out.append('')
    if dev is not None:
        out.append(f"### Table 4: what the development sample ({dev['dev_blocks']} blocks per task, {3 * dev['dev_blocks']} in all) may show\n")
        out.append('Union over the 12 (lambda, rho_C) combinations. "Central 95%" is the lowest 2.5th and the highest 97.5th percentile of the statistic over simulated development samples; "full range" is the lowest and highest value seen in any simulated sample. Counts are numbers of blocks.\n')
        out.append('| Statistic | Central 95% | Full range |')
        out.append('|---|---|---|')
        names = list(dev['cells'][0]['stats'])
        for k in names:
            lo = min(c['stats'][k]['p2_5'] for c in dev['cells']); hi = max(c['stats'][k]['p97_5'] for c in dev['cells'])
            flo = min(c['stats'][k]['min'] for c in dev['cells']); fhi = max(c['stats'][k]['max'] for c in dev['cells'])
            fmt = (lambda x: f'{x:.0f}') if 'adopt' in k and 'success' not in k or 'passes' in k else (lambda x: f'{x:.2f}')
            out.append(f'| {k} | {fmt(lo)} to {fmt(hi)} | {fmt(flo)} to {fmt(fhi)} |')
    print('\n'.join(out))


def resolved_66(row):
    """Section 6.6's share of runs resolved: a pooled run named task-dependent counts as resolved,
    because that name is a definite result (section 6.4). The two parts are disjoint. A per-task
    interval has no such name and its share is p_resolved as it stands."""
    if 'p_resolved_strict_margin_0_20' in row:
        return row['p_resolved_strict_margin_0_20'] + row['p_task_dependent']
    return row['p_resolved']['margin 0.20']


def resolved_count(row, sims):
    """Runs resolved under section 6.6, as an integer (a pooled run named task-dependent counts)."""
    parts = [row['p_resolved_strict_margin_0_20'], row['p_task_dependent']] if 'p_resolved_strict_margin_0_20' in row else [row['p_resolved']['margin 0.20']]
    return sum(round(x * sims) for x in parts)


def meets_80(row, sims):
    """The 80% test in integers: 5 * count >= 4 * sims, so 800 of 1,000 passes."""
    return 5 * resolved_count(row, sims) >= 4 * sims


def label_for(v, lo, hi, flo, fhi):
    if lo <= v <= hi:
        return 'inside the central 95% range'
    if flo <= v <= fhi:
        return 'inside the full range only'
    return 'outside the full range'


def acceptance(dev, chk):
    """Compare each row of the development check with the union over the development table's
    cells. Returns (lines, outside) where outside lists the rows outside the full range."""
    lines, outside = [], []
    for row in chk['rows']:
        k, v = row['statistic'], row['value']
        flo = min(c['stats'][k]['min'] for c in dev['cells']); fhi = max(c['stats'][k]['max'] for c in dev['cells'])
        lo = min(c['stats'][k]['p2_5'] for c in dev['cells']); hi = max(c['stats'][k]['p97_5'] for c in dev['cells'])
        lab = label_for(v, lo - 1e-9, hi + 1e-9, flo - 1e-9, fhi + 1e-9)
        lines.append(f'{k}: {v:g} central {lo:g} to {hi:g}, full {flo:g} to {fhi:g}: {lab}')
        if lab == 'outside the full range':
            outside.append(k)
    return lines, outside


def report_corrected(grid_path, old_path, dev_path, check_path, parts=None, sims=None, boot=None, seed=None):
    """Print the two tables of notes/SAMPLE-SIZE-RERUN-20261119.md and what section 6.6's rule gives."""
    new, old, dev, chk = (json.loads(Path(x).read_text()) for x in (grid_path, old_path, dev_path, check_path))
    ns = tuple(sorted({c['N'] for c in new['cells']}))
    if parts is not None:  # refuse to build any table from parts or output that do not match the grid
        rd = new['fitted']['rho_d']
        check_parts(parts, rd, sims, boot, seed, ns)
        check_cells(new['cells'], rd, sims, boot, seed, ns)
    pct = lambda x: f'{100 * x:.1f}'
    out = ['### The nine rates (ruling 72, point 4)\n', '| Rate | Count | Lower end | Share | Upper end |', '|---|---|---|---|---|']
    for k, (lo, sh, hi) in new['kind_values'].items():
        c = new['kind_counts'][k]
        out.append(f'| {k} | {c[0]} of {c[1]} | {lo:.4f} | {sh:.4f} | {hi:.4f} |')
    out.append('')
    out.append(f"### Table A: the development table of the corrected model, with the sample's value\n")
    out.append(f"Union over the {len(dev['cells'])} combinations of the three rates, lambda and rho_C, each with {dev['sims']} simulated samples of {dev['dev_blocks']} blocks per task.\n")
    out.append("| Statistic | Sample | Central 95% | Full range | Where the sample falls |")
    out.append('|---|---|---|---|---|')
    outside = []
    for row in chk['rows']:
        k = row['statistic']
        lo = min(c['stats'][k]['p2_5'] for c in dev['cells']); hi = max(c['stats'][k]['p97_5'] for c in dev['cells'])
        flo = min(c['stats'][k]['min'] for c in dev['cells']); fhi = max(c['stats'][k]['max'] for c in dev['cells'])
        v = row['value']
        fmt = (lambda x: f'{x:.0f}') if 'adopt' in k and 'success' not in k or 'passes' in k else (lambda x: f'{x:.2f}')
        lab = label_for(v, lo - 1e-9, hi + 1e-9, flo - 1e-9, fhi + 1e-9)
        if lab == 'outside the full range':
            outside.append(k)
        out.append(f'| {k} | {fmt(v)} | {fmt(lo)} to {fmt(hi)} | {fmt(flo)} to {fmt(fhi)} | {lab} |')
    out.append('')
    out.append('Rows outside the full range: ' + (', '.join(outside) if outside else 'none') + '.\n')
    names = primary_names()
    old_cells = {}
    for c in old['cells']:
        old_cells.setdefault(c['N'], []).append(c)
    out.append('### Table B: the lowest share of runs resolved, over the 324 combinations\n')
    out.append('Resolved means the class is anything but unresolved, at margin 0.20, and a pooled run named task-dependent counts as resolved (section 6.6). The combination is (pi_f, pi_r, pi_A, lambda, rho_C). "11 Nov" is the lowest over that day\'s 12 combinations at the same N.\n')
    out.append('| Interval | N | Lowest, 324 combinations (%) | Combination | Lowest, 12 settings at the observed rates (%) | Combinations at 80% or more, of 324 | 11 Nov (%) |')
    out.append('|---|---|---|---|---|---|---|')
    observed = tuple(v[1] for v in (new['kind_values'][k] for k in ('pi_f', 'pi_r', 'pi_A')))
    worst = {}
    for name in names:
        for N in ns:
            cs = [c for c in new['cells'] if c['N'] == N]
            w = min(cs, key=lambda c: resolved_66(c['intervals'][name]))
            r = resolved_66(w['intervals'][name])
            worst[(name, N)] = r
            kd = w['kinds']
            o = min((resolved_66(c['intervals'][name]) for c in old_cells.get(N, [])), default=None)
            obs = [c for c in cs if (c['kinds']['pi_f'], c['kinds']['pi_r'], c['kinds']['pi_A']) == observed]
            ro = min(resolved_66(c['intervals'][name]) for c in obs)
            ok = sum(meets_80(c['intervals'][name], c.get('sims', new['sims'])) for c in cs)
            out.append(f"| {name} | {N} | {pct(r)} | ({kd['pi_f']:.4f}, {kd['pi_r']:.4f}, {kd['pi_A']:.4f}, {w['lam']}, {w['rho_c']}) | {pct(ro)} | {ok} of {len(cs)} | {pct(o) if o is not None else 'not run'} |")
    out.append('')
    for N in ns:
        m = min((v, k[0]) for k, v in worst.items() if k[1] == N)
        out.append(f'Lowest at N = {N}: {pct(m[0])}% for {m[1]}.')
    out.append('')
    meets = [N for N in ns if all(meets_80(c['intervals'][n], c.get('sims', new['sims'])) for c in new['cells'] if c['N'] == N for n in names)]
    exact = sum(5 * resolved_count(c['intervals'][n], c.get('sims', new['sims'])) == 4 * c.get('sims', new['sims']) for c in new['cells'] for n in names)
    out.append(f'Cells (interval by combination by N) that lie exactly at 80%: {exact}.\n')
    out.append("Section 6.6's rule (every interval resolved in at least 80% of runs in every combination): " + (f'the smallest N that meets it is {meets[0]}.' if meets else f"no N of {', '.join(map(str, ns))} meets it."))
    strict = {}
    for N in ns:
        cs = [c for c in new['cells'] if c['N'] == N]
        strict[N] = min(min(c['intervals'][n].get('p_resolved_strict_margin_0_20', c['intervals'][n]['p_resolved']['margin 0.20']) for c in cs) for n in names)
    out.append('Lowest figure when a pooled run that ends task-dependent is not counted as resolved (not the rule): ' + ', '.join(f'N = {N}: {pct(v)}%' for N, v in strict.items()) + '.\n')
    out.append('### Forecast cost and run time for each N (ruling 85, point 6)\n')
    out.append('Cost is US$0.29 charged a block (US$3.4872 for the sample\'s 12 blocks) for 3 N blocks. Run time is 0.73 hours a block on four workers for each of the three task jobs (ruling 77, point 5). These are forecasts, not simulation results.\n')
    out.append('| N | Cost (US$) | Run time per task job (hours) |')
    out.append('|---|---|---|')
    for N in ns:
        out.append(f'| {N} | {0.29 * 3 * N:.0f} | {0.73 * N:.0f} |')
    out.append('')
    out.append('### Vector draws with no weighted choice (every weight 0), over the grid and the development table\n')
    out.append('| Task | Grid: draws | Grid: unweighted | Development: draws | Development: unweighted |')
    out.append('|---|---|---|---|---|')
    for t in C.TASKS:
        gw = sum(c['vector_draws'][t]['weighted'] for c in new['cells']); gu = sum(c['vector_draws'][t]['unweighted'] for c in new['cells'])
        dw = sum(c['vector_draws'][t]['weighted'] for c in dev['cells']); du = sum(c['vector_draws'][t]['unweighted'] for c in dev['cells'])
        out.append(f'| {t} | {gw + gu} | {gu} | {dw + du} | {du} |')
    print('\n'.join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=Path, default=None, help="scored-2's run folder (read only)")
    ap.add_argument('--audit', type=Path, default=Path(__file__).resolve().parents[2] / L.AUDIT)
    ap.add_argument('--out', type=Path, default=None)
    ap.add_argument('--parts', type=Path, default=None, help='folder for finished cells, so a stopped run resumes')
    ap.add_argument('--sims', type=int, default=1000)
    ap.add_argument('--boot', type=int, default=500)
    ap.add_argument('--seed', type=int, default=20261114)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--dev', action='store_true')
    ap.add_argument('--dev-blocks', type=int, default=4)
    ap.add_argument('--stop-after', type=float, default=None, help='epoch seconds: dispatch no new cell after this')
    ap.add_argument('--report', nargs='+', metavar='JSON', help='POOLED_JSON OLD_JSON [DEV_JSON]: print the tables')
    ap.add_argument('--only-n', type=int, nargs='+', default=None)
    ap.add_argument('--kinds', action='store_true', help='the corrected model of ruling 72 (see the module note)')
    ap.add_argument('--pools', type=Path, default=None, help='read pools and fitted counts from this earlier output file instead of --runs')
    ap.add_argument('--report-corrected', nargs=4, metavar=('GRID_JSON', 'OLD_GRID_JSON', 'DEV_JSON', 'DEVCHECK_JSON'), help='print the two tables of the 19 November note')
    ap.add_argument('--ns', type=int, nargs='+', default=list(NS_KINDS), help='with --kinds: the N values of the grid')
    ap.add_argument('--check-parts', type=Path, default=None, help='with --report-corrected: refuse to build any table unless every part in this folder and every cell of the output has the --sims, --boot, --seed, N, rates and settings its index gives')
    ap.add_argument('--acceptance', nargs=2, type=Path, metavar=('DEV_JSON', 'DEVCHECK_JSON'), help='exit 1 if any row of the development check is outside the full range of the development table')
    ap.add_argument('--only-kinds', type=int, nargs='+', default=None, help='with --kinds: run only these combinations (0 to 26), for timing')
    a = ap.parse_args()
    if a.acceptance:
        lines, outside = acceptance(json.loads(a.acceptance[0].read_text()), json.loads(a.acceptance[1].read_text()))
        print('\n'.join(lines))
        print(f'{len(lines)} rows, {len(outside)} outside the full range' + (': ' + '; '.join(outside) if outside else ''))
        sys.exit(1 if outside or not lines else 0)
    if a.report_corrected:
        if a.check_parts is None:
            report_corrected(*a.report_corrected)
        else:
            report_corrected(*a.report_corrected, parts=a.check_parts, sims=a.sims, boot=a.boot, seed=a.seed)
        return
    if a.report:
        new, old = (json.loads(Path(x).read_text()) for x in a.report[:2])
        report(new, old, json.loads(Path(a.report[2]).read_text()) if len(a.report) > 2 else None)
        return
    raw, counts, q, rd, tp, m0 = setup_from_json(a.pools) if a.pools else setup(a.runs, a.audit)
    G.update(raw=raw, q=q, rd=rd)
    a.parts.mkdir(parents=True, exist_ok=True)
    meta = {'counts': counts, 'fitted': {'q': q, 'rho_d': rd, 'p1_close_pass': tp, 'p0_close_pass': m0},
            'seed': a.seed, 'sims': a.sims, 'boot': a.boot,
            'analysis3_blob_sha1': blob_hash(Path(A.__file__)), 'analysis3_boot_n_in_real_analysis': C.BOOT_N,
            'pools': {t: {'P0_close': raw[t][0].tolist(), 'P1_close': raw[t][1].tolist()} for t in C.TASKS}}
    if a.kinds:
        meta['model'] = 'corrected, ruling 72'
        meta['kind_counts'] = {k: list(v) for k, v in L.KIND_COUNTS.items()}
        meta['kind_values'] = {k: list(v) for k, v in L.kind_values().items()}
    ctx = mp.get_context('fork')
    if a.dev:
        if a.kinds:
            cells = [(lam, rc, k) for k in L.kind_combinations() for lam in LAMS for rc in (-0.5, 0.0, rd, 0.9)]
            seeds = np.random.SeedSequence(a.seed).spawn(len(cells))
            jobs = [(i, c[:2], seeds[i], a.sims, a.dev_blocks, c[2]) for i, c in enumerate(cells)]
        else:
            cells = [(lam, rc) for lam in LAMS for rc in (-0.5, 0.0, rd, 0.9)]
            seeds = np.random.SeedSequence(a.seed).spawn(len(cells))
            jobs = [(i, c, seeds[i], a.sims, a.dev_blocks) for i, c in enumerate(cells)]
        with ctx.Pool(a.workers) as pool:
            res = dict(pool.map(dev_worker, jobs))
        out = dict(meta, dev_blocks=a.dev_blocks, cells=[res[i] for i in range(len(cells))])
        a.out.write_text(json.dumps(out, indent=1) + '\n')
        return
    if a.kinds:
        cells4 = grid_kinds(rd, tuple(a.ns))
        cells = [c[:3] for c in cells4]
        kin = [c[3] for c in cells4]
    else:
        cells = grid(rd)
        kin = [None] * len(cells)
    seeds = np.random.SeedSequence(a.seed).spawn(len(cells))
    order = sorted(range(len(cells)), key=lambda i: ((a.ns.index(cells[i][2]) if a.kinds else {32: 0, 24: 1, 40: 2, 48: 3}[cells[i][2]]), i))
    if a.only_n:
        order = [i for i in order if cells[i][2] in a.only_n]
    if a.only_kinds is not None:
        per = len(LAMS) * 4 * len(a.ns)
        order = [i for i in order if i // per in a.only_kinds]
        a.only_n = a.only_n or list(a.ns)  # a partial run writes cells only
    todo = []
    for i in order:
        lam, rc, N = cells[i]
        todo.append((i, cells[i], seeds[i], a.sims, a.boot, a.parts / f'cell-{i:03d}-lam{lam}-rc{rc:.4f}-N{N}.json' if a.kinds else a.parts / f'cell-{i:02d}-lam{lam}-rc{rc:.4f}-N{N}.json', a.stop_after) + ((kin[i],) if a.kinds else ()))
    done = {}
    with ctx.Pool(a.workers) as pool:
        for i, cell in pool.imap_unordered(cell_worker, todo):
            if cell is None:
                print('deadline reached; not started', i, cells[i], flush=True)
                continue
            done[i] = cell
            print('done', i, cells[i], flush=True)
    def pname(i):
        return a.parts / ((f'cell-{i:03d}' if a.kinds else f'cell-{i:02d}') + f'-lam{cells[i][0]}-rc{cells[i][1]:.4f}-N{cells[i][2]}.json')
    missing = [i for i in range(len(cells)) if i not in done and not pname(i).exists()]
    if missing and not a.only_n:
        print('cells not finished:', missing)
        return
    if a.only_n:
        return
    out = dict(meta, cells=[done.get(i) or json.loads(pname(i).read_text()) for i in range(len(cells))])
    if a.kinds:
        check_cells(out['cells'], rd, a.sims, a.boot, a.seed, tuple(a.ns))  # refuses a stale or foreign part
    a.out.write_text(json.dumps(out, indent=1) + '\n')


if __name__ == '__main__':
    main()

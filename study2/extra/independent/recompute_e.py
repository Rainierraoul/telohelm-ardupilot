#!/usr/bin/env python3
"""Independent recomputation of B - A, C - B, E - B and C - E for Paper 3's extra experiment.

Written from PROTOCOL-3.md (sections 4.2, 6.1, 6.2, 6.3) and PROTOCOL-EXTRA.md (sections 3, 4, 6) only.
It reads the raw records read-only and writes nothing into them.

Outcome (PROTOCOL-3.md 6.1, PROTOCOL-EXTRA.md 4): for each task, arm, block and the task's 24 zone evaluation
flights named in the seed book, a cell is 1 if the arm adopted a source in that block and that source met the goal
on that flight, else 0.

Where a source's flights are read from: arms A, B and C from Study 2's evaluation phase for that block and source.
Arm E from Study 2's phase when Study 2 flew the same source in the same block, otherwise from arm E's own run.
Arm E's run also holds re-flights of Study 2 sources (the platform control, PROTOCOL-EXTRA.md 6); these are never
scored, and the program checks that the phases it leaves unscored are exactly the control list in schedule.json.

Resampling (PROTOCOL-3.md 6.2): per task, 10,000 resamples; each draws the 40 blocks with replacement, keeping a
block's arms together, and draws 8 scenarios with replacement within each band, the same scenario draw for every
block and arm. A pooled resample is the mean of the three tasks' resamples with the same index. Percentile intervals.

Usage: python3 recompute_e.py [OUTPUT_DIR]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

S2_RUNS = ('/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/release-candidate-20261122/'
           'reproduce-check/records/runs')
E_RUNS = '/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/extra-e1'
SEEDS = '/Users/s.vajda/Development/telohelm-worktrees/p3-extra-arm/paper3/protocol/seeds-3.json'
SEEDS_SHA_PREFIX = '1d39a62c'

TASKS = ('reach', 'reach3d', 'land')          # task index 0, 1, 2 as in contract3.TASKS
BANDS = ('close', 'middle', 'wide')
ARMS = ('A', 'B', 'C', 'E')
N_BLOCKS = 40
PER_BAND = 8
N_SCEN = PER_BAND * len(BANDS)
COMPARISONS = (('B', 'A'), ('C', 'B'), ('E', 'B'), ('C', 'E'))

BOOT_N = 10000
# Primary seed: the protocol's BOOT_SEED with the protocol's per-task entropy [BOOT_SEED, 0, task index].
# A second, unrelated seed is run as a Monte Carlo check only.
PRIMARY_SEED = 20261112
CHECK_SEED = 777

OPENED: list[str] = []   # every file this program opens, in order
LISTED: list[str] = []   # every directory this program lists (one level, never recursive)


def read_bytes(path: str) -> bytes:
    OPENED.append(path)
    with open(path, 'rb') as f:
        return f.read()


def load_json(path: str):
    return json.loads(read_bytes(path).decode('utf-8'))


def listdir(path: str) -> list[str]:
    LISTED.append(path)
    return sorted(os.listdir(path))


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit('CHECK FAILED: ' + msg)


# ---------------------------------------------------------------- records

def scenario_names(book: dict, task: str) -> list[str]:
    rows = book['threat_evaluation'][task]
    names = []
    for band in BANDS:
        need(len(rows[band]) == PER_BAND, f'{task} {band}: expected {PER_BAND} evaluation seeds')
        names += [f'threat-{band}-{seed}' for seed in rows[band]]
    return names


class Phase:
    """One evaluation phase: 24 goal_met values and end reasons in seed-book order."""

    def __init__(self, root: str, task: str, block: int, sha: str, names: list[str], logs: set[str]):
        self.name = f'threat3-{task}-b{block}-{sha}'
        self.root = root
        folder = f'{root}/{self.name}'
        need(os.path.isdir(folder), f'missing phase folder {folder}')
        need(f'{self.name}.done' in logs, f'{self.name} has no done mark in {root}/logs')
        manifest = load_json(f'{folder}/manifest.json')
        args = manifest['args']
        need(manifest['phase'] == 'threat3', f'{self.name}: manifest phase')
        need(manifest['pilot'] is False, f'{self.name}: pilot flag')
        need(manifest['seeds_sha256'].startswith(SEEDS_SHA_PREFIX), f'{self.name}: seed book hash')
        need(args['task'] == task and args['block'] == block and args['source_sha256'] == sha,
             f'{self.name}: manifest args do not name this task, block and source')
        self.manifest_arms = list(args['arms'])
        self.includes_c0 = bool(args.get('includes_c0'))
        self.kept_late_file = os.path.isfile(f'{folder}/kept-late.json')   # existence only, not opened
        flights = f'{folder}/flights'
        present = [d for d in listdir(flights) if d.startswith('threat-')]
        need(sorted(present) == sorted(names),
             f'{self.name}: flight folders {len(present)} do not equal the 24 scheduled scenarios')
        cfg = load_json(f'{flights}/run-config.json')
        self.source_hash_ok = hashlib.sha256(cfg['source'].encode('utf-8')).hexdigest() == sha
        self.goal = np.zeros(N_SCEN, dtype=np.int64)
        self.entered = np.zeros(N_SCEN, dtype=np.int64)
        self.end_reasons = []
        for i, n in enumerate(names):
            o = load_json(f'{flights}/{n}/outcome.json')
            need(o['task'] == task, f'{self.name}/{n}: task field')
            need(isinstance(o['goal_met'], bool), f'{self.name}/{n}: goal_met not boolean')
            self.goal[i] = int(o['goal_met'])
            self.entered[i] = int(o['end_reason'] == 'entered_threat')
            self.end_reasons.append(o['end_reason'])


def load_task(book: dict, task: str, out: list[str]):
    names = scenario_names(book, task)
    s2_root = f'{S2_RUNS}/scored-20261120-S-{task}'
    e_root = f'{E_RUNS}/extra-e1-{task}/runs/extra-e1-{task}'
    s2_logs = set(listdir(f'{s2_root}/logs'))
    e_logs = set(listdir(f'{e_root}/logs'))
    s2_top = set(listdir(s2_root))
    e_top = set(listdir(e_root))
    schedule = load_json(f'{e_root}/logs/schedule.json')
    need(schedule.get('task') == task and schedule.get('pilot') is False, f'{task}: arm E schedule header')
    control_names = sorted(c[0] for c in schedule['control'])

    phases: dict[tuple[str, str], Phase] = {}

    def phase(root, block, sha, logs):
        key = (root, f'threat3-{task}-b{block}-{sha}')
        if key not in phases:
            phases[key] = Phase(root, task, block, sha, names, logs)
        return phases[key]

    cells = np.zeros((len(ARMS), N_BLOCKS, N_SCEN), dtype=np.int64)
    entered = np.zeros((len(ARMS), N_BLOCKS, N_SCEN), dtype=np.int64)
    adopted = np.zeros((len(ARMS), N_BLOCKS), dtype=bool)
    info = []   # per block: dict of facts for the arm E counts
    e_scored_in_e_root = set()
    c0_checks = {'c0_passed': 0, 'e_took_c0_when_passed': 0}

    for b in range(N_BLOCKS):
        need(f'learn3-{task}-b{b}.done' in s2_logs, f'{task} b{b}: Study 2 block has no done mark')
        need(f'learnE-{task}-b{b}.done' in e_logs, f'{task} b{b}: arm E block has no done mark')
        s2_arms_path = f'{s2_root}/learn3-{task}-b{b}/arms.json'
        s2_bytes = read_bytes(s2_arms_path)
        s2 = json.loads(s2_bytes.decode('utf-8'))
        e = load_json(f'{e_root}/learnE-{task}-b{b}/arms.json')
        need(s2['task'] == task and s2['block'] == b, f'{task} b{b}: Study 2 arms.json header')
        need(e['task'] == task and e['block'] == b, f'{task} b{b}: arm E arms.json header')
        need(e['study2_block']['folder'] == f'learn3-{task}-b{b}', f'{task} b{b}: arm E names another Study 2 block')
        need(e['study2_block']['arms_sha256'] == hashlib.sha256(s2_bytes).hexdigest(),
             f'{task} b{b}: arm E was built from a different Study 2 arms.json')
        need(list(e['arms'].keys()) == ['E'], f'{task} b{b}: arm E arms.json holds other arms')

        rows = {a: s2['arms'][a] for a in ('A', 'B', 'C')}
        rows['E'] = e['arms']['E']
        if s2['c0_zone_qualified']:
            c0_checks['c0_passed'] += 1
            if rows['E']['adopted'] and rows['E']['candidate_id'] == 'c0' \
                    and rows['E']['source_sha256'] == rows['C']['source_sha256']:
                c0_checks['e_took_c0_when_passed'] += 1

        block_info = {'block': b}
        for k, arm in enumerate(ARMS):
            r = rows[arm]
            if not r['adopted']:
                need(r['source_sha256'] is None, f'{task} b{b} {arm}: source named without adoption')
                continue
            sha = r['source_sha256']
            need(isinstance(sha, str) and len(sha) == 64, f'{task} b{b} {arm}: bad source hash')
            pname = f'threat3-{task}-b{b}-{sha}'
            if pname in s2_top:
                ph = phase(s2_root, b, sha, s2_logs)
                where = 'study2'
            else:
                need(arm == 'E', f'{task} b{b} {arm}: Study 2 never flew its adopted source')
                need(pname in e_top, f'{task} b{b} E: adopted source flown nowhere')
                need(pname not in control_names, f'{task} b{b} E: would score a control re-flight')
                ph = phase(e_root, b, sha, e_logs)
                need(ph.manifest_arms == ['E'], f'{pname}: arm E phase manifest names arms {ph.manifest_arms}')
                e_scored_in_e_root.add(pname)
                where = 'arm E run'
            if where == 'study2':
                need(arm in ph.manifest_arms or arm == 'E',
                     f'{pname}: Study 2 manifest does not list arm {arm}')
            adopted[k, b] = True
            ph.scored_for = getattr(ph, 'scored_for', []) + [arm]
            cells[k, b] = ph.goal
            entered[k, b] = ph.entered
            if arm == 'E':
                block_info.update({'cand': r['candidate_id'], 'where': where, 'sha': sha})
        info.append(block_info)

    # The arm E run's phases that were not scored must be exactly the platform control.
    e_phases = sorted(p for p in e_top if p.startswith('threat3-'))
    unscored = sorted(set(e_phases) - e_scored_in_e_root)
    need(unscored == control_names, f'{task}: unscored arm E phases {unscored} != control list {control_names}')
    for p in unscored:
        need(p in s2_top, f'{task}: control phase {p} is not a re-flight of a Study 2 phase')

    # Diagnostic only, never scored: where arm E adopted the very source the control re-flew in that block, how many
    # of the 24 cells would change if the re-flight were scored in place of Study 2's flights.
    control_overlap = []
    for bi in info:
        if 'sha' not in bi:
            continue
        pname = f'threat3-{task}-b{bi["block"]}-{bi["sha"]}'
        if pname in control_names:
            redo = Phase(e_root, task, bi['block'], bi['sha'], names, e_logs)
            orig = phases[(s2_root, pname)]
            control_overlap.append((bi['block'], bi['cand'], int(orig.goal.sum()), int(redo.goal.sum()),
                                    int((orig.goal != redo.goal).sum())))

    kept_late = sorted(f'{n} (scored for arms {",".join(ph.scored_for)})'
                       for (root, n), ph in phases.items() if ph.kept_late_file)
    hash_bad = sorted(n for (root, n), ph in phases.items() if not ph.source_hash_ok)
    return {
        'cells': cells, 'entered': entered, 'adopted': adopted, 'info': info,
        'control': control_names, 'n_phases': len(phases), 'kept_late': kept_late,
        'hash_bad': hash_bad, 'c0': c0_checks,
        'n_e_root_scored': len(e_scored_in_e_root), 'control_overlap': control_overlap,
    }


# ---------------------------------------------------------------- bootstrap

def draws(seed_entropy):
    """One set of all-band draws for one task. Order: the block draws of every resample, then the scenario draws
    of the close, middle and wide bands in turn. Returned as count matrices so a resample's statistic is a
    weighted sum over the original table."""
    rng = np.random.default_rng(seed_entropy)
    blk = rng.integers(0, N_BLOCKS, size=(BOOT_N, N_BLOCKS))
    scen = np.concatenate([rng.integers(0, PER_BAND, size=(BOOT_N, PER_BAND)) + PER_BAND * j
                           for j in range(len(BANDS))], axis=1)
    wb = np.zeros((BOOT_N, N_BLOCKS), dtype=np.int64)
    ws = np.zeros((BOOT_N, N_SCEN), dtype=np.int64)
    rows = np.arange(BOOT_N)[:, None]
    np.add.at(wb, (rows, blk), 1)
    np.add.at(ws, (rows, scen), 1)
    return wb, ws, blk, scen


def resampled_totals(diff: np.ndarray, wb: np.ndarray, ws: np.ndarray) -> np.ndarray:
    """Integer sum of the difference over the resampled blocks x resampled scenarios, per resample."""
    return ((wb @ diff) * ws).sum(axis=1)


def bootstrap(tables: dict, seed: int):
    """Returns {comparison: {'task': {task: array}, 'pooled': array}} of resampled differences."""
    denom = N_BLOCKS * N_SCEN
    res = {cmp: {'task': {}} for cmp in COMPARISONS}
    for ti, task in enumerate(TASKS):
        wb, ws, blk, scen = draws([seed, 0, ti])
        cells = tables[task]['cells']
        tot = {}
        for x, y in COMPARISONS:
            diff = cells[ARMS.index(x)] - cells[ARMS.index(y)]
            tot[(x, y)] = resampled_totals(diff, wb, ws)
            res[(x, y)]['task'][task] = tot[(x, y)] / denom
            # Self-check of the count-matrix shortcut against direct indexing, on the first 200 resamples.
            for r in range(200):
                direct = int(diff[blk[r]][:, scen[r]].sum())
                need(direct == int(tot[(x, y)][r]), f'{task} {x}-{y}: resample {r} shortcut != direct')
        # PROTOCOL-EXTRA.md 4: E - B plus C - E equals C - B in every resample.
        need(np.array_equal(tot[('E', 'B')] + tot[('C', 'E')], tot[('C', 'B')]),
             f'{task}: E-B + C-E != C-B in some resample')
    for cmp in COMPARISONS:
        res[cmp]['pooled'] = np.mean([res[cmp]['task'][t] for t in TASKS], axis=0)
    return res


def pct(a, lo, hi):
    q = np.percentile(a, [lo, hi])   # numpy's default (linear) percentile
    return float(q[0]), float(q[1])


# ---------------------------------------------------------------- main

def main() -> None:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    seeds_bytes = read_bytes(SEEDS)
    seeds_sha = hashlib.sha256(seeds_bytes).hexdigest()
    need(seeds_sha.startswith(SEEDS_SHA_PREFIX), f'seed book hash {seeds_sha}')
    book = json.loads(seeds_bytes.decode('utf-8'))

    lines: list[str] = []
    p = lines.append
    p('Independent recomputation of B-A, C-B, E-B and C-E (Paper 3, Study 2 and arm E)')
    p(f'numpy {np.__version__}; seed book sha256 {seeds_sha}')
    p('')

    tables = {}
    for task in TASKS:
        tables[task] = load_task(book, task, lines)

    p('== Record checks')
    for task in TASKS:
        t = tables[task]
        p(f'{task}: 40 Study 2 blocks and 40 arm E blocks with done marks; {t["n_phases"]} scored evaluation phases, '
          f'each with a done mark and exactly the 24 seed-book flights; {t["n_e_root_scored"]} read from the arm E run.')
        p(f'  unscored arm E phases = schedule.json control list: {", ".join(n.split("-")[2] + "-" + n.split("-")[3][:8] for n in t["control"])}')
        for blk, cand, n_orig, n_redo, n_diff in t['control_overlap']:
            p(f'  b{blk}: arm E adopted {cand}, the source the control re-flew; scored on Study 2\'s flights '
              f'({n_orig}/24 met). Diagnostic only: the re-flight met {n_redo}/24, {n_diff} cells differ.')
        p(f'  c0 passed its zone trial in {t["c0"]["c0_passed"]} blocks; arm E adopted that same c0 in '
          f'{t["c0"]["e_took_c0_when_passed"]} of them')
        p(f'  scored phases holding kept-late.json (existence checked, file not opened; recorded outcomes kept): '
          f'{len(t["kept_late"])}')
        for n in t['kept_late']:
            p(f'    {n}')
        p(f'  phases whose run-config source does not hash to the folder name: {len(t["hash_bad"])}')
    p('  No block was left out: every arm E block finished, so all 40 blocks per task enter all four arms.')
    p('')

    p('== Arm success, cells met out of 960 per task (40 blocks x 24 flights)')
    p(f'{"task":8s}' + ''.join(f'{a:>16s}' for a in ARMS))
    for task in TASKS:
        c = tables[task]['cells']
        p(f'{task:8s}' + ''.join(f'{int(c[k].sum()):>6d} ({c[k].mean():.6f})' for k in range(len(ARMS))))
    p('Blocks that adopted, out of 40:')
    for task in TASKS:
        ad = tables[task]['adopted']
        p(f'  {task:8s}' + '  '.join(f'{a}={int(ad[k].sum())}' for k, a in enumerate(ARMS)))
    p('')

    point = {}
    for x, y in COMPARISONS:
        per = {t: float((tables[t]['cells'][ARMS.index(x)] - tables[t]['cells'][ARMS.index(y)]).mean())
               for t in TASKS}
        per['pooled'] = float(np.mean([per[t] for t in TASKS]))
        point[(x, y)] = per

    results = {}
    for seed in (PRIMARY_SEED, CHECK_SEED):
        results[seed] = bootstrap(tables, seed)

    for seed in (PRIMARY_SEED, CHECK_SEED):
        label = 'PRIMARY' if seed == PRIMARY_SEED else 'MONTE CARLO CHECK'
        p(f'== {label}: estimates and percentile intervals; numpy default_rng([{seed}, 0, task index]), '
          f'{BOOT_N} resamples')
        p(f'{"comparison":10s} {"scope":8s} {"estimate":>10s}   {"95% interval":>22s}   {"90% interval":>22s}')
        for x, y in COMPARISONS:
            r = results[seed][(x, y)]
            for scope in TASKS + ('pooled',):
                arr = r['task'][scope] if scope != 'pooled' else r['pooled']
                lo95, hi95 = pct(arr, 2.5, 97.5)
                lo90, hi90 = pct(arr, 5, 95)
                p(f'{x}-{y:8s} {scope:8s} {point[(x, y)][scope]:>10.6f}   [{lo95:>9.6f}, {hi95:>9.6f}]   '
                  f'[{lo90:>9.6f}, {hi90:>9.6f}]')
            p('')

    p('== Arm E counts')
    p(f'{"task":8s} {"adopted":>8s} {"by candidate":32s} {"flights":>8s} {"goal met":>9s} {"entered zone":>13s}  where flown')
    tot = [0, 0, 0, 0]
    for task in TASKS:
        t = tables[task]
        k = ARMS.index('E')
        ad = t['adopted'][k]
        by = {}
        where = {}
        for bi in t['info']:
            if 'cand' in bi:
                by[bi['cand']] = by.get(bi['cand'], 0) + 1
                where[bi['where']] = where.get(bi['where'], 0) + 1
        n_ad = int(ad.sum())
        flights = n_ad * N_SCEN
        met = int(t['cells'][k][ad].sum())
        ent = int(t['entered'][k][ad].sum())
        tot = [tot[0] + n_ad, tot[1] + flights, tot[2] + met, tot[3] + ent]
        bys = ', '.join(f'{c}={by[c]}' for c in sorted(by))
        ws_ = ', '.join(f'{w}={where[w]}' for w in sorted(where))
        p(f'{task:8s} {n_ad:>8d} {bys:32s} {flights:>8d} {met:>9d} {ent:>13d}  {ws_}')
    p(f'{"all":8s} {tot[0]:>8d} {"":32s} {tot[1]:>8d} {tot[2]:>9d} {tot[3]:>13d}')
    p('')
    p('Zone entries among each arm\'s adopted flights (for context):')
    for task in TASKS:
        t = tables[task]
        p(f'  {task:8s}' + '  '.join(
            f'{a}: {int(t["entered"][k][t["adopted"][k]].sum())}/{int(t["adopted"][k].sum()) * N_SCEN}'
            for k, a in enumerate(ARMS)))
    p('')
    p(f'Files opened by this program: {len(OPENED)}; directories listed: {len(LISTED)} (see opened-files.txt)')

    text = '\n'.join(lines) + '\n'
    sys.stdout.write(text)
    with open(os.path.join(out_dir, 'opened-files.txt'), 'w') as f:
        f.write('# Files opened by recompute_e.py, in order\n')
        f.write('\n'.join(OPENED) + '\n')
        f.write('\n# Directories listed (one level each)\n')
        f.write('\n'.join(LISTED) + '\n')


if __name__ == '__main__':
    main()

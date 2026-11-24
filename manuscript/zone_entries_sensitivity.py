"""The comparisons again, with every flight that met the goal but crossed into the zone between two checks counted as failed.

Exploratory, written after the results were read, for a referee's question. zone_entries_onboard_logs.py found, in
ArduPilot's onboard logs, flights that the once-a-second check scored as clear although the vehicle was inside an active
zone between two checks, and most of them met the goal. The protocol's outcome is the judge's, which checks once a
second. This script applies a stricter rule than the protocol's: it counts each such flight as failed and recomputes the
comparisons, first for a crossing of any depth and then only for crossings deeper than T, the largest difference
between the judge's depth and the log's at a check that stopped a flight (found as zone_entries_onboard_logs.py finds
it).

    python3 -I zone_entries_sensitivity.py CODE_ROOT STUDY2_RUNS EXTRA_SAVED TAG ONBOARD_JSONL

CODE_ROOT is the paper3 folder of the code the analyses ran (it holds protocol/analysis3.py, protocol/contract3.py and
protocol/seeds-3.json); STUDY2_RUNS holds Study 2's run roots and scored-20261120-S-analysis/analysis.json; EXTRA_SAVED
holds the additions' saved folders and their analysis output analysis-TAG/analysis-e.json; ONBOARD_JSONL is zone_entries_onboard_logs.py's output.

The outcome, the arrays and the draws are the analyses' own. Study 2's nine intervals come from analysis3.primary_pass
with Study 2's seed and number of resamples, on arms A to D; E - B and C - E from analysis3.bootstrap on arms A, B, C and E
with each task's generator seeded [BOOT_SEED, 0, task index], as analysis_e.py makes them. The draws depend only on the
arrays' shape, so the recomputed intervals differ from the published ones only through the flights counted as failed.
Before changing any flight the script recomputes every interval from the unchanged records and stops unless each one
equals the published value to the last digit. Reads the records and writes nothing.
"""
import json
import sys
from pathlib import Path

import numpy as np

STUDY2 = 'scored-20261120-S-{task}'


def classes(row):
    """The reading: the interval's class and direction, and for a pooled primary also the answer of analysis3.answer,
    which calls a pooled result 'not settled' (the paper's 'mixed') when the tasks' estimates differ in sign."""
    c = row['classification']
    out = c['class'] if c['class'] == 'task_dependent' else f"{c['class']} {c.get('direction') or ''}".strip()
    if 'answer' in row:
        out += f"; answer {row['answer']['status']}, task signs {''.join(row['answer']['signs'].values())}"
    return out


def main(code_root, runs, saved, tag, onboard):
    sys.path.insert(0, str(code_root))
    from protocol import analysis3 as A3
    from protocol import contract3 as C3
    seeds = json.loads((code_root / 'protocol' / 'seeds-3.json').read_text())

    rows_log = [json.loads(line) for line in onboard.read_text().splitlines()]
    T = max(abs(r['judge_gap_m'] - r['log_gap_last_check_m']) for r in rows_log if r['entered'])
    crossings = {depth: {(r['source'], r['phase'], r['flight']) for r in rows_log
                         if r['source'] in ('s2', 'ex') and not r['entered'] and r['goal_met'] and r['log_gap_m'] < -depth}
                 for depth in (0.0, T)}
    crossed = set()

    def load(task, flip):
        cases = C3.evaluation_cases(seeds, task)
        ids = [c.episode_id for c in cases]
        bands = [b for b in C3.BANDS for _ in seeds['threat_evaluation'][task][b]]
        s2 = runs / STUDY2.format(task=task)
        ex = saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'
        arms = ('A', 'B', 'C', 'D', 'E')
        y = np.zeros((5, len(seeds['blocks'][task]), len(ids)))
        flipped = {a: 0 for a in arms}
        for j in range(y.shape[1]):
            rows = json.loads((s2 / f'learn3-{task}-b{j}' / 'arms.json').read_text())['arms']
            rows['E'] = json.loads((ex / f'learnE-{task}-b{j}' / 'arms.json').read_text())['arms']['E']
            for i, arm in enumerate(arms):
                if not rows[arm]['adopted']:
                    continue
                name = C3.phase_name('threat3', task, j, rows[arm]['source_sha256'])
                source, here = ('s2', s2) if (s2 / name).is_dir() else ('ex', ex)
                if not (here / 'logs' / f'{name}.done').exists():
                    raise SystemExit(f'{here / name} is not a finished phase')
                for k, cid in enumerate(ids):
                    met = json.loads((here / name / 'flights' / cid / 'outcome.json').read_text())['goal_met']
                    if flip and met and (source, name, cid) in crossed:
                        met = False
                        flipped[arm] += 1
                    y[i, j, k] = bool(met)
        return y, bands, flipped

    def study2_pass(flip):
        data, flipped = {}, {}
        for task in C3.TASKS:
            y, bands, flipped[task] = load(task, flip)
            data[task] = {'y': y[:4], 'bands': bands}
        return A3.primary_pass(data, C3.BOOT_SEED, C3.BOOT_N), flipped

    def extra_pass(flip):
        out, points, draws = {'tasks': {}, 'pooled': {}}, {}, {}
        steps = {'E-B': (3, 1), 'C-E': (2, 3)}
        for task in C3.TASKS:
            y, bands, _ = load(task, flip)
            y = y[[0, 1, 2, 4]]                               # arms A, B, C and E, as analysis_e.py orders them
            rng = np.random.default_rng([C3.BOOT_SEED, 0, C3.TASKS.index(task)])
            draws[task] = A3.bootstrap(y, bands, rng, C3.BOOT_N)
            points[task] = y.mean(axis=(1, 2))
            out['tasks'][task] = {k: A3.estimate_record(points[task][a] - points[task][b],
                                                        draws[task][a] - draws[task][b]) for k, (a, b) in steps.items()}
        pp = np.mean([points[t] for t in C3.TASKS], axis=0)
        pd = np.mean([draws[t] for t in C3.TASKS], axis=0)
        for k, (a, b) in steps.items():
            out['pooled'][k] = A3.estimate_record(pp[a] - pp[b], pd[a] - pd[b])
        return out

    same = lambda r, s: (r['estimate'], r['ci95'], r['ci90']) == (s['estimate'], s['ci95'], s['ci90'])
    published = json.loads((runs / 'scored-20261120-S-analysis' / 'analysis.json').read_text())
    published_e = json.loads((saved / f'analysis-{tag}' / 'analysis-e.json').read_text())
    before, _ = study2_pass(False)
    before_e = extra_pass(False)
    bad = [k for k, row in before['intervals'].items()
           if not same(row, published['primary'].get(k) or published['secondary_intervals'][k])]
    bad += [f'{t} {k}' for t in C3.TASKS for k, row in before['tasks'][t]['steps'].items()
            if k in ('B-A', 'C-B', 'D-C') and not same(row, published['tasks'][t]['all_band_steps'][k])]
    bad += [f'{t} {k}' for t in C3.TASKS for k in ('E-B', 'C-E')
            if not same(before_e['tasks'][t][k], published_e['tasks'][t]['steps'][k])]
    bad += [f'pooled {k}' for k in ('E-B', 'C-E') if not same(before_e['pooled'][k], published_e['pooled'][k])]
    if bad:
        raise SystemExit('the unchanged records do not give the published intervals: ' + ', '.join(bad))
    print('Unchanged records: every interval equals the published one to the last digit.')

    for depth, label in ((0.0, 'a crossing of any depth'), (T, f'a crossing deeper than T = {T:.4f} m')):
        crossed.clear()
        crossed.update(crossings[depth])
        after, flipped = study2_pass(True)
        after_e = extra_pass(True)
        print(f'Counting as failed every flight that met the goal with {label} between checks')
        print('  Flights counted as failed: '
              + '; '.join(f'{t} ' + ', '.join(f'{a} {n}' for a, n in flipped[t].items()) for t in C3.TASKS))
        print('  Comparison: estimate, 95% interval and 90% interval before -> after; reading before -> after')
        rows = [(k, before['intervals'][k], after['intervals'][k]) for k in before['intervals']]
        rows += [(f'{t}:{k}', before['tasks'][t]['steps'][k], after['tasks'][t]['steps'][k])
                 for t in C3.TASKS for k in ('B-A', 'C-B', 'D-C')]
        rows += [(f'pooled:{k}', before_e['pooled'][k], after_e['pooled'][k]) for k in ('E-B', 'C-E')]
        rows += [(f'{t}:{k}', before_e['tasks'][t][k], after_e['tasks'][t][k]) for t in C3.TASKS for k in ('E-B', 'C-E')]
        changed = 0
        for name, b, a in rows:
            f = lambda r: (f"{r['estimate']:+.3f} [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}] "
                           f"[{r['ci90'][0]:+.3f}, {r['ci90'][1]:+.3f}]")
            mark = '' if classes(b) == classes(a) else '   <- reading changed'
            changed += bool(mark)
            print(f'    {name}: {f(b)} -> {f(a)}; {classes(b)} -> {classes(a)}{mark}')
        print(f'  Readings changed: {changed} of {len(rows)}')


if __name__ == '__main__':
    a = sys.argv[1:]
    main(Path(a[0]), Path(a[1]), Path(a[2]), a[3], Path(a[4]))

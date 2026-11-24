"""Exploratory totals for Table S4e of the supplement: D - A and C - A over all 24 unseen zone flights,
for each task and pooled over the three tasks with equal weight; and the three primary comparisons with their intervals
widened to 98.3% each by the Bonferroni adjustment for three comparisons (Section 5.3).

    python3 -I total_gain_all_flights.py <records folder> <seeds-3.json> [<analysis.json>]

<records folder> is where study2-records.zip was unzipped; it holds runs/. <seeds-3.json> is the frozen seed book
(paper3/protocol/seeds-3.json at the freeze, SHA-256 1d39a62c...). The protocol names neither total, so both are
exploratory and carry no reading.

The resampling is the analysis's own: for each task a generator seeded [20261112, 0, task index] draws 10,000
resamples of the 40 blocks and of the 8 flights in each band, and the first set of draws, over all three bands, is
the one behind the pooled primary intervals. The reader and the resampling follow Codex's independent program
(codex_interval_check_20261122.py at commit 3f878edf, deposited with the code in study2/reproduction/
codex-check-20261122/), which matched all nine named intervals. Given analysis.json, the script first checks
that it reproduces the three primary intervals and each task's D - A over all flights to 1e-9, and stops if it does
not. Reads the records and writes nothing."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'


def read_cells(runs, task, book):
    """Outcome table [block, flight, arm] with 1 where the arm adopted a procedure that met the goal."""
    root = runs / f'scored-20261120-S-{task}'
    flights = [(band, seed) for band in BANDS for seed in book[task][band]]
    assert len(set(flights)) == 24
    table = np.zeros((40, 24, 4), dtype=np.int8)
    for block in range(40):
        arms = json.loads((root / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']
        assert set(arms) == set('ABCD')
        done = {}
        for index, label in enumerate('ABCD'):
            source = arms[label]['source_sha256']
            assert bool(source) == arms[label]['adopted']
            if not source:
                continue
            if source not in done:
                phase = root / f'threat3-{task}-b{block}-{source}' / 'flights'
                done[source] = [int(json.loads((phase / f'threat-{band}-{seed}' / 'outcome.json').read_text())['goal_met'])
                                for band, seed in flights]
            table[block, :, index] = done[source]
    return table


def resample(table, rng):
    count = 10_000
    blocks = rng.integers(40, size=(count, 40))
    cols = np.concatenate([8 * b + rng.integers(8, size=(count, 8)) for b in range(3)], axis=1)
    rates = np.empty((count, 4))
    for start in range(0, count, 100):
        part = slice(start, start + 100)
        rates[part] = table[blocks[part, :, None], cols[part, None, :]].mean(axis=(1, 2))
    return rates


def interval(point, draws):
    lo, a, b, hi = np.percentile(draws, [2.5, 5, 95, 97.5])
    return {'estimate': float(point), 'ci95': [float(lo), float(hi)], 'ci90': [float(a), float(b)]}


def main(records, seeds, analysis=None):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    runs = records / 'runs'
    means, draws, out = [], [], {}
    for index, task in enumerate(TASKS):
        table = read_cells(runs, task, book)
        m = table.mean(axis=(0, 1))
        d = resample(table, np.random.default_rng([20261112, 0, index]))
        means.append(m)
        draws.append(d)
        out[f'{task} D-A all flights'] = interval(m[3] - m[0], d[:, 3] - d[:, 0])
        out[f'{task} C-A all flights'] = interval(m[2] - m[0], d[:, 2] - d[:, 0])
    m, d = np.mean(means, axis=0), np.mean(draws, axis=0)
    check = {name: interval(m[a] - m[b], d[:, a] - d[:, b]) for name, a, b in (('C-B', 2, 1), ('B-A', 1, 0), ('D-C', 3, 2))}
    out['pooled D-A all flights'] = interval(m[3] - m[0], d[:, 3] - d[:, 0])
    out['pooled C-A all flights'] = interval(m[2] - m[0], d[:, 2] - d[:, 0])
    for name, r in check.items():
        a, b = {'C-B': (2, 1), 'B-A': (1, 0), 'D-C': (3, 2)}[name]
        lo, hi = np.percentile(d[:, a] - d[:, b], [100 * 0.05 / 6, 100 - 100 * 0.05 / 6])
        out[f'pooled {name} at 98.3%'] = {'estimate': r['estimate'], 'ci95': [float(lo), float(hi)], 'ci90': r['ci90'], 'level': '98.3%'}
    if analysis:
        frozen = json.loads(analysis.read_text())
        pairs = [(check[k], frozen['pooled_ladder_steps'][k]) for k in check]
        pairs += [(out[f'{t} D-A all flights'], frozen['tasks'][t]['all_band_steps']['D-A']) for t in TASKS]
        for mine, theirs in pairs:
            for key in ('ci95', 'ci90'):
                assert max(abs(x - y) for x, y in zip(mine[key], theirs[key])) < 1e-9, (mine, theirs)
            assert abs(mine['estimate'] - theirs['estimate']) < 1e-9
        print('reproduces the three primary intervals and each task\'s D - A over all flights: yes')
    for name, r in out.items():
        print(f"{name:26s} {r['estimate']:+.3f}  {r.get('level', '95%')} {r['ci95'][0]:+.3f} to {r['ci95'][1]:+.3f}"
              f"  90% {r['ci90'][0]:+.3f} to {r['ci90'][1]:+.3f}")


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)

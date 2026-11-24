"""Independently read the scored extract and reproduce the nine named intervals.

Run this file with the extract directory as its sole argument, from the frozen
worktree. Uses NumPy and the standard library. Prints JSON to standard output.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def read_cells(extract, task, book, checksums):
    def load(path):
        raw = path.read_bytes()
        name = path.relative_to(extract / 'data').as_posix()
        assert hashlib.sha256(raw).hexdigest() == checksums[name], name
        return json.loads(raw)

    root = extract / 'data' / 'runs' / f'scored-20261120-S-{task}'
    bands = ('close', 'middle', 'wide')
    scenarios = [(band, seed) for band in bands for seed in book[task][band]]
    assert len(set(scenarios)) == 24
    table = np.zeros((40, 24, 4), dtype=np.int8)
    for block in range(40):
        arms = load(root / f'learn3-{task}-b{block}' / 'arms.json')['arms']
        assert set(arms) == set('ABCD')
        cache = {}
        for index, label in enumerate('ABCD'):
            source = arms[label]['source_sha256']
            assert bool(source) == arms[label]['adopted']
            if not source:
                continue
            if source not in cache:
                phase = root / f'threat3-{task}-b{block}-{source}' / 'flights'
                values = []
                for band, seed in scenarios:
                    outcome = load(phase / f'threat-{band}-{seed}' / 'outcome.json')
                    assert type(outcome['goal_met']) is bool
                    values.append(int(outcome['goal_met']))
                cache[source] = values
            table[block, :, index] = cache[source]
    return table


def bootstrap(table, bands, rng):
    count = 10_000
    blocks = rng.integers(40, size=(count, 40))
    cols = np.concatenate(
        [8 * b + rng.integers(8, size=(count, 8)) for b in bands], axis=1
    )
    rates = np.empty((count, 4))
    for start in range(0, count, 100):
        batch = slice(start, start + 100)
        rates[batch] = table[blocks[batch, :, None], cols[batch, None, :]].mean(axis=(1, 2))
    return rates


def summarise(point, draws):
    lo, a, b, hi = np.percentile(draws, [2.5, 5, 95, 97.5])
    equivalent = a > -0.2 and b < 0.2
    if lo > 0.2 or hi < -0.2:
        label = 'useful_gain' if lo > 0.2 else 'useful_loss'
    elif lo > 0 or hi < 0:
        label = 'different_and_equivalent' if equivalent else 'different_not_equivalent'
    else:
        label = 'equivalent_not_different' if equivalent else 'unresolved'
    return dict(estimate=point, ci95=[lo, hi], ci90=[a, b], classification=label)


def main(extract):
    sums = {}
    for line in (extract / 'SHA256SUMS.extract').read_text().splitlines():
        digest, name = line.split('  ', 1)
        sums[name] = digest
    seed_path = Path(__file__).resolve().parents[1] / 'protocol/seeds-3.json'
    assert hashlib.sha256(seed_path.read_bytes()).hexdigest() == '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'
    book = json.loads(seed_path.read_bytes())['threat_evaluation']
    result, task_means, task_draws = {}, [], []
    for index, task in enumerate(('reach', 'reach3d', 'land')):
        table = read_cells(extract, task, book, sums)
        rng = np.random.default_rng([20261112, 0, index])
        task_means.append(table.mean(axis=(0, 1)))
        task_draws.append(bootstrap(table, [0, 1, 2], rng))
        for bands in ([0], [1], [2], [1, 2]):
            draw = bootstrap(table, bands, rng)
            if bands in ([0], [1, 2]):
                columns = slice(0, 8) if bands == [0] else slice(8, 24)
                cells = table[:, columns]
                point = (cells[..., 3] - cells[..., 0]).mean()
                name = 'close' if bands == [0] else 'distant'
                result[f'{task} {name} D-A'] = summarise(point, draw[:, 3] - draw[:, 0])
    means, draws = np.mean(task_means, axis=0), np.mean(task_draws, axis=0)
    for step, after, before in [('C-B', 2, 1), ('B-A', 1, 0), ('D-C', 3, 2)]:
        result[step] = summarise(means[after] - means[before], draws[:, after] - draws[:, before])
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))

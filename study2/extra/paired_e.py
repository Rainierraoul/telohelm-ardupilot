"""Arm C's and arm E's adopted procedures compared on the same blocks, and C - E split into its parts. Exploratory and
outside PROTOCOL-EXTRA.md, which names neither: written after the comparisons and rates were read, because the rates
among flights flown (extra/rates_e.py) compare different sets of blocks.

    python3 -I extra/paired_e.py STUDY2_RUNS EXTRA_SAVED TAG SEEDS_3_JSON

A block is paired when arm C adopted one of its own repairs (rC1 or rC2) and arm E one of its own fresh candidates (rE1
or rE2). In a paired block both procedures flew the same 24 unseen zone flights, so goals met and zone entries can be
compared flight for flight. Blocks where the two arms adopted the same procedure (the first candidate, or a reply arm E
shared with arm C) add nothing to C - E.

C - E over all 120 blocks is then split exactly into three parts, each a count of flights over the 2,880 flights:
  paired:  goals met by C's procedure less those met by E's, in the paired blocks;
  C only:  goals met by C's procedure in blocks where E adopted nothing;
  E only:  less the goals met by E's procedure in blocks where C adopted nothing.
The three add up to C - E, which the script checks against the pooled estimate (the pooled value is the mean of the
three tasks, and each task has 40 blocks of 24 flights, so it equals the mean over all 2,880).

Intervals are 95% percentile intervals from 10,000 resamples drawn as the analysis draws them (blocks with replacement
within each task, the 8 flights of each band with replacement, the same draw for every arm), from a generator seeded
[20261123, 3, task index], a seed chosen for this script and used for nothing else. Reads the records and writes nothing.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'
COUNT = 10_000
OWN = {'C': ('rC1', 'rC2'), 'E': ('rE1', 'rE2')}


def outcomes(phase, flights):
    got = [json.loads((phase / 'flights' / f'threat-{band}-{seed}' / 'outcome.json').read_text())
           for band, seed in flights]
    return np.array([int(o['goal_met']) for o in got]), np.array([int(o['end_reason'] == 'entered_threat') for o in got])


def read_task(runs, saved, tag, task, book):
    s2 = runs / f'scored-20261120-S-{task}'
    ex = saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'
    flights = [(band, seed) for band in BANDS for seed in book[task][band]]
    kind = np.zeros(40, dtype='<U6')                 # paired, C, E, same, none
    met = np.zeros((40, 24, 2), dtype=np.int8)       # [..., 0] arm C, [..., 1] arm E
    entered = np.zeros((40, 24, 2), dtype=np.int8)
    for block in range(40):
        rows = {'C': json.loads((s2 / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']['C'],
                'E': json.loads((ex / f'learnE-{task}-b{block}' / 'arms.json').read_text())['arms']['E']}
        for k, arm in enumerate('CE'):
            r = rows[arm]
            if r['adopted']:
                name = f'threat3-{task}-b{block}-{r["source_sha256"]}'
                phase = s2 / name if (s2 / name).is_dir() else ex / name
                met[block, :, k], entered[block, :, k] = outcomes(phase, flights)
        c, e = rows['C'], rows['E']
        if c['adopted'] and e['adopted'] and c['source_sha256'] == e['source_sha256']:
            kind[block] = 'same'
        elif c['adopted'] and e['adopted']:
            assert c['candidate_id'] in OWN['C'] and e['candidate_id'] in OWN['E'], (task, block)
            kind[block] = 'paired'
        elif c['adopted']:
            kind[block] = 'C'
        elif e['adopted']:
            kind[block] = 'E'
        else:
            kind[block] = 'none'
    return kind, met, entered


def sums(kind, met, entered, bl, cols):
    """Totals over the drawn blocks and flights: paired flights, goals met and entries by each arm on them, and the
    three parts of C - E as counts."""
    k = kind[bl]                                                  # (draws, 40)
    m = met[bl[:, :, None], cols[:, None, :]]                     # (draws, 40, 24, 2)
    e = entered[bl[:, :, None], cols[:, None, :]]
    pm = (k == 'paired')[:, :, None, None]
    return {'paired_flights': (k == 'paired').sum(axis=1) * 24,
            'met_C': (m[..., 0] * pm[..., 0]).sum(axis=(1, 2)), 'met_E': (m[..., 1] * pm[..., 0]).sum(axis=(1, 2)),
            'ent_C': (e[..., 0] * pm[..., 0]).sum(axis=(1, 2)), 'ent_E': (e[..., 1] * pm[..., 0]).sum(axis=(1, 2)),
            'part_C_only': (m[..., 0] * (k == 'C')[:, :, None]).sum(axis=(1, 2)),
            'part_E_only': -(m[..., 1] * (k == 'E')[:, :, None]).sum(axis=(1, 2))}


def main(runs, saved, tag, seeds):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    data = [read_task(runs, saved, tag, t, book) for t in TASKS]
    point = {}
    for kind, met, entered in data:
        s = sums(kind, met, entered, np.arange(40)[None, :], np.arange(24)[None, :])
        for key, v in s.items():
            point[key] = point.get(key, 0) + int(v[0])
    draws = {}
    for index, (kind, met, entered) in enumerate(data):
        rng = np.random.default_rng([20261123, 3, index])
        blocks = rng.integers(40, size=(COUNT, 40))
        cols = np.concatenate([8 * b + rng.integers(8, size=(COUNT, 8)) for b in range(3)], axis=1)
        for start in range(0, COUNT, 500):
            part = slice(start, start + 500)
            s = sums(kind, met, entered, blocks[part], cols[part])
            for key, v in s.items():
                draws.setdefault(key, np.zeros(COUNT))[part] += v

    def ci(x):
        lo, hi = np.percentile(x, [2.5, 97.5])
        return f'{lo:+.3f} to {hi:+.3f}'

    total = 3 * 40 * 24
    counts = {t: {k: int((d[0] == k).sum()) for k in ('paired', 'same', 'C', 'E', 'none')} for t, d in zip(TASKS, data)}
    print('Blocks by what arms C and E adopted:', json.dumps(counts))
    n = point['paired_flights']
    print(f'Paired blocks: {n // 24}, {n} flights')
    print(f'  goals met: arm C {point["met_C"]} ({point["met_C"] / n:.3f}), arm E {point["met_E"]} ({point["met_E"] / n:.3f}); '
          f'C minus E {(point["met_C"] - point["met_E"]) / n:+.3f} ({ci((draws["met_C"] - draws["met_E"]) / draws["paired_flights"])})')
    print(f'  zone entries: arm C {point["ent_C"]} ({point["ent_C"] / n:.3f}), arm E {point["ent_E"]} ({point["ent_E"] / n:.3f}); '
          f'E minus C {(point["ent_E"] - point["ent_C"]) / n:+.3f} ({ci((draws["ent_E"] - draws["ent_C"]) / draws["paired_flights"])})')
    parts = {'paired': (point['met_C'] - point['met_E']) / total, 'C only': point['part_C_only'] / total,
             'E only': point['part_E_only'] / total}
    part_draws = {'paired': (draws['met_C'] - draws['met_E']) / total, 'C only': draws['part_C_only'] / total,
                  'E only': draws['part_E_only'] / total}
    print('C - E over all 2,880 flights, split into its parts (share of all flights):')
    for key in parts:
        print(f'  {key}: {parts[key]:+.4f} ({ci(part_draws[key])})')
    whole = sum(parts.values())
    print(f'  sum: {whole:+.4f}')
    return whole


if __name__ == '__main__':
    got = main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
    if len(sys.argv) > 5:
        want = float(sys.argv[5])
        assert abs(got - want) < 5e-5, f'the parts add to {got}, not to the pooled C - E {want}'
        print(f'Check: the parts add up to the pooled C - E, {want:+.4f}.')

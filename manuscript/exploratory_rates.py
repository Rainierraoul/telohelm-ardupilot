"""Exploratory rates for the paper's Sections 5.2 to 5.5 and Tables S5b, S7b and S7c: for each arm, the share of its adopted
procedures' unseen zone flights that met the goal and that entered the zone, and for arms B and C the share of
attempts at each position that passed the zone test, each with a 95% bootstrap interval. It also gives zone entries
over all flights an arm was scored on, differences between arms in the share of flights flown that entered the zone,
and how the entries and goals met spread over the adopted procedures.

    python3 -I exploratory_rates.py <records folder> <seeds-3.json>

<records folder> is where study2-records.zip was unzipped; it holds runs/. <seeds-3.json> is the frozen seed book
(paper3/protocol/seeds-3.json at the freeze, SHA-256 1d39a62c...). The protocol names none of these rates, so all are
exploratory and carry no reading.

The rates among flights flown pool the three tasks' flights. Each resample draws the 40 blocks of each task with
replacement and, for rates among flights, the 8 flights of each band with replacement, the same draw for every arm, as
the analysis does. The generator is seeded [20261122, 7, task index], a seed chosen for this script and used for
nothing else. A pass rate at a position is the number of blocks that adopted at that position over the number that
reached it; a candidate refused at the format check counts as a failed attempt, as in Table S5a. Reads the records and
writes nothing."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
ARMS = 'ABCD'
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'
POSITION = {'c0': 1, 'c1': 1, 'f1': 2, 'rC1': 2, 'rD1': 2, 'f2': 3, 'rC2': 3, 'rD2': 3}
COUNT = 10_000


def read_task(runs, task, book):
    """flown[block, arm], met and entered[block, flight, arm] (0 where nothing was adopted), position[block, arm]
    (1 to 3, or 0 for no adoption)."""
    root = runs / f'scored-20261120-S-{task}'
    flights = [(band, seed) for band in BANDS for seed in book[task][band]]
    assert len(set(flights)) == 24
    flown = np.zeros((40, 4), dtype=bool)
    met = np.zeros((40, 24, 4), dtype=np.int8)
    entered = np.zeros((40, 24, 4), dtype=np.int8)
    position = np.zeros((40, 4), dtype=np.int8)
    for block in range(40):
        arms = json.loads((root / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']
        assert set(arms) == set(ARMS)
        done = {}
        for index, label in enumerate(ARMS):
            arm = arms[label]
            source = arm['source_sha256']
            assert bool(source) == arm['adopted'] == (arm['candidate_id'] is not None)
            if not source:
                continue
            position[block, index] = POSITION[arm['candidate_id']]
            if source not in done:
                phase = root / f'threat3-{task}-b{block}-{source}' / 'flights'
                outcomes = [json.loads((phase / f'threat-{band}-{seed}' / 'outcome.json').read_text())
                            for band, seed in flights]
                done[source] = ([int(o['goal_met']) for o in outcomes],
                                [int(o['end_reason'] == 'entered_threat') for o in outcomes])
            flown[block, index] = True
            met[block, :, index], entered[block, :, index] = done[source]
    return flown, met, entered, position


def pass_counts(position):
    """For each arm and position 1 to 3: blocks that reached it and blocks that adopted at it."""
    reached = np.stack([(position == 0) | (position >= k) for k in (1, 2, 3)], axis=-1).sum(axis=-3)
    passed = np.stack([position == k for k in (1, 2, 3)], axis=-1).sum(axis=-3)
    return reached, passed


def ends(draws):
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi)


def main(records, seeds):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    runs = records / 'runs'
    data = [read_task(runs, task, book) for task in TASKS]

    # point estimates
    flown_n = sum(f.sum(axis=0) * 24 for f, _, _, _ in data)
    met_n = sum(m.sum(axis=(0, 1)) for _, m, _, _ in data)
    entered_n = sum(e.sum(axis=(0, 1)) for _, _, e, _ in data)
    reached = sum(pass_counts(p)[0] for *_, p in data)
    passed = sum(pass_counts(p)[1] for *_, p in data)

    # resamples
    met_d = np.zeros((COUNT, 4)); entered_d = np.zeros((COUNT, 4)); flown_d = np.zeros((COUNT, 4))
    reached_d = np.zeros((COUNT, 4, 3)); passed_d = np.zeros((COUNT, 4, 3))
    for index, (flown, met, entered, position) in enumerate(data):
        rng = np.random.default_rng([20261122, 7, index])
        blocks = rng.integers(40, size=(COUNT, 40))
        cols = np.concatenate([8 * b + rng.integers(8, size=(COUNT, 8)) for b in range(3)], axis=1)
        for start in range(0, COUNT, 200):
            part = slice(start, start + 200)
            bl = blocks[part]
            met_d[part] += met[bl[:, :, None], cols[part, None, :]].sum(axis=(1, 2))
            entered_d[part] += entered[bl[:, :, None], cols[part, None, :]].sum(axis=(1, 2))
            flown_d[part] += flown[bl].sum(axis=1) * 24
            r, p = pass_counts(position[bl])
            reached_d[part] += r
            passed_d[part] += p

    print('Rates among the unseen zone flights flown by adopted procedures, three tasks pooled, with 95% intervals')
    for a, label in enumerate(ARMS):
        print(f'  arm {label}: flown {int(flown_n[a])}; met the goal {int(met_n[a])} '
              f'({met_n[a] / flown_n[a]:.3f}, {ends(met_d[:, a] / flown_d[:, a])[0]:.3f} to {ends(met_d[:, a] / flown_d[:, a])[1]:.3f}); '
              f'entered the zone {int(entered_n[a])} '
              f'({entered_n[a] / flown_n[a]:.3f}, {ends(entered_d[:, a] / flown_d[:, a])[0]:.3f} to {ends(entered_d[:, a] / flown_d[:, a])[1]:.3f})')
    print('Share of attempts at each position that passed the zone test (arms B, C, D) or the test without the zone (arm A)')
    for a, label in enumerate(ARMS):
        cells = []
        for k in range(3):
            if reached[a, k] == 0:
                cells.append(f'position {k + 1}: none reached')
                continue
            share = passed_d[:, a, k] / np.maximum(reached_d[:, a, k], 1)
            lo, hi = ends(share)
            cells.append(f'position {k + 1}: {int(passed[a, k])} of {int(reached[a, k])} '
                         f'({passed[a, k] / reached[a, k]:.3f}, {lo:.3f} to {hi:.3f})')
        print(f'  arm {label}: ' + '; '.join(cells))
    later = slice(1, 3)
    for a, label in ((1, 'B'), (2, 'C'), (3, 'D')):
        share = passed_d[:, a, later].sum(axis=1) / reached_d[:, a, later].sum(axis=1)
        lo, hi = ends(share)
        print(f'  arm {label}, second and third attempts together: {int(passed[a, later].sum())} of '
              f'{int(reached[a, later].sum())} ({passed[a, later].sum() / reached[a, later].sum():.3f}, {lo:.3f} to {hi:.3f})')

    # Added after the rates above were printed in the paper; computed from the same resamples, so none of them moves.
    attempted = 3 * 40 * 24
    print('Zone entries over all flights an arm was scored on, a block with no procedure counting as no entry')
    for a, label in enumerate(ARMS):
        lo, hi = ends(entered_d[:, a] / attempted)
        print(f'  arm {label}: {int(entered_n[a])} of {attempted} ({entered_n[a] / attempted:.3f}, {lo:.3f} to {hi:.3f})')
    print('Difference in the share of flights flown that entered the zone')
    for x, y in ((3, 2), (2, 1), (3, 1)):
        diff = entered_d[:, x] / flown_d[:, x] - entered_d[:, y] / flown_d[:, y]
        lo, hi = ends(diff)
        point = entered_n[x] / flown_n[x] - entered_n[y] / flown_n[y]
        print(f'  arm {ARMS[x]} minus arm {ARMS[y]}: {point:+.3f} ({lo:+.3f} to {hi:+.3f})')
    print('Spread over adopted procedures (one per arm and block) of zone entries and goals met on their 24 flights')
    for a, label in enumerate(ARMS):
        per_entries = np.concatenate([e[f[:, a], :, a].sum(axis=1) for f, _, e, _ in data])
        per_met = np.concatenate([m[f[:, a], :, a].sum(axis=1) for f, m, _, _ in data])
        n = len(per_entries)
        order = np.sort(per_entries)[::-1]
        half = int(np.searchsorted(np.cumsum(order), order.sum() / 2) + 1) if order.sum() else 0
        print(f'  arm {label}: {n} procedures; none entered: {int((per_entries == 0).sum())}; '
              f'1 or 2 entries: {int(((per_entries >= 1) & (per_entries <= 2)).sum())}; '
              f'3 or more: {int((per_entries >= 3).sum())}; most entries by one: {int(order[0]) if n else 0}; '
              f'half of all entries came from the worst {half}; '
              f'met all 24: {int((per_met == 24).sum())}; met 22 or more: {int((per_met >= 22).sum())}; '
              f'median met: {float(np.median(per_met)) if n else 0:.1f}')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))

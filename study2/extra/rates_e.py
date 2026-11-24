"""Descriptive rates for arm E beside Study 2's arms (PROTOCOL-EXTRA.md, section 5, 'also reported, with no test'):
adoption; for each arm the share of its adopted procedures' unseen zone flights that met the goal and that entered the
zone, with 95% bootstrap intervals; the share of attempts at each position that passed the zone test; zone entries over
all flights an arm was scored on; arm E's spread of entries over its procedures; and calls and list cost, each arm
counted as if it had run alone, as Online Resource 1, S9 counts Study 2's arms.

    python3 -I extra/rates_e.py STUDY2_RUNS EXTRA_SAVED TAG SEEDS_3_JSON

STUDY2_RUNS holds Study 2's run roots scored-20261120-S-<task>/; EXTRA_SAVED holds extra-TAG-<task>/runs/extra-TAG-<task>/.

The resampling is manuscript/exploratory_rates.py's, unchanged: the generator seeded [20261122, 7, task index], blocks
drawn with replacement within each task and the 8 flights of each band with replacement, the same draw for every arm.
The draws depend only on the generator and the array shapes, so arms A to D get the draws they had there, and the script
first checks that their rates and intervals come out as that script printed them for the paper (Online Resource 1, S5b
and S7). Reads the records and writes nothing."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
ARMS = 'ABCDE'
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'
POSITION = {'c0': 1, 'c1': 1, 'f1': 2, 'rC1': 2, 'rD1': 2, 'rE1': 2, 'f2': 3, 'rC2': 3, 'rD2': 3, 'rE2': 3}
COUNT = 10_000
# What manuscript/exploratory_rates.py prints for Study 2 from the same records (run 23 November 2026 on the records
# behind Online Resource 1, S7): rate among flights flown, then the 95% interval's ends, to three places.
STUDY2_PRINTED = {
    'met_among_flown': {'A': (0.446, 0.391, 0.499), 'B': (0.907, 0.844, 0.960), 'C': (0.911, 0.874, 0.943),
                        'D': (0.892, 0.848, 0.931)},
    'entered_among_flown': {'A': (0.290, 0.225, 0.358), 'B': (0.059, 0.020, 0.111), 'C': (0.064, 0.035, 0.099),
                            'D': (0.092, 0.056, 0.135)},
}


def study2_root(runs, task):
    return runs / f'scored-20261120-S-{task}'


def extra_root(saved, tag, task):
    return saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'


def outcomes(phase, flights):
    got = [json.loads((phase / 'flights' / f'threat-{band}-{seed}' / 'outcome.json').read_text())
           for band, seed in flights]
    return [int(o['goal_met']) for o in got], [int(o['end_reason'] == 'entered_threat') for o in got]


def costs(usage: Path) -> dict:
    out = {}
    if usage.exists():
        for line in usage.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[r['call_id']] = r.get('list_cost_usd') or 0.0
    return out


def read_task(runs, saved, tag, task, book):
    s2, ex = study2_root(runs, task), extra_root(saved, tag, task)
    flights = [(band, seed) for band in BANDS for seed in book[task][band]]
    assert len(set(flights)) == 24
    n = len(ARMS)
    flown = np.zeros((40, n), dtype=bool)
    met = np.zeros((40, 24, n), dtype=np.int8)
    entered = np.zeros((40, 24, n), dtype=np.int8)
    position = np.zeros((40, n), dtype=np.int8)
    cost = np.zeros(n)
    calls = np.zeros(n, dtype=int)
    for block in range(40):
        learn2 = s2 / f'learn3-{task}-b{block}'
        arms = json.loads((learn2 / 'arms.json').read_text())['arms']
        arms['E'] = json.loads((ex / f'learnE-{task}-b{block}' / 'arms.json').read_text())['arms']['E']
        price = {**costs(learn2 / 'usage.jsonl'), **costs(ex / f'learnE-{task}-b{block}' / 'usage.jsonl')}
        done = {}
        for index, label in enumerate(ARMS):
            arm = arms[label]
            ids = arm['call_ids']
            missing = [c for c in ids if c not in price]
            if missing:
                raise SystemExit(f'{task} block {block} arm {label}: no usage row for {missing[:2]}')
            cost[index] += sum(price[c] for c in ids)
            calls[index] += len(ids)
            source = arm['source_sha256']
            assert bool(source) == arm['adopted'] == (arm['candidate_id'] is not None)
            if not source:
                continue
            position[block, index] = POSITION[arm['candidate_id']]
            if source not in done:
                name = f'threat3-{task}-b{block}-{source}'
                phase = s2 / name if (s2 / name).is_dir() else ex / name
                done[source] = outcomes(phase, flights)
            flown[block, index] = True
            met[block, :, index], entered[block, :, index] = done[source]
    return flown, met, entered, position, cost, calls


def pass_counts(position):
    reached = np.stack([(position == 0) | (position >= k) for k in (1, 2, 3)], axis=-1).sum(axis=-3)
    passed = np.stack([position == k for k in (1, 2, 3)], axis=-1).sum(axis=-3)
    return reached, passed


def ends(draws):
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi)


def main(runs, saved, tag, seeds):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    data = [read_task(runs, saved, tag, task, book) for task in TASKS]
    n = len(ARMS)
    flown_n = sum(d[0].sum(axis=0) * 24 for d in data)
    met_n = sum(d[1].sum(axis=(0, 1)) for d in data)
    entered_n = sum(d[2].sum(axis=(0, 1)) for d in data)
    reached = sum(pass_counts(d[3])[0] for d in data)
    passed = sum(pass_counts(d[3])[1] for d in data)
    met_d = np.zeros((COUNT, n)); entered_d = np.zeros((COUNT, n)); flown_d = np.zeros((COUNT, n))
    reached_d = np.zeros((COUNT, n, 3)); passed_d = np.zeros((COUNT, n, 3))
    for index, (flown, met, entered, position, _, _) in enumerate(data):
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

    def rate(num_d, a):
        return ends(num_d[:, a] / np.maximum(flown_d[:, a], 1))

    bad = []
    for key, num, num_d in (('met_among_flown', met_n, met_d), ('entered_among_flown', entered_n, entered_d)):
        for label, want in STUDY2_PRINTED[key].items():
            a = ARMS.index(label)
            got = (round(num[a] / flown_n[a], 3), *(round(x, 3) for x in rate(num_d, a)))
            if got != want:
                bad.append(f'{key} arm {label}: {got} against {want}')
    if bad:
        raise SystemExit("Study 2's printed rates did not come out the same, so nothing is reported: " + '; '.join(bad))
    print("Check: arms A to D's rates among flights flown and their intervals equal those Study 2's script prints.")

    print('Adoption, blocks of 120:', {ARMS[a]: int(sum(d[0][:, a].sum() for d in data)) for a in range(n)})
    print('Rates among the unseen zone flights flown by adopted procedures, three tasks pooled, with 95% intervals')
    for a, label in enumerate(ARMS):
        lo_m, hi_m = rate(met_d, a)
        lo_e, hi_e = rate(entered_d, a)
        print(f'  arm {label}: flown {int(flown_n[a])}; met the goal {int(met_n[a])} ({met_n[a] / flown_n[a]:.3f}, '
              f'{lo_m:.3f} to {hi_m:.3f}); entered the zone {int(entered_n[a])} ({entered_n[a] / flown_n[a]:.3f}, '
              f'{lo_e:.3f} to {hi_e:.3f})')
    print('Share of attempts at each position that passed the zone test')
    for a, label in enumerate(ARMS):
        cells = []
        for k in range(3):
            if reached[a, k] == 0:
                cells.append(f'position {k + 1}: none reached')
                continue
            lo, hi = ends(passed_d[:, a, k] / np.maximum(reached_d[:, a, k], 1))
            cells.append(f'position {k + 1}: {int(passed[a, k])} of {int(reached[a, k])} '
                         f'({passed[a, k] / reached[a, k]:.3f}, {lo:.3f} to {hi:.3f})')
        print(f'  arm {label}: ' + '; '.join(cells))
    later = slice(1, 3)
    for label in 'BCDE':
        a = ARMS.index(label)
        lo, hi = ends(passed_d[:, a, later].sum(axis=1) / reached_d[:, a, later].sum(axis=1))
        print(f'  arm {label}, second and third attempts together: {int(passed[a, later].sum())} of '
              f'{int(reached[a, later].sum())} ({passed[a, later].sum() / reached[a, later].sum():.3f}, {lo:.3f} to {hi:.3f})')
    attempted = 3 * 40 * 24
    print('Zone entries over all flights an arm was scored on, a block with no procedure counting as no entry')
    for a, label in enumerate(ARMS):
        lo, hi = ends(entered_d[:, a] / attempted)
        print(f'  arm {label}: {int(entered_n[a])} of {attempted} ({entered_n[a] / attempted:.3f}, {lo:.3f} to {hi:.3f})')
    print('Difference in the share of flights flown that entered the zone')
    for x, y in (('E', 'C'), ('E', 'B')):
        i, k = ARMS.index(x), ARMS.index(y)
        lo, hi = ends(entered_d[:, i] / flown_d[:, i] - entered_d[:, k] / flown_d[:, k])
        point = entered_n[i] / flown_n[i] - entered_n[k] / flown_n[k]
        print(f'  arm {x} minus arm {y}: {point:+.3f} ({lo:+.3f} to {hi:+.3f})')
    print('Spread over adopted procedures of zone entries and goals met on their 24 flights')
    for label in 'CE':
        a = ARMS.index(label)
        per_entries = np.concatenate([d[2][d[0][:, a], :, a].sum(axis=1) for d in data])
        per_met = np.concatenate([d[1][d[0][:, a], :, a].sum(axis=1) for d in data])
        order = np.sort(per_entries)[::-1]
        half = int(np.searchsorted(np.cumsum(order), order.sum() / 2) + 1) if order.sum() else 0
        print(f'  arm {label}: {len(per_entries)} procedures; none entered: {int((per_entries == 0).sum())}; '
              f'half of all entries came from the worst {half}; met all 24: {int((per_met == 24).sum())}; '
              f'median met: {float(np.median(per_met)):.1f}')
    print('Calls and list cost, each arm counted as if it had run alone')
    for a, label in enumerate(ARMS):
        c = sum(d[4][a] for d in data)
        k = int(sum(d[5][a] for d in data))
        adopted = int(sum(d[0][:, a].sum() for d in data))
        print(f'  arm {label}: {k} calls, US${c:.2f}; US${c / 120:.3f} a block; '
              f'US${c / adopted:.3f} a procedure' if adopted else f'  arm {label}: {k} calls, US${c:.2f}')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))

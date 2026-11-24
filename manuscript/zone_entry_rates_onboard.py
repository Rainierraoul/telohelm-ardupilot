"""Zone-entry rates of arms A to E, as the once-a-second check counted them and with the crossings the onboard logs add.

Exploratory, written after the results were read, for a referee's question. For each arm, the share of its adopted
procedures' unseen zone flights that entered the zone: first as the judge scored them (end_reason entered_threat), then
also counting a flight scored as clear whose onboard log shows the vehicle inside an active zone between two checks
(zone_entries_onboard_logs.py, log_gap_m below 0), and then counting only such crossings deeper than T, the largest
difference between the judge's depth and the log's at a check that stopped a flight (found from the same output as that
script finds it). Also the difference D - C in that share, which the paper reports.

    python3 -I zone_entry_rates_onboard.py STUDY2_RUNS EXTRA_SAVED TAG SEEDS_3_JSON ONBOARD_JSONL

Each 95% interval comes from 10,000 resamples drawn as exploratory_rates.py draws them: the 40 blocks of each task with
replacement and the 8 flights of each band with replacement, the same draw for every arm, the tasks' flights pooled. The
generator is seeded [20261123, 9, task index], a seed chosen for this script and used for nothing else. A procedure is
read from Study 2's runs when Study 2 flew it, as in the rates of Online Resource 1, S7 and S19. Reads the records and
writes nothing.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
ARMS = 'ABCDE'
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'
COUNT = 10_000


def main(runs, saved, tag, seeds, onboard):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    log, stop = {}, []
    for line in onboard.read_text().splitlines():
        r = json.loads(line)
        log[(r['source'], r['phase'], r['flight'])] = r['log_gap_m']
        if r['entered']:
            stop.append(abs(r['judge_gap_m'] - r['log_gap_last_check_m']))
    T = max(stop)          # the threshold of zone_entries_onboard_logs.py, found the same way
    deep = {a: [] for a in ARMS}
    data = []
    for task in TASKS:
        s2 = runs / f'scored-20261120-S-{task}'
        ex = saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'
        names = [f'threat-{band}-{seed}' for band in BANDS for seed in book[task][band]]
        flown = np.zeros((40, 5), dtype=bool)
        judged = np.zeros((40, 24, 5), dtype=np.int8)
        either = np.zeros((40, 24, 5), dtype=np.int8)
        beyond = np.zeros((40, 24, 5), dtype=np.int8)
        for block in range(40):
            arms = json.loads((s2 / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']
            arms['E'] = json.loads((ex / f'learnE-{task}-b{block}' / 'arms.json').read_text())['arms']['E']
            for i, a in enumerate(ARMS):
                if not arms[a]['adopted']:
                    continue
                flown[block, i] = True
                phase = f'threat3-{task}-b{block}-{arms[a]["source_sha256"]}'
                source, root = ('s2', s2) if (s2 / phase).is_dir() else ('ex', ex)
                for k, name in enumerate(names):
                    o = json.loads((root / phase / 'flights' / name / 'outcome.json').read_text())
                    hit = o['end_reason'] == 'entered_threat'
                    gap = log[(source, phase, name)]
                    judged[block, k, i] = hit
                    either[block, k, i] = hit or gap < 0
                    beyond[block, k, i] = hit or gap < -T
                    if not hit and gap < 0:
                        deep[a].append(-gap)
        data.append((flown, judged, either, beyond))

    def rates(which):
        n = sum(d[which].sum(axis=(0, 1)) for d in data)
        f = sum(d[0].sum(axis=0) * 24 for d in data)
        hits = np.zeros((COUNT, 5))
        flights = np.zeros((COUNT, 5))
        for index, d in enumerate(data):
            rng = np.random.default_rng([20261123, 9, index])
            bl = rng.integers(40, size=(COUNT, 40))
            cols = np.concatenate([rng.integers(8, size=(COUNT, 8)) + 8 * b for b in range(3)], axis=1)
            flights += d[0][bl].sum(axis=1) * 24
            hits += d[which][bl[:, :, None], cols[:, None, :]].sum(axis=(1, 2))
        return n, f, hits, flights

    ends = lambda x: np.percentile(x, [2.5, 97.5])
    print(f'Threshold T, the largest disagreement between the judge and the log at a stopping check: {T:.4f} m')
    for which, label in ((1, 'as the judge scored them'), (2, 'adding the crossings in the onboard logs'),
                         (3, 'adding the crossings in the onboard logs deeper than T')):
        n, f, hits, flights = rates(which)
        print(f'Zone entries {label}: share of flights flown (95% interval)')
        for i, a in enumerate(ARMS):
            lo, hi = ends(hits[:, i] / flights[:, i])
            print(f'  arm {a}: {int(n[i])} of {int(f[i])} ({n[i] / f[i]:.4f}, {lo:.4f} to {hi:.4f})')
        d, c = ARMS.index('D'), ARMS.index('C')
        lo, hi = ends(hits[:, d] / flights[:, d] - hits[:, c] / flights[:, c])
        print(f'  D - C: {n[d] / f[d] - n[c] / f[c]:+.4f} ({lo:+.4f} to {hi:+.4f})')
    print('Spread over procedures, as the judge scored them -> counting crossings deeper than T: procedures; '
          'procedures with no entry; fewest procedures that made half the entries; procedures with a crossing found only '
          'in the logs, and the most such crossings by one procedure')

    def half(counts):
        total, running = sum(counts), 0
        for k, v in enumerate(sorted(counts, reverse=True), 1):
            running += v
            if 2 * running >= total:
                return k
        return 0
    for i, a in enumerate(ARMS):
        pj = [int(d[1][b, :, i].sum()) for d in data for b in range(40) if d[0][b, i]]
        pb = [int(d[3][b, :, i].sum()) for d in data for b in range(40) if d[0][b, i]]
        added = [y - x for x, y in zip(pj, pb)]
        print(f'  arm {a}: {len(pj)}; no entry {sum(v == 0 for v in pj)} -> {sum(v == 0 for v in pb)}; half the entries '
              f'{half(pj)} -> {half(pb)}; with a crossing {sum(v > 0 for v in added)}, most by one {max(added)}')
    print('Crossings found only in the logs, per arm: number, and how many were deeper than 0.05 m and 0.10 m')
    for a in ARMS:
        x = deep[a]
        print(f'  arm {a}: {len(x)}; deeper than 0.05 m {sum(v > 0.05 for v in x)}, 0.10 m {sum(v > 0.10 for v in x)}')


if __name__ == '__main__':
    a = sys.argv[1:]
    main(Path(a[0]), Path(a[1]), a[2], Path(a[3]), Path(a[4]))

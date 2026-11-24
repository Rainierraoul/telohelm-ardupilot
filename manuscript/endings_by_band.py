"""How the unseen zone flights of each arm's adopted procedures ended, by task and band, for arms A to E.

Exploratory, written after the results were read, for a referee's question about why arm A's untested code failed. It
also gives arm E's success on each band for Table 2: the flights met over the 320 flights of the band (40 blocks of 8),
a block with no procedure counting as 8 failed flights.

    python3 -I endings_by_band.py STUDY2_RUNS EXTRA_SAVED TAG SEEDS_3_JSON

A procedure is read from Study 2's runs when Study 2 flew it, as in the rates of Online Resource 1, S7 and S19. Reads the
records and writes nothing.
"""
import collections
import hashlib
import json
import sys
from pathlib import Path

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'


def main(runs, saved, tag, seeds):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    print('Task, band, arm: flights flown; met the goal; entered the zone; ran out of time; other endings; success '
          '(met over the 320 flights of the band)')
    for task in TASKS:
        s2 = runs / f'scored-20261120-S-{task}'
        ex = saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'
        ends = {(a, b): collections.Counter() for a in 'ABCDE' for b in BANDS}
        for block in range(40):
            arms = json.loads((s2 / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']
            arms['E'] = json.loads((ex / f'learnE-{task}-b{block}' / 'arms.json').read_text())['arms']['E']
            for a in 'ABCDE':
                if not arms[a]['adopted']:
                    continue
                phase = f'threat3-{task}-b{block}-{arms[a]["source_sha256"]}'
                root = s2 if (s2 / phase).is_dir() else ex
                for band in BANDS:
                    for seed in book[task][band]:
                        o = json.loads((root / phase / 'flights' / f'threat-{band}-{seed}' / 'outcome.json').read_text())
                        ends[a, band]['met' if o['goal_met'] else o['end_reason']] += 1
        for band in BANDS:
            for a in 'ABCDE':
                c = ends[a, band]
                n = sum(c.values())
                other = {k: v for k, v in c.items() if k not in ('met', 'entered_threat', 'timed_out')}
                print(f'  {task} {band} {a}: {n}; met {c["met"]}; entered {c["entered_threat"]}; timed out '
                      f'{c["timed_out"]}; other {dict(sorted(other.items()))}; success {c["met"] / 320:.3f}')


if __name__ == '__main__':
    a = sys.argv[1:]
    main(Path(a[0]), Path(a[1]), a[2], Path(a[3]))

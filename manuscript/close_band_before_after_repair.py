"""The close-target flights of each first candidate and of the repair that replaced it, measured from the records.

Exploratory, written after the results were read, for a referee's question: the reading of the repairs' code
(manuscript/repair_changes/) says that repairs kept a smaller distance from the zone at the close layout. This measures
what the vehicle did instead of what the code says.

    python3 -I close_band_before_after_repair.py STUDY2_RUNS SEEDS_3_JSON

A pair is a block where arm A adopted the shared first candidate (c0) and arm C adopted one of its repairs (rC1 or rC2).
Both procedures flew the same 8 unseen zone flights with a close target (3 to 4 m beyond the zone's far edge). For each
procedure the script reads, from each flight's outcome.json, whether it met the goal, whether it entered the zone, and
closest_threat_m, the smallest gap between the true position and the zone's edge at the once-a-second checks. Reads the
records and writes nothing.
"""
import hashlib
import json
import statistics
import sys
from pathlib import Path

TASKS = ('reach', 'reach3d', 'land')
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'


def close_flights(root: Path, task: str, block: int, sha: str, seeds):
    out = []
    for seed in seeds:
        o = json.loads((root / f'threat3-{task}-b{block}-{sha}' / 'flights' / f'threat-close-{seed}' /
                        'outcome.json').read_text())
        out.append((o['goal_met'], o['end_reason'] == 'entered_threat', o['closest_threat_m'], o['end_reason']))
    return out


def main(runs: Path, seeds_path: Path):
    raw = seeds_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    before, after, pairs = [], [], 0
    per_pair = []
    for task in TASKS:
        root = runs / f'scored-20261120-S-{task}'
        for block in range(40):
            arms = json.loads((root / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']
            a, c = arms['A'], arms['C']
            if not (a['adopted'] and a['candidate_id'] == 'c0' and c['adopted'] and c['candidate_id'] in ('rC1', 'rC2')):
                continue
            pairs += 1
            b = close_flights(root, task, block, a['source_sha256'], book[task]['close'])
            r = close_flights(root, task, block, c['source_sha256'], book[task]['close'])
            before += b
            after += r
            clear_b = [x[2] for x in b if not x[1]]
            clear_r = [x[2] for x in r if not x[1]]
            if clear_b and clear_r:
                per_pair.append(statistics.median(clear_r) - statistics.median(clear_b))

    def describe(name, fl):
        clear = [x[2] for x in fl if not x[1]]
        ends = {}
        for x in fl:
            ends[x[3]] = ends.get(x[3], 0) + 1
        q = statistics.quantiles(clear, n=4)
        print(f'  {name}: {len(fl)} flights; met the goal {sum(x[0] for x in fl)}; entered the zone {sum(x[1] for x in fl)}; '
              f'flights that stayed clear {len(clear)}, smallest gap to the edge median {statistics.median(clear):.2f} m '
              f'(middle half {q[0]:.2f} to {q[2]:.2f} m); endings {dict(sorted(ends.items()))}')

    print(f'Blocks where arm A adopted the first candidate and arm C a repair: {pairs}; close-target flights, 8 each')
    describe('first candidates', before)
    describe('repairs', after)
    smaller = sum(d < 0 for d in per_pair)
    print(f'  pairs where both had clear flights: {len(per_pair)}; the repair came closer to the zone (median of its '
          f'clear flights) in {smaller}; median change {statistics.median(per_pair):+.2f} m')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))

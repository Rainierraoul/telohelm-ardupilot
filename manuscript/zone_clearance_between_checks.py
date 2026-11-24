"""How close the flights scored as clear of the zone came to it, at the once-a-second checks and between them.

Exploratory, written after the results were read, for a referee's question: the judge checks the zone on the true
position once a second, so a flight can cross the zone's edge between two checks and still be scored clear.

    python3 -I zone_clearance_between_checks.py STUDY2_RUNS EXTRA_SAVED TAG SEEDS_3_JSON

STUDY2_RUNS holds Study 2's run roots scored-20261120-S-<task>/; EXTRA_SAVED holds extra-TAG-<task>/runs/extra-TAG-<task>/
(arm E). For each arm A to E, every unseen zone flight flown by a procedure the arm adopted (24 a block; a procedure two
arms adopted counts for each, as in the rates of Online Resource 1, S7 and S19) is read from its outcome.json:

  - at the checks: closest_threat_m, the smallest gap between the true position and the zone's edge over the checks,
    which the judge itself recorded;
  - between the checks: the true position at each check (native_steps, north_m and east_m, which the judge records from
    the simulator's true state), joined by straight lines. For each pair of consecutive checks at which the zone was
    active, the smallest distance from that straight segment to the zone's centre, less the radius. A negative value
    means the straight path between the two checks passes inside the zone. The real path between checks curves a
    little, so this is an estimate.

The zone is active from its start step in event_starts; the first segment counted ends at the first check after it.
Reads the records and writes nothing.
"""
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'


def seg_gap(a, b, c, r):
    """Smallest distance from segment a-b to point c, less r (all in the horizontal plane)."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / L2))
    return math.hypot(ax + u * dx - cx, ay + u * dy - cy) - r


def flight(path: Path):
    o = json.loads(path.read_text())
    entered = o['end_reason'] == 'entered_threat'
    zones = [(e[3], e[4], e[5], o['event_starts'][str(i)]) for i, e in enumerate(o['events']) if e[0] == 'threat']
    pos = {0: (0.0, 0.0)}
    for s in o['native_steps']:
        pos[s['t']] = (s['north_m'], s['east_m'])
    between = math.inf
    for n, e, r, start in zones:
        for t in sorted(pos):
            if t - 1 in pos and t > start:
                between = min(between, seg_gap(pos[t - 1], pos[t], (n, e), r))
    return entered, o['closest_threat_m'], between, o['goal_met']


def main(runs: Path, saved: Path, tag: str, seeds: Path):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    rows = {a: [] for a in 'ABCDE'}
    for task in TASKS:
        s2 = runs / f'scored-20261120-S-{task}'
        ex = saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'
        names = [f'threat-{band}-{seed}' for band in BANDS for seed in book[task][band]]
        for block in range(40):
            arms = json.loads((s2 / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']
            arms['E'] = json.loads((ex / f'learnE-{task}-b{block}' / 'arms.json').read_text())['arms']['E']
            for a in 'ABCDE':
                if not arms[a]['adopted']:
                    continue
                phase = f'threat3-{task}-b{block}-{arms[a]["source_sha256"]}'
                root = s2 / phase if (s2 / phase).is_dir() else ex / phase
                for name in names:
                    rows[a].append(flight(root / 'flights' / name / 'outcome.json'))
    print('Per arm: flights flown; scored as entering; of those scored clear, how many came within 0.35, 0.55 and '
          '1.0 m of the edge at a check; the median smallest gap at the checks; and how many had a straight path '
          'between two checks that passed inside the zone, with the deepest such path')
    for a, rs in rows.items():
        clear = [r for r in rs if not r[0]]
        at = [r[1] for r in clear]
        inside = [r[2] for r in clear if r[2] < 0]
        inside_met = sum(1 for r in clear if r[2] < 0 and r[3])
        print(f'  arm {a}: flown {len(rs)}; entered {len(rs) - len(clear)}; clear {len(clear)}; '
              f'within 0.35 m {sum(g < 0.35 for g in at)}, 0.55 m {sum(g < 0.55 for g in at)}, '
              f'1.0 m {sum(g < 1.0 for g in at)}; median gap {statistics.median(at):.2f} m; '
              f'straight path inside {len(inside)} ({inside_met} of them met the goal)'
              + (f', deepest {-min(inside):.2f} m' if inside else ''))
    print('Check: the straight-path gap is never larger than the gap at the checks, which it includes as end points: '
          + str(all(r[2] <= r[1] + 1e-2 for rs in rows.values() for r in rs if not r[0])))


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))

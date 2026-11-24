"""Exploratory: Study 2 goal counts by the gap between the threat zone and the target.

Not part of the frozen analysis of PROTOCOL-2.md. For each fresh threat-zone
scenario (seeds 44001 to 44020) of reach, reach3d and land, the gap is the
horizontal distance from the zone's edge to the target, read from the scenario
recorded in each evaluation flight. The gaps fall into two groups, 3.0 to 3.7 m
and 4.5 m or more, so a scenario is 'close' when its gap is at most 4 m. The
script counts flights that met the goal in each group, for the procedures
learned with the zone (threat arm) and without it (matched arm). Only flights
that were flown are counted, so a run that adopted nothing contributes none.

Usage: python3 manuscript/exploratory_gap.py --records FOLDER [--out FILE.json]
FOLDER contains runs/scored-2, as in the data archive. Standard library only;
it reads outcome.json files and writes nothing into the records.
"""
import argparse
import glob
import json
import math
import os
from pathlib import Path

TASKS = ('reach', 'reach3d', 'land')
ARMS = {'threat': 'learned with the zone', 'matched': 'learned without the zone'}
CLOSE_M = 4.0


def gap_m(outcome):
    kind, _trigger, _start, north, east, radius = outcome['events'][0][:6]
    assert kind == 'threat'
    goal = outcome['goal']
    return math.hypot(goal['target_north_m'] - north, goal['target_east_m'] - east) - radius


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    runs = args.records.resolve() / 'runs' / 'scored-2'
    result = {}
    for task in TASKS:
        gaps, rows = {}, {}
        for arm in ARMS:
            counts = {'close': [0, 0], 'wide': [0, 0]}
            pattern = str(runs / f'threat-{task}-b*-{arm}' / 'flights' / 'threat-440*' / 'outcome.json')
            for path in sorted(glob.glob(pattern)):
                outcome = json.loads(Path(path).read_text())
                seed = Path(path).parent.name
                gap = round(gap_m(outcome), 2)
                assert gaps.setdefault(seed, gap) == gap, (seed, gap)
                group = 'close' if gap <= CLOSE_M else 'wide'
                counts[group][0] += bool(outcome['goal_met'])
                counts[group][1] += 1
            rows[arm] = {group: {'met': met, 'flown': flown} for group, (met, flown) in counts.items()}
        assert len(gaps) == 20, (task, len(gaps))
        values = sorted(gaps.values())
        assert not any(3.7 < g < 4.5 for g in values), values
        result[task] = {'scenario_gaps_m': values,
                        'close_scenarios': sum(g <= CLOSE_M for g in values),
                        'arms': rows}
        for arm, label in ARMS.items():
            r = rows[arm]
            print(f"{task}, {label}: close gap met {r['close']['met']}/{r['close']['flown']}, "
                  f"wide gap met {r['wide']['met']}/{r['wide']['flown']}")
    if args.out:
        if args.out.exists():
            raise SystemExit(f'{args.out} exists; refusing to overwrite')
        args.out.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()

"""The counts of design section 8, from the flight folders of a run root.

Reads <root>/pass<k>/worker<j>/flights/*/ (outcome.json and planner.json) and each worker's results.jsonl. For every pass,
setting, task and distance band it counts the flights that met the goal and the flights that ended in a zone entry, out
of the flights flown, with the other end reasons. A flight that never produced an outcome in three attempts is a fault.
Faults are listed on their own and are never counted as a success or a failure, nor in a denominator. It also gives, for
each setting, on how many scenarios the two passes ended the same way. There are no intervals and no tests.

  .venv/bin/python -B -m planner_check.summarise runs/planner-check-DATE [--out summary.json]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

TASKS = ('reach', 'reach3d', 'land')
GROUPS = {'close': 'close', 'middle': 'distant', 'wide': 'distant'}   # the paper's distant targets are middle and wide


def read_flights(root: Path) -> tuple:
    """(flown, faults). flown: one record for each flight folder with an outcome. faults: one record for each item whose
    last row in a worker's results.jsonl is a fault and which has no outcome."""
    flown, rows = [], []
    for folder in sorted(Path(root).glob('pass*/worker*')):
        pass_number = int(folder.parent.name[len('pass'):])
        for planner in sorted((folder / 'flights').glob('*/planner.json')):
            meta = json.loads(planner.read_text())
            outcome = json.loads((planner.parent / 'outcome.json').read_text())
            flown.append({'pass': pass_number, 'setting': meta['setting'], 'task': meta['task'], 'band': meta['band'],
                          'seed': meta['seed'], 'end_reason': outcome['end_reason'], 'goal_met': bool(outcome['goal_met']),
                          'planner_rows': meta.get('planner_rows') or {}})
        results = folder / 'results.jsonl'
        if results.exists():
            rows += [{**json.loads(line), 'pass': pass_number} for line in results.read_text().splitlines() if line]
    have = {(f['pass'], f['setting'], f['task'], f['band'], f['seed']) for f in flown}
    last = {}
    for r in rows:
        last[(r['pass'], r['setting'], r['task'], r['band'], r['seed'])] = r
    faults = [{'pass': k[0], 'setting': k[1], 'task': k[2], 'band': k[3], 'seed': k[4], 'attempts': r['attempt'],
               'error': r.get('error')} for k, r in sorted(last.items()) if r['status'] == 'fault' and k not in have]
    return flown, faults


def acted(f: dict) -> bool | None:
    """Did the planner act in the flight: any Dijkstra path or active BendyRuler row. None if the log was not read."""
    rows = f['planner_rows']
    values = [rows.get('dijkstra_rows'), rows.get('bendyruler_rows')]
    if any(v is None for v in values):
        return None
    return sum(values) > 0


def cell(flights: list) -> dict:
    ends = Counter(f['end_reason'] for f in flights)
    unknown = sum(1 for f in flights if acted(f) is None)
    return {'flown': len(flights), 'met_goal': sum(f['goal_met'] for f in flights), 'entered_threat': ends['entered_threat'],
            'other_end_reasons': {k: v for k, v in sorted(ends.items()) if k != 'entered_threat' and not (
                k in ('held', 'landed'))},
            'planner_acted': sum(1 for f in flights if acted(f)), 'planner_log_unread': unknown,
            'dijkstra_failed_flights': sum(1 for f in flights if (f['planner_rows'].get('dijkstra_error_rows') or 0) > 0)}


def summarise(root: Path) -> dict:
    flown, faults = read_flights(root)
    groups = defaultdict(list)
    for f in flown:
        for task in (f['task'], 'all'):
            for group in (GROUPS[f['band']], 'all'):
                groups[(f['pass'], f['setting'], task, group)].append(f)
    cells = {}
    for (pass_number, setting, task, group), flights in sorted(groups.items()):
        cells.setdefault(f'pass{pass_number}', {}).setdefault(f'setting{setting}', {}).setdefault(task, {})[group] = cell(flights)
    ends = defaultdict(dict)
    for f in flown:
        ends[(f['setting'], f['task'], f['band'], f['seed'])][f['pass']] = f['end_reason']
    agreement = {}
    for setting in sorted({k[0] for k in ends}):
        both = [v for k, v in ends.items() if k[0] == setting and 1 in v and 2 in v]
        agreement[f'setting{setting}'] = {'scenarios_flown_in_both_passes': len(both),
                                          'same_end_reason': sum(v[1] == v[2] for v in both)}
    return {'flights_flown': len(flown), 'cells': cells, 'faults': faults, 'pass_agreement': agreement}


def table(summary: dict) -> str:
    lines = []
    for pass_name, by_setting in summary['cells'].items():
        lines.append(f'{pass_name}: met goal / entered zone, out of flights flown')
        lines.append(f'{"setting":8}{"task":9}{"close":>22}{"distant":>22}{"all":>22}')
        for setting_name, by_task in by_setting.items():
            for task in (*TASKS, 'all'):
                if task not in by_task:
                    continue
                parts = []
                for group in ('close', 'distant', 'all'):
                    c = by_task[task].get(group)
                    parts.append(f'{c["met_goal"]} met, {c["entered_threat"]} in, of {c["flown"]}' if c else '-')
                lines.append(f'{setting_name[len("setting"):]:8}{task:9}' + ''.join(f'{p:>22}' for p in parts))
        lines.append('')
    lines.append('faults (flights without an outcome after three attempts; not counted above):')
    lines += [f'  pass {f["pass"]}, setting {f["setting"]}, {f["task"]} {f["band"]} {f["seed"]}: {f["error"]}'
              for f in summary['faults']] or ['  none']
    lines.append('the two passes ended the same way on (scenarios flown in both):')
    lines += [f'  {k}: {v["same_end_reason"]} of {v["scenarios_flown_in_both_passes"]}'
              for k, v in summary['pass_agreement'].items()]
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('root', type=Path)
    p.add_argument('--out', type=Path, help='write the JSON here; the table goes to the screen either way')
    a = p.parse_args(argv)
    summary = summarise(a.root)
    if a.out:
        a.out.write_text(json.dumps(summary, indent=1, sort_keys=True) + '\n')
    print(table(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())

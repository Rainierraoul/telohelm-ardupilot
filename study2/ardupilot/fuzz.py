"""Fuzz an adopted procedure: fly many drawn scenarios in parallel and group what breaks it.

Run from paper3/:
  .venv/bin/python -m ardupilot.fuzz --task reach --from-run runs/reach-hold-gem-sonnet-2 --count 200 --out runs/fuzz-reach-1

Each scenario comes from draw(task, seed): a random mission, base wind and zero to three events, combined, with wider
strengths and timings than battle.py's families. Its seed fixes the scenario but not the flight, because the simulator runs freely; whether a failure repeats
has to be measured.
No model is called. Episodes are judged on the simulator's truth. Failures are grouped by how they ended and which
events were present. This is development work: seeds here must stay apart from any range later reserved for testing.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import multiprocessing
from pathlib import Path
import random
import time

from . import battle
from . import pack as P

KINDS = ('jam', 'spoof', 'rc_loss', 'gust', 'motor', 'threat')
# The simulator does not wait for Telohelm. A flight whose decisions fell more than one step behind was flown on stale
# commands, which is a fault of the machine's load and not of the procedure, so it is left out of the rates.
MAX_LAG_S = 1.0


def draw_event(rng, kind, task, goal):
    at = f'p{rng.uniform(0.05, 0.9):.2f}'
    if kind == 'jam':
        return ('jam', at, rng.randint(3, 40))
    if kind == 'spoof':
        north, east = battle.point(rng, 5, 60)
        return ('spoof', at, rng.randint(6, 40), north, east)
    if kind == 'rc_loss':
        return ('rc_loss', at, rng.randint(2, 30))
    if kind == 'gust':
        return ('gust', at, rng.randint(5, 40), round(rng.uniform(4, 16), 1), round(rng.uniform(0, 6), 1))
    if kind == 'motor':
        return ('motor', at, rng.randint(5, 40), round(rng.uniform(0.6, 0.95), 2))
    # A threat zone near the straight path, appearing early, at least 5 m clear of the start so it can be avoided.
    tn, te = goal
    share, side = rng.uniform(0.35, 0.8), rng.uniform(-10, 10)
    length = max(math.hypot(tn, te), 1.0)
    zn, ze = tn * share - side * te / length, te * share + side * tn / length
    away = max(math.hypot(zn, ze), 8.0)
    scale = away / max(math.hypot(zn, ze), 1e-6)
    return ('threat', rng.randint(1, 3), 300, round(zn * scale, 1), round(ze * scale, 1),
            round(min(rng.uniform(4, 12), away - 5.0), 1))


def draw(task: str, seed: int) -> P.Scenario:
    """One fuzz scenario, fixed by task and seed."""
    rng = random.Random(f'fuzz/{task}/{seed}')
    base = battle.generate(task, 'calm', 10_000_000 + seed)
    params = dict(base.params)
    goal = (params['centre_north_m'], params['centre_east_m']) if task == 'orbit' else (
        params['target_north_m'], params['target_east_m'])
    kinds = [k for k in KINDS if not (k == 'threat' and task == 'orbit')]
    chosen = rng.sample(kinds, rng.choices((0, 1, 2, 3), (1, 4, 3, 2))[0])
    events = tuple(draw_event(rng, kind, task, goal) for kind in chosen)
    wind = round(rng.uniform(0, 6), 1) if rng.random() < 0.5 else 0.0
    return P.Scenario(task, f'fuzz-{seed}', base.params, wind, round(rng.uniform(0, 360)), events)


def worker(index, out, task, source, origin, cases, speedup):
    battle.run(Path(out) / f'worker-{index}', task, source, origin, cases=cases, speedup=speedup, instance=index + 1,
               keep_simulators=False)


def fly_batch(out, task, source, origin, cases, workers, speedup):
    out.mkdir(parents=True)
    context = multiprocessing.get_context('spawn')
    workers = min(workers, len(cases))
    processes = [context.Process(target=worker, args=(i, str(out), task, source, origin, cases[i::workers], speedup))
                 for i in range(workers)]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    rows = []
    for path in sorted(out.glob('worker-*/results.jsonl')):
        rows += [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        row['timing_invalid'] = (row['max_decision_lag_s'] or 0) > MAX_LAG_S
    return rows, [p.exitcode for p in processes if p.exitcode]


def fly_many(out, task, source, origin, cases, workers=8, speedup=5.0, retries=2):
    """Fly scenarios in parallel with no learning. Returns one row per flight, each marked timing_invalid or not,
    and the worker exit codes that were not zero. source is a procedure's code or a list of them. The machine's load
    can change under a run, so a flight whose decisions fell behind is flown again at half the speed, up to retries
    times, and only the last try counts."""
    out = Path(out).resolve()
    rows, failures = fly_batch(out, task, source, origin, cases, workers, speedup)
    for number in range(1, retries + 1):
        late = {f"{r['family']}-{r['seed']}" for r in rows if r['timing_invalid']}
        if not late:
            break
        speedup /= 2
        again = [c for c in cases if c.episode_id in late]
        redone, bad = fly_batch(out / f'retry-{number}', task, source, origin, again, workers, speedup)
        failures += bad
        rows = [r for r in rows if f"{r['family']}-{r['seed']}" not in late] + redone
    (out / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return rows, failures


def label(row):
    return '+'.join(sorted({e[0] for e in row['events']})) or 'none'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--task', choices=sorted(P.TASKS), required=True)
    parser.add_argument('--from-run', type=Path, required=True)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--first-seed', type=int, default=1)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--speedup', type=float, default=5.0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError('Use a new output directory; records are never overwritten')
    args.out.mkdir(parents=True)
    source = battle.adopted_source(args.from_run)
    cases = [draw(args.task, seed) for seed in range(args.first_seed, args.first_seed + args.count)]
    started = time.monotonic()
    flown, worker_failures = fly_many(args.out / 'flights', args.task, source, str(args.from_run), cases, args.workers,
                                      args.speedup)
    rows = [r for r in flown if not r['timing_invalid']]
    elapsed = time.monotonic() - started
    failed = [r for r in rows if not r['goal_met']]
    groups = Counter((r['end_reason'], label(r)) for r in failed)
    by_events = Counter(label(r) for r in rows)
    summary = {'task': args.task, 'origin': str(args.from_run), 'flown': len(rows), 'of': args.count,
               'timing_invalid': len(flown) - len(rows), 'workers': args.workers, 'speedup': args.speedup,
               'met': len(rows) - len(failed), 'wall_seconds': round(elapsed),
               'episodes_per_hour': round(len(flown) / elapsed * 3600) if elapsed else None,
               'worker_failures': worker_failures,
               'endings': dict(Counter(r['end_reason'] for r in rows)),
               'failure_groups': [{'ending': k[0], 'events': k[1], 'count': n,
                                   'of_with_these_events': by_events[k[1]]} for k, n in groups.most_common()]}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(f"{args.task}: met {summary['met']} of {summary['flown']} valid flights ({summary['timing_invalid']} left out "
          f"for lag) in {summary['wall_seconds']} s, {summary['episodes_per_hour']} episodes an hour")
    for g in summary['failure_groups'][:15]:
        print(f"  {g['count']:4} of {g['of_with_these_events']:4}  {g['ending']:22} {g['events']}")
    return 0 if len(flown) == args.count else 1


if __name__ == '__main__':
    raise SystemExit(main())

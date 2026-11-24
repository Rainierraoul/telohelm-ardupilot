"""Fly an adopted procedure through a contested battlespace, with no learning.

Run from paper3/:
  .venv/bin/python -m ardupilot.battle --task reach --from-run runs/gem-sonnet-reach-2 --seeds 3 --out runs/battle-reach-1

Each scenario is drawn from a seed: where the goal lies, and one family of events (FAMILIES). Nobody writes an episode
by hand. The task, family and seed fix the scenario, not the flight: the simulator runs freely, and exact repeats are
unproven. Every episode is judged on the simulator's
truth. This measures how a procedure learned in calm conditions copes when the world turns against it, which is the
starting point for teaching Telohelm to recover (paper 4).
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import random
import time

from telohelm.demo import _write

from . import pack as P

FAMILIES = ('calm', 'wind', 'jam', 'spoof', 'rc_loss', 'gust', 'motor', 'threat')


THREAT_WARN_M = 9.0     # least distance from the drone to a threat zone's edge when the procedure first sees it
STEP_TRAVEL_M = 5.0     # the farthest the drone flies in one step: the 5 m/s speed limit for one second
THREAT_TRIGGER_M = THREAT_WARN_M + 2 * STEP_TRAVEL_M   # switch on within 19 m: up to a step to notice, a step blind
THREAT_CLEAR_M = 3.0    # least gap between a threat zone's edge and the target


def point(rng, near, far):
    bearing = math.radians(rng.uniform(0, 360))
    distance = rng.uniform(near, far)
    return round(distance * math.cos(bearing), 1), round(distance * math.sin(bearing), 1)


# The race time limit is the straight-line path between gates at RACE_PACE_MS, plus RACE_SLACK_S. Calibrated on
# 1 November 2026: the authored reference (demo.REFERENCE['race3d']) flew six scenarios at 2.7 to 3.1 m/s along that
# path (runs/race3d-ref-probe-3), so this limit leaves it 18 to 38 per cent spare. 4 m/s was tried first and the
# reference could not meet it: ArduPilot's guided mode answers a velocity command about half a second late.
RACE_PACE_MS = 3.0
RACE_SLACK_S = 3.0
# A practice stage may ask for a lower pace than the task's own (the world-modeller's graded practice). demo.py sets this
# for a staged run and records it in the run's config; None means the task's pace.
STAGE_PACE_MS = None


# How many gates a race3d course has, by family. The long families (added 2 November 2026) are practice for pacing over
# a whole course: the learned racing skill met its limit on 3 to 5 gates but fell behind on the 19-gate Split-S. They
# stay shorter than the Split-S so that track remains an unseen test.
RACE_GATE_COUNTS = {'calm': (3, 5), 'wind': (3, 5), 'long': (10, 16), 'longwind': (10, 16)}


def race_gates(rng, count=(3, 5)):
    """count[0] to count[1] gates from the take-off hover: legs of 7 to 15 m, turns of up to 110 degrees, heights of
    1.5 to 7 m, and now and then a gate straight below the one before it, as in the Split-S. Kept inside half the
    fence."""
    n, e, a = 0.0, 0.0, P.TASKS['race3d'].start_alt_m
    heading, gates, dropped = rng.uniform(0, 2 * math.pi), [], False
    for _ in range(rng.randint(*count)):
        if gates and not dropped and a >= 3.5 and rng.random() < 0.3:
            gates.append((n, e, round(max(1.2, a - rng.uniform(2.0, 2.8)), 1)))
            dropped = True
        else:
            if math.hypot(n, e) > 0.5 * P.RACE_FENCE_M:
                heading = math.atan2(-e, -n) + rng.uniform(-0.6, 0.6)
            else:
                heading += rng.uniform(-1.9, 1.9)
            leg = rng.uniform(7.0, 15.0)
            gates.append((round(n + leg * math.cos(heading), 1), round(e + leg * math.sin(heading), 1),
                          round(rng.uniform(1.5, 7.0), 1)))
            dropped = False
        n, e, a = gates[-1]
    return tuple(gates)


def race_time_limit(gates):
    start = (0.0, 0.0, P.TASKS['race3d'].start_alt_m)
    path = sum(math.dist(x, y) for x, y in zip((start,) + gates, gates))
    return round(path / (STAGE_PACE_MS or RACE_PACE_MS) + RACE_SLACK_S, 1)


def generate(task: str, family: str, seed: int) -> P.Scenario:
    """One scenario for a task and event family, fixed by the seed. The 'matched' family is the threat family's
    scenario for the same seed with its threat zone removed (matched_calm)."""
    if family == 'matched':
        return matched_calm(task, seed)
    if task == 'race3d':
        if family not in RACE_GATE_COUNTS:
            raise ValueError(f'race3d families are {sorted(RACE_GATE_COUNTS)}')
        rng = random.Random(f'{task}/{family}/{seed}')
        gates = race_gates(rng, RACE_GATE_COUNTS[family])
        wind = round(rng.uniform(3, 6), 1) if family in ('wind', 'longwind') else 0.0
        return P.Scenario(task, f'{family}-{seed}', (('gates', gates), ('time_limit_s', race_time_limit(gates))),
                          wind, round(rng.uniform(0, 360)), ())
    if family == 'threat' and task == 'orbit':
        raise ValueError('a threat zone across an orbit leaves no way to meet the goal; not generated')
    rng = random.Random(f'{task}/{family}/{seed}')
    if task == 'orbit':
        cn, ce = point(rng, 25, 35)
        params = (('centre_north_m', cn), ('centre_east_m', ce), ('orbit_radius_m', round(rng.uniform(15, 22), 1)))
        tn, te = cn, ce
    else:
        tn, te = point(rng, 45, 55) if task == 'avoid' else point(rng, 20, 35) if task == 'land' else point(rng, 30, 50)
        params = (('target_north_m', tn), ('target_east_m', te))
        if task == 'reach3d':
            params += (('target_alt_m', round(rng.uniform(8, 30), 1)),)
        if task == 'avoid':
            side = rng.uniform(-3, 3)
            length = math.hypot(tn, te)
            params += (('zone_north_m', round(tn / 2 - side * te / length, 1)),
                       ('zone_east_m', round(te / 2 + side * tn / length, 1)),
                       ('zone_radius_m', round(rng.uniform(8, 12), 1)))
    # Events start when the mission is a drawn share done, so short and long missions are hit mid-way alike.
    at = lambda low, high: f'p{rng.uniform(low, high):.2f}'
    wind = 0.0
    if family == 'calm':
        events = ()
    elif family == 'wind':
        events, wind = (), round(rng.uniform(3, 6), 1)
    elif family == 'jam':
        events = (('jam', at(0.2, 0.5), rng.randint(20, 40)),)
    elif family == 'spoof':
        sn, se = point(rng, 20, 50)
        events = (('spoof', at(0.1, 0.3), 20, sn, se),)
    elif family == 'rc_loss':
        events = (('rc_loss', at(0.2, 0.5), 20),)
    elif family == 'gust':
        events = (('gust', at(0.1, 0.4), 30, round(rng.uniform(8, 14), 1), round(rng.uniform(2, 5), 1)),)
    elif family == 'motor':
        events = (('motor', at(0.1, 0.4), 40, round(rng.uniform(0.62, 0.75), 2)),)
    elif family == 'threat':
        radius = round(rng.uniform(6, 9), 1)
        if task == 'avoid':
            # Beside the no-go zone, closing one way round it.
            p = dict(params)
            length = math.hypot(tn, te)
            gap = (p['zone_radius_m'] + radius + 4) * rng.choice((-1, 1))
            zn, ze = p['zone_north_m'] - gap * te / length, p['zone_east_m'] + gap * tn / length
            start = rng.randint(1, 3)
        else:
            # Across the straight path, its near edge 24 to 30 m from home. The zone switches on at the first step
            # that begins with the drone within THREAT_TRIGGER_M (19 m) of its edge, so after the drone has flown at
            # least 5 m, and the procedure first sees it after that step: at the 5 m/s speed limit and one step a
            # second the drone is then still more than THREAT_WARN_M (9 m) from the edge. The target lies at least
            # THREAT_CLEAR_M beyond the zone; a mission too short for that is moved out along the same bearing.
            # (Until 2 November 2026 zones switched on at second 1 to 3, then by mission progress; in a pilot flight
            # the procedure first saw one 4.2 m from its edge.)
            length = math.hypot(tn, te)
            edge = rng.uniform(THREAT_TRIGGER_M + STEP_TRAVEL_M, THREAT_TRIGGER_M + 2 * STEP_TRAVEL_M + 1)
            need = edge + 2 * radius + THREAT_CLEAR_M
            if length < need:
                k = (need + 0.1) / length
                tn, te = round(tn * k, 1), round(te * k, 1)
                params = tuple((n, tn if n == 'target_north_m' else te if n == 'target_east_m' else v)
                               for n, v in params)
                length = math.hypot(tn, te)
            centre = edge + radius
            zn, ze = tn * centre / length, te * centre / length
            start = f'g{THREAT_TRIGGER_M:g}'
        events = (('threat', start, 300, round(zn, 1), round(ze, 1), radius),)
    else:
        raise ValueError(f'unknown family {family!r}')
    return P.Scenario(task, f'{family}-{seed}', params, wind, round(rng.uniform(0, 360)), events)


def matched_calm(task: str, seed: int) -> P.Scenario:
    """The threat family's scenario for this seed with its threat zone removed, named 'matched-<seed>'. Goal, target,
    wind and heading are the threat scenario's own, so a library that learns on these differs from one that learns on
    the threat scenarios only in the threat (D3's review of the second protocol, 4 November 2026). A calm scenario
    drawn with the same seed is a different place, because each family draws from its own random stream, and the
    threat family moves short targets outward to leave room for the zone."""
    threat = generate(task, 'threat', seed)
    twin = replace(threat, episode_id=f'matched-{seed}', events=())
    assert (twin.task, twin.params, twin.wind_ms, twin.wind_from_deg) == \
        (threat.task, threat.params, threat.wind_ms, threat.wind_from_deg)
    return twin


def adopted_source(run: Path) -> str:
    sources = json.loads((run / 'summary.json').read_text()).get('adopted_sources') or []
    if len(sources) != 1:
        raise ValueError(f'{run} has {len(sources)} adopted procedures; need exactly one')
    return sources[0]


def run(out, task, source, origin, families=FAMILIES, seeds=3, speedup=10.0, cases=None, instance=0,
        keep_simulators=True):
    from telohelm.runtime.broker import Broker
    from telohelm.runtime.episode_loop import NoModels, run_episode
    from telohelm.runtime.ledger import Ledger
    from telohelm.runtime.library import Library
    from telohelm.runtime.trusted_log import TrustedLog

    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; records are never overwritten')
    out.mkdir(parents=True)
    P.HOST.update(root=out, speedup=speedup, gcs=False, instance=instance, keep_simulators=keep_simulators)
    pack, spec = P.PACKS[task], P.TASKS[task]
    library = Library(out / 'library', pack=pack.public)
    guard = library.add({'kind': 'check', 'decision': 'control', 'conditions': [], 'source': P.GUARDS[task],
                         'origin': {'trusted_control_guard': 'designer-supplied velocity format and limits'}})
    library.set_status(guard, 'adopted', 'supplied action-format guard, not learned')
    for code in [source] if isinstance(source, str) else source:
        procedure = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': code,
                                 'origin': {'imported_from': origin}})
        library.set_status(procedure, 'adopted', f'adopted earlier in {origin}; flown here without learning')
    started, rows = time.monotonic(), []
    if cases is None:
        cases = [generate(task, f, s) for f in families if not (f == 'threat' and task == 'orbit')
                 for s in range(1, seeds + 1)]
    _write(out / 'run-config.json', {'task': task, 'origin': origin, 'source': source, 'speedup': speedup,
                                    'scenarios': [asdict(c) for c in cases]})
    for scenario in cases:
        folder = out / scenario.episode_id
        folder.mkdir()
        ledger = Ledger()
        log = TrustedLog(folder / 'episode.log', folder / 'episode.heads', 'battle')
        broker_log = TrustedLog(folder / 'broker.log', folder / 'broker.heads', 'battle')
        broker = Broker(scenario.episode_id, broker_log, ledger, None, condition='battle', stream=f'battle-{task}',
                        goal=pack.goal, tools={})
        try:
            result = run_episode(scenario, library, NoModels(), log, ledger, max_steps=spec.max_ticks,
                                 broker=broker, pack=pack)
        finally:
            log.close()
            broker_log.close()
        o = result['outcome']
        _write(folder / 'outcome.json', o)
        steps = o['native_steps']
        row = {'family': scenario.episode_id.rsplit('-', 1)[0], 'seed': int(scenario.episode_id.rsplit('-', 1)[1]),
               'goal_met': o['goal_met'], 'end_reason': o['end_reason'], 'seconds': o['action_steps'],
               'max_estimate_error_m': max((s['estimate_error_m'] for s in steps), default=None),
               'closest_threat_m': o['closest_threat_m'], 'events': o['events'],
               'max_decision_lag_s': max((s['decision_lag_s'] for s in steps), default=None)}
        rows.append(row)
        (out / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        print(f"{task}/{scenario.episode_id}: {'met' if row['goal_met'] else 'FAILED'} ({row['end_reason']}), "
              f"{row['seconds']} s, estimate error up to {row['max_estimate_error_m']} m", flush=True)
    table = {}
    for family in dict.fromkeys(r['family'] for r in rows):
        mine = [r for r in rows if r['family'] == family]
        table[family] = {'met': sum(r['goal_met'] for r in mine), 'of': len(mine),
                         'endings': dict(Counter(r['end_reason'] for r in mine))}
    summary = {'task': task, 'origin': origin, 'families': table, 'elapsed_seconds': round(time.monotonic() - started),
               'limitations': 'One adopted procedure, no learning, a few seeds per family. Development only.'}
    _write(out / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--task', choices=sorted(P.TASKS), required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--from-run', type=Path, help='a run folder whose summary has one adopted source')
    source.add_argument('--reference', action='store_true', help="fly the demo's hand-written reference controller")
    parser.add_argument('--families', nargs='*', default=list(FAMILIES))
    parser.add_argument('--seeds', type=int, default=3)
    parser.add_argument('--speedup', type=float, default=10.0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.reference:
        from .demo import REFERENCE
        code, origin = REFERENCE[args.task], 'hand-written reference controller'
    else:
        code, origin = adopted_source(args.from_run), str(args.from_run)
    summary = run(args.out, args.task, code, origin, args.families, args.seeds, args.speedup)
    for family, cell in summary['families'].items():
        print(f"  {family:8} met {cell['met']} of {cell['of']}  {cell['endings']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

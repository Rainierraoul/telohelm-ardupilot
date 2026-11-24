"""Fly the Split-S race with Telohelm's adopted reach3d procedure at a chosen decision rate and speed limits.

This is the first step toward fast System 1 control: the same learned procedure, unchanged, deciding more often and
allowed to fly faster. The record gives the race time, lap times, speeds, how close each gate pass was and the decision
lag (simulated time between the observation a decision used and the command reaching the autopilot). Run at speedup 1
so the simulator runs in real time and the lag reflects the real cost of deciding (to the telemetry period).

Run from paper3/ (one flight per instance at a time):
  .venv/bin/python -m ardupilot.race_run --from-run runs/reach3d-demo --rate-hz 10 --out runs/race-10hz
  .venv/bin/python -m ardupilot.race_run --from-run runs/reach3d-demo --rate-hz 10 --fast --out runs/race-10hz-fast
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from . import battle
from . import course3d as C3
from . import course_splits as S
from . import pack as P
from .course3d_run import fly_course

# --fast gives a reach3d flight the racing task's limits: the goal's speed limits and the raised guided-mode settings
# (pack.RACE_AUTOPILOT). ArduPilot's defaults in this build are WP_SPD_UP 2.5 m/s, WP_SPD_DN 1.5 m/s, WP_ACC 2.5 m/s/s
# and WP_ACC_Z 1.0 m/s/s. WP_SPD is already 10 m/s and is left alone: at the task's 5 m/s goal limit the horizontal
# cap came from the goal, not the autopilot. A race3d flight always uses the racing limits.
FAST_PARAMS = dict(P.RACE_AUTOPILOT)
FAST_GOAL = {'max_speed_ms': P.RACE_MAX_SPEED_MS, 'max_vertical_ms': P.RACE_MAX_VERTICAL_MS}


def summarise(rec: dict, course: C3.Course3D) -> dict:
    steps, reached = rec['native_steps'], rec['reached']
    passes = [r['gap_m'] for r in reached]
    speeds = []
    for a, b in zip(steps, steps[1:]):
        dt = b['t'] - a['t']
        if dt > 0:
            speeds.append(math.dist((a['north_m'], a['east_m'], a['alt_m']), (b['north_m'], b['east_m'], b['alt_m'])) / dt)
    t_at = {r['gate']: r['t'] for r in reached}
    laps = []
    if 7 in t_at:
        laps.append(t_at[7])
    if 7 in t_at and 14 in t_at:
        laps.append(round(t_at[14] - t_at[7], 2))
    passes.sort(); p = rec['provenance']
    return {'completed': rec['completed'], 'gates': f"{rec['gates_passed']}/{rec['gates']}", 'end': rec['end_reason'],
            'race_time_s': reached[-1]['t'] if rec['completed'] else None,
            'first_two_laps_s': laps,
            'pass_median_m': round(passes[len(passes) // 2], 2) if passes else None,
            'pass_max_m': round(passes[-1], 2) if passes else None,
            'speed_mean_ms': round(sum(speeds) / len(speeds), 2) if speeds else None,
            'speed_top_ms': round(max(speeds), 2) if speeds else None,
            'decisions': p['control_steps'], 'decision_period_s': p['decision_period_s'],
            'lag_median_s': p['lag_median_s'], 'lag_max_s': p['lag_max_s'], 'overruns': p['overruns'],
            'steps_without_procedure': p['steps_without_procedure'], 'model_calls': p['model_calls'],
            'goal_limits': p['goal_limits'], 'autopilot_params_confirmed': p['autopilot_params_confirmed'],
            'speedup': p['speedup'], 'task': p['task'], 'pass_rule': p['pass_rule']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--from-run', type=Path, required=True, help='a run with one adopted reach3d procedure')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--rate-hz', type=float, default=1.0, help='decisions per simulated second')
    p.add_argument('--fast', action='store_true', help='reach3d: use the racing speed limits (FAST_*)')
    p.add_argument('--task', choices=('reach3d', 'race3d'), default='reach3d',
                   help='the adopted procedure\'s task (the from-run must have learned it)')
    p.add_argument('--pass-rule', choices=('point', 'path'), help='default: point for reach3d, path for race3d')
    p.add_argument('--gate-radius', type=float, default=1.0)
    p.add_argument('--scale', type=float, default=1.0)
    p.add_argument('--speedup', type=float, default=1.0)
    p.add_argument('--stream-hz', type=int, default=50)
    p.add_argument('--instance', type=int, default=6)
    args = p.parse_args(argv)
    out = Path(args.out).resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; records are never overwritten')
    course = S.split_s_race(gate_radius=args.gate_radius, scale=args.scale)
    cert = C3.certify(course)
    if not cert['certified']:
        print('course rejected by the feasibility check:', cert['reason']); return 1
    source = battle.adopted_source(args.from_run)
    racing = args.fast or args.task == 'race3d'
    limits = FAST_GOAL if args.fast and args.task == 'reach3d' else {}
    rule = args.pass_rule or ('path' if args.task == 'race3d' else 'point')
    rec = fly_course(course, source, str(args.from_run), out, speedup=args.speedup, instance=args.instance,
                     dt=1.0 / args.rate_hz, extra_params=FAST_PARAMS if racing else None,
                     stream_hz=args.stream_hz, task=args.task, pass_rule=rule, **limits)
    summary = summarise(rec, course)
    summary.update(rate_hz=args.rate_hz, fast=racing, gate_radius=args.gate_radius, scale=args.scale)
    (out / 'summary.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary), flush=True)
    return 0 if rec['completed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

"""The hand-written yardstick of Paper 3's extra experiment (PROTOCOL-EXTRA.md): a simple avoidance controller flown
through the same procedure interface, on the same zone flights, as the procedures the model wrote.

The controller is the designer's reference controller for the avoid task (ardupilot/demo.py, REFERENCE['avoid']) with
two changes and no others. It reads the zone from ctx.threats, the list of zones active now, as every Study 2 procedure
had to, instead of the avoid task's fixed ctx.goal.zone_* fields; with no zone active it flies straight at the target.
And it adds the vertical command of the task's own reference controller: towards the target's height for reach3d,
and for land a descent once within 0.8 m of the point. The one number left to choose is the margin it keeps beyond the
zone's edge (the reference keeps 5 m). PROTOCOL-EXTRA.md fixes the grid, 1 to 5 m, and the rule that picks one margin on
the development (pilot) book's zone flights before any scored flight; the other margins are flown on the scored flights
as a sensitivity check.

  python -m extra.phase yard3 --task reach --margin 2 --out ROOT/yard3-reach-m2 --protocol 3 --instance 10
  python -m extra.phase yard3 --task reach --margin 2 --out DEV/yard3-reach-m2 --pilot ...   # development flights

A scored yard3 phase flies Study 2's 24 zone evaluation flights of the task (contract3.evaluation_cases), in the
instance's order, with the warm-up flight first, the 0.3 s command delay, and the late rule of Study 2's threat3 phase.
A development phase flies the pilot book's zone flights: its six evaluation flights and the zone layouts of its four
learning blocks, 18 a task. No model is called.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MARGINS_M = (1, 2, 3, 4, 5)
TASKS = ('reach', 'reach3d', 'land')

_HEAD = '''import math

MARGIN_M = {margin:.1f}


def decide(ctx):
    g = ctx.goal
    px, py = ctx.north_m, ctx.east_m
    dx, dy = g.target_north_m - px, g.target_east_m - py
    length = math.hypot(dx, dy)
    # The nearest active zone whose margin the straight path to the target crosses (demo.REFERENCE['avoid']'s test).
    zone, nearest = None, None
    for z in ctx.threats:
        keep = z.radius_m + MARGIN_M
        if length > 1e-6:
            u = max(0.0, min(1.0, ((z.north_m - px) * dx + (z.east_m - py) * dy) / (length * length)))
            if math.hypot(px + u * dx - z.north_m, py + u * dy - z.east_m) < keep:
                r = math.hypot(px - z.north_m, py - z.east_m)
                if nearest is None or r < nearest:
                    zone, nearest = z, r
    if zone is not None:
        keep = zone.radius_m + MARGIN_M
        rx, ry = px - zone.north_m, py - zone.east_m
        r = math.hypot(rx, ry) or 1e-6
        side = 1.0 if rx * dy - ry * dx > 0 else -1.0
        speed = 0.8 * g.max_speed_ms
        push = 0.8 * max(0.0, keep - r)
        vn = speed * (-ry / r) * side + push * rx / r
        ve = speed * (rx / r) * side + push * ry / r
    else:
        vn, ve = 0.6 * dx, 0.6 * dy
    lim = 0.9 * g.max_speed_ms
    s = math.hypot(vn, ve)
    if s > lim:
        vn, ve = vn * lim / s, ve * lim / s
'''
_TAIL = {
    'reach': "    return {'vn': vn, 've': ve}\n",
    # demo.REFERENCE['reach3d']'s vertical command
    'reach3d': ("    vd = 0.6 * (ctx.alt_m - g.target_alt_m)\n"
                "    vlim = 0.9 * g.max_vertical_ms\n"
                "    vd = max(-vlim, min(vlim, vd))\n"
                "    return {'vn': vn, 've': ve, 'vd': vd}\n"),
    # demo.REFERENCE['land']'s vertical command
    'land': ("    vd = 0.0\n"
             "    if math.hypot(dx, dy) < 0.8:\n"
             "        vd = min(0.9 * g.max_vertical_ms, 0.3 + 0.2 * ctx.alt_m)\n"
             "    return {'vn': vn, 've': ve, 'vd': vd}\n"),
}


def controller(task: str, margin: float) -> str:
    if task not in _TAIL:
        raise ValueError(f'the yardstick is for {TASKS}')
    return _HEAD.format(margin=float(margin)) + _TAIL[task]


def development_cases(seeds: dict, task: str) -> list:
    """The pilot book's zone flights for the task: its evaluation flights, then the zone layouts of its learning blocks."""
    from protocol import contract3 as C3
    cases = C3.evaluation_cases(seeds, task, pilot=True)
    for block in range(len(C3.book(seeds, True)['blocks'][task])):
        cases += C3.learning_cases(seeds, task, block, pilot=True, threat=True)
    ids = [c.episode_id for c in cases]
    if len(set(ids)) != len(ids):
        raise RuntimeError(f'development flights repeat a layout: {ids}')
    return cases


def phase_yard(argv=None) -> int:
    from ardupilot import battle, scored as S
    from ardupilot import ladder as L
    from protocol import contract3 as C3
    p = argparse.ArgumentParser(prog='yard3')
    p.add_argument('--task', choices=TASKS, required=True)
    p.add_argument('--margin', type=float, choices=[float(m) for m in MARGINS_M], required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--speedup', type=float, default=1.0)
    p.add_argument('--instance', type=int, default=S.SCORED_INSTANCES[0])
    p.add_argument('--protocol', type=int, choices=(3,), default=3)
    p.add_argument('--at-once', type=S.at_once_arg, default=4)
    p.add_argument('--pilot', action='store_true', help='the development flights of the pilot book')
    a = p.parse_args(argv)
    S.use_protocol(3)
    S.AT_ONCE = a.at_once
    S.refuse_start(1)
    out = Path(a.out)
    if not a.pilot and a.speedup != 1.0:
        raise SystemExit('scored flights fly in real time')
    S.refuse_late_history(len(S.late_attempts_set_aside(out.parent, out.name)), out.name)
    seeds = S.seeds()
    source = controller(a.task, a.margin)
    cases = development_cases(seeds, a.task) if a.pilot else C3.evaluation_cases(seeds, a.task)
    flown = [cases[i] for i in C3.flight_order(len(cases), a.instance)]
    protocol_extra = ROOT / 'PROTOCOL-EXTRA.md'
    if not a.pilot and not protocol_extra.exists():
        raise SystemExit('PROTOCOL-EXTRA.md is missing; the yardstick flies its scored flights only under it')
    S.guard(out, 'yard3', {'task': a.task, 'margin_m': a.margin, 'speedup': a.speedup,
                           'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                           'protocol_extra_sha256': (hashlib.sha256(protocol_extra.read_bytes()).hexdigest()
                                                     if protocol_extra.exists() else None),
                           'cases': [c.episode_id for c in cases], 'flight_order': [c.episode_id for c in flown]},
            a.pilot, a.instance)
    (out / 'source.py').write_text(source, encoding='utf-8')
    # From here on, phase_eval3's steps (ardupilot/scored.py), with the yardstick's source in place of a candidate's.
    L.fly_warmup(out, a.task, S.warmup_case(C3, seeds, a.task), speedup=a.speedup, instance=a.instance)
    battle.run(out / 'flights', a.task, source, f'hand-written yardstick, margin {a.margin:g} m', cases=flown,
               speedup=a.speedup, instance=a.instance, before_flight=S.flight_gate(out),
               command_delay_periods=L.COMMAND_DELAY_PERIODS)
    rows = [{'flight': c.episode_id, **L.timing(json.loads((out / 'flights' / c.episode_id / 'outcome.json').read_text()))}
            for c in flown]
    late = [r['flight'] for r in rows if r['late']]
    rows, kept = S.keep_late_attempt(rows, S.late_attempts_set_aside(out.parent, out.name))
    (out / 'timing.json').write_text(json.dumps(rows, indent=1) + '\n')
    if kept:
        (out / S.KEPT_LATE_FILE).write_text(json.dumps(kept, indent=1) + '\n')
    bad = S.write_route_end(out)
    if late and not kept:
        print(f'{len(late)} of {len(rows)} flights were late; the phase is held, not scored: {late[:5]}', flush=True)
    S.stop_for_bad_replacement(bad, 'yard3')
    return 1 if late and not kept else 0

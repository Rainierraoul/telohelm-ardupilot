"""Fly paper 3's task scenarios with ArduPilot's own flight modes, as a comparator for learned procedures.

No procedure and no model is involved: the autopilot flies each scenario itself, held to the same speed limits a
procedure gets (WP_SPD 5 m/s horizontal, 2 m/s up and down), and the pack's judge scores it on the simulator's
true state exactly as it scores a procedure. Per task:

- reach, reach3d: a guided-mode position target at the point, sent every step.
- land: a guided-mode position target over the point at the current height; once within 0.5 m, land mode.
- orbit: guided flight to the nearest point on the circle, turned to face the centre; then circle mode, whose centre
  ArduPilot places one radius ahead of the vehicle, at the task's radius, clockwise at 4 m/s round the circle. Circle
  mode takes its climb rate from the throttle stick, and the simulator has no radio, so the sticks are held centred
  by a radio override sent every step, as a pilot would hold them.
- avoid: no ArduPilot mode flies round an arbitrary no-go zone, so there is no comparator.

Run from paper3/:
  .venv/bin/python -m ardupilot.autopilot_modes --task reach --seeds 9101 9102 --out runs/ap-check-1
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

from telohelm.demo import _write
from telohelm.runtime.trusted_log import TrustedLog

from . import pack as P

LIMITS = {'WP_SPD': P.MAX_SPEED_MS, 'WP_SPD_UP': P.MAX_VERTICAL_MS, 'WP_SPD_DN': P.MAX_VERTICAL_MS}
ORBIT_SPEED_MS = 4.0
TASKS = ('reach', 'reach3d', 'land', 'orbit')


class ModeEpisode(P.Episode):
    """The pack's episode with ArduPilot doing the flying: send_command follows a per-task plan instead of a velocity."""

    def __init__(self, scenario):
        super().__init__(scenario)
        self.extra_autopilot_params = dict(LIMITS)
        self.stage = 'approach'
        if self.task.name == 'land':
            self.allowed_modes = frozenset({'GUIDED', 'LAND'})
        if self.task.name == 'orbit':
            self.allowed_modes = frozenset({'GUIDED', 'CIRCLE'})

    def _alt(self):
        return -self.sim.state['down']

    def send_command(self):
        g, s, name = self.goal, self.sim.state, self.task.name
        if name in ('reach', 'reach3d'):
            alt = g.get('target_alt_m', self._alt() if self.t == 0 else self.hold_alt)
            if self.t == 0:
                self.hold_alt = alt
            self.sim.command_position(g['target_north_m'], g['target_east_m'], alt)
        elif name == 'land':
            if self.stage == 'approach':
                if self.t == 0:
                    self.hold_alt = self._alt()
                self.sim.command_position(g['target_north_m'], g['target_east_m'], self.hold_alt)
                if math.hypot(s['north'] - g['target_north_m'], s['east'] - g['target_east_m']) < 0.5:
                    self.sim.set_mode('LAND')
                    self.stage = 'land'
        elif name == 'orbit':
            cn, ce, r = g['centre_north_m'], g['centre_east_m'], g['orbit_radius_m']
            if self.stage == 'approach':
                if self.t == 0:
                    self.hold_alt = self._alt()
                    bearing = math.atan2(s['east'] - ce, s['north'] - cn)
                    self.entry = (cn + r * math.cos(bearing), ce + r * math.sin(bearing))
                    self.face = math.degrees(math.atan2(ce - self.entry[1], cn - self.entry[0])) % 360
                self.sim.command_position(self.entry[0], self.entry[1], self.hold_alt, yaw_deg=self.face)
                near = math.hypot(s['north'] - self.entry[0], s['east'] - self.entry[1]) < 0.7
                facing = abs(((s['heading_deg'] or 0) - self.face + 180) % 360 - 180) < 5
                if near and facing:
                    self.sim.set_param('CIRCLE_RADIUS_M', r)
                    self.sim.set_param('CIRCLE_RATE', math.degrees(ORBIT_SPEED_MS / r))   # positive is clockwise
                    self.sim.set_param('CIRCLE_OPTIONS', 0)
                    self.sim.advance_to(self.sim.state['t'] + 0.3)   # let the settings land before the mode change
                    self.sim.hold_sticks_centred()
                    self.sim.set_mode('CIRCLE')
                    self.stage = 'circle'
            else:
                self.sim.hold_sticks_centred()
        else:
            raise ValueError(f'no ArduPilot-mode comparator for {name}')


def run(out, task, cases, speedup=1.0, instance=6):
    if task not in TASKS:
        raise ValueError(f'no ArduPilot-mode comparator for {task}')
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; records are never overwritten')
    out.mkdir(parents=True)
    P.HOST.update(root=out, speedup=speedup, gcs=False, instance=instance, keep_simulators=True)
    _write(out / 'run-config.json', {'task': task, 'origin': 'ArduPilot flight modes (autopilot_modes.py)',
                                    'limits': LIMITS, 'orbit_speed_ms': ORBIT_SPEED_MS, 'speedup': speedup,
                                    'scenarios': [asdict(c) for c in cases]})
    rows, started = [], time.monotonic()
    for scenario in cases:
        folder = out / scenario.episode_id
        folder.mkdir()
        log = TrustedLog(folder / 'episode.log', folder / 'episode.heads', 'autopilot-modes')
        ep, o = ModeEpisode(scenario), None
        try:
            ep.reset()
            while ep.end_reason is None:
                ep.step({})
                st = ep.native_steps[-1]
                log.append({'kind': 'step', 't': st['t'], 'mode': st['mode'], 'stage': ep.stage,
                            'truth': {k: st[k] for k in ('north_m', 'east_m', 'alt_m')}})
            o = ep.outcome()
            # The protected log ends with the outcome, as a task flight's does, so the validation gate can check the
            # result row against it (A4 of Codex's review, 3 November 2026).
            log.append({'kind': 'episode_end', 'episode': scenario.episode_id, 'goal_met': o['goal_met'],
                        'end_reason': o['end_reason'], 'settled': True})
        finally:
            if o is None:
                ep.outcome()          # closes the simulator after a fault; no result is written for this flight
            log.close()
        _write(folder / 'outcome.json', o)
        fam, seed = scenario.episode_id.rsplit('-', 1)
        row = {'family': fam, 'seed': int(seed), 'goal_met': o['goal_met'], 'end_reason': o['end_reason'],
               'seconds': o['ended_at'] * ep.tick, 'stage_at_end': ep.stage}
        rows.append(row)
        (out / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        print(f"{task}/{scenario.episode_id}: {'met' if row['goal_met'] else 'FAILED'} ({row['end_reason']}), "
              f"{row['seconds']:.0f} s", flush=True)
    table = {}
    for fam in dict.fromkeys(r['family'] for r in rows):
        mine = [r for r in rows if r['family'] == fam]
        table[fam] = {'met': sum(r['goal_met'] for r in mine), 'of': len(mine),
                      'endings': dict(Counter(r['end_reason'] for r in mine))}
    summary = {'task': task, 'origin': 'ArduPilot flight modes', 'families': table,
               'elapsed_seconds': round(time.monotonic() - started)}
    _write(out / 'summary.json', summary)
    return summary


def main(argv=None):
    from .battle import generate
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--task', choices=TASKS, required=True)
    p.add_argument('--family', default='calm')
    p.add_argument('--seeds', type=int, nargs='+', required=True)
    p.add_argument('--speedup', type=float, default=1.0)
    p.add_argument('--instance', type=int, default=6)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    summary = run(a.out, a.task, [generate(a.task, a.family, k) for k in a.seeds], a.speedup, a.instance)
    print(json.dumps(summary['families']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Fly a seeded, certified course with Telohelm's adopted procedure, for the live demonstration.

The course comes from a seed (course.generate) and is checked flyable by an independent reference controller
(course.certify) before Telohelm runs. Telohelm then flies it: each second the adopted 'reach' procedure is run in
the real sandbox through the ordinary chooser, with the current gate as its goal, and the velocity it returns is
commanded. No model is called at any step, and the procedure has no gate or course written into it, so a clean flight
is proof the library flies a course it was never trained on.

What is recorded for the overlay: the procedure's content hash, the model-call count (zero), the seed, the
certification, and the true path. The same runner drives either plain SITL or SITL backed by Gazebo (--gazebo), where
the flight is watched in the Gazebo window.

Run from paper3/:
  .venv/bin/python -m ardupilot.course_run --seed 4242 --from-run runs/reach-hold-gem-sonnet-2 --out runs/course-4242
  .venv/bin/python -m ardupilot.course_run --seed 4242 --from-run runs/reach-hold-gem-sonnet-2 --out runs/course-4242 --gazebo --speedup 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from . import battle
from . import course as C
from . import pack as P
from .vehicle import Sitl


def _bundle(sim, t, threats):
    """The native readings the control decision needs, as pack.Episode builds them (no derived features)."""
    s = sim.state
    return {'t': t, 'north_m': round(s['north'], 3), 'east_m': round(s['east'], 3), 'alt_m': round(-s['down'], 3),
            'vn_ms': round(s['vn'], 3), 've_ms': round(s['ve'], 3), 'vd_ms': round(s['vd'], 3),
            'heading_deg': round(s['heading_deg'] or 0.0, 1),
            'battery_pct': s['battery_pct'] if s['battery_pct'] is not None else -1,
            'battery_v': round(s['battery_v'], 2) if s['battery_v'] is not None else -1,
            'gps_fix_type': s['gps_fix'] if s['gps_fix'] is not None else -1,
            'gps_satellites': s['gps_sats'] if s['gps_sats'] is not None else -1,
            'ekf_flags': s['ekf_flags'] if s['ekf_flags'] is not None else -1,
            'threats': list(threats), 'observation_age_s': 0.0, 'step_duration_s': 1.0}


def _true(sim):
    """The simulator's true position. Missing truth raises pack.MissingTruth; it never falls back to the estimate."""
    real = P.truth(sim.state)
    return real['north'], real['east']


def fly_course(course: C.Course, source: str, origin: str, out: Path, speedup: float = 10.0,
               gazebo: bool = False, instance: int = 0, pass_rule: str = 'point') -> dict:
    """Fly the adopted procedure through the course. Returns the record, including provenance and the true path."""
    from telohelm.runtime.chooser import choose
    from telohelm.runtime.library import Library
    from telohelm.runtime.trusted_log import TrustedLog, verify

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pack = P.PACKS['reach']
    needs = pack.roles.needs
    library = Library(out / 'library', pack=pack.public)
    guard = library.add({'kind': 'check', 'decision': 'control', 'conditions': [], 'source': P.GUARDS['reach'],
                         'origin': {'trusted_control_guard': 'designer-supplied velocity format and limits'}})
    library.set_status(guard, 'adopted', 'supplied action-format guard, not learned')
    proc = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': source,
                        'origin': {'imported_from': origin}})
    library.set_status(proc, 'adopted', f'adopted earlier in {origin}; flown here without learning')
    procedure_sha = hashlib.sha256(source.encode()).hexdigest()

    base_goal = dict(P.TASKS['reach'].goal({}))        # radius, fence, max_speed, etc.
    base_goal.update(version=1, time_limit_s=1e9)       # the runner, not the goal, decides when to move on

    folder = out / 'simulator'
    P.HOST.update(root=out, speedup=speedup, gcs=gazebo, instance=instance, keep_simulators=True)
    sim = Sitl(folder, 'copter', speedup, instance=instance, gcs=gazebo,
               params={'SIM_WIND_SPD': course.wind_ms, 'SIM_WIND_DIR': course.wind_from_deg},
               wall_limit_s=600.0, gazebo=gazebo)
    steps, model_calls, no_procedure = [], 0, 0   # the runner has no model; steps no procedure decided are counted
    gate_idx, t0 = 0, None
    reached = []
    end_reason, fault = 'flew the course', None
    # A hash-chained log of the flight, as in course3d_run (A2 of Codex's review, 3 November 2026): each record carries
    # a digest of the one before, and the protected heads file keeps every head, so a record edited, removed or added
    # afterwards shows up when the log is verified.
    log = TrustedLog(out / 'flight.log', out / 'flight.heads', 'course-flight-reach')
    log.append({'kind': 'flight_start', 'task': 'reach', 'procedure_sha256': procedure_sha, 'procedure_source': source,
                'origin': origin, 'course': course.as_dict(), 'decision_period_s': 1.0, 'speedup': speedup,
                'pass_rule': pass_rule, 'gate_radius_m': course.gates[0].radius_m if course.gates else None,
                'goal': base_goal, 'model_calls_possible': 0, 'flown_in': 'gazebo' if gazebo else 'sitl'})
    try:
        sim.prepare(alt_m=course.alt_m)
        t0 = sim.state['t']
        prev = _true(sim)   # for the 'path' rule: where the drone was at the previous decision
        velocity = {'vn': 0.0, 've': 0.0}
        for step in range(900):                         # a generous cap; courses finish well inside this
            gate = course.gates[gate_idx]
            goal = {**base_goal, 'target_north_m': gate.north_m, 'target_east_m': gate.east_m}
            seen_t = sim.state['position_t'] if sim.state['position_t'] is not None else sim.state['t']
            ctx = {**_bundle(sim, step, [z for z in ([course.zone] if course.zone else [])]),
                   'goal_version': 1, 'goal': goal}
            result = choose('control', ctx, library, needs=needs)
            if 'use' in result:
                velocity = {'vn': float(result['output']['vn']), 've': float(result['output']['ve'])}
                sha = result['use']
            else:
                sha = None                               # no procedure accepted; hold last velocity
                no_procedure += 1
            sim.command_velocity(velocity['vn'], velocity['ve'], 0.0)
            sim.drain(); lag = sim.state['t'] - seen_t   # decision lag, as in course3d_run (added 2 Nov 2026)
            sim.advance_to(t0 + (step + 1) * 1.0)
            real = P.truth(sim.state)
            tn, te = real['north'], real['east']
            times = P.run_times(result.get('tried'))
            steps.append({'t': step, 'north_m': round(tn, 2), 'east_m': round(te, 2),
                          'alt_m': round(-real['down'], 2), 'gate': gate_idx + 1,
                          'procedure': sha[:12] if sha else None,
                          'est_error_m': round(math.hypot(sim.state['north'] - tn, sim.state['east'] - te), 2),
                          'lag_s': round(lag, 3), 'truth_age_s': round(sim.state['t'] - sim.state['truth_t'], 3),
                          **times})
            log.append({'kind': 'step', 't': step, 'gate': gate_idx + 1, 'decided_by': sha, 'command': dict(velocity),
                        'observed': {k: ctx[k] for k in ('north_m', 'east_m', 'alt_m', 'vn_ms', 've_ms', 'vd_ms')},
                        'truth': steps[-1], 'lag_s': round(lag, 3), 'tried': result.get('tried', [])})
            # 'point': the true position at this decision is within the radius (horizontal). 'path': the straight
            # path flown since the previous decision passes within the radius, gates in order (pack.passes_on_segment),
            # horizontal on flat courses. Paper 3's scored runs use 'path' for every gate test (PROTOCOL.md).
            if pass_rule == 'path':
                centres = [(g.north_m, g.east_m, 0.0) for g in course.gates]
                n = P.passes_on_segment((prev[0], prev[1], 0.0), (tn, te, 0.0), centres, gate_idx, gate.radius_m)
                for k in range(gate_idx, gate_idx + n):
                    reached.append({'gate': k + 1, 't': step + 1})
                gate_idx += n
            elif math.hypot(tn - gate.north_m, te - gate.east_m) <= gate.radius_m:
                reached.append({'gate': gate_idx + 1, 't': step + 1})   # read at the end of the step (was step until 2 Nov 2026)
                gate_idx += 1
            prev = (tn, te)
            if gate_idx >= len(course.gates):
                break
            if math.hypot(tn, te) > course.fence_m:
                end_reason = 'left the fence'
                break
            if course.zone and math.hypot(tn - course.zone.north_m, te - course.zone.east_m) < course.zone.radius_m:
                end_reason = 'entered the no-go zone'
                break
        else:
            end_reason = 'ran out of steps'
    except BaseException as exc:
        fault = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        sim.close()
        # On a fault the end record says so; no course-flight.json is written and the phase stops (section 7).
        log.append({'kind': 'flight_end', 'end_reason': 'fault' if fault else end_reason, 'fault': fault,
                    'gates_passed': len(reached), 'gates': len(course.gates),
                    'completed': fault is None and gate_idx >= len(course.gates), 'reached': reached,
                    'steps_without_procedure': no_procedure, 'control_steps': len(steps)})
        log.close()

    record = {
        'seed': course.seed, 'gates': len(course.gates), 'gates_passed': len(reached),
        'completed': gate_idx >= len(course.gates), 'end_reason': end_reason,
        'provenance': {'procedure_sha256': procedure_sha, 'procedure_sha12': procedure_sha[:12],
                       'model_calls': model_calls, 'control_steps': len(steps),
                       'steps_without_procedure': no_procedure,
                       'pass_rule': pass_rule,
                       'flight_log_verified': verify(out / 'flight.log', out / 'flight.heads'),
                       'origin': origin, 'flown_in': 'gazebo' if gazebo else 'sitl'},
        'certification': C.certify(course), 'course': course.as_dict(),
        'reached': reached, 'native_steps': steps,
    }
    (out / 'course-flight.json').write_text(json.dumps(record, indent=1, default=str))
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--from-run', type=Path, required=True, help='a run folder with one adopted reach procedure')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--zone', action='store_true', help='include a no-go zone in the course')
    p.add_argument('--gazebo', action='store_true', help='fly in SITL backed by Gazebo (watch in the Gazebo window)')
    p.add_argument('--speedup', type=float, default=10.0)
    p.add_argument('--instance', type=int, default=0)
    args = p.parse_args(argv)

    course = C.generate(args.seed, args.zone)
    cert = C.certify(course)
    print(f"seed {args.seed}: {len(course.gates)} gates, certification: {cert['reason']} ({cert['seconds']}s)", flush=True)
    if not cert['certified']:
        print("course rejected by the feasibility check; not flying it. Try another seed.", flush=True)
        return 1
    source = battle.adopted_source(args.from_run)
    record = fly_course(course, source, str(args.from_run), args.out, speedup=args.speedup,
                        gazebo=args.gazebo, instance=args.instance)
    pv = record['provenance']
    print(f"{'completed' if record['completed'] else record['end_reason']}: passed "
          f"{record['gates_passed']} of {record['gates']} gates, procedure {pv['procedure_sha12']}, "
          f"model calls {pv['model_calls']}", flush=True)
    return 0 if record['completed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

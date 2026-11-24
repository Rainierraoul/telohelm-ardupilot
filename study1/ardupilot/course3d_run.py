"""Fly a seeded 3D course with Telohelm's adopted reach3d procedure.

Like course_run.py, but in three dimensions: the course (course3d.generate) threads gates up, over and around a building,
and the adopted reach3d procedure flies to each gate in turn, commanding vertical as well as horizontal velocity. The
course is certified flyable by the independent 3D reference first. No model is called in flight, and the procedure holds
no gate or building in it, so a clean flight is the learned 3D control generalising to a course it never saw.

Run from paper3/:
  .venv/bin/python -m ardupilot.course3d_run --seed 7 --from-run runs/reach3d-demo --out runs/course3d-7
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from . import battle
from . import course3d as C3
from . import pack as P


def _bundle(sim, t, dt=1.0):
    s = sim.state
    return {'t': t, 'north_m': round(s['north'], 3), 'east_m': round(s['east'], 3), 'alt_m': round(-s['down'], 3),
            'vn_ms': round(s['vn'], 3), 've_ms': round(s['ve'], 3), 'vd_ms': round(s['vd'], 3),
            'heading_deg': round(s['heading_deg'] or 0.0, 1),
            'battery_pct': s['battery_pct'] if s['battery_pct'] is not None else -1,
            'battery_v': round(s['battery_v'], 2) if s['battery_v'] is not None else -1,
            'gps_fix_type': s['gps_fix'] if s['gps_fix'] is not None else -1,
            'gps_satellites': s['gps_sats'] if s['gps_sats'] is not None else -1,
            'ekf_flags': s['ekf_flags'] if s['ekf_flags'] is not None else -1,
            'threats': [], 'observation_age_s': 0.0, 'step_duration_s': dt}


def fly_course(course: C3.Course3D, source: str, origin: str, out: Path, speedup: float = 10.0,
               gazebo: bool = False, instance: int = 0, dt: float = 1.0, max_speed_ms: float | None = None,
               max_vertical_ms: float | None = None, extra_params: dict | None = None,
               stream_hz: int = 10, task: str = 'reach3d', pass_rule: str = 'point') -> dict:
    """Fly the course, deciding every dt simulated seconds. max_speed_ms and max_vertical_ms replace the task's limits
    in the goal the procedure and guard read; extra_params are ArduPilot settings (for example the guided-mode speed
    and acceleration limits) applied before take-off; the record keeps both what was sent and what the autopilot
    reported back. For each decision the record keeps a lag: the newest telemetry time after the command was sent,
    minus the time of the position the decision used. It stands in for observation-to-command time and is only as
    fine as the telemetry stream period.

    task 'reach3d' gives the procedure one gate at a time as its target point. task 'race3d' gives it the whole gate
    list in the goal and ctx.gates_passed, as the racing task does. pass_rule 'point' counts a gate when a sampled
    position is within its radius (the rule of the earlier course results); 'path' counts it when the straight path
    between two samples comes within the radius, the racing task's rule. Each pass records its gap to the centre."""
    from telohelm.runtime.chooser import choose
    from telohelm.runtime.library import Library
    from telohelm.runtime.trusted_log import TrustedLog, verify
    from .vehicle import Sitl

    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    pack = P.PACKS[task]; needs = pack.roles.needs
    library = Library(out / 'library', pack=pack.public)
    guard = library.add({'kind': 'check', 'decision': 'control', 'conditions': [], 'source': P.GUARDS[task],
                         'origin': {'trusted_control_guard': 'designer-supplied velocity format and limits'}})
    library.set_status(guard, 'adopted', 'supplied action-format guard, not learned')
    proc = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': source,
                        'origin': {'imported_from': origin}})
    library.set_status(proc, 'adopted', f'adopted earlier in {origin}; flown here without learning')
    procedure_sha = hashlib.sha256(source.encode()).hexdigest()

    base_goal = dict(P.TASKS[task].goal({})); base_goal.update(version=1, time_limit_s=1e9)
    if task == 'race3d':
        from .battle import race_time_limit
        gates_xyz = tuple((g.north_m, g.east_m, g.alt_m) for g in course.gates)
        # The race task's own limit for this course (straight-line path at the task's pace, plus slack), as in
        # training; a race3d procedure may pace itself by it.
        base_goal.update(gates=[{'north_m': g.north_m, 'east_m': g.east_m, 'alt_m': g.alt_m} for g in course.gates],
                         gate_radius_m=course.gates[0].radius_m, time_limit_s=race_time_limit(gates_xyz))
    if max_speed_ms is not None:
        base_goal['max_speed_ms'] = max_speed_ms
    if max_vertical_ms is not None:
        base_goal['max_vertical_ms'] = max_vertical_ms
    P.HOST.update(root=out, speedup=speedup, gcs=gazebo, instance=instance, keep_simulators=True)
    sim = Sitl(out / 'simulator', 'copter', speedup, instance=instance, gcs=gazebo,
               params={'SIM_WIND_SPD': course.wind_ms, 'SIM_WIND_DIR': course.wind_from_deg, **(extra_params or {})},
               wall_limit_s=600.0, gazebo=gazebo, stream_hz=stream_hz)
    steps, gate_idx, reached, end_reason, confirmed, fault = [], 0, [], 'flew the course', {}, None
    # A hash-chained log of the flight: each record carries a digest of the one before, and the protected heads file
    # keeps every head, so a record edited, removed or added afterwards shows up when the log is verified.
    log = TrustedLog(out / 'flight.log', out / 'flight.heads', f'course-flight-{task}')
    log.append({'kind': 'flight_start', 'task': task, 'procedure_sha256': procedure_sha, 'procedure_source': source,
                'origin': origin, 'course': course.as_dict(), 'decision_period_s': dt, 'speedup': speedup,
                'pass_rule': pass_rule, 'goal': base_goal, 'autopilot_params': dict(extra_params or {}),
                'model_calls_possible': 0})
    no_procedure = 0   # steps no adopted procedure decided (the runner has no model to escalate to)
    overruns = 0       # decisions that finished after the next decision was due
    try:
        sim.prepare(alt_m=max(5.0, course.gates[0].alt_m))
        confirmed = {k: sim.params_seen.get(k) for k in (extra_params or {})}
        t0 = sim.state['t']; velocity = {'vn': 0.0, 've': 0.0, 'vd': 0.0}
        prev = None
        for step in range(int(round(1200 / dt))):
            g = course.gates[gate_idx]
            if task == 'race3d':
                goal, extra = base_goal, {'gates_passed': gate_idx}
            else:
                goal = {**base_goal, 'target_north_m': g.north_m, 'target_east_m': g.east_m, 'target_alt_m': g.alt_m}
                extra = {}
            seen_t = sim.state['position_t'] if sim.state['position_t'] is not None else sim.state['t']
            # ctx.t counts steps, as in the task pack's episodes (seconds = t * step_duration_s).
            ctx = {**_bundle(sim, step, dt), **extra, 'goal_version': 1, 'goal': goal}
            result = choose('control', ctx, library, needs=needs)
            sha = result.get('use')
            if not sha:
                no_procedure += 1
            if sha:
                velocity = {k: float(result['output'][k]) for k in ('vn', 've', 'vd')}
            sim.command_velocity(velocity['vn'], velocity['ve'], velocity['vd'])
            sim.drain(); lag = sim.state['t'] - seen_t
            if sim.state['t'] > t0 + (step + 1) * dt:
                overruns += 1
            sim.advance_to(t0 + (step + 1) * dt)
            # The simulator's truth; missing truth raises pack.MissingTruth and never falls back to the estimate (A1).
            real = P.truth(sim.state)
            tn, te, ta = real['north'], real['east'], -real['down']
            times = P.run_times(result.get('tried'))   # the procedure's and the guard's run times (A3)
            steps.append({'t': round(step * dt, 3), 'north_m': round(tn, 2), 'east_m': round(te, 2),
                          'alt_m': round(ta, 2), 'gate': gate_idx + 1, 'procedure': sha[:12] if sha else None,
                          'lag_s': round(lag, 3), 'truth_age_s': round(sim.state['t'] - sim.state['truth_t'], 3),
                          **times})
            log.append({'kind': 'step', 't': round(step * dt, 3), 'decided_by': sha, 'command': dict(velocity),
                        'observed': {k: ctx[k] for k in ('north_m', 'east_m', 'alt_m', 'vn_ms', 've_ms', 'vd_ms')},
                        'truth': steps[-1], 'lag_s': round(lag, 3), 'tried': result.get('tried', [])})
            pos = (tn, te, ta); prev = prev or pos
            # Times are when the position was read, at the end of the step (step + 1) * dt. Records before
            # 2 November 2026 labelled passes with the step's start, one decision period early.
            if pass_rule == 'path':
                centres = [(gg.north_m, gg.east_m, gg.alt_m) for gg in course.gates]
                n = P.passes_on_segment(prev, pos, centres, gate_idx, course.gates[gate_idx].radius_m)
                for k in range(gate_idx, gate_idx + n):
                    reached.append({'gate': k + 1, 't': round((step + 1) * dt, 3),
                                    'gap_m': round(P.segment_gap(prev, pos, centres[k]), 2)})
                gate_idx += n
            elif math.dist(pos, (g.north_m, g.east_m, g.alt_m)) <= g.radius_m:
                reached.append({'gate': gate_idx + 1, 't': round((step + 1) * dt, 3),
                                'gap_m': round(math.dist(pos, (g.north_m, g.east_m, g.alt_m)), 2)})
                gate_idx += 1
            prev = pos
            if gate_idx >= len(course.gates):
                break
            if math.hypot(tn, te) > course.fence_m or ta > C3.ALT_CAP_M + 5:
                end_reason = 'left the bounds'; break
            if course.building.inside(tn, te, ta, margin=0.0):
                end_reason = 'hit the building'; break
        else:
            end_reason = 'ran out of steps'
    except BaseException as exc:
        fault = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        sim.close()
        # On a fault the end record says so; no course3d-flight.json is written and the phase stops (section 7).
        log.append({'kind': 'flight_end', 'end_reason': 'fault' if fault else end_reason, 'fault': fault,
                    'gates_passed': len(reached), 'gates': len(course.gates),
                    'completed': fault is None and gate_idx >= len(course.gates), 'reached': reached,
                    'steps_without_procedure': no_procedure, 'control_steps': len(steps)})
        log.close()

    lags = sorted(x['lag_s'] for x in steps)
    record = {'seed': course.seed, 'gates': len(course.gates), 'gates_passed': len(reached),
              'completed': gate_idx >= len(course.gates), 'end_reason': end_reason,
              'provenance': {'procedure_sha256': procedure_sha, 'procedure_sha12': procedure_sha[:12],
                             'model_calls': 0, 'control_steps': len(steps),
                             'steps_without_procedure': no_procedure,
                             'decision_period_s': dt, 'speedup': speedup, 'overruns': overruns,
                             'lag_median_s': lags[len(lags) // 2] if lags else None,
                             'lag_max_s': lags[-1] if lags else None,
                             'goal_limits': {'max_speed_ms': base_goal.get('max_speed_ms'),
                                             'max_vertical_ms': base_goal.get('max_vertical_ms')},
                             'autopilot_params': dict(extra_params or {}),
                             'autopilot_params_confirmed': confirmed,
                             'task': task, 'pass_rule': pass_rule,
                             'flight_log_verified': verify(out / 'flight.log', out / 'flight.heads'),
                             'origin': origin, 'flown_in': 'gazebo' if gazebo else 'sitl'},
              'certification': C3.certify(course), 'course': course.as_dict(),
              'reached': reached, 'native_steps': steps}
    (out / 'course3d-flight.json').write_text(json.dumps(record, indent=1, default=str))
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--from-run', type=Path, required=True, help='a run with one adopted reach3d procedure')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--gazebo', action='store_true')
    p.add_argument('--speedup', type=float, default=10.0)
    p.add_argument('--instance', type=int, default=0)
    args = p.parse_args(argv)
    course = C3.generate(args.seed)
    cert = C3.certify(course)
    print(f"seed {args.seed}: {len(course.gates)} gates, certification: {cert['reason']} ({cert['seconds']}s)", flush=True)
    if not cert['certified']:
        print('course rejected by the feasibility check; not flying it.', flush=True); return 1
    source = battle.adopted_source(args.from_run)
    rec = fly_course(course, source, str(args.from_run), args.out, speedup=args.speedup, gazebo=args.gazebo,
                     instance=args.instance)
    print(f"{'completed' if rec['completed'] else rec['end_reason']}: passed {rec['gates_passed']} of {rec['gates']} "
          f"gates in 3D, procedure {rec['provenance']['procedure_sha12']}, model calls 0", flush=True)
    return 0 if rec['completed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

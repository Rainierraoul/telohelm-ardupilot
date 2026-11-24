"""Telohelm task packs for an ArduPilot copter: mission procedures above a real autopilot, in simulation.

Telohelm commands a velocity once a simulated second, and ArduPilot's guided mode flies it, as the fixed autopilot
flies paper 2's headings. The context holds the vehicle's raw state relative to home, with no derived features such
as the distance to a point; working those out is the procedure's job.

Each task (TASKS) is its own pack with its own goal, action fields, success and failure rules and learner text.
One Episode class serves them all: the scenario names its task, so a trial replays the same task.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import itertools
import math
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Callable

from telohelm.contracts import PublicContract, TaskPack
from telohelm.contracts.example_view import ExamplePolicy
from telohelm.contracts.decisions import DecisionRoles, HelpEvidence
from telohelm.contracts.goal_parts import GoalPart, GoalParts
from telohelm.runtime.environment import Environment

from .vehicle import MissingTruth, Sitl, TRUTH_FIELDS

TICK_S = 1.0
MAX_SPEED_MS = 5.0
MAX_VERTICAL_MS = 2.0
FENCE_M = 120.0
# The racing task flies faster, decides five times a second and lets ArduPilot climb, descend and accelerate harder.
# The autopilot settings are within ArduPilot's documented ranges (AC_WPNav.cpp); WP_SPD is already 10 m/s by default.
RACE_TICK_S = 0.2
RACE_MAX_SPEED_MS = 10.0
RACE_MAX_VERTICAL_MS = 3.0
RACE_GATE_RADIUS_M = 1.0
RACE_FENCE_M = 60.0
RACE_AUTOPILOT = (('WP_SPD_UP', 5.0), ('WP_SPD_DN', 3.0), ('WP_ACC', 5.0), ('WP_ACC_Z', 3.0))
READINGS = ('north_m', 'east_m', 'alt_m', 'vn_ms', 've_ms', 'vd_ms', 'heading_deg', 'battery_pct', 'battery_v',
            'gps_fix_type', 'gps_satellites', 'ekf_flags', 'threats')
EAST_DEG_PER_M = 1.0 / (111_319.5 * math.cos(math.radians(-35.363261)))
NORTH_DEG_PER_M = 1.0 / 111_319.5
# Host settings, outside the public contract. The driver sets root before the first episode.
HOST = dict(root=None, speedup=10.0, gcs=False, instance=0, keep_simulators=True)


@dataclass(frozen=True)
class Scenario:
    task: str
    episode_id: str
    params: tuple = ()           # ((name, value), ...) that place this scenario's goal
    wind_ms: float = 0.0
    wind_from_deg: float = 0.0
    # Timed events, each (kind, start, length_s, *values): ('jam', ...), ('spoof', ..., north_m, east_m),
    # ('rc_loss', ...), ('gust', ..., speed_ms, turbulence), ('motor', ..., multiplier),
    # ('threat', ..., north_m, east_m, radius_m). start is a second, or 'p0.3' for the step at which the mission
    # is 30% done (see Episode.progress), so a short mission is hit mid-way as a long one is, or, for a threat,
    # 'g19' for the first step that begins with the drone's true position within 19 m of the zone's edge (added
    # 2 November 2026: a progress trigger fires a step late, so the warning it leaves varies). See apply_events.
    events: tuple = ()


@dataclass(frozen=True)
class Task:
    """What makes one task: its goal, its action fields, how a step is judged, and what the learner reads."""
    name: str
    pack_id: str
    fields: tuple                                   # action fields of the control decision
    max_ticks: int
    success: str                                    # the end reason that meets the goal
    goal: Callable[[dict], dict]                    # scenario params -> goal (without version)
    judge: Callable[[dict, dict, dict], str | None]  # (state, goal, memory) -> end reason or None
    purpose: str
    actions: str
    goal_text: str
    failure_label: str
    ask: str
    tick_s: float = TICK_S                          # simulated seconds per step
    extra_readings: tuple = ()                      # readings beyond READINGS, from the episode's memory
    extra: Callable[[dict], dict] | None = None     # memory -> those readings
    autopilot_params: tuple = ()                    # ((name, value), ...) ArduPilot settings for this task
    stream_hz: int = 10                             # telemetry and truth rate
    start_alt_m: float = 10.0                       # take-off height before the first step


def off(s, n, e):
    return math.hypot(s['north'] - n, s['east'] - e)


def from_home(s):
    return math.hypot(s['north'], s['east'])


def judge_hold(s, g, m):
    m['held'] = m.get('held', 0) + 1 if off(s, g['target_north_m'], g['target_east_m']) <= g['radius_m'] else 0
    if 'zone_radius_m' in g and off(s, g['zone_north_m'], g['zone_east_m']) < g['zone_radius_m']:
        return 'entered_zone'
    return 'held' if m['held'] * TICK_S >= g['hold_s'] else None


def off3d(s, n, e, a):
    return math.hypot(s['north'] - n, s['east'] - e, (-s['down']) - a)


def judge_hold3d(s, g, m):
    m['held'] = m.get('held', 0) + 1 if off3d(s, g['target_north_m'], g['target_east_m'], g['target_alt_m']) <= g['radius_m'] else 0
    return 'held' if m['held'] * TICK_S >= g['hold_s'] else None


def segment_closest(a, b, p):
    """Where on the straight segment a-b point p is closest, as (t, distance): t runs 0 at a to 1 at b."""
    d = [b[i] - a[i] for i in range(3)]
    L2 = sum(x * x for x in d)
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, sum((p[i] - a[i]) * d[i] for i in range(3)) / L2))
    return t, math.dist([a[i] + t * d[i] for i in range(3)], p)


def segment_gap(a, b, p):
    """Closest distance from point p to the straight segment a-b, all (north, east, alt)."""
    return segment_closest(a, b, p)[1]


def passes_on_segment(a, b, gates, start, radius):
    """How many gates, from index start, the straight segment a-b passes in order: each gate's closest point on the
    segment must lie within radius of its centre and no earlier along the segment than the previous gate's.
    (Added 2 November 2026; before that, gates were counted within radius with no check on their order along the segment.)"""
    k, last_t = start, 0.0
    while k < len(gates):
        t, gap = segment_closest(a, b, gates[k])
        if gap > radius or t < last_t:
            break
        k, last_t = k + 1, t
    return k - start


def judge_race(tick_s):
    """Gates in order. A gate is passed when the path flown during a step comes within the gate radius of its centre,
    so a fast pass between two samples still counts. Several gates can be passed in one step, in order."""
    def judge(s, g, m):
        pos = (s['north'], s['east'], -s['down'])
        prev = tuple(m.get('prev', pos))
        m['ticks'] = m.get('ticks', 0) + 1
        passed, gates = m.get('passed', 0), g['gates']
        passed += passes_on_segment(prev, pos, [(x['north_m'], x['east_m'], x['alt_m']) for x in gates], passed,
                                    g['gate_radius_m'])
        m['passed'], m['prev'] = passed, list(pos)
        if passed == len(gates):
            return 'finished'
        if pos[2] < 0.3:
            return 'ground_contact'
        if m['ticks'] * tick_s > g['time_limit_s'] + 1e-9:
            return 'too_slow'
        return None
    return judge


def race_goal(p):
    """Gates arrive as ((north, east, alt), ...) in the scenario and reach procedures as records."""
    p = dict(p)
    gates = [{'north_m': n, 'east_m': e, 'alt_m': a} for n, e, a in p.pop('gates', ())]
    return {'gates': gates, 'gate_radius_m': RACE_GATE_RADIUS_M, 'fence_m': RACE_FENCE_M,
            'max_speed_ms': RACE_MAX_SPEED_MS, 'max_vertical_ms': RACE_MAX_VERTICAL_MS, 'time_limit_s': 30.0, **p}


def judge_orbit(s, g, m):
    rn, re_ = s['north'] - g['centre_north_m'], s['east'] - g['centre_east_m']
    r, angle = math.hypot(rn, re_), math.atan2(re_, rn)    # angle from north towards east
    inside = abs(r - g['orbit_radius_m']) <= g['tolerance_m']
    if m.get('captured') and not inside:
        return 'left_orbit'
    if inside:
        if m.get('captured'):
            step = (angle - m['angle'] + math.pi) % (2 * math.pi) - math.pi
            m['swept'] = m.get('swept', 0.0) + step          # clockwise seen from above counts up
        m['captured'], m['angle'] = True, angle
    return 'orbited' if m.get('swept', 0.0) >= 2 * math.pi * g['laps'] else None


def judge_land(s, g, m):
    if -s['down'] <= g['ground_alt_m']:
        if off(s, g['target_north_m'], g['target_east_m']) > g['radius_m']:
            return 'landed_off_point'
        if s['vd'] > g['touchdown_speed_ms']:
            return 'hard_landing'
        return 'landed'
    return None


def params_goal(**fixed):
    return lambda p: {**fixed, **p}


SHARED_GOAL = ('Positions and velocities are the autopilot\'s own estimate, in metres north and east of home; alt_m '
               'is metres above home. Each step is one simulated second, and the vehicle cannot stop instantly. Never '
               'go further than ctx.goal.fence_m from home. ctx.threats lists the threat zones active now, each with '
               'north_m, east_m and radius_m; entering one at any step fails the episode. gps_fix_type and '
               'gps_satellites come from the GPS receiver (MAVLink GPS_FIX_TYPE), ekf_flags is the autopilot\'s '
               'position-estimate status (MAVLink EKF_STATUS_FLAGS), battery_v is the battery voltage. If the '
               'autopilot leaves guided mode on its own, the episode fails. ')
HORIZONTAL = ('control returns {"vn": V, "ve": V}: the velocity in metres per second towards north and towards east. '
              'Numbers only; the total speed may be at most ctx.goal.max_speed_ms. The autopilot flies the commanded '
              'velocity and holds the altitude. ')

TASKS = {
    'reach': Task(
        'reach', 'ardupilot-reach-hold', ('vn', 've'), 90, 'held',
        params_goal(radius_m=2.0, hold_s=5, fence_m=FENCE_M, max_speed_ms=MAX_SPEED_MS, time_limit_s=90.0),
        judge_hold, 'fly a multirotor drone to a point and hold it there, by commanding its velocity', HORIZONTAL,
        SHARED_GOAL + 'Within ctx.goal.time_limit_s seconds, stay within ctx.goal.radius_m of the point '
        '(ctx.goal.target_north_m, ctx.goal.target_east_m) for ctx.goal.hold_s consecutive seconds. ',
        'did not reach and hold the point', 'Return {"vn": V, "ve": V} in metres per second.'),
    'reach3d': Task(
        'reach3d', 'ardupilot-reach3d-hold', ('vn', 've', 'vd'), 120, 'held',
        params_goal(radius_m=2.5, hold_s=3, fence_m=FENCE_M, max_speed_ms=MAX_SPEED_MS,
                    max_vertical_ms=MAX_VERTICAL_MS, time_limit_s=120.0),
        judge_hold3d, 'fly a multirotor drone to a point in three dimensions and hold it there, by commanding its velocity',
        'control returns {"vn": V, "ve": V, "vd": V}: the velocity in metres per second towards north, towards east and '
        'downwards (vd is positive when descending). Numbers only; the horizontal speed may be at most '
        'ctx.goal.max_speed_ms and the vertical speed at most ctx.goal.max_vertical_ms either way. ',
        SHARED_GOAL + 'Within ctx.goal.time_limit_s seconds, reach and hold the point (ctx.goal.target_north_m, '
        'ctx.goal.target_east_m, ctx.goal.target_alt_m) within ctx.goal.radius_m of it, in three dimensions, for '
        'ctx.goal.hold_s consecutive seconds. ',
        'did not reach and hold the 3D point', 'Return {"vn": V, "ve": V, "vd": V} in metres per second.'),
    'avoid': Task(
        'avoid', 'ardupilot-avoid-zone', ('vn', 've'), 120, 'held',
        params_goal(radius_m=2.0, hold_s=5, fence_m=FENCE_M, max_speed_ms=MAX_SPEED_MS, time_limit_s=120.0),
        judge_hold, 'fly a multirotor drone to a point around a no-go zone, by commanding its velocity',
        HORIZONTAL,
        SHARED_GOAL + 'A circular no-go zone of radius ctx.goal.zone_radius_m is centred on '
        '(ctx.goal.zone_north_m, ctx.goal.zone_east_m); entering it at any step fails the episode. Within '
        'ctx.goal.time_limit_s seconds, stay within ctx.goal.radius_m of the point (ctx.goal.target_north_m, '
        'ctx.goal.target_east_m) for ctx.goal.hold_s consecutive seconds. ',
        'did not reach and hold the point without entering the zone', 'Return {"vn": V, "ve": V} in metres per second.'),
    'orbit': Task(
        'orbit', 'ardupilot-orbit', ('vn', 've'), 150, 'orbited',
        params_goal(orbit_radius_m=20.0, tolerance_m=3.0, laps=1, fence_m=FENCE_M, max_speed_ms=MAX_SPEED_MS,
                    time_limit_s=150.0),
        judge_orbit, 'fly a multirotor drone round a point on a circle, by commanding its velocity', HORIZONTAL,
        SHARED_GOAL + 'Within ctx.goal.time_limit_s seconds, fly ctx.goal.laps full laps clockwise seen from above '
        '(north, then east, then south, then west of the centre) round the point (ctx.goal.centre_north_m, '
        'ctx.goal.centre_east_m), at a distance within ctx.goal.tolerance_m of ctx.goal.orbit_radius_m. Laps count '
        'from the first step inside that band, and leaving the band after that fails the episode. ',
        'did not complete the orbit', 'Return {"vn": V, "ve": V} in metres per second.'),
    'land': Task(
        'land', 'ardupilot-land', ('vn', 've', 'vd'), 120, 'landed',
        params_goal(radius_m=1.5, ground_alt_m=0.3, touchdown_speed_ms=1.0, fence_m=FENCE_M,
                    max_speed_ms=MAX_SPEED_MS, max_vertical_ms=MAX_VERTICAL_MS, time_limit_s=120.0),
        judge_land, 'land a multirotor drone on a point, by commanding its velocity',
        'control returns {"vn": V, "ve": V, "vd": V}: the velocity in metres per second towards north, towards east '
        'and downwards (vd is positive when descending). Numbers only; the horizontal speed may be at most '
        'ctx.goal.max_speed_ms and the vertical speed at most ctx.goal.max_vertical_ms either way. ',
        SHARED_GOAL + 'Within ctx.goal.time_limit_s seconds, come down to ctx.goal.ground_alt_m or lower within '
        'ctx.goal.radius_m of the point (ctx.goal.target_north_m, ctx.goal.target_east_m), descending no faster '
        'than ctx.goal.touchdown_speed_ms at that moment. Coming down anywhere else, or faster, fails the episode. ',
        'did not land on the point gently', 'Return {"vn": V, "ve": V, "vd": V} in metres per second.'),
    'race3d': Task(
        'race3d', 'ardupilot-race3d', ('vn', 've', 'vd'), int(120 / RACE_TICK_S), 'finished',
        race_goal, judge_race(RACE_TICK_S),
        'fly a multirotor drone through a sequence of gates in three dimensions as fast as possible, by commanding '
        'its velocity',
        'control returns {"vn": V, "ve": V, "vd": V}: the velocity in metres per second towards north, towards east and '
        'downwards (vd is positive when descending). Numbers only; the horizontal speed may be at most '
        'ctx.goal.max_speed_ms and the vertical speed at most ctx.goal.max_vertical_ms either way. ',
        SHARED_GOAL.replace('Each step is one simulated second', 'Each step lasts ctx.step_duration_s simulated '
                            'seconds') +
        'ctx.goal.gates lists the gates in the order they must be passed, each with north_m, east_m and alt_m. A gate '
        'is passed when the path the drone flies comes within ctx.goal.gate_radius_m of that point; there is no need '
        'to stop or hold at a gate. ctx.gates_passed is how many gates have been passed so far, so while gates remain '
        'the next one is ctx.goal.gates[ctx.gates_passed]. Pass every gate, in order, within ctx.goal.time_limit_s '
        'seconds. Touching the ground fails the episode. ',
        'did not pass every gate in order within the time limit',
        'Return {"vn": V, "ve": V, "vd": V} in metres per second.',
        tick_s=RACE_TICK_S, extra_readings=('gates_passed',), extra=lambda m: {'gates_passed': m.get('passed', 0)},
        autopilot_params=RACE_AUTOPILOT, stream_hz=50, start_alt_m=3.0),
}


def part_error_for(task):
    limits = task.goal({})
    top, vertical = limits.get('max_speed_ms', MAX_SPEED_MS), limits.get('max_vertical_ms', MAX_VERTICAL_MS)

    def part_error(part):
        values = [part.get(f) for f in task.fields]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            return ' and '.join(task.fields) + ' must be finite numbers'
        if math.hypot(part['vn'], part['ve']) > top + 1e-9:
            return f'horizontal speed must be at most {top:g} m/s'
        if 'vd' in task.fields and abs(part['vd']) > vertical + 1e-9:
            return f'vertical speed must be at most {vertical:g} m/s'
        return None
    return part_error


def guard_for(task):
    """The designer-supplied format and limit check for a task's control decision, as library source."""
    vertical = ("    if abs(out.vd) > ctx.goal.max_vertical_ms + 1e-9:\n        return 'reject'\n"
                if 'vd' in task.fields else '')
    return ("def check(ctx, out):\n    try:\n        values = [" + ', '.join(f'out.{f}' for f in task.fields) + "]\n"
            "    except Exception:\n        return 'reject'\n    for v in values:\n"
            "        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) == float('inf'):\n"
            "            return 'reject'\n"
            "    if (out.vn * out.vn + out.ve * out.ve) ** 0.5 > ctx.goal.max_speed_ms + 1e-9:\n"
            "        return 'reject'\n" + vertical + "    return 'accept'\n")


def apply_events(sim, t, events, threats, base_wind_ms=0.0, starts=None):
    """Start, update and end this second's events. starts gives the second each progress-triggered event began;
    one not yet triggered is skipped. Returns the events that changed state, for the record."""
    changed = []
    for index, event in enumerate(events):
        kind, start, length = event[0], (starts or {}).get(index, event[1]), event[2]
        if isinstance(start, str):
            continue
        end = start + length
        if not start <= t <= end:
            continue
        first, last = t == start, t == end
        if kind == 'jam' and (first or last):
            sim.set_param('SIM_GPS1_JAM', 0 if last else 1)
        elif kind == 'spoof':
            # Drag the reported position to the offset over half the window, hold it, then release.
            share = 0.0 if last else min(1.0, (t - start) / max(1.0, length / 2))
            sim.set_param('SIM_GPS1_GLTCH_X', event[3] * share * NORTH_DEG_PER_M)
            sim.set_param('SIM_GPS1_GLTCH_Y', event[4] * share * EAST_DEG_PER_M)
        elif kind == 'rc_loss' and (first or last):
            sim.set_param('SIM_RC_FAIL', 0 if last else 1)
        elif kind == 'gust' and (first or last):
            sim.set_param('SIM_WIND_SPD', base_wind_ms if last else event[3])
            sim.set_param('SIM_WIND_TURB', 0 if last else event[4])
        elif kind == 'motor' and (first or last):
            sim.set_param('SIM_ENGINE_MUL', event[3])
            sim.set_param('SIM_ENGINE_FAIL', 0 if last else 1)
        elif kind == 'threat' and (first or last):
            zone = {'north_m': event[3], 'east_m': event[4], 'radius_m': event[5]}
            if first:
                threats.append(zone)
            elif zone in threats:
                threats.remove(zone)
        else:
            continue
        changed.append({'t': t, 'kind': kind, 'phase': 'start' if first else 'end' if last else 'update'})
    return changed


def run_times(tried) -> dict:
    """Run times of one decision from the chooser's attempts (result['tried'], or a decision log record's 'tried'):
    wall-clock and processor seconds of the procedures, and separately of the checks (the guard), summed over the
    attempts at that step (A3 of Codex's review, 3 November 2026). None where nothing ran."""
    tried = tried or []
    checks = [c for a in tried for c in a.get('checks') or []]
    total = lambda xs, k: round(sum(x[k] for x in xs), 6) if xs and all(x.get(k) is not None for x in xs) else None
    return {'procedure_wall_s': total(tried, 'wall_seconds'), 'procedure_cpu_s': total(tried, 'cpu_seconds'),
            'guard_wall_s': total(checks, 'wall_seconds'), 'guard_cpu_s': total(checks, 'cpu_seconds'),
            'attempts': len(tried)}


def truth(s):
    """The simulator's true position, altitude and velocity in place of the autopilot's estimate, for judging only.
    Every true field must be present. A missing one raises MissingTruth and is never replaced by the estimate (A1 of
    Codex's review, 3 November 2026; before then the touchdown-speed test read the estimated vertical speed and a
    missing true position fell back to the estimate)."""
    missing = [k for k in TRUTH_FIELDS if s.get(k) is None]
    if missing:
        raise MissingTruth(f"simulator truth missing at simulated time {s.get('t')}: {', '.join(missing)}")
    view = dict(s)
    view.update(north=s['true_north'], east=s['true_east'], down=-s['true_alt'],
                vn=s['true_vn'], ve=s['true_ve'], vd=s['true_vd'])
    return view


class ContextBuilder:
    def __init__(self, briefing):
        self.goal = dict(briefing['goal'])

    def update(self, bundle):
        # Copy the native readings without selecting or deriving features.
        return {**bundle, 'goal_version': 1, 'goal': dict(self.goal)}


class Episode:
    """One episode, with its own simulator. The task's judge decides each step whether the episode has ended; leaving
    the fence, losing guided flight or reaching the time limit also end it, with failure."""
    _serial = itertools.count()

    def __init__(self, scenario):
        if HOST['root'] is None:
            raise RuntimeError('Set pack.HOST["root"] to a run folder before creating episodes')
        self.task = TASKS[scenario.task]
        self.scenario, self.goal = scenario, {'version': 1, **self.task.goal(dict(scenario.params))}
        self.folder = Path(HOST['root']) / 'simulators' / f'{scenario.episode_id}-{os.getpid()}-{next(self._serial):03d}'
        self.sim = None
        self.t, self.end_reason, self.memory = 0, None, {}
        self.threats, self.event_log, self.closest_threat_m = [], [], None
        self.progress, self.starts, self.initial_distance = 0.0, {}, None
        self.last_truth = None     # true position at the end of the last step, for 'g' event triggers
        self.velocity = {f: 0.0 for f in self.task.fields}         # hold still until a procedure acts
        self.record = SimpleNamespace(actions=[])
        self.refusals, self.native_steps = [], []
        self.part_error = part_error_for(self.task)
        self.tick = self.task.tick_s
        # Hooks for flying the same scenario under ArduPilot's own modes (autopilot_modes.py): which flight modes
        # count as staying in control, and how each step's command reaches the autopilot. Defaults: guided velocity.
        self.allowed_modes = frozenset({'GUIDED'})

    def _bundle(self):
        s = self.sim.state
        return {'t': self.t, 'north_m': round(s['north'], 3), 'east_m': round(s['east'], 3),
                'alt_m': round(-s['down'], 3), 'vn_ms': round(s['vn'], 3), 've_ms': round(s['ve'], 3),
                'vd_ms': round(s['vd'], 3), 'heading_deg': round(s['heading_deg'] or 0.0, 1),
                'battery_pct': s['battery_pct'] if s['battery_pct'] is not None else -1,
                'battery_v': round(s['battery_v'], 2) if s['battery_v'] is not None else -1,
                'gps_fix_type': s['gps_fix'] if s['gps_fix'] is not None else -1,
                'gps_satellites': s['gps_sats'] if s['gps_sats'] is not None else -1,
                'ekf_flags': s['ekf_flags'] if s['ekf_flags'] is not None else -1,
                'threats': [dict(z) for z in self.threats],
                'observation_age_s': round(max(0.0, s['t'] - s['position_t']), 3), 'step_duration_s': self.tick,
                **(self.task.extra(self.memory) if self.task.extra else {})}

    def reset(self):
        if self.sim is not None:
            raise RuntimeError('Create another episode rather than reusing this one')
        params = {'SIM_WIND_SPD': self.scenario.wind_ms, 'SIM_WIND_DIR': self.scenario.wind_from_deg,
                  **dict(self.task.autopilot_params), **getattr(self, 'extra_autopilot_params', {})}
        self.sim = Sitl(self.folder, 'copter', HOST['speedup'], instance=HOST['instance'], gcs=HOST['gcs'],
                        params=params, stream_hz=self.task.stream_hz)
        try:
            self.sim.prepare(alt_m=self.task.start_alt_m)
        except Exception:
            self.sim.close()
            raise
        self.t0 = self.sim.state['t']
        self.last_truth = truth(self.sim.state)   # so a 'g' trigger can fire before the first step
        return {'briefing': {'goal': dict(self.goal), 'fallback': dict(self.velocity), 'step_duration_s': self.tick},
                'bundle': self._bundle()}

    def step(self, action):
        if self.end_reason is not None:
            raise RuntimeError('The episode has ended')
        for index, event in enumerate(self.scenario.events):
            if isinstance(event[1], str) and index not in self.starts:
                due = self.t >= self.task.max_ticks // 2
                if event[1][0] == 'p':
                    due = due or self.progress >= float(event[1][1:])
                elif event[1][0] == 'g':      # a threat zone, by the true distance to its edge
                    due = due or (self.last_truth is not None and
                                  off(self.last_truth, event[3], event[4]) - event[5] <= float(event[1][1:]))
                if due:
                    self.starts[index] = self.t
        self.event_log += apply_events(self.sim, self.t, self.scenario.events, self.threats, self.scenario.wind_ms,
                                       self.starts)
        accepted = (not action or (set(action) <= {*self.task.fields, 'goal_version'}
                    and self.part_error(action) is None and action.get('goal_version', 1) == 1))
        if accepted and action:
            self.velocity = {f: float(action[f]) for f in self.task.fields}
        elif not accepted:
            self.refusals.append({'t': self.t, 'reason': 'invalid velocity command'})
        # Simulated time that passed while Telohelm decided, from the observation to the command.
        self.sim.drain()
        lag = round(self.sim.state['t'] - (self.t0 + self.t * self.tick), 3)
        self.send_command()
        self.sim.advance_to(self.t0 + (self.t + 1) * self.tick)
        self.record.actions.append({'actions': dict(action), 'accepted': accepted})
        self.t += 1
        s = self.sim.state
        real = truth(s)
        # Safety first: a threat zone, then the autopilot taking over, then the task's own rules.
        for zone in self.threats:
            gap = off(real, zone['north_m'], zone['east_m']) - zone['radius_m']
            self.closest_threat_m = gap if self.closest_threat_m is None else min(self.closest_threat_m, gap)
        if any(off(real, z['north_m'], z['east_m']) < z['radius_m'] for z in self.threats):
            self.end_reason = 'entered_threat'
        elif not s['armed']:
            self.end_reason = 'disarmed'
        elif s['mode'] not in self.allowed_modes:
            self.end_reason = f"autopilot_{str(s['mode']).lower()}"
        else:
            self.end_reason = self.task.judge(real, self.goal, self.memory)
        self.progress = max(self.progress, self.measure_progress(real))
        self.last_truth = real
        if self.end_reason is None:
            if from_home(real) > self.goal['fence_m']:
                self.end_reason = 'left_fence'
            elif 'vd' not in self.task.fields and -real['down'] < 0.5:
                self.end_reason = 'ground_contact'
            elif self.t >= self.task.max_ticks:
                self.end_reason = 'timed_out'
        self.native_steps.append({'t': self.t, 'sim_s': round(s['t'] - self.t0, 3), 'velocity_applied': self.velocity,
                                  'decision_lag_s': lag, 'north_m': round(real['north'], 3),
                                  'east_m': round(real['east'], 3), 'alt_m': round(-real['down'], 3),
                                  'estimate_error_m': round(off(s, real['north'], real['east']), 2),
                                  'vd_ms': round(s['vd'], 3), 'true_vd_ms': round(real['vd'], 3),
                                  'truth_age_s': round(s['t'] - s['truth_t'], 3),
                                  'mode': s['mode'], 'ekf_flags': s['ekf_flags'],
                                  'threats': len(self.threats), 'memory': dict(self.memory)})
        if self.end_reason is not None:
            self.sim.close()
            return None
        return self._bundle()

    def send_command(self):
        self.sim.command_velocity(self.velocity['vn'], self.velocity['ve'], self.velocity.get('vd', 0.0))

    def measure_progress(self, real):
        """How much of the mission is done, 0 to 1, from the truth: the share of the way to the point, or of the
        laps flown."""
        g = self.goal
        if 'gates' in g:
            return self.memory.get('passed', 0) / max(1, len(g['gates']))
        if 'laps' in g:
            return min(1.0, self.memory.get('swept', 0.0) / (2 * math.pi * g['laps']))
        distance = off(real, g['target_north_m'], g['target_east_m'])
        if self.initial_distance is None:
            self.initial_distance = max(distance, 1.0)
        return max(0.0, min(1.0, 1.0 - distance / self.initial_distance))

    def outcome(self):
        if self.sim is not None:
            self.sim.close()
            if not HOST['keep_simulators']:
                shutil.rmtree(self.folder, ignore_errors=True)
        met = self.end_reason == self.task.success
        return {'task': self.task.name, 'goal_met': met, self.task.success: met, 'settled': True, 'model_calls': 0,
                'end_reason': self.end_reason, 'ended_at': self.t, 'action_steps': len(self.record.actions),
                'alternatives': [], 'goal': dict(self.goal), 'help_requests': [], 'refusals': list(self.refusals),
                'events': [list(e) for e in self.scenario.events], 'event_log': list(self.event_log),
                'event_starts': {str(k): v for k, v in self.starts.items()},
                'closest_threat_m': round(self.closest_threat_m, 2) if self.closest_threat_m is not None else None,
                'native_steps': list(self.native_steps),
                'simulator': {'folder': str(self.folder), 'command': self.sim.command if self.sim else None,
                              'messages': self.sim.texts[-20:] if self.sim else []}}


def component_trial(decision, sha, outcome, records):
    task = TASKS[outcome['task']]
    part_error = part_error_for(task)
    refused = {r['t'] for r in outcome.get('refusals', [])}
    used = [r for r in records if r.get('decision') == decision == 'control'
            and r.get('method') == sha and r.get('goal_version') == 1
            and part_error(r.get('part') or {}) is None and r['t'] not in refused]
    steps = outcome.get('action_steps') or 0
    passed = bool(sha and steps and {r['t'] for r in used} == set(range(steps))
                  and outcome.get('goal_met') is True and outcome.get('end_reason') == task.success
                  and not outcome.get('refusals') and not outcome.get('help_requests'))
    return {'passed': passed, 'candidate': sha, 'used_steps': len(used),
            'reason': None if passed else f'{task.failure_label} with accepted candidate control'}


EXAMPLE_RULES = ('examples: moments from your own completed episodes, failures first (newest episode first), then one '
                 'episode that met the goal. Each names its episode by the same opaque name as feedback and gives the '
                 'second and the context your procedures saw at that second. Its positions are the autopilot\'s '
                 'estimate, which can be wrong. submitted is the action sent that second and the method that issued '
                 'it; applied says whether it was accepted; ended_by, on an episode\'s last moment, says how the '
                 'episode ended. outcome is the result as fed back. No example says whether its action was right.')


def example_points(decisions, failed, outcome, goal):
    """Three moments of an episode: halfway, three-quarters of the way through, and the last."""
    seconds = sorted({p['t'] for p in decisions})
    picks = {seconds[len(seconds) // 2], seconds[3 * len(seconds) // 4], seconds[-1]}
    return sorted(picks), []


def example_project(context):
    return dict(context), {}


def example_details(t, outcome, actions, sources, steps, goal_changes):
    return {'ended_by': outcome['end_reason']} if t == outcome.get('ended_at', 0) - 1 else {}


EXAMPLES = ExamplePolicy(EXAMPLE_RULES, example_points, example_project, example_details)


def tools_text(limits):
    return 'No tools are available. Read the named observations directly.'


def make_pack(task: Task) -> TaskPack:
    public = PublicContract(
        pack_id=task.pack_id, schema_version=1, decisions=('control',),
        decision_fields={'control': frozenset(task.fields)}, pair_decisions=(),
        context_fields=frozenset({'t', 'goal_version', 'goal', 'observation_age_s', 'step_duration_s', *READINGS,
                                  *task.extra_readings}),
        output_fields=frozenset(task.fields),
        learner_purpose=task.purpose, learner_actions=task.actions, learner_goal=task.goal_text,
        learner_tools=tools_text,
        learner_trial_rule='control procedure must act at every step and meet the goal without refusals or help.',
        learner_attribute_example='ctx.north_m and ctx.goal.fence_m in a procedure, and out.vn in a check',
        learner_decision_choices='"control"',
        flight_system=f'Choose the velocity that will {task.purpose.split(", by")[0]}.',
        flight_ask={'control': task.ask})
    return TaskPack(
        public=public, goal=GoalParts((GoalPart(task.success, task.failure_label, {'control'}),), 'not_met'),
        roles=DecisionRoles(('control',), 'control', (), {'control': READINGS + task.extra_readings}),
        help=HelpEvidence('observation_age_s', 1.0, 'The vehicle state is stale.'),
        part_error=part_error_for(task), context_builder=ContextBuilder, example_policy=EXAMPLES,
        environment=Environment(public.pack_id, public.schema_version, Episode, component_trial, task.max_ticks,
                                tools={}))


PACKS = {name: make_pack(task) for name, task in TASKS.items()}
GUARDS = {name: guard_for(task) for name, task in TASKS.items()}

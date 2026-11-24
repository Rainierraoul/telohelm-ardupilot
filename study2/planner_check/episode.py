"""One planner flight: the study's episode, with ArduPilot's own planner doing the flying (design sections 3, 4 and 6).

The planner gets what a procedure gets, at the same moment. It is given the goal once, at the first command stamp. It is
given a zone as an exclusion circle in the autopilot's fence, at the first command after the observation that first
lists the zone. Everything that decides how a flight ends comes from the study's own `Episode` in ardupilot/pack.py:
the step, the zone switch-on, the judge on the simulator's true state, and the outcome. This file defines none of them.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from pymavlink import mavutil

from ardupilot import pack as P
from ardupilot.vehicle import ARDUPILOT, HOME, M_PER_DEG_LAT, MODELS, Sitl

from . import settings as S

HOST, truth = P.HOST, P.truth      # the names `Episode.reset` uses, so that PlannerEpisode.reset can read the same

if mavutil.mavlink.WIRE_PROTOCOL_VERSION != '2.0':     # a fence upload needs it; see this package's __init__
    raise ImportError('MAVLink 2 is not active: import planner_check before any module that loads pymavlink')

LAND_WITHIN_M = 0.5                  # the comparator's rule (ardupilot/autopilot_modes.py): within 0.5 m, switch to LAND
FENCE = mavutil.mavlink.MAV_MISSION_TYPE_FENCE
FENCE_CIRCLE_EXCLUSION = mavutil.mavlink.MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION
ACCEPTED = mavutil.mavlink.MAV_MISSION_ACCEPTED
READ_BACK_SIM_LIMIT_S = 10.0         # simulated seconds allowed for each try of the parameter read-back
PRELOAD_SIM_LIMIT_S = 10.0           # simulated seconds allowed for the fallback's fence upload before take-off
ROUTES = ('midflight', 'preloaded')  # how the zone reaches the autopilot: loaded in flight, or loaded before and enabled in flight


class PlannerFault(RuntimeError):
    """A flight that cannot be judged as a flight of the check: a parameter that reads back wrong, or a fence upload
    that was not acknowledged before the end of its step. The flight is kept apart and flown again (design section 6)."""


def zone_latlon(north_m: float, east_m: float) -> tuple:
    """A point given as metres north and east of home, as latitude and longitude, with the study's own constants."""
    lat = HOME[0] + north_m / M_PER_DEG_LAT
    lon = HOME[1] + east_m / (M_PER_DEG_LAT * math.cos(math.radians(HOME[0])))
    return lat, lon


def latlon_zone(lat_e7: int, lon_e7: int) -> tuple:
    """The reverse of zone_latlon, from the whole numbers (degrees times 10 million) sent to the autopilot."""
    north = (lat_e7 / 1e7 - HOME[0]) * M_PER_DEG_LAT
    east = (lon_e7 / 1e7 - HOME[1]) * M_PER_DEG_LAT * math.cos(math.radians(HOME[0]))
    return north, east


class PlannerSitl(Sitl):
    """The study's simulator, started with the setting's defaults file as well, and able to read parameters back and to
    load exclusion circles into the fence during flight.

    Sitl builds its start command inside its constructor, so the constructor is repeated here with one change: the
    setting's defaults file is added to the end of `--defaults`. A test shows the two commands differ only there."""

    def __init__(self, folder: Path, defaults_file: Path, expect: dict, vehicle: str = 'copter', speedup: float = 10.0,
                 instance: int = 0, gcs: bool = False, params: dict | None = None, wall_limit_s: float = 120.0,
                 stream_hz: int = 10, absent: tuple = (), preload: list | None = None):
        binary, model, defaults = MODELS[vehicle]
        self.folder, self.vehicle, self.speedup, self.gazebo = Path(folder), vehicle, speedup, False
        self.wall_limit_s = wall_limit_s
        self.folder.mkdir(parents=True)
        self.expect, self.absent = dict(expect), tuple(absent)
        self.preload = list(preload) if preload else None      # the fallback: circles loaded before take-off
        default_files = [str(ARDUPILOT / 'Tools' / 'autotest' / 'default_params' / defaults), str(defaults_file)]
        self.command = [str(ARDUPILOT / 'build' / 'sitl' / 'bin' / binary), '--model', model,
                        '--speedup', str(speedup), '--wipe', '--instance', str(instance),
                        '--home', ','.join(str(x) for x in HOME),
                        '--defaults', ','.join(default_files)]
        if gcs:
            self.command += ['--serial1', f'udpclient:127.0.0.1:{14550 + 10 * instance}']
        self._log = open(self.folder / 'sitl.log', 'w')
        self.process = subprocess.Popen(self.command, cwd=self.folder, stdout=self._log, stderr=subprocess.STDOUT)
        self.state = dict(t=0.0, position_t=None, north=None, east=None, down=None, vn=None, ve=None, vd=None,
                          heading_deg=None, battery_pct=None, battery_v=None, gps_fix=None, gps_sats=None,
                          ekf_flags=None, true_north=None, true_east=None, true_alt=None, true_vn=None,
                          true_ve=None, true_vd=None, truth_t=None, armed=False, mode=None)
        self.texts: list[dict] = []
        self.params_seen: dict[str, float] = {}
        self.read_back_values: dict[str, float] | None = None
        self.read_back_absent: dict[str, str] | None = None   # names expected not to exist: 'absent', 'present' or 'no answer'
        self.params_absent: set = set()      # names the autopilot answered "does not exist"
        self._acks: list = []                # command acknowledgements seen
        self.fence_enabled_record: dict | None = None
        self.sensors_enabled = 0             # SYS_STATUS onboard_control_sensors_enabled, last seen
        self.preload_record: dict | None = None
        self._mission_events: list = []     # fence-upload messages seen, handled by upload_exclusion_circles
        try:
            self.conn = self._connect(5760 + 10 * instance)
            self.conn.mav.request_data_stream_send(self.conn.target_system, self.conn.target_component,
                                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, stream_hz, 1)
            self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component,
                                            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                            mavutil.mavlink.MAVLINK_MSG_ID_SIM_STATE, int(1e6 / stream_hz), 0, 0, 0, 0, 0)
            for name, value in (params or {}).items():
                self.conn.mav.param_set_send(self.conn.target_system, self.conn.target_component, name.encode(),
                                             float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        except Exception:
            self.close()
            raise

    def _handle(self, msg):
        """The study's handling of every message; the fence-upload messages are also kept for the upload."""
        if msg.get_type() in ('MISSION_REQUEST', 'MISSION_REQUEST_INT', 'MISSION_ACK'):
            self._mission_events.append(msg)
        elif msg.get_type() == 'PARAM_ERROR':
            name = msg.param_id.decode() if isinstance(msg.param_id, bytes) else msg.param_id
            self.params_absent.add(name.rstrip('\x00'))
        elif msg.get_type() == 'SYS_STATUS':
            self.sensors_enabled = msg.onboard_control_sensors_enabled
        elif msg.get_type() == 'COMMAND_ACK':
            self._acks.append(msg)
        super()._handle(msg)

    def read_back(self) -> dict:
        """Ask the autopilot for every parameter in `expect` and check each value. Raises PlannerFault if one is missing
        or differs from the setting's value. The values read are kept in `read_back_values`. A name still missing after
        one try is asked for again once, because the autopilot keeps only 20 requests at a time and drops the rest. The
        names in `absent` (BendyRuler's, when BendyRuler is not in use) are asked for too, and the answer is kept in
        `read_back_absent`; an absent name that is not answered is not a fault."""
        self.params_absent.clear()
        names = list(self.expect)
        for name in (*names, *self.absent):
            self.params_seen.pop(name, None)
        for batch in (names, None):
            for name in (batch if batch is not None else [n for n in names if n not in self.params_seen]):
                self.conn.mav.param_request_read_send(self.conn.target_system, self.conn.target_component,
                                                      name.encode(), -1)
            self.wait(lambda: all(n in self.params_seen for n in names), READ_BACK_SIM_LIMIT_S)
            if all(n in self.params_seen for n in names):
                break
        for name in self.absent:
            self.conn.mav.param_request_read_send(self.conn.target_system, self.conn.target_component,
                                                  name.encode(), -1)
        if self.absent:
            self.wait(lambda: all(n in self.params_seen or n in self.params_absent for n in self.absent),
                      READ_BACK_SIM_LIMIT_S)
        self.read_back_absent = {n: 'present' if n in self.params_seen else 'absent' if n in self.params_absent
                                 else 'no answer' for n in self.absent}
        got = {name: self.params_seen.get(name) for name in self.expect}
        self.read_back_values = got
        wrong = {name: (want, got[name]) for name, want in self.expect.items()
                 if got[name] is None or abs(got[name] - want) > 1e-4 * max(1.0, abs(want))}
        if wrong:
            raise PlannerFault('parameters read back wrong (name: wanted, read): '
                               + '; '.join(f'{k}: {w}, {g}' for k, (w, g) in sorted(wrong.items())))
        return got

    def prepare(self, alt_m: float = 10.0):
        """The study's preparation, with the parameter read-back first: the read-back is made before take-off. In the
        fallback route the fence is loaded here too, still switched off."""
        self.read_back()
        if self.preload:
            self.preload_record = self.upload_exclusion_circles(self.preload, self.state['t'] + PRELOAD_SIM_LIMIT_S)
        super().prepare(alt_m)

    def geofence_enabled(self) -> bool:
        return bool(self.sensors_enabled & mavutil.mavlink.MAV_SYS_STATUS_GEOFENCE)

    def enable_fence(self, deadline_t: float) -> dict:
        """The fallback's moment of truth: switch the fence on with MAV_CMD_DO_FENCE_ENABLE, wait for the acknowledgement
        by simulated time deadline_t, then see the geofence bit in SYS_STATUS. Raises PlannerFault if it fails."""
        command = mavutil.mavlink.MAV_CMD_DO_FENCE_ENABLE
        self._acks.clear()
        started = self.state['t']
        self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component, command, 0, 1, 0, 0, 0, 0, 0, 0)
        got = {}

        def acknowledged() -> bool:
            for msg in self._acks:
                if msg.command == command:
                    got['result'], got['t'] = msg.result, self.state['t']
                    return True
            return False

        arrived = self.wait(acknowledged, max(0.0, deadline_t - started))
        if not arrived or got['t'] > deadline_t:
            raise PlannerFault(f'the fence enable was not acknowledged before the end of its step (sent at {started:.3f} s)')
        if got['result'] != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            raise PlannerFault(f'the autopilot did not accept the fence enable (result {got["result"]})')
        # FENCE_ENABLE does not change: the command sets only the autopilot's in-memory mask of enabled fences. The
        # autopilot reports that mask in SYS_STATUS, as the geofence bit of the enabled sensors, so that is what is read.
        # It must show before the end of the step.
        seen = self.wait(lambda: self.geofence_enabled(), max(0.0, deadline_t - self.state['t']))
        if not seen or self.state['t'] > deadline_t:
            raise PlannerFault('SYS_STATUS did not show the geofence enabled before the end of the step '
                               f'(enable sent at {started:.3f} s, deadline {deadline_t:.3f} s)')
        self.fence_enabled_record = {'sent_t': started, 'acknowledged_t': got['t'], 'deadline_t': deadline_t,
                                     'geofence_bit_seen_t': self.state['t']}
        return self.fence_enabled_record

    def upload_exclusion_circles(self, circles: list, deadline_t: float) -> dict:
        """Replace the autopilot's fence items with these exclusion circles, each (north_m, east_m, radius_m), using
        the mission protocol with mission type FENCE, and wait for the autopilot's acknowledgement. Every other message
        that arrives while waiting goes to the study's own handling, so the state stays current. The acknowledgement must
        arrive by simulated time deadline_t, the end of the step, or PlannerFault is raised. Returns the simulated times
        at which the upload started and was acknowledged, and the items sent."""
        if not circles:
            raise ValueError('nothing to upload')
        items = []
        for north, east, radius in circles:
            lat, lon = zone_latlon(north, east)
            items.append((round(lat * 1e7), round(lon * 1e7), float(radius)))
        mav, ts, tc = self.conn.mav, self.conn.target_system, self.conn.target_component
        self._mission_events.clear()
        started = self.state['t']
        mav.mission_count_send(ts, tc, len(items), FENCE)
        outcome = {}

        def finished() -> bool:
            while self._mission_events:
                msg = self._mission_events.pop(0)
                if getattr(msg, 'mission_type', FENCE) != FENCE:
                    continue
                if msg.get_type() == 'MISSION_ACK':
                    outcome['ack'] = msg.type
                    outcome['t'] = self.state['t']
                    return True
                lat_e7, lon_e7, radius = items[msg.seq]
                mav.mission_item_int_send(ts, tc, msg.seq, mavutil.mavlink.MAV_FRAME_GLOBAL, FENCE_CIRCLE_EXCLUSION,
                                          0, 0, radius, 0, 0, 0, lat_e7, lon_e7, 0.0, FENCE)
            return False

        arrived = self.wait(finished, max(0.0, deadline_t - started))
        if not arrived or outcome['t'] > deadline_t:
            raise PlannerFault(f'the fence upload was not acknowledged before the end of its step (started at '
                               f'{started:.3f} s, deadline {deadline_t:.3f} s, acknowledged at {outcome.get("t")})')
        if outcome['ack'] != ACCEPTED:
            raise PlannerFault(f'the autopilot did not accept the fence upload (MISSION_ACK type {outcome["ack"]})')
        return {'started_t': started, 'acknowledged_t': outcome['t'], 'deadline_t': deadline_t,
                'items': [{'lat_e7': a, 'lon_e7': b, 'radius_m': r} for a, b, r in items]}


def make_sim(*args, **kwargs):
    """Start a PlannerSitl. A name of its own so that a test can put a stand-in simulator in its place."""
    return PlannerSitl(*args, **kwargs)


class PlannerEpisode(P.Episode):
    """The study's episode, flown by ArduPilot's own planner. Only two things differ from `Episode`: how the simulator is
    started (with the setting's defaults file) and how each step's command reaches the autopilot (`send_command`).

    route 'midflight' (the design's own) loads the zone into the fence when a procedure's first command could react to it.
    route 'preloaded' is the fallback of design section 4: the zone's circle is loaded before take-off with the fence
    switched off, and the fence is switched on at that same moment. It is used only if the shake-down shows that the
    autopilot will not take a fence in flight."""

    def __init__(self, scenario, setting: S.Setting, defaults_file: Path, route: str = 'midflight'):
        super().__init__(scenario)
        if route not in ROUTES:
            raise ValueError(f'route must be one of {ROUTES}')
        self.setting, self.defaults_file, self.route = setting, Path(defaults_file), route
        self.extra_autopilot_params = dict(S.LIMITS)
        if self.task.name == 'land':
            self.allowed_modes = frozenset({'GUIDED', 'LAND'})
        self.stage = 'approach'
        self.hold_alt = None
        self.listed: list = []          # the zones the last observation listed
        self.uploaded: list = []        # the zones loaded into the fence so far, in the order loaded
        self.uploads: list = []         # one record for each upload (or, on the fallback route, for the enable)
        self.target_sent: dict | None = None

    def _bundle(self):
        """The study's observation, remembering which zones it lists: the planner learns of a zone only from here on."""
        self.listed = [dict(z) for z in self.threats]
        return super()._bundle()

    def _zone_circles(self) -> list:
        """The scenario's zones as (north, east, radius), for the fallback route's upload before take-off."""
        return [(e[3], e[4], e[5]) for e in self.scenario.events if e[0] == 'threat']

    def reset(self):
        """The study's `Episode.reset`, with the simulator started through `make_sim`. The parameter read-back happens
        inside `prepare`, before take-off. A test pins this method to the study's, apart from the simulator line."""
        if self.sim is not None:
            raise RuntimeError('Create another episode rather than reusing this one')
        params = {'SIM_WIND_SPD': self.scenario.wind_ms, 'SIM_WIND_DIR': self.scenario.wind_from_deg,
                  **dict(self.task.autopilot_params), **getattr(self, 'extra_autopilot_params', {})}
        self.sim = make_sim(self.folder, self.defaults_file, S.expected(self.setting, self.route == 'preloaded'),
                            speedup=HOST['speedup'], instance=HOST['instance'], gcs=HOST['gcs'], params=params,
                            stream_hz=self.task.stream_hz, absent=S.expected_absent(self.setting),
                            preload=self._zone_circles() if self.route == 'preloaded' else None)
        try:
            self.sim.prepare(alt_m=self.task.start_alt_m)
        except Exception:
            self.sim.close()
            raise
        self.t0 = self.sim.state['t']
        self.observed = self.t0
        self.last_truth = truth(self.sim.state)   # so a 'g' trigger can fire before the first step
        return {'briefing': {'goal': dict(self.goal), 'fallback': dict(self.velocity), 'step_duration_s': self.tick},
                'bundle': self._bundle()}

    def _alt(self):
        return -self.sim.state['down']

    def send_command(self):
        """The planner's command for this step. The goal goes out once, at the first command stamp. Any zone that the
        last observation listed and that is not yet in the fence is loaded now. A land flight switches to LAND within
        0.5 m of the point, by the autopilot's own estimate, as the study's comparator does."""
        g, s, name = self.goal, self.sim.state, self.task.name
        if self.t == 0:
            self.hold_alt = g['target_alt_m'] if 'target_alt_m' in g else self._alt()
            self.sim.command_position(g['target_north_m'], g['target_east_m'], self.hold_alt)
            self.target_sent = {'step': self.t, 'sim_t': s['t'], 'north_m': g['target_north_m'],
                                'east_m': g['target_east_m'], 'alt_m': self.hold_alt}
        self._load_new_zones()
        if name == 'land' and self.stage == 'approach':
            if math.hypot(s['north'] - g['target_north_m'], s['east'] - g['target_east_m']) < LAND_WITHIN_M:
                self.sim.set_mode('LAND')
                self.stage = 'land'

    def _load_new_zones(self):
        new = [z for z in self.listed if z not in self.uploaded]
        if not new:
            return
        everything = self.uploaded + new       # a fence upload replaces the whole list, so every zone so far is sent
        deadline = self.t0 + (self.t + 1) * self.tick
        if self.route == 'preloaded':
            record = self.sim.enable_fence(deadline)
        else:
            record = self.sim.upload_exclusion_circles([(z['north_m'], z['east_m'], z['radius_m']) for z in everything],
                                                       deadline)
        self.uploaded = everything
        self.uploads.append({'step': self.t, 'route': self.route, 'new_zones': [dict(z) for z in new], **record})


def planner_rows(sim_folder: Path) -> dict:
    """How often the planner acted in a flight, from the simulator's own log (design section 6): the rows in which
    Dijkstra returned a path (OADJ, state 2), the rows in which Dijkstra failed (OADJ, state 1) with the error codes seen,
    and the rows in which BendyRuler was active (OABR, Act 1). A log that cannot be read gives None and the reason, which
    the summary reports as unknown and never as zero."""
    logs = sorted(Path(sim_folder).glob('logs/*.BIN'))
    if not logs:
        return {'dijkstra_rows': None, 'dijkstra_error_rows': None, 'dijkstra_error_codes': None,
                'bendyruler_rows': None, 'log': None, 'note': 'no onboard log found'}
    dj = dj_err = br = 0
    codes: dict = {}
    try:
        log = mavutil.mavlink_connection(str(logs[-1]))
        try:
            while (m := log.recv_match(type=['OADJ', 'OABR'])) is not None:
                if m.get_type() == 'OADJ' and m.State == 2:
                    dj += 1
                elif m.get_type() == 'OADJ' and m.State == 1:
                    dj_err += 1
                    codes[str(m.Err)] = codes.get(str(m.Err), 0) + 1
                elif m.get_type() == 'OABR' and m.Act == 1:
                    br += 1
        finally:
            log.close()
    except Exception as e:
        return {'dijkstra_rows': None, 'dijkstra_error_rows': None, 'dijkstra_error_codes': None,
                'bendyruler_rows': None, 'log': logs[-1].name, 'note': f'log not readable: {type(e).__name__}: {e}'}
    return {'dijkstra_rows': dj, 'dijkstra_error_rows': dj_err, 'dijkstra_error_codes': codes, 'bendyruler_rows': br,
            'log': logs[-1].name}

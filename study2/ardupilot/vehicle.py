"""A running ArduPilot simulator that a Telohelm host can step: start it, read the raw state, send guidance, advance.

The simulator runs freely at its speed-up; it does not wait for the host. advance_to() reads messages until the
simulated clock reaches a time, so anything the host does in between (Telohelm deciding) costs simulated time, and
the delay is recorded rather than hidden.
"""
from __future__ import annotations

import math
import os
import subprocess
import time
from pathlib import Path

from pymavlink import mavutil

ARDUPILOT = Path(os.environ.get('ARDUPILOT_HOME', Path.home() / 'Development' / 'ardupilot'))
HOME = (-35.363261, 149.165230, 584.0, 353.0)  # ArduPilot's CMAC test field near Canberra
M_PER_DEG_LAT = 111_319.5
MODELS = {'copter': ('arducopter', '+', 'copter.parm'), 'rover': ('ardurover', 'rover', 'rover.parm')}
VELOCITY_ONLY = 0b110111000111  # use vx, vy, vz; ignore position, acceleration, yaw and yaw rate
POSITION_ONLY = 0b110111111000  # use x, y, z; ignore velocity, acceleration, yaw and yaw rate
POSITION_AND_YAW = 0b100111111000  # use x, y, z and yaw; ignore velocity, acceleration and yaw rate


class SimulatorError(RuntimeError):
    pass


class MissingTruth(RuntimeError):
    """The simulator's true state was missing when a flight needed it for judging. Not a SimulatorError, so that
    nothing that handles simulator trouble can turn it into a scored outcome: it stops the flight and its phase, the
    records are kept, and the protocol's faults rule decides what happens next (PROTOCOL.md section 7)."""


TRUTH_FIELDS = ('true_north', 'true_east', 'true_alt', 'true_vn', 'true_ve', 'true_vd')


class Sitl:
    def __init__(self, folder: Path, vehicle: str = 'copter', speedup: float = 10.0, instance: int = 0,
                 gcs: bool = False, params: dict | None = None, wall_limit_s: float = 120.0,
                 gazebo: bool = False, stream_hz: int = 10):
        binary, model, defaults = MODELS[vehicle]
        self.folder, self.vehicle, self.speedup, self.gazebo = Path(folder), vehicle, speedup, gazebo
        self.wall_limit_s = wall_limit_s
        self.folder.mkdir(parents=True)
        default_files = [str(ARDUPILOT / 'Tools' / 'autotest' / 'default_params' / defaults)]
        if gazebo:
            # Gazebo provides the physics through the ardupilot_gazebo plugin's JSON flight-dynamics interface; the
            # vehicle appears in the Gazebo window. The gazebo-iris parameters match that model (vehicle must be copter).
            model = 'JSON'
            default_files.append(str(ARDUPILOT / 'Tools' / 'autotest' / 'default_params' / 'gazebo-iris.parm'))
            # The stock iris_with_ardupilot model once reported an inverted attitude on the ground, so the autopilot
            # refused to arm. The Split-S flights of 1 November 2026 used the iris_cine model (gazebo/README.md),
            # which took off and flew; the stock model has not been rechecked.
        self.command = [str(ARDUPILOT / 'build' / 'sitl' / 'bin' / binary), '--model', model,
                        '--speedup', str(speedup), '--wipe', '--instance', str(instance),
                        '--home', ','.join(str(x) for x in HOME),
                        '--defaults', ','.join(default_files)]
        if gcs:
            self.command += ['--serial1', f'udpclient:127.0.0.1:{14550 + 10 * instance}']
        self._log = open(self.folder / 'sitl.log', 'w')
        self.process = subprocess.Popen(self.command, cwd=self.folder, stdout=self._log, stderr=subprocess.STDOUT)
        # north/east/down and velocities are ArduPilot's own estimate, which jamming and spoofing corrupt;
        # true_north/true_east/true_alt and the true velocities are the simulator's truth (SIM_STATE), for judging
        # only and never shown to procedures; truth_t is the simulated time when the last SIM_STATE was read.
        self.state = dict(t=0.0, position_t=None, north=None, east=None, down=None, vn=None, ve=None, vd=None,
                          heading_deg=None, battery_pct=None, battery_v=None, gps_fix=None, gps_sats=None,
                          ekf_flags=None, true_north=None, true_east=None, true_alt=None, true_vn=None,
                          true_ve=None, true_vd=None, truth_t=None, armed=False, mode=None)
        self.texts: list[dict] = []
        self.params_seen: dict[str, float] = {}   # values the autopilot reported back (PARAM_VALUE)
        try:
            self.conn = self._connect(5760 + 10 * instance)
            self.conn.mav.request_data_stream_send(self.conn.target_system, self.conn.target_component,
                                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, stream_hz, 1)
            # The simulator's full true state, including altitude, when it offers it (at stream_hz).
            self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component,
                                            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                            mavutil.mavlink.MAVLINK_MSG_ID_SIM_STATE, int(1e6 / stream_hz), 0, 0, 0, 0, 0)
            for name, value in (params or {}).items():
                self.conn.mav.param_set_send(self.conn.target_system, self.conn.target_component, name.encode(),
                                             float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        except Exception:
            self.close()
            raise

    def _connect(self, port):
        give_up = time.monotonic() + 30
        while True:
            try:
                conn = mavutil.mavlink_connection(f'tcp:127.0.0.1:{port}', source_system=255)
                if conn.wait_heartbeat(timeout=10):
                    return conn
            except OSError:
                pass
            if time.monotonic() > give_up:
                raise SimulatorError(f'no heartbeat on port {port}')
            time.sleep(0.5)

    def _read(self, timeout=0.5):
        msg = self.conn.recv_match(blocking=True, timeout=timeout)
        if msg is not None:
            self._handle(msg)

    def _handle(self, msg):
        kind, s = msg.get_type(), self.state
        if hasattr(msg, 'time_boot_ms') and msg.time_boot_ms:
            s['t'] = max(s['t'], msg.time_boot_ms / 1000.0)
        if kind == 'HEARTBEAT' and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
            s['armed'] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            s['mode'] = mavutil.mode_string_v10(msg)
        elif kind == 'LOCAL_POSITION_NED':
            s.update(position_t=msg.time_boot_ms / 1000.0, north=msg.x, east=msg.y, down=msg.z,
                     vn=msg.vx, ve=msg.vy, vd=msg.vz)
        elif kind == 'ATTITUDE':
            s['heading_deg'] = math.degrees(msg.yaw) % 360.0
        elif kind == 'SYS_STATUS':
            s['battery_pct'], s['battery_v'] = msg.battery_remaining, msg.voltage_battery / 1000.0
        elif kind == 'GPS_RAW_INT':
            s['gps_fix'], s['gps_sats'] = msg.fix_type, msg.satellites_visible
        elif kind == 'EKF_STATUS_REPORT':
            s['ekf_flags'] = msg.flags
        elif kind == 'SIMSTATE':
            self._truth(msg.lat / 1e7, msg.lng / 1e7, None)
        elif kind == 'SIM_STATE':
            lat = msg.lat_int / 1e7 if getattr(msg, 'lat_int', 0) else msg.lat
            lon = msg.lon_int / 1e7 if getattr(msg, 'lon_int', 0) else msg.lon
            self._truth(lat, lon, msg.alt - HOME[2], (msg.vn, msg.ve, msg.vd))
        elif kind == 'PARAM_VALUE':
            name = msg.param_id.decode() if isinstance(msg.param_id, bytes) else msg.param_id
            self.params_seen[name.rstrip('\x00')] = msg.param_value
        elif kind == 'STATUSTEXT':
            self.texts.append(dict(t=s['t'], text=msg.text))

    def _truth(self, lat, lon, alt, velocity=None):
        self.state['true_north'] = (lat - HOME[0]) * M_PER_DEG_LAT
        self.state['true_east'] = (lon - HOME[1]) * M_PER_DEG_LAT * math.cos(math.radians(HOME[0]))
        if alt is not None:
            self.state['true_alt'] = alt
        if velocity is not None:   # SIM_STATE: true north, east and down velocity, m/s
            self.state['true_vn'], self.state['true_ve'], self.state['true_vd'] = map(float, velocity)
            self.state['truth_t'] = self.state['t']

    def set_param(self, name: str, value: float):
        """Change a setting during flight, such as a SIM_ fault. Not confirmed; the effect shows in the state."""
        self.conn.mav.param_set_send(self.conn.target_system, self.conn.target_component, name.encode(),
                                     float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)

    def drain(self):
        """Read every message already waiting, so the clock shows the simulated time now."""
        while (msg := self.conn.recv_match(blocking=False)) is not None:
            self._handle(msg)

    def wait(self, done, sim_limit_s, every=None):
        """Read until done() holds; False if simulated or wall time runs out first."""
        start_t, start_wall, last = self.state['t'], time.monotonic(), 0.0
        while not done():
            if self.state['t'] - start_t > sim_limit_s or time.monotonic() - start_wall > self.wall_limit_s:
                return False
            if self.process.poll() is not None:
                raise SimulatorError('the simulator exited')
            if every and time.monotonic() - last > 1.0:
                every()
                last = time.monotonic()
            self._read()
        return True

    def set_mode(self, mode):
        self.conn.set_mode(mode)
        if not self.wait(lambda: self.state['mode'] == mode, 10):
            raise SimulatorError(f'did not enter {mode}')

    def prepare(self, alt_m: float = 10.0):
        """Bring the vehicle to steady guided flight: hovering at alt_m for a copter, armed and still for a rover."""
        if not self.wait(lambda: self.state['north'] is not None, 90):
            raise SimulatorError('no local position')
        # The judge needs the simulator's truth (A1 of Codex's review, 3 November 2026): a flight whose truth never
        # arrives does not start, and that is an infrastructure fault before any outcome exists.
        if not self.wait(lambda: all(self.state[k] is not None for k in TRUTH_FIELDS), 30):
            raise SimulatorError('no simulator truth (SIM_STATE): ' +
                                 ', '.join(k for k in TRUTH_FIELDS if self.state[k] is None))
        if self.gazebo:
            # With the Gazebo backend, GUIDED only holds once the position estimate has a GPS fix; without this wait
            # the mode reverts to STABILIZE and the take-off is ignored. Waiting for the fix is responding to the
            # vehicle's own readiness, not forcing it.
            if not self.wait(lambda: (self.state['gps_fix'] or 0) >= 3, 120):
                raise SimulatorError('no GPS fix for guided flight (gazebo)')
        self.set_mode('GUIDED')
        # Pre-arm checks pass once the position estimate uses GPS, so keep asking.
        if not self.wait(lambda: self.state['armed'], 120, every=self.conn.arducopter_arm):
            raise SimulatorError('did not arm: ' + '; '.join(x['text'] for x in self.texts[-3:]))
        if self.vehicle == 'copter':
            self.conn.mav.command_long_send(self.conn.target_system, self.conn.target_component,
                                            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, alt_m)
            if not self.wait(lambda: -self.state['down'] >= alt_m - 0.3, 60):
                raise SimulatorError('did not reach take-off height')
            self.advance_to(self.state['t'] + 3.0)

    def command_velocity(self, vn: float, ve: float, vd: float = 0.0):
        self.conn.mav.set_position_target_local_ned_send(
            0, self.conn.target_system, self.conn.target_component, mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            VELOCITY_ONLY, 0, 0, 0, vn, ve, vd, 0, 0, 0, 0, 0)

    def command_position(self, north_m: float, east_m: float, alt_m: float, yaw_deg: float | None = None):
        """A guided-mode position target relative to home (ArduPilot flies there itself), for comparator flights."""
        mask = POSITION_ONLY if yaw_deg is None else POSITION_AND_YAW
        self.conn.mav.set_position_target_local_ned_send(
            0, self.conn.target_system, self.conn.target_component, mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            mask, north_m, east_m, -alt_m, 0, 0, 0, 0, 0, 0, math.radians(yaw_deg or 0.0), 0)

    def hold_sticks_centred(self):
        """Radio override with every stick centred (1500 us), as a pilot holding still. Modes that read the sticks,
        such as circle mode's throttle for climb rate, then hold height. Expires after RC_OVERRIDE_TIME (3 s by
        default), so send it every step."""
        self.conn.mav.rc_channels_override_send(self.conn.target_system, self.conn.target_component,
                                                1500, 1500, 1500, 1500, 0, 0, 0, 0)

    def advance_to(self, t: float):
        if not self.wait(lambda: self.state['t'] >= t, max(5.0, t - self.state['t'] + 5.0)):
            raise SimulatorError(f'simulated clock stalled before {t:.1f} s')

    def close(self):
        if getattr(self, 'process', None) is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if getattr(self, 'conn', None) is not None:
            self.conn.close()
            self.conn = None
        if not self._log.closed:
            self._log.close()

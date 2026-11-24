"""Fly one short guided mission in ArduPilot's simulator and record what happened.

Starts the simulator binary directly (no MAVProxy), talks to it over MAVLink on TCP and
writes one JSON line per position sample, the simulator's own output and a summary.
Copter: take off to 10 m, fly 50 m north, land. Rover: drive 30 m north, then hold.

Usage:
  ~/Development/ardupilot/.venv-build/bin/python smoke_test.py copter --speedup 5
  ~/Development/ardupilot/.venv-build/bin/python smoke_test.py copter --speedup 1 --gcs   # watch in QGroundControl
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from datetime import datetime
from pathlib import Path

from pymavlink import mavutil

ARDUPILOT = Path.home() / 'Development' / 'ardupilot'
HOME = (-35.363261, 149.165230, 584.0, 353.0)  # ArduPilot's CMAC test field near Canberra
VEHICLES = {
    'copter': dict(binary='arducopter', model='+', defaults='copter.parm', north_m=50.0, alt_m=10.0, arrived_m=1.0),
    'rover': dict(binary='ardurover', model='rover', defaults='rover.parm', north_m=30.0, alt_m=0.0, arrived_m=3.0),
}


def metres_between(lat1, lon1, lat2, lon2):
    north = (lat2 - lat1) * 111_320.0
    east = (lon2 - lon1) * 111_320.0 * math.cos(math.radians(lat1))
    return math.hypot(north, east)


class Flight:
    def __init__(self, conn, samples):
        self.conn, self.samples = conn, samples
        self.state = dict(t=0.0, lat=None, lon=None, alt=None, armed=False, mode=None)
        self.texts: list[dict] = []
        self.phases: list[dict] = []
        self.wall0 = time.monotonic()

    def phase(self, name):
        self.phases.append(dict(phase=name, sim_s=round(self.state['t'], 2),
                                wall_s=round(time.monotonic() - self.wall0, 2)))
        print(f"{self.state['t']:7.1f} sim s  {name}", flush=True)

    def pump(self, done, sim_limit, wall_limit=300.0, every=None):
        """Read messages until done() holds. Calls every() about once a wall second."""
        start_t, start_wall, last = self.state['t'], time.monotonic(), 0.0
        while not done():
            if self.state['t'] - start_t > sim_limit or time.monotonic() - start_wall > wall_limit:
                return False
            if every and time.monotonic() - last > 1.0:
                every()
                last = time.monotonic()
            msg = self.conn.recv_match(blocking=True, timeout=0.5)
            if msg is None:
                continue
            kind = msg.get_type()
            if kind == 'HEARTBEAT' and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
                self.state['armed'] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                self.state['mode'] = mavutil.mode_string_v10(msg)
            elif kind == 'GLOBAL_POSITION_INT':
                self.state.update(t=msg.time_boot_ms / 1000.0, lat=msg.lat / 1e7, lon=msg.lon / 1e7,
                                  alt=msg.relative_alt / 1000.0)
                self.samples.write(json.dumps(dict(self.state)) + '\n')
            elif kind == 'STATUSTEXT':
                self.texts.append(dict(sim_s=round(self.state['t'], 2), text=msg.text))
        return True


def connect(port, wall_limit=30.0):
    give_up = time.monotonic() + wall_limit
    while True:
        try:
            conn = mavutil.mavlink_connection(f'tcp:127.0.0.1:{port}', source_system=255)
            if conn.wait_heartbeat(timeout=10):
                return conn
        except OSError:
            pass
        if time.monotonic() > give_up:
            raise RuntimeError(f'no heartbeat on port {port}')
        time.sleep(0.5)


def fly(vehicle, f, conn):
    spec = VEHICLES[vehicle]
    sysid, compid = conn.target_system, conn.target_component
    conn.mav.request_data_stream_send(sysid, compid, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    if not f.pump(lambda: f.state['lat'] not in (None, 0.0), sim_limit=60):
        return 'no position from the simulator'
    f.phase('position received')

    conn.set_mode('GUIDED')
    if not f.pump(lambda: f.state['mode'] == 'GUIDED', sim_limit=10):
        return 'did not enter GUIDED'
    f.phase('GUIDED')

    # Pre-arm checks pass once the position estimate has settled, so keep asking.
    if not f.pump(lambda: f.state['armed'], sim_limit=120, every=conn.arducopter_arm):
        return 'did not arm'
    f.phase('armed')

    if vehicle == 'copter':
        conn.mav.command_long_send(sysid, compid, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                                   0, 0, 0, 0, 0, 0, 0, spec['alt_m'])
        if not f.pump(lambda: f.state['alt'] >= spec['alt_m'] - 0.5, sim_limit=60):
            return 'did not reach take-off height'
        f.phase(f"at {spec['alt_m']:.0f} m")

    home_lat, home_lon = HOME[0], HOME[1]
    target_lat = home_lat + spec['north_m'] / 111_320.0
    position_only = 0b110111111000
    conn.mav.set_position_target_global_int_send(
        0, sysid, compid, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, position_only,
        int(target_lat * 1e7), int(home_lon * 1e7), spec['alt_m'], 0, 0, 0, 0, 0, 0, 0, 0)
    left = lambda: metres_between(f.state['lat'], f.state['lon'], target_lat, home_lon)
    if not f.pump(lambda: left() < spec['arrived_m'], sim_limit=90):
        return f'did not reach the point ({left():.1f} m away)'
    f.phase(f"within {spec['arrived_m']:.0f} m of the point {spec['north_m']:.0f} m north")
    f.arrival_error_m = round(left(), 2)

    if vehicle == 'copter':
        conn.set_mode('LAND')
        if not f.pump(lambda: not f.state['armed'], sim_limit=90):
            return 'did not land and disarm'
        f.phase('landed and disarmed')
    else:
        conn.set_mode('HOLD')
        if not f.pump(lambda: f.state['mode'] == 'HOLD', sim_limit=10):
            return 'did not enter HOLD'
        f.phase('holding')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('vehicle', choices=sorted(VEHICLES))
    parser.add_argument('--speedup', type=float, default=5.0)
    parser.add_argument('--instance', type=int, default=0)
    parser.add_argument('--out', type=Path, default=Path(__file__).parent / 'runs')
    parser.add_argument('--gcs', action='store_true',
                        help='also send telemetry to a ground station on UDP 14550 (QGroundControl connects by itself)')
    args = parser.parse_args()

    spec = VEHICLES[args.vehicle]
    run = args.out / f"{args.vehicle}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run.mkdir(parents=True)
    binary = ARDUPILOT / 'build' / 'sitl' / 'bin' / spec['binary']
    defaults = ARDUPILOT / 'Tools' / 'autotest' / 'default_params' / spec['defaults']
    command = [str(binary), '--model', spec['model'], '--speedup', str(args.speedup), '--wipe',
               '--instance', str(args.instance), '--home', ','.join(str(x) for x in HOME),
               '--defaults', str(defaults)]
    if args.gcs:
        command += ['--serial1', f'udpclient:127.0.0.1:{14550 + 10 * args.instance}']
    with open(run / 'sitl.log', 'w') as log, open(run / 'samples.jsonl', 'w') as samples:
        sim = subprocess.Popen(command, cwd=run, stdout=log, stderr=subprocess.STDOUT)
        try:
            conn = connect(5760 + 10 * args.instance)
            f = Flight(conn, samples)
            f.arrival_error_m = None
            failure = fly(args.vehicle, f, conn)
        finally:
            sim.terminate()
            try:
                sim.wait(timeout=10)
            except subprocess.TimeoutExpired:
                sim.kill()

    git = lambda *a: subprocess.run(['git', '-C', str(ARDUPILOT), *a], capture_output=True, text=True).stdout
    tags = [t for t in git('tag', '--points-at', 'HEAD').split() if t.startswith(('Copter-', 'Rover-'))]
    version = dict(commit=git('rev-parse', 'HEAD').strip(), tags=tags,
                   local_changes=git('diff', '--stat').strip() or None)
    wall = time.monotonic() - f.wall0
    summary = dict(vehicle=args.vehicle, ardupilot=version, speedup=args.speedup, passed=failure is None,
                   failure=failure, phases=f.phases, arrival_error_m=f.arrival_error_m,
                   sim_s=round(f.state['t'], 2), wall_s=round(wall, 2),
                   achieved_speedup=round(f.state['t'] / wall, 2) if wall else None,
                   statustext=f.texts, command=command)
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(('PASSED' if failure is None else f'FAILED: {failure}') + f'  ({run})')
    return 0 if failure is None else 1


if __name__ == '__main__':
    raise SystemExit(main())

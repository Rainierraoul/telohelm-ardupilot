"""Long, complex 3D courses that thread around a structure, with an independent feasibility check.

Where course.py makes a flat ring of gates at one height, this makes a freestyle line in three dimensions: a building
(a box on the ground) and an ordered list of gates that climb, drop and weave around it, the shape of an FPV flight
around an old building. A course is a pure function of a seed, so it is reproducible.

Before Telohelm flies, an independent reference controller that sees the true position flies the course in 3D, steering
to each gate and pushing away from the building. Only a certified course is handed on, so a failure is the procedure's,
not an impossible line's. Courses are built to be flyable: gates sit outside the building with a margin, legs are within
reach and turn, and everything stays inside the fence and under the height cap.

This module is geometry and a point-mass check, with no dependency on the simulator or Telohelm. The 3D flight itself
needs a procedure that commands vertical as well as horizontal velocity (the reach3d subtask).

Run from paper3/:
  python -m ardupilot.course3d --seed 7                 # print and certify one course
  python -m ardupilot.course3d --check 1000 1100        # certify a range of seeds
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
import math
import random

FENCE_M = 100.0
ALT_CAP_M = 40.0
MAX_SPEED_MS = 5.0
MAX_VERTICAL_MS = 2.0
GATE_RADIUS_M = 3.0


@dataclass(frozen=True)
class Building:
    north_m: float
    east_m: float
    half_n_m: float      # half-depth (north extent)
    half_e_m: float      # half-width (east extent)
    height_m: float

    def inside(self, n, e, alt, margin=0.0):
        return (abs(n - self.north_m) < self.half_n_m + margin
                and abs(e - self.east_m) < self.half_e_m + margin
                and alt < self.height_m + margin)

    def clear_of_footprint(self, n, e, margin):
        return abs(n - self.north_m) > self.half_n_m + margin or abs(e - self.east_m) > self.half_e_m + margin


@dataclass(frozen=True)
class Gate3D:
    north_m: float
    east_m: float
    alt_m: float
    radius_m: float = GATE_RADIUS_M


@dataclass(frozen=True)
class Course3D:
    seed: int
    building: Building
    gates: tuple
    wind_ms: float = 0.0
    wind_from_deg: float = 0.0
    fence_m: float = FENCE_M
    max_speed_ms: float = MAX_SPEED_MS
    max_vertical_ms: float = MAX_VERTICAL_MS

    def as_dict(self):
        return asdict(self)


def generate(seed: int, gate_radius: float = GATE_RADIUS_M) -> Course3D:
    """A building near the middle of the field, and a line of gates that approaches it, climbs a face, crosses over the
    top, drops down the far side and rounds a corner. Gate heights vary; every gate clears the building."""
    rng = random.Random(f'course3d/{seed}')
    # A building offset from home, sized so a flight can go over it within the height cap.
    bn, be = rng.uniform(-15, 15), rng.uniform(25, 45)
    hn, he = rng.uniform(6, 12), rng.uniform(6, 12)
    h = rng.uniform(12, 24)
    building = Building(round(bn, 1), round(be, 1), round(hn, 1), round(he, 1), round(h, 1))

    margin = 4.0
    top = min(h + rng.uniform(4, 8), ALT_CAP_M)
    # Waypoints as a readable plan around the box: a corner approach, up a face, over the top, down the far side, round.
    def corner(sn, se, alt):
        return (building.north_m + sn * (building.half_n_m + margin + rng.uniform(2, 6)),
                building.east_m + se * (building.half_e_m + margin + rng.uniform(2, 6)), alt)
    legs = [
        corner(-1, -1, rng.uniform(6, 10)),     # approach a near corner, low
        corner(-1, -1, top),                     # climb that corner to roof height
        (building.north_m, building.east_m, top),  # cross over the roof
        corner(1, 1, top),                       # far corner at roof height
        corner(1, 1, rng.uniform(6, 10)),        # descend the far corner
        corner(1, -1, rng.uniform(8, 14)),       # round to another corner, mid height
    ]
    gates = []
    for n, e, alt in legs:
        n, e = _clamp(n, e)
        alt = max(3.0, min(alt, ALT_CAP_M))
        gates.append(Gate3D(round(n, 1), round(e, 1), round(alt, 1), radius_m=gate_radius))
    wind = round(rng.uniform(0, 4), 1) if rng.random() < 0.5 else 0.0
    return Course3D(seed, building, tuple(gates), wind, round(rng.uniform(0, 360), 1))


def _clamp(n, e):
    r = math.hypot(n, e)
    if r <= FENCE_M - 10:
        return n, e
    s = (FENCE_M - 10) / max(r, 1e-6)
    return n * s, e * s


def _reference_velocity(pos, gate, building, vmax, vzmax):
    tn, te, ta = gate.north_m - pos[0], gate.east_m - pos[1], gate.alt_m - pos[2]
    dh = math.hypot(tn, te)
    vn, ve = (tn / dh * vmax, te / dh * vmax) if dh > 1e-6 else (0.0, 0.0)
    vz = max(-vzmax, min(vzmax, ta))
    # Push out of the building footprint when below roof height and close to it.
    if pos[2] < building.height_m + 1.0:
        dn, de = pos[0] - building.north_m, pos[1] - building.east_m
        over_n = abs(dn) - building.half_n_m
        over_e = abs(de) - building.half_e_m
        near = max(over_n, over_e)
        if near < 5.0:
            push = (5.0 - near) / 5.0 * vmax * 1.5
            if over_n > over_e:
                vn += math.copysign(push, dn)
            else:
                ve += math.copysign(push, de)
    sp = math.hypot(vn, ve)
    if sp > vmax:
        vn, ve = vn / sp * vmax, ve / sp * vmax
    return vn, ve, vz


def certify(course: Course3D, dt: float = 0.1) -> dict:
    pos = (0.0, 0.0, course.gates[0].alt_m if course.gates else 10.0)
    pos = (0.0, 0.0, 2.0)
    vmax, vzmax, b = course.max_speed_ms, course.max_vertical_ms, course.building
    t = 0.0
    straight = 0.0
    prev = (0.0, 0.0, 2.0)
    for g in course.gates:
        straight += math.dist(prev, (g.north_m, g.east_m, g.alt_m)); prev = (g.north_m, g.east_m, g.alt_m)
    cap = straight / vmax * 4.0 + 40.0
    for idx, gate in enumerate(course.gates):
        while math.dist(pos, (gate.north_m, gate.east_m, gate.alt_m)) > gate.radius_m:
            vn, ve, vz = _reference_velocity(pos, gate, b, vmax, vzmax)
            pos = (pos[0] + vn * dt, pos[1] + ve * dt, pos[2] + vz * dt)
            t += dt
            if math.hypot(pos[0], pos[1]) > course.fence_m or pos[2] > ALT_CAP_M + 2:
                return {"certified": False, "reason": f"reference left the bounds near gate {idx + 1}", "seconds": round(t, 1)}
            if b.inside(pos[0], pos[1], pos[2], margin=0.0):
                return {"certified": False, "reason": f"reference hit the building near gate {idx + 1}", "seconds": round(t, 1)}
            if t > cap:
                return {"certified": False, "reason": f"reference ran out of time at gate {idx + 1}", "seconds": round(t, 1)}
    return {"certified": True, "reason": "reference flew the 3D course", "seconds": round(t, 1), "gates": len(course.gates),
            "height_climbed_m": round(max(g.alt_m for g in course.gates), 1)}


def reference_path(course: Course3D, dt: float = 0.1):
    pos = (0.0, 0.0, 2.0); path = [pos]; b = course.building
    for gate in course.gates:
        guard = 0.0
        while math.dist(pos, (gate.north_m, gate.east_m, gate.alt_m)) > gate.radius_m and guard < 400:
            vn, ve, vz = _reference_velocity(pos, gate, b, course.max_speed_ms, course.max_vertical_ms)
            pos = (pos[0] + vn * dt, pos[1] + ve * dt, pos[2] + vz * dt); path.append(pos); guard += dt
    return path


def sdf_world(course: Course3D) -> str:
    """A Gazebo world (SDFormat, sdformat.org) holding the iris, the building and the gates, placed where the course
    puts them. Gazebo's world frame is east-north-up, so an ArduPilot (north, east, alt) point maps to (x=east,
    y=north, z=alt). The building has collision, so flying into it is a real crash; gates are translucent markers to
    fly through. The IMU and NavSat systems and the spherical coordinates (ArduPilot's CMAC home field) are required:
    without them the ArduPilot bridge gets no sensor data and the drone cannot fly. This is the world-modeller's Gazebo
    staging output for a 3D course."""
    b = course.building
    gates = []
    for i, g in enumerate(course.gates, 1):
        gates.append(f"""    <model name="gate_{i}"><static>true</static>
      <pose>{g.east_m} {g.north_m} {g.alt_m} 0 0 0</pose>
      <link name="l"><visual name="v"><geometry><sphere><radius>{g.radius_m}</radius></sphere></geometry>
        <transparency>0.55</transparency>
        <material><ambient>0.1 0.9 0.3 0.45</ambient><diffuse>0.1 0.9 0.3 0.45</diffuse>
          <emissive>0.1 0.6 0.2 0.4</emissive></material></visual></link></model>""")
    building = f"""    <model name="building"><static>true</static>
      <pose>{b.east_m} {b.north_m} {b.height_m / 2} 0 0 0</pose>
      <link name="l">
        <collision name="c"><geometry><box><size>{b.half_e_m * 2} {b.half_n_m * 2} {b.height_m}</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>{b.half_e_m * 2} {b.half_n_m * 2} {b.height_m}</size></box></geometry>
          <material><ambient>0.4 0.4 0.42 1</ambient><diffuse>0.5 0.5 0.52 1</diffuse></material></visual></link></model>"""
    return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <world name="course3d_{course.seed}">
    <physics name="1ms" type="ignore"><max_step_size>0.001</max_step_size><real_time_factor>1.0</real_time_factor></physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
    <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
    <plugin filename="gz-sim-navsat-system" name="gz::sim::systems::NavSat"/>
    <spherical_coordinates>
      <latitude_deg>-35.363262</latitude_deg><longitude_deg>149.165237</longitude_deg>
      <elevation>584</elevation><heading_deg>0</heading_deg><surface_model>EARTH_WGS84</surface_model>
    </spherical_coordinates>
    <light type="directional" name="sun"><cast_shadows>true</cast_shadows><direction>-0.5 0.3 -0.9</direction>
      <diffuse>1 1 1 1</diffuse><specular>0.3 0.3 0.3 1</specular></light>
    <model name="ground"><static>true</static><link name="l">
      <collision name="c"><geometry><plane><normal>0 0 1</normal><size>400 400</size></plane></geometry></collision>
      <visual name="v"><geometry><plane><normal>0 0 1</normal><size>400 400</size></plane></geometry>
        <material><ambient>0.3 0.3 0.3 1</ambient><diffuse>0.35 0.35 0.35 1</diffuse></material></visual></link></model>
    <include><uri>model://iris_with_ardupilot</uri></include>
{building}
{chr(10).join(gates)}
  </world>
</sdf>
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--seed', type=int)
    p.add_argument('--check', nargs=2, type=int, metavar=('LO', 'HI'))
    p.add_argument('--sdf', type=str, help='write the Gazebo SDF world for this seed to this path')
    args = p.parse_args(argv)
    if args.sdf is not None and args.seed is not None:
        from pathlib import Path
        course = generate(args.seed)
        Path(args.sdf).write_text(sdf_world(course))
        print(f"wrote {args.sdf} (building + {len(course.gates)} gates, certified={certify(course)['certified']})")
        return 0
    if args.check:
        lo, hi = args.check
        bad = [s for s in range(lo, hi) if not certify(generate(s))['certified']]
        print(f"certified {hi - lo - len(bad)} of {hi - lo}; failures: {bad}")
        return 0
    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    course = generate(seed)
    print(json.dumps({"course": course.as_dict(), "certification": certify(course)}, indent=1, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

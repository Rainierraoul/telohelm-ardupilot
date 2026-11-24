"""The Split-S drone-racing track, recreated from the published geometry.

The gate coordinates are taken verbatim from the University of Zurich Robotics and Perception Group's time-optimal
planning repository (uzh-rpg/rpg_time_optimal, tracks/track.yaml: gates and initial position), checked on 1 November
2026; the repository asks users to cite Foehn, Romero and Scaramuzza (2021), Science Robotics 6(56):eabh1221. The signature of the track is gates 4 and 5, which share the
same ground position while the height drops from 3.5 m to 0.8 m: fly through the high gate, then immediately descend
through the gate directly below it.

We recreate the track's layout, not its racing performance. The published work flies time-optimal trajectories near
the vehicle's limits. Here Telohelm flies the same gate layout as a navigation task with its learned reach3d procedure,
through ArduPilot's guided mode. The value is a recognised, literature-grounded course flown by learned
transferable control; matching racing speed needs fast low-level control, which is a separate step.

Coordinates are the repository's (x, y, z) in metres, in a right-handed frame with z up. We map x to east, y to north and
z to altitude (east-north-up is also right-handed), and shift the track so the drone's home sits at the published start.
Until 2 November 2026 this module mapped x to north and y to east. That is a reflection: the recreated track had the same
distances, heights, gate order and vertical drop, but every turn went the other way (the published lap is clockwise
seen from above; the old recreation was anticlockwise). Every Split-S flight recorded before then flew the mirror image.
mirrored=True reproduces it for checking those records.

Run from paper3/:
  python -m ardupilot.course_splits --sdf ~/Development/ardupilot_gazebo/worlds/split_s.sdf
  python -m ardupilot.course_splits --laps 1            # print and certify
"""
from __future__ import annotations

import argparse
import json

from . import course3d as C3

# uzh-rpg/rpg_time_optimal, tracks/track.yaml (checked 2026-11-01). One lap is these seven gates; the file repeats
# them for three laps. initial position [-5, 4.5, 1.2].
SPLIT_S_XYZ = [
    (-1.1, -1.6, 3.6),
    (9.2, 6.6, 1.0),
    (9.2, -4.0, 1.2),
    (-4.5, -6.0, 3.5),   # high gate of the Split-S
    (-4.5, -6.0, 0.8),   # low gate directly below: the steep descent
    (4.75, -0.9, 1.2),
    (-2.8, 6.8, 1.2),
]
START_XY = (-5.0, 4.5)   # published initial position; home is placed here
GATE_RADIUS_M = 1.5      # navigation tolerance (looser than the racing 0.3 m; stated in the write-up)


def _gates(xyz, gate_radius: float, scale: float, mirrored: bool = False):
    out = []
    for x, y, z in xyz:
        dx, dy = (x - START_XY[0]) * scale, (y - START_XY[1]) * scale   # shifted so home is the published start
        n, e = (dx, dy) if mirrored else (dy, dx)     # published frame: x -> east, y -> north
        out.append(C3.Gate3D(round(n, 2), round(e, 2), round(z * scale, 2), gate_radius))
    return out


def split_s_course(laps: int = 1, gate_radius: float = GATE_RADIUS_M, scale: float = 1.0,
                   mirrored: bool = False) -> C3.Course3D:
    """laps x 7 gates. scale > 1 enlarges the whole track (positions and heights) by that factor, keeping its shape."""
    gates = _gates(SPLIT_S_XYZ * max(1, laps), gate_radius, scale, mirrored)
    building = C3.Building(north_m=1000.0, east_m=1000.0, half_n_m=0.1, half_e_m=0.1, height_m=0.1)
    return C3.Course3D(seed=-1, building=building, gates=tuple(gates), wind_ms=0.0, wind_from_deg=0.0)


def split_s_race(gate_radius: float = GATE_RADIUS_M, scale: float = 1.0, mirrored: bool = False) -> C3.Course3D:
    """The published three-lap race: the file's 19 gates (two full laps and the first five gates of the third)."""
    gates = _gates((SPLIT_S_XYZ * 3)[:19], gate_radius, scale, mirrored)
    building = C3.Building(north_m=1000.0, east_m=1000.0, half_n_m=0.1, half_e_m=0.1, height_m=0.1)
    return C3.Course3D(seed=-1, building=building, gates=tuple(gates), wind_ms=0.0, wind_from_deg=0.0)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--laps', type=int, default=1)
    p.add_argument('--sdf', type=str, help='write the Gazebo SDF world to this path')
    args = p.parse_args(argv)
    course = split_s_course(args.laps)
    cert = C3.certify(course)
    if args.sdf:
        from pathlib import Path
        Path(args.sdf).write_text(C3.sdf_world(course))
        print(f"wrote {args.sdf} ({len(course.gates)} gates, certified={cert['certified']})")
        return 0
    print(json.dumps({"gates_north_east_alt": [[g.north_m, g.east_m, g.alt_m] for g in course.gates],
                      "certification": cert}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

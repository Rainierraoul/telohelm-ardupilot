"""Seeded race courses for the live demonstration, with an independent feasibility check.

A course is a start, an ordered list of gates to pass, an optional no-go zone and a wind. It is a pure function of a
seed: the same number always gives the same course, so someone can hand over a seed and the course is reproducible.

Before Telohelm flies, a separate reference controller that sees the true position flies the course first. If it gets
round, the course is certified flyable, using nothing Telohelm knows. Only certified courses are handed to Telohelm.
Courses are also built to be flyable by construction (gates within reach and within a flyable turn, any zone kept off
the direct path, everything inside the fence), so certification almost always passes first time.

This module has no dependency on Telohelm or the simulator: the generator is geometry and the certifier is a small
point-mass flight. The SITL and Gazebo runners in the demo call generate() and certify() before flying the library.

Run:
  python -m ardupilot.course --seed 1234            # print and certify one course
  python -m ardupilot.course --check 1000 1100      # certify a range of seeds, report any that fail
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, asdict
import json
import math
import random

FENCE_M = 100.0          # the course stays inside this radius of home
ALT_M = 20.0             # gates and flight at this height above home
MAX_SPEED_MS = 5.0       # the vehicle's horizontal speed limit (matches the task pack)
GATE_RADIUS_M = 3.0      # a gate counts as passed within this distance
MIN_LEG_M, MAX_LEG_M = 18.0, 30.0
MAX_TURN_RAD = 0.8       # heading change allowed between legs, so a leg is flyable


@dataclass(frozen=True)
class Gate:
    north_m: float
    east_m: float
    alt_m: float = ALT_M
    radius_m: float = GATE_RADIUS_M


@dataclass(frozen=True)
class Zone:
    north_m: float
    east_m: float
    radius_m: float


@dataclass(frozen=True)
class Course:
    seed: int
    gates: tuple
    wind_ms: float = 0.0
    wind_from_deg: float = 0.0
    zone: Zone | None = None
    fence_m: float = FENCE_M
    alt_m: float = ALT_M
    max_speed_ms: float = MAX_SPEED_MS

    def as_dict(self):
        d = asdict(self)
        return d


def _clamp_into_fence(n, e, fence):
    r = math.hypot(n, e)
    if r <= fence - 10.0:
        return n, e
    scale = (fence - 10.0) / max(r, 1e-6)
    return n * scale, e * scale


def _seg_point_distance(p, a, b):
    """Shortest distance from point p to segment a-b, all (north, east)."""
    (pn, pe), (an, ae), (bn, be) = p, a, b
    dn, de = bn - an, be - ae
    L2 = dn * dn + de * de
    if L2 < 1e-9:
        return math.hypot(pn - an, pe - ae)
    t = max(0.0, min(1.0, ((pn - an) * dn + (pe - ae) * de) / L2))
    cn, ce = an + t * dn, ae + t * de
    return math.hypot(pn - cn, pe - ce)


def generate(seed: int, with_zone: bool = False, gate_radius: float = GATE_RADIUS_M) -> Course:
    """One course from a seed. Gates walk out from home with bounded legs and turns, inside the fence. A zone, when
    asked for, is placed clear of every leg so the course stays flyable."""
    rng = random.Random(f"course/{seed}")
    n_gates = rng.randint(4, 6)
    heading = rng.uniform(0.0, 2 * math.pi)
    pos = (0.0, 0.0)
    gates = []
    for _ in range(n_gates):
        # Near the fence, aim the next leg back toward home so a leg is never clamped onto the previous gate.
        if math.hypot(pos[0], pos[1]) > 0.55 * FENCE_M:
            heading = math.atan2(-pos[1], -pos[0]) + rng.uniform(-0.6, 0.6)
        else:
            heading += rng.uniform(-MAX_TURN_RAD, MAX_TURN_RAD)
        leg = rng.uniform(MIN_LEG_M, MAX_LEG_M)
        n = pos[0] + leg * math.cos(heading)
        e = pos[1] + leg * math.sin(heading)
        n, e = _clamp_into_fence(n, e, FENCE_M)
        gates.append(Gate(round(n, 1), round(e, 1), radius_m=gate_radius))
        pos = (n, e)

    zone = None
    if with_zone:
        pts = [(0.0, 0.0)] + [(g.north_m, g.east_m) for g in gates]
        for _ in range(40):
            k = rng.randint(0, len(pts) - 2)
            a, b = pts[k], pts[k + 1]
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            radius = round(rng.uniform(5.0, 9.0), 1)
            # offset to one side of the leg by more than the radius, so a straight leg would skirt it
            dn, de = b[0] - a[0], b[1] - a[1]
            length = max(math.hypot(dn, de), 1e-6)
            side = rng.choice((-1.0, 1.0))
            off = radius + rng.uniform(1.0, 4.0)
            zn = mid[0] + side * (-de / length) * off
            ze = mid[1] + side * (dn / length) * off
            cand = Zone(round(zn, 1), round(ze, 1), radius)
            clear_gates = all(math.hypot(g.north_m - zn, g.east_m - ze) > radius + 3.0 for g in gates)
            clear_home = math.hypot(zn, ze) > radius + 3.0
            if clear_gates and clear_home and math.hypot(zn, ze) < FENCE_M:
                zone = cand
                break

    wind = round(rng.uniform(0.0, 5.0), 1) if rng.random() < 0.5 else 0.0
    return Course(seed, tuple(gates), wind, round(rng.uniform(0, 360), 1), zone)


def _reference_velocity(pos, gate, zone, vmax):
    """The independent reference controller: steer straight at the gate, and push away from a zone if close. It sees
    the true position. This is deliberately simple and shares nothing with Telohelm's procedures."""
    tn, te = gate.north_m - pos[0], gate.east_m - pos[1]
    d = math.hypot(tn, te)
    vn, ve = (tn / d * vmax, te / d * vmax) if d > 1e-6 else (0.0, 0.0)
    if zone is not None:
        zn, ze = pos[0] - zone.north_m, pos[1] - zone.east_m
        dz = math.hypot(zn, ze)
        buffer = zone.radius_m + 6.0
        if dz < buffer and dz > 1e-6:
            push = (buffer - dz) / buffer * vmax * 1.5
            vn += zn / dz * push
            ve += ze / dz * push
    sp = math.hypot(vn, ve)
    if sp > vmax:
        vn, ve = vn / sp * vmax, ve / sp * vmax
    return vn, ve


def reference_path(course: Course, dt: float = 0.1):
    """The reference controller's path through the course, as a list of (north, east). For previews and plots."""
    pos = (0.0, 0.0); vmax = course.max_speed_ms; path = [pos]
    for gate in course.gates:
        guard = 0.0
        while math.hypot(gate.north_m - pos[0], gate.east_m - pos[1]) > gate.radius_m and guard < 400.0:
            vn, ve = _reference_velocity(pos, gate, course.zone, vmax)
            pos = (pos[0] + vn * dt, pos[1] + ve * dt); path.append(pos); guard += dt
    return path


def certify(course: Course, dt: float = 0.1) -> dict:
    """Fly the reference controller through the course as a point mass. Certified if it passes every gate in order
    without entering the zone or leaving the fence, within a generous time. Deterministic, no simulator."""
    pos = (0.0, 0.0)
    vmax = course.max_speed_ms
    t = 0.0
    straight = sum(math.hypot(course.gates[i].north_m - (0.0 if i == 0 else course.gates[i - 1].north_m),
                              course.gates[i].east_m - (0.0 if i == 0 else course.gates[i - 1].east_m))
                   for i in range(len(course.gates)))
    time_cap = straight / vmax * 3.0 + 30.0
    for idx, gate in enumerate(course.gates):
        guard = 0.0
        while math.hypot(gate.north_m - pos[0], gate.east_m - pos[1]) > gate.radius_m:
            vn, ve = _reference_velocity(pos, gate, course.zone, vmax)
            pos = (pos[0] + vn * dt, pos[1] + ve * dt)
            t += dt
            guard += dt
            if math.hypot(pos[0], pos[1]) > course.fence_m:
                return {"certified": False, "reason": f"reference left the fence near gate {idx + 1}", "seconds": round(t, 1)}
            if course.zone is not None and math.hypot(pos[0] - course.zone.north_m, pos[1] - course.zone.east_m) < course.zone.radius_m:
                return {"certified": False, "reason": f"reference could not avoid the zone near gate {idx + 1}", "seconds": round(t, 1)}
            if t > time_cap or guard > time_cap:
                return {"certified": False, "reason": f"reference ran out of time at gate {idx + 1}", "seconds": round(t, 1)}
    return {"certified": True, "reason": "reference controller flew the course", "seconds": round(t, 1),
            "gates": len(course.gates)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seed", type=int, help="print and certify one course")
    p.add_argument("--zone", action="store_true", help="include a no-go zone")
    p.add_argument("--check", nargs=2, type=int, metavar=("LO", "HI"), help="certify every seed in [LO, HI)")
    args = p.parse_args(argv)
    if args.check:
        lo, hi = args.check
        bad = []
        for s in range(lo, hi):
            if not certify(generate(s, args.zone))["certified"]:
                bad.append(s)
        print(f"certified {hi - lo - len(bad)} of {hi - lo} seeds; failures: {bad}")
        return 0
    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    course = generate(seed, args.zone)
    result = certify(course)
    print(json.dumps({"course": course.as_dict(), "certification": result}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

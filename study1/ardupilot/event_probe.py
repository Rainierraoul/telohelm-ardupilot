"""See how ArduPilot itself reacts to each contested-environment event, before Telohelm is involved.

Run from paper3/:  .venv/bin/python -m ardupilot.event_probe --out runs/event-probe-1 [EVENT ...]
For each event a fresh copter hovers in guided mode at 10 m, holding still by command once a second. The event starts
15 s in and lasts 30 s; the hover is watched for 30 s more. Every second records ArduPilot's mode, its position
estimate, the simulator's true position, GPS fix and satellites, the estimate's health flags and battery voltage.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .vehicle import HOME, M_PER_DEG_LAT, Sitl

START, LENGTH, AFTER = 15, 30, 30
EAST_DEG_PER_M = 1.0 / (M_PER_DEG_LAT * math.cos(math.radians(HOME[0])))


def jam(sim, t, on):
    if t == START:
        sim.set_param('SIM_GPS1_JAM', 1)
    elif t == START + LENGTH:
        sim.set_param('SIM_GPS1_JAM', 0)


def spoof(sim, t, on):
    """Drag the reported position 40 m east over 20 s, hold it there, then let it snap back."""
    if START <= t <= START + LENGTH:
        metres = min(40.0, 2.0 * (t - START))
        sim.set_param('SIM_GPS1_GLTCH_Y', metres * EAST_DEG_PER_M)
    elif t == START + LENGTH + 1:
        sim.set_param('SIM_GPS1_GLTCH_Y', 0)


def motor(sim, t, on):
    if t == START:
        sim.set_param('SIM_ENGINE_MUL', 0.6)
        sim.set_param('SIM_ENGINE_FAIL', 1)
    elif t == START + LENGTH:
        sim.set_param('SIM_ENGINE_FAIL', 0)


def gust(sim, t, on):
    if t == START:
        sim.set_param('SIM_WIND_SPD', 12)
        sim.set_param('SIM_WIND_TURB', 4)
    elif t == START + LENGTH:
        sim.set_param('SIM_WIND_SPD', 0)
        sim.set_param('SIM_WIND_TURB', 0)


def link(sim, t, on):
    pass  # handled by not commanding during the window


def rc(sim, t, on):
    """The pilot's radio control link fails (ArduPilot's default answer is to return to launch)."""
    if t == START:
        sim.set_param('SIM_RC_FAIL', 1)
    elif t == START + LENGTH:
        sim.set_param('SIM_RC_FAIL', 0)


def weak(multiplier):
    def event(sim, t, on):
        if t == START:
            sim.set_param('SIM_ENGINE_MUL', multiplier)
            sim.set_param('SIM_ENGINE_FAIL', 1)
        elif t == START + LENGTH:
            sim.set_param('SIM_ENGINE_FAIL', 0)
    return event


EVENTS = {'jam': jam, 'spoof': spoof, 'link': link, 'motor': motor, 'gust': gust, 'rc': rc,
          'motor85': weak(0.85), 'motor75': weak(0.75)}


def probe(name, folder, speedup):
    sim = Sitl(folder, 'copter', speedup)
    rows = []
    try:
        sim.prepare(alt_m=10.0)
        t0, hold = sim.state['t'], None
        for t in range(START + LENGTH + AFTER):
            on = START <= t < START + LENGTH
            EVENTS[name](sim, t, on)
            if hold is None:
                hold = (sim.state['north'], sim.state['east'])
            if not (name == 'link' and on):
                sim.command_velocity(0.0, 0.0)
            sim.advance_to(t0 + t + 1)
            s = sim.state
            err = (math.hypot(s['north'] - s['true_north'], s['east'] - s['true_east'])
                   if s['true_north'] is not None else None)
            rows.append({'t': t + 1, 'event_on': on, 'mode': s['mode'], 'armed': s['armed'],
                         'est_north': round(s['north'], 2), 'est_east': round(s['east'], 2),
                         'true_north': round(s['true_north'], 2), 'true_east': round(s['true_east'], 2),
                         'estimate_error_m': round(err, 2) if err is not None else None,
                         'est_alt': round(-s['down'], 2), 'true_alt': s['true_alt'],
                         'gps_fix': s['gps_fix'], 'gps_sats': s['gps_sats'], 'ekf_flags': s['ekf_flags'],
                         'battery_v': s['battery_v']})
            if not s['armed']:
                break
    finally:
        sim.close()
    true_drift = [math.hypot(r['true_north'] - hold[0], r['true_east'] - hold[1]) for r in rows] if hold else []
    summary = {'event': name, 'seconds': len(rows), 'modes': sorted({r['mode'] for r in rows}),
               'armed_at_end': rows[-1]['armed'] if rows else None,
               'max_estimate_error_m': max((r['estimate_error_m'] or 0) for r in rows) if rows else None,
               'max_true_drift_m': round(max(true_drift), 1) if true_drift else None,
               'min_alt_m': min(r['est_alt'] for r in rows) if rows else None,
               'ekf_flags_seen': sorted({r['ekf_flags'] for r in rows}),
               'messages': [x for x in sim.texts if x['t'] >= sim.texts[0]['t']][-25:] if sim.texts else []}
    return rows, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('events', nargs='*', default=list(EVENTS))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--speedup', type=float, default=10.0)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True)
    for name in args.events:
        rows, summary = probe(name, args.out / name / 'simulator', args.speedup)
        (args.out / name / 'seconds.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        (args.out / name / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
        print(json.dumps({k: v for k, v in summary.items() if k != 'messages'}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

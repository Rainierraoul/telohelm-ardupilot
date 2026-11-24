"""Measure how well a learned procedure generalises to unseen, certified courses.

This produces the first result the current system can report (PAPER-DRAFT.md, 5.1): Telohelm's adopted 'reach' procedure,
learned only to fly to a single point and hold, flown with no model calls through many multi-gate courses it never saw,
each generated from a reserved seed and certified flyable by an independent reference controller first.

It reports, with denominators: how many seeds certify, how many certified courses the learned procedure completes, the
gates passed, the failure reasons, the model-call count (zero by construction), and a repeatability check (a subset
flown several times, with the agreement of their endings). Development seeds and this held-out range must not overlap.

Run from paper3/ (when no other process is using SITL):
  .venv/bin/python -m ardupilot.course_study --from-run runs/reach-hold-gem-sonnet-2 --seeds 500000 500060 \
      --repeat-seeds 500000 500010 --repeats 3 --instance 3 --out runs/course-study-1
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

from . import battle
from . import course as C
from .course_run import fly_course


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--from-run', type=Path, required=True)
    p.add_argument('--seeds', nargs=2, type=int, required=True, metavar=('LO', 'HI'), help='held-out seed range [LO,HI)')
    p.add_argument('--repeat-seeds', nargs=2, type=int, metavar=('LO', 'HI'), help='subset flown several times')
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--zone', action='store_true')
    p.add_argument('--gate-radius', type=float, default=C.GATE_RADIUS_M, help='pass radius in metres (default 3)')
    p.add_argument('--speedup', type=float, default=10.0)
    p.add_argument('--instance', type=int, default=3)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)

    out = Path(args.out).resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; records are never overwritten')
    out.mkdir(parents=True)
    source = battle.adopted_source(args.from_run)
    started = time.monotonic()
    lo, hi = args.seeds
    rows, certified = [], 0
    for seed in range(lo, hi):
        course = C.generate(seed, args.zone, gate_radius=args.gate_radius)
        cert = C.certify(course)
        if not cert['certified']:
            rows.append({'seed': seed, 'certified': False, 'reason': cert['reason']})
            continue
        certified += 1
        rec = fly_course(course, source, str(args.from_run), out / f'seed-{seed}', speedup=args.speedup,
                         gazebo=False, instance=args.instance)
        rows.append({'seed': seed, 'certified': True, 'completed': rec['completed'],
                     'gates': rec['gates'], 'gates_passed': rec['gates_passed'], 'end_reason': rec['end_reason'],
                     'model_calls': rec['provenance']['model_calls'],
                     'steps': rec['provenance'].get('control_steps'),
                     'steps_without_procedure': rec['provenance'].get('steps_without_procedure'),
                     'wind_ms': course.wind_ms, 'gate_radius_m': args.gate_radius})
        done = [r for r in rows if r.get('certified')]
        print(f"seed {seed}: {'completed' if rec['completed'] else rec['end_reason']} "
              f"({rec['gates_passed']}/{rec['gates']} gates); running completion "
              f"{sum(r.get('completed', False) for r in done)}/{len(done)}", flush=True)
        _write(out, rows, certified, lo, hi, args, started, None)

    # Repeatability: fly a subset several times and record how often the ending agrees.
    repeat = None
    if args.repeat_seeds:
        rlo, rhi = args.repeat_seeds
        repeat = []
        for seed in range(rlo, rhi):
            course = C.generate(seed, args.zone, gate_radius=args.gate_radius)
            if not C.certify(course)['certified']:
                continue
            endings = []
            for k in range(args.repeats):
                rec = fly_course(course, source, str(args.from_run), out / f'repeat-{seed}-{k}',
                                 speedup=args.speedup, gazebo=False, instance=args.instance)
                endings.append(rec['end_reason'])
            agree = max(Counter(endings).values())
            repeat.append({'seed': seed, 'endings': endings, 'agreement': f'{agree}/{len(endings)}'})
            print(f"repeat seed {seed}: {endings} agree {agree}/{len(endings)}", flush=True)
    _write(out, rows, certified, lo, hi, args, started, repeat)
    return 0


def _write(out, rows, certified, lo, hi, args, started, repeat):
    flown = [r for r in rows if r.get('certified')]
    completed = sum(r.get('completed', False) for r in flown)
    gates_total = sum(r.get('gates', 0) for r in flown)
    gates_passed = sum(r.get('gates_passed', 0) for r in flown)
    summary = {
        'scope': 'development system, held-out courses; result for PAPER-DRAFT.md 5.1',
        'from_run': str(args.from_run), 'seed_range': [lo, hi], 'zone': args.zone,
        'seeds_tried': hi - lo, 'certified': certified,
        'courses_flown': len(flown), 'completed': completed,
        'completion_rate': round(completed / len(flown), 3) if flown else None,
        'gates_passed': gates_passed, 'gates_total': gates_total,
        'gate_rate': round(gates_passed / gates_total, 3) if gates_total else None,
        'gate_radius_m': args.gate_radius,
        'model_calls_total': sum(r.get('model_calls', 0) for r in flown),   # the runner has no model; zero by construction
        'control_steps': sum(r.get('steps') or 0 for r in flown),
        'steps_without_procedure': sum(r.get('steps_without_procedure') or 0 for r in flown),
        'courses_with_wind': sum(1 for r in flown if (r.get('wind_ms') or 0) > 0),
        'end_reasons': dict(Counter(r.get('end_reason') for r in flown)),
        'repeatability': repeat,
        'elapsed_seconds': round(time.monotonic() - started),
    }
    (out / 'rows.json').write_text(json.dumps(rows, indent=1))
    (out / 'summary.json').write_text(json.dumps(summary, indent=1))


if __name__ == '__main__':
    raise SystemExit(main())

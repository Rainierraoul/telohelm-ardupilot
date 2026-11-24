"""Carry the learned reach3d skill into the race3d task, as the designer's one adaptation.

A reach3d procedure reads its target from ctx.goal.target_north_m, target_east_m and target_alt_m. The race3d task gives
the whole gate list and ctx.gates_passed instead. This rewrites the procedure's source so it reads the next gate as its
target, and changes nothing else: same gains, limits, threat and fence handling. It is a designer's edit, recorded in
DESIGNER-KNOWLEDGE.md, so a race3d run that starts from it starts from a known, working but slow skill rather than from
nothing. Whatever the learner then adopts replaces it.

Run from paper3/:
  .venv/bin/python -m ardupilot.retarget --from-run runs/reach3d-demo
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import battle

GOAL_LINE = '    g = ctx.goal\n'
NEXT_GATE = '    gate = g.gates[min(ctx.gates_passed, len(g.gates) - 1)]\n'
FIELDS = (('g.target_north_m', 'gate.north_m'), ('g.target_east_m', 'gate.east_m'), ('g.target_alt_m', 'gate.alt_m'))


def reach3d_to_race3d(source: str) -> str:
    if source.count(GOAL_LINE) != 1:
        raise ValueError('expected exactly one "g = ctx.goal" line to anchor the next-gate lookup')
    out = source.replace(GOAL_LINE, GOAL_LINE + NEXT_GATE)
    for old, new in FIELDS:
        if old not in out:
            raise ValueError(f'{old} not found; this does not look like a reach3d procedure')
        out = out.replace(old, new)
    if 'target_' in out:
        raise ValueError('a target field is left after retargeting')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--from-run', type=Path, required=True)
    args = p.parse_args(argv)
    print(reach3d_to_race3d(battle.adopted_source(args.from_run)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

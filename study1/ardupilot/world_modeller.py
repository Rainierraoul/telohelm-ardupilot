"""The world-modeller: turn a mission goal into a task tree and a focused world per subtask.

This is the first version of the piece Simon asked for. Given a mission goal, it does a hierarchical task analysis:
it decomposes the mission into subtasks (the capabilities the library must hold), writes a readable task tree, and for
each subtask generates a graded curriculum of focused scenarios in that subtask's cheap world. Telohelm then learns and
adopts one procedure per subtask (ardupilot/learn.py), and the mission plan composes them to fly the whole mission
(ardupilot/course_run.py). The decomposition is written out so a person can read and check it, like the procedures.

The subtask catalogue is the existing task packs (reach, avoid, orbit, land). The decomposition here is rule-based over
that catalogue, which keeps it inspectable and reproducible; a later version can let a language model propose the tree
from a free-text goal, emitting the same structure. The mission plan is the task-analysis "plan": the order the
subtasks run in.

Run from paper3/:
  python -m ardupilot.world_modeller --mission-seed 7 --out runs/mission-7
  python -m ardupilot.world_modeller --legs reach avoid orbit land --out runs/mission-demo
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, asdict
import json
import math
from pathlib import Path
import random

from . import battle
from . import pack as P

# Each subtask capability: a plain description, and the disturbance it most needs to learn to handle. The curriculum
# grades from calm, through wind, to that disturbance, so a subtask learns one hard thing on top of the basics.
CAPABILITIES = {
    'reach': ('fly to a point and hold there', 'gust'),
    'avoid': ('reach a point while staying out of a no-go zone', 'threat'),
    'orbit': ('fly a circle around a point', 'spoof'),
    'land': ('descend gently onto a point', 'spoof'),
}


@dataclass(frozen=True)
class Leg:
    """One step of the mission: do this subtask at this place."""
    subtask: str
    label: str


@dataclass(frozen=True)
class Mission:
    seed: int
    legs: tuple
    note: str = ''


def random_mission(seed: int) -> Mission:
    """A mission from a seed: take off, a few subtasks in order, then land."""
    rng = random.Random(f'mission/{seed}')
    middle = rng.sample(['reach', 'avoid', 'orbit'], rng.randint(2, 3))
    legs = [Leg('reach', 'climb out and reach the first waypoint')]
    for i, s in enumerate(middle, 1):
        legs.append(Leg(s, f'{CAPABILITIES[s][0]} (waypoint {i})'))
    legs.append(Leg('land', 'return and land on the pad'))
    return Mission(seed, tuple(legs), note='generated from a seed')


def mission_from_legs(legs: list[str]) -> Mission:
    for s in legs:
        if s not in CAPABILITIES:
            raise ValueError(f'unknown subtask {s!r}; known: {sorted(CAPABILITIES)}')
    return Mission(0, tuple(Leg(s, CAPABILITIES[s][0]) for s in legs), note='given as a list of legs')


def interface_of(subtask: str) -> dict:
    """The observation and action contract the subtask's procedures run against (from the task pack)."""
    pack = P.PACKS[subtask]
    return {'observes': list(pack.roles.needs['control']),
            'acts': sorted(P.TASKS[subtask].fields),
            'succeeds_when': P.TASKS[subtask].success}


def curriculum(subtask: str, seeds: int = 4) -> list:
    """Graded learning scenarios for one subtask: calm first, then wind, then its key disturbance. Each is a focused
    world holding one kind of difficulty, so the subtask learns one hard thing at a time."""
    _, key = CAPABILITIES[subtask]
    stages = [('calm', 'basics, no disturbance'), ('gust', 'wind and turbulence')]
    if key not in ('gust',):
        stages.append((key, f'the {subtask} subtask\'s hard case'))
    out = []
    for family, why in stages:
        if family == 'threat' and subtask == 'orbit':
            continue                      # the generator does not place a zone for an orbit
        scenarios = [battle.generate(subtask, family, 7_000_000 + s) for s in range(seeds)]
        out.append({'stage': family, 'why': why, 'count': len(scenarios),
                    'example_events': list(scenarios[0].events)})
    return out


def decompose(mission: Mission) -> dict:
    """The hierarchical task analysis: the mission, the distinct subtask capabilities it needs (learned once each), and
    the plan that orders the legs. Each capability carries its interface and its learning curriculum."""
    order, seen = [], set()
    for leg in mission.legs:
        if leg.subtask not in seen:
            seen.add(leg.subtask)
            order.append(leg.subtask)
    capabilities = []
    for s in order:
        capabilities.append({'subtask': s, 'does': CAPABILITIES[s][0], 'key_disturbance': CAPABILITIES[s][1],
                             'interface': interface_of(s), 'curriculum': curriculum(s)})
    return {
        'mission': {'seed': mission.seed, 'note': mission.note,
                    'legs': [{'subtask': l.subtask, 'label': l.label} for l in mission.legs]},
        'capabilities_to_learn': capabilities,
        'plan': [l.subtask for l in mission.legs],
        'how_to_use': ('Learn one procedure per capability with ardupilot/learn.py on its curriculum, each adopted by '
                       'the monitor. Then compose: the plan orders the adopted procedures to fly the whole mission, '
                       'tested in SITL or Gazebo.'),
    }


def outline(tree: dict) -> str:
    """A readable task tree for a person to check."""
    m = tree['mission']
    lines = [f"MISSION (seed {m['seed']}): {m['note']}"]
    for i, leg in enumerate(m['legs'], 1):
        lines.append(f"  leg {i}: {leg['label']}  [{leg['subtask']}]")
    lines.append("")
    lines.append("CAPABILITIES TO LEARN (each once, reused across legs):")
    for c in tree['capabilities_to_learn']:
        lines.append(f"  - {c['subtask']}: {c['does']}  (hard case: {c['key_disturbance']})")
        lines.append(f"      observes {len(c['interface']['observes'])} raw fields, acts with {c['interface']['acts']}, "
                     f"succeeds when end reason is '{c['interface']['succeeds_when']}'")
        for stage in c['curriculum']:
            lines.append(f"      curriculum stage '{stage['stage']}' ({stage['why']}): {stage['count']} scenarios")
    lines.append("")
    lines.append("PLAN (order the adopted procedures run to fly the mission): " + " -> ".join(tree['plan']))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--mission-seed', type=int, help='generate a mission from a seed')
    g.add_argument('--legs', nargs='+', help='give the mission as a list of subtasks (reach avoid orbit land)')
    p.add_argument('--out', type=Path, help='write the task tree and outline here')
    args = p.parse_args(argv)

    mission = random_mission(args.mission_seed) if args.mission_seed is not None else mission_from_legs(args.legs)
    tree = decompose(mission)
    text = outline(tree)
    print(text)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'task-tree.json').write_text(json.dumps(tree, indent=1, default=str))
        (out / 'task-tree.txt').write_text(text + "\n")
        print(f"\nwrote {out}/task-tree.json and task-tree.txt")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

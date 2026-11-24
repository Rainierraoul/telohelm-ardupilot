"""How Study 1's 3 m clearance rule placed the targets of its zone flights (Section 4.2 of the paper and S14).

    python3 study1/manuscript/study1_target_clearance.py study1

The argument is the folder that holds Study 1's ardupilot/ and protocol/ (study1/ in the code deposit, where this
script sits in manuscript/). For reach, reach3d and land, and for each of Study 1's five zone seeds (seeds-2.json),
the script builds the layout twice with Study 1's own generator: once with its rule that a target lies at least
THREAT_CLEAR_M = 3.0 m beyond the zone's far edge, and once with that rule switched off. The zone's centre lies on the
line from home to the target, so a target's place is its distance from home against the zone's near and far edges on
that line. For each layout the script prints whether the rule moved the target and, with and without the rule, the
target's distance beyond the zone's far edge and whether it lay short of the zone, inside it or beyond it; then the
totals. Flies nothing and writes nothing."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from ardupilot import battle, scored  # noqa: E402

RULE_M = battle.THREAT_CLEAR_M
assert RULE_M == 3.0, RULE_M


def layout(task, seed, clear_m):
    battle.THREAT_CLEAR_M = clear_m
    try:
        scenario = battle.generate(task, 'threat', seed)
    finally:
        battle.THREAT_CLEAR_M = RULE_M
    p = dict(scenario.params)
    zone = scenario.events[0]
    target = (p['target_north_m'], p['target_east_m'])
    from_home, centre, radius = math.hypot(*target), math.hypot(zone[3], zone[4]), zone[5]
    beyond_far_edge = from_home - (centre + radius)
    place = 'short' if from_home < centre - radius else 'inside' if beyond_far_edge <= 0 else 'beyond'
    return target, beyond_far_edge, place


scored.use_protocol(2)   # Study 1 flew under the second protocol, with seeds-2.json (zone seeds 43001 to 43005)
seeds = scored.seeds()['disturbance']['threat']
assert seeds == [43001, 43002, 43003, 43004, 43005], seeds
from collections import Counter
moved, without, with_rule = 0, Counter(), []
print('task      seed  moved  without the rule: beyond far edge (m), place   with it: beyond far edge (m), place')
for task in ('reach', 'reach3d', 'land'):
    for seed in seeds:
        target_a, gap_a, place_a = layout(task, seed, RULE_M)
        target_b, gap_b, place_b = layout(task, seed, -1000.0)   # a clearance no layout fails: no target is moved
        was_moved = target_a != target_b
        assert place_a == 'beyond' and gap_a >= RULE_M - 0.05, (task, seed, gap_a)   # 0.05: coordinates kept to 0.1 m
        assert was_moved or (gap_a, place_a) == (gap_b, place_b), (task, seed)
        moved += was_moved
        if was_moved:
            without[place_b] += 1
        with_rule.append(gap_a)
        print(f'{task:8s} {seed:5d}  {"yes" if was_moved else "no ":5s}  {gap_b:35.2f}, {place_b:6s}   '
              f'{gap_a:28.2f}, {place_a}')
n = len(with_rule)
print(f'\nThe rule moved {moved} of {n} targets. Without it, of those {moved}, {without["short"]} would have lain short of '
      f'the zone, {without["inside"]} inside it and {without["beyond"]} beyond it but less than {RULE_M:g} m from its far edge.')
print(f'With the rule the targets lay {min(with_rule):.1f} to {max(with_rule):.1f} m beyond the zone\'s far edge.')

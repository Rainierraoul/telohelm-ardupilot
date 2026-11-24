"""Reserve protocol-3 cohorts before use, without calling a model or simulator.

Build distinct task/band/role seeds -> compare all numbers with protocol1/2
reservations and recorded run identities -> refuse overlap -> write once.
--check validates an existing reservation without overwriting it; freshness
against actual run records is checked at creation, not after its legitimate use.
Block b of task t, band j has the number base + 10000 t + 100 b + j + 1, whatever the block count, so a larger --blocks only
adds blocks at the end: blocks 0 to 31 keep the numbers of the 32-block book, and every other section is the same. Ruling 88
(19 November 2026) set 40 blocks, which reserves blocks 32 to 39 (numbers 3003201 to 3003903, 3013201 to 3013903 and 3023201
to 3023903). Run it with the earlier file moved away; the 40-block book was checked entry by entry against it
(test_protocol3.py, test_blocks_0_to_31_keep_their_seeds).
Generation
never silently replaces a reservation, including a pre-freeze draft.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol.contract3 import ARMS, BANDS, SEED_PATH, TASKS
from protocol import make_seeds_2 as old


def cohort(base: int, blocks: int, per_band: int, retention: int) -> dict:
    return {
        'blocks': {task: [{band: base + ti * 10000 + bi * 100 + j + 1
                          for j, band in enumerate(BANDS)} for bi in range(blocks)]
                   for ti, task in enumerate(TASKS)},
        'threat_evaluation': {
            task: {band: [base + 100000 + ti * 10000 + j * 100 + k + 1 for k in range(per_band)]
                   for j, band in enumerate(BANDS)} for ti, task in enumerate(TASKS)},
        'heldout': {task: {family: list(range(base + 200000 + ti * 10000 + fi * 100 + 1,
                                             base + 200000 + ti * 10000 + fi * 100 + 1 + retention // 2))
                          for fi, family in enumerate(('calm', 'wind'))} for ti, task in enumerate(TASKS)},
    }


def build(blocks: int = 40) -> dict:
    if not 1 <= blocks <= 64:
        raise ValueError('Block bank supports 1 to 64 independent blocks per task')
    return {'version': 3, 'written_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'reservation': 'Prospective reservation; protocol freeze and launch approval are separate.',
            'design': {'blocks_per_task': blocks, 'tasks': list(TASKS), 'arms': list(ARMS),
                       'bands_m': {'close': [3, 4], 'middle': [9, 11], 'wide': [19, 21]},
                       'evaluation_per_band': 8, 'retention_per_task': 10,
                       'pilot_blocks_per_task': 4, 'pilot_evaluation_per_band': 2,
                       'pilot_retention_per_task': 4},
            **cohort(3000000, blocks, 8, 10), 'pilot': cohort(4000000, 4, 2, 4)}


def seed_numbers(seeds: dict) -> list:
    def leaves(value):
        if isinstance(value, int) and not isinstance(value, bool):
            yield value
        elif isinstance(value, list):
            for v in value:
                yield from leaves(v)
        elif isinstance(value, dict):
            for v in value.values():
                yield from leaves(v)
        else:
            raise ValueError('Unexpected value in seed lists')
    return list(leaves({k: seeds[k] for k in ('blocks', 'threat_evaluation', 'heldout', 'pilot')}))


def validate(seeds: dict, *, scan_runs: bool = True) -> dict:
    numbers = seed_numbers(seeds)
    if len(numbers) != len(set(numbers)):
        raise ValueError('A task, band, layout or cohort reuses a seed number')
    if (seeds['version'] != 3 or tuple(seeds['blocks']) != TASKS
            or tuple(seeds['design']['tasks']) != TASKS or tuple(seeds['design']['arms']) != ARMS
            or seeds['design']['bands_m'] != {'close': [3, 4], 'middle': [9, 11], 'wide': [19, 21]}):
        raise ValueError('Wrong protocol or task order')
    for pilot in (False, True):
        rows = seeds['pilot'] if pilot else seeds
        n = seeds['design']['pilot_blocks_per_task' if pilot else 'blocks_per_task']
        per = seeds['design']['pilot_evaluation_per_band' if pilot else 'evaluation_per_band']
        retention = seeds['design']['pilot_retention_per_task' if pilot else 'retention_per_task']
        for task in TASKS:
            if len(rows['blocks'][task]) != n:
                raise ValueError('Wrong block count')
            if any(tuple(b) != BANDS for b in rows['blocks'][task]):
                raise ValueError('Each learning block needs exactly one distinct seed per band')
            if tuple(rows['threat_evaluation'][task]) != BANDS or any(len(v) != per for v in rows['threat_evaluation'][task].values()):
                raise ValueError('Unequal or missing evaluation bands')
            if tuple(rows['heldout'][task]) != ('calm', 'wind') or any(len(v) != retention // 2 for v in rows['heldout'][task].values()):
                raise ValueError('Wrong retention set')
    taken = old.first_protocol_reserved() | old.wanted() | old.pilot_identities()
    if scan_runs:
        taken |= old.used_in_runs()
    old_numbers = {row[-1] for row in taken}
    overlap = set(numbers) & old_numbers
    if overlap:
        raise ValueError(f'Seed numbers already used/reserved: {sorted(overlap)[:10]}')
    return {'ok': True, 'reserved_numbers': len(numbers), 'historical_numbers_checked': len(old_numbers),
            'run_records_scanned': scan_runs, 'blocks_per_task': seeds['design']['blocks_per_task']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=SEED_PATH)
    parser.add_argument('--blocks', type=int, default=40)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    seeds = json.loads(args.out.read_text()) if args.check else build(args.blocks)
    checked = validate(seeds, scan_runs=not args.check)
    if not args.check:
        with args.out.open('x') as f:
            json.dump(seeds, f, indent=2)
            f.write('\n')
    print(json.dumps(checked, indent=2))


if __name__ == '__main__':
    main()

"""Write paper 3's reserved scored seeds (seeds.json) and check them against every scenario development used.

Run from paper3/:  .venv/bin/python protocol/make_seeds.py

Scenario seeds live in per-generator namespaces: battle.generate uses "{task}/{family}/{seed}", the course generators
"course/{seed}" and "course3d/{seed}". A scored seed is refused if the same (generator, task, family, seed) appears in
any saved development run. Ranges are also kept clear of the development ranges named in PROTOCOL.md section 5.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ('reach', 'avoid', 'orbit', 'land', 'reach3d')
DISTURBANCES = ('jam', 'spoof', 'rc_loss', 'gust', 'motor', 'threat')

SEEDS = {
    'version': 1,
    'written': '2 November 2026',
    'learning': {t: [[1000 + 100 * r + i for i in (1, 2, 3)] for r in range(5)] for t in TASKS},
    'heldout': {'calm': list(range(20001, 20021)), 'wind': list(range(21001, 21011))},
    # Never flown. The attribution check looks for these scenarios' numbers in the learning requests too, so the
    # held-out match count can be read against the count that chance alone gives (added after the pilot).
    'attribution_control': {'calm': list(range(22001, 22021)), 'wind': list(range(23001, 23011))},
    'repeatability': {'calm': list(range(20001, 20006)), 'repeats': 3},
    'disturbance': {f: list(range(30001, 30006)) for f in DISTURBANCES},
    'courses_flat': [520000, 520030],
    'courses_3d': [620000, 620020],
    'pilot': {'learning': [9001, 9002, 9003], 'heldout_calm': [9101, 9102, 9103, 9104, 9105], 'disturbance': [9201]},
    'notes': ('learning[task][run] are the three calm learning scenarios of run 0-4. heldout and disturbance seeds are '
              'shared by every task, each in its own task namespace. Orbit has no threat family. Course ranges are '
              'half-open [lo, hi). attribution_control seeds are never flown. Pilot seeds are development seeds; nothing from the pilot is reported.'),
}


def used_in_development():
    used = set()
    for cfg in glob.glob(str(ROOT / 'runs' / '*' / 'run-config.json')):
        try:
            c = json.loads(Path(cfg).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for s in c.get('scenarios') or []:
            eid = s.get('episode_id', '')
            if '-' in eid and eid.rsplit('-', 1)[1].isdigit():
                fam, seed = eid.rsplit('-', 1)
                used.add(('battle', s.get('task') or c.get('task'), fam, int(seed)))
    for res in glob.glob(str(ROOT / 'runs' / '*' / 'results.jsonl')):
        task = json.loads((Path(res).parent / 'summary.json').read_text()).get('task') if (Path(res).parent / 'summary.json').exists() else None
        for line in Path(res).read_text().splitlines():
            r = json.loads(line)
            if 'family' in r and 'seed' in r:
                used.add(('battle', task, r['family'], int(r['seed'])))
    for summ in glob.glob(str(ROOT / 'runs' / 'course*study*' / 'summary.json')):
        s = json.loads(Path(summ).read_text())
        lo, hi = s['seed_range']
        gen = 'course3d' if 'course3d' in summ else 'course'
        used.update((gen, None, None, k) for k in range(lo, hi))
    return used


def main():
    used = used_in_development()
    clashes = []
    for t in TASKS:
        for run in SEEDS['learning'][t]:
            clashes += [('battle', t, 'calm', k) for k in run if ('battle', t, 'calm', k) in used]
        for fam, seeds in (*SEEDS['heldout'].items(), *SEEDS['attribution_control'].items()):
            clashes += [('battle', t, fam, k) for k in seeds if ('battle', t, fam, k) in used]
        for fam, seeds in SEEDS['disturbance'].items():
            clashes += [('battle', t, fam, k) for k in seeds if ('battle', t, fam, k) in used]
    for gen, key in (('course', 'courses_flat'), ('course3d', 'courses_3d')):
        lo, hi = SEEDS[key]
        clashes += [(gen, None, None, k) for k in range(lo, hi) if (gen, None, None, k) in used]
    print(f'{len(used)} development scenario identities scanned; {len(clashes)} clashes')
    if clashes:
        raise SystemExit(f'refusing to write seeds.json: {clashes[:10]}')
    (ROOT / 'protocol' / 'seeds.json').write_text(json.dumps(SEEDS, indent=1) + '\n')
    print('wrote protocol/seeds.json')


if __name__ == '__main__':
    main()

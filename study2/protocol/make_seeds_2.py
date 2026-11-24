"""Write the second protocol's reserved seeds (protocol/seeds-2.json) and check them against every scenario identity
already used or reserved.

Run from paper3/:  .venv/bin/python protocol/make_seeds_2.py

The first protocol's seeds.json stays as it was frozen. Scenario seeds live in per-generator namespaces:
battle.generate uses "{task}/{family}/{seed}", the course generators "course/{seed}" and "course3d/{seed}". The
'matched' family is drawn from the threat family's stream (battle.matched_calm), so a matched learning seed uses the
threat identity of the same number, and the check treats it so. A seed is refused if its identity appears in any saved
run configuration or result file under runs/ (searched at every depth, which includes the first scored run, the
pilots and development), or in the first protocol's reserved ranges, including its attribution controls, which were
generated and searched although never flown (D3's review, 4 November 2026).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ('reach', 'avoid', 'orbit', 'land', 'reach3d')
STUDY2_TASKS = ('reach', 'reach3d', 'land')
DISTURBANCES = ('jam', 'spoof', 'rc_loss', 'gust', 'motor', 'threat')
BLOCKS = 8          # matched learning blocks reserved per Study 2 task; a smaller study uses the first ones
CALM_RUNS = 5       # Study 1's ordinary calm learning runs for avoid and orbit

SEEDS = {
    'version': 2,
    'written': '4 November 2026',
    # Study 2 and Study 1 for reach, reach3d and land: block b learns on these three layouts, once on the threat family
    # (the threat arm) and once on the matched family, the same layouts with the zones removed (the calm arm).
    'blocks': {t: [[40000 + 100 * b + i for i in (1, 2, 3)] for b in range(BLOCKS)] for t in STUDY2_TASKS},
    # Study 1 for avoid and orbit: ordinary calm learning, as in the first protocol.
    'learning_calm': {t: [[40000 + 100 * r + i for i in (1, 2, 3)] for r in range(CALM_RUNS)] for t in ('avoid', 'orbit')},
    'heldout': {'calm': list(range(41001, 41021)), 'wind': list(range(41101, 41111))},
    'attribution_control': {'calm': list(range(42001, 42021)), 'wind': list(range(42101, 42111)),
                            'threat': list(range(45001, 45021))},
    'repeatability': {'calm': list(range(41001, 41006)), 'repeats': 3},
    'disturbance': {f: list(range(43001, 43006)) for f in DISTURBANCES},
    # Study 2's evaluation: every library of both arms flies these, learning off.
    'threat_evaluation': list(range(44001, 44021)),
    'courses_flat': [530000, 530030],
    'courses_3d': [630000, 630020],
    # Development seeds for checking the second protocol's scheduler and runners before the freeze. Nothing flown on
    # them is reported. Kept apart from the first protocol's pilot (9001 to 9204) and the threat and matched
    # learning pilots of 4 November (9301 to 9333).
    'pilot': {'blocks': {t: [9401, 9402, 9403] for t in STUDY2_TASKS}, 'learning_calm': [9411, 9412, 9413],
              'heldout_calm': [9501, 9502, 9503, 9504, 9505], 'disturbance': [9601], 'threat_evaluation': [9701, 9702]},
    'notes': ('blocks[task][b] are block b\'s three learning layouts for reach, reach3d and land, learned on the threat '
              'family (threat arm) and on the matched family (calm arm; battle.matched_calm). learning_calm[task][r] are '
              'avoid\'s and orbit\'s calm learning runs. heldout, disturbance and threat_evaluation seeds are shared by '
              'every task, each in its own task namespace. Orbit has no threat family; avoid is not in Study 2. Course '
              'ranges are half-open [lo, hi). attribution_control seeds are never flown.'),
}


def first_protocol_reserved() -> set:
    """Every identity the first protocol reserved, flown or not."""
    old = json.loads((ROOT / 'protocol' / 'seeds.json').read_text())
    out = set()
    for t in TASKS:
        for run in old['learning'][t]:
            out.update(('battle', t, 'calm', k) for k in run)
        for group in ('heldout', 'attribution_control'):
            for fam, seeds in old[group].items():
                out.update(('battle', t, fam, k) for k in seeds)
        for fam, seeds in old['disturbance'].items():
            out.update(('battle', t, fam, k) for k in seeds)
        for fam, seeds in old['pilot'].items():
            out.update(('battle', t, f, k) for k in seeds for f in ('calm', 'wind', *DISTURBANCES))
    for gen, key in (('course', 'courses_flat'), ('course3d', 'courses_3d')):
        lo, hi = old[key]
        out.update((gen, None, None, k) for k in range(lo, hi))
    return out


def used_in_runs() -> set:
    used = set()
    def add(task, eid):
        if '-' in eid and eid.rsplit('-', 1)[1].isdigit():
            fam, seed = eid.rsplit('-', 1)
            used.add(('battle', task, 'threat' if fam == 'matched' else fam, int(seed)))
    for cfg in (ROOT / 'runs').rglob('run-config.json'):
        try:
            c = json.loads(cfg.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for s in c.get('scenarios') or []:
            add(s.get('task') or c.get('task'), s.get('episode_id', ''))
    for res in (ROOT / 'runs').rglob('results.jsonl'):
        summary = res.parent / 'summary.json'
        task = json.loads(summary.read_text()).get('task') if summary.exists() else None
        for line in res.read_text().splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if 'family' in r and 'seed' in r:
                add(r.get('task') or task, f"{r['family']}-{r['seed']}")
    for summ in (ROOT / 'runs').rglob('summary.json'):
        try:
            s = json.loads(summ.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(s, dict) and isinstance(s.get('seed_range'), list) and len(s['seed_range']) == 2:
            lo, hi = s['seed_range']
            gen = 'course3d' if '3d' in str(summ) else 'course'
            used.update((gen, None, None, k) for k in range(lo, hi))
    return used


def wanted() -> set:
    w = set()
    for t, blocks in SEEDS['blocks'].items():
        w.update(('battle', t, 'threat', k) for b in blocks for k in b)   # matched uses the threat stream
    for t, runs in SEEDS['learning_calm'].items():
        w.update(('battle', t, 'calm', k) for r in runs for k in r)
    for t in TASKS:
        for group in ('heldout', 'attribution_control'):
            for fam, seeds in SEEDS[group].items():
                if not (fam == 'threat' and t not in STUDY2_TASKS):
                    w.update(('battle', t, fam, k) for k in seeds)
        for fam, seeds in SEEDS['disturbance'].items():
            if not (fam == 'threat' and t == 'orbit'):
                w.update(('battle', t, fam, k) for k in seeds)
    for t in STUDY2_TASKS:
        w.update(('battle', t, 'threat', k) for k in SEEDS['threat_evaluation'])
    for gen, key in (('course', 'courses_flat'), ('course3d', 'courses_3d')):
        lo, hi = SEEDS[key]
        w.update((gen, None, None, k) for k in range(lo, hi))
    return w


def pilot_identities() -> set:
    pl = SEEDS['pilot']
    out = set()
    for t in TASKS:
        for fam in ('calm', 'wind', 'threat', *DISTURBANCES):
            out.update(('battle', t, fam, k) for k in [*pl['learning_calm'], *pl['heldout_calm'], *pl['disturbance'],
                                                      *pl['threat_evaluation'], *(pl['blocks'].get(t) or [])])
    return out


def main():
    taken = used_in_runs() | first_protocol_reserved()
    w = wanted()
    overlap = sorted(w & pilot_identities(), key=str)
    if overlap:
        raise SystemExit(f'development seeds overlap reserved ones: {overlap[:5]}')
    clashes = sorted(w & taken, key=str)
    # Within the second protocol, no learning seed number is also a test or control seed number, in any family.
    learning = {k for bl in SEEDS['blocks'].values() for b in bl for k in b} | \
        {k for rs in SEEDS['learning_calm'].values() for r in rs for k in r}
    tests = {k for g in ('heldout', 'attribution_control', 'disturbance') for v in SEEDS[g].values() for k in v} | \
        set(SEEDS['threat_evaluation'])
    internal = sorted(learning & tests)
    print(f'{len(taken)} identities already used or reserved; {len(w)} wanted; {len(clashes)} clashes; '
          f'{len(internal)} learning/test overlaps')
    if clashes or internal:
        raise SystemExit(f'refusing to write seeds-2.json: {(clashes + internal)[:10]}')
    (ROOT / 'protocol' / 'seeds-2.json').write_text(json.dumps(SEEDS, indent=1) + '\n')
    print('wrote protocol/seeds-2.json')


if __name__ == '__main__':
    main()

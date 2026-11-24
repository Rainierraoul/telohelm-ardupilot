"""The analysis of Paper 3's extra experiment (PROTOCOL-EXTRA.md, section 8). No simulator or model is called.

  python extra/analysis_e.py STUDY2_RUNS EXTRA_SAVED TAG OUT_DIR

STUDY2_RUNS holds Study 2's run roots scored-20261120-S-<task>/ and its analysis folder scored-20261120-S-analysis/.
EXTRA_SAVED holds the jobs' saved folders as extra.sbatch leaves them: extra-TAG-<task>/runs/extra-TAG-<task>/ for arm E
(its learnE blocks, its own threat3 phases and the control's) and extra-TAG-all/runs/yard-TAG/ for the yardstick.
OUT_DIR is created and gets analysis-e.json and report-e.md. A threat3 folder in arm E's root whose name is also in
Study 2's root is a control phase; any other is arm E's own.

The outcome is Study 2's: for each block and each of the task's 24 zone evaluation flights, 1 if the arm adopted a
procedure and that procedure met the goal on the flight, else 0. Arms A, B and C are read from Study 2's records and
arm E from the extra experiment's; a source arm E shares with Study 2 in the same block (c0, or arm C's candidate when
the two requests were the same) is scored on Study 2's flights of that source.

The intervals come from analysis3.bootstrap, unchanged, on an array of the arms (A, B, C, E) with each task's own
generator, seeded as the primary pass seeds it ([BOOT_SEED, 0, task index]) and BOOT_N resamples. The draws of blocks and
flights depend only on the array's shape and the generator, so arms A, B and C get exactly the draws they had in Study 2,
and the script checks that its C - B and B - A, per task and pooled, equal Study 2's analysis.json to the last digit
before it reports anything about arm E. E - B and C - E are made from the same draws. The pooled value is the mean of
the three tasks, as in Study 2.

Over the blocks where c0 was valid and failed its zone trial, E - B and C - E come from the generator Study 2 used for its
conditional C - B there ([BOOT_SEED, 1, task index]), and that C - B must also equal Study 2's.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import analysis3 as A3  # noqa: E402
from protocol import contract3 as C3  # noqa: E402

ARMS = ('A', 'B', 'C', 'E')           # the array's arms; A, B and C stand where Study 2's primary pass had them
STEPS = {'E-B': ('E', 'B'), 'C-E': ('C', 'E'), 'C-B': ('C', 'B'), 'B-A': ('B', 'A')}
STUDY2 = 'scored-20261120-S-{task}'
SEEDS = json.loads(C3.SEED_PATH.read_text())


def flights(phase: Path) -> dict:
    """{episode id: outcome} of a finished evaluation phase (its done mark is checked by the caller)."""
    out = {}
    for f in sorted((phase / 'flights').glob('*/outcome.json')):
        out[f.parent.name] = json.loads(f.read_text())
    return out


def finished(root: Path, name: str) -> Path:
    phase = root / name
    if not (phase.is_dir() and (root / 'logs' / f'{name}.done').exists()):
        raise SystemExit(f'{phase} is not a finished phase')
    return phase


def load_task(task: str, s2: Path, ex: Path) -> dict:
    cases = C3.evaluation_cases(SEEDS, task)
    ids = [c.episode_id for c in cases]
    bands = [b for b in C3.BANDS for _ in SEEDS['threat_evaluation'][task][b]]
    blocks = range(len(SEEDS['blocks'][task]))
    y = np.zeros((len(ARMS), len(blocks), len(cases)))
    ends = {a: Counter() for a in ARMS}
    adopted = np.zeros((len(ARMS), len(blocks)), dtype=bool)
    detail, valid_failed = [], []
    for j, b in enumerate(blocks):
        learn2 = s2 / f'learn3-{task}-b{b}'
        arms2 = json.loads((learn2 / 'arms.json').read_text())['arms']
        e_rec = json.loads((ex / f'learnE-{task}-b{b}' / 'arms.json').read_text())
        if not (ex / 'logs' / f'learnE-{task}-b{b}.done').exists():
            raise SystemExit(f'arm E block {task} {b} has no done mark')
        rows = {a: arms2[a] for a in ('A', 'B', 'C')}
        rows['E'] = e_rec['arms']['E']
        for i, arm in enumerate(ARMS):
            row = rows[arm]
            if not row['adopted']:
                continue
            adopted[i, j] = True
            name = C3.phase_name('threat3', task, b, row['source_sha256'])
            # A source Study 2 flew in this block is scored on Study 2's flights; arm E's root may hold a control
            # flight of the same name, which is never scored.
            here = s2 if (s2 / name).is_dir() else ex
            got = flights(finished(here, name))
            if sorted(got) != sorted(ids):
                raise SystemExit(f'{here / name}: flights {sorted(got)[:3]}... are not the 24 scheduled')
            for k, cid in enumerate(ids):
                y[i, j, k] = bool(got[cid]['goal_met'])
                ends[arm][got[cid]['end_reason']] += 1
        c0 = json.loads((learn2 / 'candidates' / 'c0' / 'candidate.json').read_text())
        if c0['format_valid'] and not json.loads((learn2 / 'arms.json').read_text())['c0_zone_qualified']:
            valid_failed.append(j)
        detail.append({'block': b, 'E': rows['E']['candidate_id'], 'E_slots': [s['from'] for s in e_rec['slots']],
                       'C': rows['C']['candidate_id'], 'B': rows['B']['candidate_id']})
    return {'y': y, 'bands': bands, 'ends': ends, 'adopted': adopted, 'detail': detail, 'cases': ids,
            'valid_failed': valid_failed}


def steps_of(y, draws):
    points = y.mean(axis=(1, 2))
    out = {}
    for key, (a, b) in STEPS.items():
        i, k = ARMS.index(a), ARMS.index(b)
        out[key] = A3.estimate_record(points[i] - points[k], draws[i] - draws[k], (y[i], y[k]), y.shape[1])
    return out, points


def check_against_study2(result: dict, s2_analysis: dict) -> list:
    """Study 2's C - B and B - A, per task and pooled, must come out to the last digit."""
    bad = []
    for task in C3.TASKS:
        for key in ('C-B', 'B-A'):
            mine, theirs = result['tasks'][task]['steps'][key], s2_analysis['tasks'][task]['all_band_steps'][key]
            if (mine['estimate'], mine['ci95'], mine['ci90']) != (theirs['estimate'], theirs['ci95'], theirs['ci90']):
                bad.append(f'{task} {key}: {mine["estimate"]} {mine["ci95"]} against {theirs["estimate"]} {theirs["ci95"]}')
    for task in C3.TASKS:
        mine = result['tasks'][task]['conditional']['steps']['C-B']
        theirs = s2_analysis['tasks'][task]['conditional_first_qualification_failure']['C-B']
        if (mine['estimate'], mine['ci95'], mine['ci90']) != (theirs['estimate'], theirs['ci95'], theirs['ci90']):
            bad.append(f'{task} conditional C-B: {mine["estimate"]} {mine["ci95"]} against {theirs["estimate"]}')
    for key in ('C-B', 'B-A'):
        mine, theirs = result['pooled'][key], s2_analysis['primary']['pooled:' + key]
        if (mine['estimate'], mine['ci95'], mine['ci90']) != (theirs['estimate'], theirs['ci95'], theirs['ci90']):
            bad.append(f'pooled {key}: {mine["estimate"]} {mine["ci95"]} against {theirs["estimate"]} {theirs["ci95"]}')
    return bad


def usage_rows(ex: Path, task: str) -> list:
    rows = []
    for f in sorted(ex.glob(f'learnE-{task}-b*/usage.jsonl')):
        rows += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return rows


def provider_rows(ex: Path, task: str) -> list:
    rows = []
    for f in sorted(ex.glob(f'learnE-{task}-b*/claude-usage.jsonl')):
        rows += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return rows


def attempts(ex: Path, s2: Path, task: str) -> dict:
    """Slots and trials: for arm E's drawn candidates and, in the same blocks, arm C's repairs."""
    out = {'E': Counter(), 'C': Counter()}
    for learn in sorted(ex.glob(f'learnE-{task}-b*')):
        rec = json.loads((learn / 'arms.json').read_text())
        drawn = {s['candidate_id'] for s in rec['slots'] if s['from'] == 'drawn'}
        for t in rec['arms']['E']['trials']:
            if t['candidate_id'] in drawn:
                out['E']['slots'] += 1
                out['E']['valid'] += t['flight_dir'] is not None
                out['E']['passed'] += t['passed']
        arms2 = json.loads((s2 / f'learn3-{task}-b{rec["block"]}' / 'arms.json').read_text())['arms']
        if drawn:      # the same blocks: those where arm E had to draw (c0 valid and failed its zone trial)
            for t in arms2['C']['trials']:
                if t['candidate_id'] != 'c0':
                    out['C']['slots'] += 1
                    out['C']['valid'] += t['flight_dir'] is not None
                    out['C']['passed'] += t['passed']
    return {k: dict(v) for k, v in out.items()}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p from the two discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def control(task: str, s2: Path, ex: Path) -> dict:
    """PROTOCOL-EXTRA.md, section 6: the flights of each control phase (a threat3 folder in arm E's root whose name is in
    Study 2's root) against Study 2's flights of the same phase."""
    pairs, same_end = [], 0
    phases = sorted(p.name for p in ex.glob('threat3-*') if p.is_dir() and (s2 / p.name).is_dir())
    for name in phases:
        new, old = flights(finished(ex, name)), flights(finished(s2, name))
        for cid in sorted(old):
            pairs.append((bool(old[cid]['goal_met']), bool(new[cid]['goal_met'])))
            same_end += old[cid]['end_reason'] == new[cid]['end_reason']
    b = sum(o and not n for o, n in pairs)
    c = sum(n and not o for o, n in pairs)
    return {'phases': phases, 'flights': len(pairs), 'goal_met_study2': sum(o for o, _ in pairs),
            'goal_met_now': sum(n for _, n in pairs), 'met_then_not_now': b, 'met_now_not_then': c,
            'same_ending': same_end, 'mcnemar_exact_p': round(mcnemar_exact(b, c), 6),
            'reading': 'the platform is judged to have changed' if mcnemar_exact(b, c) < 0.05 else
                       'no change in goal met detected'}


def study2_reflights(s2: Path) -> dict:
    """Study 2's own repeats: each evaluation attempt set aside for a late flight, against the attempt kept. A baseline
    for the control, with the caveat that the set-aside attempts held late flights."""
    pairs, same_end = [], 0
    aside = Path(str(s2) + '.set-aside')
    for att in sorted(aside.glob('threat3-*-attempt*')):
        name = att.name.rsplit('-attempt', 1)[0]
        if not (s2 / name).is_dir():
            continue
        old, new = flights(att / name), flights(s2 / name)
        for cid in sorted(set(old) & set(new)):
            pairs.append((bool(old[cid]['goal_met']), bool(new[cid]['goal_met'])))
            same_end += old[cid]['end_reason'] == new[cid]['end_reason']
    return {'flights': len(pairs), 'same_goal_met': sum(o == n for o, n in pairs), 'same_ending': same_end}


def yardstick(yard: Path) -> dict:
    """The yardstick's scored flights: for each task and margin, goals met and zone entries out of 24, and the margin
    chosen on the development flights."""
    choice = json.loads((yard / 'yard-choice.json').read_text())
    out = {'choice': choice, 'tasks': {}}
    for task in C3.TASKS:
        ids = [c.episode_id for c in C3.evaluation_cases(SEEDS, task)]
        out['tasks'][task] = {}
        for m in (1, 2, 3, 4, 5):
            got = flights(finished(yard, f'yard3-{task}-m{m}'))
            if sorted(got) != sorted(ids):
                raise SystemExit(f'yard3-{task}-m{m}: not the 24 scheduled flights')
            ends = Counter(o['end_reason'] for o in got.values())
            out['tasks'][task][m] = {'flights': len(got), 'goal_met': sum(bool(o['goal_met']) for o in got.values()),
                                     'entered_zone': ends.get('entered_threat', 0), 'endings': dict(ends)}
    chosen = [out['tasks'][t][choice[t]['margin_m']] for t in C3.TASKS]
    out['chosen_pooled'] = {'flights': sum(r['flights'] for r in chosen), 'goal_met': sum(r['goal_met'] for r in chosen),
                            'entered_zone': sum(r['entered_zone'] for r in chosen)}
    return out


def analyse(s2_runs: Path, saved: Path, tag: str) -> dict:
    result = {'tasks': {}, 'pooled': {}}
    points, draws, cells = {}, {}, {}
    for task in C3.TASKS:
        s2 = s2_runs / STUDY2.format(task=task)
        ex = saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'
        d = load_task(task, s2, ex)
        idx = C3.TASKS.index(task)
        rng = np.random.default_rng([C3.BOOT_SEED, 0, idx])
        draws[task] = A3.bootstrap(d['y'], d['bands'], rng, C3.BOOT_N)
        steps, points[task] = steps_of(d['y'], draws[task])
        vf = d['valid_failed']
        sub = d['y'][:, vf, :]
        conditional = {'blocks': len(vf), 'rule': 'blocks where c0 was valid and failed its zone trial',
                       'steps': steps_of(sub, A3.bootstrap(sub, d['bands'], np.random.default_rng([C3.BOOT_SEED, 1, idx]),
                                                           C3.BOOT_N))[0]}
        cells[task] = d['y']
        y, adopted = d['y'], d['adopted']
        per_arm = {}
        for i, arm in enumerate(ARMS):
            n = int(adopted[i].sum())
            ends = d['ends'][arm]
            flown = n * y.shape[2]
            per_arm[arm] = {'adopted': n, 'blocks': y.shape[1], 'mean': round(float(y[i].mean()), 12),
                            'goal_met_among_flights_flown': round(float(y[i][adopted[i]].mean()), 12) if n else None,
                            'flights_flown': flown, 'entered_zone': ends.get('entered_threat', 0),
                            'entered_zone_share_of_flown': round(ends.get('entered_threat', 0) / flown, 12) if flown else None,
                            'endings': dict(ends)}
        rows = usage_rows(ex, task)
        prov = provider_rows(ex, task)
        result['tasks'][task] = {
            'steps': steps, 'conditional': conditional, 'arms': per_arm, 'blocks': d['detail'],
            'attempts': attempts(ex, s2, task),
            'calls': len(rows), 'list_cost_usd': round(sum(r.get('list_cost_usd') or 0 for r in rows), 6),
            'charged_usd': round(sum(r.get('charged_usd') or 0 for r in prov), 6),
            'served_by': dict(Counter(r.get('served_by') for r in rows)),
            'control': control(task, s2, ex),
        }
    pp = np.mean([points[t] for t in C3.TASKS], axis=0)
    pd = np.mean([draws[t] for t in C3.TASKS], axis=0)
    for key, (a, b) in STEPS.items():
        i, k = ARMS.index(a), ARMS.index(b)
        cell = tuple(np.concatenate([cells[t][x].ravel() for t in C3.TASKS]) for x in (i, k))
        result['pooled'][key] = A3.estimate_record(pp[i] - pp[k], pd[i] - pd[k], cell,
                                                   sum(cells[t].shape[1] for t in C3.TASKS))
    result['study2_reflights'] = {t: study2_reflights(s2_runs / STUDY2.format(task=t)) for t in C3.TASKS}
    yard = saved / f'extra-{tag}-all' / 'runs' / f'yard-{tag}'
    result['yardstick'] = yardstick(yard) if yard.is_dir() else None
    return result


def report(result: dict) -> str:
    lines = ['# Paper 3, extra experiment: results', '']
    lines.append('| step | pooled estimate | 95% interval | name |')
    lines.append('|---|---|---|---|')
    for key in ('E-B', 'C-E', 'C-B', 'B-A'):
        r = result['pooled'][key]
        lines.append(f"| {key} | {r['estimate']:+.4f} | {r['ci95'][0]:+.4f} to {r['ci95'][1]:+.4f} | "
                     f"{r['classification']['class'] if isinstance(r['classification'], dict) else r['classification']} |")
    lines.append('')
    for task, t in result['tasks'].items():
        lines.append(f'## {task}')
        for key in ('E-B', 'C-E'):
            r = t['steps'][key]
            lines.append(f"- {key}: {r['estimate']:+.4f} ({r['ci95'][0]:+.4f} to {r['ci95'][1]:+.4f})")
            r = t['conditional']['steps'][key]
            lines.append(f"- {key} over the {t['conditional']['blocks']} blocks where c0 was valid and failed: "
                         f"{r['estimate']:+.4f} ({r['ci95'][0]:+.4f} to {r['ci95'][1]:+.4f})")
        for arm, a in t['arms'].items():
            lines.append(f"- arm {arm}: adopted {a['adopted']} of {a['blocks']}; goal met on {a['goal_met_among_flights_flown']} "
                         f"of flights flown; zone entered on {a['entered_zone']} of {a['flights_flown']}")
        lines.append(f"- drawn candidates: arm E {t['attempts']['E']}, arm C in the same blocks {t['attempts']['C']}")
        lines.append(f"- calls {t['calls']}, US${t['list_cost_usd']} at list, US${t['charged_usd']} charged; served by {t['served_by']}")
        lines.append(f"- control: {t['control']}")
        lines.append('')
    lines.append(f"Study 2's own repeats: {result['study2_reflights']}")
    lines.append('')
    lines.append(f"Yardstick: {json.dumps(result['yardstick'])}")
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    s2_runs, saved, tag, out = Path(argv[0]), Path(argv[1]), argv[2], Path(argv[3])
    result = analyse(s2_runs, saved, tag)
    s2_analysis = json.loads((s2_runs / 'scored-20261120-S-analysis' / 'analysis.json').read_text())
    bad = check_against_study2(result, s2_analysis)
    if bad:
        raise SystemExit("Study 2's intervals did not come out the same, so nothing is reported: " + '; '.join(bad))
    result['study2_check'] = ("C - B and B - A, per task and pooled, and the conditional C - B per task, equal Study 2's "
                              'analysis.json')
    out.mkdir(parents=True)
    (out / 'analysis-e.json').write_text(json.dumps(result, indent=1, default=int) + '\n')
    (out / 'report-e.md').write_text(report(result))
    print(report(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

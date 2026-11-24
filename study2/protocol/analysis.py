"""Paper 3's analysis (PROTOCOL.md section 6): read the scored records once and write the results.

Run from paper3/:  .venv/bin/python protocol/analysis.py runs/scored  [--out runs/scored/analysis]

It finds every phase folder by its manifest.json, refuses folders whose manifest is a pilot (unless --include-pilot,
for checking the script on pilot records), verifies every hash-chained log, and writes analysis.json and a short
report.md. Proportions carry Wilson 95% intervals. Paired comparisons on the same scenarios carry a percentile
bootstrap 95% interval over scenarios, with a fixed bootstrap seed, so the script gives the same numbers every run.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
from dataclasses import asdict
import json
import math
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'protocol'))
BOOT_SEED, BOOT_N = 20261102, 10000


def wilson(k: int, n: int, z: float = 1.959964) -> dict:
    if n == 0:
        return {'k': 0, 'n': 0, 'rate': None, 'low': None, 'high': None}
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {'k': k, 'n': n, 'rate': round(p, 4), 'low': round(c - h, 4), 'high': round(c + h, 4)}


def paired_difference(a: dict, b: dict) -> dict:
    """a, b: scenario -> 0/1 met. Difference a - b over shared scenarios, with a bootstrap interval."""
    keys = sorted(set(a) & set(b), key=str)
    if not keys:
        return {'n': 0}
    diffs = [a[k] - b[k] for k in keys]
    rng = random.Random(BOOT_SEED)
    boots = sorted(statistics.fmean(rng.choice(diffs) for _ in diffs) for _ in range(BOOT_N))
    return {'n': len(keys), 'difference': round(statistics.fmean(diffs), 4),
            'low': round(boots[int(0.025 * BOOT_N)], 4), 'high': round(boots[int(0.975 * BOOT_N) - 1], 4),
            'a_only': sum(1 for d in diffs if d > 0), 'b_only': sum(1 for d in diffs if d < 0)}


def clustered_difference(pairs: dict) -> dict:
    """pairs: (library, scenario) -> (learned met 0/1, comparator met 0/1). Mean difference over all pairs, with a
    two-level percentile bootstrap: resample libraries, then scenarios within each, because flights by the same
    library are not independent."""
    by_lib = {}
    for (lib, _), (x, y) in pairs.items():
        by_lib.setdefault(lib, []).append(x - y)
    if not by_lib:
        return {'n': 0}
    libs = sorted(by_lib)
    all_d = [d for lib in libs for d in by_lib[lib]]
    rng = random.Random(BOOT_SEED)
    boots = []
    for _ in range(BOOT_N):
        sample = []
        for lib in (rng.choice(libs) for _ in libs):
            ds = by_lib[lib]
            sample += [rng.choice(ds) for _ in ds]
        boots.append(statistics.fmean(sample))
    boots.sort()
    return {'n_pairs': len(all_d), 'libraries': len(libs), 'difference': round(statistics.fmean(all_d), 4),
            'low': round(boots[int(0.025 * BOOT_N)], 4), 'high': round(boots[int(0.975 * BOOT_N) - 1], 4),
            'learned_only': sum(1 for d in all_d if d > 0), 'comparator_only': sum(1 for d in all_d if d < 0)}


def crossed_difference(pairs: dict, scenarios=None, libraries=None) -> dict:
    """Second protocol, Study 1's pooled comparisons. pairs: (library, scenario) -> (learned value, comparator value).
    Every library flies the same scheduled scenarios, so libraries and scenarios are crossed, as in Study 2. The
    percentile bootstrap resamples libraries and, separately, scenario identities, and applies the same scenario draw
    to every drawn library (D3's review, 4 November 2026). Resampling scenarios inside each library, as
    clustered_difference does for the first protocol, treats one scenario flown by eight libraries as eight
    independent draws and narrows the interval.

    scenarios and libraries: the scheduled identities to draw from, by default those present in pairs. Where pairs
    hold a selected subset (course steps, on the courses both the library and the reference completed), the draws are
    over every scheduled course and every learned library, and each resample keeps the selected pairs it contains. A
    resample that contains none is set aside and counted in empty_resamples."""
    d = {k: x - y for k, (x, y) in pairs.items()}
    if not d:
        return {'n': 0}
    libs = sorted(set(libraries) if libraries is not None else {lib for lib, _ in d}, key=str)
    pool = sorted(set(scenarios) if scenarios is not None else {sc for _, sc in d}, key=str)
    rng = random.Random(BOOT_SEED)
    boots, empty = [], 0
    for _ in range(BOOT_N):
        bs = [rng.choice(libs) for _ in libs]
        ss = [rng.choice(pool) for _ in pool]
        sample = [d[(b, sc)] for b in bs for sc in ss if (b, sc) in d]
        if sample:
            boots.append(statistics.fmean(sample))
        else:
            empty += 1
    boots.sort()
    vals = list(d.values())
    out = {'n_pairs': len(vals), 'libraries': len(libs), 'scenarios': len(pool),
           'difference': round(statistics.fmean(vals), 4),
           'low': round(boots[int(0.025 * len(boots))], 4) if boots else None,
           'high': round(boots[max(int(0.975 * len(boots)) - 1, 0)], 4) if boots else None,
           'learned_only': sum(1 for x in vals if x > 0), 'comparator_only': sum(1 for x in vals if x < 0),
           'resampling': 'libraries and one common scenario draw'}
    if empty:
        out['empty_resamples'] = empty
    return out


def matched_block_difference(outcomes: dict) -> dict:
    """Study 2: threat-trained minus calm-trained, for one task.

    outcomes: (block, scenario) -> (threat arm 0/1, calm arm 0/1). A block is one matched pair of learning runs, the
    calm run learning on the threat run's layouts with the zones removed. Every library flies the same evaluation
    scenarios, so blocks and scenarios are crossed. A learning run that did not adopt contributes 0 on every scenario
    (the pipeline outcome: acquiring, within the fixed budget, a procedure that then meets the goal); the caller
    supplies those zeros. The difference is the mean of threat minus calm over all pairs. Its 95% percentile interval
    comes from a bootstrap that resamples blocks and, separately, scenario identities, and applies the same scenario
    draw to every drawn block, keeping both arms and their pairing. So uncertainty from either arm, from the blocks
    and from the scenarios all reach the interval. Neither arm is treated as a fixed reference."""
    blocks = sorted({b for b, _ in outcomes}, key=str)
    scenarios = sorted({sc for _, sc in outcomes}, key=str)
    if not blocks or not scenarios:
        return {'blocks': 0}
    missing = [(b, sc) for b in blocks for sc in scenarios if (b, sc) not in outcomes]
    if missing:
        raise ValueError(f'blocks and scenarios must be fully crossed; missing {missing[:3]}')
    d = {(b, sc): outcomes[(b, sc)][0] - outcomes[(b, sc)][1] for b in blocks for sc in scenarios}
    rng = random.Random(BOOT_SEED)
    boots = []
    for _ in range(BOOT_N):
        bs = [rng.choice(blocks) for _ in blocks]
        ss = [rng.choice(scenarios) for _ in scenarios]
        boots.append(statistics.fmean(d[(b, sc)] for b in bs for sc in ss))
    boots.sort()
    threat = [outcomes[k][0] for k in d]
    calm = [outcomes[k][1] for k in d]
    return {'blocks': len(blocks), 'scenarios': len(scenarios), 'difference': round(statistics.fmean(d.values()), 4),
            'low': round(boots[int(0.025 * BOOT_N)], 4), 'high': round(boots[int(0.975 * BOOT_N) - 1], 4),
            'threat_mean': round(statistics.fmean(threat), 4), 'calm_mean': round(statistics.fmean(calm), 4),
            'threat_only': sum(1 for x in d.values() if x > 0), 'calm_only': sum(1 for x in d.values() if x < 0)}


def load(path: Path):
    return json.loads(Path(path).read_text())


def verify_chains(folder: Path) -> list:
    from telohelm.runtime.trusted_log import verify
    bad = []
    for heads in Path(folder).rglob('*.heads'):
        log = heads.with_name(heads.name[:-5] + 'log')
        if log.exists() and not verify(log, heads).get('ok'):
            bad.append(str(log))
    return bad


def phases(root: Path, include_pilot: bool):
    found = []
    for m in sorted(Path(root).rglob('manifest.json')):
        man = load(m)
        if man.get('pilot') and not include_pilot:
            continue
        found.append((m.parent, man))
    return found


def battle_rows(folder: Path) -> dict:
    """scenario id -> row, from a battle.run or autopilot_modes.run folder."""
    rows = {}
    f = folder / 'results.jsonl'
    if f.exists():
        for line in f.read_text().splitlines():
            r = json.loads(line)
            rows[f"{r['family']}-{r['seed']}"] = r
    return rows


def exposure(flights: Path, rows: dict, family: str) -> dict:
    """For one disturbance family in a phase: which flights the disturbance actually reached, and its realised effect.
    A configured event is not always an exposure: a flight can end before its event starts. Such a flight stays in
    the family's denominator and is listed as unexposed. The realised effect is the largest error of the autopilot's
    position estimate from the true position after the event starts. For spoofing, a goal met before the injection's
    recorded end is counted apart from one met after it. These describe the flights; they are not a second success
    criterion."""
    unexposed, peaks, during, after = [], [], 0, 0
    for key, r in sorted(rows.items()):
        if r['family'] != family:
            continue
        o = load(flights / key / 'outcome.json')
        starts = [e['t'] for e in o.get('event_log') or [] if e.get('phase') == 'start']
        if not starts:
            unexposed.append(key)
            continue
        # The event starts during the step that ends at start + 1, so the sample at t == start is from before it.
        errs = [st.get('estimate_error_m') for st in o.get('native_steps') or [] if st['t'] > min(starts)]
        errs = [e for e in errs if e is not None]
        if errs:
            peaks.append(max(errs))
        if family == 'spoof' and r['goal_met']:
            ends = [e['t'] for e in o['event_log'] if e.get('kind') == 'spoof' and e.get('phase') == 'end']
            if ends and min(ends) <= o['ended_at']:
                after += 1
            else:
                during += 1
    out = {'exposed': sum(1 for r in rows.values() if r['family'] == family) - len(unexposed),
           'unexposed': unexposed, 'peak_estimate_error_m': quantiles(peaks)}
    if family == 'spoof':
        out.update(met_while_injection_active=during, met_after_injection_ended=after)
    return out


def lags(folder: Path) -> list:
    """Every decision's lag in a phase folder, each real flight once: task-pack flights (outcome.json,
    decision_lag_s), candidate trial flights during learning (trial-evidence/**/result.json), and course flights
    (course-flight.json, course3d-flight.json, lag_s). Learning's mirrored example copies hold no outcome.json."""
    out = []
    for name, key in (('outcome.json', 'decision_lag_s'), ('course-flight.json', 'lag_s'),
                      ('course3d-flight.json', 'lag_s')):
        for o in Path(folder).rglob(name):
            out += [s[key] for s in load(o).get('native_steps', []) if s.get(key) is not None]
    for o in Path(folder).rglob('result.json'):
        if 'trial-evidence' in o.parts:
            out += [s['decision_lag_s'] for s in (load(o).get('outcome') or {}).get('native_steps', [])
                    if s.get('decision_lag_s') is not None]
    return out


def run_times(folder: Path) -> dict:
    """Procedure and guard run times per decision in a phase folder (section 4.5), each real flight once: task flights
    from their protected decision logs (episode.log, and the bare trial logs of learning), course flights from their
    records. Learning's mirrored example copies (run/learning/<episode>/episode.log) are skipped."""
    from ardupilot.pack import run_times as times
    proc, guard, proc_cpu, guard_cpu, undecided, steps = [], [], [], [], 0, 0
    logs = [p for p in Path(folder).rglob('episode.log') if p.parent.parent.name != 'learning']
    logs += [p for p in Path(folder).rglob('log') if p.is_file() and 'trial-evidence' in p.parts]
    for log in logs:
        for line in log.read_text().splitlines():
            r = json.loads(line)['payload']
            if r.get('kind') != 'decision' or r.get('decision') != 'control':
                continue
            steps += 1
            undecided += r.get('source') != 'procedure'
            t = times(r.get('tried'))
            for key, xs in (('procedure_wall_s', proc), ('guard_wall_s', guard), ('procedure_cpu_s', proc_cpu),
                            ('guard_cpu_s', guard_cpu)):
                if t[key] is not None:
                    xs.append(t[key])
    for name in ('course-flight.json', 'course3d-flight.json'):
        for o in Path(folder).rglob(name):
            for st in load(o).get('native_steps', []):
                steps += 1
                undecided += st.get('procedure') is None
                for key, xs in (('procedure_wall_s', proc), ('guard_wall_s', guard), ('procedure_cpu_s', proc_cpu),
                                ('guard_cpu_s', guard_cpu)):
                    if st.get(key) is not None:
                        xs.append(st[key])
    return {'procedure_wall_s': proc, 'guard_wall_s': guard, 'procedure_cpu_s': proc_cpu, 'guard_cpu_s': guard_cpu,
            'decisions': steps, 'decisions_without_procedure': undecided}


def threat_first_sight(folder: Path) -> list:
    """Each threat flight's realised first sight (section 8.3, change 1): the true distance from the drone to the zone's
    edge in the first reading that shows the zone, which is the step after it switched on."""
    out = []
    for o in Path(folder).rglob('outcome.json'):
        rec = load(o)
        for i, ev in enumerate(rec.get('events') or []):
            start = (rec.get('event_starts') or {}).get(str(i))
            if ev[0] != 'threat' or start is None:
                continue
            seen = [st for st in rec['native_steps'] if st['t'] == start + 1]
            if seen:
                gap = math.hypot(seen[0]['north_m'] - ev[3], seen[0]['east_m'] - ev[4]) - ev[5]
                out.append({'flight': o.parent.name, 'switched_on_step': start, 'first_sight_m': round(gap, 2),
                            'end_reason': rec['end_reason']})
    return out


def quantiles(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return {'n': len(xs), 'median': round(statistics.median(xs), 4), 'p95': round(xs[max(0, math.ceil(0.95 * len(xs)) - 1)], 4),
            'max': round(xs[-1], 4)}


def capped_seconds(outcome: Path) -> float:
    """Seconds a task flight took to meet its goal, or its time limit if it did not (D3's review: an early failure
    must not count as fast)."""
    o = load(outcome)
    return float(o['ended_at']) if o['goal_met'] else float(o['goal']['time_limit_s'])


def billed_cost(rows: list) -> dict:
    """The gateway's billed charge for one learning run's recorded calls. A total only when every call carries a
    charge; otherwise null, with the charges that did arrive kept apart as a known subtotal. The run summary adds a
    missing charge up as 0, so it is not used for this."""
    charges = [r['charged_usd'] for r in rows if r.get('charged_usd') is not None]
    return {'gateway_charged_usd': round(sum(charges), 6) if rows and len(charges) == len(rows) else None,
            'gateway_charged_known_subtotal_usd': round(sum(charges), 6) if charges else None,
            'calls_with_gateway_charge': len(charges), 'calls_recorded': len(rows)}


def list_usage(rows: list, summary_cost) -> dict:
    """List-price cost and token counts for one learning run's recorded calls (D3's review, 4 November 2026). A call
    that failed can carry no cost or token counts. The run summary adds those up as 0, so its figure is a known
    subtotal; it is a total only when every recorded call carries a cost. The same rule holds for tokens. Every
    recorded call stays in the call count."""
    costed = [r for r in rows if r.get('cost_usd') is not None]
    counted = [r for r in rows if r.get('input_tokens') is not None and r.get('output_tokens') is not None]
    known = lambda f: [r[f] for r in rows if r.get(f) is not None]     # each token field on its own (Fable, draft 2)
    complete = lambda f: bool(rows) and len(known(f)) == len(rows)
    return {'cost_usd_list': summary_cost if rows and len(costed) == len(rows) else None,
            'cost_usd_list_known_subtotal': summary_cost,
            'calls_with_list_cost': len(costed),
            'input_tokens': sum(known('input_tokens')) if complete('input_tokens') else None,
            'output_tokens': sum(known('output_tokens')) if complete('output_tokens') else None,
            'input_tokens_known_subtotal': sum(known('input_tokens')),
            'output_tokens_known_subtotal': sum(known('output_tokens')),
            'calls_with_input_tokens': len(known('input_tokens')),
            'calls_with_output_tokens': len(known('output_tokens')),
            'calls_with_token_counts': len(counted)}    # both fields; kept for the earlier reader


def usage_totals(runs: list) -> dict:
    """Across learning runs: the list-price total only when every run's every call carries a cost, beside the known
    subtotal and the number of calls without one."""
    total = round(sum(r['cost_usd_list'] for r in runs), 4) if runs and all(r['cost_usd_list'] is not None
                                                                          for r in runs) else None
    return {'cost_usd_list_total': total,
            'cost_usd_list_known_subtotal': round(sum(r['cost_usd_list_known_subtotal'] or 0 for r in runs), 4),
            'calls_without_list_cost': sum(r['calls_recorded'] - r['calls_with_list_cost'] for r in runs)}


def lag_quantiles(xs):
    """Decision lag summary. Lag comes in steps of the 0.1 s telemetry period, so the median hides how many decisions
    were late; the share at least 0.1 s late goes with it. Other summaries (seconds of run time, metres, finish
    times) carry no such share."""
    q = quantiles(xs)
    if q:
        q['share_at_least_0.1s'] = round(sum(1 for x in xs if x >= 0.095) / len(xs), 4)
    return q


def arm_of(origin: str):
    """Second protocol: the Study 2 arm a library belongs to, from its learning folder's name (learn-<task>-b<b>-<arm>),
    or None for a first-protocol library, an avoid or orbit library, or a comparator."""
    for part in Path(str(origin)).parts:
        if part.startswith('learn-') and part.rsplit('-', 1)[-1] in ('matched', 'threat') and '-b' in part:
            return part.rsplit('-', 1)[-1]
    return None


def analyse(root: Path, include_pilot=False, protocol: int = 1) -> dict:
    from ardupilot import attribution
    from ardupilot.battle import generate
    from ardupilot.scored import VERSIONS
    seeds = load(ROOT / 'protocol' / VERSIONS[protocol][0])
    found = phases(root, include_pilot)
    result = {'root': str(root), 'phases_found': len(found), 'chain_errors': [], 'learning': {}, 'heldout': {},
              'comparisons': {}, 'courses': {}, 'splits': {}, 'disturbance': {}, 'repeatability': {},
              'decision_lag_s': {}, 'run_times': {}, 'threat_first_sight': {}, 'attribution': {}}
    by = defaultdict(list)
    for folder, man in found:
        result['chain_errors'] += verify_chains(folder)
        by[man['phase']].append((folder, man))

    # RQ1: learning runs
    learned, study2_learning = {}, {}
    for folder, man in by['learn']:
        task, run = man['args']['task'], man['args'].get('run')   # the second protocol's blocks have none
        s = load(folder / 'run' / 'summary.json')
        usage = folder / 'run' / 'claude-usage.jsonl'
        rows = [json.loads(l) for l in usage.read_text().splitlines()] if usage.exists() else []
        bill = billed_cost(rows)
        adopted = bool(s['checks'].get('candidate_passed_trial_and_adopted'))
        entry = {'run': run, 'adopted': adopted, 'attempts': s.get('learning_attempts'),
                 'model_calls': s.get('real_model_calls'), **list_usage(rows, s.get('claude_cost_usd')),
                 'served_by': sorted({r.get('served_by') for r in rows if r.get('served_by')}),
                 'elapsed_s': s.get('elapsed_seconds'),
                 # The summary adds missing charges up as 0; a charge is available only where the gateway sent one.
                 **bill}
        arm = man['args'].get('family') if protocol == 2 else None
        entry.update({'block': man['args'].get('block'), 'arm': arm} if arm else {})
        if arm == 'threat':
            study2_learning.setdefault(task, []).append(entry)    # Study 2 only; Study 1's runs are the calm ones
        else:
            result['learning'].setdefault(task, []).append(entry)
            if arm == 'matched':
                study2_learning.setdefault(task, []).append(entry)
        if adopted:
            learned[(task, run)] = folder
            tests = ([asdict(generate(task, 'calm', k)) for k in seeds['heldout']['calm']] +
                     [asdict(generate(task, 'wind', k)) for k in seeds['heldout']['wind']])
            control = ([asdict(generate(task, 'calm', k)) for k in seeds['attribution_control']['calm']] +
                       [asdict(generate(task, 'wind', k)) for k in seeds['attribution_control']['wind']])
            if protocol == 2 and task in ('reach', 'reach3d', 'land'):
                tests += [asdict(generate(task, 'threat', k)) for k in seeds['threat_evaluation']]
                control += [asdict(generate(task, 'threat', k)) for k in seeds['attribution_control']['threat']]
            key = folder.name[len('learn-'):]
            result['attribution'][key] = attribution.check(folder / 'run', tests=tests)
            # Chance baseline: the same search for numbers from never-flown scenarios of the same kinds.
            c = attribution.check(folder / 'run', tests=control)
            result['attribution'][key]['control'] = {
                'checked': c['test_scenario_numbers_checked'], 'found': c['test_scenario_numbers_found_in_requests']}
    for task, runs in result['learning'].items():
        a = [r for r in runs if r['adopted']]
        known = lambda k: [r[k] for r in runs if r[k] is not None]
        span = lambda k: [min(known(k)), max(known(k))] if known(k) else None
        # Cost median and range over the runs whose every call carries a cost; the rest are counted beside them.
        result['learning'][task] = {'runs': runs, 'adopted': wilson(len(a), len(runs)),
                                    'calls_median': statistics.median([r['model_calls'] or 0 for r in runs]) if runs else None,
                                    'cost_usd_median': statistics.median(known('cost_usd_list')) if known('cost_usd_list') else None,
                                    'runs_with_unknown_list_cost': sum(1 for r in runs if r['cost_usd_list'] is None),
                                    **usage_totals(runs),
                                    'calls_range': span('model_calls'), 'cost_usd_range': span('cost_usd_list'),
                                    'elapsed_s_range': span('elapsed_s'),
                                    'gateway_charged_usd': (round(sum(r['gateway_charged_usd'] for r in runs), 6)
                                                            if runs and all(r['gateway_charged_usd'] is not None
                                                                            for r in runs) else None),
                                    'gateway_charged_known_subtotal_usd': (
                                        round(sum(r['gateway_charged_known_subtotal_usd'] for r in runs
                                                  if r['gateway_charged_known_subtotal_usd'] is not None), 6)
                                        if any(r['gateway_charged_known_subtotal_usd'] is not None for r in runs)
                                        else None),
                                    'calls_with_gateway_charge': sum(r['calls_with_gateway_charge'] for r in runs),
                                    'calls_recorded': sum(r['calls_recorded'] for r in runs)}

    # RQ2: held-out quality, per condition, with paired comparisons against the learned libraries
    cond = defaultdict(dict)   # task -> condition -> scenario -> met (learned libraries pooled by run)
    capped = defaultdict(dict) # task -> condition -> scenario -> seconds to the goal, or the time limit if not met
    for phase in ('heldout', 'autopilot'):
        for folder, man in by[phase]:
            task = man['args']['task']
            origin = man['args'].get('origin', '')
            if arm_of(origin) == 'threat':
                continue    # the threat arm's held-out flights are Study 2's retention check, not Study 1
            name = ('autopilot' if phase == 'autopilot' else 'reference' if 'reference' in origin
                    else 'hold' if 'hold still' in origin else f"learned:{origin}")
            rows = battle_rows(folder / 'flights')
            cond[task][name] = {k: int(r['goal_met']) for k, r in rows.items()}
            if protocol == 2:
                capped[task][name] = {k: capped_seconds(folder / 'flights' / k / 'outcome.json')
                                      for k in rows}
            result['heldout'].setdefault(task, {})[name] = wilson(sum(cond[task][name].values()), len(rows))
    for task, conds in cond.items():
        learned_names = [c for c in conds if c.startswith('learned:')]
        for ln in learned_names:
            for other in ('reference', 'autopilot', 'hold'):
                if other in conds:
                    result['comparisons'].setdefault(task, {})[f'{ln} - {other}'] = paired_difference(conds[ln], conds[other])
        # Pooled over the task's learned libraries: every (library, scenario) pair against the comparator on the same
        # scenario. Runs that adopted nothing have no library and are counted in RQ1, not here.
        if learned_names:
            pooled = {(ln, k): v for ln in learned_names for k, v in conds[ln].items()}
            result['heldout'][task]['learned, pooled'] = wilson(sum(pooled.values()), len(pooled))
            for other in ('reference', 'autopilot', 'hold'):
                if other in conds:
                    pairs = {(ln, k): (v, conds[other][k]) for (ln, k), v in pooled.items() if k in conds[other]}
                    pooled_diff = crossed_difference if protocol == 2 else clustered_difference
                    result['comparisons'][task][f'learned, pooled - {other}'] = pooled_diff(pairs)
        # Second protocol, secondary: seconds to the goal with a failed flight at its time limit, learned minus the
        # reference controller and ArduPilot's modes (hold still never meets the goal). Goal met stays primary.
        if protocol == 2 and learned_names:
            times = capped[task]
            for other in ('reference', 'autopilot'):
                if other in times:
                    pairs = {(ln, k): (v, times[other][k]) for ln in learned_names for k, v in times[ln].items()
                             if k in times[other]}
                    result['comparisons'][task][f'capped seconds: learned, pooled - {other}'] = crossed_difference(pairs)
                    for ln in learned_names:
                        result['comparisons'][task][f'capped seconds: {ln} - {other}'] = paired_difference(
                            times[ln], times[other])

    # RQ3: courses and the Split-S
    # Every course is flown by every condition. The headline counts every course. Beside it, the learned procedures'
    # counts on the courses the reference controller completed, with the courses it failed listed.
    ref_failed, ref_done = {}, {}
    for folder, man in by['courses']:
        if 'reference' in man['args']['origin']:
            ref_rows = load(folder / 'rows.json')
            ref_failed[man['args']['kind']] = {r['seed'] for r in ref_rows if not r['completed']}
            ref_done[man['args']['kind']] = {r['seed']: int(bool(r['completed'])) for r in ref_rows}
    for folder, man in by['courses']:
        kind, origin = man['args']['kind'], man['args']['origin']
        rows = load(folder / 'rows.json')
        excluded = sorted(r['seed'] for r in rows if r['seed'] in ref_failed.get(kind, set())) \
            if 'reference' not in origin else []
        kept = [r for r in rows if r['seed'] not in excluded]
        result['courses'][f'{kind}:{origin}'] = {
            'completed': wilson(sum(bool(r['completed']) for r in rows), len(rows)),
            'gates': wilson(sum(r['gates_passed'] for r in rows), sum(r['gates'] for r in rows)),
            'steps_without_procedure': sum(r['steps_without_procedure'] or 0 for r in rows),
            'courses_with_wind': sum(1 for r in rows if (r['wind_ms'] or 0) > 0),
            'reference_failed': excluded,
            'completed_where_reference_completed': wilson(sum(bool(r['completed']) for r in kept), len(kept))}
        if 'reference' not in origin and kind in ref_done:
            # Per library: learned minus reference on the same courses, with the scenario bootstrap used for RQ2.
            result['courses'][f'{kind}:{origin}']['learned_minus_reference'] = paired_difference(
                {r['seed']: int(bool(r['completed'])) for r in rows}, ref_done[kind])
    for kind in ('flat', '3d'):
        ref = next((load(f / 'rows.json') for f, m in by['courses'] if m['args']['kind'] == kind
                    and 'reference' in m['args']['origin']), None)
        learned = [(m['args']['origin'], load(f / 'rows.json')) for f, m in by['courses']
                   if m['args']['kind'] == kind and 'reference' not in m['args']['origin']]
        if not learned:
            continue
        pooled = [r for _, rows in learned for r in rows]
        entry = {'completed': wilson(sum(bool(r['completed']) for r in pooled), len(pooled)),
                 'gates': wilson(sum(r['gates_passed'] for r in pooled), sum(r['gates'] for r in pooled)),
                 'libraries': len(learned)}
        if ref:
            done = {r['seed']: int(bool(r['completed'])) for r in ref}
            pairs = {(lib, r['seed']): (int(bool(r['completed'])), done[r['seed']])
                     for lib, rows in learned for r in rows if r['seed'] in done}
            entry['learned_minus_reference'] = (crossed_difference if protocol == 2 else clustered_difference)(pairs)
            if protocol == 2:
                # Secondary: decision steps (one a second) to finish a course, on the courses both the library and
                # the reference completed; how many that is goes with the result, since it selects on success.
                ref_steps = {r['seed']: r['steps'] for r in ref if r['completed']}
                steps = {(lib, r['seed']): (r['steps'], ref_steps[r['seed']])
                         for lib, rows in learned for r in rows if r['completed'] and r['seed'] in ref_steps}
                entry['steps_learned_minus_reference_where_both_completed'] = {
                    **crossed_difference(steps, scenarios={sc for _, sc in pairs}, libraries={lib for lib, _ in learned}),
                    'pairs_scheduled': len(pairs)}   # library-course pairs, before selecting on both completing
        result['courses'][f'{kind}:learned, pooled'] = entry
    for phase in ('splits', 'gazebo'):
        learned = [load(f / 'rows.json') for f, m in by[phase] if 'reference' not in m['args']['origin']]
        pooled = [r for rows in learned for r in rows]
        if pooled:
            result['splits'][('Gazebo, ' if phase == 'gazebo' else '') + 'learned, pooled'] = {
                'completed': wilson(sum(bool(r['completed']) for r in pooled), len(pooled)),
                'gates': wilson(sum(r['gates_passed'] for r in pooled), sum(r['gates'] for r in pooled)),
                'libraries': len(learned), 'finish_s': quantiles([r['finish_s'] for r in pooled if r.get('finish_s') is not None])}
    for folder, man in by['splits'] + [(f, m) for f, m in by['gazebo']]:
        rows = load(folder / 'rows.json')
        times = [r['finish_s'] for r in rows if r.get('finish_s') is not None]
        where = 'Gazebo, ' if man['phase'] == 'gazebo' else ''
        result['splits'][where + man['args']['origin']] = {'completed': wilson(sum(r['completed'] for r in rows), len(rows)),
                                                   'gates': wilson(sum(r['gates_passed'] for r in rows), sum(r['gates'] for r in rows)),
                                                   'steps_without_procedure': sum(r.get('steps_without_procedure') or 0 for r in rows),
                                                   'finish_s': quantiles(times)}

    # Descriptive: disturbances, repeatability, decision timing
    for folder, man in by['disturb']:
        rows = battle_rows(folder / 'flights')
        fams = defaultdict(list)
        for k, r in rows.items():
            fams[r['family']].append(int(r['goal_met']))
        ends = defaultdict(lambda: defaultdict(int))
        for r in rows.values():
            ends[r['family']][r['end_reason']] += 1
        result['disturbance'][f"{man['args']['task']}:{man['args']['origin']}"] = {
            f: {**wilson(sum(v), len(v)), 'end_reasons': dict(ends[f]), **exposure(folder / 'flights', rows, f)}
            for f, v in fams.items()}
        sight = threat_first_sight(folder / 'flights')
        if sight:
            result['threat_first_sight'][f"{man['args']['task']}:{man['args']['origin']}"] = {
                'flights': sight, 'least_m': min(x['first_sight_m'] for x in sight),
                'under_9_m': sum(x['first_sight_m'] < 9.0 for x in sight)}
    # Second protocol: the same check on Study 2's evaluation flights, where the 9 m margin matters most.
    for folder, man in by['threat']:
        sight = threat_first_sight(folder / 'flights')
        if sight:
            result['threat_first_sight'][f"threat evaluation:{man['args']['task']}:{man['args']['origin']}"] = {
                'flights': sight, 'least_m': min(x['first_sight_m'] for x in sight),
                'under_9_m': sum(x['first_sight_m'] < 9.0 for x in sight)}
    for folder, man in by['repeat']:
        reps = [battle_rows(folder / f'repeat-{i}') for i in (1, 2, 3)]
        keys = sorted(set.intersection(*(set(r) for r in reps))) if all(reps) else []
        agree = sum(1 for k in keys if len({r[k]['end_reason'] for r in reps}) == 1)
        result['repeatability'][f"{man['args']['task']}:{man['args']['origin']}"] = wilson(agree, len(keys))
    for phase in ('learn', 'heldout', 'repeat', 'autopilot', 'disturb', 'threat', 'courses', 'splits', 'gazebo'):
        lag, rt = [], []
        for folder, man in by[phase]:
            lag += lags(folder)
            rt.append(run_times(folder))
        result['decision_lag_s'][phase] = lag_quantiles(lag)
        if phase != 'autopilot':   # ArduPilot flies the comparators; no procedure runs
            result['run_times'][phase] = {
                'decisions': sum(x['decisions'] for x in rt),
                'decisions_without_procedure': sum(x['decisions_without_procedure'] for x in rt),
                **{key: quantiles([v for x in rt for v in x[key]])
                   for key in ('procedure_wall_s', 'guard_wall_s', 'procedure_cpu_s', 'guard_cpu_s')}}
    if protocol == 2:
        result['study2'] = study2(by, study2_learning, seeds, include_pilot)
    return result


def study2(by: dict, learning: dict, seeds: dict, pilot: bool) -> dict:
    """Study 2 (second protocol): does learning and qualifying with threat zones change how procedures meet the goal
    when a threat zone appears, against the matched calm arm?

    For each task, every scheduled block counts. A learning run that finished without adopting has no evaluation
    flights and contributes 0 on every scenario to the primary pipeline outcome (acquiring, within the fixed
    learning budget, a procedure that then meets the goal); its capped time is the time limit. Conditional quality,
    among adopted libraries only, is secondary."""
    from ardupilot import pack
    from ardupilot.battle import generate
    out = {}
    ids = [f'threat-{k}' for k in (seeds['pilot']['threat_evaluation'] if pilot else seeds['threat_evaluation'])]
    # The planned scenario identities and time limits come from the seeds and the task, never from the flights that
    # happened, so a task on which no run adopted keeps its full denominators (D3's review, 4 November 2026).
    planned_held = ([f'calm-{k}' for k in seeds['pilot']['heldout_calm']] if pilot else
                    [f'calm-{k}' for k in seeds['heldout']['calm']] + [f'wind-{k}' for k in seeds['heldout']['wind']])
    for task, runs in sorted(learning.items()):
        arms = {(r['block'], r['arm']): r for r in runs}
        blocks = sorted({b for b, _ in arms})
        flights = {}   # (block, arm) -> scenario -> (met, capped seconds, entered a zone)
        sights = {}    # arm -> first-sight records of its evaluation flights (Fable's review: per arm)
        limits = {pack.TASKS[task].goal(dict(generate(task, 'threat', int(sc.split('-')[1])).params))['time_limit_s']
                  for sc in ids}
        if len(limits) != 1:
            raise ValueError(f'{task}: threat scenarios have different time limits {sorted(limits)}')
        horizon = limits.pop()
        for folder, man in by['threat']:
            if man['args']['task'] != task:
                continue
            o_arm, block = arm_of(man['args']['origin']), block_of(man['args']['origin'])
            rows = battle_rows(folder / 'flights')
            got = {}
            for key, r in rows.items():
                o = load(folder / 'flights' / key / 'outcome.json')
                if o['goal']['time_limit_s'] != horizon:
                    raise ValueError(f'{folder.name} {key}: time limit {o["goal"]["time_limit_s"]}, planned {horizon}')
                got[key] = (int(r['goal_met']), o['ended_at'] if r['goal_met'] else o['goal']['time_limit_s'],
                            int(r['end_reason'] in ('entered_threat', 'entered_zone')))
            flights[(block, o_arm)] = got
            sights.setdefault(o_arm, []).extend(threat_first_sight(folder / 'flights'))
        held = {}      # (block, arm) -> held-out scenario (20 calm, 10 wind) -> met
        for folder, man in by['heldout']:
            if man['args']['task'] == task and arm_of(man['args'].get('origin', '')):
                held[(block_of(man['args']['origin']), arm_of(man['args']['origin']))] = {
                    k: int(r['goal_met']) for k, r in battle_rows(folder / 'flights').items()}
        held_ids = planned_held
        # A zero stands in only for a run that finished without adopting. An adopted library with missing evaluation
        # flights, or flights from a library that did not adopt, is a fault in the records, never a 0 (the gate should
        # already have refused such a run).
        for b in blocks:
            for arm in ('threat', 'matched'):
                ok = bool((b, arm) in arms and arms[(b, arm)]['adopted'])
                for name, got, want in (('threat', flights.get((b, arm)), ids), ('held-out', held.get((b, arm)), held_ids)):
                    if ok and (got is None or sorted(got) != sorted(want)):
                        raise ValueError(f'{task} block {b} {arm}: adopted, but its {name} flights are missing or incomplete')
                    if not ok and got:
                        raise ValueError(f'{task} block {b} {arm}: {name} flights from a run that did not adopt')
        pairs, times, retention = {}, {}, {}
        for b in blocks:
            for sc in ids:
                t = flights.get((b, 'threat'), {}).get(sc)
                c = flights.get((b, 'matched'), {}).get(sc)
                pairs[(b, sc)] = ((t or (0,))[0], (c or (0,))[0])
                times[(b, sc)] = ((t or (0, horizon))[1], (c or (0, horizon))[1])
            for sc in held_ids:
                retention[(b, sc)] = (held.get((b, 'threat'), {}).get(sc, 0), held.get((b, 'matched'), {}).get(sc, 0))
        entry = {'blocks': len(blocks), 'scenarios': len(ids)}
        for arm in ('threat', 'matched'):
            rs = [arms[(b, arm)] for b in blocks if (b, arm) in arms]
            adopted = [r for r in rs if r['adopted']]
            met = [v[0] for b in blocks for v in flights.get((b, arm), {}).values()]
            entry[arm] = {'adopted': wilson(len(adopted), len(rs)),
                          'goal_met_given_adoption': wilson(sum(met), len(met)),
                          'entered_a_zone': sum(v[2] for b in blocks for v in flights.get((b, arm), {}).values()),
                          # Flights whose zone switched on, so a first sight could be measured, and how many first saw
                          # it under the 9 m of section 3.
                          'first_sight': {'flights_measured': len(sights.get(arm, [])),
                                          'under_9_m': sum(x['first_sight_m'] < 9.0 for x in sights.get(arm, [])),
                                          'least_m': min((x['first_sight_m'] for x in sights.get(arm, [])), default=None)},
                          'calls_median': statistics.median([r['model_calls'] or 0 for r in rs]) if rs else None,
                          'attempts_median': statistics.median([r['attempts'] or 0 for r in rs]) if rs else None,
                          **usage_totals(rs),
                          'per_block_goal_met': {str(b): sum(v[0] for v in flights.get((b, arm), {}).values())
                                                 for b in blocks}}
        entry['threat_goal_threat_minus_calm'] = matched_block_difference(pairs) if pairs else {'blocks': 0}
        entry['capped_time_s_threat_minus_calm'] = matched_block_difference(times) if times else {'blocks': 0}
        entry['heldout_threat_minus_calm'] = matched_block_difference(retention) if retention else {'blocks': 0}
        out[task] = entry
    return out


def block_of(origin: str):
    for part in Path(str(origin)).parts:
        if part.startswith('learn-') and '-b' in part and part.rsplit('-', 1)[-1] in ('matched', 'threat'):
            return int(part.rsplit('-', 2)[-2][1:])
    return None


def report(r: dict) -> str:
    v = r.get('validation') or {}
    lines = [f"# Paper 3 analysis\n\nRecords: {r['root']}; phase folders read: {r['phases_found']}; "
             f"hash-chain errors: {len(r['chain_errors'])}.\n"]
    if not v.get('ok'):
        lines.append("**DIAGNOSTIC ONLY. The validation gate failed, so nothing below is a result** (PROTOCOL.md "
                     f"section 6). {len(v.get('errors', []))} problems:\n")
        lines += [f"- {e}" for e in v.get('errors', [])] + ['']
    else:
        lines.append(f"Validation gate passed: {v.get('scheduled_phases')} scheduled phases, {v.get('checked')}.\n")
    lines.append("## RQ1, learning\n")
    for task, v in r['learning'].items():
        a = v['adopted']
        lines.append(f"- {task}: adopted in {a['k']} of {a['n']} runs (95% interval {a['low']} to {a['high']}); "
                     f"median {v['calls_median']} model calls, " + (f"median US${v['cost_usd_median']} at list price." if v['cost_usd_median'] is not None
                        else 'list cost unknown for every run.'))
    lines.append("\n## RQ2, held-out scenarios\n")
    for task, conds in r['heldout'].items():
        for name, w in conds.items():
            lines.append(f"- {task}, {name}: {w['k']} of {w['n']} met ({w['low']} to {w['high']}).")
    for task, v in (r.get('study2') or {}).items():
        if task == list(r['study2'])[0]:
            lines.append("\n## RQ4, learning under threat (Study 2)\n")
        g = v['threat_goal_threat_minus_calm']
        lines.append(f"- {task}: {v['blocks']} blocks x {v['scenarios']} threat scenarios. Threat arm adopted "
                     f"{v['threat']['adopted']['k']} of {v['threat']['adopted']['n']}, calm arm "
                     f"{v['matched']['adopted']['k']} of {v['matched']['adopted']['n']}. Pipeline goal rate threat "
                     f"{g.get('threat_mean')} against calm {g.get('calm_mean')}; threat minus calm {g.get('difference')} "
                     f"(95% interval {g.get('low')} to {g.get('high')}). Goals met given adoption: threat "
                     f"{v['threat']['goal_met_given_adoption']['k']} of {v['threat']['goal_met_given_adoption']['n']}, "
                     f"calm {v['matched']['goal_met_given_adoption']['k']} of {v['matched']['goal_met_given_adoption']['n']}. "
                     f"Flights that entered a zone: threat {v['threat']['entered_a_zone']}, calm {v['matched']['entered_a_zone']}.")
    lines.append("\n## RQ3, transfer\n")
    for key, v in r['courses'].items():
        if 'libraries' in v:   # pooled over the task's learned libraries
            d = v.get('learned_minus_reference') or {}
            lines.append(f"- courses {key} ({v['libraries']} libraries): {v['completed']['k']} of {v['completed']['n']} "
                         f"completed ({v['completed']['low']} to {v['completed']['high']}), {v['gates']['k']} of "
                         f"{v['gates']['n']} gates" + (f"; learned minus reference on the same courses {d['difference']} "
                                                       f"(95% interval {d['low']} to {d['high']})" if 'difference' in d else '') + ".")
            continue
        lines.append(f"- courses {key}: {v['completed']['k']} of {v['completed']['n']} completed, "
                     f"{v['gates']['k']} of {v['gates']['n']} gates; steps no procedure decided: {v['steps_without_procedure']}"
                     + (f"; on the courses the reference completed, {v['completed_where_reference_completed']['k']} of "
                        f"{v['completed_where_reference_completed']['n']} (reference failed {v['reference_failed']})"
                        if v['reference_failed'] else '') + ".")
    for key, v in r['splits'].items():
        lines.append(f"- Split-S, {key}: {v['completed']['k']} of {v['completed']['n']} completed, {v['gates']['k']} of "
                     f"{v['gates']['n']} gates; finish {v['finish_s']}.")
    lines.append("\n## Paired comparisons on the same held-out scenarios\n")
    for task, comps in r['comparisons'].items():
        for name, c in comps.items():
            if 'difference' in c:
                lines.append(f"- {task}, {name}: difference {c['difference']} (95% interval {c['low']} to {c['high']}).")
            else:
                lines.append(f"- {task}, {name}: no shared scenarios.")
    lines.append("\n## Disturbances (descriptive)\n")
    for key, fams in r['disturbance'].items():
        for f, w in fams.items():
            ends = ', '.join(f'{e} {n}' for e, n in sorted(w['end_reasons'].items()))
            lines.append(f"- {key}, {f}: {w['k']} of {w['n']} met; ended by {ends}.")
    lines.append("\n## Repeatability\n")
    for key, w in r['repeatability'].items():
        lines.append(f"- {key}: {w['k']} of {w['n']} scenarios ended the same way in all three repeats.")
    lines.append("\n## Decision lag (seconds of simulated time)\n\nHeld-out and learning flights: simulated time from "
                 "the scheduled observation to the command. Courses and Split-S: newest telemetry time after the "
                 "command minus the time of the position the decision used, so it includes that position's age and "
                 "is only as fine as the 0.1 s telemetry period.\n")
    for phase, q in r['decision_lag_s'].items():
        lines.append(f"- {phase}: " + (f"median {q['median']}, 95th percentile {q['p95']}, max {q['max']} over {q['n']} steps; "
                                       f"share of decisions 0.1 s or more late {q['share_at_least_0.1s']}." if q else "no records."))
    lines.append("\n## Procedure and guard run times (wall-clock seconds per decision)\n")
    for phase, t in r.get('run_times', {}).items():
        lines.append(f"- {phase}: {t['decisions']} decisions, {t['decisions_without_procedure']} without a deciding "
                     f"procedure; procedure {t['procedure_wall_s']}; guard {t['guard_wall_s']}.")
    lines.append("\n## Threat zones: realised first sight\n")
    for key, t in r.get('threat_first_sight', {}).items():
        lines.append(f"- {key}: least {t['least_m']} m over {len(t['flights'])} flights; under 9 m: {t['under_9_m']}.")
    lines.append("\n## Attribution checks on adopted procedures\n")
    for key, a in r['attribution'].items():
        lines.append(f"- {key}: {a['adopted_procedure_lines']} lines; numbers matching training scenarios "
                     f"{len(a['numbers_matching_training_scenarios'])}, matching task defaults "
                     f"{len(a['numbers_matching_task_defaults'])}; reference lines reaching the model in a request "
                     f"{len(a['reference_lines_in_requests'])} (lines the model itself wrote that match the reference: "
                     f"{len({ln for w in a['reference_lines_written_by_model'] for ln in w['lines']})} distinct); held-out scenario numbers found in requests "
                     f"{len(a['test_scenario_numbers_found_in_requests'])} of {a['test_scenario_numbers_checked']} "
                     f"{a['test_scenario_numbers_found_in_requests']}; from never-flown control scenarios "
                     f"{len(a['control']['found'])} of {a['control']['checked']} {a['control']['found']}.")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('root', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--include-pilot', action='store_true')
    p.add_argument('--tasks', help='the scheduled tasks (default: all five)')
    p.add_argument('--libraries', type=Path, help='a pilot folder whose libraries the scheduler reused')
    p.add_argument('--protocol', type=int, choices=(1, 2), default=1)
    p.add_argument('--blocks', type=int, help='second protocol: matched blocks per Study 2 task')
    a = p.parse_args(argv)
    from validate import validate
    out = a.out or (a.root / 'analysis')
    if (out / 'analysis.json').exists():
        raise SystemExit(f'{out} already holds an analysis; a later reading goes to a new, separately named folder')
    # The validation gate runs first (section 6). If it fails, the report is written as a diagnostic and the exit code
    # says so; nothing is rerun.
    gate = validate(a.root, a.tasks.split(',') if a.tasks else None, a.libraries, a.include_pilot, a.protocol, a.blocks)
    if a.protocol == 2 and not gate['ok']:
        # Second protocol: a failed gate computes no outcome. The diagnostic holds the gate's errors only, so nobody
        # reads an outcome before the gate passes (section 6; Fable's review of draft 2, 4 November 2026). Once the
        # fault is dealt with, the analysis runs again into a new folder.
        r = {'root': str(a.root), 'outcomes_withheld': True}
    else:
        try:
            r = analyse(a.root, a.include_pilot, a.protocol)
        except Exception as exc:
            if gate['ok']:
                raise
            # The gate failed and the records could not all be read: still write the diagnostic, with the gate's errors.
            r = {'root': str(a.root), 'phases_found': None, 'chain_errors': [], 'learning': {}, 'heldout': {},
                 'courses': {}, 'analysis_error': f'{type(exc).__name__}: {exc}'}
    r['validation'] = gate
    r['analysis_source_sha256'] = {n: hashlib.sha256((ROOT / 'protocol' / n).read_bytes()).hexdigest()
                                   for n in ('analysis.py', 'validate.py')}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'analysis.json').write_text(json.dumps(r, indent=1, default=str))
    if r.get('outcomes_withheld'):
        text = ("# Paper 3 analysis\n\n**DIAGNOSTIC ONLY. The validation gate failed, so no outcome was computed.** "
                f"{len(gate['errors'])} problems:\n\n" + '\n'.join(f'- {e}' for e in gate['errors']) + '\n')
    elif 'analysis_error' in r:
        text = ("# Paper 3 analysis\n\n**DIAGNOSTIC ONLY. The validation gate failed and the records could not all be "
                f"read** ({r['analysis_error']}). {len(gate['errors'])} problems:\n\n" +
                '\n'.join(f'- {e}' for e in gate['errors']) + '\n')
    else:
        text = report(r)
    (out / 'report.md').write_text(text)
    print(text)
    return 0 if gate['ok'] else 3


if __name__ == '__main__':
    raise SystemExit(main())

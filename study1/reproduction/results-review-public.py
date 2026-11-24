"""Independent reconciliation of the released Paper 3 scored-2 records.

Standard library only; imports none of the experimental code. Reads existing
records and exported sources, verifies chains and reproduces the registered
comparisons. No simulator or model is invoked. It writes one new JSON output.

From the exported repository:
    python reproduction/results-review-public.py --records <unzipped-folder> --out <new.json>
The records folder contains runs/scored-2. The simulator-log ZIP is not needed.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

P3 = Path(__file__).resolve().parents[1]
TASKS = ('reach', 'reach3d', 'avoid', 'orbit', 'land')
S2 = ('reach', 'reach3d', 'land')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bootstrap(pairs):
    """Recompute the registered paired, crossed block/scenario bootstrap."""
    blocks = sorted({b for b, _ in pairs}, key=str)
    cases = sorted({c for _, c in pairs}, key=str)
    assert len(pairs) == len(blocks) * len(cases)
    rng = random.Random(20261102)
    diff = {k: a-b for k, (a, b) in pairs.items()}
    draws = []
    for _ in range(10000):
        bs = [rng.choice(blocks) for _ in blocks]
        cs = [rng.choice(cases) for _ in cases]
        draws.append(statistics.fmean(diff[b, c] for b in bs for c in cs))
    draws.sort()
    return dict(blocks=len(blocks), scenarios=len(cases),
                difference=round(statistics.fmean(diff.values()), 4),
                low=round(draws[250], 4), high=round(draws[9749], 4),
                threat_mean=round(statistics.fmean(v[0] for v in pairs.values()), 4),
                calm_mean=round(statistics.fmean(v[1] for v in pairs.values()), 4),
                threat_only=sum(d > 0 for d in diff.values()), calm_only=sum(d < 0 for d in diff.values()))


def review(root):
    root = root.resolve()
    errors, inputs, endings, locations = [], {}, {}, {}

    def need(ok, message):
        if not ok:
            errors.append(message)

    def read(p):
        p = Path(p).resolve()
        data = p.read_bytes()
        if p.is_relative_to(root):
            key = 'records/' + str(p.relative_to(root))
        elif p.is_relative_to(P3):
            key = 'code/' + str(p.relative_to(P3))
        else:
            raise ValueError('An input lies outside the code and record roots')
        locations[key] = p
        h = digest(data)
        need(key not in inputs or inputs[key] == h, f'changed input: {key}')
        inputs[key] = h
        return data

    def load(p):
        return json.loads(read(p))

    def lines(p):
        return [json.loads(x) for x in read(p).splitlines() if x.strip()]

    def counts(recorded, values, where):
        need(recorded['k'] == sum(values) and recorded['n'] == len(values), f'count mismatch: {where}')

    seeds = load(P3/'protocol/seeds-2.json')
    protocol_sha = digest(read(P3/'PROTOCOL-2.md'))
    need(protocol_sha == '9a80c2b34041219927ade9200ebe42ccef6426c7adf92d908ff9afcfc050be85', 'protocol binding')
    seed_sha = digest(read(P3/'protocol/seeds-2.json'))
    source = sorted((P3/'ardupilot').glob('*.py'))
    for sub in ('worlds', 'ardupilot_gazebo'):
        source += sorted(p for p in (P3/'ardupilot/gazebo'/sub).rglob('*') if p.is_file())
    source += [P3/'protocol'/n for n in ('run_scored.py', 'seeds.json', 'seeds-2.json')]
    fingerprint = digest(''.join(f'{p.relative_to(P3)}\0{digest(read(p))}\n' for p in source).encode())
    need(fingerprint == '2e02a6e11b9f6e6e4117112195c734fc26cd5759262a3ff252bcf19ec6195ace', 'source binding')
    wheel = digest(read(P3/'protocol/telohelm-0.1.0.dev0-py3-none-any.whl'))
    r = load(root/'analysis/analysis.json')
    need(r['validation']['ok'] and not r['validation']['errors'] and not r['chain_errors'], 'saved gate failed')
    for f, h in r['analysis_source_sha256'].items():
        need(digest(read(P3/'protocol'/f)) == h, f'analysis source changed: {f}')
    archive = P3/'results/scored-2-20261106'
    for row in read(archive/'SHA256SUMS').decode().splitlines():
        h, f = row.split(maxsplit=1)
        original = root/('logs' if f == 'scheduler.log' else 'analysis')/f
        need(read(original) == read(archive/f) and digest(read(original)) == h, f'archive mismatch: {f}')
    scheduler = read(root/'logs/scheduler.log').decode().splitlines()
    need(scheduler[-1].endswith('finished; phases needing a decision: none'), 'scheduler not terminal')
    need(not any('FAILED ' in l or 'HOLD ' in l for l in scheduler), 'fault in scheduler')
    manifests = {p.parent.name: load(p) for p in sorted(root.glob('*/manifest.json'))}
    done = {p.stem for p in (root/'logs').glob('*.done')}
    for p in (root/'logs').glob('*.done'):
        read(p)
    need(set(manifests) == done, 'manifest/done inventory mismatch')
    for name, m in manifests.items():
        need(not m['pilot'] and m['protocol_sha256'] == protocol_sha and m['seeds_sha256'] == seed_sha,
             f'protocol/seed/pilot binding: {name}')
        need(m['git']['source']['sha256'] == fingerprint and m['core']['ok'] and m['core']['wheel_sha256'] == wheel,
             f'source/core binding: {name}')

    expected, learning, study1 = set(), {}, defaultdict(list)
    costs, raw_costs, calls = Counter(), Counter(), Counter()
    for task in TASKS:
        labels = [f'b{b}-{a}' for b in range(8) for a in ('matched', 'threat')] if task in S2 else list(map(str, range(5)))
        for label in labels:
            name = f'learn-{task}-{label}'
            expected.add(name)
            s = load(root/name/'run/summary.json')
            usage = lines(root/name/'run/claude-usage.jsonl')
            adopted = bool(s['checks']['candidate_passed_trial_and_adopted'])
            block = int(label.split('-')[0][1:]) if task in S2 else int(label)
            arm = label.split('-')[-1] if task in S2 else 'calm'
            learning[name] = dict(adopted=adopted, block=block, arm=arm, task=task,
                                  calls=s['real_model_calls'], cost=s['claude_cost_usd'])
            need(len(usage) == s['real_model_calls'], f'usage/call count: {name}')
            need(all(u.get('cost_usd') is not None for u in usage), f'unknown list cost: {name}')
            need(abs(sum(u['cost_usd'] for u in usage)-s['claude_cost_usd']) <= .000051, f'cost sum: {name}')
            group = 'threat' if arm == 'threat' else 'study1'
            costs[group] += s['claude_cost_usd']
            raw_costs[group] += sum(u['cost_usd'] for u in usage)
            calls[group] += len(usage)
            need(all(u.get('charged_usd') is None for u in usage), f'new available billed charge: {name}')
            if arm != 'threat':
                recorded = next(x for x in r['learning'][task]['runs'] if
                                (x.get('block') == block if task in S2 else x['run'] == block))
                need(recorded['adopted'] == adopted and recorded['model_calls'] == len(usage) and
                     recorded['cost_usd_list'] == s['claude_cost_usd'], f'learning output: {name}')
                for token in ('input_tokens', 'output_tokens'):
                    need(recorded[token] == sum(u[token] for u in usage), f'{token}: {name}')
                if adopted:
                    study1[task].append(label)
            if task in S2 and adopted:
                expected.add(f'threat-{task}-{label}')
                if arm == 'threat':
                    expected.add(f'heldout-{task}-learned-{label}')
    expected.update(('courses-flat-reference', 'courses-3d-reference', 'splits-reference', 'gazebo-reference'))
    for task in TASKS:
        expected.update((f'heldout-{task}-reference', f'heldout-{task}-hold', f'repeat-{task}-reference'))
        if task != 'avoid':
            expected.add(f'autopilot-{task}')
        for label in study1[task]:
            expected.update((f'heldout-{task}-learned-{label}', f'disturb-{task}-learned-{label}'))
            if task == 'reach':
                expected.add(f'courses-flat-learned-{label}')
            if task == 'reach3d':
                expected.update(f'{prefix}-learned-{label}' for prefix in ('courses-3d', 'splits', 'gazebo'))
        if study1[task]:
            expected.add(f'repeat-{task}-learned-{sorted(study1[task])[0]}')
    need(expected == set(manifests) and len(expected) == 254, 'independent scheduled inventory')
    # Matched training must retain the threat arm's layouts, with the threat removed.
    for task in S2:
        for b in range(8):
            configs = [load(root/f'learn-{task}-b{b}-{arm}'/'run/run-config.json') for arm in ('threat', 'matched')]
            for left, right in zip(configs[0]['scenarios'][:3], configs[1]['scenarios'][:3]):
                need(left['params'] == right['params'] and left['wind_ms'] == right['wind_ms'] and
                     not right['events'] and bool(left['events']), f'matched training layout: {task} {b}')
    print(f'Inventory: {len(expected)} phases, {len(learning)} learning runs', flush=True)

    protected = sorted([*root.rglob('*.heads'), *root.rglob('heads')])
    for heads in protected:
        log = heads.with_name('log' if heads.name == 'heads' else heads.name[:-5]+'log')
        raw, anchors = read(log).splitlines(), lines(heads)
        need(bool(raw) and len(raw) == len(anchors), f'chain length: {log}')
        previous = '0'*64
        for i, data in enumerate(raw, 1):
            event = json.loads(data)
            need(event['seq'] == i and event['prev'] == previous, f'chain sequence: {log} {i}')
            previous = digest(data)
            if i <= len(anchors):
                need(anchors[i-1]['head'] == previous and anchors[i-1]['count'] == i, f'chain hash: {log} {i}')
                if i == 1:
                    need(anchors[0].get('anchor') == previous, f'chain anchor: {log}')
            p = event['payload']
            if p.get('kind') in ('episode_end', 'flight_end'):
                need(str(log) not in endings, f'multiple endings: {log}')
                endings[str(log)] = p
    need(len(protected) == 10081, 'protected pair count')
    print(f'Protected logs: {len(protected)} pairs; {len(errors)} errors', flush=True)

    battles, transfer, sights = {}, {}, defaultdict(list)
    task_flights, course_flights = 0, 0
    for name, m in manifests.items():
        phase, a, folder = m['phase'], m['args'], root/name
        if phase == 'learn':
            continue
        if phase in ('heldout', 'autopilot', 'disturb', 'repeat', 'threat'):
            if phase in ('heldout', 'autopilot'):
                specs = [(f, k) for f in ('calm', 'wind') for k in seeds['heldout'][f]]
            elif phase == 'repeat':
                specs = [('calm', k) for k in seeds['repeatability']['calm']]
            elif phase == 'threat':
                specs = [('threat', k) for k in seeds['threat_evaluation']]
            else:
                specs = [(f, k) for f, ks in seeds['disturbance'].items()
                         if not (a['task'] == 'orbit' and f == 'threat') for k in ks]
            expected_cases = [f'{f}-{k}' for f, k in specs]
            need(sorted(a['cases']) == sorted(expected_cases), f'manifest/seed cases: {name}')
            aggregate = {}
            rounds = range(1, seeds['repeatability']['repeats']+1) if phase == 'repeat' else [None]
            for repetition in rounds:
                sub = folder/f'repeat-{repetition}' if repetition else folder/'flights'
                rows = lines(sub/'results.jsonl')
                keys = [f"{x['family']}-{x['seed']}" for x in rows]
                need(sorted(keys) == sorted(expected_cases) and len(keys) == len(set(keys)), f'case inventory: {name}')
                for row, key in zip(rows, keys):
                    p = sub/key/'outcome.json'
                    o, end = load(p), endings[str(sub/key/'episode.log')]
                    need((row['goal_met'], row['end_reason']) == (o['goal_met'], o['end_reason']) ==
                         (end.get('goal_met'), end.get('end_reason')), f'row/native/protected outcome: {p}')
                    aggregate[f'{repetition}:{key}' if repetition else key] = dict(
                        met=int(o['goal_met']), time=o['ended_at'] if o['goal_met'] else o['goal']['time_limit_s'],
                        horizon=o['goal']['time_limit_s'], reason=o['end_reason'])
                    for i, event in enumerate(o.get('events') or []):
                        switch = (o.get('event_starts') or {}).get(str(i))
                        if event[0] == 'threat' and switch is not None:
                            step = next((s for s in o['native_steps'] if s['t'] == switch+1), None)
                            if step:
                                sights[name].append(round(math.hypot(step['north_m']-event[3], step['east_m']-event[4])-event[5], 2))
                    task_flights += 1
            battles[name] = aggregate
            if phase in ('heldout', 'autopilot') and '-threat' not in name:
                cond = 'autopilot modes' if phase == 'autopilot' else 'hold' if name.endswith('-hold') else 'reference' if name.endswith('-reference') else 'learned:'+a['origin']
                # The public JSON uses "autopilot" for the mode comparator.
                if phase == 'autopilot':
                    cond = next(k for k in r['heldout'][a['task']] if 'autopilot' in k)
                counts(r['heldout'][a['task']][cond], [v['met'] for v in aggregate.values()], name)
        elif phase in ('courses', 'splits', 'gazebo'):
            rows = load(folder/'rows.json')
            expected_n = (30 if a['kind'] == 'flat' else 20) if phase == 'courses' else 5 if phase == 'splits' else 3
            need(len(rows) == expected_n, f'course count: {name}')
            if phase == 'courses':
                lo, hi = seeds['courses_flat' if a['kind'] == 'flat' else 'courses_3d']
                need(sorted(x['seed'] for x in rows) == list(range(lo, hi)), f'course identities: {name}')
            else:
                need([x['flight'] for x in rows] == list(range(1, expected_n+1)), f'flight identities: {name}')
            for row in rows:
                case = f"seed-{row['seed']}" if phase == 'courses' else f"flight-{row['flight']}"
                sub = folder/case/('flight' if phase == 'gazebo' else '')
                filename = 'course-flight.json' if phase == 'courses' and a['kind'] == 'flat' else 'course3d-flight.json'
                native = load(sub/filename)
                end = endings[str(sub/'flight.log')]
                for key in ('completed', 'gates_passed', 'gates', 'end_reason'):
                    if key in row:
                        need(row[key] == native[key] == end.get(key), f'course row/native/protected {name} {case} {key}')
                course_flights += 1
            transfer[name] = dict(n=len(rows), completed=sum(x['completed'] for x in rows),
                                  gates=sum(x['gates_passed'] for x in rows), total_gates=sum(x['gates'] for x in rows))
    need(task_flights == 4165 and course_flights == 522, 'flight totals')
    for task in TASKS:
        names = [f'heldout-{task}-learned-{label}' for label in study1[task]]
        values = [v['met'] for name in names for v in battles[name].values()]
        counts(r['heldout'][task]['learned, pooled'], values, f'{task} heldout pooled')
    for kind in ('flat', '3d'):
        selected = [v for name, v in transfer.items() if name.startswith(f'courses-{kind}-learned-')]
        recorded = r['courses'][f'{kind}:learned, pooled']
        need(recorded['completed']['k'] == sum(v['completed'] for v in selected) and
             recorded['completed']['n'] == sum(v['n'] for v in selected) and
             recorded['gates']['k'] == sum(v['gates'] for v in selected) and
             recorded['gates']['n'] == sum(v['total_gates'] for v in selected), f'pooled courses: {kind}')

    study2 = {}
    for task in S2:
        threat_cases = [f'threat-{k}' for k in seeds['threat_evaluation']]
        held_cases = [f'{f}-{k}' for f in ('calm', 'wind') for k in seeds['heldout'][f]]
        native_horizons = {v['horizon'] for name, rs in battles.items() if name.startswith(f'threat-{task}-') for v in rs.values()}
        need(len(native_horizons) == 1, f'threat horizons: {task}')
        horizon = next(iter(native_horizons))
        pairs, times, retention = {}, {}, {}
        for b in range(8):
            arms = {}
            for arm in ('threat', 'matched'):
                adopted = learning[f'learn-{task}-b{b}-{arm}']['adopted']
                name = f'threat-{task}-b{b}-{arm}'
                rs = battles.get(name, {})
                held = battles.get(f'heldout-{task}-learned-b{b}-{arm}', {})
                need((set(rs) == set(threat_cases) and set(held) == set(held_cases)) if adopted else not rs and not held,
                     f'adoption/evaluation consistency: {task} {b} {arm}')
                arms[arm] = (rs, held)
                need(r['study2'][task][arm]['per_block_goal_met'][str(b)] == sum(v['met'] for v in rs.values()),
                     f'per-block goal count: {task} {b} {arm}')
            for sc in threat_cases:
                t, c = (arms[arm][0].get(sc, {'met': 0, 'time': horizon}) for arm in ('threat', 'matched'))
                pairs[b, sc], times[b, sc] = (t['met'], c['met']), (t['time'], c['time'])
            for sc in held_cases:
                retention[b, sc] = tuple(arms[arm][1].get(sc, {'met': 0})['met'] for arm in ('threat', 'matched'))
        out = {}
        for label, values in (('threat_goal_threat_minus_calm', pairs), ('capped_time_s_threat_minus_calm', times), ('heldout_threat_minus_calm', retention)):
            out[label] = bootstrap(values)
            need(out[label] == r['study2'][task][label], f'Study 2 bootstrap differs: {task} {label}')
        for arm in ('threat', 'matched'):
            values = [v for name, xs in sights.items() if name.startswith(f'threat-{task}-') and name.endswith('-'+arm) for v in xs]
            got = dict(flights_measured=len(values), under_9_m=sum(x < 9 for x in values), least_m=min(values, default=None))
            need(got == r['study2'][task][arm]['first_sight'], f'first sight: {task} {arm}')
        study2[task] = out
    print(f'Flight counts and all 9 primary/secondary bootstrap summaries checked; {len(errors)} errors', flush=True)

    # Inspect the frozen attribution hits in source and conversation chronology.
    # Keep the matcher unchanged; these are interpretation checks on its saved flags.
    flagged = {k: v for k, v in r['attribution'].items()
               if v['reference_lines_in_requests'] or v['numbers_matching_training_scenarios']}
    need(set(flagged) == {'reach-b3-threat', 'reach-b7-threat'}, 'attribution flag inventory')
    needle = "return {'vn': 0.0, 've': 0.0}"
    chronology = []
    for p in sorted((root/'learn-reach-b3-threat/run').rglob('gateway.log')):
        for i, event in enumerate(lines(p), 1):
            payload = event['payload']
            if payload.get('kind') in ('model_start', 'model_end') and needle in json.dumps(payload):
                chronology.append(dict(file=str(p.relative_to(root)), line=i, kind=payload['kind']))
    need(chronology[0]['kind'] == 'model_end' and 'attempt-1' in chronology[0]['file'], 'reference-hit first appearance')
    need(any(x['kind'] == 'model_start' and 'attempt-2' in x['file'] for x in chronology), 'cross-attempt carry-forward')
    summary = load(root/'learn-reach-b7-threat/run/summary.json')
    adopted_source = summary['adopted_sources'][0]
    source_line = adopted_source.splitlines()[24]
    need(source_line.strip() == 'k = L * i / 8.0', 'training-number match context')
    config = load(root/'learn-reach-b7-threat/run/run-config.json')
    need(any(ev[0] == 'threat' and ev[5] == 8.0 for sc in config['scenarios'][:3] for ev in sc['events']),
         '8.0 is also a training-zone radius')
    attribution_context = dict(flags=flagged, reference_hit_chronology=chronology,
                               training_literal=dict(value=8.0, line=25, code=source_line.strip()),
                               test_hits=sum(len(x['test_scenario_numbers_found_in_requests']) for x in r['attribution'].values()),
                               test_checked=sum(x['test_scenario_numbers_checked'] for x in r['attribution'].values()),
                               control_hits=sum(len(x['control']['found']) for x in r['attribution'].values()),
                               control_checked=sum(x['control']['checked'] for x in r['attribution'].values()))

    for rel, h in list(inputs.items()):
        need(digest(locations[rel].read_bytes()) == h, f'input changed at end: {rel}')
    return dict(made=datetime.now().astimezone().isoformat(), ok=not errors, errors=errors,
                protocol_sha256=protocol_sha, seeds_sha256=seed_sha, source_sha256=fingerprint,
                phases=len(manifests), learning_runs=len(learning), task_flights=task_flights,
                course_flights=course_flights, protected_pairs=len(protected),
                learning=learning, calls=dict(calls), cost_summary_subtotals=dict(costs), raw_call_cost_subtotals=dict(raw_costs),
                study2=study2, transfer=transfer, attribution_context=attribution_context, inputs_sha256=inputs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--records', type=Path, required=True, help='Extracted folder containing runs/scored-2')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit('preserve an existing review output; choose a new path')
    root = (a.records / 'runs' / 'scored-2').resolve()
    if not (root / 'analysis' / 'analysis.json').is_file():
        raise SystemExit('The records folder must contain runs/scored-2/analysis/analysis.json')
    result = review(root)
    result['reader_sha256'] = digest(Path(__file__).read_bytes())
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('ok', 'errors', 'phases', 'learning_runs', 'task_flights', 'course_flights', 'protected_pairs', 'calls', 'cost_summary_subtotals')}, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

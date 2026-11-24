"""The paper's results tables, read from the frozen analysis output (protocol/analysis.py writes analysis/analysis.json).

This script computes no statistics. Every rate, interval and difference is copied from analysis.json. The only
arithmetic is adding counts across a task's libraries for the disturbance table, which is descriptive (section 4.4 of
PROTOCOL.md) and is shown as counts without intervals. If the validation gate did not pass, the tables are marked as
diagnostic, as the analysis report is.

  .venv/bin/python manuscript/results_tables.py runs/scored/analysis/analysis.json > manuscript/drafts/RESULTS-TABLES.md
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

TASKS = ('reach', 'reach3d', 'avoid', 'orbit', 'land')
FAMILIES = ('jam', 'spoof', 'rc_loss', 'gust', 'motor', 'threat')
FAMILY_NAMES = {'jam': 'Jamming', 'spoof': 'Spoofing', 'rc_loss': 'Radio loss', 'gust': 'Gust', 'motor': 'Weak motor',
                'threat': 'Threat zone'}


def label(origin: str) -> str:
    """A short name for a condition key from the analysis: the learning run's folder, or the comparator."""
    if 'reference' in origin:
        return 'Reference controller'
    if 'hold' in origin:
        return 'Hold still'
    if 'pooled' in origin:
        return 'Learned, pooled'
    return Path(origin).parent.name if origin.endswith('/run') else origin


def rate(w) -> str:
    if not w:
        return ''
    if not w.get('n') or w.get('rate') is None:
        return f"{w.get('k', 0)}/{w.get('n', 0)} (none flown)"
    return f"{w['k']}/{w['n']} ({w['rate']:.2f}; {w['low']:.2f} to {w['high']:.2f})"


def diff(d) -> str:
    if not d or d.get('difference') is None:
        return ''
    return f"{d['difference']:+.2f} ({d['low']:+.2f} to {d['high']:+.2f})"


def pooled_interval(r) -> str:
    """How the pooled comparisons' intervals were drawn. The second protocol draws libraries and one common set of
    scenarios (analysis.crossed_difference); the first drew scenarios inside each library."""
    return ('the crossed bootstrap 95% interval (libraries and one common draw of scenarios)' if 'study2' in r
            else 'the two-level bootstrap 95% interval')


def table(head, rows) -> str:
    out = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out) + '\n'


def cost(a) -> str:
    """List-price cost of a group of learning runs: the total when every call carries a cost, otherwise the known
    subtotal with the number of calls that carry none."""
    if a.get('cost_usd_list_total') is not None:
        return f"{a['cost_usd_list_total']:.3f}"
    return f"{a['cost_usd_list_known_subtotal']:.3f} known; {a['calls_without_list_cost']} calls without a cost"


def learning(r) -> str:
    rows = []
    for t in TASKS:
        v = r['learning'].get(t)
        if not v:
            continue
        rows.append([t, rate(v['adopted']), f"{v['calls_median']} ({v['calls_range'][0]} to {v['calls_range'][1]})",
                     f"{v['cost_usd_median']:.3f} ({v['cost_usd_range'][0]:.3f} to {v['cost_usd_range'][1]:.3f})"
                     + (f"; {v['runs_with_unknown_list_cost']} runs with calls without a cost"
                        if v.get('runs_with_unknown_list_cost') else ''),
                     f"{v['elapsed_s_range'][0] / 60:.0f} to {v['elapsed_s_range'][1] / 60:.0f}"])
    return ('Table 1. Learning (RQ1). Adoption over learning runs with Wilson 95% interval; model calls and list-price '
            'cost per run, median (range), the cost from recorded token counts at list price (the gateway reports no '
            'billed charge, so billed cost is unavailable); wall-clock minutes per run.\n\n' +
            table(['Task', 'Adopted', 'Model calls', 'Cost, US$', 'Minutes'], rows))


def heldout(r) -> str:
    rows = []
    for t in TASKS:
        conds, comps = r['heldout'].get(t), r['comparisons'].get(t, {})
        if not conds:
            continue
        rows.append([t, rate(conds.get('learned, pooled')), rate(conds.get('reference')), rate(conds.get('autopilot')),
                     rate(conds.get('hold')), diff(comps.get('learned, pooled - reference')),
                     diff(comps.get('learned, pooled - autopilot'))])
    return ('Table 2. Held-out scenarios (RQ2). Goal met, k/n (rate; Wilson 95% interval). Learned libraries pooled; '
            f'differences are learned minus comparator on the same scenarios, with {pooled_interval(r)}. '
            'Avoid has no autopilot-mode comparator.\n\n' +
            table(['Task', 'Learned', 'Reference', 'ArduPilot modes', 'Hold still', 'Learned - reference',
                   'Learned - modes'], rows))


def heldout_per_library(r) -> str:
    rows = []
    for t in TASKS:
        for key, w in (r['heldout'].get(t) or {}).items():
            if key.startswith('learned:'):
                rows.append([t, label(key[len('learned:'):]), rate(w),
                             diff((r['comparisons'].get(t) or {}).get(f'{key} - reference'))])
    return ('Table 2a. Held-out scenarios per library.\n\n' +
            table(['Task', 'Library', 'Goal met', 'Learned - reference'], rows))


def transfer(r) -> str:
    rows = []
    for kind, name in (('flat', 'Flat courses (reach)'), ('3d', 'Building courses (reach3d)')):
        pooled = r['courses'].get(f'{kind}:learned, pooled')
        ref = next((v for k, v in r['courses'].items() if k.startswith(f'{kind}:') and 'reference' in k), None)
        if pooled:
            rows.append([name, rate(pooled['completed']), rate(pooled['gates']), rate(ref and ref['completed']),
                         diff(pooled.get('learned_minus_reference'))])
    for prefix, name in (('', 'Split-S, SITL (reach3d)'), ('Gazebo, ', 'Split-S, Gazebo (reach3d)')):
        pooled = r['splits'].get(prefix + 'learned, pooled')
        ref = next((v for k, v in r['splits'].items() if k.startswith(prefix) and 'reference' in k
                    and (prefix or not k.startswith('Gazebo'))), None)
        if pooled:
            rows.append([name, rate(pooled['completed']), rate(pooled['gates']), rate(ref and ref['completed']), ''])
    return ('Table 3. Transfer with learning off (RQ3). Courses completed and gates passed by the learned libraries, '
            'pooled; the reference controller on the same courses; learned minus reference on the same courses with '
            f'{pooled_interval(r)}.\n\n' +
            table(['Test', 'Learned, completed', 'Learned, gates', 'Reference, completed', 'Learned - reference'], rows))


def transfer_per_library(r) -> str:
    # The analysis lists the reference's failed courses only on the learned rows (every condition flies the same
    # courses), and gives the reference row an empty list and its all-course rate as the subset. So the reference row
    # takes its failures from the learned rows of the same kind and leaves the subset cell blank.
    failed = defaultdict(set)
    for key, v in r['courses'].items():
        kind, origin = key.split(':', 1)
        if 'reference' not in origin and 'pooled' not in origin:
            failed[kind].update(v.get('reference_failed') or [])
    rows = []
    for key, v in sorted(r['courses'].items()):
        kind, origin = key.split(':', 1)
        if 'pooled' in origin:
            continue
        is_ref = 'reference' in origin
        ids = sorted(failed[kind]) if is_ref else (v.get('reference_failed') or [])
        rows.append([{'flat': 'Flat courses', '3d': 'Building courses'}[kind], label(origin), rate(v['completed']),
                     rate(v['gates']), '' if is_ref else rate(v.get('completed_where_reference_completed')),
                     ', '.join(str(c) for c in ids) or 'none'])
    for key, v in sorted(r['splits'].items()):
        if 'pooled' in key:
            continue
        where, origin = ('Split-S, Gazebo', key[len('Gazebo, '):]) if key.startswith('Gazebo, ') else ('Split-S, SITL', key)
        rows.append([where, label(origin), rate(v['completed']), rate(v['gates']), '', ''])
    return ('Table 3a. Transfer per library and for the reference controller. The subset column is secondary: '
            'courses completed among those the reference controller completed; the headline counts every course.\n\n' +
            table(['Test', 'Controller', 'Completed', 'Gates', 'Completed where reference completed',
                   'Courses the reference failed'], rows))


def disturbances(r) -> str:
    sums = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    ends = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for key, fams in r['disturbance'].items():
        task = key.split(':', 1)[0]
        for f, w in fams.items():
            sums[task][f][0] += w['k']
            sums[task][f][1] += w['n']
            for reason, n in (w.get('end_reasons') or {}).items():
                ends[task][f][reason] += n
    rows = [[t] + [f"{sums[t][f][0]}/{sums[t][f][1]}" if f in sums[t] else '-' for f in FAMILIES]
            for t in TASKS if t in sums]
    reasons = [[t, FAMILY_NAMES[f], ', '.join(f'{k} {v}' for k, v in sorted(ends[t][f].items()))]
               for t in TASKS if t in ends for f in FAMILIES if f in ends[t]]
    return ('Table 4. Disturbances, descriptive. Goal met, summed over the task\'s learned libraries (counts only). '
            'Jamming and radio loss test ArduPilot\'s configured failsafes (landing and return-to-launch), not the learned '
            'procedure; Table 4a gives each flight\'s actual ending. In the other four the procedure stays in control.\n\n' +
            table(['Task'] + [FAMILY_NAMES[f] for f in FAMILIES], rows) +
            '\nTable 4a. How the disturbance flights ended.\n\n' + table(['Task', 'Family', 'Endings'], reasons))


def repeatability(r) -> str:
    rows = [[key.split(':', 1)[0], label(key.split(':', 1)[1]), rate(w)] for key, w in sorted(r['repeatability'].items())]
    return ('Table 5. Repeatability. Scenarios whose three repeat endings agree.\n\n' +
            table(['Task', 'Controller', 'Endings agree'], rows))


def timing(r) -> str:
    q = lambda d: f"{d['median']:.3f} / {d['p95']:.3f} / {d['max']:.3f}" if d else '-'
    late = lambda d: f"{d['share_at_least_0.1s']:.3f}" if d and d.get('share_at_least_0.1s') is not None else '-'
    rows = []
    for phase, lag in r['decision_lag_s'].items():
        t = r['run_times'].get(phase) or {}
        undecided = (f"{t['decisions_without_procedure']}/{t['decisions']}" if t.get('decisions') is not None else '-')
        rows.append([phase, q(lag), late(lag), q(t.get('procedure_wall_s')), q(t.get('guard_wall_s')), undecided])
    sight = [[label(k.split(':', 1)[1]) + f" ({k.split(':', 1)[0]})", v['least_m'], len(v['flights']), v['under_9_m']]
             for k, v in r.get('threat_first_sight', {}).items()]
    return ('Table 6. Decision timing, descriptive: decision lag in seconds of simulated time, and the procedure\'s '
            'and guard\'s wall-clock seconds per decision, median / 95th percentile / maximum.\n\n' +
            table(['Phase', 'Lag', 'Share of decisions at least 0.1 s late', 'Procedure', 'Guard',
                   'Decisions without a procedure'], rows) +
            '\nTable 6a. Threat zones: least realised first-sight distance (m).\n\n' +
            table(['Library', 'Least distance', 'Flights', 'Under 9 m'], sight))


def attribution(r) -> str:
    rows = []
    for key, a in sorted(r['attribution'].items()):
        rows.append([key, a['adopted_procedure_lines'], len(a['numbers_matching_training_scenarios']),
                     len(a['reference_lines_in_requests']),
                     f"{len(a['test_scenario_numbers_found_in_requests'])}/{a['test_scenario_numbers_checked']}",
                     f"{len(a['control']['found'])}/{a['control']['checked']}"])
    return ('Table 7. Attribution checks per adopted procedure: code lines; matches in its code of numbers from its own '
            'learning scenarios (each occurrence counted); model requests containing a reference-controller line longer '
            'than 25 characters, after removing text the model wrote earlier; held-out scenario numbers found in the '
            'requests, against the same search for never-flown control scenarios.\n\n' +
            table(['Library', 'Lines', 'Learning-number matches in code', 'Requests with reference-line hits',
                   'Held-out numbers found', 'Control numbers found'], rows))


def num(d, unit='') -> str:
    """A continuous difference with its interval (capped seconds, course steps)."""
    if not d or d.get('difference') is None:
        return ''
    return f"{d['difference']:+.2f}{unit} ({d['low']:+.2f} to {d['high']:+.2f})"


def secondary(r) -> str:
    """Second protocol, Study 1 secondary measures. Empty for the first protocol, which did not compute them."""
    rows = []
    for t in TASKS:
        c = r['comparisons'].get(t) or {}
        if any(k.startswith('capped seconds') for k in c):
            rows.append([t, num(c.get('capped seconds: learned, pooled - reference'), ' s'),
                         num(c.get('capped seconds: learned, pooled - autopilot'), ' s')])
    course = []
    for kind, name in (('flat', 'Flat courses'), ('3d', 'Building courses')):
        d = (r['courses'].get(f'{kind}:learned, pooled') or {}).get('steps_learned_minus_reference_where_both_completed')
        if d:
            course.append([name, num(d), f"{d.get('n_pairs', 0)} of {d.get('pairs_scheduled', 0)}"])
    if not rows and not course:
        return ''
    return ('Table 2b. Capped seconds on held-out scenarios (secondary): seconds to meet the goal, a failed flight '
            'counted at its time limit; learned libraries pooled minus the comparator on the same scenarios, with '
            f'{pooled_interval(r)}.\n\n' + table(['Task', 'Learned - reference', 'Learned - modes'], rows) +
            '\nTable 3b. Decision steps to finish a course (secondary), learned minus reference, on the courses both '
            'completed; the last column gives how many pairs that is out of those scheduled, since the subset selects '
            'on success.\n\n' + table(['Courses', 'Learned - reference', 'Pairs used'], course))


def study2(r) -> str:
    """Second protocol, Study 2: threat-trained minus calm-trained by matched blocks."""
    s2 = r.get('study2') or {}
    if not s2:
        return ''
    rows, arms = [], []
    for t in ('reach', 'reach3d', 'land'):
        v = s2.get(t)
        if not v:
            continue
        g = v['threat_goal_threat_minus_calm']
        rows.append([t, f"{v['blocks']} x {v['scenarios']}",
                     f"{g.get('threat_mean', 0):.2f}", f"{g.get('calm_mean', 0):.2f}", diff(g),
                     num(v['capped_time_s_threat_minus_calm'], ' s'), diff(v['heldout_threat_minus_calm'])])
        for arm, name in (('threat', 'Threat arm'), ('matched', 'Calm arm')):
            a = v[arm]
            arms.append([t, name, rate(a['adopted']), rate(a['goal_met_given_adoption']), a['entered_a_zone'],
                         a['calls_median'], a['attempts_median'], cost(a)])
    return ('Table 8. Study 2, learning under threat. Per task, blocks x fresh threat scenarios; the share of '
            'block-scenario pairs whose learning run adopted and whose procedure then met the goal, for each arm (a '
            'non-adopted run counts 0 on every scenario); threat arm minus calm arm with the matched-block bootstrap '
            '95% interval (blocks and scenarios resampled, arms kept paired). Capped seconds count a failed flight at '
            'its time limit. The held-out column compares the arms on the whole held-out set, 20 calm and 10 wind '
            'scenarios.\n\n' +
            table(['Task', 'Pairs', 'Threat arm', 'Calm arm', 'Threat - calm', 'Capped seconds, threat - calm',
                   'Held-out, threat - calm'], rows) +
            '\nTable 8a. Study 2 by arm: adoption over scheduled learning runs; goals met on the threat scenarios by '
            'adopted libraries only (secondary, conditional on adoption); flights that entered a zone; median model '
            'calls and attempts per run; list-price cost of the arm\'s learning runs, US$.\n\n' +
            table(['Task', 'Arm', 'Adopted', 'Goal met given adoption', 'Entered a zone', 'Calls', 'Attempts',
                   'Cost'], arms))


def main(argv=None):
    path = Path((argv or sys.argv[1:])[0])
    r = json.loads(path.read_text())
    v = r.get('validation') or {}
    head = [f"# Paper 3 results tables\n\nFrom `{path}` (phase folders read {r['phases_found']}, hash-chain errors "
            f"{len(r['chain_errors'])}).\n"]
    if not v.get('ok'):
        head.append('**Diagnostic only: the validation gate did not pass, so these are not results.**\n')
    parts = [learning, heldout, heldout_per_library, transfer, transfer_per_library, secondary, disturbances,
             repeatability, timing, attribution, study2]
    print('\n'.join(head + [x for x in (p(r) for p in parts) if x]))   # a table the run did not compute is left out


if __name__ == '__main__':
    main()

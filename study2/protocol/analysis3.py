"""Protocol 3 inference from one fully validated, in-memory evidence snapshot.

Validate the entire planned cohort before computing outcomes. Keep all completed
learning blocks, including non-adoptions; share within-block source outcomes as
declared; draw blocks jointly across arms and scenarios within clearance bands.
Independent task draws form the equally weighted mean of these three named tasks.
A failed gate creates no scientific result. No simulator or model is called.
"""
from __future__ import annotations

import argparse
import datetime
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import contract3 as C


def interval(draws, coverage=0.95):
    x = np.asarray(draws, dtype=float)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all():
        raise ValueError('Invalid bootstrap draws')
    alpha = (1 - coverage) / 2
    return [round(float(v), 12) for v in np.quantile(x, [alpha, 1 - alpha], method='linear')]


def classify(estimate, ci95, ci90, margin=0.20):
    """Separate difference/equivalence flags; do not give direction priority.

This is the Lakens decision structure with approximate crossed-bootstrap CIs,
not the article's parametric t-test or a claim of exact error calibration.
"""
    if not (margin > 0 and math.isfinite(margin)):
        raise ValueError('Invalid margin')
    # Percentile bounds need not contain the point estimate; do not recenter them.
    if not all(math.isfinite(v) for v in [estimate, *ci95, *ci90]) or ci95[0] > ci95[1] or ci90[0] > ci90[1]:
        raise ValueError('Invalid interval')
    if ci90[0] < ci95[0] or ci90[1] > ci95[1]:
        raise ValueError('The 90% interval must be nested within the 95% interval')
    direction = 'gain' if ci95[0] > 0 else 'loss' if ci95[1] < 0 else 'not_detected'
    different = direction != 'not_detected'
    equivalent = ci90[0] > -margin and ci90[1] < margin
    category = ('different_and_equivalent' if different and equivalent else
                'different_not_equivalent' if different else
                'equivalent_not_different' if equivalent else 'unresolved')
    return {'class': category, 'direction': direction, 'different_from_zero': different,
            'equivalent_within_margin': equivalent, 'margin': margin,
            'useful_gain': ci95[0] > margin, 'useful_loss': ci95[1] < -margin}


NO_SUCCESS = 'no_success_in_either_arm'
EVERY_SUCCESS = 'every_flight_succeeded_in_both_arms'
IDENTICAL = 'identical_outcomes'
NOTHING_TO_COMPARE = (NO_SUCCESS, EVERY_SUCCESS, IDENTICAL)
NAMES = {NO_SUCCESS: 'no success in either arm', EVERY_SUCCESS: 'every flight succeeded in both arms'}


def identical_bound(n_blocks):
    """One-sided 95% upper bound on the share of blocks in which two arms would differ, when they were the same in all
    n_blocks blocks: the share p at which n_blocks identical blocks in a row have probability 0.05, 1 - 0.05^(1/n)."""
    return round(1 - 0.05 ** (1 / n_blocks), 12)


def nothing_to_compare(cells_a, cells_b, n_blocks):
    """Ruling 38, point 2. Decided on the cells of the two arms and never on the interval's width. Returns None when the
    two arms differ in some cell and the section 6.4 name applies, otherwise a record that replaces that name:
    both arms 0 in every cell, both 1 in every cell, or equal cell for cell (with the number of blocks and the bound)."""
    a, b = np.asarray(cells_a, dtype=float), np.asarray(cells_b, dtype=float)
    if a.shape != b.shape or not a.size:
        return None
    if not a.any() and not b.any():
        key = NO_SUCCESS
    elif a.all() and b.all():
        key = EVERY_SUCCESS
    elif np.array_equal(a, b):
        key = IDENTICAL
    else:
        return None
    identical = f'identical outcomes in all {n_blocks} blocks' if n_blocks != 1 else 'identical outcomes in the 1 block'
    rec = {'class': key, 'name': NAMES.get(key) or identical, 'blocks': int(n_blocks),
           'cells_per_arm': int(a.size)}
    if key == IDENTICAL:
        rec['one_sided_95_bound_on_share_of_blocks_differing'] = identical_bound(n_blocks)
    return rec


def base_classification(row):
    """The section 6.4 classification of an interval, whatever name the row carries now."""
    return row.get('underlying_classification', row['classification'])


def estimate_record(point, draws, cells=None, blocks=None):
    """cells is (the first arm's cells, the second arm's cells) when the interval compares two arms, and blocks the number
    of blocks in them. If the two arms have nothing to compare (ruling 38, point 2) the section 6.4 name is replaced and
    the classification it would have had is kept under underlying_classification."""
    ci95, ci90 = interval(draws), interval(draws, .90)
    point = round(float(point), 12)
    row = {'estimate': point, 'ci95': ci95, 'ci90': ci90,
           'classification': classify(point, ci95, ci90),
           'sensitivity_margin_0_10': classify(point, ci95, ci90, .10),
           'zero_width_bootstrap': ci95[0] == ci95[1],
           'interval_method': 'pointwise percentile crossed bootstrap; linear quantiles'}
    if cells is not None:
        empty = nothing_to_compare(cells[0], cells[1], blocks)
        if empty:
            row['underlying_classification'] = row['classification']
            row['underlying_sensitivity_margin_0_10'] = row['sensitivity_margin_0_10']
            row['classification'] = empty
            row['sensitivity_margin_0_10'] = empty
    return row


def bootstrap(y, bands, rng, n_boot=C.BOOT_N):
    """Return all four arm means for each shared crossed-stratified draw."""
    y = np.asarray(y, dtype=float)
    if y.ndim != 3 or y.shape[0] != 4 or min(y.shape[1:]) < 1:
        raise ValueError('Expected four arms, at least one block and one scenario')
    if not np.isfinite(y).all() or not np.isin(y, [0, 1]).all() or len(bands) != y.shape[2] or n_boot < 2:
        raise ValueError('Outcomes must be complete binary cells with matching bands')
    nb, ns = y.shape[1:]
    groups = [np.flatnonzero(np.asarray(bands) == b) for b in dict.fromkeys(bands)]
    if any(len(g) != len(groups[0]) for g in groups):
        raise ValueError('Equal declared band weights require equal planned sample sizes')
    block_draw = rng.integers(nb, size=(n_boot, nb))
    wb = np.zeros((n_boot, nb))
    np.add.at(wb, (np.repeat(np.arange(n_boot), nb), block_draw.ravel()), 1 / nb)
    ws = np.zeros((n_boot, ns))
    for ids in groups:
        sampled = rng.choice(ids, size=(n_boot, len(ids)))
        np.add.at(ws, (np.repeat(np.arange(n_boot), len(ids)), sampled.ravel()), 1 / ns)
    return np.einsum('rb,abs,rs->ar', wb, y, ws, optimize=True)


def bootstrap_by_band(y, bands, rng, n_boot=C.BOOT_N):
    """Ruling 38, point 4. Return {band: the four arms' mean in that band, for every replicate}, all from ONE shared draw:
    one draw of blocks and one draw of scenarios in each band, as `bootstrap` makes them and in the same order, so with the
    same generator state the mean of the bands' arrays is bootstrap's array. `bootstrap` itself is left as it was, so the
    primary intervals keep their numbers. These resamples are shared between the bands; they are not the primaries' own."""
    y = np.asarray(y, dtype=float)
    if y.ndim != 3 or y.shape[0] != 4 or min(y.shape[1:]) < 1:
        raise ValueError('Expected four arms, at least one block and one scenario')
    if not np.isfinite(y).all() or not np.isin(y, [0, 1]).all() or len(bands) != y.shape[2] or n_boot < 2:
        raise ValueError('Outcomes must be complete binary cells with matching bands')
    nb, ns = y.shape[1:]
    order = list(dict.fromkeys(bands))
    groups = [np.flatnonzero(np.asarray(bands) == b) for b in order]
    if any(len(g) != len(groups[0]) for g in groups):
        raise ValueError('Equal declared band weights require equal planned sample sizes')
    block_draw = rng.integers(nb, size=(n_boot, nb))
    wb = np.zeros((n_boot, nb))
    np.add.at(wb, (np.repeat(np.arange(n_boot), nb), block_draw.ravel()), 1 / nb)
    out = {}
    for band, ids in zip(order, groups):
        sampled = rng.choice(ids, size=(n_boot, len(ids)))
        ws = np.zeros((n_boot, ns))
        np.add.at(ws, (np.repeat(np.arange(n_boot), len(ids)), sampled.ravel()), 1 / len(ids))
        out[band] = np.einsum('rb,abs,rs->ar', wb, y, ws, optimize=True)
    return out


def close_minus_distant(y, bands, rng, n_boot=C.BOOT_N):
    """Ruling 38, point 4, RQ4's descriptive estimate for one task: (D - A on close targets) minus (D - A on distant
    targets, the middle and wide bands together), with its interval made from the same resamples for both parts. It has
    no section 6.4 name. The distant mean is the mean of the middle and wide bands' means, since the bands have equal
    weight. If D and A have nothing to compare in the task's cells, that is recorded under nothing_to_compare."""
    y = np.asarray(y, dtype=float)
    by_band = bootstrap_by_band(y, bands, rng, n_boot)
    close = by_band['close']
    far = [by_band[b] for b in by_band if b != 'close']
    distant = np.mean(far, axis=0)
    d, a = C.ARMS.index('D'), C.ARMS.index('A')
    mask = np.asarray(bands) == 'close'
    p_close = y[d][:, mask].mean() - y[a][:, mask].mean()
    p_far = np.mean([y[d][:, np.asarray(bands) == b].mean() - y[a][:, np.asarray(bands) == b].mean()
                     for b in by_band if b != 'close'])
    diff = (close[d] - close[a]) - (distant[d] - distant[a])

    def part(point, draws):
        return {'estimate': round(float(point), 12), 'ci95': interval(draws), 'ci90': interval(draws, .90)}
    row = {**part(p_close - p_far, diff), 'd_minus_a_close': part(p_close, close[d] - close[a]),
           'd_minus_a_distant': part(p_far, distant[d] - distant[a]), 'descriptive': True, 'section_6_4_name': None,
           'interval_method': 'percentile; one crossed draw shared by the close and distant parts, not the primaries\' own draws'}
    empty = nothing_to_compare(y[d], y[a], y.shape[1])
    if empty:
        row['nothing_to_compare'] = empty
    return row


def comparisons(y, bands, rng, n_boot=C.BOOT_N):
    draws = bootstrap(y, bands, rng, n_boot)
    y_ = np.asarray(y)
    points = y_.mean(axis=(1, 2))
    results = {}
    for key, (a, b) in C.STEPS.items():
        ai, bi = C.ARMS.index(a), C.ARMS.index(b)
        results[key] = estimate_record(points[ai] - points[bi], draws[ai] - draws[bi],
                                       (y_[ai], y_[bi]), y_.shape[1])
    return results, points, draws


def usage(rows):
    """Unknown cost/usage stays unknown, while the known subtotal is retained."""
    out = {'calls': len(rows), 'served_by': dict(Counter(r.get('served_by') or 'unavailable' for r in rows))}
    for field in ('input_tokens', 'output_tokens', 'list_cost_usd'):
        vals = [r.get(field) for r in rows]
        known = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0]
        out[field] = sum(known) if len(known) == len(rows) else None
        out[field + '_known_subtotal'] = sum(known)
        out[field + '_calls_known'] = len(known)
    return out


def sign_of(estimate) -> str:
    """The sign of a per-task point estimate. An estimate of exactly 0 has no sign: '0'."""
    return '+' if estimate > 0 else '-' if estimate < 0 else '0'


def task_summary(task, row):
    return {'task': task, 'estimate': row['estimate'], 'ci95': row['ci95'], 'name': row['classification']['class']}


def answer(row, per_task):
    """Ruling 38, point 3: the answer to RQ1 for one pooled step, from the pooled result's name and the signs of the three
    per-task point estimates. The signs differ when one task's estimate is above 0 and another's below it; a task whose
    estimate is exactly 0 differs from neither. Each cell of the ruling's table is one branch below. A cell the ruling says
    cannot occur raises an error. row is a pooled step, per_task its three per-task rows."""
    signs = {t: sign_of(r['estimate']) for t, r in per_task.items()}
    differ = '+' in signs.values() and '-' in signs.values()
    name = row['classification']['class']
    out = {'result': name, 'signs': signs, 'signs_differ': differ,
           'per_task': [task_summary(t, r) for t, r in per_task.items()]}
    if name == 'task_dependent':
        if not differ:
            raise ValueError('Ruling 38 table: a task-dependent step whose per-task signs do not differ cannot occur')
        raised = [t for t, r in per_task.items() if base_classification(r)['direction'] == 'gain']
        lowered = [t for t, r in per_task.items() if base_classification(r)['direction'] == 'loss']
        out.update(status='answered', raised_on=raised, lowered_on=lowered,
                   text='The step raised success on ' + ', '.join(raised) + ' and lowered it on ' + ', '.join(lowered)
                   + ', each shown by that task\'s own 95% interval.')
    elif name in ('different_not_equivalent', 'different_and_equivalent'):
        direction = row['classification']['direction']
        word = 'gain' if direction == 'gain' else 'loss'
        out.update(status='answered', text=f'A pooled {word} over these three tasks.')
        if differ:
            other = [task_summary(t, r) for t, r in per_task.items()
                     if signs[t] == ('-' if direction == 'gain' else '+')]
            out['other_sign_tasks'] = other
            out['text'] += ' The tasks whose estimate has the other sign are named with their intervals: ' + '; '.join(
                f"{o['task']} {o['estimate']:+.4f} ({o['ci95'][0]:+.4f}, {o['ci95'][1]:+.4f})" for o in other) + '.'
    elif name == 'equivalent_not_different':
        if differ:
            out.update(status='not_settled',
                       text='Not settled. The average is near zero while the tasks\' estimates point in opposite directions. '
                            'Each is given with its interval. This does not show that the step made no difference.')
        else:
            out.update(status='answered', text='No pooled gain or loss as large as the margin over these three tasks.')
    elif name == 'unresolved':
        listed = ', '.join(f'{t} {s}' for t, s in signs.items())
        out.update(status='unresolved', text=f'Unresolved. The per-task signs are: {listed}.')
    elif name in NOTHING_TO_COMPARE:
        if differ:
            raise ValueError('Ruling 38 table: a result with nothing to compare cannot have per-task signs that differ')
        out.update(status='answered', text=row['classification']['name'][0].upper() + row['classification']['name'][1:] + '.')
    else:
        raise ValueError(f'Unknown pooled result {name!r}')
    return out


def pooled_comparisons(task_points, task_draws, task_steps, task_cells=None):
    """Pool only the three named tasks, retaining opposing task evidence. task_cells ({task: array of arms by blocks by
    scenarios}) lets the pooled step be tested for having nothing to compare, on the cells of the three tasks together
    (ruling 38, point 2), and then N is the number of blocks of the three tasks added up."""
    if set(task_points) != set(C.TASKS):
        return {}
    pp = np.mean([task_points[t] for t in C.TASKS], axis=0)
    pd = np.mean([task_draws[t] for t in C.TASKS], axis=0)
    pooled = {}
    for key in ('C-B', 'B-A', 'D-C'):
        a, b = C.STEPS[key]
        ai, bi = C.ARMS.index(a), C.ARMS.index(b)
        cells = blocks = None
        if task_cells is not None:
            cells = tuple(np.concatenate([np.asarray(task_cells[t])[i].ravel() for t in C.TASKS]) for i in (ai, bi))
            blocks = sum(np.asarray(task_cells[t]).shape[1] for t in C.TASKS)
        row = estimate_record(pp[ai] - pp[bi], pd[ai] - pd[bi], cells, blocks)
        per_task = {t: task_steps[t][key] for t in C.TASKS}
        signs = [base_classification(r)['direction'] for r in per_task.values()]
        dependent = 'gain' in signs and 'loss' in signs
        row.update(task_dependent=dependent, per_task=per_task,
                   pooled_class_used=not dependent, weight_per_named_task=1 / 3)
        if cells is not None:
            row['blocks_counted'] = 'blocks of the three tasks added up'
        if dependent:
            row['underlying_classification'] = row['classification']
            row['classification'] = {'class': 'task_dependent'}
        if task_cells is not None:
            row['answer'] = answer(row, per_task)
        pooled[key] = row
    return pooled


def primary_pass(task_data, boot_seed, n_boot):
    """The draws behind the nine intervals, three primary and six secondary (ruling 88). Each task has a generator of its own, seeded with [boot_seed, 0, the task's
    index in C.TASKS] (the index analyse_snapshot gives the task for the secondaries, whose generators are
    [boot_seed, 1, index] and [boot_seed, 2, index]), and nothing else uses it. A task's draws come from it in this order:
    all bands, then each band, then the middle and wide bands together. So one task's primary intervals do not depend on
    another task's data or on any secondary (ruling 46, point 1). The pooled steps keep each task's all-band draws.
    task_data is {task: {'y', 'bands', 'unqualified'}} with y of arms by blocks by scenarios ('unqualified' is not read here).
    The three pooled steps (B - A, C - B and D - C) are the primary intervals. The six per-task D - A intervals, close and
    middle-wide for each task, are secondary: ruling 88 moved them out of the primary set at N = 40, and they are computed
    from the same draws, in the same order, under the same names as before. 'intervals' holds all nine in the order they
    were always made (each task's two D - A intervals, then the pooled steps), for the fills and the sensitivity analyses,
    which fill every one of them.
    Returns {'tasks': per task, 'pooled': the pooled steps, 'primary': the three pooled steps, 'secondary_intervals': the six
    D - A intervals, 'intervals': all nine, 'points': per task arm means}."""
    tasks, intervals, points, draws, cells = {}, {}, {}, {}, {}
    for task, d in task_data.items():
        rng = np.random.default_rng([boot_seed, 0, C.TASKS.index(task)])
        y, bands = d['y'], d['bands']
        steps, points[task], draws[task] = comparisons(y, bands, rng, n_boot)
        cells[task] = y
        by_band = {}
        for band in C.BANDS:
            mask = np.asarray(bands) == band
            by_band[band] = comparisons(y[:, :, mask], [band] * int(mask.sum()), rng, n_boot)[0]
        distant = np.asarray(bands) != 'close'
        middle_wide = comparisons(y[:, :, distant], list(np.asarray(bands)[distant]), rng, n_boot)[0]
        tasks[task] = {'steps': steps, 'by_band': by_band}
        intervals[task + ':D-A:close'] = by_band['close']['D-A']
        intervals[task + ':D-A:middle-wide'] = middle_wide['D-A']
    secondary = dict(intervals)
    pooled = pooled_comparisons(points, draws, {t: r['steps'] for t, r in tasks.items()}, cells)
    primary = {'pooled:' + key: row for key, row in pooled.items()}
    intervals.update(primary)
    return {'tasks': tasks, 'pooled': pooled, 'primary': primary, 'secondary_intervals': secondary,
            'intervals': intervals, 'points': points}


def designation(key):
    """'primary' for a pooled step, 'secondary' for a per-task D - A interval (ruling 88)."""
    return 'primary' if key.startswith('pooled:') else 'secondary'


def first_sight_m(outcome):
    """The true distance from the drone to the zone's edge at the first reading that shows the zone, as
    protocol/analysis.threat_first_sight reads it (that file is not imported: it reads a folder). None for a flight whose
    outcome has no zone that switched on or does not carry the fields."""
    starts = outcome.get('event_starts') or {}
    best = None
    for i, event in enumerate(outcome.get('events') or []):
        start = starts.get(str(i))
        if not event or event[0] != 'threat' or start is None or len(event) < 6:
            continue
        seen = [s for s in outcome.get('native_steps') or [] if s.get('t') == start + 1]
        if seen:
            gap = round(math.hypot(seen[0]['north_m'] - event[3], seen[0]['east_m'] - event[4]) - event[5], 2)
            best = gap if best is None else min(best, gap)
    return best


def distribution(values):
    """n, median, 99th percentile (nearest rank) and largest of a list of numbers; None for an empty list."""
    xs = sorted(values)
    if not xs:
        return None
    return {'n': len(xs), 'median': round(float(np.median(xs)), 6),
            'p99': xs[min(len(xs) - 1, math.ceil(0.99 * len(xs)) - 1)], 'max': xs[-1]}


def timing_figures(outcomes):
    """Section 4.6 and 6.5: the timing figures of a set of flights, pooled over their decisions. ardupilot.ladder.timing
    reads each flight (the gate and the driver use the same function). Figures a flight does not carry are counted, not
    guessed: flights_with_no_lag_figures, flights_without_call_times, and zone flights are those with a first sight."""
    from ardupilot import ladder as L
    lags, own, observations, missed, late, no_lag, no_calls = [], [], 0, 0, 0, 0, 0
    sights, procedure, guard = [], [], []
    for o in outcomes:
        t = L.timing(o)
        late += bool(t['late'])
        if t['median_lag_s'] is None:
            no_lag += 1
        else:
            lags.extend(s['decision_lag_s'] for s in o['native_steps'])
            own.append(t['max_own_lag_s'])
            observations += t['observations_late']
            missed += t['missed_deadlines']
        sight = first_sight_m(o)
        if sight is not None:
            sights.append(sight)
        calls = o.get('_call_wall_s')
        if calls is None:
            no_calls += 1
        else:
            procedure.extend(calls['procedure'])
            guard.extend(calls['guard'])
    return {'flights': len(outcomes), 'flights_with_no_lag_figures': no_lag, 'late_flights': late, 'decisions': len(lags),
            'median_recorded_lag_s': round(float(np.median(lags)), 6) if lags else None,
            'max_recorded_lag_s': max(lags) if lags else None,
            'share_of_decisions_at_least_0_1s_late': round(sum(x >= L.LATE_SHARE_FROM_S for x in lags) / len(lags), 6) if lags else None,
            'max_own_lag_s': max(own) if own else None, 'observations_read_a_step_or_more_late': observations,
            'missed_deadlines': missed,
            'first_sight_m': {'zone_flights': len(sights), 'median': round(float(np.median(sights)), 3) if sights else None,
                              'min': min(sights) if sights else None},
            'flights_without_call_times': no_calls,
            'procedure_call_s': distribution(procedure), 'guard_call_s': distribution(guard)}


KINDS = ('c0', 'c1', 'fresh', 'repair')
SLOT_STATES = ('valid_at_first_call', 'valid_after_format_repair', 'not_valid')


def candidate_kind(candidate_id):
    return 'c0' if candidate_id == 'c0' else 'c1' if candidate_id == 'c1' else 'fresh' if candidate_id[0] == 'f' else 'repair'


def slot_state(meta):
    """Ruling 37 and 38: a candidate slot is valid at the first call, valid after the format repair (a second call to the
    model for the same slot), or not valid, which uses the slot up."""
    if not meta['format_valid']:
        return 'not_valid'
    return 'valid_at_first_call' if len(meta['call_ids']) == 1 else 'valid_after_format_repair'


def arms_of_call(call, row_of):
    """The arms whose learner flew a learning call: the first-round list P0 for A, B and C and P1 for D, or the trial
    folder an arm's trial used. A call two arms share (B and C's trial of c0) counts for both."""
    if call == 'flights/first/P0':
        return ['A', 'B', 'C']
    if call == 'flights/first/P1':
        return ['D']
    return [arm for arm, row in row_of.items() if any(t.get('flight_dir') == call for t in row['trials'])]


def calls_flown_again(learn):
    """From a block's timing.json rows: for each call, the attempts set aside as late and the flights kept late. Returns
    ({call: set of attempt numbers set aside}, {call: flights kept late}). A block with no rows gives two empty dicts."""
    aside, kept = {}, Counter()
    for r in learn.get('timing') or []:
        if 'set_aside_from' in r:
            aside.setdefault(r['set_aside_from'].rsplit('/', 1)[0], set()).add(r.get('attempt'))
        if r.get('kept_late'):
            kept[r['flight'].rsplit('/', 1)[0]] += 1
    return aside, kept


def charged_known(rows):
    vals = [r['charged_usd'] for r in rows if isinstance(r.get('charged_usd'), (int, float)) and not isinstance(r.get('charged_usd'), bool)]
    return {'rows': len(rows), 'rows_with_charge': len(vals), 'charged_usd_known_subtotal': round(sum(vals), 6)}


def contrast_group(key):
    """The group of fills an interval belongs to: 'D-A' for the six D - A intervals (they share one pair of fills), and
    the step's own name ('B-A', 'C-B', 'D-C') for a pooled step."""
    return 'D-A' if ':D-A:' in key else key.split(':', 1)[1]


def filled(task_data, late_mask, late_source, group, bound):
    """Build G4. task_data with the kept-late hazard cells of the two arms of a contrast set to the value that gives one bound
    of X - Y. X, Y = C.STEPS[group]. For the lower bound each kept-late cell of X is 0 and each of Y is 1; for the upper bound
    the reverse. The two arms' cells for one flight are one flight: where X and Y flew the same source in the same block, the
    flight is the same, so its value cancels in X - Y and both cells are set to 0 whatever the bound. Arms other than X and Y
    are left as kept (an interval of this group does not read them)."""
    x, y_arm = (C.ARMS.index(a) for a in C.STEPS[group])
    x_value, y_value = (0, 1) if bound == 'lower' else (1, 0)
    out = {}
    for task, d in task_data.items():
        y = d['y'].copy()
        mx, my = late_mask[task][x], late_mask[task][y_arm]
        sources_x, sources_y = late_source[task][x], late_source[task][y_arm]
        same = np.array([sx is not None and sx == sy for sx, sy in zip(sources_x, sources_y)])[:, None]
        shared = mx & my & same
        y[x] = np.where(mx, x_value, y[x])
        y[y_arm] = np.where(my, y_value, y[y_arm])
        y[x] = np.where(shared, 0, y[x])
        y[y_arm] = np.where(shared, 0, y[y_arm])
        out[task] = {**d, 'y': y}
    return out


def kept_late_report(snapshot, task_data, late_mask, late_cells, late_source, primary, boot_seed, n_boot):
    """Ruling 39, point 2, as ruling 49, point 4 changed it. The evaluation flights kept late on a phase's third attempt, by
    arm, and for each of the nine intervals (three primary, six secondary, ruling 88) its two real bounds. The lower bound of X - Y takes each kept-late cell of
    X as 0 and each of Y as 1; the upper bound the reverse; a flight both arms share cancels (see `filled`). The six D - A
    intervals share one pair of fills; each pooled step has its own. Each fill replays the whole draw sequence of the primary
    pass on a fresh generator with the same seed and keeps only the rows of its own group, so with no kept-late cell both
    fills are the intervals exactly. `primary` here is the dict of all nine (the key names are kept for the readers of
    earlier records); 'designation' says which are primary. Retention flights are reported but are not in the primary cells."""
    by_phase = Counter()
    for (phase, _, _, _), ids in snapshot['kept_late_eval'].items():
        by_phase[phase] += len(ids)
    cells_set = int(sum(m.sum() for m in late_mask.values()))
    out = {'flights_by_phase': dict(by_phase), 'flights_in_all': int(sum(by_phase.values())),
           'cells_by_arm': late_cells, 'primary_cells_set': cells_set,
           'fills': {g: {'contrast': f'{C.STEPS[g][0]} - {C.STEPS[g][1]}',
                         'lower': f'each kept-late cell of {C.STEPS[g][0]} is 0 and of {C.STEPS[g][1]} is 1',
                         'upper': f'each kept-late cell of {C.STEPS[g][0]} is 1 and of {C.STEPS[g][1]} is 0',
                         'shared_flight': 'cancels: both cells are set to 0'} for g in C.STEPS},
           'designation': {k: designation(k) for k in primary},
           'primary_under_lower_fill': {}, 'primary_under_upper_fill': {}}
    for group in C.STEPS:
        keys = [k for k in primary if contrast_group(k) == group]
        for bound in ('lower', 'upper'):
            done = primary_pass(filled(task_data, late_mask, late_source, group, bound), boot_seed, n_boot)['intervals']
            for k in keys:
                out[f'primary_under_{bound}_fill'][k] = done[k]
    low, high = out['primary_under_lower_fill'], out['primary_under_upper_fill']
    out['primary_under_lower_fill'] = {k: low[k] for k in primary}
    out['primary_under_upper_fill'] = {k: high[k] for k in primary}
    names = {k: [primary[k]['classification']['class'], low[k]['classification']['class'], high[k]['classification']['class']] for k in primary}
    out['names_change'] = {k: v for k, v in names.items() if len(set(v)) > 1}
    return out


def attempts_flown_again(snapshot):
    """Ruling 39, point 2. For every evaluation phase that was flown again, how many cells of each set-aside attempt differ
    from the attempt kept. A cell the attempt has no readable outcome for is counted apart (a crashed attempt may be partial)."""
    phases = {}
    for item in snapshot['evaluation_attempts']:
        kept = (snapshot['hazard'] if item['phase'] == 'threat3' else snapshot['retention'])[(item['task'], item['block'], item['source'])]
        differ = [ep for ep, v in item['cells'].items() if v is not None and v != kept[ep]['goal_met']]
        absent = [ep for ep, v in item['cells'].items() if v is None]
        name = f"{item['phase']}-{item['task']}-b{item['block']}-{item['source']}"
        phases.setdefault(name, []).append({'attempt': item['attempt'], 'reason': item['reason'], 'cells': len(item['cells']),
                                            'cells_differing_from_the_attempt_kept': len(differ),
                                            'cells_without_an_outcome': len(absent), 'differing': differ})
    return {'phases': phases, 'phases_flown_again': len(phases),
            'attempts_set_aside': sum(len(v) for v in phases.values()),
            'cells_compared': sum(a['cells'] - a['cells_without_an_outcome'] for v in phases.values() for a in v),
            'cells_differing': sum(a['cells_differing_from_the_attempt_kept'] for v in phases.values() for a in v)}


def spend_stops(snapshot):
    """Ruling 39, point 3. Every scheduler session's spending stop and whether the --spend-limit flag set it, from the gate's
    report, and a plain sentence for the paper. The figure the protocol fixes is the gate's (run_scored3.SPEND_LIMIT_USD_3)."""
    g = snapshot['gate']
    sessions, other, fixed = g['session_spend_stops'], g['sessions_with_other_spend_stop'], g['spend_stop_in_protocol_usd']
    if len(snapshot.get('roots', ())) > 1 and not snapshot['pilot']:
        # Build H7: three one-task roots, each with its own stop set by --spend-limit (the gate refuses any above US$20 or not from
        # the flag), so the stops add up to at most three times the largest. The protocol's single figure is not each root's.
        highest = {r['task']: max([s['spend_limit_usd'] for s in sessions if s.get('task') == r['task']] or [None]) for r in snapshot['roots']}
        total = sum(v for v in highest.values() if v is not None)
        text = ('The scored run flew as three runs, one task each. Every session had a spending stop set by --spend-limit; the highest '
                'of each run was ' + ', '.join(f'US${v:g} for {k}' for k, v in highest.items() if v is not None)
                + f', US${total:g} in all (the protocol\'s whole-run stop is US${fixed:g}).')
        return {'protocol_stop_usd': fixed, 'sessions': sessions, 'sessions_with_other_stop': [], 'statement': text,
                'highest_stop_by_root_usd': highest, 'highest_stops_added_usd': total}
    if snapshot['pilot']:
        text = ('This is a pilot. The gate does not judge a pilot\'s stops against the protocol\'s US$'
                f'{fixed:g}; the stops it recorded are listed.')
    elif not sessions:
        text = 'The gate has no session record to read the spending stop from.'
    elif other:
        listed = '; '.join(f"the {e['event']} at {e['time']} had US${e['spend_limit_usd']:g}"
                           f"{' (set by the --spend-limit flag)' if e['spend_limit_from_flag'] else ''}" for e in other)
        text = (f"In {len(other)} of {len(sessions)} sessions the spending stop was not the protocol's US${fixed:g}: {listed}. "
                'The paper says so.')
    else:
        text = f"Every one of the {len(sessions)} sessions had the protocol's spending stop of US${fixed:g}."
    return {'protocol_stop_usd': fixed, 'sessions': sessions, 'sessions_with_other_stop': other, 'statement': text}


FAULT_STATUSES = ('timed_out', 'copied')


def fault_of(provider_rows):
    """The model-service fault that stopped a learning block, from the provider's log (claude-usage.jsonl): the last row that
    the driver treats as a fault. These are a call that timed out, a reply whose message id was seen before (status copied),
    and a call that failed with an error type, with the HTTP status where the row has one (ardupilot/claude_provider.py and
    ladder.py). Returns (kind, http_status) or None. An empty reply or a refusal is a used slot, not a fault."""
    found = None
    for row in provider_rows:
        status = row.get('status')
        if status == 'timed_out':
            found = ('timed_out', None)
        elif status == 'copied':
            found = ('RepeatedMessageId', None)
        elif status == 'failed' and row.get('error'):
            found = (str(row['error']), row.get('http_status'))
    return found


def blocks_set_aside(snapshot):
    """Ruling 39, points 3 and 4. The learning blocks set aside and flown again: by the reason on the receipt, by the
    scheduler's evidence for a crash, and, for those whose provider log ends in a fault, by kind of fault and HTTP status."""
    reasons, evidence, faults = Counter(), Counter(), Counter()
    listed, without = [], 0
    for item in snapshot['set_aside_learning']:
        reasons[item['reason'] or 'unreadable receipt'] += 1
        if item['crash_evidence_kind']:
            evidence[item['crash_evidence_kind']] += 1
        fault = fault_of(item['provider'])
        if fault:
            label = fault[0] + (f', HTTP {fault[1]}' if fault[1] is not None else ', no HTTP status in the record')
            faults[label] += 1
        else:
            without += 1
        listed.append({'phase': item['phase'], 'attempt': item['attempt'], 'reason': item['reason'],
                       'fault': None if not fault else {'kind': fault[0], 'http_status': fault[1]}})
    return {'blocks': len(listed), 'by_reason': dict(reasons), 'by_crash_evidence': dict(evidence),
            'stopped_by_a_fault': {'blocks': sum(faults.values()), 'by_kind_and_http_status': dict(faults)},
            'without_a_fault_in_the_provider_log': without, 'list': listed}


def spend_by_root(snapshot):
    """Build H7. The spend of each run root and in total: the list cost of the unique calls of its learning blocks and of the blocks
    set aside in it, and the provider's charge where the rows have one. A single root reports itself as the one root. The total is
    the sum of the roots'; for one root it is that root's."""
    roots = snapshot.get('roots') or [{'task': ','.join(snapshot['learning']), 'root': snapshot.get('root')}]
    out = []
    for r in roots:
        tasks = [t for t in snapshot['learning'] if r['task'] == ','.join(snapshot['learning']) or t == r['task']]
        calls = [row for t in tasks for block in snapshot['learning'][t].values() for row in block['usage']]
        aside = [item for item in snapshot['set_aside_learning'] if item['phase'].split('-')[1] in tasks]
        aside_rows = [row for item in aside for row in item['usage']]
        out.append({'task': r['task'], 'root': r.get('root'), 'unique': usage(calls),
                    'learning_blocks_set_aside': {'blocks': len(aside), 'usage': usage(aside_rows),
                                                  'provider_charge': charged_known([row for item in aside for row in item['provider']])}})
    def listed(entry):
        parts = [entry['unique']['list_cost_usd'], entry['learning_blocks_set_aside']['usage']['list_cost_usd']]
        return None if None in parts else sum(parts)
    sums = [listed(e) for e in out]
    return {'roots': out, 'list_cost_usd_by_root': {e['task']: s for e, s in zip(out, sums)},
            'list_cost_usd_total': None if None in sums else round(sum(sums), 6),
            'note': 'List price of the unique calls and of the blocks set aside, without the calls that never reached a spending row.'}


DESCRIPTIVE_RULE = ('Counts and means of the fresh zone flights (the hazard evaluation), with no interval and no resampling. A block '
                    'that adopted nothing counts as 0 in every cell, as in arm_means, except in the fields marked adopting_blocks.')


def descriptive_counts(y, bands, adopted):
    """Ruling 55, point 3. For one task: y is arms by blocks by scenarios (0 or 1), bands names each scenario's distance band,
    adopted is arms by blocks (True where the arm adopted a procedure). Returns, for each arm: the successes out of the flights
    possible (all blocks times all scenarios); the same restricted to the blocks that adopted, with their number; and the mean
    success in each band over all blocks. It reads the cells only. It draws nothing and no interval comes from it."""
    out = {}
    bands = np.asarray(bands)
    n_blocks, n_scenarios = y.shape[1], y.shape[2]
    for i, arm in enumerate(C.ARMS):
        yes = adopted[i]
        n_adopting = int(yes.sum())
        adopting_successes = int(y[i][yes].sum())
        adopting_possible = n_adopting * n_scenarios
        out[arm] = {
            'blocks': n_blocks,
            'successes': int(y[i].sum()),
            'flights_possible': n_blocks * n_scenarios,
            'adopting_blocks': n_adopting,
            'adopting_blocks_successes': adopting_successes,
            'adopting_blocks_flights_possible': adopting_possible,
            'adopting_blocks_mean': round(adopting_successes / adopting_possible, 12) if adopting_possible else None,
            'mean_by_band': {band: round(float(y[i][:, bands == band].mean()), 12) for band in C.BANDS if (bands == band).any()},
            'flights_possible_by_band': {band: int((bands == band).sum()) * n_blocks for band in C.BANDS if (bands == band).any()},
        }
    return out


def analyse_snapshot(snapshot, *, n_boot=C.BOOT_N, boot_seed=C.BOOT_SEED):
    """Pure analysis: all records have already passed validate3.load_run()."""
    seeds, pilot = snapshot['seeds'], snapshot['pilot']
    task_results, close_vs_distant, task_data = {}, {}, {}
    unique_calls, unique_hazard, unique_retention = [], 0, 0
    total_fresh = Counter()
    total_kinds = {k: Counter() for k in KINDS}
    adoption_slots = {a: Counter() for a in C.ARMS}
    arm_timing_flights = {a: {'learning_trials': [], 'evaluation_hazard': [], 'evaluation_retention': []} for a in C.ARMS}
    arm_calls_again = {a: {'calls_flown_again': 0, 'attempts_set_aside': 0, 'flights_kept_late': 0} for a in C.ARMS}
    run_calls_again = {'calls_flown_again': 0, 'attempts_set_aside': 0, 'flights_kept_late': 0, 'blocks_without_timing_rows': 0}
    c0_all = {'blocks': 0, 'blocks_c0_not_valid': 0}
    late_cells = {a: {'hazard_cells': 0, 'retention_cells': 0} for a in C.ARMS}
    late_mask, late_source = {}, {}
    descriptive = {}
    for task, blocks in snapshot['learning'].items():
        ids = sorted(blocks)
        cases = C.evaluation_cases(seeds, task, pilot)
        band_sizes = [len(C.book(seeds, pilot)['threat_evaluation'][task][b]) for b in C.BANDS]
        bands = [b for b, count in zip(C.BANDS, band_sizes) for _ in range(count)]
        y = np.zeros((4, len(ids), len(cases)))
        adopted_cells = np.zeros((4, len(ids)), dtype=bool)
        late_mask[task] = np.zeros(y.shape, dtype=bool)
        late_source[task] = [[None] * len(ids) for _ in C.ARMS]
        retained_cases = C.retention_cases(seeds, task, pilot)
        retained = np.zeros((4, len(ids), len(retained_cases)))
        c0 = np.zeros((len(ids), len(cases)))
        arm_calls = {a: [] for a in C.ARMS}
        arm_counts = {a: 0 for a in C.ARMS}
        arm_flights = {a: {'initial_examples': 3 * len(ids), 'qualification': 0,
                          'hazard_evaluation': 0, 'retention': 0} for a in C.ARMS}
        endings = {a: Counter() for a in C.ARMS}
        unqualified, valid_failed, c0_not_valid = [], [], []
        fresh = Counter()
        slots = {k: Counter() for k in KINDS}
        slots_by_arm = {a: Counter() for a in C.ARMS}
        for j, block in enumerate(ids):
            learn = blocks[block]
            calls = {r['call_id']: r for r in learn['usage']}
            unique_calls.extend(learn['usage'])
            c0_meta = learn['candidates']['c0']
            if not learn['arms_record']['c0_zone_qualified']:
                unqualified.append(j)
                # Ruling 38, point 5: C - B in the blocks where c0 was valid and failed its threat trial. A block where
                # c0 was not valid has no trial to fail; it is counted and left out.
                (valid_failed if c0_meta['format_valid'] else c0_not_valid).append(j)
            elif not c0_meta['format_valid']:
                c0_not_valid.append(j)
            for cid, meta in learn['candidates'].items():
                slots[candidate_kind(cid)][slot_state(meta)] += 1
                if cid in ('f1', 'f2'):
                    fresh['candidates'] += 1
                    if meta['format_valid']:
                        fresh['valid'] += 1
                        if c0_meta['format_valid'] and meta['source_sha256'] == c0_meta['source_sha256']:
                            fresh['same_source_as_c0'] += 1
            for i, arm in enumerate(C.ARMS):
                row = learn['arms_record']['arms'][arm]
                arm_calls[arm].extend(calls[k] for k in row['call_ids'])
                arm_flights[arm]['qualification'] += sum(len(t['outcomes']) for t in row['trials'])
                adoption_slots[arm][row['candidate_id'] if row['adopted'] else 'nothing'] += 1
                for t in row['trials']:
                    if t.get('flight_dir'):
                        arm_timing_flights[arm]['learning_trials'].extend(learn['flights'][t['flight_dir']].values())
                adopted_cells[i, j] = bool(row['adopted'])
                if not row['adopted']:
                    continue
                arm_counts[arm] += 1
                arm_flights[arm]['hazard_evaluation'] += len(cases)
                arm_flights[arm]['retention'] += len(retained_cases)
                flights = snapshot['hazard'][(task, block, row['source_sha256'])]
                ordinary = snapshot['retention'][(task, block, row['source_sha256'])]
                arm_timing_flights[arm]['evaluation_hazard'].extend(flights.values())
                arm_timing_flights[arm]['evaluation_retention'].extend(ordinary.values())
                late_hazard = set(snapshot['kept_late_eval'].get(('threat3', task, block, row['source_sha256']), ()))
                late_retention = set(snapshot['kept_late_eval'].get(('retain3', task, block, row['source_sha256']), ()))
                late_source[task][i][j] = row['source_sha256']
                late_cells[arm]['hazard_cells'] += len(late_hazard)
                late_cells[arm]['retention_cells'] += len(late_retention)
                for k, case in enumerate(cases):
                    late_mask[task][i, j, k] = case.episode_id in late_hazard
                retained[i, j] = [ordinary[c.episode_id]['goal_met'] for c in retained_cases]
                for k, case in enumerate(cases):
                    y[i, j, k] = flights[case.episode_id]['goal_met']
                    endings[arm][flights[case.episode_id]['end_reason']] += 1
            if c0_meta['format_valid']:
                flights = snapshot['hazard'][(task, block, c0_meta['source_sha256'])]
                c0[j] = [flights[c.episode_id]['goal_met'] for c in cases]
            aside, kept = calls_flown_again(learn)
            run_calls_again['blocks_without_timing_rows'] += learn.get('timing') is None
            for call in set(aside) | set(kept):
                n_aside, n_kept = len(aside.get(call, ())), kept.get(call, 0)
                run_calls_again['calls_flown_again'] += bool(n_aside)
                run_calls_again['attempts_set_aside'] += n_aside
                run_calls_again['flights_kept_late'] += n_kept
                for arm in arms_of_call(call, learn['arms_record']['arms']):
                    arm_calls_again[arm]['calls_flown_again'] += bool(n_aside)
                    arm_calls_again[arm]['attempts_set_aside'] += n_aside
                    arm_calls_again[arm]['flights_kept_late'] += n_kept
        task_data[task] = {'y': y, 'bands': bands, 'unqualified': unqualified}
        descriptive[task] = descriptive_counts(y, bands, adopted_cells)
        # RQ4's descriptive estimate and the corrected C - B each have a generator of their own, so that no primary
        # interval's draws move (ruling 38, points 4 and 5)
        idx = C.TASKS.index(task)
        close_vs_distant[task] = close_minus_distant(y, bands, np.random.default_rng([boot_seed, 2, idx]), n_boot)
        conditional = {'blocks': len(valid_failed), 'c0_not_valid_blocks_left_out': len(c0_not_valid), 'C-B': None,
                       'rule': 'blocks where c0 was valid and failed its threat trial (ruling 38, point 5)'}
        if valid_failed:
            conditional['C-B'] = comparisons(y[:, valid_failed, :], bands, np.random.default_rng([boot_seed, 1, idx]), n_boot)[0]['C-B']
        valid_rows = [j for j in range(len(ids)) if j not in c0_not_valid]
        task_results[task] = {
            'blocks': len(ids), 'scenarios': len(cases),
            'arm_means': {},
            'adoption': {a: {'adopted': arm_counts[a], 'scheduled': len(ids)} for a in C.ARMS},
            'standalone_usage': {a: usage(arm_calls[a]) for a in C.ARMS},
            'standalone_flights': arm_flights,
            'conditional_first_qualification_failure': conditional,
            'c0_one_shot': {'mean': round(float(c0.mean()), 12), 'scheduled_outcomes': int(c0.size),
                            'blocks': len(ids), 'blocks_c0_not_valid': len(c0_not_valid),
                            'not_valid_c0_counted_as': 0,
                            'mean_over_blocks_with_valid_c0': round(float(c0[valid_rows].mean()), 12) if valid_rows else None},
            'actual_flight_endings_by_arm': {a: dict(v) for a, v in endings.items()},
            'planned_arm_outcomes': int(y.size),
            'fresh_candidates': dict(candidates=fresh['candidates'], valid=fresh['valid'], same_source_as_c0=fresh['same_source_as_c0']),
            'slots_by_kind': {k: {state: slots[k][state] for state in SLOT_STATES} for k in KINDS},
            'retention': {arm: {'primary_style_mean': round(float(retained[i].mean()), 12),
                                'met': int(retained[i].sum()),
                                'planned': int(retained[i].size),
                                'flown_given_adoption': arm_counts[arm] * len(retained_cases)}
                          for i, arm in enumerate(C.ARMS)},
        }
        c0_all['blocks'] += len(ids)
        c0_all['blocks_c0_not_valid'] += len(c0_not_valid)
        total_fresh.update(fresh)
        for k in KINDS:
            total_kinds[k].update(slots[k])
        unique_hazard += sum(len(v) for (t, _, _), v in snapshot['hazard'].items() if t == task)
        unique_retention += sum(len(v) for (t, _, _), v in snapshot['retention'].items() if t == task)
    done = primary_pass(task_data, boot_seed, n_boot)
    for task, d in done['tasks'].items():
        task_results[task]['arm_means'] = dict(zip(C.ARMS, [round(float(v), 12) for v in done['points'][task]]))
        task_results[task]['all_band_steps'] = d['steps']
        task_results[task]['steps_by_band'] = d['by_band']
    pooled, primary, secondary_intervals = done['pooled'], done['primary'], done['secondary_intervals']
    kept_late = kept_late_report(snapshot, task_data, late_mask, late_cells, late_source, done['intervals'], boot_seed, n_boot)
    aside_blocks = snapshot['set_aside_learning']
    aside_rows = [r for item in aside_blocks for r in item['usage']]
    gate = snapshot['gate']
    # G6: provider rows in set-aside blocks that have no spending row (a process killed between the two writes). Their list cost
    # is in no spending row, so it is added to the set-aside spend here; their charge is already in the provider rows.
    unpaired = gate.get('provider_rows_with_no_spending_row') or {'count': 0, 'list_cost_usd': 0.0, 'charged_usd': 0.0, 'rows_with_charge': 0}
    # J1: a row with no price (a call cut off before its usage arrived) is a call of unknown cost, never a cost of zero. The
    # list cost in this record is then a known subtotal.
    unpaired = {**unpaired, 'rows_without_list_cost': unpaired.get('rows_without_list_cost', 0)}
    secondary = {
        'adoption_by_candidate': {a: dict(adoption_slots[a]) for a in C.ARMS},
        'fresh_candidates_equal_to_c0': {'candidates': total_fresh['candidates'], 'valid': total_fresh['valid'],
                                         'same_source_as_c0': total_fresh['same_source_as_c0'], 'share_of_fresh_candidates': round(total_fresh['same_source_as_c0'] / total_fresh['candidates'], 6) if total_fresh['candidates'] else None,
                                         'share_of_valid_fresh_candidates': round(total_fresh['same_source_as_c0'] / total_fresh['valid'], 6) if total_fresh['valid'] else None},
        'slots_by_kind': {k: {state: total_kinds[k][state] for state in SLOT_STATES} for k in KINDS},
        'timing_by_arm': {a: {group: timing_figures(flights) for group, flights in groups.items()}
                          for a, groups in arm_timing_flights.items()},
        'calls_flown_again_by_arm': arm_calls_again,
        'calls_flown_again_in_the_run': run_calls_again,
        'spend': {'unique': usage(unique_calls),
                  'learning_blocks_set_aside': {'blocks': len(aside_blocks), 'usage': usage(aside_rows),
                                                'provider_rows_with_no_spending_row': unpaired,
                                                'provider_charge': charged_known([r for item in aside_blocks for r in item['provider']])},
                  'unique_plus_set_aside_list_cost_usd': None},
        'message_ids_that_appear_more_than_once': {'count': gate.get('repeated_message_ids'), 'message_ids_seen': gate.get('message_ids_seen'),
                                                   'gate_requires': 0, 'copies_caught': gate.get('copies_caught'),
                                                   'message_ids_in_file_with_no_row': gate.get('message_ids_in_file_with_no_row'),
                                                   'provider_rows_with_no_spending_row': unpaired,
                                                   'message_id_file_fragments': gate.get('message_id_file_fragments', 0)},
        'c0_one_shot': {**c0_all, 'not_valid_c0_counted_as': 0},
    }
    # L2: gateway spending rows past the number of provider rows for their request id, in set-aside blocks. Given only when there
    # are some. Their price is already in the set-aside spend, so it is not added to any total.
    surplus = gate.get('spending_rows_with_no_provider_row')
    if surplus and surplus['count']:
        secondary['spend']['learning_blocks_set_aside']['spending_rows_with_no_provider_row'] = dict(surplus)
    both = [secondary['spend']['unique']['list_cost_usd'], secondary['spend']['learning_blocks_set_aside']['usage']['list_cost_usd']]
    known_unpaired = unpaired['rows_without_list_cost'] == 0
    secondary['spend']['unique_plus_set_aside_list_cost_usd'] = sum(both) + unpaired['list_cost_usd'] if None not in both and known_unpaired else None
    # The known part of the total, and how many calls have no price, are given whenever the total is not known.
    ledger = [secondary['spend']['unique'], secondary['spend']['learning_blocks_set_aside']['usage']]
    # L1: every price that is known counts, including those of a ledger that also holds an unknown one (that ledger's own
    # list_cost_usd is null, but its known subtotal is not).
    secondary['spend']['unique_plus_set_aside_known_subtotal_usd'] = sum(u['list_cost_usd_known_subtotal'] for u in ledger) + unpaired['list_cost_usd']
    secondary['spend']['unique_plus_set_aside_calls_of_unknown_cost'] = (
        sum(u['calls'] - u['list_cost_usd_calls_known'] for u in ledger) + unpaired['rows_without_list_cost'])
    return {'status': 'development only; not scored evidence' if pilot else 'protocol3 scored analysis',
            'tasks': task_results, 'pooled_ladder_steps': pooled, 'primary': primary,
            'secondary_intervals': secondary_intervals,
            'rq4_close_minus_distant': close_vs_distant, 'secondary': secondary, 'kept_late_evaluation': kept_late,
            'evaluation_phases_flown_again': attempts_flown_again(snapshot),
            'descriptive_counts': {'rule': DESCRIPTIVE_RULE, 'by_task': descriptive},
            'spend_stops': spend_stops(snapshot), 'spend_by_root': spend_by_root(snapshot),
            'learning_blocks_set_aside': blocks_set_aside(snapshot),
            'unique_experiment_usage': usage(unique_calls),
            'unique_hazard_flights': unique_hazard, 'unique_retention_flights': unique_retention,
            'unique_experiment_flights': snapshot['unique_flights'],
            'unique_learning_flights': snapshot['unique_flights'] - unique_hazard - unique_retention,
            'requested_models': snapshot['requested_models'],
            'bootstrap': {'seed': boot_seed, 'replicates': n_boot, 'direction_coverage': .95,
                          'equivalence_coverage': .90, 'margin': .20, 'sensitivity_margin': .10,
                          'familywise_claim': False, 'named_task_weights': 'equal'},
            'limitations': ['Pointwise approximate bootstrap intervals, not simultaneous coverage.',
                            'Zero-width empirical bootstrap intervals do not prove population certainty.',
                            'Pooled steps concern these three tasks; per-task results remain visible.']}


RUN_RECORD = 'analysis-run.json'
ANALYSIS_SOURCES = ('analysis3.py', 'validate3.py', 'contract3.py')


def analysis_sources_sha256():
    return {name: C.sha(Path(__file__).with_name(name)) for name in ANALYSIS_SOURCES}


def check_not_run_before(root):
    """Ruling 39, point 5. A scored run is analysed once. If the run root holds the record of an analysis, refuse. Given the three
    roots of a split run (build H7), refuse if any of them holds one."""
    for one in (root if isinstance(root, (list, tuple)) else [root]):
        path = Path(one) / RUN_RECORD
        if path.exists():
            raise FileExistsError(f'{path} exists: this run has been analysed, and a scored run is analysed once. '
                                  'Read the earlier analysis; do not run it again.')


def check_protocol_settings(n_boot, boot_seed):
    """Build G3 (ruling 49, point 3). A scored analysis is made with the protocol's resample count and seed, and with no other.
    Raises ValueError for any other; it runs before the run record is written, so a refused call leaves none."""
    if type(n_boot) is not int or n_boot != C.BOOT_N:
        raise ValueError(f'A scored analysis resamples {C.BOOT_N} times; {n_boot!r} was asked for. Nothing was written.')
    if type(boot_seed) is not int or boot_seed != C.BOOT_SEED:
        raise ValueError(f'A scored analysis uses the seed {C.BOOT_SEED}; {boot_seed!r} was asked for. Nothing was written.')


def write_run_record(root, out, n_boot=None, boot_seed=None):
    """Ruling 39, point 5. Write the record of this run of the analysis into the run root: the time, the hashes of the
    analysis sources, the output folder, and (G3) the resample count and the seed. It is opened for exclusive creation, so two runs started together cannot both
    write one, and a second run finds it and refuses (check_not_run_before). For a split run (build H7) `root` is the three roots:
    the one record, naming all three, is written into each, and if one of the three cannot be created the ones made are removed."""
    roots = [Path(r) for r in (root if isinstance(root, (list, tuple)) else [root])]
    record = {'time': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
              'analysis_sources_sha256': analysis_sources_sha256(), 'output_folder': str(Path(out).resolve()),
              'resamples': n_boot, 'seed': boot_seed}
    if len(roots) > 1:
        record['roots'] = [str(r.resolve()) for r in roots]
    made = []
    try:
        for one in roots:
            path = one / RUN_RECORD
            with open(path, 'x') as f:
                made.append(path)
                f.write(json.dumps(record, indent=2) + '\n')
    except FileExistsError as error:
        for path in made:
            path.unlink(missing_ok=True)
        raise FileExistsError(f'{path} exists: this run has been analysed, and a scored run is analysed once.') from error
    return made[0] if len(made) == 1 else made


def analyse(root, *, pilot=False, seed_path=C.SEED_PATH, n_boot=C.BOOT_N, boot_seed=C.BOOT_SEED, protocol_path=None, out=None):
    """The gate, then the analysis of its snapshot. `root` is one run root, or the three roots of a split run, one task each (build
    H7), which the gate judges as one run. A pilot may be analysed any number of times. A run that is not a pilot
    is analysed once: this refuses when any root holds the record of an earlier analysis (before the gate, which opens
    every file), and writes the record, naming out (and, for three roots, all three), after the gate has passed and before any
    outcome is read. A run that
    stops after the record is written cannot be analysed again, as the ruling intends. A scored analysis (G3) must use the
    protocol's resample count and seed (check_protocol_settings), checked first; a pilot may use others. The manifests' pilot
    flag must match the mode: the gate refuses any manifest that differs (Run.manifest), before the record is written."""
    from protocol.validate3 import load_runs
    roots = [Path(r) for r in (root if isinstance(root, (list, tuple)) else [root])]
    if not pilot:
        check_protocol_settings(n_boot, boot_seed)
        check_not_run_before(roots)
    gate, snapshot = load_runs(roots if len(roots) > 1 else roots[0], pilot=pilot, seed_path=Path(seed_path), protocol_path=protocol_path)
    if not gate['ok']:
        raise ValueError('Protocol3 evidence gate failed: ' + '; '.join(gate['errors'][:10]))
    if not pilot:
        if out is None:
            raise ValueError('A scored analysis needs its output folder, which the run record names')
        write_run_record(roots if len(roots) > 1 else roots[0], out, n_boot, boot_seed)
    result = analyse_snapshot(snapshot, n_boot=n_boot, boot_seed=boot_seed)
    result['validation'] = gate
    result['input_sha256'] = snapshot['input_sha256']
    result['inputs_aggregate_sha256'] = hashlib.sha256(C.canonical(snapshot['input_sha256'])).hexdigest()
    if len(roots) > 1:
        result['roots'] = snapshot['roots']
    result['analysis_sources_sha256'] = analysis_sources_sha256()
    return result


def result_name(row, pooled=False):
    """The plain words for an interval's result, from its classification (section 6.4 and ruling 38, point 2)."""
    c = row['classification']
    key = c['class']
    if key in NOTHING_TO_COMPARE:
        return c['name']
    if key == 'task_dependent':
        return 'task-dependent: one task gained and another lost, each by its own interval'
    gain = c['direction'] == 'gain'
    if key == 'different_not_equivalent':
        word = ('a useful gain' if c['useful_gain'] else 'a gain') if gain else ('a useful loss' if c['useful_loss'] else 'a loss')
        return word
    if key == 'different_and_equivalent':
        return 'a gain smaller than the margin' if gain else 'a loss smaller than the margin'
    if key == 'equivalent_not_different':
        return ('no pooled gain or loss as large as the margin over these three tasks' if pooled
                else 'no gain or loss as large as the margin')
    return 'unresolved'


def table_row(label, row, pooled=False):
    lo, hi = row['ci95']
    name = result_name(row, pooled)
    if row['classification']['class'] == IDENTICAL:
        bound = row['classification']['one_sided_95_bound_on_share_of_blocks_differing']
        name += f' (one-sided 95% bound on the share of blocks in which the arms would differ: {bound:.1%})'
    return f"| {label} | {row['estimate']:+.4f} | {lo:+.4f}, {hi:+.4f} | {name} | {row['classification']['class']} |"


def fmt(value, digits=4):
    return 'none' if value is None else f'{value:.{digits}f}'


def usd(value):
    """A list cost for the report: 'not known' where a call had no price (a scripted call has none)."""
    return 'not known' if value is None else f'US${value:.4f}'


def kept_late_lines(result):
    """Ruling 39, point 2, as report.md lines."""
    k, again = result['kept_late_evaluation'], result['evaluation_phases_flown_again']
    lines = ['## Evaluation flights kept late and evaluation phases flown again', '',
             'An evaluation phase with a late flight is set aside and flown again, up to two times. The third attempt is kept '
             'whatever its timing, and each late flight in it is kept late.', '']
    if k['flights_in_all']:
        lines.append(f"Flights kept late: {k['flights_in_all']} ({', '.join(f'{p} {n}' for p, n in sorted(k['flights_by_phase'].items()))}). "
                     f"Cells of the nine intervals that belong to them: {k['primary_cells_set']}.")
    else:
        lines.append('No evaluation flight was kept late. Both fills of the intervals below are the intervals as kept.')
    lines += ['', '| Arm | Hazard cells kept late | Retention cells kept late |', '|---|---:|---:|']
    for arm, c in k['cells_by_arm'].items():
        lines.append(f"| {arm} | {c['hazard_cells']} | {c['retention_cells']} |")
    lines += ['', 'The kept-late cells decide a bound only through the arms of the contrast. For the lower bound of X - Y, each '
              'kept-late cell of X is taken as 0 (a failure) and each of Y as 1 (a success); for the upper bound the reverse. A flight '
              'that both arms share is one flight and cancels, so both cells are set to 0. The six D - A intervals share one pair of '
              'fills (D low and A high, then the reverse), and each pooled step has its own. The draws are the primaries\' own. '
              'Each cell below is the interval, then the name of section 6.4 under that fill. All nine intervals are '
              'filled: the three pooled steps are primary and the six per-task D - A intervals are secondary (ruling 88).', '',
              '| Contrast | Designation | As kept | Lower fill | Upper fill |', '|---|---|---|---|---|']
    for key, row in {**result['secondary_intervals'], **result['primary']}.items():
        def cell(r):
            return f"{r['estimate']:+.4f} ({r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}), {result_name(r, key.startswith('pooled:'))}"
        lines.append(f"| {key} | {designation(key)} | {cell(row)} | {cell(k['primary_under_lower_fill'][key])} | {cell(k['primary_under_upper_fill'][key])} |")
    if k['names_change']:
        lines += ['', 'The name differs from the as-kept name under one or both fills for: ' + ', '.join(sorted(k['names_change'])) + '.']
    else:
        lines += ['', 'The name is the as-kept name under both fills for every contrast.']
    lines += ['', 'Evaluation phases flown again: ' + str(again['phases_flown_again']) + f". Attempts set aside: {again['attempts_set_aside']}. "
              f"Cells compared with the attempt kept: {again['cells_compared']}, of which {again['cells_differing']} differ.", '']
    if again['phases']:
        lines += ['| Phase | Attempt set aside | Reason | Cells | Cells differing from the attempt kept | Cells with no outcome |', '|---|---:|---|---:|---:|---:|']
        for name, attempts in again['phases'].items():
            for a in attempts:
                lines.append(f"| {name} | {a['attempt']} | {a['reason']} | {a['cells']} | {a['cells_differing_from_the_attempt_kept']} | {a['cells_without_an_outcome']} |")
        lines.append('')
    return lines


def stops_and_faults_lines(result):
    """Ruling 39, points 3 and 4, as report.md lines."""
    st, ab = result['spend_stops'], result['learning_blocks_set_aside']
    lines = ['## The spending stop of each session, and learning blocks set aside', '',
             'The stop is a test made when a block is about to start. Blocks already running go on spending after it trips. '
             'It counts list price, and the gateway has charged more than list price.', '', st['statement'], '']
    if st['sessions']:
        lines += ['| Session event | Time | Stop (US$) | Set by the flag |', '|---|---|---:|---|']
        for e in st['sessions']:
            lines.append(f"| {e['event']} | {e['time']} | {e['spend_limit_usd']} | {e['spend_limit_from_flag']} |")
        lines.append('')
    lines += [f"Learning blocks set aside and flown again: {ab['blocks']}"
              + (f" ({', '.join(f'{r} {n}' for r, n in sorted(ab['by_reason'].items()))})." if ab['blocks'] else '.')]
    if ab['blocks']:
        lines += [f"Stopped by a fault of the model service (the provider's log ends in one): {ab['stopped_by_a_fault']['blocks']}."]
        for label, n in sorted(ab['stopped_by_a_fault']['by_kind_and_http_status'].items()):
            lines.append(f'- {label}: {n}')
        lines += [f"Set aside with no model-service fault in the provider's log: {ab['without_a_fault_in_the_provider_log']}."]
        if ab['by_crash_evidence']:
            lines.append("The scheduler's evidence for the crashes: " + ', '.join(f'{k} {n}' for k, n in sorted(ab['by_crash_evidence'].items())) + '.')
    lines.append('')
    sb = result.get('spend_by_root')
    if sb:
        lines += ['## Spend by run root, list price', '', '| Root (task) | Unique calls (US$) | Blocks set aside (US$) |', '|---|---:|---:|']
        for r in sb['roots']:
            lines.append(f"| {r['task']} | {fmt(r['unique']['list_cost_usd'], 4)} | {fmt(r['learning_blocks_set_aside']['usage']['list_cost_usd'], 4)} |")
        lines += ['', f"In total: {'not known' if sb['list_cost_usd_total'] is None else 'US$' + fmt(sb['list_cost_usd_total'], 4)}. {sb['note']}", '']
    return lines


def secondary_lines(result):
    """The secondary estimates of section 6.5 that are counts and figures, as report.md lines (ruling 38, point 5)."""
    sec = result['secondary']
    lines = ['## Secondary estimates', '', 'These sit beside the primary intervals and do not override them.', '',
             '### The candidate at which each arm adopted, and how often it adopted nothing', '']
    for arm, counts in sec['adoption_by_candidate'].items():
        lines.append(f"- Arm {arm}: " + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))
    f = sec['fresh_candidates_equal_to_c0']
    lines += ['', '### Fresh candidates whose source equals their block\'s c0', '',
              f"{f['same_source_as_c0']} of {f['valid']} valid fresh candidates ({f['candidates']} fresh slots in all). "
              f"Share of valid fresh candidates: {fmt(f['share_of_valid_fresh_candidates'])}. "
              f"Share of all fresh slots: {fmt(f['share_of_fresh_candidates'])}.",
              '', '### Candidate slots by kind', '',
              'Valid at the first call, valid after the format repair (a second call for the same slot), or not valid.', '',
              '| Kind | Valid at the first call | Valid after the format repair | Not valid |', '|---|---:|---:|---:|']
    for kind, row in sec['slots_by_kind'].items():
        lines.append(f"| {kind} | {row['valid_at_first_call']} | {row['valid_after_format_repair']} | {row['not_valid']} |")
    lines += ['', '### C - B in the blocks where c0 was valid and failed its threat trial', '',
              '| Task | Blocks | Blocks left out because c0 was not valid | Estimate | 95% interval | Result |', '|---|---:|---:|---:|---|---|']
    for task, t in result['tasks'].items():
        c = t['conditional_first_qualification_failure']
        if c['C-B'] is None:
            lines.append(f"| {task} | {c['blocks']} | {c['c0_not_valid_blocks_left_out']} | none | none | no such block |")
        else:
            row = c['C-B']
            lines.append(f"| {task} | {c['blocks']} | {c['c0_not_valid_blocks_left_out']} | {row['estimate']:+.4f} | "
                         f"{row['ci95'][0]:+.4f}, {row['ci95'][1]:+.4f} | {result_name(row)} |")
    c0 = sec['c0_one_shot']
    lines += ['', '### c0 on the evaluation scenarios', '',
              f"A block whose c0 was not valid counts as 0 in every cell, as an arm that adopted nothing does. "
              f"Blocks whose c0 was not valid: {c0['blocks_c0_not_valid']} of {c0['blocks']}.", '',
              '| Task | Mean over all blocks | Mean over blocks with a valid c0 | Blocks with c0 not valid |', '|---|---:|---:|---:|']
    for task, t in result['tasks'].items():
        o = t['c0_one_shot']
        lines.append(f"| {task} | {o['mean']:.4f} | {fmt(o['mean_over_blocks_with_valid_c0'])} | {o['blocks_c0_not_valid']} |")
    lines += ['', '### Timing by arm (section 4.6)', '',
              'Pooled over the decisions of the arm\'s flights. A flight that two arms share counts for both. Lags are in seconds, '
              'call times are the wall time of one sandboxed call.', '']
    for group, title in (('learning_trials', 'Learning trial flights'), ('evaluation_hazard', 'Evaluation flights, hazard'),
                         ('evaluation_retention', 'Evaluation flights, retention')):
        lines += [f'{title}.', '',
                  '| Arm | Flights | Median lag | Largest lag | Share of decisions 0.1 s late | Largest own lag | Observations a step late | '
                  'Missed deadlines | First sight, median m | Procedure call, median and largest | Guard call, median and largest |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|']
        for arm, groups in sec['timing_by_arm'].items():
            g = groups[group]
            def calls(d):
                return 'none' if d is None else f"{d['median']:.4f} and {d['max']:.4f}"
            lines.append(f"| {arm} | {g['flights']} | {fmt(g['median_recorded_lag_s'], 3)} | {fmt(g['max_recorded_lag_s'], 3)} | "
                         f"{fmt(g['share_of_decisions_at_least_0_1s_late'])} | {fmt(g['max_own_lag_s'], 3)} | "
                         f"{g['observations_read_a_step_or_more_late']} | {g['missed_deadlines']} | {fmt(g['first_sight_m']['median'], 2)} | "
                         f"{calls(g['procedure_call_s'])} | {calls(g['guard_call_s'])} |")
        lines.append('')
    lines += ['### Calls flown again and flights kept late in learning', '',
              '| Arm | Calls flown again | Attempts set aside as late | Flights kept late |', '|---|---:|---:|---:|']
    for arm, row in sec['calls_flown_again_by_arm'].items():
        lines.append(f"| {arm} | {row['calls_flown_again']} | {row['attempts_set_aside']} | {row['flights_kept_late']} |")
    r = sec['calls_flown_again_in_the_run']
    lines += ['', f"In the run, each call counted once: {r['calls_flown_again']} calls flown again, {r['attempts_set_aside']} attempts set aside, "
              f"{r['flights_kept_late']} flights kept late. Blocks with no timing.json: {r['blocks_without_timing_rows']}.", '']
    sp = sec['spend']
    aside = sp['learning_blocks_set_aside']
    lines += ['### Spend (list price)', '',
              f"Unique spend of the blocks kept: {sp['unique']['calls']} calls, {usd(sp['unique']['list_cost_usd'])}. "
              f"Blocks set aside: {aside['blocks']}, {aside['usage']['calls']} calls, {usd(aside['usage']['list_cost_usd'])} "
              f"(the provider's charge on {aside['provider_charge']['rows_with_charge']} of {aside['provider_charge']['rows']} rows: "
              f"{usd(aside['provider_charge']['charged_usd_known_subtotal'])}). "
              f"Together, with the list cost of the provider rows that have no spending row: {usd(sp['unique_plus_set_aside_list_cost_usd'])}."
              + (f" Known subtotal {usd(sp['unique_plus_set_aside_known_subtotal_usd'])}; {sp['unique_plus_set_aside_calls_of_unknown_cost']} "
                 f"calls of unknown cost (a call with no price, in a spending row or in a provider row with no spending row) are not in it."
                 if sp['unique_plus_set_aside_calls_of_unknown_cost'] else ''), '']
    m = sec['message_ids_that_appear_more_than_once']
    lines += ['### Message ids', '', f"Message ids that appear for more than one call: {m['count']} (the gate requires 0; it saw {m['message_ids_seen']}).",
              '', f"Copies caught (replies the gateway returned from its store that the provider logged as copied, in learning blocks that were "
              f"set aside and flown again): {m['copies_caught']}. Message ids in the run's file with no provider row (a process killed "
              f"between the claim and the row): {m['message_ids_in_file_with_no_row']}. Provider rows with no spending row (a process killed "
              f"between the provider's row and the ladder's): {m['provider_rows_with_no_spending_row']['count']}, list cost "
              f"{usd(m['provider_rows_with_no_spending_row']['list_cost_usd'])}, charge {usd(m['provider_rows_with_no_spending_row']['charged_usd'])} "
              f"on {m['provider_rows_with_no_spending_row']['rows_with_charge']} rows. "
              + (f"{m['provider_rows_with_no_spending_row']['rows_without_list_cost']} of them have no list cost, so the list cost is a known subtotal. "
                 if m['provider_rows_with_no_spending_row']['rows_without_list_cost'] else '')
              + f"Their list cost is added to the spend of the blocks set aside "
              f"above. Lines of the run's file of message ids cut short by a crash and skipped: {m['message_id_file_fragments']}."
              + (f" Spending rows on the gateway route with no provider row of their own (more spending rows than provider rows for one "
                 f"request id), in blocks set aside: {aside['spending_rows_with_no_provider_row']['count']}; their price is already in the spend above."
                 if aside.get('spending_rows_with_no_provider_row') else ''), '']
    return lines


def descriptive_lines(result):
    """The descriptive counts of ruling 55, point 3, as report.md lines. No interval is printed."""
    d = result['descriptive_counts']
    lines = ['## Descriptive counts (no interval)', '', d['rule'], '',
             'Fields in analysis.json under descriptive_counts.by_task[task][arm]: blocks, successes, flights_possible, adopting_blocks, '
             'adopting_blocks_successes, adopting_blocks_flights_possible, adopting_blocks_mean, mean_by_band, flights_possible_by_band.', '',
             '| Task | Arm | Successes of flights possible | Adopting blocks | Successes in adopting blocks, of flights possible | '
             'Mean in adopting blocks | Mean close | Mean middle | Mean wide |', '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for task, arms in d['by_task'].items():
        for arm, r in arms.items():
            band = lambda name: fmt(r['mean_by_band'].get(name), 4) if name in r['mean_by_band'] else 'none'
            lines.append(f"| {task} | {arm} | {r['successes']} of {r['flights_possible']} | {r['adopting_blocks']} of {r['blocks']} | "
                         f"{r['adopting_blocks_successes']} of {r['adopting_blocks_flights_possible']} | {fmt(r['adopting_blocks_mean'])} | "
                         f"{band('close')} | {band('middle')} | {band('wide')} |")
    lines.append('')
    return lines


def report_lines(result):
    """report.md, as lines. Plain words first; the keys of analysis.json are in the last column."""
    lines = ['# Protocol 3 analysis', '', result['status'], '',
             '## Primary intervals (the three pooled steps)', '',
             '| Primary contrast | Estimate | 95% interval | Result | Key in analysis.json |', '|---|---:|---|---|---|']
    for key, row in result['primary'].items():
        lines.append(table_row(key, row, key.startswith('pooled:')))
    lines += ['', '## Secondary intervals: D - A for each task, close and distant (RQ4\'s answer, ruling 88)', '',
              'The six per-task D - A intervals are secondary. They are computed from the same draws as before and reported in '
              'full. The protocol said before the run that most were expected to be unresolved; an unresolved interval is not '
              'evidence of no difference.', '',
              '| Secondary contrast | Estimate | 95% interval | Result | Key in analysis.json |', '|---|---:|---|---|---|']
    for key, row in result['secondary_intervals'].items():
        lines.append(table_row(key, row, False))
    lines += ['', 'Intervals are pointwise. Direction and equivalence are distinct; see analysis.json.',
              'When the two arms of a contrast are equal cell for cell, or both 0 in every cell, or both 1 in every cell, the '
              'bootstrap has nothing to resample. The result is then named for that and not by section 6.4. '
              'For a pooled step the cells of the three tasks are taken together and N counts the blocks of all three.']
    lines += ['', '## RQ1: the answer for each pooled step', '',
              'Each answer comes from the pooled result and the signs of the three per-task point estimates '
              '(ruling 38, point 3). A task whose estimate is exactly 0 has no sign and differs from neither.', '']
    for key, row in result['pooled_ladder_steps'].items():
        a = row['answer']
        signs = ', '.join(f'{t} {s}' for t, s in a['signs'].items())
        lines += [f'### {key}', '', f"Pooled result: {result_name(row, True)}. Per-task signs: {signs}"
                  f"{' (they differ)' if a['signs_differ'] else ' (they do not differ)'}.", '',
                  (f"Answer: {a['text']}" if a['status'] == 'answered' else f"Answer ({a['status'].replace('_', ' ')}): {a['text']}"), '',
                  '| Task | Estimate | 95% interval | Result |', '|---|---:|---|---|']
        for t in a['per_task']:
            lines.append(f"| {t['task']} | {t['estimate']:+.4f} | {t['ci95'][0]:+.4f}, {t['ci95'][1]:+.4f} | {result_name(row['per_task'][t['task']])} |")
        lines.append('')
    lines += ['## RQ4: D - A on close targets minus D - A on distant targets (descriptive, no section 6.4 name)', '',
              'For each task, from one set of resamples shared by the close and distant parts. These resamples are not the ones '
              'that made the primary intervals. The sample-size work did not plan this difference\'s resolution.', '',
              '| Task | Close D - A | Distant D - A | Close minus distant | 95% interval |', '|---|---:|---:|---:|---|']
    for task, row in result['rq4_close_minus_distant'].items():
        lo, hi = row['ci95']
        note = f" ({row['nothing_to_compare']['name']}: D and A have nothing to compare)" if 'nothing_to_compare' in row else ''
        lines.append(f"| {task} | {row['d_minus_a_close']['estimate']:+.4f} | {row['d_minus_a_distant']['estimate']:+.4f} | "
                     f"{row['estimate']:+.4f} | {lo:+.4f}, {hi:+.4f}{note} |")
    lines += [''] + kept_late_lines(result)
    lines += [''] + stops_and_faults_lines(result)
    lines += [''] + secondary_lines(result)
    lines += [''] + descriptive_lines(result)
    lines += ['No scored conclusion may be drawn from a development/pilot analysis.']
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='+', help='one run root, or the three roots of a split run (one task each)')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Use a new analysis directory; previous records are preserved')
    result = analyse(args.root if len(args.root) > 1 else args.root[0], pilot=args.pilot, out=args.out)
    args.out.mkdir(parents=True)
    (args.out / 'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    lines = report_lines(result)
    (args.out / 'report.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'ok': True, 'status': result['status'], 'primary_intervals': len(result['primary']), 'secondary_intervals': len(result['secondary_intervals'])}))


if __name__ == '__main__':
    main()

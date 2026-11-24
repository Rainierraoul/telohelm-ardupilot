"""Protocol 3 timing counts and sensitivity analyses for late and re-flown learning, from one validated snapshot.

This script is outside the source fingerprint. It is written to rulings 78, 80 and 81 and to protocol draft 3 (sections 4.9
and 6.2), before any scored outcome exists, and Codex reproduces it before the paper states what it computes. It calls no
simulator and no model, writes only its own two files into a new folder, and changes no record.

It computes four things:

1. Off-stamp commands by arm (ruling 80, point 3): the sum of off_deadline_commands over the flights kept late, for learning
   trials, zone evaluation and retention, grouped by arm as the analysis groups flights. Every other flight has zero by
   construction (ardupilot/ladder.py, timing()); the script checks every flight it can see and lists any breach.
2. The kept-late learning list (ruling 78, point 2; ruling 80, point 4): every arm-block touched by a learning call that was
   kept late on its third attempt.
3. The re-flown block list (ruling 81, point 3; ruling 87): every learning block set aside for a fault or lost with a dead job
   whose set-aside attempt had sent a request for a fresh candidate or a repair. This is read from the usage rows the gate
   hands over for that attempt (usage.jsonl and claude-usage.jsonl), and from which candidate slot folders hold a
   request.json (folder and file names only). A request file with no row counts as sent ("sending not established"), and an
   attempt whose candidate folders are not kept is listed for all four arms ("not determinable"). No file's contents, and no
   outcome, flight record, arms.json or trial result of a set-aside attempt, is read. An attempt that cannot be placed in a
   block, or a kept-late call that cannot be tied to its arms, makes its list incomplete, and an incomplete list is never
   reported as empty.
4. When list 2 or list 3 is not empty, each list's two fills of every one of the nine intervals (the three primary and the six secondary D - A), by analysis3.filled, with each listed
   arm-block filled on its own and none cancelled against another arm (see `fills`), and analysis3.primary_pass, with the analysis's seed and draws. The two lists' analyses are separate and never combined.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ardupilot import ladder as L
from protocol import analysis3 as A
from protocol import contract3 as C

GROUPS = ('learning_trials', 'evaluation_hazard', 'evaluation_retention')
GROUP_WORDS = {'learning_trials': 'learning trials', 'evaluation_hazard': 'zone evaluation',
               'evaluation_retention': 'retention'}
EVALUATION_PHASES = {'evaluation_hazard': 'threat3', 'evaluation_retention': 'retain3'}
BLOCK_NAME = re.compile(r'learn3-([a-z0-9]+)-b(\d+)')
CAUSES = {'failed_exit': 'fault', 'no_scheduler_no_end': 'dead job'}


INCOMPLETE_WORDS = {'kept_late_learning': 'a call kept late could not be tied to its arms (ruling 87, point 4).',
                    'reflown_learning_blocks': 'a set-aside attempt could not be placed in a block (ruling 87, point 4).'}


def off_stamp(outcome):
    """off_deadline_commands of one flight, as ardupilot.ladder.timing reads it (None where the flight has no steps)."""
    return L.timing(outcome)['off_deadline_commands']


def kept_late_trial_paths(learn):
    """The flights of a learning block marked kept_late in its timing rows, as paths inside the block."""
    return {r['flight'] for r in learn.get('timing') or [] if r.get('kept_late')}


def tally():
    return {'flights': 0, 'flights_kept_late': 0, 'off_deadline_commands': 0, 'kept_late_flights_without_timing_figures': 0}


def add_flight(cell, outcome, kept):
    cell['flights'] += 1
    if kept:
        cell['flights_kept_late'] += 1
        off = off_stamp(outcome)
        if off is None:
            cell['kept_late_flights_without_timing_figures'] += 1
        else:
            cell['off_deadline_commands'] += off


def off_stamp_report(snapshot):
    """Ruling 80, point 3. Per arm and group, the kept-late flights and their off-stamp commands, counted as the analysis
    groups flights (a source two arms adopted counts for each; learning trials are the arm's own trial flights). Then a
    sweep of every flight in the snapshot, the first-round lists and sources no arm adopted included: a flight that is not
    kept late must have no off-stamp command, and one that has is a breach."""
    by_arm = {a: {g: tally() for g in GROUPS} for a in C.ARMS}
    for task, blocks in snapshot['learning'].items():
        for block, learn in blocks.items():
            late_paths = kept_late_trial_paths(learn)
            for arm in C.ARMS:
                row = learn['arms_record']['arms'][arm]
                for t in row['trials']:
                    d = t.get('flight_dir')
                    if d:
                        for episode, o in learn['flights'][d].items():
                            add_flight(by_arm[arm]['learning_trials'], o, f'{d}/{episode}' in late_paths)
                if not row['adopted']:
                    continue
                for group, phase in EVALUATION_PHASES.items():
                    flights = snapshot['hazard' if phase == 'threat3' else 'retention'][(task, block, row['source_sha256'])]
                    marked = set(snapshot['kept_late_eval'].get((phase, task, block, row['source_sha256']), ()))
                    for episode, o in flights.items():
                        add_flight(by_arm[arm][group], o, episode in marked)
    breaches, swept, first_round = [], 0, tally()
    for task, blocks in snapshot['learning'].items():
        for block, learn in blocks.items():
            late_paths = kept_late_trial_paths(learn)
            for d, flights in learn['flights'].items():
                for episode, o in flights.items():
                    swept += 1
                    kept = f'{d}/{episode}' in late_paths
                    if d.startswith('flights/first/'):
                        add_flight(first_round, o, kept)
                    check_flight(breaches, kept, o, {'group': 'learning', 'task': task, 'block': block, 'flight': f'{d}/{episode}'})
    for group, phase in EVALUATION_PHASES.items():
        for (task, block, source), flights in snapshot['hazard' if phase == 'threat3' else 'retention'].items():
            marked = set(snapshot['kept_late_eval'].get((phase, task, block, source), ()))
            for episode, o in flights.items():
                swept += 1
                check_flight(breaches, episode in marked, o,
                             {'group': group, 'task': task, 'block': block, 'source_sha256': source, 'flight': episode})
    totals = {g: {k: sum(by_arm[a][g][k] for a in C.ARMS) for k in tally()} for g in GROUPS}
    return {'by_arm': by_arm, 'totals_by_group': totals,
            'first_round_flights_outside_the_arm_groups': first_round,
            'flights_checked_for_zero_off_stamp_commands': swept,
            'flights_kept_late_in_the_arm_groups': sum(by_arm[a][g]['flights_kept_late'] for a in C.ARMS for g in GROUPS),
            'breaches': breaches, 'breach_count': len(breaches),
            'rule': 'a flight that is not kept late has no command off the third telemetry stamp (ardupilot/ladder.py, timing())'}


def check_flight(breaches, kept, outcome, where):
    if kept:
        return
    off = off_stamp(outcome)
    if off is None or off > 0:
        breaches.append({**where, 'off_deadline_commands': off})


def learning_list(snapshot):
    """Ruling 78, point 2 and ruling 80, point 4. Every learning call kept late on its third attempt, with the arms it
    touches as analysis3.arms_of_call gives them (a first-round call: A, B and C for P0, D for P1; a trial: the arms whose
    trial it was, so B and C for the c0 trial they share). Each such call is listed. A trial's result always decides whether
    its candidate is adopted, and a first-round call's flights are shown to the model when it writes the candidates, so every
    kept-late call meets the rule's condition; `role` says which part of it applies. Returns the entries and the arm-blocks."""
    entries, unattributed = [], []
    for task, blocks in sorted(snapshot['learning'].items()):
        for block, learn in sorted(blocks.items()):
            rows = learn['arms_record']['arms']
            for call, n in sorted(A.calls_flown_again(learn)[1].items()):
                arms = A.arms_of_call(call, rows)
                if not arms:
                    unattributed.append({'task': task, 'block': block, 'call': call, 'flights_kept_late': n})
                for arm in arms:
                    entry = {'task': task, 'block': block, 'arm': arm, 'call': call, 'flights_kept_late': n}
                    if call.startswith('flights/first/'):
                        entry.update(role='first-round flights, shown to the model when it wrote the candidates', candidate_id=None)
                    else:
                        trials = rows[arm]['trials']
                        k = next(i for i, t in enumerate(trials) if t.get('flight_dir') == call)
                        t = trials[k]
                        role = ('result decided the adoption of the candidate' if t['passed'] else
                                'result decided against the candidate, and the arm went on to a later candidate' if k < len(trials) - 1 else
                                'result decided against the last candidate, and the arm adopted nothing')
                        entry.update(role=role, candidate_id=t['candidate_id'])
                    entries.append(entry)
    arm_blocks = sorted({(e['task'], e['block'], e['arm']) for e in entries})
    return {'calls_kept_late': entries, 'arm_blocks': [{'task': t, 'block': b, 'arm': a} for t, b, a in arm_blocks],
            'unattributed_calls': unattributed, 'complete': not unattributed, 'empty': not entries and not unattributed}


def candidate_of_request_id(request_id):
    """The candidate id a provider row's request id names: the second element of its JSON list, after the block's name
    ('land-b0-f1' gives 'f1'). None for an id that is not in that form."""
    try:
        parts = json.loads(request_id)
        return parts[1].rsplit('-', 1)[1]
    except (TypeError, ValueError, IndexError, AttributeError):
        return None


def requests_sent(item):
    """The candidates a set-aside attempt sent a request for, from its usage rows and its provider rows, and nothing else."""
    found = {r.get('candidate_id') for r in item['usage']} | {candidate_of_request_id(r.get('request_id')) for r in item['provider']}
    return sorted(c for c in found if isinstance(c, str) and c)


STATUS_SENT = 'sent'
STATUS_NOT_ESTABLISHED = 'sending not established'
STATUS_NOT_DETERMINABLE = 'not determinable'


def attempt_root(snapshot, task):
    """The run root a task's set-aside attempts sit beside: the root of the split-run part that flew the task, or the one
    root of an ordinary run. None where the snapshot does not say."""
    for part in snapshot.get('roots') or []:
        if part.get('task') == task:
            return part.get('root')
    return snapshot.get('root')


def request_folders(snapshot, task, phase, attempt):
    """Which candidate slot folders of a set-aside attempt hold a request.json. A phase set aside is moved whole to
    ROOT.set-aside/PHASE-attemptN (protocol/set_aside3.py), so its candidates/ folder goes with it. Only folder names and
    whether request.json exists are read; no file is opened, because a request shows earlier flights (ruling 81).
    Returns the sorted slot names, or None when candidates/ cannot be found, so that what was due next cannot be read."""
    from protocol.set_aside3 import set_aside_dir
    root = attempt_root(snapshot, task)
    if not root:
        return None
    folder = set_aside_dir(Path(root)) / f'{phase}-attempt{attempt}' / 'candidates'
    try:
        return sorted(e.name for e in folder.iterdir() if e.is_dir() and (e / 'request.json').exists())
    except OSError:
        return None


def reflown_list(snapshot):
    """Ruling 81, points 3 and 4, and ruling 87, points 2 to 4. For every set-aside learning attempt that is not 'late' (a
    learning block is never set aside for lateness, protocol section 7.3, so any other reason counts, and an unreadable
    receipt is counted under its own heading), whether it had sent a request for a fresh candidate or a repair:
      sent                     a usage or provider row names such a request;
      sending not established  a slot folder of the attempt holds a request.json for one, and no row names it (the driver
                               writes the request file before it calls the model and the rows after, so a job killed during
                               the call leaves a request with no row); it counts as sent, because a wrong 'sent' can only
                               widen the sensitivity range;
      not determinable         the attempt's candidate folders are not kept, so what was due next cannot be read, and no row
                               shows such a request; the attempt is listed for all four arms of its block.
    Every listed block is filled for all four arms. An attempt that cannot be placed in a block makes the list incomplete,
    and an incomplete list is never reported as empty. The cause is read from the receipt's crash evidence: a failed exit
    recorded by the scheduler is a fault, a scheduler gone with no end to the phase is a dead job."""
    by_reason, by_cause, by_status = Counter(), Counter(), Counter()
    listed, unplaced, with_any = {}, [], set()
    without_records = 0
    for item in snapshot['set_aside_learning']:
        reason = item['reason'] or 'unreadable receipt'
        cause = CAUSES.get(item['crash_evidence_kind'], 'no crash evidence on the receipt')
        by_reason[reason] += 1
        by_cause[cause] += 1
        m = BLOCK_NAME.fullmatch(item['phase'])
        if not m or m.group(1) not in snapshot['learning'] or int(m.group(2)) not in snapshot['learning'][m.group(1)]:
            unplaced.append({'phase': item['phase'], 'attempt': item['attempt'], 'reason': reason})
            continue
        key = (m.group(1), int(m.group(2)))
        with_any.add(key)
        if reason == 'late':
            continue
        sent = requests_sent(item)
        if not (item['usage'] or item['provider']):
            without_records += 1
        wanted = [c for c in sent if A.candidate_kind(c) in ('fresh', 'repair')]
        folders = request_folders(snapshot, key[0], item['phase'], item['attempt'])
        due = [c for c in (folders or []) if c not in ('c0', 'c1') and c not in sent]
        if wanted:
            status = STATUS_SENT
        elif due:
            status = STATUS_NOT_ESTABLISHED
        elif folders is None:
            status = STATUS_NOT_DETERMINABLE
        else:
            continue
        by_status[status] += 1
        block = listed.setdefault(key, {'task': key[0], 'block': key[1], 'arms': list(C.ARMS), 'attempts': []})
        block['attempts'].append({'attempt': item['attempt'], 'reason': reason, 'cause': cause, 'status': status,
                                  'fresh_or_repair_requests': wanted, 'requests_of_all_kinds': sent,
                                  'request_files_with_no_row': due, 'candidate_folders_kept': folders is not None})
    return {'set_aside_attempts': sum(by_reason.values()), 'set_aside_attempts_by_reason': dict(by_reason),
            'set_aside_attempts_by_cause': dict(by_cause),
            'distinct_blocks_with_any_set_aside_attempt': len(with_any),
            'distinct_listed_blocks': len(listed),
            'listed_attempts_by_status': {k: by_status.get(k, 0) for k in (STATUS_SENT, STATUS_NOT_ESTABLISHED, STATUS_NOT_DETERMINABLE)},
            'attempts_with_no_call_records': without_records,
            'affected_blocks': [listed[k] for k in sorted(listed)], 'unplaced_attempts': unplaced,
            'complete': not unplaced, 'empty': not listed and not unplaced,
            'rule': 'a set-aside attempt (any reason but late) with a recorded fresh or repair request, whatever came back, or '
                    'with a request file for one and no row (sending not established), or whose candidate folders are not kept '
                    '(not determinable); read from call records and folder names only'}


def cell_data(snapshot):
    """The arms-by-blocks-by-scenarios cells of each task and the source each arm adopted, built as analysis3.analyse_snapshot
    builds the primary cells. (The analysis does not hand them out, so they are rebuilt here; the tests check them against it.)"""
    seeds, pilot = snapshot['seeds'], snapshot['pilot']
    task_data, source, order = {}, {}, {}
    for task, blocks in snapshot['learning'].items():
        ids = sorted(blocks)
        cases = C.evaluation_cases(seeds, task, pilot)
        sizes = [len(C.book(seeds, pilot)['threat_evaluation'][task][b]) for b in C.BANDS]
        bands = [b for b, n in zip(C.BANDS, sizes) for _ in range(n)]
        y = np.zeros((4, len(ids), len(cases)))
        source[task] = [[None] * len(ids) for _ in C.ARMS]
        for j, block in enumerate(ids):
            for i, arm in enumerate(C.ARMS):
                row = blocks[block]['arms_record']['arms'][arm]
                if row['adopted']:
                    source[task][i][j] = row['source_sha256']
                    flights = snapshot['hazard'][(task, block, row['source_sha256'])]
                    y[i, j] = [flights[c.episode_id]['goal_met'] for c in cases]
        task_data[task] = {'y': y, 'bands': bands, 'unqualified': []}
        order[task] = ids
    return task_data, source, order


def masks(task_data, order, cells):
    """cells is a list of (task, block, arm index or None for all four arms). Returns the mask `filled` takes."""
    mask = {t: np.zeros(d['y'].shape, dtype=bool) for t, d in task_data.items()}
    for task, block, arm in cells:
        j = order[task].index(block)
        if arm is None:
            mask[task][:, j, :] = True
        else:
            mask[task][arm, j, :] = True
    return mask


def fills(task_data, mask, source, primary, boot_seed, n_boot):
    """Both fills of every one of the nine intervals, as analysis3.kept_late_report makes them (`primary` is the dict of all
    nine; ruling 78 fills every contrast, and ruling 88 made the six D - A intervals secondary without changing this): for
    each group of contrasts, a replay of the whole draw sequence on the group's filled cells. The six D - A intervals share
    one pair of fills and each pooled step has its own.

    Each listed arm-block is filled on its own. analysis3.filled cancels two arms that flew the same source in a block, which
    is right for a kept-late evaluation flight, because that is one flight. Here it is not: a listed block is one whose
    learning might have gone otherwise, and had it, arms that adopted the same source might have adopted different ones.
    A re-flown block whose c0 passed, where A, B and C all adopted c0, is the case the reflown list exists to bound
    (protocol section 6.2), so no arm-block is cancelled against another: every source is passed to `filled` as unknown."""
    independent = {t: [[None] * len(row) for row in rows] for t, rows in source.items()}
    out = {'lower': {}, 'upper': {}}
    for group in C.STEPS:
        keys = [k for k in primary if A.contrast_group(k) == group]
        for bound in out:
            done = A.primary_pass(A.filled(task_data, mask, independent, group, bound), boot_seed, n_boot)['intervals']
            out[bound].update({k: done[k] for k in keys})
    low, high = ({k: out[b][k] for k in primary} for b in ('lower', 'upper'))
    classes = {k: [primary[k]['classification']['class'], low[k]['classification']['class'], high[k]['classification']['class']]
               for k in primary}
    return {'cells_set': int(sum(m.sum() for m in mask.values())),
            'primary_under_lower_fill': low, 'primary_under_upper_fill': high,
            'names_change': {k: v for k, v in classes.items() if len(set(v)) > 1}}


def sensitivity(snapshot, *, n_boot=C.BOOT_N, boot_seed=C.BOOT_SEED):
    """The whole result from a snapshot the gate has passed."""
    off = off_stamp_report(snapshot)
    learning, reflown = learning_list(snapshot), reflown_list(snapshot)
    result = {'status': 'development only; not scored evidence' if snapshot['pilot'] else 'protocol3 scored sensitivity analyses',
              'off_stamp_commands': off, 'kept_late_learning': {'list': learning}, 'reflown_learning_blocks': {'list': reflown},
              'bootstrap': {'seed': boot_seed, 'replicates': n_boot}}
    task_data = source = order = primary = None
    for label, listing, cells in (
            ('kept_late_learning', learning, [(e['task'], e['block'], C.ARMS.index(e['arm'])) for e in learning['calls_kept_late']]),
            ('reflown_learning_blocks', reflown, [(b['task'], b['block'], None) for b in reflown['affected_blocks']])):
        result[label]['complete'] = listing['complete']
        if not cells:
            result[label]['fills'] = None
            result[label]['statement'] = ('The list is empty, so nothing is computed for it.' if listing['empty'] else
                                          'The list is INCOMPLETE and has nothing placed to fill: ' + INCOMPLETE_WORDS[label])
            continue
        if task_data is None:
            task_data, source, order = cell_data(snapshot)
            primary = A.primary_pass(task_data, boot_seed, n_boot)['intervals']
            result['primary_as_recorded'] = primary      # all nine, in the order they were always made
            result['designation'] = {k: A.designation(k) for k in primary}
        done = fills(task_data, masks(task_data, order, cells), source, primary, boot_seed, n_boot)
        result[label]['fills'] = done
        result[label]['statement'] = ('Each contrast (the three primary and the six secondary D - A intervals) is shown with the listed arm-blocks\' evaluation cells set to the values that '
                                      'raise it most (upper) and lower it most (lower). Denominators stay as they are.'
                                      + ('' if listing['complete'] else ' The list is INCOMPLETE, so the fills cover only what was placed: '
                                         + INCOMPLETE_WORDS[label]))
    return result


def run(root, *, pilot=False, seed_path=C.SEED_PATH, n_boot=C.BOOT_N, boot_seed=C.BOOT_SEED, protocol_path=None):
    """The gate on the run root (or the three roots of a split run), then the sensitivity analyses of its snapshot. It writes
    no run record: the analysis's own record is made by analysis3.py. A scored call uses the protocol's count and seed."""
    from protocol.validate3 import load_runs
    roots = [Path(r) for r in (root if isinstance(root, (list, tuple)) else [root])]
    if not pilot:
        A.check_protocol_settings(n_boot, boot_seed)
    gate, snapshot = load_runs(roots if len(roots) > 1 else roots[0], pilot=pilot, seed_path=Path(seed_path), protocol_path=protocol_path)
    if not gate['ok']:
        raise ValueError('Protocol3 evidence gate failed: ' + '; '.join(gate['errors'][:10]))
    result = sensitivity(snapshot, n_boot=n_boot, boot_seed=boot_seed)
    result['input_sha256'] = snapshot['input_sha256']
    result['inputs_aggregate_sha256'] = hashlib.sha256(C.canonical(snapshot['input_sha256'])).hexdigest()
    result['script_sha256'] = C.sha(Path(__file__))
    if len(roots) > 1:
        result['roots'] = snapshot['roots']
    return result


def fmt_interval(row):
    lo, hi = row['ci95']
    return f"{row['estimate']:+.4f} ({lo:+.4f}, {hi:+.4f})"


def fill_table(primary, done):
    lines = []
    for label, which in (('Primary contrast', 'primary'), ('Secondary contrast', 'secondary')):
        lines += [f'| {label} | As recorded | Lower fill | Upper fill | Result as recorded, lower, upper |', '|---|---:|---:|---:|---|']
        for key, row in primary.items():
            if A.designation(key) != which:
                continue
            low, high = done['primary_under_lower_fill'][key], done['primary_under_upper_fill'][key]
            pooled = key.startswith('pooled:')
            names = ' / '.join(A.result_name(r, pooled) for r in (row, low, high))
            lines.append(f"| {key} | {fmt_interval(row)} | {fmt_interval(low)} | {fmt_interval(high)} | {names} |")
        lines.append('')
    changed = done['names_change']
    lines.append('Contrasts whose name changes under either fill: ' + (', '.join(sorted(changed)) if changed else 'none') + '.')
    return lines


def report_lines(result):
    off = result['off_stamp_commands']
    lines = ['# Protocol 3 timing counts and sensitivity analyses', '', result['status'], '',
             '## Off-stamp commands in flights kept late', '',
             'Commands sent at other than the third telemetry stamp, summed over the flights kept late, by arm. A flight that is '
             'not kept late has none by construction (ardupilot/ladder.py, timing()).', '',
             '| Arm | ' + ' | '.join(f'{GROUP_WORDS[g]}: flights kept late, commands' for g in GROUPS) + ' |', '|---|---:|---:|---:|']
    for arm, groups in off['by_arm'].items():
        lines.append(f'| {arm} | ' + ' | '.join(f"{groups[g]['flights_kept_late']}, {groups[g]['off_deadline_commands']}" for g in GROUPS) + ' |')
    if not off['flights_kept_late_in_the_arm_groups']:
        lines += ['', 'No flight was kept late, so every count is zero and nothing more is computed.']
    first = off['first_round_flights_outside_the_arm_groups']
    lines += ['', f"First-round flights, which the analysis does not group by arm: {first['flights_kept_late']} kept late, "
                  f"{first['off_deadline_commands']} off-stamp commands.",
              f"Flights checked for the zero-by-construction rule: {off['flights_checked_for_zero_off_stamp_commands']}. "
              + ('The rule held in all of them.' if not off['breach_count'] else
                 f"The rule was BROKEN in {off['breach_count']} flights not kept late; they are listed in the JSON file and the paper must say so."),
              '']
    k = result['kept_late_learning']
    lines += ['## Learning calls kept late (ruling 78)', '']
    if k['list']['empty']:
        lines += ['No learning call was kept late on its third attempt. The list is empty and nothing is computed.']
    elif not k['list']['calls_kept_late']:
        lines += ['No learning call was placed in the list.']
    else:
        lines += ['| Task | Block | Arm | Call | Flights kept late | Role |', '|---|---:|---|---|---:|---|']
        lines += [f"| {e['task']} | {e['block']} | {e['arm']} | {e['call']} | {e['flights_kept_late']} | {e['role']} |"
                  for e in k['list']['calls_kept_late']]
        lines += ['', f"Arm-blocks touched: {len(k['list']['arm_blocks'])}.", ''] + fill_table(result['primary_as_recorded'], k['fills'])
    if k['list']['unattributed_calls']:
        lines += ['', 'THE LIST IS INCOMPLETE. Calls kept late that no arm\'s record names, so their arms cannot be listed: '
                  + '; '.join(f"{u['task']} block {u['block']} {u['call']} ({u['flights_kept_late']} flights)" for u in k['list']['unattributed_calls'])
                  + '. No statement is made that the list is empty.']
    r = result['reflown_learning_blocks']
    rl = r['list']
    lines += ['', '## Learning blocks set aside and flown again (ruling 81, ruling 87)', '',
              f"Set-aside learning attempts (each counts one attempt): {rl['set_aside_attempts']}. By reason on the receipt: "
              + (', '.join(f'{n} {k_}' for k_, n in sorted(rl['set_aside_attempts_by_reason'].items())) or 'none')
              + '. By cause: ' + (', '.join(f'{n} {k_}' for k_, n in sorted(rl['set_aside_attempts_by_cause'].items())) or 'none') + '.',
              f"Distinct blocks with any set-aside attempt (each block once, whatever the reason): {rl['distinct_blocks_with_any_set_aside_attempt']}.",
              f"Distinct listed blocks (each block once, all four arms filled): {rl['distinct_listed_blocks']}. Listed attempts by status: "
              + ', '.join(f'{n} {k_}' for k_, n in rl['listed_attempts_by_status'].items()) + '.', '']
    if rl['unplaced_attempts']:
        lines += ['THE LIST IS INCOMPLETE. Set-aside attempts that could not be placed in a block: '
                  + '; '.join(f"{u['phase']} attempt {u['attempt']} ({u['reason']})" for u in rl['unplaced_attempts'])
                  + '. No statement is made that the list is empty.', '']
    if rl['empty']:
        lines += ['No set-aside attempt has a recorded fresh or repair request, a request file with no row, or missing candidate folders. '
                  'The list is empty and nothing is computed.']
    elif rl['affected_blocks']:
        lines += ['| Task | Block | Attempt | Cause | Status | Fresh or repair requests |', '|---|---:|---:|---|---|---|']
        lines += [f"| {b['task']} | {b['block']} | {a['attempt']} | {a['cause']} | {a['status']} | "
                  f"{', '.join(a['fresh_or_repair_requests'] + a['request_files_with_no_row']) or 'none readable'} |"
                  for b in rl['affected_blocks'] for a in b['attempts']]
        lines += ['', f"Listed blocks: {rl['distinct_listed_blocks']}. All four arms of each are filled.", '']
        lines += fill_table(result['primary_as_recorded'], r['fills'])
    lines += ['', 'The two analyses are separate and are never combined. Neither changes the primary estimate.']
    if result['status'].startswith('development'):
        lines += ['No scored conclusion may be drawn from a development/pilot run.']
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('root', type=Path, nargs='+', help='one run root, or the three roots of a split run (one task each)')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--n-boot', type=int, default=C.BOOT_N)
    parser.add_argument('--boot-seed', type=int, default=C.BOOT_SEED)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Use a new output directory; previous records are preserved')
    result = run(args.root if len(args.root) > 1 else args.root[0], pilot=args.pilot, n_boot=args.n_boot, boot_seed=args.boot_seed)
    args.out.mkdir(parents=True)
    (args.out / 'sensitivity.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    (args.out / 'sensitivity.md').write_text('\n'.join(report_lines(result)) + '\n')
    print('\n'.join(report_lines(result)))


if __name__ == '__main__':
    main()

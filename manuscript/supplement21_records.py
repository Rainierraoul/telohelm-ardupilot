"""Reads the small record files of Study 2's main experiment and prints the facts that draft 21 of the supplement states
from them. It reads only, computes no interval and changes nothing.

Run it with the two folders as arguments (the defaults are the paths on the author's computer):

    python3 -I supplement21_records.py [EXTRACT_RUNS_FOLDER] [RESULTS_FOLDER] [STUDY1_ANALYSIS_JSON] [PLANNER_CHECK_FOLDER]

EXTRACT_RUNS_FOLDER holds the six run roots (scored-20261120-S-<task> and scored-20261120-S-<task>.set-aside).
RESULTS_FOLDER holds scored-20261120-S-gate.json, the validation check's report.

What it prints, by section:
  1  platform: for every phase manifest, the node, kernel, batch job, sandbox route, Python and processor, by run root
  2  sessions: each start and restart of a task's scheduler, and which phases started after each restart
  3  timing: flights of record, missed deadlines with each flight counted once, and the attempts set aside as late
  4  late flights: when each late decision fell, to see whether flights in the air together were late together
  5  the adoption test: flights that met the goal while failing the pass rule
  6  the kept-late flights, by task, block and band
  7  Study 1: the per-run counts, the Split-S times and Table S14d (draft 25 labels), copied from Study 1's analysis record (the third argument)
  8  the planner check: zone entries by direction of approach, for Dijkstra's planner (the fourth argument)
"""
import collections
import datetime
import json
import os
import sys

RUNS = sys.argv[1] if len(sys.argv) > 1 else \
    '/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-20261120-S-extract/data/runs'
RESULTS = sys.argv[2] if len(sys.argv) > 2 else \
    '/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-20261120-S-results'
TASKS = ('reach', 'reach3d', 'land')
TAG = 'scored-20261120-S-'
DEADLINE_PERIODS = 3          # a decision whose own lag is three telemetry periods or more missed its deadline
PERIOD_MS = 100


def load(path):
    with open(path) as f:
        return json.load(f)


def periods(lag_s):
    """A lag in whole telemetry periods, read 0.005 s early, as ardupilot/ladder.py reads it (telemetry_steps)."""
    return (round(lag_s * 1000) + 5) // PERIOD_MS


def when(text):
    return datetime.datetime.fromisoformat(text.replace(' ', 'T')[:19])


def phases(root):
    """Every folder under a run root that holds a manifest.json, with the manifest."""
    found = []
    for folder, _, files in os.walk(root):
        if 'manifest.json' in files:
            found.append((folder, load(os.path.join(folder, 'manifest.json'))))
    return sorted(found)


def head(title):
    print()
    print('=' * 100)
    print(title)
    print('=' * 100)


# ---------------------------------------------------------------------------------------------------------------------
head('1  Platform, from every manifest')
all_kernels = collections.Counter()
for task in TASKS:
    for suffix in ('', '.set-aside'):
        root = os.path.join(RUNS, TAG + task + suffix)
        tally = collections.Counter()
        for folder, m in phases(root):
            p, s, c, g = m.get('platform', {}), m.get('sandbox', {}), m.get('core', {}), m.get('git', {})
            tally[(m.get('phase'), p.get('node'), s.get('kernel'), p.get('slurm_job_id'), s.get('route'),
                   p.get('python_version'), p.get('cpu_model'), p.get('cores_allowed'), m.get('at_once'),
                   (m.get('args') or {}).get('speedup'))] += 1
            all_kernels[(task, p.get('node'), s.get('kernel'))] += 1
            assert p.get('arducopter_sha256', '').startswith('adad8e23'), folder
            assert p.get('ardupilot_commit', '').startswith('fb773567'), folder
            assert c.get('wheel_sha256', '').startswith('36d36b86'), folder
            assert m.get('protocol_sha256', '').startswith('06fbf29d'), folder
            assert (g.get('source') or {}).get('sha256', '').startswith('8700e012'), folder
        print(f'{TAG}{task}{suffix}')
        for key, n in sorted(tally.items(), key=str):
            print(f'   {n:4d} manifests: phase {key[0]}, node {key[1]}, kernel {key[2]}, job {key[3]}, route {key[4]}, '
                  f'Python {key[5]}, {key[6]}, cores {key[7]}, at once {key[8]}, speed-up {key[9]}')
print()
print('Task, node and kernel over all manifests, kept and set aside:')
for key, n in sorted(all_kernels.items()):
    print(f'   {key[0]:8s} {key[1]}  {key[2]}  {n} manifests')
print('Every manifest names the same ArduPilot binary (adad8e23...), ArduPilot commit (fb773567...), wheel (36d36b86...), '
      'protocol (06fbf29d...) and code fingerprint (8700e012...): asserted above.')

# ---------------------------------------------------------------------------------------------------------------------
head('2  Sessions: starts and restarts of each task\'s scheduler, and what started after each restart')
gate = load(os.path.join(RESULTS, 'scored-20261120-S-gate.json'))
sessions = collections.defaultdict(list)
for e in gate['session_spend_stops']:
    sessions[e['task']].append((e['event'], when(e['time'])))
restarts_total = 0
for task in TASKS:
    events = sessions[task]
    restarts = [t for e, t in events if e == 'resume']
    restarts_total += len(restarts)
    kept = phases(os.path.join(RUNS, TAG + task))
    aside = phases(os.path.join(RUNS, TAG + task + '.set-aside'))
    aside_names = collections.Counter(os.path.basename(f) for f, _ in aside)
    print(f'{task}: events {[e for e, _ in events]}; {len(kept)} phases kept, {len(aside)} attempts set aside '
          f'in {len(aside_names)} evaluation sets')
    bounds = restarts + [datetime.datetime.max]
    before = [f for f, m in kept if when(m['started']) < restarts[0]] if restarts else [f for f, _ in kept]
    print(f'   phases started before the first restart: {len(before)}')
    for i, start in enumerate(restarts):
        after = sorted(os.path.basename(f) for f, m in kept if start <= when(m['started']) < bounds[i + 1])
        after_aside = sorted(os.path.basename(os.path.dirname(f)) for f, m in aside
                             if start <= when(m['started']) < bounds[i + 1])
        print(f'   restart {i + 1}: {len(after)} kept phases and {len(after_aside)} later-set-aside attempts started after it')
        for name in after:
            print(f'        kept       {name[:60]}  (attempts of this set that were set aside: {aside_names.get(name, 0)})')
        for name in after_aside:
            print(f'        set aside  {name[:75]}')
        ok = all(aside_names.get(name, 0) > 0 for name in after)
        print(f'        every phase started after this restart is a set with an earlier attempt set aside: {ok}')
    # every set-aside attempt 1 started before the first restart
    first_attempts = [m for f, m in aside if os.path.basename(os.path.dirname(f)).endswith('attempt1')]
    print(f'   every first attempt later set aside started before the first restart: '
          f'{all(when(m["started"]) < restarts[0] for m in first_attempts)}')
    learn = [m for f, m in kept if m['phase'] == 'learn3']
    print(f'   learning blocks: {len(learn)}, all started before the first restart: '
          f'{all(when(m["started"]) < restarts[0] for m in learn)}')
print(f'Restarts in all: {restarts_total}. Batch jobs named in the manifests: one for each task (section 1).')

# ---------------------------------------------------------------------------------------------------------------------
head('3  Timing rows: flights of record, missed deadlines with each flight counted once, attempts set aside')
record = collections.Counter()
aside_learning = collections.Counter()
aside_eval = collections.Counter()
late_rows = []
for task in TASKS:
    for folder, m in phases(os.path.join(RUNS, TAG + task)):
        for row in load(os.path.join(folder, 'timing.json')):
            kind = m['phase']
            if 'set_aside_from' in row:          # a learning call moved aside as late and flown again
                aside_learning['rows'] += 1
                aside_learning['late rows'] += bool(row['late'])
                aside_learning['missed deadlines'] += row['missed_deadlines']
                if row['late']:
                    late_rows.append((task, 'learning, set aside', folder, row))
                continue
            record[(kind, 'flights')] += 1
            record[(kind, 'late')] += bool(row['late'])
            record[(kind, 'kept late')] += bool(row.get('kept_late'))
            record[(kind, 'missed deadlines')] += row['missed_deadlines']
            record[(kind, 'commands off the deadline')] += row['off_deadline_commands']
            if row['late']:
                late_rows.append((task, 'of record, kept late', folder, row))
    for folder, m in phases(os.path.join(RUNS, TAG + task + '.set-aside')):
        rows = load(os.path.join(folder, 'timing.json'))
        aside_eval['attempts'] += 1
        aside_eval[('attempts', task)] += 1
        aside_eval['rows'] += len(rows)
        aside_eval['late rows'] += sum(bool(r['late']) for r in rows)
        aside_eval['missed deadlines'] += sum(r['missed_deadlines'] for r in rows)
        aside_eval['commands off the deadline'] += sum(r['off_deadline_commands'] for r in rows)
        for r in rows:
            if r['late']:
                late_rows.append((task, 'evaluation, set aside', folder, r))
total = collections.Counter()
for (kind, what), n in sorted(record.items()):
    print(f'   flights of record, {kind}: {what} {n}')
    total[what] += n
print(f'   flights of record in all: {total["flights"]} (the validation check counted {gate["checked"]["unique flights"]})')
print(f'   late {total["late"]}, kept late {total["kept late"]}, missed deadlines {total["missed deadlines"]}, '
      f'commands off the deadline {total["commands off the deadline"]}')
print(f'   learning calls set aside as late: rows {aside_learning["rows"]}, late rows {aside_learning["late rows"]}, '
      f'missed deadlines {aside_learning["missed deadlines"]}')
print(f'   evaluation attempts set aside: {aside_eval["attempts"]} '
      f'(reach {aside_eval[("attempts", "reach")]}, reach3d {aside_eval[("attempts", "reach3d")]}, '
      f'land {aside_eval[("attempts", "land")]}); flights in them {aside_eval["rows"]}, late {aside_eval["late rows"]}, '
      f'missed deadlines {aside_eval["missed deadlines"]}, commands off the deadline {aside_eval["commands off the deadline"]}')

# ---------------------------------------------------------------------------------------------------------------------
head('4  Late flights: when each late decision fell')
print('For each late flight: the phase, the flight, each decision that missed its deadline (second of the flight and own lag)')
print('and the moment of that decision, taken as the time recorded before the flight plus the second of the flight. The start-up')
print('of a flight (arming and take-off) comes between the two, so the moments are comparable between flights and are not exact.')


def before_flight(outcome_path):
    """The time recorded before a flight and its length, from the results.jsonl beside the flight's folder."""
    flight = os.path.dirname(outcome_path)
    name = os.path.basename(flight)
    with open(os.path.join(os.path.dirname(flight), 'results.jsonl')) as f:
        for line in f:
            r = json.loads(line)
            if f'{r["family"]}-{r["seed"]}' == name:
                return when(r['before_flight']['time']), r['seconds'], r['before_flight'].get('load_1min')
    raise SystemExit(f'no results row for {outcome_path}')


moments = []
for task, kind, folder, row in late_rows:
    name = row['flight'].rsplit('/', 1)[-1]
    if kind.startswith('learning'):
        outcome_path = os.path.join(folder, row['flight'], 'outcome.json')
    else:
        outcome_path = os.path.join(folder, 'flights', name, 'outcome.json')
    o = load(outcome_path)
    began, lasted, load_1min = before_flight(outcome_path)
    missed = []
    for s in o['native_steps']:
        own = round(s['decision_lag_s'] - s['observation_lag_s'], 3)
        if periods(own) >= DEADLINE_PERIODS:
            missed.append((s['t'], own))
    assert len(missed) == row['missed_deadlines'], outcome_path
    for t, own in missed:
        at = began + datetime.timedelta(seconds=t)
        attempt = os.path.basename(os.path.dirname(folder)).rsplit('-', 1)[-1] if kind.startswith('evaluation') else ''
        print(f'   {task:8s} {kind:22s} {os.path.basename(folder)[:34]:34s} {attempt:9s} {name:22s} second {t:3d}, own lag '
              f'{own:.3f} s, at about {at}; flight of {lasted} s; node load before the flight {load_1min}')
        moments.append((task, kind, os.path.basename(folder), name, at, own))
print()
print('Late decisions of one task that fell within 10 s of each other, in different sets of flights:')
for task in TASKS:
    mine = sorted((m for m in moments if m[0] == task), key=lambda m: m[4])
    groups, group = [], []
    for m in mine:
        if group and (m[4] - group[-1][4]).total_seconds() > 10:
            groups.append(group)
            group = []
        group.append(m)
    if group:
        groups.append(group)
    for g in groups:
        sets = sorted({m[2][:40] for m in g})
        lags = sorted(m[5] for m in g)
        mark = 'TOGETHER' if len(sets) > 1 else 'alone   '
        print(f'   {task:8s} {mark} {g[0][4]} to {g[-1][4].time()}: {len(g)} late decisions in {len(sets)} sets, own lags '
              f'{lags[0]:.3f} to {lags[-1]:.3f} s ({", ".join(sorted({m[1] for m in g}))})')

# ---------------------------------------------------------------------------------------------------------------------
head('5  The adoption test: flights that met the goal while failing the pass rule')
flights = {}
conflicts = 0
for task in TASKS:
    root = os.path.join(RUNS, TAG + task)
    for block in range(40):
        folder = os.path.join(root, f'learn3-{task}-b{block}')
        arms = load(os.path.join(folder, 'arms.json'))
        assert arms['task'] == task and arms['block'] == block
        for arm, record_ in sorted(arms['arms'].items()):
            for trial in record_['trials']:
                for o in trial['outcomes']:
                    key = (task, block, trial['flight_dir'], o['episode_id'])
                    value = (o['goal_met'], o['trial_passed'], o['end_reason'], trial['trial_list'])
                    if key in flights and flights[key] != value:
                        conflicts += 1
                    flights[key] = value
unique = flights
by = collections.Counter()
met_but_failed = []
passed_not_met = []
checked_files = 0
missing_files = 0
disagree = 0
refusals = help_requests = 0
for key, (goal_met, passed, end_reason, trial_list) in sorted(unique.items()):
    task, block, flight_dir, episode = key
    by[(task, trial_list, 'flights')] += 1
    by[(task, trial_list, 'goal met')] += bool(goal_met)
    by[(task, trial_list, 'passed')] += bool(passed)
    if goal_met and not passed:
        met_but_failed.append(key)
    if passed and not goal_met:
        passed_not_met.append(key)
    path = os.path.join(RUNS, TAG + task, f'learn3-{task}-b{block}', flight_dir, episode, 'outcome.json')
    if os.path.exists(path):
        o = load(path)
        checked_files += 1
        disagree += (bool(o['goal_met']) != bool(goal_met)) or (o['end_reason'] != end_reason)
        refusals += bool(o.get('refusals'))
        help_requests += bool(o.get('help_requests'))
        if goal_met and (o.get('refusals') or o.get('help_requests')):
            met_but_failed.append(key + ('from the outcome record',))
    else:
        missing_files += 1
print(f'Adoption-test flights, each counted once (arms B and C share the first candidate\'s zone test): {len(unique)}')
print(f'Records of one flight that differ between two arms of a block: {conflicts}')
for task in TASKS:
    for trial_list in ('matched', 'threat'):
        name = 'zone-free test' if trial_list == 'matched' else 'zone test'
        print(f'   {task:8s} {name:15s} flights {by[(task, trial_list, "flights")]:4d}, goal met '
              f'{by[(task, trial_list, "goal met")]:4d}, passed the rule {by[(task, trial_list, "passed")]:4d}')
print(f'Flights that met the goal and failed the pass rule: {len(met_but_failed)} {met_but_failed}')
print(f'Flights that passed the rule without meeting the goal: {len(passed_not_met)}')
print(f'Outcome records found in the extract for these flights: {checked_files} (missing {missing_files}); '
      f'records whose goal_met or end reason differ from arms.json: {disagree}; '
      f'records with a guard refusal: {refusals}; records with a request for help: {help_requests}')
sizes = collections.Counter()
for task in TASKS:
    for block in range(40):
        arms = load(os.path.join(RUNS, TAG + task, f'learn3-{task}-b{block}', 'arms.json'))
        for arm, record_ in arms['arms'].items():
            for trial in record_['trials']:
                sizes[len(trial['outcomes'])] += 1
                if trial['outcomes']:
                    assert trial['passed'] == all(o['trial_passed'] for o in trial['outcomes'])
                else:                            # a reply that was not valid never flew: no flights and not passed
                    assert trial['flight_dir'] is None and trial['passed'] is False
print(f'Flights in each adoption test, over every arm\'s tests: {dict(sizes)} (0 flights: a reply that was not valid and never '
      f'flew); a test that flew passed exactly when all three of its flights passed.')

# ---------------------------------------------------------------------------------------------------------------------
head('6  The kept-late flights')
for task in TASKS:
    for folder, m in phases(os.path.join(RUNS, TAG + task)):
        path = os.path.join(folder, 'kept-late.json')
        if os.path.exists(path):
            k = load(path)
            for name in k['kept_late_flights']:
                o = load(os.path.join(folder, 'flights', name, 'outcome.json')) \
                    if os.path.exists(os.path.join(folder, 'flights', name, 'outcome.json')) else None
                if o is None:
                    for sub, _, files in os.walk(folder):
                        if os.path.basename(sub) == name and 'outcome.json' in files:
                            o = load(os.path.join(sub, 'outcome.json'))
                arms = (m.get('args') or {}).get('arms')
                print(f'   {task}, {os.path.basename(folder)[:40]}, arms {arms}, flight {name}: goal met {o["goal_met"]}, '
                      f'ended {o["end_reason"]}; attempts set aside before it {k["late_attempts_set_aside"]}')

# ---------------------------------------------------------------------------------------------------------------------
head('7  Study 1: three tables of S14, copied from Study 1\'s analysis record (nothing is computed)')
STUDY1 = sys.argv[3] if len(sys.argv) > 3 else \
    '/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-2/analysis/analysis.json'
a = load(STUDY1)
PREFIX = a['root'] + '/'


def of(d):
    return f'{d["k"]} of {d["n"]}'


def signed(x, places):
    return f'{x:+.{places}f}'.replace('-', '−')


def name_of(task, run):
    return f'learn-{task}-{run}' if task in ('avoid', 'orbit') else f'learn-{task}-b{run}-matched'


print('BEGIN S14b')
print('| Task | Run | Adopted at candidate | Held-out flights met | Courses completed (gates reached) | Split-S in ArduPilot\'s simulator, completed (gates) | Split-S in Gazebo, completed (gates) |')
print('|---|---|---|---|---|---|---|')
for task in ('reach', 'reach3d', 'avoid', 'orbit', 'land'):
    runs = a['learning'][task]['runs']
    for i, r in enumerate(runs):
        assert r['adopted'] is True
        if r['run'] is not None:
            assert r['run'] == i
        elif task in ('reach', 'reach3d', 'land'):
            assert r['attempts'] == 1          # the order of these runs in the list is then immaterial to this table
        key = PREFIX + name_of(task, i) + '/run'
        held = a['heldout'][task]['learned:' + key]
        course = a['courses'].get(('flat:' if task == 'reach' else '3d:') + key) if task in ('reach', 'reach3d') else None
        sitl = a['splits'].get(key) if task == 'reach3d' else None
        gz = a['splits'].get('Gazebo, ' + key) if task == 'reach3d' else None
        cell = lambda c: f'{of(c["completed"])} ({of(c["gates"])})' if c else ''
        print(f'| {task} | {i} | {r["attempts"]} | {of(held)} | {cell(course)} | {cell(sitl)} | {cell(gz)} |')
print('END S14b')
print('BEGIN S14c')
print('| Controller | ArduPilot\'s simulator: flights, median finish, longest finish, s | Gazebo: flights, median finish, longest finish, s |')
print('|---|---|---|')
REF = 'designer reference controller (demo.REFERENCE)'
rows = [(f'reach3d run {i}', PREFIX + name_of('reach3d', i) + '/run') for i in range(8)] + \
       [('all eight learned procedures', 'learned, pooled'), ('reference controller', REF)]
for label, key in rows:
    s1 = a['splits'][key]['finish_s']
    s2 = a['splits']['Gazebo, ' + key]['finish_s']
    print(f'| {label} | {s1["n"]}, {s1["median"]:.0f}, {s1["max"]:.0f} | {s2["n"]}, {s2["median"]:.0f}, {s2["max"]:.0f} |')
print('END S14c')
print('BEGIN S14d')
print('| Task | Goals met, learned minus reference | Goals met, learned minus ArduPilot\'s modes | Goals met, learned minus hovering | Seconds, learned minus reference | Seconds, learned minus ArduPilot\'s modes |')
print('|---|---|---|---|---|---|')
for task in ('reach', 'reach3d', 'avoid', 'orbit', 'land'):
    c = a['comparisons'][task]

    def cell(key, places):
        d = c.get(key)
        if d is None:
            return 'not flown'
        return f'{signed(d["difference"], places)} ({signed(d["low"], places)} to {signed(d["high"], places)})'
    print(f'| {task} | {cell("learned, pooled - reference", 2)} | {cell("learned, pooled - autopilot", 2)} | '
          f'{cell("learned, pooled - hold", 2)} | {cell("capped seconds: learned, pooled - reference", 2)} | '
          f'{cell("capped seconds: learned, pooled - autopilot", 2)} |')
print('END S14d')
print(f'Study 1\'s record: {a["phases_found"]} phase folders read, validation ok {a["validation"]["ok"]}, '
      f'adopted runs {a["validation"]["adopted_libraries"]}.')

# ---------------------------------------------------------------------------------------------------------------------
head('8  The planner check: zone entries by the direction of approach, for Dijkstra\'s planner (settings 1 and 2)')
PLANNER = sys.argv[4] if len(sys.argv) > 4 else \
    '/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/planner-check-20261120/both'
import math
print('Dijkstra\'s planner stands a hexagon in for each circle, with corners at compass bearings 30, 90, 150, 210, 270 and 330')
print('degrees from the centre. For each flight: the drone\'s bearing from the zone\'s centre at the decision when the zone was')
print('sent (the step of the first upload in planner.json, the position ArduPilot reported at that step in outcome.json),')
print('as degrees from the nearest corner. A bearing 0 to 10 degrees from a corner faces a corner; 20 to 30 faces the middle of a side.')
groups = collections.defaultdict(lambda: [0, 0])
flights_read = 0
for folder, _, files in os.walk(PLANNER, followlinks=True):
    if 'planner.json' in files and 'outcome.json' in files:
        p = load(os.path.join(folder, 'planner.json'))
        if p['setting'] not in (1, 2):
            continue
        o = load(os.path.join(folder, 'outcome.json'))
        up = p['uploads'][0]
        zone = up['new_zones'][0]
        steps = {s['t']: s for s in o['native_steps']}
        s = steps.get(up['step']) or steps[min(steps, key=lambda t: abs(t - up['step']))]
        bearing = math.degrees(math.atan2(s['east_m'] - zone['east_m'], s['north_m'] - zone['north_m'])) % 360
        from_corner = abs(((bearing - 30) + 30) % 60 - 30)
        g = 'corner (0 to 10)' if from_corner < 10 else 'between (10 to 20)' if from_corner < 20 else 'side (20 to 30)'
        groups[(p['setting'], g)][1] += 1
        groups[(p['setting'], g)][0] += o['end_reason'] == 'entered_threat'
        flights_read += 1
print(f'flights read: {flights_read}')
for key in sorted(groups):
    print(f'   setting {key[0]}, facing a {key[1]}: {groups[key][0]} of {groups[key][1]} entered the zone')

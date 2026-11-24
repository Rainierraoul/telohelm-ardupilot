"""Timing preflight for protocol 3 (notes/TAKEOVER-20261111.md, job 5).

From 13 November 2026 protocol 3's flights carry a fixed delay between each observation and its command, and
ardupilot/ladder.py timing() judges them by its deadline (round four). This tool flies and reads as before the delay,
with ladder.timing_before_delay, and is kept for the records it made; the load limit it set is a Mac figure.

Decision lag rises with machine load, so before the protocol is frozen a quiet machine has to show that flights with
four simulators at once stay on time, and the load limit that the scored run enforces comes from that preflight.

Run from paper3/ with the project interpreter. Without --fly nothing is started: the command prints the plan, checks
the seeds, and with --write-readonly saves the count of earlier flights that the rules below would call late.

  .venv/bin/python -m protocol.timing_preflight3 --task reach                       (plan only)
  .venv/bin/python -m protocol.timing_preflight3 --task reach --write-readonly      (the read-only count, saved once)
  .venv/bin/python -m protocol.timing_preflight3 --task reach --fly                 (flies; needs the machine alone)

Rules, each from the note (TAKEOVER-20261111.md, "Open items and rulings", the rulings of 11 November, 5:05 pm, and
the section of 12 November 2026 on the two timing preflights):
  a flight is late if any lag is missing, if the median of its lags read on the telemetry step is above 0.05 s
  (5% of the 1 s decision period, PROTOCOL-2.md line 66), or if any command is issued 1 s or more after its
  scheduled time. The rule is the driver's own (ardupilot/ladder.py, timing), so the preflight, the driver, the gate
  and the set-aside tool cannot disagree. Read on the step, the median rule means more than half the decisions at
  least one step late, or exactly half when every lag in the late half is two steps or more; exactly half with
  one-step lags is on time.
  The share of decisions at least 0.1 s late is reported beside every median (PROTOCOL-2.md line 66; DESIGN line 124).
  Lag arrives in steps of the 0.1 s telemetry period and is recorded as 0.098, 0.1 or 0.101 s for one step, so a
  threshold on a step is applied 0.005 s below it, as protocol/analysis.py line 349 does: 0.095 s and 0.995 s.
  The load limit is the highest one-minute load average recorded at the start of a four-at-once flight, in a
  preflight in which every flight of both stages was on time. One-at-a-time flights do not set it: a load at which
  one simulator flew has not been checked with four. If any flight is late, or the preflight did not finish, there
  is no limit.
  In the four-at-once stage each simulator flies the same development cases in its own order (case_order), so that
  no two simulators fly the same seed at the same moment. Scored phases on the four simulators fly different
  scenarios. The first two attempts flew the same seed on all four together, which makes every decision's two
  sandboxed calls start at the same instant on four simulators (reproduction/timing-diagnostic-sandbox-*.json).

The summary functions read timing fields only. Flying uses the repository's own pieces: battle.run with the authored
reference procedure (demo.REFERENCE), one process per simulator instance as protocol/parallel_lag.py does, and the
development seeds of seeds-3.json (its 'pilot' book).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS_3 = ROOT / 'protocol' / 'seeds-3.json'
READONLY_PATH = ROOT / 'reproduction' / 'timing-preflight-20261111.json'
sys.path.insert(0, str(ROOT))
from ardupilot import ladder  # noqa: E402  the lateness rule is the driver's own

MAX_MEDIAN_LAG_S = ladder.MAX_MEDIAN_LAG_S      # 0.05 s: PROTOCOL-2.md line 66; TAKEOVER-20261111.md line 62
LATE_DECISION_S = ladder.LATE_DECISION_S        # 0.995 s: 1 s behind schedule, read 0.005 s below the step (item 8)
LATE_SHARE_FROM_S = ladder.LATE_SHARE_FROM_S    # 0.095 s: 'at least 0.1 s late' as protocol/analysis.py line 349 counts
DECISION_PERIOD_S = 1.0     # 'The decision period is 1 s in every runner' (PROTOCOL-2.md line 66)
FIRST_INSTANCE = 10         # PROTOCOL-2.md line 66 and scored.SCORED_INSTANCES: instances 10 to 13
INSTANCES = (10, 11, 12, 13)
SPEEDUP = 1.0               # every scored phase runs in real time (PROTOCOL-2.md line 66)
ONE_AT_A_TIME, FOUR_AT_ONCE = 'one_at_a_time', 'four_at_once'
TASKS = ('reach', 'reach3d', 'land')


# ---------------------------------------------------------------- timing of one flight, and the summary

def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def flight_timing(outcome: dict) -> dict:
    """Timing fields of one recorded flight, from its native steps, by the rule of its time
    (ladder.timing_before_delay). Any missing or non-finite lag makes the lag fields None, which the rule counts as late."""
    t = ladder.timing_before_delay(outcome)
    return {'median_lag_s': t['median_lag_s'], 'max_lag_s': t['max_lag_s'],
            'share_at_least_0_1s': t['late_share_0_1s'], 'step_median_lag_s': t['step_median_lag_s'],
            'steps': len(outcome.get('native_steps') or [])}


def _field(rec: dict, *names):
    for n in names:
        if n in rec:
            return rec[n]
    return None


def late_reasons(rec: dict) -> list:
    """Why a recorded flight is late under the note's rule, from its timing fields only. An empty list means on
    time. The stored 'late' flag of older records is not used: the earlier driver omitted the 1 s rule.

    The fields are those flight_timing gives, which applies ladder.timing's rule. A record written before 12 November
    2026 has no median read on the step; its recorded median stands in for it, which reads exactly half the decisions
    one step late as late and so can only make it later."""
    median, largest = rec.get('median_lag_s'), rec.get('max_lag_s')
    step = rec['step_median_lag_s'] if 'step_median_lag_s' in rec else median
    if not _finite(median) or not _finite(largest) or not _finite(step):
        return ['a lag is missing']
    reasons = []
    if step > MAX_MEDIAN_LAG_S:
        reasons.append(f'median lag read on the telemetry step {step} s is above {MAX_MEDIAN_LAG_S} s '
                       f'(recorded median {median} s)')
    if largest >= LATE_DECISION_S:
        reasons.append(f'a command was {largest} s late against its schedule')
    return reasons


def _start_load(rec: dict):
    """The one-minute load average at the flight's start, or None."""
    if _finite(rec.get('load_1min_at_start')):
        return rec['load_1min_at_start']
    pair = rec.get('load_average_1_5_15_at_start')
    return pair[0] if pair and _finite(pair[0]) else None


def summarise(flights: list, require_four_at_once: bool = True) -> dict:
    """Per-flight figures, on-time or late for each flight, and the proposed load limit with pass or fail.

    Each flight is a dict of timing fields: median_lag_s, max_lag_s, share_at_least_0_1s (or late_share_0_1s),
    steps (or action_steps), first_sight_m, group, and the load at its start (load_average_1_5_15_at_start or
    load_1min_at_start). The proposed limit is the highest one-minute start load over the four-at-once flights, and
    exists only if no flight of either stage was late and every flight has a recorded load. With require_four_at_once
    switched off, recorded flights from other probes can be summarised, and the figure is then the highest start load
    over all of them."""
    rows = []
    for rec in flights:
        reasons = late_reasons(rec)
        rows.append({'flight': rec.get('flight'), 'group': rec.get('group'), 'instance': rec.get('instance'),
                     'median_lag_s': rec.get('median_lag_s'), 'max_lag_s': rec.get('max_lag_s'),
                     'step_median_lag_s': rec.get('step_median_lag_s'),
                     'share_at_least_0_1s': _field(rec, 'share_at_least_0_1s', 'late_share_0_1s'),
                     'steps': _field(rec, 'steps', 'action_steps'), 'first_sight_m': rec.get('first_sight_m'),
                     'load_average_1_5_15_at_start': rec.get('load_average_1_5_15_at_start'),
                     'load_1min_at_start': _start_load(rec),
                     'late': bool(reasons), 'late_reasons': reasons})
    groups = {}
    for r in rows:
        g = groups.setdefault(r['group'], {'flights': 0, 'late': 0})
        g['flights'] += 1
        g['late'] += r['late']
    loads = [r['load_1min_at_start'] for r in rows]
    problems = []
    if not rows:
        problems.append('no flights')
    if any(r['late'] for r in rows):
        problems.append(f"{sum(r['late'] for r in rows)} of {len(rows)} flights were late")
    if any(x is None for x in loads):
        problems.append('a flight has no recorded start load')
    if require_four_at_once and FOUR_AT_ONCE not in groups:
        problems.append('no four-at-once flights')
    known = [x for x in loads if x is not None]
    four = [r['load_1min_at_start'] for r in rows if r['group'] == FOUR_AT_ONCE and r['load_1min_at_start'] is not None]
    basis = four if require_four_at_once else known
    limit = max(basis) if basis and not problems else None
    return {'rule': 'late if any lag is missing, median lag read on the telemetry step above 0.05 s (more than half '
                    'the decisions a step late, or exactly half with every late lag two steps or more), or any command 1 s or more behind its schedule (recorded lag 0.995 s '
                    'or more), as ardupilot/ladder.py timing(); load limit '
                    'is the highest one-minute start load of a four-at-once flight in a preflight where every flight '
                    'was on time',
            'flights': rows, 'groups': groups, 'late_flights': sum(r['late'] for r in rows),
            'on_time_flights': sum(not r['late'] for r in rows),
            'max_start_load_1min_all_flights': max(known) if known else None,
            'max_start_load_1min_four_at_once': max(four) if four else None,
            'proposed_load_limit_1min': limit, 'pass': limit is not None, 'problems': problems}


# ---------------------------------------------------------------- the read-only count on the earlier scored run

def default_frozen_root() -> Path:
    """scored-2's folder: in this checkout, or else in the main checkout of the repository that holds the worktree."""
    here = ROOT / 'runs' / 'scored-2'
    if here.is_dir():
        return here
    common = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    return Path(common).parent / 'paper3' / 'runs' / 'scored-2'


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def count_frozen_hazard_flights(root: Path) -> dict:
    """Open every hazard-phase flight record of the earlier scored run, read only, and say how many of them the 1 s
    rule and the median rule would call late. The hazard phase is the phase named 'threat' in its manifest. Phases
    set aside earlier live in a sibling folder and are not read."""
    root = Path(root)
    phases = sorted(m.parent for m in root.glob('*/manifest.json')
                    if json.loads(m.read_bytes()).get('phase') == 'threat')
    rows = []
    for phase in phases:
        for f in sorted((phase / 'flights').glob('*/outcome.json')):
            raw = f.read_bytes()
            t = flight_timing(json.loads(raw))
            reasons = late_reasons(t)
            rows.append({'file': str(f.relative_to(root)), 'sha256': _sha256(raw), **t,
                         'late_by_median_rule': t['median_lag_s'] is None or t['median_lag_s'] > MAX_MEDIAN_LAG_S,
                         'late_by_1s_rule': t['max_lag_s'] is None or t['max_lag_s'] >= LATE_DECISION_S,
                         'late_by_either': bool(reasons)})
    listing = '\n'.join(f"{r['sha256']}  {r['file']}" for r in rows)
    analysis = root / 'analysis' / 'analysis.json'
    cross = None
    if analysis.exists():
        a = json.loads(analysis.read_bytes())['decision_lag_s']['threat']
        cross = {'file': str(analysis.relative_to(root)), 'sha256': _sha256(analysis.read_bytes()),
                 'decisions_in_analysis': a['n'], 'decisions_in_these_flights': sum(r['steps'] for r in rows),
                 'max_lag_in_analysis_s': a['max']}
    lags = sorted({x for f in [root / r['file'] for r in rows]
                   for x in [s['decision_lag_s'] for s in json.loads(f.read_bytes())['native_steps']]})
    return {'flights': len(rows), 'phases': len(phases),
            'late_by_1s_rule': sum(r['late_by_1s_rule'] for r in rows),
            'late_by_median_rule': sum(r['late_by_median_rule'] for r in rows),
            'late_by_either_rule': sum(r['late_by_either'] for r in rows),
            'largest_lag_s': max(r['max_lag_s'] for r in rows), 'distinct_lag_values_s': lags,
            'input_list_sha256': _sha256(listing.encode()),
            'input_list_basis': "sha256 of the lines '<file sha256>  <path relative to the runs folder>', one per "
                                'flight in sorted order; each flight is also listed with its own hash',
            'runs_folder': str(root), 'analysis_cross_check': cross, 'rows': rows}


# ---------------------------------------------------------------- development seeds only

def reserved_seeds(seeds: dict) -> set:
    """Every seed that seeds-3.json reserves for scored runs: all integers outside its 'pilot' book."""
    found = set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, int):
            found.add(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk({k: v for k, v in seeds.items() if k not in ('pilot', 'design', 'version')})
    return found


def development_seeds(seeds: dict, task: str) -> list:
    """The development evaluation seeds, then the development retention seeds, of one task, in flying order."""
    book = seeds['pilot']
    return [s for band in ('close', 'middle', 'wide') for s in book['threat_evaluation'][task][band]] + \
           [s for fam in ('calm', 'wind') for s in book['heldout'][task][fam]]


def refuse_scored_seeds(used, seeds: dict):
    """Stop the program if any seed in use is one that scored runs reserve."""
    clash = sorted(set(int(s) for s in used) & reserved_seeds(seeds))
    if clash:
        raise SystemExit(f'refusing to fly: seeds {clash[:5]} are reserved for scored runs in {SEEDS_3.name}')


def flight_cases(seeds: dict, task: str):
    """The scenarios to fly, from the development book, after the seed check. Needs the telohelm environment."""
    sys.path.insert(0, str(ROOT))
    from protocol import contract3
    cases = contract3.evaluation_cases(seeds, task, pilot=True) + contract3.retention_cases(seeds, task, pilot=True)
    refuse_scored_seeds([int(c.episode_id.rsplit('-', 1)[1]) for c in cases], seeds)
    return cases


# ---------------------------------------------------------------- flying

def load_now() -> list:
    return [round(x, 2) for x in os.getloadavg()]


def first_sight_m(folder: Path):
    """The true distance to the zone's edge at the first reading that shows it (analysis.threat_first_sight, which
    the earlier run's analysis used), or None for a flight with no zone that switched on."""
    from protocol.analysis import threat_first_sight
    sights = [x['first_sight_m'] for x in threat_first_sight(folder)]
    return min(sights) if sights else None


def case_order(n: int, instance: int, group: str) -> list:
    """The order in which one simulator flies the n development cases. One at a time it is the listed order. Four at
    once, simulator k of the four starts k quarters of the way down the list and wraps round, so every simulator
    flies every case and no two fly the same case at the same moment (TAKEOVER-20261111.md, 12 November 2026)."""
    if group != FOUR_AT_ONCE:
        return list(range(n))
    from protocol import contract3
    if instance not in INSTANCES:
        raise ValueError(f'instance {instance} is not one of {INSTANCES}')
    return contract3.flight_order(n, instance)     # the scored run's evaluation order too (round two, ruling 2)


def warmup_case(seeds: dict, task: str):
    """The warm-up flight's case: the first calm retention case of the task's development book (the same case
    ardupilot/scored.py's warmup_case picks), checked against the scored seeds."""
    from protocol import contract3
    case = contract3.retention_cases(seeds, task, pilot=True)[0]
    refuse_scored_seeds([int(case.episode_id.rsplit('-', 1)[1])], seeds)
    return case


def worker(task: str, instance: int, group: str, out: Path):
    """Fly every development case of the task on one simulator instance, one at a time, with the load recorded just
    before each flight. A file named STOP in the preflight folder ends the worker after the flight in progress."""
    sys.path.insert(0, str(ROOT))
    from ardupilot import battle, demo
    seeds = json.loads(SEEDS_3.read_text())
    listed = flight_cases(seeds, task)
    cases = [listed[j] for j in case_order(len(listed), instance, group)]
    base = out / group / f'instance-{instance}'
    base.mkdir(parents=True)
    log = base / 'flights.jsonl'
    # The process's first flight is a warm-up (ruling 6): the first calm retention case of the development book, with
    # the reference controller, in base/warmup/. It is in no flights.jsonl row, so no count below includes it.
    ladder.fly_warmup(base, task, warmup_case(seeds, task), speedup=SPEEDUP, instance=instance)
    for i, case in enumerate(cases):
        if (out / 'STOP').exists():
            print(f'instance {instance}: stop file found, ending before flight {i}', flush=True)
            break
        load, started = load_now(), datetime.datetime.now().astimezone().isoformat()
        folder = base / f'{i:02d}-{case.episode_id}'
        battle.run(folder, task, demo.REFERENCE[task], 'authored reference procedure (timing preflight)',
                   speedup=SPEEDUP, cases=[case], instance=instance)
        ended = datetime.datetime.now().astimezone().isoformat()
        outcome = json.loads((folder / case.episode_id / 'outcome.json').read_text())
        rec = {'flight': f'{group}/instance-{instance}/{folder.name}/{case.episode_id}', 'task': task, 'group': group,
               'instance': instance, 'case': case.episode_id, 'started': started, 'ended': ended,
               'load_average_1_5_15_at_start': load, 'end_reason': outcome['end_reason'],
               'goal_met': outcome['goal_met'], **flight_timing(outcome), 'first_sight_m': first_sight_m(folder)}
        with open(log, 'a') as fh:
            fh.write(json.dumps(rec) + '\n')


def stage(task: str, instances: tuple, group: str, out: Path, stopping: list) -> dict:
    """Start one worker process per instance, wait for them, and return their records. Workers run in their own
    session, so a Ctrl-C in the terminal reaches only this process, which then asks them to stop between flights."""
    sys.path.insert(0, str(ROOT))
    from ardupilot import scored
    busy = scored.other_simulators()
    if busy:
        raise SystemExit(f'the preflight needs the machine to itself; running now: {busy}')
    for inst in instances:
        ports = scored.ports_free(inst)
        if ports:
            raise SystemExit(f'instance {inst} cannot start: ports {ports} are in use')
    before = load_now()
    print(f'{group}: load averages before the stage {before}; starting instances {list(instances)}', flush=True)
    procs = []
    for k, i in enumerate(instances):
        if k:
            # Four at once, the workers start a quarter of the 1 s decision period apart, so their first flights do
            # not decide at the same instant; case_order keeps them on different cases after that.
            time.sleep(DECISION_PERIOD_S / len(INSTANCES))
        procs.append(subprocess.Popen([sys.executable, '-u', '-m', 'protocol.timing_preflight3', '--worker', '--task',
                                       task, '--instance', str(i), '--group', group, '--out', str(out)],
                                      cwd=ROOT, start_new_session=True))
    codes = []
    for p in procs:
        while p.poll() is None:
            if stopping and not (out / 'STOP').exists():
                (out / 'STOP').write_text('stop requested\n')
            time.sleep(1)
        codes.append(p.returncode)
    records = []
    for f in sorted((out / group).glob('instance-*/flights.jsonl')):
        records += [json.loads(line) for line in f.read_text().splitlines()]
    # Each worker's warm-up record, kept under a key of its own and in no count of flights.
    warmups = [json.loads(f.read_text()) for f in sorted((out / group).glob(f'instance-*/{ladder.WARMUP_DIR}/'
                                                                             f'{ladder.WARMUP_RECORD}'))]
    return {'group': group, 'instances': list(instances), 'load_before_stage': before, 'worker_exit_codes': codes,
            'flights': records, 'warmups': warmups}


def plan(seeds: dict, tasks) -> dict:
    per_task = {t: len(development_seeds(seeds, t)) for t in tasks}
    n = sum(per_task.values())
    return {'tasks': list(tasks), 'flights_per_task_per_instance': per_task,
            'one_at_a_time': {'instances': [FIRST_INSTANCE], 'flights': n},
            'four_at_once': {'instances': list(INSTANCES), 'flights': n * len(INSTANCES)},
            'flights_total': n * (1 + len(INSTANCES))}


def fly(tasks, seeds: dict) -> Path:
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    out = ROOT / 'runs' / f'timing-preflight-{stamp}'
    result_path = ROOT / 'reproduction' / f'timing-preflight-flights-{stamp}.json'
    if out.exists() or result_path.exists():
        raise SystemExit(f'{out.name} or {result_path.name} already exists; results are never overwritten')
    out.mkdir(parents=True)
    stopping = []
    signal.signal(signal.SIGINT, lambda *_: stopping.append('INT'))
    signal.signal(signal.SIGTERM, lambda *_: stopping.append('TERM'))
    stages, flights = [], []
    status = 'complete'
    for task in tasks:
        for group, instances in ((ONE_AT_A_TIME, (FIRST_INSTANCE,)), (FOUR_AT_ONCE, INSTANCES)):
            if stopping:
                status = 'stopped before ' + group + ' of ' + task
                break
            tag = f'{task}-{group}'
            sub = out / task
            sub.mkdir(exist_ok=True)
            s = stage(task, instances, group, sub, stopping)
            stages.append({'task': task, **{k: v for k, v in s.items() if k != 'flights'}})
            flights += [{**f, 'group': group} for f in s['flights']]
            if stopping or any(s['worker_exit_codes']):
                status = 'stopped or a worker failed during ' + tag
                break
        if status != 'complete':
            break
    summary = summarise(flights)
    if status != 'complete':
        # A preflight that stopped early or lost a worker sets no limit, whatever the flights it did fly show.
        summary['problems'].append(f'the preflight did not finish: {status}')
        summary['proposed_load_limit_1min'], summary['pass'] = None, False
    git = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    record = {'status': status, 'development_only': True, 'model_calls': 0, 'tasks': list(tasks),
              'procedure': 'demo.REFERENCE[task], the authored reference procedure, real time (speedup 1.0)',
              'four_at_once_order': 'each simulator flies the cases in its own order (case_order); from 12 November '
                                    '2026, before which all four flew the same case together',
              'warm_up': 'every worker first flew one warm-up flight, the first calm retention case of the development '
                         'book with the reference controller; its record is under stages[].warmups and in no count',
              'git_commit': git, 'tool_sha256': _sha256(Path(__file__).read_bytes()),
              'seeds_file_sha256': _sha256(SEEDS_3.read_bytes()), 'seed_book': 'pilot (development) only',
              'stages': stages, 'summary': summary, 'raw_records': str(out)}
    with open(result_path, 'x') as fh:
        fh.write(json.dumps(record, indent=1) + '\n')
    print(f'wrote {result_path}; pass: {record["summary"]["pass"]}; proposed limit: '
          f'{record["summary"]["proposed_load_limit_1min"]}', flush=True)
    return result_path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--task', nargs='+', choices=TASKS, required=True,
                   help='task or tasks whose development cases are flown with that task\'s reference procedure')
    p.add_argument('--fly', action='store_true', help='start simulators and fly; off by default')
    p.add_argument('--write-readonly', action='store_true',
                   help=f'save the read-only count to {READONLY_PATH.name} (refuses to overwrite)')
    p.add_argument('--frozen-root', type=Path, default=None, help="the earlier scored run's folder (default: found)")
    p.add_argument('--worker', action='store_true', help='internal: fly one instance')
    p.add_argument('--instance', type=int)
    p.add_argument('--group')
    p.add_argument('--out', type=Path)
    a = p.parse_args(argv)
    seeds = json.loads(SEEDS_3.read_text())
    if a.worker:
        worker(a.task[0], a.instance, a.group, a.out)
        return 0
    for t in a.task:
        refuse_scored_seeds(development_seeds(seeds, t), seeds)
    pl = plan(seeds, a.task)
    print(json.dumps(pl, indent=1))
    print(f"{pl['flights_total']} flights in all: {pl['one_at_a_time']['flights']} one at a time on instance "
          f"{FIRST_INSTANCE}, then {pl['four_at_once']['flights']} on instances {INSTANCES[0]} to {INSTANCES[-1]} "
          f"({'will fly' if a.fly else 'plan only, no simulator started'})", flush=True)
    if a.write_readonly:
        root = a.frozen_root or default_frozen_root()
        counts = count_frozen_hazard_flights(root)
        doc = {'status': 'development tooling output; reads the earlier scored run, changes nothing',
               'read_only_part': counts,
               'rules': {'median_rule': f'median lag above {MAX_MEDIAN_LAG_S} s (PROTOCOL-2.md line 66)',
                         '1s_rule': f'any command with a recorded lag of {LATE_DECISION_S} s or more '
                                    '(TAKEOVER-20261111.md, rulings of 11 November)',
                         'share_threshold_s': f'{LATE_SHARE_FROM_S} (as protocol/analysis.py line 349)'},
               'tool_sha256': _sha256(Path(__file__).read_bytes())}
        with open(READONLY_PATH, 'x') as fh:
            fh.write(json.dumps(doc, indent=1) + '\n')
        print(f"flights {counts['flights']}: late by the 1 s rule {counts['late_by_1s_rule']}, by the median rule "
              f"{counts['late_by_median_rule']}; wrote {READONLY_PATH}")
    if a.fly:
        fly(a.task, seeds)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

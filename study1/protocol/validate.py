"""Paper 3's validation gate (PROTOCOL.md section 6; A4 of Codex's review, 3 November 2026).

Before any result is computed, check that a run folder holds exactly what the scheduler (protocol/run_scored.py)
should have produced, and that every record is whole:

- every scheduled learning run is present and finished; one that finished without adopting is a non-adoption, one
  that is missing or crashed is a fault;
- every flight phase implied by the adopted libraries is present, finished (its logs/<phase>.done mark) and was run
  with the scheduled arguments, and no other phase is there;
- each phase holds exactly its scheduled scenarios, repeat rounds, courses and flights, each once;
- every hash-chained log has its partner file and verifies, including the bare log/heads pairs of candidate trials;
- result rows agree with each flight's own record and with the end record of its protected log;
- every phase shares one protocol hash, one seeds hash and one code commit, with the core check passed.

validate() returns {'ok', 'errors', 'checked'}. It reads only; it never changes, reruns or removes anything.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'protocol'))

PROTECTED_LOGS = ('episode.log', 'broker.log', 'gateway.log', 'flight.log')   # each needs its .heads partner


def load(path: Path):
    return json.loads(Path(path).read_text())


def payloads(log: Path) -> list:
    return [json.loads(line)['payload'] for line in Path(log).read_text().splitlines() if line.strip()]


def expected_cases(phase: str, task: str, seeds: dict, pilot: bool) -> list:
    """Scenario ids a battle-style phase must fly, as ardupilot/scored.py chooses them."""
    from ardupilot.battle import generate
    if phase in ('heldout', 'autopilot', 'repeat'):
        if pilot:
            spec = [('calm', k) for k in seeds['pilot']['heldout_calm']]
        elif phase == 'repeat':
            spec = [('calm', k) for k in seeds['repeatability']['calm']]
        else:
            spec = [('calm', k) for k in seeds['heldout']['calm']] + [('wind', k) for k in seeds['heldout']['wind']]
    elif phase == 'disturb':
        families = [f for f in seeds['disturbance'] if not (f == 'threat' and task == 'orbit')]
        spec = [(f, k) for f in families for k in (seeds['pilot']['disturbance'] if pilot else seeds['disturbance'][f])]
    elif phase == 'threat':     # second protocol, Study 2's evaluation
        spec = [('threat', k) for k in (seeds['pilot']['threat_evaluation'] if pilot else seeds['threat_evaluation'])]
    else:
        raise ValueError(phase)
    return [generate(task, f, k).episode_id for f, k in spec]


def check_chains(root: Path, errors: list, checked: Counter):
    from telohelm.runtime.trusted_log import verify
    for heads in sorted(list(root.rglob('*.heads')) + list(root.rglob('heads'))):
        log = heads.with_name('log') if heads.name == 'heads' else heads.with_name(heads.name[:-len('heads')] + 'log')
        if not log.exists():
            errors.append(f'protected log missing beside {heads.relative_to(root)}')
            continue
        checked['protected log pairs'] += 1
        if not verify(log, heads).get('ok'):
            errors.append(f'protected log does not verify: {log.relative_to(root)}')
    for name in PROTECTED_LOGS:
        for log in root.rglob(name):
            if not log.with_name(name[:-len('log')] + 'heads').exists():
                errors.append(f'heads file missing for {log.relative_to(root)}')
    for log in root.rglob('log'):
        if log.is_file() and 'trial-evidence' in log.parts and not log.with_name('heads').exists():
            errors.append(f'heads file missing for trial log {log.relative_to(root)}')


def check_battle_folder(folder: Path, cases: list, root: Path, errors: list, checked: Counter):
    """A battle.run or autopilot_modes.run folder: each scheduled scenario once, its row, record and log agreeing."""
    where = folder.relative_to(root)
    f = folder / 'results.jsonl'
    if not f.exists():
        errors.append(f'{where}: results.jsonl missing')
        return
    rows = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    ids = [f"{r['family']}-{r['seed']}" for r in rows]
    dup = sorted(k for k, n in Counter(ids).items() if n > 1)
    if dup:
        errors.append(f'{where}: scenarios with more than one row: {dup}')
    if sorted(set(ids)) != sorted(cases):
        missing, extra = sorted(set(cases) - set(ids)), sorted(set(ids) - set(cases))
        errors.append(f'{where}: rows do not match the schedule (missing {missing}, unscheduled {extra})')
    for r, k in zip(rows, ids):
        d = folder / k
        if not (d / 'outcome.json').exists() or not (d / 'episode.log').exists():
            errors.append(f'{where}/{k}: outcome.json or episode.log missing')
            continue
        o = load(d / 'outcome.json')
        ends = [p for p in payloads(d / 'episode.log') if p.get('kind') == 'episode_end']
        if (o['goal_met'], o['end_reason']) != (r['goal_met'], r['end_reason']):
            errors.append(f'{where}/{k}: result row disagrees with outcome.json')
        if len(ends) != 1 or (ends[0].get('goal_met'), ends[0].get('end_reason')) != (r['goal_met'], r['end_reason']):
            errors.append(f'{where}/{k}: result row disagrees with the protected episode log')
        checked['task flights'] += 1


def check_course_flight(folder: Path, name: str, row: dict, root: Path, errors: list, checked: Counter):
    where = folder.relative_to(root)
    if not (folder / name).exists() or not (folder / 'flight.log').exists():
        errors.append(f'{where}: {name} or flight.log missing')
        return
    rec = load(folder / name)
    logged = payloads(folder / 'flight.log')
    starts = [p for p in logged if p.get('kind') == 'flight_start']
    ends = [p for p in logged if p.get('kind') == 'flight_end']
    for k in ('completed', 'gates_passed', 'gates', 'end_reason'):
        if k in row and row.get(k) != rec.get(k):
            errors.append(f'{where}: result row and {name} disagree on {k}')
    if len(starts) != 1 or len(ends) != 1:
        errors.append(f'{where}: the protected flight log lacks one start and one end record')
        return
    gates = len(starts[0]['course']['gates'])
    end = ends[0]
    if (rec['end_reason'], rec['gates_passed'], rec['gates'], rec['completed']) != \
            (end.get('end_reason'), end.get('gates_passed'), gates, end.get('gates_passed') == gates) or \
            end.get('completed', rec['completed']) != rec['completed']:
        errors.append(f'{where}: {name} disagrees with the protected flight log')
    checked['course flights'] += 1


def same_library(recorded: str, scheduled: str) -> bool:
    """The library a phase flew is the one scheduled for it. In the original records the paths are the same. In a copy
    of the records moved to another folder only the root differs, so the learning-run folder and its run folder
    (learn-<task>-<run>/run) must match. The manifest keeps the recorded absolute path as provenance."""
    r, s = Path(recorded), Path(scheduled)
    return r.resolve() == s.resolve() or (len(r.parts) >= 2 and r.parts[-2:] == s.parts[-2:])


def validate(root: Path, tasks=None, reuse: Path | None = None, pilot: bool = False, protocol: int = 1,
             blocks: int | None = None) -> dict:
    import run_scored as S
    from ardupilot import scored as R
    from ardupilot.battle import adopted_source
    from ardupilot.scored import GAZEBO_FLIGHTS, SPLITS_FLIGHTS
    root = Path(root)
    tasks = list(tasks or S.TASKS)
    runs = range(1) if (pilot or reuse) else S.RUNS
    block_range = range(1) if (pilot or reuse) else range(blocks or S.BLOCKS)
    seeds_name, protocol_name, _ = R.VERSIONS[protocol]
    seeds = load(ROOT / 'protocol' / seeds_name)
    R.use_protocol(protocol)
    errors, checked = [], Counter()
    if protocol == 2 and not (pilot or reuse) and blocks not in (None, S.BLOCKS):
        # A scored run is checked against every scheduled block, so learning runs held by the spending stop, or never
        # started, are missing runs (faults), and the run cannot pass as a smaller study.
        errors.append(f'a scored second-protocol run is checked at {S.BLOCKS} blocks, not {blocks}')
    if not root.is_dir():
        return {'ok': False, 'errors': [f'{root} is not a folder'], 'checked': {}}
    done = lambda name: (root / 'logs' / f'{name}.done').exists()

    # Learning runs: present and finished; adoption decides the later schedule.
    if reuse:
        learn = []
    else:
        learn = S.learning_jobs(root, tasks, runs) if protocol == 1 else S.learning_jobs_2(root, tasks, block_range)
    for name, args in learn:
        folder, task = root / name, args[args.index('--task') + 1]
        run = int(args[args.index('--run') + 1]) if '--run' in args else 0
        block = int(args[args.index('--block') + 1]) if '--block' in args else None
        family = args[args.index('--family') + 1] if '--family' in args else None
        summary = folder / 'run' / 'summary.json'
        if not (folder / 'manifest.json').exists() or not summary.exists() or not done(name):
            errors.append(f'{name}: learning run missing or not finished (a fault, not a non-adoption)')
            continue
        man, s = load(folder / 'manifest.json'), load(summary)
        want_family, want, which = R.learning_plan(seeds, task, run, block, family, pilot)
        if man.get('phase') != 'learn' or man['args'].get('task') != task \
                or any(man['args'].get(k) != v for k, v in which.items()) \
                or man['args'].get('learning_seeds') != want \
                or (protocol == 2 and man['args'].get('learning_family') != want_family):
            errors.append(f'{name}: manifest does not match the scheduled learning run')
        if s.get('chain_errors'):
            errors.append(f'{name}: the learning run reported chain errors {s["chain_errors"]}')
        if s['checks'].get('candidate_passed_trial_and_adopted'):
            try:
                adopted_source(folder / 'run')
            except Exception as exc:
                errors.append(f'{name}: summary says adopted but no adopted source could be read ({exc})')
        checked['learning runs'] += 1
    if protocol == 1:
        libs = S.libraries(root, tasks, runs, reuse)
        jobs = S.flight_jobs(root, tasks, libs) + S.gazebo_jobs(root, libs)
    else:
        libs, study2, s2, s1, gz = S.jobs_2(root, tasks, block_range, reuse)
        jobs = s2 + s1 + gz

    # Flight phases: exactly the scheduled ones, finished, with the scheduled arguments and contents.
    scheduled = {name for name, _ in learn + jobs}
    for m in root.rglob('manifest.json'):
        top = m.relative_to(root).parts[0]
        if top not in scheduled:
            errors.append(f'{top}: a phase folder that is not in the schedule')
    for name, args in jobs:
        folder = root / name
        if not (folder / 'manifest.json').exists() or not done(name):
            errors.append(f'{name}: flight phase missing or not finished')
            continue
        man, phase = load(folder / 'manifest.json'), args[0]
        a = man.get('args', {})
        if man.get('phase') != phase:
            errors.append(f'{name}: manifest phase {man.get("phase")} is not {phase}')
        if '--library' in args and not same_library(a.get('origin', ''), args[args.index('--library') + 1]):
            errors.append(f'{name}: flown with {a.get("origin")}, scheduled with {args[args.index("--library") + 1]}')
        if '--reference' in args and 'reference' not in a.get('origin', ''):
            errors.append(f'{name}: scheduled with the reference controller, flown with {a.get("origin")}')
        if '--hold' in args and 'hold still' not in a.get('origin', ''):
            errors.append(f'{name}: scheduled as hold still, flown with {a.get("origin")}')
        if phase in ('heldout', 'autopilot', 'disturb', 'repeat', 'threat'):
            task = args[args.index('--task') + 1]
            if a.get('task') != task:
                errors.append(f'{name}: manifest task {a.get("task")} is not {task}')
            cases = expected_cases(phase, task, seeds, pilot)
            if a.get('cases') != cases:
                errors.append(f'{name}: manifest scenarios differ from the scheduled ones')
            if phase == 'repeat':
                for i in range(1, seeds['repeatability']['repeats'] + 1):
                    check_battle_folder(folder / f'repeat-{i}', cases, root, errors, checked)
            else:
                check_battle_folder(folder / 'flights', cases, root, errors, checked)
        elif phase == 'courses':
            kind = args[args.index('--kind') + 1]
            lo, hi = ((900000, 900003) if kind == 'flat' else (910000, 910003)) if pilot else \
                seeds['courses_flat' if kind == 'flat' else 'courses_3d']
            rows = load(folder / 'rows.json') if (folder / 'rows.json').exists() else []
            got = [r['seed'] for r in rows]
            if sorted(got) != list(range(lo, hi)) or len(got) != len(set(got)):
                errors.append(f'{name}: courses flown {sorted(got)[:5]}... do not match the scheduled {lo} to {hi - 1}')
            for r in rows:
                check_course_flight(folder / f'seed-{r["seed"]}',
                                    'course-flight.json' if kind == 'flat' else 'course3d-flight.json', r, root,
                                    errors, checked)
        elif phase in ('splits', 'gazebo'):
            n = 1 if pilot else (SPLITS_FLIGHTS if phase == 'splits' else GAZEBO_FLIGHTS)
            rows = load(folder / 'rows.json') if (folder / 'rows.json').exists() else []
            got = [r['flight'] for r in rows]
            if a.get('flights') != n or got != list(range(1, n + 1)):
                errors.append(f'{name}: flights {got} do not match the scheduled {n}')
            for r in rows:
                sub = folder / f'flight-{r["flight"]}' / ('flight' if phase == 'gazebo' else '')
                check_course_flight(sub, 'course3d-flight.json', r, root, errors, checked)
        checked['flight phases'] += 1

    # Provenance: one protocol, one seeds file, one commit, the core check passed, pilot or scored throughout.
    mans = [load(m) for m in root.rglob('manifest.json')]
    # The source binding is the fingerprint of the executed paper 3 files (scored.source_fingerprint), not the
    # repository HEAD, which moves with other agents' unrelated commits during a run; HEAD stays in each manifest.
    for key, get in (('protocol hash', lambda m: m.get('protocol_sha256')), ('seeds hash', lambda m: m.get('seeds_sha256')),
                     ('paper 3 source fingerprint', lambda m: ((m.get('git') or {}).get('source') or {}).get('sha256')),
                     ('learning core wheel', lambda m: (m.get('core') or {}).get('wheel_sha256'))):
        values = {get(m) for m in mans}
        if len(values) > 1:
            errors.append(f'phases differ in {key}: {sorted(map(str, values))}')
    for m in mans:
        if not (m.get('core') or {}).get('ok'):
            errors.append(f"{m.get('phase')}: the core check did not pass")
        if bool(m.get('pilot')) != bool(pilot):
            errors.append(f"{m.get('phase')}: pilot flag {m.get('pilot')} in a {'pilot' if pilot else 'scored'} check")
        if not pilot and ((m.get('git') or {}).get('uncommitted_paper3') or m.get('protocol') != protocol_name):
            errors.append(f"{m.get('phase')}: not run from committed code under {protocol_name}")
        if (m.get('protocol_version') or 1) != protocol:
            errors.append(f"{m.get('phase')}: run under protocol {m.get('protocol_version') or 1}, checked as {protocol}")
    check_chains(root, errors, checked)
    return {'ok': not errors, 'errors': errors, 'checked': dict(checked), 'adopted_libraries': len(libs),
            'scheduled_phases': len(learn) + len(jobs)}


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('root', type=Path)
    p.add_argument('--tasks')
    p.add_argument('--libraries', type=Path)
    p.add_argument('--pilot', action='store_true')
    p.add_argument('--protocol', type=int, choices=(1, 2), default=1)
    p.add_argument('--blocks', type=int)
    a = p.parse_args(argv)
    r = validate(a.root, a.tasks.split(',') if a.tasks else None, a.libraries, a.pilot, a.protocol, a.blocks)
    print(json.dumps(r, indent=1))
    return 0 if r['ok'] else 3


if __name__ == '__main__':
    raise SystemExit(main())

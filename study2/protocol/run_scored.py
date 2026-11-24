"""Run paper 3's phases in order: the learning runs, then every SITL flight phase up to four at a time (one per
scored simulator instance, ardupilot.scored.SCORED_INSTANCES), then the Gazebo flights alone, then the analysis.

Each phase is one call of `python -m ardupilot.scored` with its own output folder and log. A phase that finished is
marked in logs/<phase>.done and skipped on a restart. A phase that failed is left as it is and listed at the end: under
the protocol's faults rule, whether it is rerun is decided by hand, never here.

  .venv/bin/python protocol/run_scored.py plan ROOT                 # list what would run
  .venv/bin/python protocol/run_scored.py run ROOT                  # the scored runs (runs/scored)
  .venv/bin/python protocol/run_scored.py run ROOT --pilot --libraries runs/pilot-20261102-c --tasks reach,reach3d
      # a check of the scheduler on development seeds, reusing a pilot's learned libraries (no model calls)
  .venv/bin/python protocol/run_scored.py pause ROOT                # finish the running phases, start no more

Pausing (4 November 2026), so the Mac can sleep during a run longer than a night: `pause` writes logs/PAUSE. Each
worker then finishes the phase it is flying and starts no other, and the scheduler stops with exit status 2 before
the Gazebo flights and the analysis. Running `run` again removes the pause and carries on: finished phases are
skipped by their done marks, as on any restart. A pause never interrupts a phase. Learning runs are not paused, so
that every learning run of the study falls in one window of model use; a pause asked for during learning takes effect
when the flight phases begin.
"""
import argparse
import datetime
import json
import queue
import random
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ardupilot.scored import SCORED_INSTANCES  # noqa: E402

TASKS = ('reach', 'reach3d', 'avoid', 'orbit', 'land')
SPEND_LIMIT_USD = 10.0   # list-price model cost of finished learning runs at which no further learning run starts
# Second protocol: Simon approved 8 blocks on 4 November 2026 against a forecast of about US$5.70 at list price, with
# the stop at US$12.
SPEND_LIMIT_USD_2 = 12.0
RUNS = range(5)
PY = [str(ROOT / '.venv' / 'bin' / 'python'), '-u', '-m', 'ardupilot.scored']

# Second protocol (4 November 2026). Reach, reach3d and land learn in matched blocks: in block b one run learns on
# block b's threat layouts (the threat arm) and one on the same layouts with the zones removed (the calm arm,
# family 'matched'). The calm arm's libraries are also Study 1's libraries for those tasks. Avoid and orbit learn on
# calm scenarios, five runs each, as in the first protocol.
STUDY2_TASKS = ('reach', 'reach3d', 'land')
BLOCKS = 8                   # matched blocks per Study 2 task; fixed at the freeze
ARMS = ('matched', 'threat')
ORDER_SEED = 20261104        # fixes the order of the two arms within each block, for learning and for evaluation


def now():
    return datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')


def adopted(run_folder: Path) -> bool:
    s = run_folder / 'summary.json'
    return s.exists() and bool(json.loads(s.read_text())['checks'].get('candidate_passed_trial_and_adopted'))


def learning_jobs(out: Path, tasks, runs):
    return [(f'learn-{t}-{r}', ['learn', '--task', t, '--run', str(r), '--out', str(out / f'learn-{t}-{r}')])
            for t in tasks for r in runs]


def arm_order(t: str, b: int, stage: str) -> list:
    """The two arms of block b in the order they run, drawn from ORDER_SEED, separately for learning and for
    evaluation, so that neither arm always goes first."""
    arms = list(ARMS)
    random.Random(f'{ORDER_SEED}/{stage}/{t}/{b}').shuffle(arms)
    return arms


def learning_jobs_2(out: Path, tasks, blocks):
    """Block by block, so both arms' learning runs are spread through the same window of model use."""
    jobs = []
    for b in blocks:
        for t in tasks:
            if t in STUDY2_TASKS:
                for arm in arm_order(t, b, 'learn'):
                    name = f'learn-{t}-b{b}-{arm}'
                    jobs.append((name, ['learn', '--task', t, '--block', str(b), '--family', arm,
                                        '--out', str(out / name)]))
            elif b in RUNS:
                jobs.append((f'learn-{t}-{b}', ['learn', '--task', t, '--run', str(b), '--out', str(out / f'learn-{t}-{b}')]))
    return jobs


def libraries_2(out: Path, tasks, blocks, reuse: Path | None):
    """(Study 1 libraries, Study 2 arms). Study 1: (task, label) -> adopted library, the calm arm's for reach,
    reach3d and land. Study 2: (task, block, arm) -> adopted library, or None for a finished run that did not adopt."""
    base = reuse or out
    study1, study2 = {}, {}
    for t in tasks:
        if t in STUDY2_TASKS:
            for b in blocks:
                for arm in ARMS:
                    folder = base / f'learn-{t}-b{b}-{arm}' / 'run'
                    study2[(t, b, arm)] = folder if adopted(folder) else None
                    if arm == 'matched' and adopted(folder):
                        study1[(t, f'b{b}-matched')] = folder
        else:
            for r in (range(1) if reuse else RUNS):
                folder = base / f'learn-{t}-{r}' / 'run'
                if adopted(folder):
                    study1[(t, r)] = folder
    return study1, study2


def study2_jobs(out: Path, study2: dict):
    """Every adopted library of both arms flies the fresh threat scenarios; the threat arm's also fly the calm
    held-out set (the calm arm's fly it in Study 1), so retention in calm flight can be compared."""
    jobs, tasks = [], sorted({t for t, _, _ in study2})
    for b in sorted({b for _, b, _ in study2}):
        for t in tasks:
            for arm in arm_order(t, b, 'evaluate'):
                lib = study2.get((t, b, arm))
                if lib is None:
                    continue
                name = f'threat-{t}-b{b}-{arm}'
                jobs.append((name, ['threat', '--task', t, '--library', str(lib), '--out', str(out / name)]))
                if arm == 'threat':
                    name = f'heldout-{t}-learned-b{b}-threat'
                    jobs.append((name, ['heldout', '--task', t, '--library', str(lib), '--out', str(out / name)]))
    return jobs


def libraries(out: Path, tasks, runs, reuse: Path | None):
    """(task, run) -> adopted library folder."""
    found = {}
    for t in tasks:
        for r in runs:
            folder = (reuse / f'learn-{t}' / 'run') if reuse else (out / f'learn-{t}-{r}' / 'run')
            if adopted(folder):
                found[(t, r)] = folder
    return found


def flight_jobs(out: Path, tasks, libs: dict):
    jobs = []
    o = lambda name: str(out / name)
    # Reference course flights first, so their results are on record before the learned procedures fly the same courses.
    # Every course counts for every condition (PROTOCOL.md section 4.3); nothing here filters on the reference's result.
    if 'reach' in tasks:
        jobs.append(('courses-flat-reference', ['courses', '--kind', 'flat', '--reference', '--out', o('courses-flat-reference')]))
    if 'reach3d' in tasks:
        jobs.append(('courses-3d-reference', ['courses', '--kind', '3d', '--reference', '--out', o('courses-3d-reference')]))
        jobs.append(('splits-reference', ['splits', '--reference', '--out', o('splits-reference')]))
    for t in tasks:
        jobs.append((f'heldout-{t}-reference', ['heldout', '--task', t, '--reference', '--out', o(f'heldout-{t}-reference')]))
        jobs.append((f'heldout-{t}-hold', ['heldout', '--task', t, '--hold', '--out', o(f'heldout-{t}-hold')]))
        if t != 'avoid':
            jobs.append((f'autopilot-{t}', ['autopilot', '--task', t, '--out', o(f'autopilot-{t}')]))
        jobs.append((f'repeat-{t}-reference', ['repeat', '--task', t, '--reference', '--out', o(f'repeat-{t}-reference')]))
        task_libs = sorted((r, lib) for (tt, r), lib in libs.items() if tt == t)
        for r, lib in task_libs:
            L = ['--library', str(lib)]
            jobs.append((f'heldout-{t}-learned-{r}', ['heldout', '--task', t, *L, '--out', o(f'heldout-{t}-learned-{r}')]))
            jobs.append((f'disturb-{t}-learned-{r}', ['disturb', '--task', t, *L, '--out', o(f'disturb-{t}-learned-{r}')]))
            if t == 'reach':
                jobs.append((f'courses-flat-learned-{r}', ['courses', '--kind', 'flat', *L, '--out', o(f'courses-flat-learned-{r}')]))
            if t == 'reach3d':
                jobs.append((f'courses-3d-learned-{r}', ['courses', '--kind', '3d', *L, '--out', o(f'courses-3d-learned-{r}')]))
                jobs.append((f'splits-learned-{r}', ['splits', *L, '--out', o(f'splits-learned-{r}')]))
        if task_libs:   # repeatability for the procedures: the task's first adopted library
            r, lib = task_libs[0]
            jobs.append((f'repeat-{t}-learned-{r}', ['repeat', '--task', t, '--library', str(lib), '--out', o(f'repeat-{t}-learned-{r}')]))
    return jobs


def gazebo_jobs(out: Path, libs: dict):
    jobs = [('gazebo-reference', ['gazebo', '--reference', '--out', str(out / 'gazebo-reference')])]
    for (t, r), lib in sorted(libs.items()):
        if t == 'reach3d':
            jobs.append((f'gazebo-learned-{r}', ['gazebo', '--library', str(lib), '--out', str(out / f'gazebo-learned-{r}')]))
    return jobs


class Runner:
    def __init__(self, out: Path, pilot: bool):
        self.out, self.pilot = out, pilot
        self.logs = out / 'logs'
        self.logs.mkdir(parents=True, exist_ok=True)
        self.failed, self.lock = [], threading.Lock()
        self.pausable, self.paused = False, False

    def note(self, text):
        line = f'{now()} {text}'
        with self.lock:
            print(line, flush=True)
            with open(self.logs / 'scheduler.log', 'a') as f:
                f.write(line + '\n')

    def spent_usd(self) -> float:
        """List-price model cost of the finished learning runs, those with a done mark. A run still writing its summary
        has no done mark and is not read. A finished run's summary must be readable and carry claude_cost_usd (None
        when no priced model reply was used); if not, this raises and the learning run about to start is held."""
        total = 0.0
        for done in sorted(self.logs.glob('learn-*.done')):
            total += json.loads((self.out / done.stem / 'run' / 'summary.json').read_text())['claude_cost_usd'] or 0.0
        return round(total, 4)

    protocol = 1
    spend_limit = None    # --spend-limit; None keeps the protocol's

    def one(self, name, args, instance):
        if (self.logs / f'{name}.done').exists():
            self.note(f'skip {name} (done earlier)')
            return
        spent = self.spent_usd() if args[0] == 'learn' else 0.0
        limit = self.spend_limit if self.spend_limit is not None else (
            SPEND_LIMIT_USD_2 if self.protocol == 2 else SPEND_LIMIT_USD)
        if spent >= limit:
            # First protocol: Simon approved a forecast of about US$2, stop at US$10 (PROTOCOL.md section 10). Second
            # protocol: forecast about US$5.70, stop at US$12. Past the stop the decision is his.
            self.note(f'HOLD {name}: finished learning runs cost US${spent}, at or past the '
                      f'US${limit:g} limit; not started, decision for Simon')
            with self.lock:
                self.failed.append(name)
            return
        if Path(args[args.index('--out') + 1]).exists():
            self.note(f'HOLD {name}: its folder exists without a done mark; decide under the faults rule')
            self.failed.append(name)
            return
        cmd = PY + args + (['--pilot'] if self.pilot else []) + (['--instance', str(instance)] if instance is not None else []) \
            + (['--protocol', str(self.protocol)] if self.protocol != 1 else [])
        self.note(f'start {name} on instance {instance}')
        with open(self.logs / f'{name}.log', 'w') as log:
            code = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        if code == 0:
            (self.logs / f'{name}.done').write_text(now() + '\n')
            self.note(f'end {name} on instance {instance}')
        else:
            self.note(f'FAILED {name} on instance {instance} (exit {code}); see logs/{name}.log')
            with self.lock:
                self.failed.append(name)

    def pause_marked(self) -> bool:
        """Checked at each stage boundary and before the analysis. A pause asked for while the last phase of the last
        stage is flying finds the queue empty, so pool() does not record it, and the analysis would have started. The
        marker file is read again here, so no later stage and no analysis starts after a pause (D3's review,
        4 November 2026)."""
        if self.pausable and (self.logs / 'PAUSE').exists():
            self.paused = True
        return self.paused

    def pool(self, jobs, instances):
        q = queue.Queue()
        for j in jobs:
            q.put(j)

        def worker(instance):
            while True:
                if self.pausable and (self.logs / 'PAUSE').exists():
                    with self.lock:   # note() takes the lock too, so it is called after this block
                        first = not q.empty() and not self.paused
                        self.paused = self.paused or not q.empty()
                    if first:
                        self.note('paused: running phases finish, no new phase starts')
                    return
                try:
                    name, args = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    self.one(name, args, instance)
                except BaseException as exc:   # a scheduler error is held like a failed phase, never lost (A4)
                    self.note(f'FAILED {name} on instance {instance}: scheduler error {type(exc).__name__}: {exc}')
                    with self.lock:
                        self.failed.append(name)

        threads = [threading.Thread(target=worker, args=(i,)) for i in instances]
        for th in threads:
            th.start()
        for th in threads:
            th.join()


def analysis_folder(out: Path) -> Path:
    """The first analysis folder not yet used: analysis, then analysis-2, analysis-3 and so on. A failed gate leaves
    its diagnostic in the folder it was given, and analysis.py never writes over an analysis, so the run after a fault
    has been dealt with writes beside the diagnostic (Fable's review of draft 2, 4 November 2026)."""
    n = 1
    while (out / ('analysis' if n == 1 else f'analysis-{n}') / 'analysis.json').exists():
        n += 1
    return out / ('analysis' if n == 1 else f'analysis-{n}')


def gated_reading(out: Path):
    """The analysis folder whose reading passed the validation gate, if there is one. That first gated reading is the
    one reported, so the scheduler never writes a second (Fable's closure read of draft 3, 4 November 2026)."""
    for f in sorted(out.glob('analysis*/analysis.json')):
        try:
            if (json.loads(f.read_text()).get('validation') or {}).get('ok'):
                return f.parent
        except (OSError, json.JSONDecodeError):
            continue
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('action', choices=('plan', 'run', 'pause'))
    p.add_argument('root', type=Path)
    p.add_argument('--pilot', action='store_true')
    p.add_argument('--tasks', default=','.join(TASKS))
    p.add_argument('--libraries', type=Path, help='reuse learned libraries from a pilot folder (learn-<task>/run); no learning')
    p.add_argument('--protocol', type=int, choices=(1, 2), default=1)
    p.add_argument('--blocks', type=int, default=BLOCKS, help='second protocol: matched blocks per Study 2 task')
    p.add_argument('--spend-limit', type=float, help='list-price US$ of finished learning runs at which no further '
                   'learning run starts (default: the protocol\'s). Raising it is Simon\'s decision; it is logged, and '
                   'as an argument it leaves the source fingerprint unchanged (Fable\'s review of draft 2).')
    a = p.parse_args(argv)
    out = (ROOT / a.root) if not a.root.is_absolute() else a.root
    tasks = [t for t in a.tasks.split(',') if t]
    runs = range(1) if (a.pilot or a.libraries) else RUNS
    reuse = (ROOT / a.libraries) if a.libraries and not a.libraries.is_absolute() else a.libraries

    if a.protocol == 2:
        return main_2(a, out, tasks, reuse)

    if a.action == 'plan':
        learn = [] if reuse else learning_jobs(out, tasks, runs)
        libs = libraries(out, tasks, runs, reuse) if reuse else {(t, r): out / f'learn-{t}-{r}' / 'run' for t in tasks for r in runs}
        for stage, jobs in (('learning', learn), (f'SITL flights, {len(SCORED_INSTANCES)} at once', flight_jobs(out, tasks, libs)),
                            ('Gazebo, alone', gazebo_jobs(out, libs))):
            print(f'{stage}: {len(jobs)} phases')
            for name, _ in jobs:
                print('  ', name)
        return 0

    if a.action == 'pause':
        (out / 'logs').mkdir(parents=True, exist_ok=True)
        (out / 'logs' / 'PAUSE').write_text(now() + '\n')
        Runner(out, a.pilot).note('pause asked for')
        return 0

    r = Runner(out, a.pilot)
    if (r.logs / 'PAUSE').exists():
        (r.logs / 'PAUSE').unlink()
        r.note('pause removed; resuming')
    r.note(f'begin {"pilot " if a.pilot else ""}run into {out}; tasks {tasks}; instances {SCORED_INSTANCES}')
    if not reuse:
        r.pool(learning_jobs(out, tasks, runs), SCORED_INSTANCES)   # never paused: one window of model use
    libs = libraries(out, tasks, runs, reuse)
    r.note(f'adopted libraries: {len(libs)} of {len(tasks) * len(runs)}')
    r.pausable = True
    r.pool(flight_jobs(out, tasks, libs), SCORED_INSTANCES)
    if not r.pause_marked():
        r.pool(gazebo_jobs(out, libs), [None])
    if r.pause_marked():
        r.note(f'paused; run the same command to continue. Phases needing a decision so far: {r.failed or "none"}')
        return 2
    done = gated_reading(out)
    if done:
        r.note(f'analysis already done: {done.name} passed the gate, and no second reading is written')
        r.note(f'finished; phases needing a decision: {r.failed or "none"}')
        return 1 if r.failed else 0
    dest = analysis_folder(out)
    r.note(f'analysis into {dest.name}')
    with open(r.logs / f'{dest.name}.log', 'w') as log:
        code = subprocess.run([PY[0], str(ROOT / 'protocol' / 'analysis.py'), str(out), '--out', str(dest),
                               '--tasks', ','.join(tasks)] + (['--libraries', str(reuse)] if reuse else [])
                              + (['--include-pilot'] if a.pilot else []),
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
    if code != 0:   # the validation gate failed or the analysis crashed: the report is diagnostic only (A4)
        r.note(f'analysis exited {code}; its report is diagnostic only, see logs/{dest.name}.log')
        r.failed.append('analysis')
    r.note(f'finished; phases needing a decision: {r.failed or "none"}')
    return 1 if r.failed else 0


def jobs_2(out: Path, tasks, blocks, reuse: Path | None, planned=False):
    """The second protocol's flight phases from the adopted libraries (or, when planning, as if every run adopted)."""
    if planned:
        study1 = {(t, f'b{b}-matched' if t in STUDY2_TASKS else b): out / 'planned'
                  for t in tasks for b in (blocks if t in STUDY2_TASKS else [r for r in RUNS if r in blocks])}
        study2 = {(t, b, arm): out / 'planned' for t in tasks if t in STUDY2_TASKS for b in blocks for arm in ARMS}
    else:
        study1, study2 = libraries_2(out, tasks, blocks, reuse)
    # Study 2's evaluation first, its arms interleaved block by block; then Study 1's phases on the calm libraries.
    return study1, study2, study2_jobs(out, study2), flight_jobs(out, tasks, study1), gazebo_jobs(out, study1)


def main_2(a, out: Path, tasks, reuse: Path | None):
    blocks = range(1) if (a.pilot or reuse) else range(a.blocks)
    learn = [] if reuse else learning_jobs_2(out, tasks, blocks)
    if a.action == 'plan':
        _, _, s2, s1, gz = jobs_2(out, tasks, blocks, reuse, planned=True)
        for stage, jobs in (('learning', learn), ('Study 2 evaluation', s2), (f'Study 1 SITL flights', s1),
                            ('Gazebo, alone', gz)):
            print(f'{stage}: {len(jobs)} phases')
            for name, _ in jobs:
                print('  ', name)
        return 0
    if a.action == 'pause':
        (out / 'logs').mkdir(parents=True, exist_ok=True)
        (out / 'logs' / 'PAUSE').write_text(now() + '\n')
        Runner(out, a.pilot).note('pause asked for')
        return 0
    r = Runner(out, a.pilot)
    r.protocol = 2
    r.spend_limit = a.spend_limit
    if (r.logs / 'PAUSE').exists():
        (r.logs / 'PAUSE').unlink()
        r.note('pause removed; resuming')
    r.note(f'begin {"pilot " if a.pilot else ""}run of the second protocol into {out}; tasks {tasks}; '
           f'blocks {len(blocks)}; instances {SCORED_INSTANCES}; spending stop US$'
           f'{a.spend_limit if a.spend_limit is not None else SPEND_LIMIT_USD_2:g}'
           + (' (set by --spend-limit)' if a.spend_limit is not None else ''))
    if learn:
        r.pool(learn, SCORED_INSTANCES)   # never paused: one window of model use
    study1, study2, s2, s1, gz = jobs_2(out, tasks, blocks, reuse)
    r.note(f'adopted: Study 1 libraries {len(study1)}; Study 2 arms '
           f'{sum(v is not None for v in study2.values())} of {len(study2)}')
    r.pausable = True
    r.pool(s2 + s1, SCORED_INSTANCES)
    if not r.pause_marked():
        r.pool(gz, [None])
    if r.pause_marked():
        r.note(f'paused; run the same command to continue. Phases needing a decision so far: {r.failed or "none"}')
        return 2
    done = gated_reading(out)
    if done:
        r.note(f'analysis already done: {done.name} passed the gate, and no second reading is written')
        r.note(f'finished; phases needing a decision: {r.failed or "none"}')
        return 1 if r.failed else 0
    dest = analysis_folder(out)
    r.note(f'analysis into {dest.name}')
    with open(r.logs / f'{dest.name}.log', 'w') as log:
        code = subprocess.run([PY[0], str(ROOT / 'protocol' / 'analysis.py'), str(out), '--out', str(dest),
                               '--tasks', ','.join(tasks), '--protocol', '2', '--blocks', str(len(blocks))]
                              + (['--libraries', str(reuse)] if reuse else [])
                              + (['--include-pilot'] if a.pilot else []),
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
    if code != 0:
        r.note(f'analysis exited {code}; its report is diagnostic only, see logs/{dest.name}.log')
        r.failed.append('analysis')
    r.note(f'finished; phases needing a decision: {r.failed or "none"}')
    return 1 if r.failed else 0


if __name__ == '__main__':
    raise SystemExit(main())

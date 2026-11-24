"""Run the third protocol's phases in order: every learning block, then each block's evaluation flights.

Notes: notes/PROTOCOL3-CONTRACT-C3-20261109.md (phases) and notes/PROTOCOL3-SCHEMA-D3-20261109.md (names and records).
The machinery is protocol 2's scheduler (run_scored.Runner): each phase is one call of `python -m ardupilot.scored`
with its own folder and log, up to four at once on the scored simulator instances; a finished phase is marked
logs/PHASE.done and skipped on a restart; a failed phase, or a folder left without a done mark, is held and listed,
and whether it is rerun is decided by hand under the faults rule, never here.

  .venv/bin/python protocol/run_scored3.py plan ROOT [--pilot]     # list the learning phases
  .venv/bin/python protocol/run_scored3.py run ROOT [--pilot]      # learn, then evaluate
  .venv/bin/python protocol/run_scored3.py run ROOT --pause-at 04:30  # the session asks for its own pause then
  .venv/bin/python protocol/run_scored3.py pause ROOT --reason TEXT  # finish the running phases, start no more
  .venv/bin/python protocol/run_scored3.py run ROOT --reason TEXT    # a later session needs a reason for resuming

Exit status: 0 finished, 1 finished with phases held for a decision, 2 paused, 3 refused to start (see the log).

Learning comes first, block by block, with the three tasks in an order drawn for each block. Learning pauses between
blocks (the owner's ruling in notes/TAKEOVER-20261111.md, "Pausing and resuming"; protocol 2's rule that learning is
never paused does not carry over). A learning phase starts only while the list-price spend of finished learning
blocks, of blocks set aside and of blocks in flight, read from the rows on disk, is below the spending stop; past it,
the phase is held for Simon. The stop is a test made when a block is about to start. Blocks already in flight go on
spending after it trips, and the stop counts list price, below what the gateway charges. Evaluation follows,
planned from the finished blocks' arms.json and candidate records (contract3.source_roles): every distinct adopted
source, and c0 even if no arm adopted it, flies the 24 hazard scenarios (threat3); every adopted source flies the 10
ordinary ones (retain3). A pause takes effect between phases, in learning and in evaluation. On the Mac, before each phase
starts, the scheduler waits until the one-minute load average is at or below the calibrated limit
(scored.LOAD_LIMIT_1MIN). The phase's own guard (scored.load_check) looks again and, if the load is above the limit, waits
too, each minute with no upper bound; it does not refuse. Before each flight the phase waits the same way
(scored.flight_gate). On the cluster no phase or flight waits for the load, which is recorded only. Phases are launched at least START_SPACING_S apart, the timing
preflight's spacing, and a phase that waited for the load is released the same way, one at a time, so that phases
never start together after a wait (notes/TAKEOVER-20261111.md, round two, ruling 2, and the review's finding 7).
"""
import argparse
import datetime
import json
import os
import random
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'protocol'))
import run_scored as R  # noqa: E402
from ardupilot import scored as S  # noqa: E402
from protocol import contract3 as C  # noqa: E402
from protocol import set_aside3 as SA  # noqa: E402
from protocol import timing_preflight3 as TP  # noqa: E402

ORDER_SEED = 20261113        # the task order within each learning block
# Simon, 9 November 2026: "the cost is fine". The forecast for 96 blocks is about US$14 to US$40 at list price; the
# stop is set above it so that only a run far outside the forecast waits for him.
# Ruling 88, 19 November 2026: N = 40 blocks a task, 120 blocks in all. The forecast is about US$35 charged (US$0.29 a block), inside
# ruling 39's US$40; each task's job takes about 29 hours. The three US$20 stops are unchanged.
# Simon, 11 November 2026, 4:20 pm, asked for "a yes to a US$4 development sample, a yes to the scored spend, and the
# quiet Mac": "yes to all 3". Relayed by the coordinating session (notes/TAKEOVER-20261111.md). The stop is unchanged.
SPEND_LIMIT_USD_3 = 60.0
LOAD_WAIT_S = 60
# The timing preflight starts its four workers a quarter of a second apart, the decision period over the four
# instances (timing_preflight3.stage), and the scored run keeps that spacing (round two, ruling 2).
START_SPACING_S = TP.DECISION_PERIOD_S / len(TP.INSTANCES)
_clock, _pause = time.monotonic, time.sleep     # replaced in tests


def task_order(block: int) -> list:
    tasks = list(C.TASKS)
    random.Random(f'{ORDER_SEED}/learn/{block}').shuffle(tasks)
    return tasks


def learning_jobs(out: Path, blocks, extra=(), tasks=None) -> list:
    """The learning phases in the order they are taken. tasks, when given, keeps only those tasks' blocks, in the order
    task_order draws for the whole set, so that one task's run on its own node takes its blocks as it would have in the
    one run of all three (ruling 52)."""
    jobs = []
    for b in blocks:
        for t in task_order(b):
            if tasks is not None and t not in tasks:
                continue
            name = C.phase_name('learn3', t, b)
            jobs.append((name, ['learn3', '--task', t, '--block', str(b), '--out', str(out / name), *extra]))
    return jobs


def evaluation_jobs(out: Path, done) -> list:
    """From each finished learning block: threat3 for every source it must fly, retain3 for adopted ones."""
    jobs = []
    for learn in done:
        arms = json.loads((learn / 'arms.json').read_text())
        candidates = {p.parent.name: json.loads(p.read_text()) for p in (learn / 'candidates').glob('*/candidate.json')}
        task, block = arms['task'], arms['block']
        for source, role in sorted(C.source_roles(arms['arms'], candidates, include_c0=True).items()):
            common = ['--task', task, '--block', str(block), '--learning', str(learn), '--source', source]
            name = C.phase_name('threat3', task, block, source)
            jobs.append((name, ['threat3', *common, '--out', str(out / name)]))
            if role['arms']:
                name = C.phase_name('retain3', task, block, source)
                jobs.append((name, ['retain3', *common, '--out', str(out / name)]))
    return jobs


def _usage_cost(usage: Path):
    """(US$ listed, calls without a list cost) in one usage.jsonl. A block in flight may be writing the file as it is
    read, so a final fragment with no newline after it is a row being written and is skipped. Only that. A last line
    that ends with a newline is a finished row and must parse, as must every earlier line (ruling 39, point 3; build F4,
    ruling 45, point 4). The file's text is read, not its split lines, to tell the two apart."""
    total, unknown = 0.0, 0
    text = usage.read_text() if usage.exists() else ''
    lines = text.split('\n')
    # Split on newline: the last piece is '' after a finished row, or the fragment of a row being written.
    fragment = lines.pop()
    rows = [json.loads(line) for line in lines]
    if fragment.strip():
        try:
            rows.append(json.loads(fragment))
        except ValueError:
            pass
    for row in rows:
        if row.get('list_cost_usd') is None:
            unknown += 1
        else:
            total += row['list_cost_usd']
    return total, unknown


def held_folders(out: Path, jobs) -> list:
    """Scheduled phases whose folder exists without a done mark. A phase that finished has the mark, so these are
    phases that crashed, were killed or failed in an earlier session."""
    held = []
    for name, args in jobs:
        folder = Path(args[args.index('--out') + 1])
        if folder.exists() and not (out / 'logs' / f'{name}.done').exists():
            held.append(name)
    return held


class Runner3(R.Runner):
    protocol = 3

    def __init__(self, out: Path, pilot: bool):
        super().__init__(out, pilot)
        self.in_flight = set()      # phases whose process is running now
        self.launch_lock = threading.Lock()
        self.last_launch = None     # monotonic time of the last launch or release
        self.pause_at = None        # (wall-clock time, HH:MM) of a timed pause, if run was given --pause-at
        self.at_once = 4            # phases flown at once (--at-once); a semaphore of this size gates `one`
        self.slots = threading.Semaphore(4)

    def space_launch(self):
        """Hold a phase until START_SPACING_S has passed since the last one was launched. Each waiting phase reads the
        load on its own; only this step is shared, so phases that waited for the load leave one at a time."""
        with self.launch_lock:
            if self.last_launch is not None:
                wait = self.last_launch + START_SPACING_S - _clock()
                if wait > 0:
                    _pause(wait)
            self.last_launch = _clock()

    def spent_usd(self) -> float:
        """List-price cost of every learning block, from its usage.jsonl: blocks with a done mark, blocks that stopped on
        a fault and have no mark, blocks set aside, and blocks in flight (ruling 39, point 3). A block in flight counts
        the rows it has written so far, and a last row that is half written is skipped (_usage_cost). Unknown costs
        count as zero and are reported. The folders are on disk, so the sum covers the whole run and not one session.
        A block that stopped on a fault has already made its calls, so it counts at once and not only when it is set
        aside (TAKEOVER-20261111.md, rulings of 11 November, item 2). The sum is a figure at the moment it is read:
        calls a block in flight has not yet logged are not in it, so the stop still lets those through.
        Every call the provider logged has a row in usage.jsonl, a copy and a call that ended in a fault included, because
        the ladder writes the row before it raises (ladder.Block._receipt, build F2). So this sum counts each call once."""
        total, unknown = 0.0, 0
        sources = [f / 'usage.jsonl' for f in sorted(self.out.glob('learn3-*')) if f.is_dir()]
        sources += sorted(SA.set_aside_dir(self.out).glob('learn3-*-attempt*/learn3-*/usage.jsonl'))
        for usage in sources:
            t, u = _usage_cost(usage)
            total, unknown = total + t, unknown + u
        if unknown:
            self.note(f'{unknown} finished model calls have no list cost; counted as US$0')
        return round(total, 4)

    def event(self, kind: str, reason=None, **more):
        """One line in logs/pauses.jsonl for each start, pause asked for, pause taking effect and resume, with the
        time and the reason ("Each pause and resume is logged with its time and reason", TAKEOVER-20261111.md,
        "Pausing and resuming")."""
        row = {'time': R.now(), 'event': kind, 'reason': reason, **more}
        with self.lock:
            with open(self.logs / 'pauses.jsonl', 'a') as f:
                f.write(json.dumps(row) + '\n')

    def events(self) -> list:
        path = self.logs / 'pauses.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def pause_asked(self):
        """(time, reason) from the marker file, or None. The file holds the time, then the reason."""
        f = self.logs / 'PAUSE'
        if not f.exists():
            return None
        lines = (f.read_text().splitlines() + ['', ''])[:2]
        return lines[0], lines[1].removeprefix('reason: ') or 'no reason recorded'

    def timed_pause_due(self, name) -> bool:
        """True, with the pause asked for, once the wall clock has passed the --pause-at time. Read before each phase
        starts, because the timer's clock stops while the Mac sleeps and the wall clock does not."""
        if not (self.pausable and self.pause_at and time.time() >= self.pause_at[0]):
            return False
        if not (self.logs / 'PAUSE').exists():
            ask_pause(self, self.out, f'timed pause at {self.pause_at[1]}, set when this session started (ruling 5)')
        with self.lock:
            self.paused = True
        self.note(f'{name} not started: the timed pause at {self.pause_at[1]} is due')
        return True

    def set_at_once(self, n: int):
        self.at_once = n
        self.slots = threading.Semaphore(n)

    def one(self, name, args, instance):
        # The slot is taken first, so the pause, spend and load checks below run at the moment the phase really starts.
        with self.slots:
            self.one_in_slot(name, args, instance)

    def one_in_slot(self, name, args, instance):
        args = list(args) + ['--at-once', str(self.at_once)]
        if not (self.logs / f'{name}.done').exists():
            if self.pausable and (self.logs / 'PAUSE').exists():
                # A pause asked while this phase waited for a slot: the pool looked for it before the phase was taken.
                with self.lock:
                    self.paused = True
                self.note(f'{name} not started: pause asked while it waited for a slot')
                return
            if self.timed_pause_due(name):
                return
            if args[0] == 'learn3':
                limit = self.spend_limit if self.spend_limit is not None else SPEND_LIMIT_USD_3
                spent = self.spent_usd()
                if spent >= limit:
                    self.note(f'HOLD {name}: learning blocks have cost US${spent} so far, counting blocks in flight, '
                              f'at or past the US${limit:g} stop; not started, decision for Simon')
                    with self.lock:
                        self.failed.append(name)
                    return
            if S.LOAD_LIMIT_1MIN is not None and not S.is_cluster():     # no load wait on the cluster
                waited = False
                while os.getloadavg()[0] > S.LOAD_LIMIT_1MIN:
                    if self.timed_pause_due(name):
                        return
                    if self.pausable and (self.logs / 'PAUSE').exists():
                        # Not started, so no block is split. A resume plans it again from the done marks.
                        with self.lock:
                            self.paused = True
                        self.note(f'{name} not started: pause asked while it waited for the load to fall')
                        return
                    if not waited:
                        self.note(f'{name} waits: one-minute load {os.getloadavg()[0]:.1f} is above '
                                  f'{S.LOAD_LIMIT_1MIN}')
                        waited = True
                    time.sleep(LOAD_WAIT_S)
            self.space_launch()
        with self.lock:
            self.in_flight.add(name)
        try:
            super().one(name, args, instance)
        finally:
            with self.lock:
                self.in_flight.discard(name)


def seconds_until(clock: str, now=None) -> float:
    """Seconds from now to the next local time clock (HH:MM): today if it is still ahead, else tomorrow."""
    now = now or datetime.datetime.now().astimezone()
    hour, minute = (int(x) for x in clock.split(':'))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f'not a time of day: {clock}')
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


def ask_pause(r: Runner3, out: Path, reason: str):
    """Write the pause marker and log it. The pause command and the timed pause both come here."""
    (out / 'logs').mkdir(parents=True, exist_ok=True)
    (out / 'logs' / 'PAUSE').write_text(f'{R.now()}\nreason: {reason}\n')
    r.note(f'pause asked for: {reason}')
    r.event('pause_asked', reason)


def timed_pause(r: Runner3, out: Path, clock: str) -> threading.Timer:
    """Ask for a pause at the local time clock from inside the scheduler, so no command has to be typed while flights
    are in the air (round three, ruling 5, after the code review's finding 5, 13 November 2026). The timer only sleeps;
    it ends with the scheduler. A pause already asked for is left as it is."""
    def fire():
        if not (out / 'logs' / 'PAUSE').exists():
            ask_pause(r, out, f'timed pause at {clock}, set when this session started (ruling 5)')
    t = threading.Timer(seconds_until(clock), fire)
    t.daemon = True
    t.start()
    return t


def refuse(r: Runner3, why: str) -> int:
    r.note(f'REFUSED: {why}')
    return 3


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('action', choices=('plan', 'run', 'pause'))
    p.add_argument('root', type=Path)
    p.add_argument('--pilot', action='store_true', help='development blocks and evaluation seeds (seeds-3 pilot book)')
    p.add_argument('--blocks', type=int, help='learning blocks per task (default: all in the seed book)')
    p.add_argument('--tasks', help='a comma-separated subset of the tasks this root flies (default: all three); the scored '
                   'run flies one task to a root, each on its own node (ruling 52)')
    p.add_argument('--spend-limit', type=float, help='raising the stop is Simon\'s decision; it is logged')
    p.add_argument('--reason', help='pause: why (required). run: why this session resumes an earlier one (required '
                   'when there was an earlier session). Neither may come from the study\'s outcomes.')
    p.add_argument('--stub', choices=S.STUB_CHOICES, help='pilot only: scripted replies, no model calls')
    p.add_argument('--at-once', type=int, default=4, help='run: phases flown at once, 1 to 4 (default 4); the scheduler '
                   'keeps its four workers and instances, and a semaphore of this size holds the rest back')
    p.add_argument('--record-late-flights', action='store_true', help='pilot only: learning records late flights')
    p.add_argument('--speedup', type=float, help='pilot only: simulator speed-up (scored phases fly in real time)')
    p.add_argument('--pause-at', metavar='HH:MM', help='run: ask for a pause at this local time (the next one to come); '
                   'phases flying then finish and no new phase starts')
    a = p.parse_args(argv)
    if a.pause_at:
        seconds_until(a.pause_at)                 # refuses a malformed time before anything starts
    out = (ROOT / a.root) if not a.root.is_absolute() else a.root
    S.use_protocol(3)
    book = C.book(S.seeds(), a.pilot)
    available = min(len(book['blocks'][t]) for t in C.TASKS)
    blocks = range(a.blocks if a.blocks is not None else available)
    if len(blocks) > available:
        raise SystemExit(f'the seed book has {available} blocks per task')
    if (a.stub or a.record_late_flights or a.speedup) and not a.pilot:
        raise SystemExit('--stub, --record-late-flights and --speedup are for pilots only')
    extra = (['--stub', a.stub] if a.stub else []) + (['--record-late-flights'] if a.record_late_flights else [])
    fast = ['--speedup', str(a.speedup)] if a.speedup else []
    tasks = list(C.TASKS) if a.tasks is None else [t for t in a.tasks.split(',') if t]
    if not tasks or len(set(tasks)) != len(tasks) or any(t not in C.TASKS for t in tasks):
        raise SystemExit(f'--tasks must name tasks from {list(C.TASKS)}, each once')
    tasks = [t for t in C.TASKS if t in tasks]
    learn = learning_jobs(out, blocks, extra + fast, tasks)
    if a.action == 'plan':
        print(f'learning: {len(learn)} phases')
        for name, _ in learn:
            print('  ', name)
        print('evaluation: planned from the finished learning blocks')
        return 0
    if a.action == 'pause':
        # A pause is asked for by writing a marker file in the run's logs folder, the mechanism protocol 2 uses. The
        # scheduler reads it before it takes each phase, so it takes effect at a phase boundary only.
        if not a.reason:
            raise SystemExit('a pause needs --reason')
        (out / 'logs').mkdir(parents=True, exist_ok=True)
        ask_pause(Runner3(out, a.pilot), out, a.reason)
        return 0
    r = Runner3(out, a.pilot)
    r.spend_limit = a.spend_limit
    if not S.AT_ONCE_RANGE[0] <= a.at_once <= S.AT_ONCE_RANGE[1]:
        return refuse(r, f'--at-once must be from {S.AT_ONCE_RANGE[0]} to {S.AT_ONCE_RANGE[1]}, not {a.at_once}')
    r.set_at_once(a.at_once)
    why = S.start_refusal(a.at_once)     # nice 0 on both platforms; on the cluster, 3 cores for each simulator at once
    if why:
        return refuse(r, why)
    # One scheduler at a time on a root, or two could start the same block.
    running = r.logs / 'RUNNING'
    if SA.scheduler_alive(out):
        return refuse(r, f'another scheduler is running on this root ({running.read_text().strip()})')
    # The schedule is fixed at the first start. A later session with other blocks or flags would change the run.
    schedule = {'pilot': a.pilot, 'at_once': a.at_once, 'tasks': tasks, 'learning': [[n, args] for n, args in learn]}
    sched_file = r.logs / 'schedule.json'
    first = json.loads(sched_file.read_text()) if sched_file.exists() else None
    if first is not None:
        first.setdefault('at_once', 4)          # written before --at-once existed: 4
        first.setdefault('tasks', list(C.TASKS))  # written before --tasks existed: all three
        if first['at_once'] != a.at_once:
            return refuse(r, f'--at-once {a.at_once} differs from the {first["at_once"]} fixed at the first start; '
                             f'one run root flies at one number of simulators at once')
    if first is not None and first != schedule:
        return refuse(r, 'the learning schedule (blocks, flags, order) differs from the one fixed at the first start')
    earlier = any(e['event'] == 'start' for e in r.events())
    if earlier and not a.reason:
        return refuse(r, 'an earlier session exists; give --reason for resuming')
    # A killed or crashed session leaves a folder without a done mark. The phase may be half-written, so it is not
    # treated as finished and it is not rerun here (PROTOCOL-2.md section 7: the owner moves it aside by hand with
    # set_aside3.py, and the rerun uses the same name and seeds). Nothing starts until that is done.
    held = held_folders(out, learn)
    if held:
        return refuse(r, f'learning folders without a done mark: {held}; decide each by hand (set_aside3.py) first')
    sched_file.write_text(json.dumps(schedule, indent=1) + '\n')
    running.write_text(f'{os.getpid()} {R.now()} {socket.gethostname()}\n')
    try:
        a.tasks_flown = tasks
        return run_session(r, a, out, learn, blocks, fast, earlier)
    finally:
        running.unlink(missing_ok=True)


def run_session(r: Runner3, a, out: Path, learn, blocks, fast, earlier) -> int:
    asked = r.pause_asked()
    if asked:
        (r.logs / 'PAUSE').unlink()
        r.note(f'pause removed (asked {asked[0]}: {asked[1]}); resuming')
    cluster = S.is_cluster()
    if cluster and getattr(a, 'pause_at', None):
        r.note(f'--pause-at {a.pause_at} ignored: the timed pause is off on the cluster (ruling 7); '
               f'`pause` still works')
        a.pause_at = None
    r.event('resume' if earlier else 'start', a.reason, pause_cleared=asked[1] if asked else None,
            pause_at=getattr(a, 'pause_at', None), platform=S.platform_record(),
            spend_limit_usd=a.spend_limit if a.spend_limit is not None else SPEND_LIMIT_USD_3,
            spend_limit_from_flag=a.spend_limit is not None, tasks=list(getattr(a, 'tasks_flown', C.TASKS)))
    if getattr(a, 'pause_at', None):
        r.pause_at = (time.time() + seconds_until(a.pause_at), a.pause_at)
        timed_pause(r, out, a.pause_at)
        r.note(f'a pause will be asked for at {a.pause_at}')
    r.note(f'begin {"pilot " if a.pilot else ""}run of the third protocol into {out}; tasks '
           f'{",".join(getattr(a, "tasks_flown", C.TASKS))}; blocks {len(blocks)} per task; '
           f'instances {S.SCORED_INSTANCES}, {r.at_once} at once; spending stop US$'
           f'{a.spend_limit if a.spend_limit is not None else SPEND_LIMIT_USD_3:g}'
           + (' (set by --spend-limit)' if a.spend_limit is not None else '')
           + f'; load limit {None if cluster else S.LOAD_LIMIT_1MIN}; platform {S.platform_name()}'
           + (f'; resuming: {a.reason}' if earlier else ''))
    r.pausable = True
    r.pool(learn, S.SCORED_INSTANCES)          # pauses between blocks
    if r.pause_marked():
        return stopped(r, 'learning')
    done = [out / name for name, _ in learn if (r.logs / f'{name}.done').exists()]
    missing = [name for name, _ in learn if not (r.logs / f'{name}.done').exists()]
    if missing:
        # A missing learning block is a fault, never a non-adoption (D3's schema).
        r.note(f'learning blocks without a done mark, held: {missing}')
    evaluate = [(name, args + fast) for name, args in evaluation_jobs(out, done)]
    held = held_folders(out, evaluate)
    if held:
        return refuse(r, f'evaluation folders without a done mark: {held}; decide each by hand (set_aside3.py) first')
    r.note(f'evaluation: {len(evaluate)} phases from {len(done)} finished blocks')
    r.pool(evaluate, S.SCORED_INSTANCES)
    if r.pause_marked():
        return stopped(r, 'evaluation')
    r.note(f'finished; phases needing a decision: {r.failed or "none"}')
    return 1 if r.failed else 0


def stopped(r: Runner3, stage: str) -> int:
    asked = r.pause_asked()
    reason = asked[1] if asked else 'no reason recorded'
    r.event('paused', reason, stage=stage)
    r.note(f'paused in {stage} ({reason}); run the same command with --reason to continue. '
           f'Phases needing a decision so far: {r.failed or "none"}')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

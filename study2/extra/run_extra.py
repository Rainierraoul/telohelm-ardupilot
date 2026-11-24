"""The scheduler of Paper 3's extra experiment (PROTOCOL-EXTRA.md), one run root at a time.

  python extra/run_extra.py arm-e ROOT --task reach --study2 S2ROOT --seen-ids F... --spend-limit 4.33 --control
  python extra/run_extra.py arm-e ROOT --task reach --study2 S2ROOT --spend-limit 0.01 --pilot --blocks 1,4,7 --control
  python extra/run_extra.py yard ROOT DEVROOT
  ... --resume REASON      a later session on the same root, after a job ended early

Study 2's scheduler does the work (protocol/run_scored3.Runner3): one worker for each of the four scored simulator
instances, a done mark for each finished phase, a phase that fails held and listed, and the spending stop tested before
each learning block starts, from the usage rows on disk. Each phase is one process of `python -m extra.phase`.

arm-e: the blocks of one task's arm E (learnE, extra/arm_e.py), then, in one pool, the zone evaluation (Study 2's
threat3 phase, unchanged) of every source arm E adopted that Study 2 did not fly in that block and, with --control, the
platform control: Study 2's zone evaluation of arm C's adopted source in the first two blocks of the task where arm C
adopted one, flown again (PROTOCOL-EXTRA.md, section 6). A threat3 folder in ROOT whose name is also in Study 2's root is
a control phase; any other is arm E's. S2ROOT is Study 2's saved run root for the task, read and never written. At the
first start, ROOT/message-ids.jsonl is filled with the message ids of every reply Study 2 accepted (--seen-ids, one file
for each task), so a reply that repeats one of them stops its block as a fault.

Once a learning block has failed or been held for the spending stop, no further block starts in that session; the
finished blocks are evaluated and the run exits 1, for a decision by hand. A refused key then costs one block's calls,
not a hundred.

yard: the yardstick's development flights (the pilot book, into DEVROOT), the choice of margin for each task from them,
written to ROOT/yard-choice.json before any scored flight, then the scored flights of all five margins into ROOT.

A held phase is settled as Study 2's job did it (cluster/scored.sbatch, sched): an evaluation phase held for a late
flight is set aside by protocol/set_aside3.py's own function and flown again, at most twice, and the phase keeps its
third attempt itself. Anything else held ends the run with exit 1. With --resume, before anything starts, each phase
folder without a done mark is set aside by the same rule a resumed Study 2 job used (phase_kind3: late or crashed; a
learning block is always crashed), at most twice for each phase, and the session goes on from the done marks.
"""
import argparse
import json
import math
import os
import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'protocol'))
import run_scored as R  # noqa: E402
from ardupilot import scored as S  # noqa: E402
from protocol import contract3 as C3  # noqa: E402
from protocol import phase_kind3 as PK  # noqa: E402
from protocol import run_scored3 as R3  # noqa: E402
from protocol import set_aside3 as SA  # noqa: E402
from extra import yardstick as Y  # noqa: E402

R.PY = [str(ROOT / '.venv' / 'bin' / 'python'), '-u', '-m', 'extra.phase']
# set_aside3's function, with arm E's and the yardstick's phase names added to the names it accepts. Only in this process.
SA.PHASE_PATTERN = re.compile(SA.PHASE_PATTERN.pattern[:-2] + r'|learnE-[a-z0-9]+-b\d+|yard3-[a-z0-9]+-m\d)$')
PROTOCOL_EXTRA = ROOT / 'PROTOCOL-EXTRA.md'
CONTROL_BLOCKS = 2
MAX_ASIDE = 2


class RunnerE(R3.Runner3):
    def __init__(self, out: Path, pilot: bool, spend_limit: float = math.inf):
        super().__init__(out, pilot)
        self.spend_limit = spend_limit

    def spent_usd(self) -> float:
        """List-price cost of arm E's calls, from the usage rows of every learnE block of this root, finished, in flight,
        stopped or set aside, as Runner3.spent_usd counts Study 2's blocks."""
        total, unknown = 0.0, 0
        sources = [f / 'usage.jsonl' for f in sorted(self.out.glob('learnE-*')) if f.is_dir()]
        sources += sorted(SA.set_aside_dir(self.out).glob('learnE-*-attempt*/learnE-*/usage.jsonl'))
        for usage in sources:
            t, u = R3._usage_cost(usage)
            total, unknown = total + t, unknown + u
        if unknown:
            self.note(f'{unknown} finished model calls have no list cost; counted as US$0')
        return round(total, 4)

    def one_in_slot(self, name, args, instance):
        if args[0] == 'learnE' and not (self.logs / f'{name}.done').exists():
            with self.lock:
                earlier = [n for n in self.failed if n.startswith('learnE-')]
            if earlier:
                self.note(f'HOLD {name}: not started, because {earlier[0]} failed or was held in this session')
                with self.lock:
                    self.failed.append(name)
                return
            spent = self.spent_usd()
            if spent >= self.spend_limit:
                self.note(f'HOLD {name}: arm E has cost US${spent} at list so far, counting blocks in flight, at or '
                          f'past the US${self.spend_limit:g} stop; not started')
                with self.lock:
                    self.failed.append(name)
                return
        super().one_in_slot(name, args, instance)


def out_of(args) -> Path:
    return Path(args[args.index('--out') + 1])


def late_held(out: Path) -> bool:
    """phase_kind3's rule (a timing row late and not kept), which it applies to threat3 and retain3 names only."""
    if out.name.startswith('yard3-'):
        rows = json.loads((out / 'timing.json').read_text()) if (out / 'timing.json').exists() else None
        return isinstance(rows, list) and any(r.get('late') is True and r.get('kept_late') is not True for r in rows)
    return PK.kind(out.parent, out.name) == 'late'


def aside_count(out: Path, reason: str) -> int:
    n = 0
    for folder in SA.set_aside_dir(out.parent).glob(f'{out.name}-attempt*'):
        try:
            receipt = json.loads((folder / 'receipt.json').read_text())
        except (OSError, ValueError):
            continue
        n += receipt.get('phase') == out.name and receipt.get('reason') == reason
    return n


def aside(r: RunnerE, out: Path, reason: str, note: str) -> None:
    """set_aside3's function on one phase of this root. It refuses while a scheduler marker names the root; Study 2's
    scheduler had exited when its job set phases aside, and this one has finished its pool, so no phase is flying, and
    its marker is lifted for the set-aside and put back."""
    marker = r.logs / 'RUNNING'
    text = marker.read_text() if marker.exists() else None
    if text is not None:
        marker.unlink()
    try:
        SA.set_aside(out.parent, out.name, reason, note)
    finally:
        if text is not None:
            marker.write_text(text)
    r.note(f'set aside {out.name} ({reason}): {note}')


def settle(r: RunnerE, jobs) -> list:
    """Run the jobs, then set aside and fly again the phases held for a late flight. Returns the phases that need a
    decision by hand (empty when every phase finished)."""
    r.pool(jobs, S.SCORED_INSTANCES)
    by_name = dict(jobs)
    while r.failed:
        held, r.failed = list(r.failed), []
        log = (r.logs / 'scheduler.log').read_text()
        again, stop = [], []
        for name in held:
            args = by_name[name]
            out = out_of(args)
            failed_line = [line for line in log.splitlines() if f'FAILED {name} on instance' in line]
            if not out.exists() or (failed_line and '(exit 4)' in failed_line[-1]) or not late_held(out):
                stop.append(name)
                continue
            n = aside_count(out, 'late')
            if n >= MAX_ASIDE:
                stop.append(name)
                continue
            aside(r, out, 'late', f'held after a late flight; late number {n + 1}')
            again.append((name, args))
        if stop:
            r.note(f'phases needing a decision by hand: {stop}')
            return stop
        r.pool(again, S.SCORED_INSTANCES)
    return []


def resume(r: RunnerE, jobs, reason: str) -> str | None:
    """Before a resumed session starts: each scheduled phase folder without a done mark is set aside by phase_kind3's
    rule, at most MAX_ASIDE times for each phase and reason. All are classified before any is moved. Returns a refusal
    or None."""
    plan = []
    for name, args in jobs:
        out = out_of(args)
        if not out.exists() or (r.logs / f'{name}.done').exists():
            continue
        kind = 'late' if late_held(out) else 'crashed'
        if aside_count(out, kind) >= MAX_ASIDE:
            return f'{name} has been set aside {MAX_ASIDE} times already for reason {kind}'
        plan.append((out, kind))
    for out, kind in plan:
        aside(r, out, kind, f'resumed session: {reason}')
    return None


def start(r: RunnerE, schedule: dict, pilot: bool, jobs, resumed: str | None) -> str | None:
    """The checks of run_scored3.main before a session: the platform, one scheduler on the root, a schedule fixed at the
    first start, and no phase folder left without a done mark unless the session is a resume. Returns a refusal or None."""
    S.use_protocol(3)
    frozen = json.loads((ROOT / 'protocol' / 'FROZEN-3.json').read_text())
    if S.source_fingerprint() != frozen['source_fingerprint']:
        return f'the source fingerprint {S.source_fingerprint()} is not the frozen {frozen["source_fingerprint"]}'
    if S.sha256(S.SEEDS) != frozen['seeds_sha256']:
        return 'the seed book is not the frozen one'
    if not pilot and not PROTOCOL_EXTRA.exists():
        return 'PROTOCOL-EXTRA.md is missing'
    why = S.start_refusal(4)
    if why:
        return why
    if SA.scheduler_alive(r.out):
        return f'another scheduler is running on this root ({(r.logs / "RUNNING").read_text().strip()})'
    sched = r.logs / 'schedule.json'
    if sched.exists() and json.loads(sched.read_text()) != schedule:
        return 'the schedule differs from the one fixed at the first start'
    if sched.exists() and not resumed:
        return 'an earlier session exists; give --resume with the reason'
    if resumed:
        why = resume(r, jobs, resumed)
        if why:
            return why
    held = R3.held_folders(r.out, jobs)
    if held:
        return f'phase folders without a done mark: {held}'
    sched.write_text(json.dumps(schedule, indent=1) + '\n')
    return None


def control_jobs(task: str, study2: Path, root: Path) -> list:
    """Arm C's adopted source in the first CONTROL_BLOCKS blocks of the task where arm C adopted one, read from arms.json
    alone: the rule never looks at an outcome."""
    jobs = []
    for block in range(len(S.seeds()['blocks'][task])):
        learn = study2 / f'learn3-{task}-b{block}'
        row = json.loads((learn / 'arms.json').read_text())['arms']['C']
        if not row['adopted']:
            continue
        name = C3.phase_name('threat3', task, block, row['source_sha256'])
        jobs.append((name, ['threat3', '--task', task, '--block', str(block), '--learning', str(learn),
                            '--source', row['source_sha256'], '--out', str(root / name)]))
        if len(jobs) == CONTROL_BLOCKS:
            return jobs
    return jobs


def evaluation_jobs(task: str, root: Path, study2: Path, done: list) -> list:
    """threat3 for each source arm E adopted that Study 2 did not fly in the same block (its folder and done mark)."""
    jobs = []
    for learn in done:
        arms = json.loads((learn / 'arms.json').read_text())
        e = arms['arms']['E']
        if not e['adopted']:
            continue
        name = C3.phase_name('threat3', task, arms['block'], e['source_sha256'])
        if (study2 / name).is_dir() and (study2 / 'logs' / f'{name}.done').exists():
            continue
        jobs.append((name, ['threat3', '--task', task, '--block', str(arms['block']), '--learning', str(learn),
                            '--source', e['source_sha256'], '--out', str(root / name)]))
    return jobs


class running:
    """The scheduler's marker in ROOT/logs/RUNNING for the length of a session, as run_scored3 writes it."""

    def __init__(self, r: RunnerE):
        self.marker = r.logs / 'RUNNING'

    def __enter__(self):
        self.marker.write_text(f'{os.getpid()} {R.now()} {socket.gethostname()}\n')

    def __exit__(self, *exc):
        self.marker.unlink(missing_ok=True)


def run_arm_e(a) -> int:
    root = a.root.resolve()
    r = RunnerE(root, a.pilot, a.spend_limit)
    blocks = ([int(b) for b in a.blocks.split(',')] if a.blocks else list(range(len(S.seeds()['blocks'][a.task]))))
    study2 = a.study2.resolve()
    learn = []
    for b in blocks:
        name = f'learnE-{a.task}-b{b}'
        learn.append((name, ['learnE', '--task', a.task, '--block', str(b), '--saved',
                             str(study2 / f'learn3-{a.task}-b{b}'), '--out', str(root / name)]))
    control = control_jobs(a.task, study2, root) if a.control else []
    schedule = {'action': 'arm-e', 'task': a.task, 'pilot': a.pilot, 'study2': str(study2),
                'learning': [[n, x] for n, x in learn], 'control': [[n, x] for n, x in control]}
    # Evaluation phases are planned from the finished blocks, so a resume classifies the folders of all of them.
    planned_eval = evaluation_jobs(a.task, root, study2, [root / n for n, _ in learn if (r.logs / f'{n}.done').exists()])
    why = start(r, schedule, a.pilot, learn + planned_eval + control, a.resume)
    if why:
        r.note(f'REFUSED: {why}')
        return 3
    ids = root / 'message-ids.jsonl'
    if not ids.exists():
        seen = []
        for f in a.seen_ids:
            seen += [line for line in Path(f).read_text().splitlines() if line.strip()]
        ids.write_text(''.join(line + '\n' for line in seen))
        r.note(f'message-ids.jsonl started with the {len(seen)} reply ids Study 2 accepted ({len(a.seen_ids)} files)')
    with running(r):
        r.note(f'arm E for {a.task}: {len(learn)} blocks; spending stop US${a.spend_limit:g} at list (this session); '
               f'{"rehearsal (scripted replies)" if a.pilot else "scored"}; platform {S.platform_name()}'
               + (f'; resumed: {a.resume}' if a.resume else ''))
        held_learning = settle(r, learn)
        done = [root / n for n, _ in learn if (r.logs / f'{n}.done').exists()]
        # The control phases go first, so that they fly beside arm E's phases, four at once, as Study 2's did.
        jobs = control + evaluation_jobs(a.task, root, study2, done)
        r.note(f'evaluation: {len(jobs)} phases ({len(control)} control) from {len(done)} finished blocks; '
               f'arm E has cost US${r.spent_usd()} at list')
        held = settle(r, jobs)
        r.note(f'finished; learning blocks needing a decision: {held_learning or "none"}; evaluation phases needing a '
               f'decision: {held or "none"}; arm E cost US${r.spent_usd()} at list')
    return 1 if held or held_learning else 0


def choose_margins(dev: Path) -> dict:
    """PROTOCOL-EXTRA.md, section 7: for each task, the margin under which the most development flights met the goal;
    a tie goes to the larger margin."""
    choice = {}
    for task in Y.TASKS:
        met, n = {}, len(Y.development_cases(S.seeds(), task))
        for m in Y.MARGINS_M:
            flights = sorted((dev / f'yard3-{task}-m{m}' / 'flights').glob('*/outcome.json'))
            if len(flights) != n:
                raise SystemExit(f'yard3-{task}-m{m}: {len(flights)} development flights, not {n}')
            met[m] = sum(bool(json.loads(f.read_text())['goal_met']) for f in flights)
        best = max(met.values())
        choice[task] = {'margin_m': max(m for m in Y.MARGINS_M if met[m] == best), 'goal_met_by_margin': met,
                        'flights_per_margin': n}
    return choice


def run_yard(a) -> int:
    dev_root, root = a.dev.resolve(), a.root.resolve()
    jobs = lambda base: [(f'yard3-{t}-m{m}', ['yard3', '--task', t, '--margin', str(m), '--out',
                                              str(base / f'yard3-{t}-m{m}')]) for t in Y.TASKS for m in Y.MARGINS_M]
    dev = RunnerE(dev_root, True)
    pick = root / 'yard-choice.json'
    if not pick.exists():
        why = start(dev, {'action': 'yard-development', 'jobs': jobs(dev_root)}, True, jobs(dev_root), a.resume)
        if why:
            dev.note(f'REFUSED: {why}')
            return 3
        with running(dev):
            held = settle(dev, jobs(dev_root))
        if held:
            return 1
    scored = RunnerE(root, a.pilot)
    why = start(scored, {'action': 'yard', 'pilot': a.pilot, 'jobs': jobs(root)}, a.pilot, jobs(root),
                a.resume if (root / 'logs' / 'schedule.json').exists() else None)
    if why:
        scored.note(f'REFUSED: {why}')
        return 3
    if not pick.exists():
        pick.write_text(json.dumps(choose_margins(dev_root), indent=1) + '\n')
    scored.note(f'margins chosen on the development flights: {json.dumps(json.loads(pick.read_text()))}')
    with running(scored):
        held = settle(scored, jobs(root))
        scored.note(f'finished; phases needing a decision: {held or "none"}')
    return 1 if held else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='action', required=True)
    q = sub.add_parser('arm-e')
    q.add_argument('root', type=Path)
    q.add_argument('--task', choices=C3.TASKS, required=True)
    q.add_argument('--study2', type=Path, required=True, help="Study 2's run root for the task")
    q.add_argument('--seen-ids', nargs='*', default=[], help="Study 2's message-ids.jsonl files")
    q.add_argument('--spend-limit', type=float, required=True)
    q.add_argument('--control', action='store_true')
    q.add_argument('--pilot', action='store_true', help='a rehearsal: scripted replies, pilot evaluation flights')
    q.add_argument('--blocks', help='a comma-separated list of blocks (rehearsals only)')
    q.add_argument('--resume', metavar='REASON', help='a later session on the same root, and why')
    q = sub.add_parser('yard')
    q.add_argument('root', type=Path)
    q.add_argument('dev', type=Path)
    q.add_argument('--pilot', action='store_true', help='a rehearsal: the scored stage flies the pilot book too')
    q.add_argument('--resume', metavar='REASON', help='a later session on the same roots, and why')
    a = p.parse_args(argv)
    S.use_protocol(3)
    if a.action == 'arm-e':
        if a.blocks and not a.pilot:
            raise SystemExit('--blocks is for rehearsals; a scored run flies every block')
        if not a.pilot and not a.seen_ids:
            raise SystemExit("a scored run needs Study 2's message ids (--seen-ids)")
        return run_arm_e(a)
    return run_yard(a)


if __name__ == '__main__':
    raise SystemExit(main())

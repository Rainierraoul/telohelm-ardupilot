"""One worker of one pass of the planner check (design sections 5, 6 and 7).

A pass is every pair of a setting and an evaluation scenario, flown once. Four workers fly it at once, one on each of
simulator instances 10 to 13. This file flies one worker's share. With --shakedown it flies the development evaluation
cases instead, to check the machinery.

Run from paper3/, for example:
  .venv/bin/python -B -m planner_check.fly --pass 1 --worker 0 --out runs/planner-check-DATE/pass1/worker0

The evaluation seeds are scored seeds. Like the study's own scored phases, a flight of them is refused unless
PROTOCOL-3.md exists. The shake-down flies development seeds and needs no such file. --out must have a folder named
planner-check-* on its path, so that nothing can be written into a scored run's root.

It makes no model call. It refuses a seed that is not in the seed book's evaluation list for the cohort it flies, refuses
any seed from 5000 to 5099, and refuses to write into a folder that already exists.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from ardupilot import ladder, pack as P, scored
from ardupilot.battle import generate
from ardupilot.vehicle import ARDUPILOT
from protocol import contract3 as C3
from telohelm.runtime.trusted_log import TrustedLog

from . import episode as E, settings as S

WORKERS = len(C3.FLIGHT_INSTANCES)          # four workers, one on each of instances 10 to 13
ATTEMPTS = ladder.REFLIGHTS + 1             # a flight that faults is flown again at the end of the list, three attempts in all
EXCLUDED_SEEDS = range(5000, 5100)          # seeds the study keeps for itself; this check never flies them
HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Item:
    """One flight of the check: a setting on one scenario."""
    setting: int
    task: str
    band: str
    seed: int

    @property
    def name(self) -> str:
        return f'{self.task}-s{self.setting}-threat-{self.band}-{self.seed}'


def evaluation_seeds(book: dict, pilot: bool) -> dict:
    """The seed book's evaluation list for the cohort, {task: {band: [seeds]}}."""
    return C3.book(book, pilot)['threat_evaluation']


def allowed_seeds(book: dict, pilot: bool) -> set:
    rows = evaluation_seeds(book, pilot)
    return {seed for task in C3.TASKS for band in C3.BANDS for seed in rows[task][band]}


def refuse_unlisted(item: Item, allowed: set) -> None:
    if item.seed in EXCLUDED_SEEDS:
        raise SystemExit(f'seed {item.seed} is one of the reserved seeds 5000 to 5099; the planner check never flies them')
    if item.seed not in allowed:
        raise SystemExit(f'seed {item.seed} is not in the evaluation list of the cohort being flown')


def flight_list(book: dict, pilot: bool, pass_number: int) -> list:
    """Every pair of a setting and an evaluation scenario, sorted by task (in the protocol's order), band (close, middle,
    wide), seed and setting. The second pass is the same list in reverse order, so that a drift in the node's speed over
    a job falls on different settings in the two passes."""
    rows = evaluation_seeds(book, pilot)
    items = [Item(s.number, task, band, seed) for task in C3.TASKS for band in C3.BANDS
             for seed in sorted(rows[task][band]) for s in S.SETTINGS]
    if pass_number not in (1, 2):
        raise ValueError('the check flies two passes, 1 and 2')
    return items if pass_number == 1 else items[::-1]


def worker_items(items: list, worker: int) -> list:
    """Worker k of four flies items k, k + 4, k + 8 and so on."""
    if not 0 <= worker < WORKERS:
        raise ValueError(f'worker must be 0 to {WORKERS - 1}')
    return items[worker::WORKERS]


def scenario(item: Item):
    return generate(item.task, 'threat', item.seed, gap_stratum=item.band)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str) + '\n')


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def own_files() -> dict:
    """The SHA-256 of each of the check's own files, for the manifest."""
    return {p.name: _sha(p) for p in sorted(HERE.iterdir()) if p.suffix in ('.py', '.sbatch')}


def _ardupilot_commit():
    try:
        return subprocess.run(['git', '-C', str(ARDUPILOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def refuse_unless_frozen(pilot: bool) -> dict:
    """The study's rule for scored seeds (scored.guard): the evaluation seeds fly only once the protocol is frozen, which
    is when PROTOCOL-3.md exists. Returns the file's SHA-256 and the commit for the manifest; the shake-down returns None."""
    if pilot:
        return {'frozen_protocol': None}
    scored.use_protocol(3)       # a fresh process starts on protocol 1, whose PROTOCOL.md exists
    if not scored.PROTOCOL.exists():
        raise SystemExit(f'{scored.PROTOCOL.name} does not exist: the evaluation seeds are scored seeds and fly only after '
                         'the freeze. Fly the shake-down (--shakedown) instead.')
    try:
        commit = scored.git_state().get('commit')
    except Exception:
        commit = None
    return {'frozen_protocol': scored.PROTOCOL.name, 'frozen_protocol_sha256': _sha(scored.PROTOCOL), 'commit': commit}


def refuse_out_outside_planner_check(out: Path) -> None:
    if not any(part.startswith('planner-check-') for part in Path(out).resolve().parts):
        raise SystemExit(f'--out {out} has no folder named planner-check-* on its path; nothing is written')


def fly_one(item: Item, out: Path, attempt: int, route: str = 'midflight') -> dict:
    """Fly one flight into out/flights/<name>/ and return its row. Raises on a fault, leaving the folder for the caller to
    set aside."""
    sc = scenario(item)
    setting = S.setting(item.setting)
    folder = out / 'flights' / item.name
    if folder.exists():
        raise FileExistsError(f'{folder} exists; records are never overwritten')
    folder.mkdir(parents=True)
    ep = E.PlannerEpisode(sc, setting, out / 'defaults' / f'setting-{setting.number}.parm', route)
    log = TrustedLog(folder / 'episode.log', folder / 'episode.heads', 'planner-check')
    outcome = None
    try:
        ep.reset()
        while ep.end_reason is None:
            ep.step({})
            st = ep.native_steps[-1]
            log.append({'kind': 'step', 't': st['t'], 'mode': st['mode'], 'stage': ep.stage,
                        'truth': {k: st[k] for k in ('north_m', 'east_m', 'alt_m')}})
        outcome = ep.outcome()
        log.append({'kind': 'episode_end', 'episode': sc.episode_id, 'goal_met': outcome['goal_met'],
                    'end_reason': outcome['end_reason'], 'settled': True})
    finally:
        if outcome is None:
            try:
                ep.outcome()          # closes the simulator; no result is written for a flight that faulted
            except Exception:
                pass
        log.close()
    _write(folder / 'outcome.json', outcome)       # the outcome first: reading the log can fail, and must not undo a flight
    planner = {'setting': setting.number, 'task': item.task, 'band': item.band, 'seed': item.seed,
               'episode_id': sc.episode_id, 'attempt': attempt, 'route': route, 'read_back': ep.sim.read_back_values,
               'read_back_absent': ep.sim.read_back_absent, 'target': ep.target_sent, 'uploads': ep.uploads,
               'preload': ep.sim.preload_record, 'fence_enabled': ep.sim.fence_enabled_record,
               'planner_rows': E.planner_rows(Path(ep.folder)), 'timing': ladder.timing(outcome)}
    _write(folder / 'planner.json', planner)
    return {'status': 'flown', 'goal_met': outcome['goal_met'], 'end_reason': outcome['end_reason']}


def fly_worker(out: Path, pass_number: int, worker: int, *, pilot: bool, speedup: float,
               route: str = 'midflight') -> dict:
    refuse_out_outside_planner_check(out)
    scored.use_protocol(3)
    frozen = refuse_unless_frozen(pilot)
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f'{out} exists; records are never overwritten')
    book = scored.seeds()
    items = worker_items(flight_list(book, pilot, pass_number), worker)
    allowed = allowed_seeds(book, pilot)
    for item in items:
        refuse_unlisted(item, allowed)
    instance = C3.FLIGHT_INSTANCES[worker]
    out.mkdir(parents=True)
    hashes = {f'setting-{s.number}.parm': S.write_defaults(s, out / 'defaults' / f'setting-{s.number}.parm', route == 'preloaded')
              for s in S.SETTINGS}
    _write(out / 'manifest.json', {
        'what': 'planner check, one worker of one pass', 'pass': pass_number, 'worker': worker, 'instance': instance,
        'cohort': 'development (shake-down)' if pilot else 'evaluation', 'route': route, **frozen, 'speedup': speedup,
        'command_delay_periods': ladder.COMMAND_DELAY_PERIODS, 'ardupilot_commit': _ardupilot_commit(),
        'settings': [{'number': s.number, 'oa_type': s.oa_type, 'oa_margin_max_m': s.margin_m,
                      'oa_br_lookahead_m': s.lookahead_m, 'label': s.label} for s in S.SETTINGS],
        'defaults_sha256': hashes, 'seed_book': str(scored.SEEDS.name), 'seed_book_sha256': _sha(scored.SEEDS),
        'scored_build_fingerprint': scored.source_fingerprint(), 'own_files_sha256': own_files(),
        'node': platform.node(), 'job': os.environ.get('SLURM_JOB_ID'),
        'started': datetime.datetime.now().astimezone().isoformat(),
        'order': [i.name for i in items]})
    # The study's own warm-up flight, which is not a flight of the check: the first flight of a process takes the
    # start-up effect on the clock. It flies a development case of the task of this worker's first flight.
    task = items[0].task
    ladder.fly_warmup(out, task, scored.warmup_case(C3, book, task), speedup=speedup, instance=instance)
    P.HOST.update(root=out, speedup=speedup, gcs=False, instance=instance, keep_simulators=True,
                  command_delay_periods=ladder.COMMAND_DELAY_PERIODS)
    queue, tries, rows = list(items), {}, []
    while queue:
        item = queue.pop(0)
        tries[item.name] = attempt = tries.get(item.name, 0) + 1
        row = {'pass': pass_number, 'worker': worker, 'setting': item.setting, 'task': item.task, 'band': item.band,
               'seed': item.seed, 'name': item.name, 'attempt': attempt}
        try:
            row.update(fly_one(item, out, attempt, route))
        except Exception as e:      # a fault: the flight stopped without an outcome
            aside = out / 'faults' / f'{item.name}-attempt-{attempt}'
            aside.parent.mkdir(parents=True, exist_ok=True)
            folder = out / 'flights' / item.name
            if folder.exists():
                folder.rename(aside)
            _write(aside / 'fault.json', {'item': item.name, 'attempt': attempt, 'error': f'{type(e).__name__}: {e}'})
            row.update(status='fault', error=f'{type(e).__name__}: {e}')
            if attempt < ATTEMPTS:
                queue.append(item)       # flown again at the end of this worker's list
        rows.append(row)
        with open(out / 'results.jsonl', 'a') as f:
            f.write(json.dumps(row) + '\n')
        print(f"{item.name}: {row.get('end_reason', row.get('error'))} (attempt {attempt})", flush=True)
    return {'flights': len(items), 'rows': len(rows)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--pass', dest='pass_number', type=int, choices=(1, 2), required=True)
    p.add_argument('--worker', type=int, choices=range(WORKERS), required=True,
                   help='0 to 3; it flies on simulator instance 10 to 13')
    p.add_argument('--out', type=Path, required=True, help="this worker's own new folder")
    p.add_argument('--shakedown', action='store_true', help='fly the development evaluation cases (one pass only)')
    p.add_argument('--preloaded-fence', action='store_true',
                   help="the fallback of design section 4: load the zone before take-off with the fence off, switch it on at the moment")
    p.add_argument('--speedup', type=float, default=1.0)
    a = p.parse_args(argv)
    if a.shakedown and a.pass_number != 1:
        p.error('the shake-down flies one pass')
    fly_worker(a.out, a.pass_number, a.worker, pilot=a.shakedown, speedup=a.speedup,
               route='preloaded' if a.preloaded_fence else 'midflight')
    return 0


if __name__ == '__main__':
    sys.exit(main())

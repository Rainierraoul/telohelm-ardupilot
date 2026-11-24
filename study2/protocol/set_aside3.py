"""Set a held protocol-3 phase aside: move its folder and its log out of the run root and write the receipt.

  .venv/bin/python protocol/set_aside3.py ROOT PHASE --reason late      # a flight in the phase was late
  .venv/bin/python protocol/set_aside3.py ROOT PHASE --reason crashed   # the phase crashed or was killed

Rulings: notes/TAKEOVER-20261111.md, "Replacing a late flight" (the unit is the whole phase; the owner's tool reads
the timing fields only, writes the receipt, and moves the folder and its log out of the run root as
protocol/PROTOCOL-2.md section 7 does for a crashed phase; the phase is then run again under its scheduled name with
the same seeds, and a learning block makes new model calls; both attempts are listed in the paper).

The decision to set a phase aside must not depend on how the phase turned out. So for a late phase the tool opens
timing.json first and copies only the named timing fields of each row into the receipt (TIMING_FIELDS).
It never opens an outcome file, a flight record or the phase log, and it does not read model cost: the scheduler reads
the cost of set-aside learning blocks itself, so that their calls stay in the spend (run_scored3.Runner3.spent_usd).
A crashed phase is set aside without reading its outcome or flight files, and from its timing.json only the late flag of each row, to refuse a phase that was late (use --reason late); it is set aside only with evidence that it crashed
(crash_evidence): either logs/scheduler.log records a failed exit for the phase ("FAILED NAME on instance N (exit CODE)",
which run_scored.py writes), or no scheduler is running on the root and the log has the phase's last "start NAME" line with
no "end NAME" and no FAILED line after it (a job killed by its time limit or a lost node). Without one of the two the tool
refuses, so a phase cannot be removed as crashed on someone's say-so. The receipt names the kind of evidence and copies the
log lines read. The tool refuses a phase that has a done mark, so a phase that finished cannot be removed after its result is known. It also refuses while a scheduler is running on the root,
and while any process still names the phase's folder: if a scheduler was killed, the phases it started may still be
flying, and their folders must not be moved under them (TAKEOVER-20261111.md, rulings of 11 November, item 3).

For a phase of either reason it then opens, only where the phase has one, sandbox-end.json, which is the route's
record (the calls made and the holders replaced) and holds no outcome, flight record or model cost. If it holds a
replacement that the gate refuses (one whose reason is neither 'stopped' nor 'residue', or whose spent holder had died;
refused_replacements), the phase is not set aside, because it would be flown again to be refused by the gate again, and
the tool prints the replacement and stops, as it does for its other refusals. A phase with no such replacement, or with no
sandbox-end.json, is set aside as before, and the receipt is the same (a crashed phase's receipt also has its evidence). A sandbox-end.json that cannot be read is refused. On a cluster phase (the manifest's platform, as the gate reads it) one that
is not an object, names no route or another route than the expected one, or has no list of replacements is refused too,
as the gate refuses it; the gate reads nothing of the file off the cluster. To judge that route record the tool then
opens the phase's manifest.json, where there is one, for its platform, and only when there is a sandbox-end.json. So the
files a phase's receipt lists as read (files_read) are, for a crashed phase, logs/scheduler.log first; then, for a late
phase, timing.json; then, for either, sandbox-end.json where there is one, then manifest.json where there is both a route
record and a manifest, in the order opened. A crashed phase opens no outcome or flight file; it opens timing.json, where there is one, to see that no flight in it is late, and lists it after the scheduler log.

The folders go to ROOT.set-aside/PHASE-attemptN, beside the run root and not inside it, because the gate flags any
folder in the run root that is not scheduled.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# Run as a script (protocol/set_aside3.py), sys.path[0] is protocol/, so paper3/ is put on the path for the imports of
# ardupilot in processes_naming, as the other protocol scripts do.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The only fields of a timing.json row that are read. Anything else in the row is dropped without being looked at.
TIMING_FIELDS = ('flight', 'median_lag_s', 'max_lag_s', 'late_share_0_1s', 'step_median_lag_s', 'late',
                 'command_delay_s', 'max_own_lag_s', 'observations_late', 'missed_deadlines', 'off_deadline_commands')
# the fields ardupilot/ladder.py timing() writes: step_median_lag_s from 12 November 2026, the rest with the fixed delay
# (round four), so that a receipt says why a flight was late. All are timing fields.
REASONS = ('late', 'crashed')    # the reasons a receipt may name
PHASE_PATTERN = re.compile(r'^(learn3-[a-z0-9]+-b\d+|(threat3|retain3)-[a-z0-9]+-b\d+-[0-9a-f]{64})$')


def set_aside_dir(root: Path) -> Path:
    root = Path(root)
    return root.parent / f'{root.name}.set-aside'


def is_evaluation(phase: str) -> bool:
    """True for an evaluation phase (threat3 or retain3), False for a learning block (learn3)."""
    return phase.startswith(('threat3-', 'retain3-'))


def now() -> str:
    return datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')


def scheduler_alive(root: Path) -> bool:
    """True when logs/RUNNING names a live process (written by run_scored3 for the length of a session)."""
    marker = Path(root) / 'logs' / 'RUNNING'
    if not marker.exists():
        return False
    try:
        fields = marker.read_text().split()
        pid = int(fields[0])
    except (OSError, ValueError, IndexError):
        return False
    # The marker is 'pid date time host'. A run root on a shared disk may be written from another node, where this
    # process table says nothing about that pid, so a marker from another host counts as alive (older markers have no host).
    if len(fields) >= 4 and fields[3] != socket.gethostname():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def processes_naming(folder: Path) -> list:
    """Running processes, other than this one, whose command line names the folder: a phase still flying, or one of
    its simulators. Each is given as 'pid command'."""
    names = {str(Path(folder)), str(Path(folder).resolve())}
    if os.environ.get('PAPER3_PLATFORM') == 'cluster':      # this user's processes only (ruling 7)
        from ardupilot import scored as S
        uid = os.getuid()
        out = S.own_processes(subprocess.run(['ps', '-u', str(uid), '-o', 'uid=,pid=,args='], capture_output=True,
                                             text=True).stdout, uid)
    else:
        out = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(' ')
        if pid.isdigit() and int(pid) != os.getpid() and any(n in cmd for n in names):
            found.append(f'{pid} {cmd[:160]}')
    return found


def read_timing(path: Path) -> list:
    """The timing rows of a phase, cut down to TIMING_FIELDS. This is the only read of a phase's contents."""
    return read_timing_and_hash(path)[0]


def read_timing_and_hash(path: Path) -> tuple:
    """The timing rows, cut down to TIMING_FIELDS, and the SHA-256 of the file they came from, from one read."""
    raw = Path(path).read_bytes()
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f'{path} is not a list of timing rows')
    kept = []
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit(f'{path} has a row that is not an object')
        kept.append({k: row[k] for k in TIMING_FIELDS if k in row})
    for row in kept:
        if not isinstance(row.get('late'), bool):
            raise SystemExit(f'{path} has a row without a true or false "late"; nothing is set aside')
    return kept, hashlib.sha256(raw).hexdigest()


def refused_replacements(end) -> list:
    """The replacements in a sandbox-end.json that the gate refuses: one that is not a mapping, whose spent holder had died,
    or whose reason is neither 'stopped' nor 'residue'. This is the rule of scored.write_route_end and of the gate's
    check_route in validate3.py, written out here because neither is a function this tool can call; a test runs
    scored.write_route_end on the same replacements and compares, so that the copies cannot drift apart unseen."""
    replacements = end.get('replacements') if isinstance(end, dict) else None
    if not isinstance(replacements, list):
        return []        # the shape is route_end_problem's to judge, and only on the cluster
    return [r for r in replacements if not isinstance(r, dict) or r.get('holder_died')
            or r.get('reason') not in ('stopped', 'residue')]


def phase_platform(manifest: Path) -> str:
    """'cluster' or 'mac', decided as validate3.Run.check_route decides it: a manifest with no platform record is a Mac
    one. A manifest that is missing is taken the same way; one that cannot be read stops the tool, since the platform
    is then unknown."""
    if not manifest.exists():
        return 'mac'
    try:
        m = json.loads(manifest.read_text())
    except ValueError as error:
        raise SystemExit(f'{manifest} cannot be read ({error}); the platform of the phase is not known, so it is not set aside')
    plat = m.get('platform') if isinstance(m, dict) else None
    return 'mac' if plat is None else (plat.get('platform') if isinstance(plat, dict) else None)


def route_end_problem(end, platform) -> str | None:
    """Why a sandbox-end.json is refused by the gate's check_route (validate3.py), or None. The gate asks nothing of it off
    the cluster. On the cluster it must be an object that names the cluster's expected route and holds a list of
    replacements. (The route the gate compares with is the manifest's, which it has already required to be the expected
    one.)"""
    if platform != 'cluster':
        return None
    from ardupilot import scored as S
    if not isinstance(end, dict):
        return 'is not an object'
    if end.get('route') != S.EXPECTED_ROUTE['cluster']:
        return f"names the route {end.get('route')!r}, not {S.EXPECTED_ROUTE['cluster']!r}"
    if not isinstance(end.get('replacements'), list):
        return 'has no list of replacements'
    return None


def crash_evidence(root: Path, phase: str) -> dict:
    """The proof that a phase crashed, read from logs/scheduler.log, or a refusal. Only the lines after the phase's last
    'start NAME on instance' line count, so an earlier attempt's lines prove nothing about this one.
      failed_exit          a 'FAILED NAME on instance N (exit CODE)' line follows the start (run_scored.py writes it)
      no_scheduler_no_end  no scheduler runs on the root, and nothing follows the start that ends the phase: no 'end NAME'
                           line and no FAILED line (a job killed by its time limit, or a lost node)
    Returns {'kind', 'log_lines'}: the start line and the line that settles the case, as written."""
    log = Path(root) / 'logs' / 'scheduler.log'
    if not log.exists():
        raise SystemExit(f'{log} is missing, so there is no evidence that {phase} crashed; it is not set aside')
    lines = log.read_text().splitlines()
    start = re.compile(rf'^\S+ \S+ start {re.escape(phase)} on instance ')
    starts = [i for i, line in enumerate(lines) if start.match(line)]
    if not starts:
        raise SystemExit(f'{log} has no "start {phase}" line, so there is no evidence that it crashed; it is not set aside')
    first = starts[-1]
    after = lines[first + 1:]
    failed = [line for line in after if re.match(rf'^\S+ \S+ FAILED {re.escape(phase)} on instance \S+ \(exit -?\d+\)', line)]
    if failed:
        return {'kind': 'failed_exit', 'log_lines': [lines[first], failed[0]]}
    ended = [line for line in after if re.match(rf'^\S+ \S+ (end|FAILED) {re.escape(phase)} on instance ', line)]
    if ended:
        raise SystemExit(f'{log} has a later line for {phase} that is not a failed exit ({ended[0]!r}), so there is no '
                         f'evidence that it crashed; it is not set aside')
    if scheduler_alive(root):
        raise SystemExit(f'a scheduler may still be running on this root, so a start with no end in the log is not a '
                         f'crash; {phase} is not set aside')
    return {'kind': 'no_scheduler_no_end', 'log_lines': [lines[first]]}


def set_aside(root: Path, phase: str, reason: str, note: str = '') -> Path:
    root = Path(root)
    logs = root / 'logs'
    if not PHASE_PATTERN.match(phase):
        raise SystemExit(f'{phase!r} is not a protocol-3 phase name')
    if reason not in REASONS:
        raise SystemExit('the reason is late or crashed')
    if scheduler_alive(root):
        raise SystemExit('a scheduler is running on this root; pause it and let it stop first')
    folder = root / phase
    if not folder.is_dir():
        raise SystemExit(f'{folder} does not exist')
    if (logs / f'{phase}.done').exists():
        raise SystemExit(f'{phase} has a done mark; a finished phase is not set aside')
    alive = processes_naming(folder)
    if alive:
        raise SystemExit(f'{phase} is still in use by a running process; let it end first: {alive[:3]}')
    rows, files_read, timing_sha256, evidence = [], [], None, None
    if reason == 'crashed':
        # A held late phase leaves the same failed-exit line in the scheduler log as a crash. So a phase whose timing.json
        # records a late flight is never set aside as crashed: that would take the attempt out of the count of late
        # attempts (ruling 45, point 3). Only the late flag of each row is looked at. A timing.json that is not a list of
        # rows, as a crash in the middle of writing it would leave, records no late flight.
        # This holds for an evaluation phase only, and only for a late row the driver did not keep. A learning block
        # flies a late call again inside the block and leaves the late attempt's rows in its timing.json, so a block that
        # later stops on a fault has late rows and is still a crash; and an evaluation phase whose third attempt was kept
        # late (its late rows marked kept_late) and whose job then died before the done mark is a crash too (ruling 52).
        timing = folder / 'timing.json'
        if timing.exists() and is_evaluation(phase):
            try:
                found = json.loads(timing.read_bytes())
            except ValueError:
                found = None
            if isinstance(found, list) and any(isinstance(r, dict) and r.get('late') is True
                                               and r.get('kept_late') is not True for r in found):
                raise SystemExit(f'{timing} records a late flight, so {phase} is not a crash; use --reason late')
        evidence = crash_evidence(root, phase)
        files_read.append(str(logs / 'scheduler.log'))
        if timing.exists():
            files_read.append(str(timing))
    if reason == 'late':
        timing = folder / 'timing.json'
        if not timing.exists():
            raise SystemExit(f'{timing} is missing; there is no timing evidence (use --reason crashed for a crash)')
        files_read.append(str(timing))
        rows, timing_sha256 = read_timing_and_hash(timing)
        if not any(r['late'] for r in rows):
            raise SystemExit(f'no flight in {phase} is recorded late; nothing is set aside')
    route_end = folder / 'sandbox-end.json'
    if route_end.exists():
        files_read.append(str(route_end))
        try:
            end = json.loads(route_end.read_text())
        except ValueError as error:
            raise SystemExit(f'{route_end} cannot be read ({error}); {phase} is not set aside')
        # The gate reads the file on a cluster phase only, so the platform is read from the phase's manifest as the gate
        # reads it. A phase with no manifest is taken as the gate takes one with no platform, a Mac phase.
        manifest = folder / 'manifest.json'
        if manifest.exists():
            files_read.append(str(manifest))      # phase_platform opens it next; files_read is in the order opened
        problem = route_end_problem(end, phase_platform(manifest))
        if problem:
            raise SystemExit(f'{route_end} {problem}, which the gate refuses; {phase} is not set aside')
        bad = refused_replacements(end) if isinstance(end, dict) else []
        if bad:
            raise SystemExit(f'{phase} is not set aside: a sandbox holder was replaced for a reason the gate refuses (not '
                             f'stopped or residue, or the spent holder had died), so flying it again would be refused '
                             f'again: {bad[:3]}')
    base = set_aside_dir(root)
    n = 1
    while (base / f'{phase}-attempt{n}').exists():
        n += 1
    dest = base / f'{phase}-attempt{n}'
    dest.mkdir(parents=True)
    shutil.move(str(folder), str(dest / phase))
    log = logs / f'{phase}.log'
    log_moved = log.exists()
    if log_moved:
        shutil.move(str(log), str(dest / f'{phase}.log'))
    receipt = {'phase': phase, 'attempt': n, 'reason': reason, 'note': note, 'time': now(),
               'moved_from': str(folder), 'moved_to': str(dest / phase), 'log_moved': log_moved,
               'files_read': files_read, 'timing_sha256': timing_sha256,
               'timing_fields_read': list(TIMING_FIELDS) if rows else [],
               'outcome_fields_read': False, 'crash_evidence': evidence,
               'late_flights': [r.get('flight') for r in rows if r['late']], 'timing_rows': rows}
    (dest / 'receipt.json').write_text(json.dumps(receipt, indent=1) + '\n')
    with open(logs / 'scheduler.log', 'a') as f:
        f.write(f'{now()} set aside {phase} ({reason}) to {dest}; receipt written\n')
    return dest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('root', type=Path)
    p.add_argument('phase')
    p.add_argument('--reason', choices=REASONS, required=True)
    p.add_argument('--note', default='', help='free text for the receipt, such as what was seen in the scheduler log')
    a = p.parse_args(argv)
    print(set_aside(a.root, a.phase, a.reason, a.note))
    return 0


if __name__ == '__main__':
    sys.exit(main())

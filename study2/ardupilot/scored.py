"""Paper 3's scored runner: a thin driver over demo.run, battle.run and the course runners (PROTOCOL.md).

Before any phase it checks that the Telohelm core imported here is byte-identical to the Paper 3 build of the wheel
(WHEEL: paper 2's scored wheel with the sandbox's Linux route changed, built by protocol/wheel3/build_wheel3.py) and
has its version, that no other simulator is running on the machine, and that the reserved seeds file is present. It then
writes manifest.json in the phase's output folder: protocol and seeds hashes, git commit and uncommitted files, the
core check, the speed-up, and the phase's arguments. Records under it are the ordinary hash-chained records of the
runners it calls.

--pilot uses the development pilot seeds and marks the learning model's records unreportable. Nothing from a pilot
is reported.

Run from paper3/:
  .venv/bin/python -m ardupilot.scored check
  .venv/bin/python -m ardupilot.scored learn --task reach --run 0 --out runs/scored/learn-reach-0
  .venv/bin/python -m ardupilot.scored heldout --task reach --library runs/scored/learn-reach-0 --out ...
  .venv/bin/python -m ardupilot.scored heldout --task reach --reference --out ...      (or --hold)
  .venv/bin/python -m ardupilot.scored repeat --task reach --library ... --out ...
  .venv/bin/python -m ardupilot.scored disturb --task reach --library ... --out ...
  .venv/bin/python -m ardupilot.scored courses --kind flat --library runs/scored/learn-reach-0 --out ...
  .venv/bin/python -m ardupilot.scored splits --library runs/scored/learn-reach3d-0 --flights 5 --out ...
  .venv/bin/python -m ardupilot.scored gazebo --library runs/scored/learn-reach3d-0 --flights 3 --out ...

The third protocol (notes/PROTOCOL3-CONTRACT-C3-20261109.md) has three phases of its own:
  .venv/bin/python -m ardupilot.scored learn3 --protocol 3 --task reach --block 0 --out runs/scored-3/learn3-reach-b0
  .venv/bin/python -m ardupilot.scored threat3 --protocol 3 --task reach --block 0 --learning runs/.../learn3-reach-b0 \
      --source SHA256 --out runs/scored-3/threat3-reach-b0-SHA256                      (retain3 the same)
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform as _platform
import socket
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
# The Paper 3 build of the telohelm wheel (notes/TAKEOVER-20261111.md, round five, ruling 19). The wheel Paper 3 shipped
# before it, protocol/telohelm-0.1.0.dev0-py3-none-any.whl, stays in protocol/ as the build's input; every record flown
# before this change names it.
WHEEL = ROOT / 'protocol' / 'telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl'
WHEEL_SHA256 = '36d36b86028643cdec9c3bbc5c90b6e6abe5dcdf31e5877367c38df995ab34b5'
WHEEL_VERSION = '0.1.0.dev0+paper3.2'
WHEEL_BUILD_RECORD = ROOT / 'protocol' / 'wheel3' / 'WHEEL3.json'
# The sandbox route each platform's records must name (notes/TAKEOVER-20261111.md, round five, B2). They are written out
# here and not read from the installed package, so that a package from the old wheel cannot satisfy them.
EXPECTED_ROUTE = {'cluster': 'netns-per-process+keyring-per-call/2', 'mac': 'sandbox-exec'}
SEEDS = ROOT / 'protocol' / 'seeds.json'
PROTOCOL = ROOT / 'PROTOCOL.md'               # the frozen protocol, written at the freeze; scored runs need it
PROTOCOL_DRAFT = ROOT / 'PROTOCOL-DRAFT.md'   # what a pilot records when nothing is frozen yet
PROTOCOL_VERSION = 1
# The second protocol (4 November 2026) has its own seeds and protocol files; the first protocol's stay as frozen.
VERSIONS = {1: ('seeds.json', 'PROTOCOL.md', 'PROTOCOL-DRAFT.md'),
            2: ('seeds-2.json', 'PROTOCOL-2.md', 'PROTOCOL-2-DRAFT.md'),
            3: ('seeds-3.json', 'PROTOCOL-3.md', 'PROTOCOL-3-DRAFT.md')}
STUDY2_TASKS = ('reach', 'reach3d', 'land')
# The scripted reply sets a third-protocol pilot may use (ladder.PILOT_STUBS): 'pilot' passes every path once,
# 'adopt' lets arms adopt so that the evaluation of an adopted source is exercised.
STUB_CHOICES = ('pilot', 'adopt')


def use_protocol(version: int):
    """Point the runner at one protocol's seeds and protocol files."""
    global SEEDS, PROTOCOL, PROTOCOL_DRAFT, PROTOCOL_VERSION
    seeds, protocol, draft = VERSIONS[version]
    SEEDS, PROTOCOL, PROTOCOL_DRAFT = ROOT / 'protocol' / seeds, ROOT / protocol, ROOT / draft
    PROTOCOL_VERSION = version
GEM_MODEL = 'bedrock/au.anthropic.claude-sonnet-5-5'
GATE_RADIUS_M = 1.0


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wheel_version(z: zipfile.ZipFile) -> str | None:
    """The Version line of the wheel's own METADATA."""
    for name in z.namelist():
        if name.endswith('.dist-info/METADATA'):
            for line in z.read(name).decode().splitlines():
                if line.startswith('Version: '):
                    return line[len('Version: '):].strip()
    return None


def core_check() -> dict:
    """The imported telohelm package against the scored wheel (WHEEL, the Paper 3 build), file by file (Python sources
    and package data), and the installed version against the wheel's. A package installed from the wheel Paper 3
    shipped before fails it on telohelm/runtime/sandbox.py and on the version. The record names the wheel, its version
    and its SHA-256."""
    import importlib.metadata
    import telohelm
    pkg = Path(telohelm.__file__).resolve().parent
    named = {'wheel': WHEEL.name, 'wheel_version': WHEEL_VERSION, 'wheel_sha256': WHEEL_SHA256}
    if sha256(WHEEL) != WHEEL_SHA256:
        return {'ok': False, 'reason': f'{WHEEL.name} has a different SHA-256 from the one this code names', **named}
    mismatched, missing = [], []
    with zipfile.ZipFile(WHEEL) as z:
        in_metadata = wheel_version(z)
        names = [n for n in z.namelist() if n.startswith('telohelm/') and not n.endswith('/')]
        for n in names:
            local = pkg / n[len('telohelm/'):]
            if not local.exists():
                missing.append(n)
            elif local.read_bytes() != z.read(n):
                mismatched.append(n)
        in_wheel = {n[len('telohelm/'):] for n in names}
    extra = sorted(str(p.relative_to(pkg)) for p in pkg.rglob('*.py') if '__pycache__' not in p.parts
                   and str(p.relative_to(pkg)) not in in_wheel)
    # The version is read from the metadata folder that sits beside the imported package.
    dists = list(importlib.metadata.distributions(name='telohelm', path=[str(pkg.parent)]))
    installed = dists[0].version if dists else None
    version_ok = installed is not None and installed == in_metadata == WHEEL_VERSION
    ok = not (mismatched or missing or extra) and version_ok
    return {'ok': ok, **named, 'installed_version': installed, 'version_in_wheel_metadata': in_metadata,
            'version_ok': version_ok, 'package_dir': str(pkg), 'files_compared': len(names),
            'mismatched': mismatched, 'missing': missing, 'extra_py': extra}


# Scored SITL flights may run up to four at once, each on its own simulator instance (ports 5760 + 10 x instance and
# up). On 2 November 2026 two, four and seven simulators flying together (protocol/parallel_lag.py, runs/pilot-par*)
# gave the same step counts as one alone on every flight and no rise in decision lag; an eighth, on instance 14, could
# not start because its port 5900 is the Mac's screen sharing. Gazebo flights run alone.
SCORED_INSTANCES = (10, 11, 12, 13)


# The platform is named, never guessed (notes/TAKEOVER-20261111.md, round four, ruling 7). PAPER3_PLATFORM is 'mac' or
# 'cluster'. Unset on macOS it means 'mac'; unset on Linux, or any other value, is a refusal. On 'cluster' the Mac's
# machine rules are off (the load limit, the power source, the quiet-Mac hours and the timed pause), because the batch
# system gives a job cores of its own and a node's load average counts other users' jobs.
PLATFORMS = ('mac', 'cluster')
MIN_CORES_PER_SIMULATOR = 3     # the driver, the simulator and the sandboxed child (ruling 7)


def platform_name() -> str:
    value = os.environ.get('PAPER3_PLATFORM')
    if value is None:
        if sys.platform == 'darwin':
            return 'mac'
        raise SystemExit("PAPER3_PLATFORM is not set. On Linux it must be 'mac' or 'cluster'; the platform is never "
                         'guessed.')
    if value not in PLATFORMS:
        raise SystemExit(f"PAPER3_PLATFORM is {value!r}; it must be 'mac' or 'cluster'.")
    return value


def is_cluster() -> bool:
    return platform_name() == 'cluster'


def allowed_cores() -> int:
    return len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else (os.cpu_count() or 1)


def _cpu_model():
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):
                return line.partition(':')[2].strip()
    except OSError:
        pass
    return None


def ardupilot_build() -> dict:
    """The simulator the phase will fly: the SHA-256 of its binary and the ArduPilot commit (null when either cannot be
    read). core_check() covers the telohelm package only, so this is not recorded anywhere else."""
    from . import vehicle
    binary = vehicle.ARDUPILOT / 'build' / 'sitl' / 'bin' / 'arducopter'
    try:
        digest = sha256(binary)
    except OSError:
        digest = None
    try:
        done = subprocess.run(['git', '-C', str(vehicle.ARDUPILOT), 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, timeout=30)
        commit = done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {'arducopter_sha256': digest, 'ardupilot_commit': commit}


def platform_record() -> dict:
    """What every manifest says about the platform. On the cluster: the node, the batch job, the CPU model, the cores
    this process may use, the load at start and the Python version."""
    name = platform_name()
    record = {'platform': name, **ardupilot_build()}
    if name == 'cluster':
        record.update({'node': socket.gethostname(), 'slurm_job_id': os.environ.get('SLURM_JOB_ID'),
                       'slurm_job_partition': os.environ.get('SLURM_JOB_PARTITION'), 'cpu_model': _cpu_model(),
                       'cores_allowed': allowed_cores(), 'load_1min_at_start': round(os.getloadavg()[0], 2),
                       'python_version': _platform.python_version()})
    return record


def system_name() -> str:
    """'darwin' on macOS, 'linux' on Linux; tests replace it to state which machine they pretend to be on."""
    return sys.platform


def start_refusal(phases_at_once: int = 1):
    """The reason this process must not start, or None. Both platforms: the named platform must be the machine's (cluster:
    Linux inside a SLURM job; mac: macOS); a nice value other than 0 (zsh lowers
    background jobs by 5 unless NO_BG_NICE is set, and the flights of 12 November ran at 5). Cluster: fewer than three
    allowed cores for each simulator flown at once. The caller prints it and exits with status 3."""
    try:
        name = platform_name()
    except SystemExit as exc:
        return str(exc)
    if name == 'cluster':
        if not system_name().startswith('linux') or not os.environ.get('SLURM_JOB_ID'):
            return ("PAPER3_PLATFORM is 'cluster' but this is not a Linux batch job (SLURM_JOB_ID is "
                    f"{os.environ.get('SLURM_JOB_ID')!r}, system {system_name()!r}); a login node does not count")
    elif system_name() != 'darwin':
        return f"PAPER3_PLATFORM is 'mac' but the system is {system_name()!r}, not macOS"
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    if nice != 0:
        return (f'the nice value is {nice}, not 0 (round two, ruling 5; a zsh background job is lowered by 5 unless '
                f'NO_BG_NICE is set); start it again at normal priority')
    if name == 'cluster':
        need, have = MIN_CORES_PER_SIMULATOR * phases_at_once, allowed_cores()
        if have < need:
            return (f'{have} cores are allowed to this process and {need} are needed ({MIN_CORES_PER_SIMULATOR} for '
                    f'each of {phases_at_once} simulator(s) flown at once)')
    return None


def refuse_start(phases_at_once: int = 1):
    """For a phase: print the refusal to stderr and exit with status 3, if there is one."""
    why = start_refusal(phases_at_once)
    if why:
        print(f'REFUSED: {why}', file=sys.stderr, flush=True)
        raise SystemExit(3)


def own_processes(text: str, uid: int) -> str:
    """Lines of `ps -o uid=,pid=,args=` output that belong to uid, as 'pid args' lines. ps is asked for this user's
    processes already; the uid column is checked again so that another user's process cannot get through."""
    keep = []
    for line in text.splitlines():
        first, _, rest = line.strip().partition(' ')
        if first == str(uid):
            keep.append(rest.strip())
    return '\n'.join(keep)


def simulators(ps_text: str | None = None) -> dict:
    """Running ArduPilot SITL processes (with their instance) and Gazebo servers, matched on the program name in the
    process table, so a shell or script that merely mentions them does not count."""
    if ps_text is None:
        # On the cluster only this user's own processes count: another user's simulator on the node is not ours to
        # wait for, and ports_free still guards against a clash.
        if is_cluster():
            uid = os.getuid()
            text = subprocess.run(['ps', '-u', str(uid), '-o', 'uid=,pid=,args='], capture_output=True, text=True).stdout
            ps_text = own_processes(text, uid)
        else:
            ps_text = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout
    out = ps_text
    sitl, gz = [], []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(' ')
        parts = cmd.split()
        if not parts:
            continue
        prog = Path(parts[0]).name
        if prog == 'arducopter':
            inst = int(parts[parts.index('--instance') + 1]) if '--instance' in parts else 0
            sitl.append({'pid': int(pid), 'instance': inst})
        elif prog == 'gz' and parts[1:2] == ['sim']:
            gz.append({'pid': int(pid)})
    return {'sitl': sitl, 'gazebo': gz}


def other_simulators() -> list[str]:
    s = simulators()
    return [f"arducopter instance {x['instance']} (pid {x['pid']})" for x in s['sitl']] + \
           [f"gazebo (pid {x['pid']})" for x in s['gazebo']]


def ports_free(instance: int) -> list[int]:
    """The SITL instance's TCP ports that something else already holds."""
    import socket
    busy = []
    for port in (5760 + 10 * instance, 5762 + 10 * instance, 5763 + 10 * instance):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', port))
            except OSError:
                busy.append(port)
    return busy


AT_ONCE_RANGE = (1, 4)
AT_ONCE = 4        # how many phases the scheduler flies at once; set from --at-once, 4 when a phase starts without it


def at_once_arg(text: str) -> int:
    n = int(text)
    if not AT_ONCE_RANGE[0] <= n <= AT_ONCE_RANGE[1]:
        raise ValueError(f'--at-once must be from {AT_ONCE_RANGE[0]} to {AT_ONCE_RANGE[1]}, not {n}')
    return n


def machine_check(phase: str, instance: int, pilot: bool, at_once: int | None = None) -> dict:
    """Refuse a flight phase unless the machine is shared only as the protocol allows: a Gazebo phase alone; a SITL
    phase on a scored instance whose ports are free, with no Gazebo server and at most three other SITL processes,
    all on scored instances. Returns what was running, for the manifest."""
    s = simulators()
    if phase == 'gazebo':
        if s['sitl'] or s['gazebo']:
            raise SystemExit(f'Gazebo flights run alone; running now: {other_simulators()}')
        return {'concurrent_sitl_instances': [], 'parallel_limit': 1}
    if s['gazebo']:
        raise SystemExit(f'a Gazebo server is running; SITL phases wait for it: {other_simulators()}')
    if not pilot and instance not in SCORED_INSTANCES:
        raise SystemExit(f'scored SITL phases use instances {SCORED_INSTANCES}; got {instance}')
    others = [x['instance'] for x in s['sitl']]
    if instance in others:
        raise SystemExit(f'instance {instance} is already flying')
    foreign = [i for i in others if i not in SCORED_INSTANCES]
    if foreign:
        raise SystemExit(f'simulators outside the scored instances are running (development runs?): {foreign}')
    limit = AT_ONCE if at_once is None else at_once
    if len(others) >= limit:
        raise SystemExit(f'{len(others)} scored simulators already running; at most {limit} at once, this one included')
    busy = ports_free(instance)
    if busy:
        raise SystemExit(f'instance {instance} cannot start: ports {busy} are in use')
    return {'concurrent_sitl_instances': sorted(others), 'parallel_limit': limit}


def source_files() -> list[Path]:
    """The paper 3 files a scored phase executes or reads as its design: the runner and task-pack modules, the Gazebo
    world and models, the scheduler and the seeds. Other agents' commits elsewhere in the repository (paper 2,
    coordination, review notes) do not touch these. The analysis and validation gate run after the flights and record
    their own hashes in analysis.json."""
    files = sorted((ROOT / 'ardupilot').glob('*.py'))
    for sub in ('worlds', 'ardupilot_gazebo'):
        files += sorted(p for p in (ROOT / 'ardupilot' / 'gazebo' / sub).rglob('*') if p.is_file())
    files += [ROOT / 'protocol' / n for n in ('run_scored.py', 'seeds.json', 'seeds-2.json')]
    if PROTOCOL_VERSION == 3:
        # The third protocol's seed book, shared selectors and scheduler; earlier protocols' file lists are unchanged.
        # set_aside3.py and timing_preflight3.py are imported and run by the scheduler (run_scored3.py).
        files += [f for f in (ROOT / 'protocol' / n for n in ('seeds-3.json', 'contract3.py', 'run_scored3.py',
                                                              'set_aside3.py', 'timing_preflight3.py'))
                  if f.exists()]
        # The package's own bytes: the wheel Paper 3 flies and the record of how it was built, so that a flight on one
        # wheel can never share a source fingerprint with a flight on another (ruling 19).
        files += [WHEEL, WHEEL_BUILD_RECORD]
    return files


def source_fingerprint() -> dict:
    """One SHA-256 over the executed paper 3 source (source_files), so every phase can be bound to one source snapshot
    even while the repository's HEAD moves with unrelated commits (Codex's closure note, 3 November 2026)."""
    h, n = hashlib.sha256(), 0
    for f in source_files():
        h.update(f'{f.relative_to(ROOT)}\0{sha256(f)}\n'.encode())
        n += 1
    return {'sha256': h.hexdigest(), 'files': n}


def git_state() -> dict:
    """The commit and the paper 3 files that differ from it. In a git checkout: git's own answer. In an archive
    (no .git for the repository): paper3/SOURCE.json, written by protocol/package_for_cluster.py, names the commit and
    the SHA-256 of every covered file, and a file that differs, is missing or is not listed is reported in the same
    field. With neither, it refuses."""
    if not (REPO / '.git').exists():
        return archive_state()
    run = lambda *a: subprocess.run(['git', '-C', str(REPO), *a], capture_output=True, text=True).stdout.strip()
    # The texts of the first two protocols are always checked. The text use_protocol named is checked as well, so that
    # under protocol 3 an uncommitted change to PROTOCOL-3.md refuses a scored run too. Before the freeze that file does
    # not exist, and git status says nothing about a path that is not there.
    paths = [str(f.relative_to(REPO)) for f in source_files()]
    paths += list(dict.fromkeys(['paper3/PROTOCOL.md', 'paper3/PROTOCOL-2.md', str(PROTOCOL.relative_to(REPO))]))
    dirty = run('status', '--short', '--', *paths).splitlines()
    return {'commit': run('rev-parse', 'HEAD'), 'uncommitted_paper3': dirty, 'source': source_fingerprint(),
            'from_archive': False}


SOURCE_JSON = 'SOURCE.json'


SOURCE_SKIP_TOP = ('runs', '.venv')     # not part of the code: run folders (maybe a symlink) and the virtual environment


def archive_files() -> dict:
    """Every file under paper3/ as {path relative to paper3: sha256}, leaving out runs/ and .venv/ at the top, any
    __pycache__ folder and SOURCE.json. Directories that are symbolic links are not followed."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__'
                             and not (here == ROOT and d in SOURCE_SKIP_TOP))
        for n in sorted(filenames):
            f = here / n
            rel = str(f.relative_to(ROOT))
            if rel != SOURCE_JSON and f.is_file():
                found[rel] = sha256(f)
    return found


def archive_state() -> dict:
    """The state of an unpacked archive: paper3/SOURCE.json names the commit and the SHA-256 of every file the
    archive carries (protocol/package_for_cluster.py). Any file that differs, is missing or is not listed is reported
    in 'uncommitted_paper3', the field a git checkout uses for changed files, so the guarantee is the same as on the
    Mac. The 'source' fingerprint stays over source_files(), so manifests from both platforms compare."""
    path = ROOT / SOURCE_JSON
    if not path.exists():
        raise SystemExit(f'no .git for the repository and no paper3/{SOURCE_JSON}; cannot name the code that runs')
    listed = json.loads(path.read_text())
    if not listed.get('commit') or not isinstance(listed.get('files'), dict):
        raise SystemExit(f'paper3/{SOURCE_JSON} has no commit or no file list')
    have, problems = archive_files(), []
    for rel, digest in sorted(listed['files'].items()):
        if rel not in have:
            problems.append(f'missing: paper3/{rel}')
        elif have[rel] != digest:
            problems.append(f'differs from {SOURCE_JSON}: paper3/{rel}')
    for rel in sorted(set(have) - set(listed['files'])):
        problems.append(f'not listed in {SOURCE_JSON}: paper3/{rel}')
    return {'commit': listed['commit'], 'uncommitted_paper3': problems, 'source': source_fingerprint(),
            'from_archive': True}


# The third protocol refuses to start a phase when the machine is busy: on 9 November 2026 decision lag rose from
# 0.1 s at a one-minute load average of about 7 to over 4 s at 18 to 58 (reproduction/dev-timing-c3-20261109*.json).
# The limit is the highest one-minute start load of a four-at-once flight in a timing preflight where every flight was
# on time (notes/TAKEOVER-20261111.md, 9:25 am of 12 November). The fourth preflight, flown at night on 12 November
# 2026, was the first to pass: reproduction/timing-preflight-flights-20261112-214408.json, 150 flights, none late,
# proposed_load_limit_1min 4.89 (round two, ruling 4). Start load did not tell late flights from on-time ones in the
# range flown, so the limit guards against sustained overload and does not predict lateness below it.
LOAD_LIMIT_1MIN = 4.89
# Before every counted flight a third-protocol phase waits while the one-minute load is above the limit, looking again
# each minute as the scheduler does (run_scored3.LOAD_WAIT_S), and a phase that waited is released through a lock in
# the run's logs folder, at least a quarter of a second after the last release by any phase: the timing preflight's
# spacing, the decision period over the four instances (round two, ruling 2, and the review's finding 7).
FLIGHT_LOAD_WAIT_S = 60
RELEASE_SPACING_S = 0.25
FLIGHT_RELEASE_FILE = 'flight-release'
_pause = time.sleep          # replaced in tests


def release_spaced(lock: Path) -> float:
    """Wait until RELEASE_SPACING_S after the last release recorded in lock, by any process, then record this one.
    Returns the seconds waited."""
    import fcntl
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            text = f.read().strip()
            wait = max(0.0, float(text) + RELEASE_SPACING_S - time.time()) if text else 0.0
            if wait:
                _pause(wait)
            f.seek(0)
            f.truncate()
            f.write(repr(time.time()))
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return wait


def flight_gate(out: Path):
    """The check before each counted flight of a phase writing into out. It reads the load and starts no process."""
    logs = Path(out).parent / 'logs'
    lock = (logs if logs.is_dir() else Path(out)) / FLIGHT_RELEASE_FILE

    def before(scenario) -> dict:
        waited = 0
        # On the cluster the load is recorded and never waited for or limited: a node's load counts other users' jobs.
        limit = None if is_cluster() else LOAD_LIMIT_1MIN
        while limit is not None:
            load = os.getloadavg()[0]
            if load <= limit:
                break
            if not waited:
                print(f'{getattr(scenario, "episode_id", "next flight")} waits: one-minute load {load:.2f} is above '
                      f'{LOAD_LIMIT_1MIN}; looking again each minute, with no upper bound', flush=True)
            _pause(FLIGHT_LOAD_WAIT_S)
            waited += FLIGHT_LOAD_WAIT_S
        spacing = release_spaced(lock) if waited else 0.0
        # The local time each flight was released, so a flight flown after a late wake can be found afterwards. Power
        # is read only at the phase start: reading it here would start a process before each flight (round three,
        # ruling 5, after the code review's finding 5, 13 November 2026).
        return {'time': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
                'load_1min': round(os.getloadavg()[0], 2), 'limit_1min': limit, 'waited_s': waited,
                'release_spacing_wait_s': round(spacing, 3)}
    return before


def power_and_priority() -> dict:
    """The power source (pmset, macOS only) and this process's nice value, for the manifest (round two, ruling 5,
    after the review's finding 4). The quality-of-service class is not recorded: no simple call reads it."""
    if is_cluster():
        return {'power_source': None, 'nice': os.getpriority(os.PRIO_PROCESS, 0)}
    try:
        out = subprocess.run(['pmset', '-g', 'ps'], capture_output=True, text=True, timeout=10).stdout
        power = out.splitlines()[0].strip() if out else None
    except (OSError, subprocess.SubprocessError):
        power = None
    return {'power_source': power, 'nice': os.getpriority(os.PRIO_PROCESS, 0)}


def load_check(pilot: bool) -> dict:
    """The load when a phase starts. Above the limit the phase waits, looking again each minute with no upper bound,
    as flight_gate does before each flight; it used to refuse, and a refused phase then needed a resume by hand (round
    three, ruling 6, after the code review's finding 6, 13 November 2026). On the cluster it records the load and does
    not wait."""
    if is_cluster():
        load = os.getloadavg()
        return {'load_average_1_5_15': [round(x, 2) for x in load], 'limit_1min': None, 'cores': os.cpu_count(),
                'cores_allowed': allowed_cores(), 'waited_s': 0, 'limit_status': 'not applied (cluster)'}
    if LOAD_LIMIT_1MIN is None:
        load = os.getloadavg()
        record = {'load_average_1_5_15': [round(x, 2) for x in load], 'limit_1min': None, 'cores': os.cpu_count()}
        if not pilot:
            raise SystemExit('no calibrated load limit; scored third-protocol phases wait for the timing preflight')
        return {**record, 'limit_status': 'uncalibrated (pilot only)'}
    waited = 0
    while True:
        load = os.getloadavg()
        if load[0] <= LOAD_LIMIT_1MIN:
            break
        if not waited:
            print(f'phase waits: one-minute load {load[0]:.2f} is above {LOAD_LIMIT_1MIN}; looking again each minute, '
                  f'with no upper bound', flush=True)
        _pause(FLIGHT_LOAD_WAIT_S)
        waited += FLIGHT_LOAD_WAIT_S
    return {'load_average_1_5_15': [round(x, 2) for x in load], 'limit_1min': LOAD_LIMIT_1MIN,
            'cores': os.cpu_count(), 'waited_s': waited, 'limit_status': 'calibrated'}


def start_route() -> dict:
    """Start this process's sandbox route and return its record (telohelm.runtime.sandbox.start_route). Under protocol 3
    every process that flies calls this before anything in it makes a sandboxed call. A process whose route cannot
    start, or whose installed package has no route to start (the wheel before the Paper 3 build), refuses."""
    from telohelm.runtime import sandbox
    start = getattr(sandbox, 'start_route', None)
    if start is None:
        raise SystemExit('the installed telohelm has no start_route: it is not the Paper 3 wheel')
    try:
        return start()
    except (sandbox.SandboxUnavailable, OSError) as error:      # OSError: the process limit, say, when the holder starts
        raise SystemExit(f'the sandbox route cannot start: {error}')


def write_route_end(out: Path) -> list:
    """The route's state at the end of a phase: the calls made and every holder replaced (sandbox-end.json). Returns the
    replacements the gate refuses (validate3.py): one whose reason is not 'stopped' or 'residue', or whose spent holder had
    died. The file is written either way, so that the record shows them."""
    from telohelm.runtime import sandbox
    state = sandbox.route_state()
    (Path(out) / 'sandbox-end.json').write_text(json.dumps(state, indent=1) + '\n')
    return [r for r in state.get('replacements') or []
            if not isinstance(r, dict) or r.get('holder_died') or r.get('reason') not in ('stopped', 'residue')]


def stop_for_bad_replacement(bad: list, phase: str) -> None:
    """A phase whose holder was replaced for a reason the gate refuses stops here with a message and a non-zero exit, so the
    scheduler writes no done mark and holds the phase, and the chain does not fly on to be refused by the gate afterwards."""
    if bad:
        raise SystemExit(f'{phase} is stopped: a sandbox holder was replaced for a reason the gate refuses (not stopped or '
                         f'residue, or the spent holder had died): {bad[:3]}')


KEPT_LATE_FILE = 'kept-late.json'


def late_attempts_set_aside(root: Path, phase: str) -> list:
    """The folders of this phase's earlier attempts that were set aside for lateness, by name and in attempt order. The
    set-aside folder and its attempt folders are protocol/set_aside3.py's (set_aside_dir, PHASE-attemptN); an attempt
    counts when its receipt.json names this phase and the reason late. A folder with no readable receipt does not count."""
    from protocol import set_aside3 as SA
    found = []
    for folder in SA.set_aside_dir(root).glob(f'{phase}-attempt*'):
        suffix = folder.name[len(phase) + len('-attempt'):]
        try:
            receipt = json.loads((folder / 'receipt.json').read_text())
        except (OSError, ValueError):
            continue
        if suffix.isdigit() and isinstance(receipt, dict) and receipt.get('phase') == phase and receipt.get('reason') == 'late':
            found.append((int(suffix), folder.name))
    return [name for _, name in sorted(found)]


LATE_HISTORY_EXIT = 4     # the exit status of an evaluation phase that is refused because of its history of late attempts


def refuse_late_history(count: int, phase: str | None = None) -> None:
    """An evaluation phase is set aside for lateness at most ladder.REFLIGHTS times; its next attempt is kept (ruling 39,
    point 2). A phase with more such attempts than that has a history the rule never makes, so it is not flown: print one
    line and exit with LATE_HISTORY_EXIT, which the scheduler records as a failed exit, and the phase is seen and
    looked at (ruling 45, point 3)."""
    from .ladder import REFLIGHTS
    if count > REFLIGHTS:
        print(f'LATE HISTORY REFUSED: {phase or "this phase"} has {count} attempts set aside for lateness, more than the '
              f'{REFLIGHTS} the rule allows; it is not flown, and its history needs to be looked at', flush=True)
        raise SystemExit(LATE_HISTORY_EXIT)


def keep_late_attempt(rows: list, set_aside: list) -> tuple:
    """The evaluation phase's rule for a late flight (ruling 39, point 2), on its timing rows and the names of its
    earlier attempts set aside for lateness. With fewer than ladder.REFLIGHTS such attempts, or no late row, the rows
    come back unchanged and the second value is None: the phase is held as before. With REFLIGHTS or more, each late
    row gains kept_late true, and the second value is the record written to kept-late.json for the gate: the number of
    late attempts set aside before this one, their folders' names, and the flights kept late. With more than REFLIGHTS
    such attempts it exits with LATE_HISTORY_EXIT (refuse_late_history)."""
    from .ladder import REFLIGHTS
    refuse_late_history(len(set_aside))
    if len(set_aside) < REFLIGHTS or not any(r['late'] for r in rows):
        return rows, None
    marked = [{**r, 'kept_late': True} if r['late'] else r for r in rows]
    return marked, {'late_attempts_set_aside': len(set_aside), 'attempt_folders': list(set_aside),
                    'kept_late_flights': [r['flight'] for r in rows if r['late']]}


def guard(out: Path, phase: str, args: dict, pilot: bool, instance: int) -> dict:
    out = Path(out)
    if out.exists():
        raise FileExistsError(f'{out} exists; records are never overwritten')
    core = core_check()
    if not core['ok']:
        raise SystemExit(f'core check failed: {json.dumps(core)[:400]}')
    route = start_route() if PROTOCOL_VERSION == 3 else None     # before the manifest, and before any call is made
    machine = machine_check(phase, instance, pilot, AT_ONCE)
    if PROTOCOL_VERSION == 3:
        machine = {**machine, 'load': load_check(pilot), **power_and_priority()}
    if not SEEDS.exists():
        raise SystemExit(f'protocol/{SEEDS.name} is missing')
    if not pilot and not PROTOCOL.exists():
        raise SystemExit(f'paper3/{PROTOCOL.name} (the frozen protocol) is missing; scored runs start only after the freeze')
    protocol = PROTOCOL if PROTOCOL.exists() else PROTOCOL_DRAFT
    git = git_state()
    if git['uncommitted_paper3'] and not pilot:
        raise SystemExit(f'uncommitted paper 3 files; commit before a scored run: {git["uncommitted_paper3"][:8]}')
    out.mkdir(parents=True)
    manifest = {'phase': phase, 'pilot': pilot, 'started': datetime.datetime.now().astimezone().isoformat(),
                'protocol': str(protocol.relative_to(ROOT)), 'protocol_version': PROTOCOL_VERSION,
                'protocol_sha256': sha256(protocol), 'seeds': SEEDS.name, 'seeds_sha256': sha256(SEEDS), 'git': git, 'core': core,
                'args': args, 'instance': instance, 'machine': machine, 'platform': platform_record(),
                'at_once': AT_ONCE}
    if PROTOCOL_VERSION == 3:
        manifest['sandbox'] = route
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, default=str))
    return manifest


def seeds() -> dict:
    return json.loads(SEEDS.read_text())


def library_source(run: Path) -> tuple[str, str]:
    from .battle import adopted_source
    return adopted_source(Path(run)), str(run)


def chosen_source(a) -> tuple[str, str]:
    from . import demo
    if a.reference:
        return demo.REFERENCE[a.task], 'designer reference controller (demo.REFERENCE)'
    if getattr(a, 'hold', False):
        return demo.HOLD_STILL[a.task], 'no procedure: hold still (demo.HOLD_STILL)'
    return library_source(a.library)


def learning_plan(s: dict, task: str, run: int, block, family, pilot: bool) -> tuple[str, list, dict]:
    """The family and seeds of one learning run, and the arguments its manifest records. In the first protocol every
    run learns on calm scenarios. In the second, reach, reach3d and land learn by matched block: block b's three layouts
    on the threat family (the threat arm) or on the matched family, the same layouts with the zones removed (the calm
    arm); avoid and orbit learn on calm scenarios as before."""
    if PROTOCOL_VERSION == 1:
        return 'calm', (s['pilot']['learning'] if pilot else s['learning'][task][run]), {'run': run}
    if task in STUDY2_TASKS:
        if block is None or family not in ('threat', 'matched'):
            raise SystemExit(f'{task} learns by --block and --family threat|matched in the second protocol')
        return family, (s['pilot']['blocks'][task] if pilot else s['blocks'][task][block]), \
            {'block': block, 'family': family}
    if block is not None or family not in (None, 'calm'):
        raise SystemExit(f'{task} learns on calm scenarios by --run in the second protocol')
    return 'calm', (s['pilot']['learning_calm'] if pilot else s['learning_calm'][task][run]), {'run': run}


def phase_learn(a):
    from . import demo
    from .battle import generate
    s = seeds()
    family, learn_seeds, which = learning_plan(s, a.task, a.run, a.block, a.family, a.pilot)
    guard(a.out, 'learn', {'task': a.task, **which, 'learning_family': family, 'learning_seeds': learn_seeds,
                           'speedup': a.speedup, 'model': GEM_MODEL, 'attempts': 3, 'trial_scenarios': 3,
                           'examples': True}, a.pilot, a.instance)
    learning = [generate(a.task, family, k) for k in learn_seeds]
    # demo.run refuses an existing folder, so it writes into a subfolder of the guarded one.
    summary = demo.run(Path(a.out) / 'run', task=a.task, speedup=a.speedup, gem_model=GEM_MODEL, attempts=3,
                       trial_scenarios=3, instance=a.instance, examples=True, scenarios=(learning, []),
                       scored=not a.pilot)
    print(json.dumps({k: summary.get(k) for k in ('learning_attempts', 'real_model_calls', 'claude_cost_usd')}))
    return 0


def phase_heldout(a, repeat=False):
    from . import battle
    from .battle import generate
    s = seeds()
    source, origin = chosen_source(a)
    if a.pilot:
        cases = [generate(a.task, 'calm', k) for k in s['pilot']['heldout_calm']]
    elif repeat:
        cases = [generate(a.task, 'calm', k) for k in s['repeatability']['calm']]
    else:
        cases = ([generate(a.task, 'calm', k) for k in s['heldout']['calm']] +
                 [generate(a.task, 'wind', k) for k in s['heldout']['wind']])
    phase = 'repeat' if repeat else 'heldout'
    guard(a.out, phase, {'task': a.task, 'origin': origin, 'speedup': a.speedup,
                         'cases': [c.episode_id for c in cases]}, a.pilot, a.instance)
    rounds = s['repeatability']['repeats'] if repeat else 1
    for r in range(1, rounds + 1):
        target = Path(a.out) / (f'repeat-{r}' if repeat else 'flights')
        battle.run(target, a.task, source, origin, cases=cases, speedup=a.speedup, instance=a.instance)
    return 0


def phase_disturb(a):
    from . import battle
    from .battle import generate
    s = seeds()
    source, origin = chosen_source(a)
    families = [f for f in s['disturbance'] if not (f == 'threat' and a.task == 'orbit')]
    cases = [generate(a.task, f, k) for f in families
             for k in (s['pilot']['disturbance'] if a.pilot else s['disturbance'][f])]
    guard(a.out, 'disturb', {'task': a.task, 'origin': origin, 'speedup': a.speedup,
                             'cases': [c.episode_id for c in cases]}, a.pilot, a.instance)
    battle.run(Path(a.out) / 'flights', a.task, source, origin, cases=cases, speedup=a.speedup, instance=a.instance)
    return 0


def phase_threat(a):
    """Study 2's evaluation (second protocol): a library flies the reserved fresh threat scenarios, learning off."""
    from . import battle
    from .battle import generate
    if PROTOCOL_VERSION != 2 or a.task not in STUDY2_TASKS:
        raise SystemExit(f'the threat evaluation is a second-protocol phase for {", ".join(STUDY2_TASKS)}')
    s = seeds()
    source, origin = chosen_source(a)
    cases = [generate(a.task, 'threat', k) for k in (s['pilot']['threat_evaluation'] if a.pilot
                                                     else s['threat_evaluation'])]
    guard(a.out, 'threat', {'task': a.task, 'origin': origin, 'speedup': a.speedup,
                            'cases': [c.episode_id for c in cases]}, a.pilot, a.instance)
    battle.run(Path(a.out) / 'flights', a.task, source, origin, cases=cases, speedup=a.speedup, instance=a.instance)
    return 0


def _third(a):
    if PROTOCOL_VERSION != 3 or a.task not in STUDY2_TASKS:
        raise SystemExit(f'{a.phase} is a third-protocol phase (--protocol 3) for {", ".join(STUDY2_TASKS)}')
    from protocol import contract3
    return contract3, seeds()


def warmup_case(C3, s: dict, task: str):
    """The case a phase's warm-up flight flies: the first calm retention case of the task's development (pilot) seed
    book, whatever the phase's own cohort. A calm case with the reference controller lasts well past the start-up
    effect, which strikes decisions two to eight of a process's first flight, where a hazard flight ends in about
    eight. It is never a reserved scored seed (notes/TAKEOVER-20261111.md, ruling 6)."""
    return C3.retention_cases(s, task, pilot=True)[0]


def phase_learn3(a):
    """One learning block: the four arms of ladder.py on the block's three layouts."""
    from . import ladder
    C3, s = _third(a)
    if a.stub and not a.pilot:
        raise SystemExit('scripted replies are for pilots only')
    matched = C3.learning_cases(s, a.task, a.block, a.pilot, threat=False)
    threat = C3.learning_cases(s, a.task, a.block, a.pilot, threat=True)
    # A late call is flown again in place, at most twice, with no model call (round two, ruling 3); --record-late-flights
    # keeps late flights as flown, for pilots only.
    late = 'record' if a.record_late_flights else 'refly'
    if late == 'record' and not a.pilot:
        raise SystemExit('a scored block flies a late call again in place')
    guard(a.out, 'learn3', {'task': a.task, 'block': a.block, 'speedup': a.speedup,
                            'model': None if a.stub else GEM_MODEL, 'scripted_replies': a.stub,
                            'learning_cases': {'matched': [c.episode_id for c in matched],
                                               'threat': [c.episode_id for c in threat]},
                            'arms': {k: list(v[1]) for k, v in ladder.ARMS.items()},
                            'calls_per_slot': ladder.CALLS_PER_SLOT, 'late_flights': late}, a.pilot, a.instance)
    record = ladder.run_block(a.out, a.task, a.block, matched, threat, speedup=a.speedup, instance=a.instance,
                              scored=not a.pilot, gem_model=None if a.stub else GEM_MODEL,
                              stub=ladder.PILOT_STUBS[a.stub](a.task) if a.stub else None, late_flights=late,
                              warmup_case=warmup_case(C3, s, a.task), before_flight=flight_gate(Path(a.out)),
                              run_root=Path(a.out).resolve().parent)
    # The adoptions are printed only after the check that can stop the block, so that a block about to be stopped and set
    # aside never shows them to the people who watch the log (ruling 39, point 4).
    stop_for_bad_replacement(write_route_end(a.out), 'learn3')
    print(json.dumps({arm: r['candidate_id'] for arm, r in record['arms'].items()}))
    return 0


def _evaluated_source(a) -> tuple[str, dict]:
    """The source with SHA-256 a.source in a learning block, and the arms that adopted it."""
    learning = Path(a.learning)
    arms = json.loads((learning / 'arms.json').read_text())
    if (arms['task'], arms['block']) != (a.task, a.block):
        raise SystemExit(f'{learning} is {arms["task"]} block {arms["block"]}, not {a.task} block {a.block}')
    found = [f for f in sorted((learning / 'candidates').glob('*/source.py')) if sha256(f) == a.source]
    if not found:
        raise SystemExit(f'no candidate in {learning} has source {a.source}')
    c0 = json.loads((learning / 'candidates' / 'c0' / 'candidate.json').read_text())
    return found[0].read_text(encoding='utf-8'), {
        'arms': sorted(k for k, r in arms['arms'].items() if r['adopted'] and r['source_sha256'] == a.source),
        'includes_c0': c0.get('source_sha256') == a.source, 'learning': str(learning)}


def phase_eval3(a):
    """threat3 (the 24 hazard scenarios) or retain3 (the 10 ordinary ones) for one source of one block."""
    from . import battle
    C3, s = _third(a)
    # Before anything is read or flown: a phase with more than REFLIGHTS attempts set aside for lateness is not flown.
    refuse_late_history(len(late_attempts_set_aside(Path(a.out).parent, Path(a.out).name)), Path(a.out).name)
    source, roles = _evaluated_source(a)
    if a.phase == 'threat3':
        cases = C3.evaluation_cases(s, a.task, a.pilot)
    else:
        if not roles['arms']:
            raise SystemExit('retention is flown only for a source some arm adopted')
        cases = C3.retention_cases(s, a.task, a.pilot)
    # The scheduled cases in the instance's order, the timing preflight's (round two, ruling 2). The manifest keeps both.
    flown = [cases[i] for i in C3.flight_order(len(cases), a.instance)]
    guard(a.out, a.phase, {'task': a.task, 'block': a.block, 'source_sha256': a.source, **roles,
                           'speedup': a.speedup, 'cases': [c.episode_id for c in cases],
                           'flight_order': [c.episode_id for c in flown]}, a.pilot, a.instance)
    from .ladder import COMMAND_DELAY_PERIODS, fly_warmup, timing
    # The process's first flight is the warm-up, in its own folder and in no timing row (ruling 6).
    fly_warmup(Path(a.out), a.task, warmup_case(C3, s, a.task), speedup=a.speedup, instance=a.instance)
    battle.run(Path(a.out) / 'flights', a.task, source, roles['learning'], cases=flown, speedup=a.speedup,
               instance=a.instance, before_flight=flight_gate(Path(a.out)), command_delay_periods=COMMAND_DELAY_PERIODS)
    rows = [{'flight': c.episode_id, **timing(json.loads((Path(a.out) / 'flights' / c.episode_id /
                                                          'outcome.json').read_text()))} for c in flown]
    # A late flight is an infrastructure fault, never a result (notes/TAKEOVER-20261111.md, "Replacing a late flight"),
    # until the phase has been set aside for lateness REFLIGHTS times: then its next attempt is kept, as a learning
    # call's third attempt is (ruling 39, point 2). Otherwise the phase exits with a failure so the scheduler holds it;
    # the folder and timing.json stay as evidence.
    late = [r['flight'] for r in rows if r['late']]
    rows, kept = keep_late_attempt(rows, late_attempts_set_aside(Path(a.out).parent, Path(a.out).name))
    (Path(a.out) / 'timing.json').write_text(json.dumps(rows, indent=1) + '\n')
    if kept:
        (Path(a.out) / KEPT_LATE_FILE).write_text(json.dumps(kept, indent=1) + '\n')
    # The route's state is written whether or not a flight was late: a held phase is set aside, and the pass script reads
    # the replacements in the attempts set aside as it reads those of the run's own phases.
    bad = write_route_end(a.out)
    if kept:
        print(f'{len(late)} of {len(rows)} flights were late at the third attempt, after {kept["late_attempts_set_aside"]} '
              f'attempts set aside for lateness; the phase is kept, the late flights marked kept_late: {late[:5]}',
              flush=True)
    elif late:
        print(f'{len(late)} of {len(rows)} flights were late; the phase is held, not scored: {late[:5]}', flush=True)
    stop_for_bad_replacement(bad, a.phase)
    return 1 if late and not kept else 0


def phase_autopilot(a):
    from . import autopilot_modes
    from .battle import generate
    s = seeds()
    if a.pilot:
        cases = [generate(a.task, 'calm', k) for k in s['pilot']['heldout_calm']]
    else:
        cases = ([generate(a.task, 'calm', k) for k in s['heldout']['calm']] +
                 [generate(a.task, 'wind', k) for k in s['heldout']['wind']])
    guard(a.out, 'autopilot', {'task': a.task, 'origin': 'ArduPilot flight modes', 'speedup': a.speedup,
                               'cases': [c.episode_id for c in cases]}, a.pilot, a.instance)
    autopilot_modes.run(Path(a.out) / 'flights', a.task, cases, speedup=a.speedup, instance=a.instance)
    return 0


def phase_courses(a):
    from . import course as C, course3d as C3
    from .course_run import fly_course as fly_flat
    from .course3d_run import fly_course as fly_3d
    s = seeds()
    task = 'reach' if a.kind == 'flat' else 'reach3d'
    a.task = task
    source, origin = chosen_source(a)
    lo, hi = s['courses_flat'] if a.kind == 'flat' else s['courses_3d']
    if a.pilot:
        lo, hi = (900000, 900003) if a.kind == 'flat' else (910000, 910003)
    guard(a.out, 'courses', {'kind': a.kind, 'origin': origin, 'seeds': [lo, hi], 'speedup': a.speedup,
                             'gate_radius_m': GATE_RADIUS_M, 'pass_rule': 'path'}, a.pilot, a.instance)
    rows, started = [], time.monotonic()
    for seed in range(lo, hi):
        course = (C.generate(seed, False, gate_radius=GATE_RADIUS_M) if a.kind == 'flat'
                  else C3.generate(seed, gate_radius=GATE_RADIUS_M))
        folder = Path(a.out) / f'seed-{seed}'
        rec = (fly_flat(course, source, origin, folder, speedup=a.speedup, instance=a.instance, pass_rule='path')
               if a.kind == 'flat' else
               fly_3d(course, source, origin, folder, speedup=a.speedup, instance=a.instance, pass_rule='path'))
        pv = rec['provenance']
        rows.append({'seed': seed, 'wind_ms': course.wind_ms, 'completed': rec['completed'], 'gates': rec['gates'],
                     'gates_passed': rec['gates_passed'], 'end_reason': rec['end_reason'],
                     'steps': pv.get('control_steps'), 'steps_without_procedure': pv.get('steps_without_procedure')})
        print(f"{a.kind} seed {seed}: {rec['gates_passed']}/{rec['gates']} {rec['end_reason']}", flush=True)
        _course_summary(a.out, rows, origin, started)
    return 0


def _course_summary(out, rows, origin, started):
    summary = {'origin': origin, 'gate_radius_m': GATE_RADIUS_M, 'courses': len(rows),
               'completed': sum(r['completed'] for r in rows),
               'gates_passed': sum(r['gates_passed'] for r in rows), 'gates_total': sum(r['gates'] for r in rows),
               'control_steps': sum(r['steps'] or 0 for r in rows),
               'steps_without_procedure': sum(r['steps_without_procedure'] or 0 for r in rows),
               'courses_with_wind': sum(1 for r in rows if (r['wind_ms'] or 0) > 0),
               'end_reasons': dict(Counter(r['end_reason'] for r in rows)),
               'model_calls': 'none possible: the course runners have no model',
               'elapsed_seconds': round(time.monotonic() - started)}
    (Path(out) / 'rows.json').write_text(json.dumps(rows, indent=1))
    (Path(out) / 'summary.json').write_text(json.dumps(summary, indent=1))


def phase_splits(a):
    from .course_splits import split_s_race
    from .course3d_run import fly_course
    a.task = 'reach3d'
    source, origin = chosen_source(a)
    flights = 1 if a.pilot else a.flights
    guard(a.out, 'splits', {'origin': origin, 'flights': flights, 'speedup': 1.0, 'decision_period_s': 1.0,
                            'pass_rule': 'path', 'gate_radius_m': GATE_RADIUS_M, 'mirrored': False}, a.pilot, a.instance)
    course = split_s_race(gate_radius=GATE_RADIUS_M)
    rows = []
    for k in range(1, flights + 1):
        rec = fly_course(course, source, origin, Path(a.out) / f'flight-{k}', speedup=1.0, instance=a.instance,
                         dt=1.0, task='reach3d', pass_rule='path')
        rows.append({'flight': k, 'completed': rec['completed'], 'gates_passed': rec['gates_passed'],
                     'gates': rec['gates'], 'end_reason': rec['end_reason'],
                     'finish_s': rec['reached'][-1]['t'] if rec.get('reached') and rec['completed'] else None,
                     'steps_without_procedure': rec['provenance'].get('steps_without_procedure')})
        print(f"Split-S flight {k}: {rec['gates_passed']}/{rec['gates']} {rec['end_reason']}", flush=True)
        (Path(a.out) / 'rows.json').write_text(json.dumps(rows, indent=1))
    return 0


SPLITS_FLIGHTS = 5      # Split-S flights per library in a scored run (one in a pilot); the validation gate reads these
GAZEBO_FLIGHTS = 3      # Gazebo Split-S flights per library in a scored run (one in a pilot)
GZ = '/opt/homebrew/bin/gz'
GZ_PLUGIN_DIR = Path('/Users/s.vajda/Development/ardupilot_gazebo/build')     # ArduPilot's plugin, commit f116b035
GZ_MODELS = [ROOT / 'ardupilot' / 'gazebo' / 'ardupilot_gazebo' / 'models',
             Path('/Users/s.vajda/Development/ardupilot_gazebo/models')]
GZ_WORLD = ROOT / 'ardupilot' / 'gazebo' / 'worlds' / 'splits_open.sdf'


def phase_gazebo(a):
    """The Split-S in Gazebo: a fresh Gazebo server per flight on an open field (GZ_WORLD), the autopilot taking its
    physics through ArduPilot's plugin, the same course, gate rule and decision period as the SITL Split-S."""
    from .course_splits import split_s_race
    from .course3d_run import fly_course
    a.task = 'reach3d'
    a.instance = 0                                 # the plugin listens for instance 0's autopilot
    source, origin = chosen_source(a)
    flights = 1 if a.pilot else a.flights
    guard(a.out, 'gazebo', {'origin': origin, 'flights': flights, 'speedup': 1.0, 'decision_period_s': 1.0,
                            'pass_rule': 'path', 'gate_radius_m': GATE_RADIUS_M, 'mirrored': False,
                            'world': str(GZ_WORLD.relative_to(ROOT)), 'world_sha256': sha256(GZ_WORLD),
                            'plugin_dir': str(GZ_PLUGIN_DIR)}, a.pilot, a.instance)
    env = {**os.environ, 'GZ_IP': '127.0.0.1', 'GZ_SIM_SYSTEM_PLUGIN_PATH': str(GZ_PLUGIN_DIR),
           'GZ_SIM_RESOURCE_PATH': ':'.join(str(m) for m in GZ_MODELS)}
    course = split_s_race(gate_radius=GATE_RADIUS_M)
    rows = []
    for k in range(1, flights + 1):
        folder = Path(a.out) / f'flight-{k}'
        folder.mkdir(parents=True)
        with open(folder / 'gz.log', 'w') as log:
            server = subprocess.Popen([GZ, 'sim', '-s', '-r', '-v2', str(GZ_WORLD)], env=env, stdout=log,
                                      stderr=subprocess.STDOUT)
            try:
                time.sleep(10)                     # the server loads the world before the autopilot connects
                if server.poll() is not None:
                    raise SystemExit(f'Gazebo server exited early (code {server.returncode}); see {folder / "gz.log"}')
                # The plugin listens for instance 0's autopilot, so Gazebo flights always use instance 0.
                rec = fly_course(course, source, origin, folder / 'flight', speedup=1.0, instance=0, dt=1.0,
                                 task='reach3d', pass_rule='path', gazebo=True)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
        rows.append({'flight': k, 'completed': rec['completed'], 'gates_passed': rec['gates_passed'],
                     'gates': rec['gates'], 'end_reason': rec['end_reason'],
                     'finish_s': rec['reached'][-1]['t'] if rec.get('reached') and rec['completed'] else None,
                     'steps_without_procedure': rec['provenance'].get('steps_without_procedure')})
        print(f"Gazebo Split-S flight {k}: {rec['gates_passed']}/{rec['gates']} {rec['end_reason']}", flush=True)
        (Path(a.out) / 'rows.json').write_text(json.dumps(rows, indent=1))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='phase', required=True)
    sub.add_parser('check')

    def common(q, task=True, source=True):
        if task:
            q.add_argument('--task', choices=('reach', 'avoid', 'orbit', 'land', 'reach3d'), required=True)
        if source:
            g = q.add_mutually_exclusive_group(required=True)
            g.add_argument('--library', type=Path, help='a learning run folder with one adopted procedure')
            g.add_argument('--reference', action='store_true')
            g.add_argument('--hold', action='store_true')
        q.add_argument('--out', type=Path, required=True)
        q.add_argument('--speedup', type=float, default=1.0)
        q.add_argument('--instance', type=int, default=SCORED_INSTANCES[0])
        q.add_argument('--pilot', action='store_true')
        q.add_argument('--protocol', type=int, choices=sorted(VERSIONS), default=1)
        q.add_argument('--at-once', type=at_once_arg, default=4, help='phases the scheduler flies at once (1 to 4)')

    q = sub.add_parser('learn'); common(q, source=False); q.add_argument('--run', type=int, choices=range(5), default=0)
    q.add_argument('--block', type=int, help='second protocol: the matched learning block')
    q.add_argument('--family', choices=('calm', 'threat', 'matched'), help='second protocol: the learning family')
    for name in ('heldout', 'repeat', 'disturb', 'threat'):
        common(sub.add_parser(name))
    common(sub.add_parser('autopilot'), source=False)
    q = sub.add_parser('learn3'); common(q, source=False); q.add_argument('--block', type=int, required=True)
    q.add_argument('--stub', choices=STUB_CHOICES, help='pilot only: scripted replies, no model calls')
    q.add_argument('--record-late-flights', action='store_true', help='pilot only: record late flights, do not stop')
    for name in ('threat3', 'retain3'):
        q = sub.add_parser(name); common(q, source=False); q.add_argument('--block', type=int, required=True)
        q.add_argument('--learning', type=Path, required=True, help='the block\'s learn3 folder')
        q.add_argument('--source', required=True, help='SHA-256 of the candidate source to fly')
    q = sub.add_parser('courses'); common(q, task=False); q.add_argument('--kind', choices=('flat', '3d'), required=True)
    q = sub.add_parser('splits'); common(q, task=False); q.add_argument('--flights', type=int, default=SPLITS_FLIGHTS)
    q = sub.add_parser('gazebo'); common(q, task=False); q.add_argument('--flights', type=int, default=GAZEBO_FLIGHTS)
    a = p.parse_args(argv)
    use_protocol(getattr(a, 'protocol', 1))
    global AT_ONCE
    AT_ONCE = getattr(a, 'at_once', 4)
    if a.phase != 'check':
        refuse_start(1)
    if a.phase == 'check':
        print(json.dumps({'core': core_check(), 'other_simulators': other_simulators(), 'git': git_state(),
                          'seeds_present': SEEDS.exists()}, indent=1))
        return 0
    if a.phase == 'learn':
        return phase_learn(a)
    if a.phase == 'learn3':
        return phase_learn3(a)
    if a.phase in ('threat3', 'retain3'):
        return phase_eval3(a)
    if a.phase in ('heldout', 'repeat'):
        return phase_heldout(a, repeat=a.phase == 'repeat')
    if a.phase == 'disturb':
        return phase_disturb(a)
    if a.phase == 'threat':
        return phase_threat(a)
    if a.phase == 'autopilot':
        return phase_autopilot(a)
    if a.phase == 'courses':
        return phase_courses(a)
    if a.phase == 'gazebo':
        return phase_gazebo(a)
    return phase_splits(a)


if __name__ == '__main__':
    raise SystemExit(main())

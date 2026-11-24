"""Paper 3's scored runner: a thin driver over demo.run, battle.run and the course runners (PROTOCOL.md).

Before any phase it checks that the Telohelm core imported here is byte-identical to the wheel paper 2's scored
streams used, that no other simulator is running on the machine, and that the reserved seeds file is present. It then
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
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
WHEEL = ROOT / 'protocol' / 'telohelm-0.1.0.dev0-py3-none-any.whl'
WHEEL_SHA256 = 'bb2c6e779b7526c85fb6ced29bd0db01f0d30a88a16e2252f2f058cab3ce2f8c'
SEEDS = ROOT / 'protocol' / 'seeds.json'
PROTOCOL = ROOT / 'PROTOCOL.md'               # the frozen protocol, written at the freeze; scored runs need it
PROTOCOL_DRAFT = ROOT / 'PROTOCOL-DRAFT.md'   # what a pilot records when nothing is frozen yet
PROTOCOL_VERSION = 1
# The second protocol (4 November 2026) has its own seeds and protocol files; the first protocol's stay as frozen.
VERSIONS = {1: ('seeds.json', 'PROTOCOL.md', 'PROTOCOL-DRAFT.md'),
            2: ('seeds-2.json', 'PROTOCOL-2.md', 'PROTOCOL-2-DRAFT.md')}
STUDY2_TASKS = ('reach', 'reach3d', 'land')


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


def core_check() -> dict:
    """The imported telohelm package against the scored wheel, file by file (Python sources and package data)."""
    import telohelm
    pkg = Path(telohelm.__file__).resolve().parent
    if sha256(WHEEL) != WHEEL_SHA256:
        return {'ok': False, 'reason': 'wheel file hash differs from paper 2\'s scored wheel'}
    mismatched, missing = [], []
    with zipfile.ZipFile(WHEEL) as z:
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
    ok = not (mismatched or missing or extra)
    return {'ok': ok, 'wheel_sha256': WHEEL_SHA256, 'package_dir': str(pkg), 'files_compared': len(names),
            'mismatched': mismatched, 'missing': missing, 'extra_py': extra}


# Scored SITL flights may run up to four at once, each on its own simulator instance (ports 5760 + 10 x instance and
# up). On 2 November 2026 two, four and seven simulators flying together (protocol/parallel_lag.py, runs/pilot-par*)
# gave the same step counts as one alone on every flight and no rise in decision lag; an eighth, on instance 14, could
# not start because its port 5900 is the Mac's screen sharing. Gazebo flights run alone.
SCORED_INSTANCES = (10, 11, 12, 13)


def simulators() -> dict:
    """Running ArduPilot SITL processes (with their instance) and Gazebo servers, matched on the program name in the
    process table, so a shell or script that merely mentions them does not count."""
    out = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout
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


def machine_check(phase: str, instance: int, pilot: bool) -> dict:
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
    if len(others) >= len(SCORED_INSTANCES):
        raise SystemExit(f'{len(others)} scored simulators already running; the limit is {len(SCORED_INSTANCES)}')
    busy = ports_free(instance)
    if busy:
        raise SystemExit(f'instance {instance} cannot start: ports {busy} are in use')
    return {'concurrent_sitl_instances': sorted(others), 'parallel_limit': len(SCORED_INSTANCES)}


def source_files() -> list[Path]:
    """The paper 3 files a scored phase executes or reads as its design: the runner and task-pack modules, the Gazebo
    world and models, the scheduler and the seeds. Other agents' commits elsewhere in the repository (paper 2,
    coordination, review notes) do not touch these. The analysis and validation gate run after the flights and record
    their own hashes in analysis.json."""
    files = sorted((ROOT / 'ardupilot').glob('*.py'))
    for sub in ('worlds', 'ardupilot_gazebo'):
        files += sorted(p for p in (ROOT / 'ardupilot' / 'gazebo' / sub).rglob('*') if p.is_file())
    files += [ROOT / 'protocol' / n for n in ('run_scored.py', 'seeds.json', 'seeds-2.json')]
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
    run = lambda *a: subprocess.run(['git', '-C', str(REPO), *a], capture_output=True, text=True).stdout.strip()
    paths = [str(f.relative_to(REPO)) for f in source_files()] + ['paper3/PROTOCOL.md', 'paper3/PROTOCOL-2.md']
    dirty = run('status', '--short', '--', *paths).splitlines()
    return {'commit': run('rev-parse', 'HEAD'), 'uncommitted_paper3': dirty, 'source': source_fingerprint()}


def guard(out: Path, phase: str, args: dict, pilot: bool, instance: int) -> dict:
    out = Path(out)
    if out.exists():
        raise FileExistsError(f'{out} exists; records are never overwritten')
    core = core_check()
    if not core['ok']:
        raise SystemExit(f'core check failed: {json.dumps(core)[:400]}')
    machine = machine_check(phase, instance, pilot)
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
                'args': args, 'instance': instance, 'machine': machine}
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

    q = sub.add_parser('learn'); common(q, source=False); q.add_argument('--run', type=int, choices=range(5), default=0)
    q.add_argument('--block', type=int, help='second protocol: the matched learning block')
    q.add_argument('--family', choices=('calm', 'threat', 'matched'), help='second protocol: the learning family')
    for name in ('heldout', 'repeat', 'disturb', 'threat'):
        common(sub.add_parser(name))
    common(sub.add_parser('autopilot'), source=False)
    q = sub.add_parser('courses'); common(q, task=False); q.add_argument('--kind', choices=('flat', '3d'), required=True)
    q = sub.add_parser('splits'); common(q, task=False); q.add_argument('--flights', type=int, default=SPLITS_FLIGHTS)
    q = sub.add_parser('gazebo'); common(q, task=False); q.add_argument('--flights', type=int, default=GAZEBO_FLIGHTS)
    a = p.parse_args(argv)
    use_protocol(getattr(a, 'protocol', 1))
    if a.phase == 'check':
        print(json.dumps({'core': core_check(), 'other_simulators': other_simulators(), 'git': git_state(),
                          'seeds_present': SEEDS.exists()}, indent=1))
        return 0
    if a.phase == 'learn':
        return phase_learn(a)
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

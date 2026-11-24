"""Fail-closed protocol-3 evidence gate and one-read analysis snapshot.

Derive the complete schedule from the seed book, verify each completed learning
block and its provenance, receipts, trials and adoption, then derive the distinct
source evaluation schedule. Check every planned outcome against protected logs,
scenario definitions and timing. Missing, corrupt, duplicate or extra evidence
never becomes a zero. A completed non-adoption supplies planned zeros later.

No model, simulator, replacement selection or record mutation occurs here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import contract3 as C
from protocol import freeze3 as F
from protocol.make_seeds_3 import validate as check_seed_book


from ardupilot import scored as S
from ardupilot.ladder import COMMAND_DELAY_PERIODS, COMMAND_DELAY_S, LATE_DIR, REFLIGHTS, WARMUP_DIR, timing


class InvalidEvidence(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise InvalidEvidence(message)


def is_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def reject_constant(value):
    raise InvalidEvidence('Non-finite JSON constant: ' + value)


class Reader:
    """The one place the gate reads a file from. It reads each file once, records the SHA-256 of the bytes under the file's
    name (hashes), and refuses a path that is outside the run root, the folder of set-aside attempts beside it
    (set_aside3.set_aside_dir) and the few named outside files. A file in the set-aside folder is named
    'ROOTNAME.set-aside/...'; an outside file is named '@' and its file name. Build G2."""
    def __init__(self, root, allowed_external=()):
        from protocol.set_aside3 import set_aside_dir
        self.root = root.resolve()
        self.aside = set_aside_dir(self.root).resolve()
        self.allowed_external = {Path(p).resolve() for p in allowed_external}
        self.cache = {}
        self.hashes = {}

    def permitted(self, path) -> bool:
        p = Path(path).resolve()
        return p.is_relative_to(self.root) or p.is_relative_to(self.aside) or p in self.allowed_external

    def name(self, p) -> str:
        if p.is_relative_to(self.root):
            return str(p.relative_to(self.root))
        if p.is_relative_to(self.aside):
            return self.aside.name + '/' + str(p.relative_to(self.aside))
        return '@' + p.name

    def raw(self, path):
        p = Path(path).resolve()
        need(self.permitted(p), 'Evidence symlink escapes the run')
        if p not in self.cache:
            value = p.read_bytes()
            self.cache[p] = value
            self.hashes[self.name(p)] = hashlib.sha256(value).hexdigest()
        return self.cache[p]

    def try_json(self, path):
        """The JSON in a file, or None when the file is absent or does not parse. A path outside the allowed places is
        still refused."""
        need(self.permitted(path), 'Evidence symlink escapes the run')
        try:
            return self.json(path)
        except (OSError, ValueError):
            return None

    def json(self, path):
        return json.loads(self.raw(path), parse_constant=reject_constant)

    def lines(self, path):
        return [json.loads(line, parse_constant=reject_constant) for line in self.raw(path).splitlines() if line.strip()]

    def inside(self, base, relative):
        need(isinstance(relative, str) and relative != '', 'Missing evidence path')
        p = (base / relative).resolve()
        need(not Path(relative).is_absolute() and '..' not in Path(relative).parts and p.is_relative_to(base.resolve()),
             'Evidence path escapes its phase')
        return p

    def log(self, path):
        protected = path.with_name(path.name[:-3] + 'heads') if path.name.endswith('.log') else path.with_name('heads')
        lines = self.raw(path).splitlines()
        heads = self.lines(protected)
        need(lines and len(lines) == len(heads), f'{path}: missing or incomplete protected heads')
        previous = '0' * 64
        payloads = []
        for i, (line, head) in enumerate(zip(lines, heads), 1):
            rec = json.loads(line, parse_constant=reject_constant)
            digest = hashlib.sha256(line).hexdigest()
            need(rec['seq'] == i and rec['prev'] == previous and head['count'] == i and head['head'] == digest,
                 f'{path}: broken protected chain at {i}')
            if i == 1:
                need(head.get('anchor') == digest, f'{path}: missing protected anchor')
            previous = digest
            payloads.append(rec['payload'])
        return payloads


def call_times(payloads) -> dict:
    """Build E2.4. The wall seconds of every sandboxed call in a flight's decision records, as cluster/read_calls.py reads
    them: the procedure's call (each entry of a decision's `tried`) and the guard's (each entry of that call's `checks`).
    A record without a number is skipped, so a fixture with no such fields gives empty lists. Nothing is refused."""
    procedure, guard = [], []
    for p in payloads:
        if not isinstance(p, dict) or p.get('kind') != 'decision':
            continue
        for tried in p.get('tried') or []:
            if not isinstance(tried, dict):
                continue
            if is_number(tried.get('wall_seconds')):
                procedure.append(round(tried['wall_seconds'], 6))
            for check in tried.get('checks') or []:
                if isinstance(check, dict) and is_number(check.get('wall_seconds')):
                    guard.append(round(check['wall_seconds'], 6))
    return {'procedure': procedure, 'guard': guard}


class Run:
    def __init__(self, root, seeds, pilot, protocol_path):
        allowed = [protocol_path, seeds['_path'], S.WHEEL]
        self.root, self.r, self.seeds, self.pilot = root, Reader(root, allowed), seeds, pilot
        self.protocol_path = Path(protocol_path)
        self.expected_phases = set()
        self.expected_flights = set()
        self.expected_requests = set()
        self.expected_calls = set()
        self.expected_usage = set()
        self.trial_identities = {}
        self.bindings = set()
        self.source_fingerprints = set()    # (sha256, file count) of each manifest's source binding
        self.at_once_values = set()
        self.platforms = set()      # (platform, partition, CPU model) of each manifest; a root has one
        self.routes = set()         # the sandbox route each manifest names; a root has one (round five, B2)
        self.kernels = set()        # the kernel release each cluster manifest names; listed, not gated
        self.nodes = set()
        self.settings = set()
        self.checked = Counter()
        self.message_ids = set()    # every message id the root's rows and its file of ids name (build H7: none may be in two roots)
        # report fields that are also given when the gate refuses (message ids, gateway charge, kept-late flights, ...)
        self.extra = {'kept_late_evaluation_flights': {'by_phase': {}, 'by_source': {}}}
        self.protocol_hash = hashlib.sha256(self.r.raw(self.protocol_path)).hexdigest()
        self.wheel_hash = hashlib.sha256(self.r.raw(S.WHEEL)).hexdigest()


    def check_platform(self, name, m, record, limit, load):
        """Round four, ruling 7. On the Mac: the calibrated one-minute load limit held at the phase start. A manifest with
        no platform record is a Mac manifest, so earlier runs still validate. On the cluster the load limit is off, and
        the manifest must instead carry the node's name, at least 3 allowed cores and a recorded nice value of 0."""
        plat = m.get('platform')
        kind = 'mac' if plat is None else (plat.get('platform') if isinstance(plat, dict) else None)
        need(kind in ('mac', 'cluster'), f'{name}: unknown platform record')
        plat_d = plat if isinstance(plat, dict) else {}
        self.platforms.add((kind, plat_d.get('slurm_job_partition'), plat_d.get('cpu_model')))
        if plat_d.get('node'):
            self.nodes.add(plat_d['node'])
        # The nice value is the one scored.power_and_priority() put in machine (both platforms). Present and not 0 is
        # refused everywhere, since the scheduler and every phase refuse to start at another value (last night's Mac
        # runs recorded 5 and are refused on purpose). Absent is read as an older Mac record and refused on the cluster.
        nice = m['machine'].get('nice')
        if nice is not None:
            need(type(nice) is int and nice == 0, f'{name}: nice value {nice!r} is not 0')
        if kind == 'mac':
            need(type(limit) in (int, float) and math.isfinite(limit) and limit >= 0 and load[0] <= limit,
                 f'{name}: no calibrated load limit or load gate failed')
            return
        need(limit is None and record.get('limit_status') == 'not applied (cluster)',
             f'{name}: cluster manifest with a load limit applied or an unmarked load record')
        need(isinstance(plat.get('node'), str) and plat['node'], f'{name}: cluster manifest without the node name')
        cores = plat.get('cores_allowed')
        need(type(cores) is int and cores >= 3, f'{name}: cluster manifest with fewer than 3 allowed cores')
        need(nice is not None, f'{name}: cluster manifest without a recorded nice value')

    def check_route(self, name, folder, m):
        """Round five, B2. A protocol 3 phase names its sandbox route, which is its platform's expected one (written out
        in scored.EXPECTED_ROUTE, so an old wheel cannot satisfy it). A cluster phase, which has a done mark, also holds
        sandbox-end.json, and any holder it replaced was replaced for a stopped call or a socket left behind. Whether a
        replacement is allowed at all is the pilot's rule (pilot_pass3.py), not the gate's."""
        record = m.get('sandbox')
        need(isinstance(record, dict) and isinstance(record.get('route'), str), f'{name}: the manifest names no sandbox route')
        plat = m.get('platform')
        kind = 'mac' if plat is None else plat.get('platform')
        need(record['route'] == S.EXPECTED_ROUTE.get(kind),
             f'{name}: sandbox route {record["route"]!r}, not {S.EXPECTED_ROUTE.get(kind)!r} as the {kind} platform needs')
        self.routes.add(record['route'])
        if kind != 'cluster':
            return
        need(isinstance(record.get('kernel'), str) and record['kernel'], f'{name}: the sandbox record names no kernel release')
        self.kernels.add(record['kernel'])
        end = self.r.json(folder / 'sandbox-end.json')
        need(isinstance(end, dict) and end.get('route') == record['route'] and isinstance(end.get('replacements'), list),
             f'{name}: sandbox-end.json is missing its route or its list of replacements')
        for replacement in end['replacements']:
            need(isinstance(replacement, dict) and replacement.get('reason') in ('stopped', 'residue')
                 and not replacement.get('holder_died'),
                 f'{name}: a holder was replaced for a reason that is neither stopped nor residue, or because it died: '
                 f'{replacement!r}')

    def manifest(self, phase, task, block, source=None):
        name = C.phase_name(phase, task, block, source)
        folder = self.root / name
        self.expected_phases.add(folder.resolve())
        m = self.r.json(folder / 'manifest.json')
        self.r.raw(self.root / 'logs' / (name + '.done'))
        need(m['protocol_version'] == 3 and m['phase'] == phase and m['pilot'] is self.pilot,
             f'{name}: wrong protocol, phase or cohort')
        need(m['args']['task'] == task and type(m['args']['block']) is int and m['args']['block'] == block,
             f'{name}: wrong task/block')
        need(m['seeds_sha256'] == self.seeds['_sha256'] and m['protocol_sha256'] == self.protocol_hash,
             f'{name}: seed/protocol binding differs')
        need(Path(m['protocol']).name == self.protocol_path.name, f'{name}: wrong protocol identity')
        need(m['core']['ok'] is True and m['core']['wheel_sha256'] == self.wheel_hash,
             f'{name}: learning core binding failed')
        source_binding = m['git']['source']
        need(is_hash(source_binding.get('sha256')) and source_binding.get('files', 0) > 0, f'{name}: missing source fingerprint')
        self.bindings.add((m['protocol_sha256'], m['seeds_sha256'], source_binding['sha256'], m['core']['wheel_sha256']))
        self.source_fingerprints.add((source_binding['sha256'], source_binding['files']))
        if not self.pilot:
            need(not m['git'].get('uncommitted_paper3') and not m.get('synthetic'), f'{name}: uncommitted/synthetic scored phase')
        need(type(m['instance']) is int and m['instance'] in (10, 11, 12, 13), f'{name}: wrong instance')
        # The phase guard writes the load record (ardupilot/scored.py, load_check): machine['load'] holds the three
        # load averages and the one-minute limit. The contract gives the manifest to the guard and names no load
        # field (notes/PROTOCOL3-CONTRACT-C3-20261109.md, learn3; notes/PROTOCOL3-SCHEMA-D3-20261109.md, manifest).
        record = m['machine'].get('load')
        need(isinstance(record, dict), f'{name}: missing/invalid measured load')
        load = record.get('load_average_1_5_15')
        limit = record.get('limit_1min')
        need(isinstance(load, list) and len(load) == 3 and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in load),
             f'{name}: missing/invalid measured load')
        self.check_platform(name, m, record, limit, load)
        self.check_route(name, folder, m)
        n = m.get('at_once')
        need(type(n) is int and 1 <= n <= 4, f'{name}: at_once is missing or not an integer from 1 to 4')
        self.at_once_values.add(n)
        need(m['machine'].get('parallel_limit') == n, f'{name}: parallel_limit does not equal at_once {n}')
        others = m['machine'].get('concurrent_sitl_instances')
        need(isinstance(others, list) and len(others) <= n - 1,
             f'{name}: {others!r} simulators were running with at_once {n}; at most {n - 1} may')
        self.checked['phases'] += 1
        return folder, m

    def evaluation(self, phase, task, block, source, roles, case_fn):
        """The manifest of one evaluation phase against the learning block it names. The driver writes the block's
        folder under args['learning'] (ardupilot/scored.py, phase_eval3); the schema asks only that the manifest name
        the learning block (notes/PROTOCOL3-SCHEMA-D3-20261109.md, Evaluation and quality). Returns the phase folder
        and the scheduled cases."""
        folder, manifest = self.manifest(phase, task, block, source)
        cases = case_fn(self.seeds, task, self.pilot)
        a = manifest['args']
        need(a['source_sha256'] == source and a['arms'] == roles['arms'] and a['includes_c0'] is roles['includes_c0']
             and a['cases'] == [c.episode_id for c in cases], f'{folder}: wrong source, roles or evaluation schedule')
        need(isinstance(a['learning'], str) and Path(a['learning']).name == C.phase_name('learn3', task, block),
             f'{folder}: wrong source learning block')
        # The phase flies its cases in its instance's order (round two, ruling 2); the gate checks the order recorded
        # and the order flown against the instance, and returns the flown order.
        flown = [cases[i] for i in C.flight_order(len(cases), manifest['instance'])]
        need(a.get('flight_order') == [c.episode_id for c in flown], f'{folder}: flight order differs from its instance\'s')
        return folder, flown

    def kept_late_evaluation(self, folder, phase, source, case_ids=None) -> set:
        """Ruling 39, point 2. An evaluation phase may hold late flights only when it was kept on its third attempt. Returns
        the episode ids that may be late: empty unless every condition holds, and then those marked kept_late in timing.json.
        All of these must hold, or the run is refused:
          1. the phase folder has kept-late.json;
          2. the set-aside folder holds exactly REFLIGHTS attempts of this phase whose receipt.json names the phase and the
             reason late, each with a flight late by the driver's rule when its own outcome.json files are read again
             (further attempts set aside as crashed are allowed and do not count; one with another reason, or a receipt
             that cannot be read, is refused);
          3. kept-late.json's count and folder names are those attempts';
          4. the flights marked kept_late in timing.json are exactly the late flights of the kept attempt, read again from
             its outcome.json files (Run.flights checks the last part, flight by flight);
          5. (G1) every id in kept-late.json and in a timing row marked late or kept_late is the episode id of a case the phase
             schedules (case_ids), and a set-aside attempt counts only if each of its late flights is such a case.
        case_ids is the set of the phase's scheduled episode ids; None leaves out check 5, which only a test does.        With no kept-late.json, a timing.json that marks any flight kept_late is refused as well."""
        from protocol.set_aside3 import set_aside_dir
        phase_name = folder.name
        marker = folder / 'kept-late.json'
        timing_path = folder / 'timing.json'
        marked = set()
        if timing_path.exists():
            rows = self.r.json(timing_path)
            need(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), f'{folder}: timing.json is not a list of rows')
            marked = {r.get('flight') for r in rows if r.get('kept_late')}
            if case_ids is not None:
                stray = sorted(str(r.get('flight')) for r in rows if (r.get('late') or r.get('kept_late')) and r.get('flight') not in case_ids)
                need(not stray, f'{folder}: timing.json marks a flight late that the phase does not schedule: {stray[:3]}')
            need(all(r.get('kept_late') is True for r in rows if 'kept_late' in r), f'{folder}: kept_late is not true or absent')
        if not marker.exists():
            need(not marked, f'{folder}: flights are marked kept late but the phase has no kept-late.json')
            return set()
        need(timing_path.exists() and marked, f'{folder}: kept-late.json without timing rows that mark a kept late flight')
        record = self.r.json(marker)
        need(isinstance(record, dict) and set(record) == {'late_attempts_set_aside', 'attempt_folders', 'kept_late_flights'},
             f'{marker}: not the record the driver writes')
        if case_ids is not None:
            listed = record['kept_late_flights']
            need(isinstance(listed, list) and all(f in case_ids for f in listed),
                 f'{marker}: it names a kept late flight that the phase does not schedule')
        late_names, late_count = [], 0
        for attempt in sorted(set_aside_dir(self.root).glob(f'{phase_name}-attempt*')):
            suffix = attempt.name[len(phase_name) + len('-attempt'):]
            if not suffix.isdigit():
                continue          # another phase's folder that shares this name's start; its own check judges it
            need(self.r.permitted(attempt / 'receipt.json'), 'Evidence symlink escapes the run')
            try:
                receipt = self.r.json(attempt / 'receipt.json')
            except (OSError, ValueError) as error:
                raise InvalidEvidence(f'{attempt}: the receipt of a set-aside attempt cannot be read ({error})') from error
            need(isinstance(receipt, dict) and receipt.get('phase') == phase_name and receipt.get('attempt') == int(suffix)
                 and receipt.get('reason') in ('late', 'crashed'), f'{attempt}: its receipt does not name this phase and a reason')
            if receipt['reason'] != 'late':
                continue
            outcomes = sorted((attempt / phase_name / 'flights').glob('*/outcome.json'))
            need(outcomes, f'{attempt}: a set-aside attempt with no flights to read again')
            late_flights = []
            for o in outcomes:
                need(self.r.permitted(o), 'Evidence symlink escapes the run')
                try:
                    outcome = self.r.json(o)
                    is_late = timing(outcome)['late']
                except (OSError, ValueError) as error:
                    raise InvalidEvidence(f'{o}: cannot be read ({error})') from error
                self.check_aside_ending(o, outcome)
                if is_late:
                    late_flights.append(o.parent.name)
            need(late_flights, f'{attempt}: set aside as late but no flight in it is late by the driver\'s rule')
            if case_ids is not None and not all(f in case_ids for f in late_flights):
                continue          # a late flight that is no scheduled case is not a late attempt of this phase; it does not count
            late_names.append((int(suffix), attempt.name))
        late_names = [name for _, name in sorted(late_names)]
        need(len(late_names) == REFLIGHTS, f'{marker}: the phase was kept late but the set-aside folder holds '
                                         f'{len(late_names)} attempts set aside as late, not {REFLIGHTS}')
        need(record['late_attempts_set_aside'] == len(late_names) and record['attempt_folders'] == late_names,
             f'{marker}: its count or folder names differ from the attempts in the set-aside folder')
        need(isinstance(record['kept_late_flights'], list) and sorted(record['kept_late_flights']) == sorted(marked),
             f'{marker}: its kept late flights differ from those marked in timing.json')
        self.checked['evaluation phases kept late on the third attempt'] += 1
        self.checked['evaluation flights kept late'] += len(marked)
        by = self.extra['kept_late_evaluation_flights']
        by['by_phase'][phase] = by['by_phase'].get(phase, 0) + len(marked)
        by['by_source'][source] = by['by_source'].get(source, 0) + len(marked)
        return marked

    def set_aside_attempts(self, phase_name, case_ids) -> list:
        """Build E2.5 (ruling 39, point 2). What each attempt of an evaluation phase that was set aside flew, so that the
        analysis can say how many cells differ from the attempt kept. Read for every evaluation phase, not only the phases
        kept late (kept_late_evaluation looks in the set-aside folder only for those). Returns, in attempt order,
        {'attempt', 'reason', 'cells'} where cells maps each scheduled case to its goal_met or None when the attempt has no
        readable outcome for it (a crashed attempt may be partial). Nothing here refuses: the checks on these attempts are
        kept_late_evaluation's, and an attempt the analysis cannot read is shown as unread. Since G2 every file is read through
        the gate's reader, so it is in the record of input hashes, and an outcome that holds a Boolean goal_met is checked
        against its own protected episode log (check_aside_ending): a disagreement refuses. An outcome that is absent, does
        not parse or holds no Boolean stays None and is counted apart by the analysis."""
        from protocol.set_aside3 import set_aside_dir
        found = []
        for attempt in set_aside_dir(self.root).glob(f'{phase_name}-attempt*'):
            suffix = attempt.name[len(phase_name) + len('-attempt'):]
            if not suffix.isdigit() or not attempt.is_dir():
                continue
            receipt = self.r.try_json(attempt / 'receipt.json')
            reason = receipt.get('reason') if isinstance(receipt, dict) else None
            cells = {}
            for case_id in case_ids:
                path = attempt / phase_name / 'flights' / case_id / 'outcome.json'
                o = self.r.try_json(path)
                if isinstance(o, dict) and type(o.get('goal_met')) is bool:
                    self.check_aside_ending(path, o)
                    cells[case_id] = o['goal_met']
                else:
                    cells[case_id] = None
            found.append({'attempt': int(suffix), 'reason': reason, 'cells': cells})
        return sorted(found, key=lambda x: x['attempt'])

    def check_aside_ending(self, path, outcome):
        """G2. A set-aside attempt's outcome that holds a Boolean goal_met is read as a kept outcome is: the flight's own
        protected episode log (beside it, read through the reader) must have exactly one episode_end that gives the same
        goal_met and end_reason. A log that is missing or broken refuses, as does a disagreement. An outcome without a Boolean
        goal_met is not checked here: it stays missing."""
        if not isinstance(outcome, dict) or type(outcome.get('goal_met')) is not bool:
            return
        log = self.r.log(Path(path).parent / 'episode.log')
        ends = [p for p in log if p.get('kind') == 'episode_end']
        need(len(ends) == 1 and (ends[0].get('goal_met'), ends[0].get('end_reason')) == (outcome['goal_met'], outcome.get('end_reason')),
             f'{path}: the outcome of a set-aside attempt disagrees with its protected episode ending')

    def check_trial(self, where, trial, wanted, records=None, task=None, recomputed=None):
        """A trial passes when Telohelm's own trial rule passes on all three layouts (ardupilot/pack.py,
        component_trial): the candidate issued the command at every step, the flight met the goal with the task's
        success ending, no command was refused and no help was requested. That is the rule scored-2 adopted by, and
        the owner ruled that it stands (notes/TAKEOVER-20261111.md, rulings of 11 November, the trial rule). The
        contract's "meeting the goal on all three" was shorthand for it.

        The driver records the rule's verdict for each layout as trial_passed. The gate requires that verdict, checks
        that a layout recorded as passed is not contradicted by its flight record (goal met, the success ending, no
        refusal, no help request), and requires the trial to pass exactly when all three layouts did. A layout that
        met its goal and still failed the rule is accepted on the driver's verdict and counted, so the report shows
        how often the two wordings differ. When recomputed is given (episode id to the verdict that
        pack.component_trial returns from the flight's protected decision log, see trial_verdicts), the driver's verdict
        for each layout must equal it."""
        from ardupilot import pack as P
        shown = [{k: r.get(k) for k in wanted[0]} for r in trial['outcomes']]
        need(shown == wanted, f'{where}: trial/adoption evidence disagrees')
        verdicts = []
        for row in trial['outcomes']:
            verdict = row.get('trial_passed')
            need(type(verdict) is bool, f'{where}: trial/adoption evidence disagrees: a layout has no trial verdict')
            if recomputed is not None:
                need(recomputed.get(row['episode_id']) is verdict,
                     f'{where}: trial/adoption evidence disagrees: the recorded verdict for {row["episode_id"]} is not the '
                     f'trial rule\'s verdict on its decision log')
            if verdict:
                ok = row['goal_met'] is True
                if records is not None:
                    o = records[row['episode_id']]
                    ok = ok and o.get('end_reason') == P.TASKS[task].success and not o.get('refusals') \
                        and not o.get('help_requests')
                need(ok, f'{where}: trial/adoption evidence disagrees: a layout is recorded as passed against its flight')
            elif row['goal_met']:
                self.checked['trial layouts failed with the goal met'] += 1
            verdicts.append(verdict)
        need(trial['passed'] == all(verdicts), f'{where}: trial/adoption evidence disagrees')

    def flights(self, folder, cases, *, source=None, allow_late=False):
        """allow_late: True for a learning call kept late after REFLIGHTS set-aside attempts (round two, ruling 3). For an
        evaluation phase a set of episode ids: those flights must be late and all others on time."""
        from ardupilot import pack as P
        config = self.r.json(folder / 'run-config.json')
        need(C.canonical(config['scenarios']) == C.canonical([asdict(c) for c in cases]), f'{folder}: wrong scheduled scenario parameters')
        need(config.get('speedup') == 1.0, f'{folder}: not real time')
        need(config.get('command_delay_periods') == COMMAND_DELAY_PERIODS,
             f'{folder}: run configuration does not carry the {COMMAND_DELAY_PERIODS}-period command delay')
        if source is not None:
            codes = config['source'] if isinstance(config['source'], list) else [config['source']]
            need(len(codes) == 1 and hashlib.sha256(codes[0].encode()).hexdigest() == source, f'{folder}: wrong flown source')
        rows = self.r.lines(folder / 'results.jsonl')
        ids = [str(row['family']) + '-' + str(row['seed']) for row in rows]
        expected = [c.episode_id for c in cases]
        need(len(ids) == len(set(ids)) and set(ids) == set(expected), f'{folder}: missing, duplicate or extra scenario rows')
        out = {}
        by_id = dict(zip(ids, rows))
        for case in cases:
            d = folder / case.episode_id
            self.expected_flights.add(d.resolve())
            o = self.r.json(d / 'outcome.json')
            need(o['task'] == case.task and type(o['goal_met']) is bool and isinstance(o['end_reason'], str), f'{d}: invalid outcome')
            need(o.get('settled') is True and o.get('model_calls') == 0, f'{d}: incomplete flight or model used during control')
            success = P.TASKS[case.task].success
            valid_end = o['end_reason'] in (success, 'timed_out', 'entered_threat', 'disarmed', 'left_fence',
                                            'ground_contact', 'landed_off_point', 'hard_landing') or o['end_reason'].startswith('autopilot_')
            need(valid_end and o['goal_met'] == (o['end_reason'] == success), f'{d}: invalid terminal classification')
            r = by_id[case.episode_id]
            need(type(r['goal_met']) is bool and (r['goal_met'], r['end_reason']) == (o['goal_met'], o['end_reason']), f'{d}: row/outcome mismatch')
            events = o.get('events', [])
            need(C.canonical(events) == C.canonical(case.events), f'{d}: wrong zone/event definition')
            goal = P.TASKS[case.task].goal(dict(case.params))
            need(all(o['goal'].get(k) == v for k, v in goal.items()), f'{d}: wrong task goal')
            steps = o['native_steps']
            need(isinstance(steps, list) and steps, f'{d}: no timing/trajectory record')
            need(type(o['action_steps']) is int and len(steps) == o['action_steps'] <= P.TASKS[case.task].max_ticks
                 and all(type(s['t']) is int and s['t'] == i for i, s in enumerate(steps, 1)), f'{d}: incomplete/reordered trajectory')
            for s in steps:
                need(all(type(s.get(k)) in (int, float) and math.isfinite(s[k])
                         for k in ('north_m', 'east_m', 'alt_m', 'true_vd_ms', 'truth_age_s')),
                     f'{d}: missing/non-finite simulator truth')
            if o['goal_met']:
                # Native truth is rounded to millimetres; allow its rounding
                # bound, not a new tolerance on the flight's actual goal.
                eps = .001
                if case.task == 'land':
                    final = steps[-1]
                    gap = math.hypot(final['north_m'] - goal['target_north_m'], final['east_m'] - goal['target_east_m'])
                    need(final['alt_m'] <= goal['ground_alt_m'] + eps and gap <= goal['radius_m'] + eps
                         and final['true_vd_ms'] <= goal['touchdown_speed_ms'] + eps,
                         f'{d}: landing success contradicts simulator truth')
                else:
                    n_hold = math.ceil(goal['hold_s'] / P.TASKS[case.task].tick_s)
                    need(len(steps) >= n_hold, f'{d}: insufficient hold witness')
                    for s in steps[-n_hold:]:
                        delta = [s['north_m'] - goal['target_north_m'], s['east_m'] - goal['target_east_m']]
                        if case.task == 'reach3d':
                            delta.append(s['alt_m'] - goal['target_alt_m'])
                        need(math.sqrt(sum(v * v for v in delta)) <= goal['radius_m'] + eps,
                             f'{d}: hold success contradicts simulator truth')
            lag = [s['decision_lag_s'] for s in steps]
            need(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in lag), f'{d}: non-finite/invalid lag')
            # Lateness is the driver's own judgement (ardupilot/ladder.py, timing), so the gate and the driver cannot
            # disagree about which flight is late. The rule is in notes/TAKEOVER-20261111.md, "Late flights".
            # A protocol 3 flight flew with the fixed delay, kept late or not (round four, ruling 2): the late rule's
            # own delay test is not enough, since a kept-late flight is accepted whatever made it late.
            delay = o.get('command_delay_s')
            need(type(delay) in (int, float) and math.isfinite(delay) and abs(delay - COMMAND_DELAY_S) < 1e-9,
                 f'{d}: flown without the {COMMAND_DELAY_S} s command delay')
            if isinstance(allow_late, (set, frozenset)):
                # An evaluation phase: exactly the flights marked kept late are late, as the driver's rule reads them now
                # (Run.kept_late_evaluation), and no other.
                need(timing(o)['late'] == (case.episode_id in allow_late),
                     f'{d}: infrastructure timing fault' if timing(o)['late'] else f'{d}: marked kept late but flown on time')
            else:
                need(allow_late or not timing(o)['late'], f'{d}: infrastructure timing fault')
                if allow_late and timing(o)['late']:
                    self.checked['learning flights kept late after two flights again'] += 1
            log = self.r.log(d / 'episode.log')
            ends = [p for p in log if p.get('kind') == 'episode_end']
            self.r.log(d / 'broker.log')
            need(len(ends) == 1 and (ends[0].get('goal_met'), ends[0].get('end_reason')) == (o['goal_met'], o['end_reason']),
                 f'{d}: protected episode ending disagrees')
            # E2.4: the call times ride with the outcome for the analysis; nothing here is checked against them.
            out[case.episode_id] = {**o, '_call_wall_s': call_times(log)}
            self.checked['unique flights'] += 1
        return out

    def trial_verdicts(self, d, cases, outcomes, task):
        """Telohelm's trial rule (pack.component_trial) for each layout of a flown trial, recomputed from the flight's own
        protected decision log, the flight's outcome and the one procedure adopted in the folder's library, as the
        driver computes it (ardupilot/ladder.py, Block.trial). Returns episode id to passed."""
        from ardupilot import pack as P
        from telohelm.runtime.library import Library
        # Opening a library that is missing a part would create that part. The gate changes no record, so an
        # incomplete library is refused before it is opened.
        store = d / 'library'
        need((store / 'events.log').is_file() and (store / 'contract.json').is_file() and (store / 'content').is_dir(),
             f'{d}: the trial library is missing or incomplete')
        for p in sorted(store.rglob('*')):      # the library package opens its own files; they are read here first, so they are hashed
            if p.is_file():
                self.r.raw(p)
        try:
            adopted = list(Library(store, pack=P.PACKS[task].public).adopted('control', 'procedure'))
        except RuntimeError as error:        # telohelm's LibraryError: a damaged store or another task's contract
            raise InvalidEvidence(f'{d}: the trial library cannot be read: {error}') from error
        need(len(adopted) == 1, f'{d}: expected one adopted procedure in the trial library, found {len(adopted)}')
        out = {}
        for case in cases:
            records = [p for p in self.r.log(d / case.episode_id / 'episode.log') if p.get('kind') == 'decision']
            out[case.episode_id] = P.component_trial('control', adopted[0], outcomes[case.episode_id], records)['passed']
        return out

    def shown_flights(self, folder, req, receipts):
        """The flight folders whose moments the request's text shows, as the driver took them from the core's own record
        of what it kept. They must be among the flights the learner had seen, and no call of the slot may show a flight
        the request did not (a format repair adds text and can only drop more). Returns them as a set."""
        def flights(record, where):
            value = record.get('shown_flights')
            need(isinstance(value, list) and all(isinstance(f, str) for f in value) and len(set(value)) == len(value),
                 f'{where}: shown_flights is missing or is not a list of distinct folders')
            return value
        shown = flights(req, f'{folder}/{req["candidate_id"]}')
        need(set(shown).issubset(req['context_flights']), f'{folder}/{req["candidate_id"]}: shows a flight its learner never saw')
        need(flights(receipts[0], f'{folder}/{req["candidate_id"]}/calls/1') == shown,
             f'{folder}/{req["candidate_id"]}: first call and request disagree on shown_flights')
        for k, receipt in enumerate(receipts[1:], 2):
            need(set(flights(receipt, f'{folder}/{req["candidate_id"]}/calls/{k}')).issubset(shown),
                 f'{folder}/{req["candidate_id"]}: call {k} shows a flight the request did not')
        return set(shown)

    def call_receipts(self, d, meta, calls):
        """The receipts of one candidate's calls, candidates/<id>/calls/<k>.json, numbered from 1. The driver writes
        one for every call, the format repair included, and never overwrites the first. Each names its usage row."""
        calls_dir = d / 'calls'
        names = {p.name for p in calls_dir.iterdir()} if calls_dir.is_dir() else set()
        wanted = {f'{k}.json' for k in range(1, len(meta['call_ids']) + 1)}
        need(names == wanted, f'{d}: call receipts do not match the candidate\'s calls')
        receipts = []
        for k, call_id in enumerate(meta['call_ids'], 1):
            path = calls_dir / f'{k}.json'
            self.expected_calls.add(path.resolve())
            receipt = self.r.json(path)
            row = calls[call_id]
            need(receipt['call_id'] == call_id and receipt['candidate_id'] == meta['candidate_id'] and receipt['call'] == k
                 and receipt['request_sha256'] == row['request_sha256'] and isinstance(receipt['model_payload_json'], str),
                 f'{path}: receipt does not match its usage row')
            receipts.append(receipt)
        return receipts

    def check_payload(self, d, payload, digest):
        """The payload is the list of (role, text) messages the driver sent, and digest hashes its UTF-8 bytes."""
        need(hashlib.sha256(payload.encode()).hexdigest() == digest, f'{d}: request hash mismatch')
        parsed = json.loads(payload, parse_constant=reject_constant)
        need(isinstance(parsed, list) and parsed and all(isinstance(m, list) and len(m) == 2 and all(isinstance(x, str) for x in m)
                                                         for m in parsed), f'{d}: model payload is not a list of messages')

    def requested_settings(self, d, receipt, request):
        """The settings the call requested (C.SETTINGS_FIELD in its receipt, and in request.json for a first call), as
        canonical bytes. The design asks the driver to record them (notes/REWORK-DESIGN-C3-20261108.md, fresh
        generation). A scored run needs a model name among them. A pilot with scripted replies may carry none."""
        got = receipt.get(C.SETTINGS_FIELD)
        if request is not None and C.SETTINGS_FIELD in request:
            need(request[C.SETTINGS_FIELD] == got, f'{d}: request and call receipt disagree on settings')
        named = isinstance(got, dict) and isinstance(got.get('model'), str) and bool(got['model'])
        if got is None or (receipt.get('real_model_call') is False and not named):
            # A scripted reply asked no model: the driver records its settings with no model name.
            need(self.pilot, f'{d}: requested model settings are missing')
            return None
        need(isinstance(got, dict) and isinstance(got.get('model'), str) and got['model'], f'{d}: missing requested model settings')
        return C.canonical(got)

    def learn(self, task, block):
        folder, _ = self.manifest('learn3', task, block)
        data = self.r.json(folder / 'arms.json')
        need(data['schema_version'] == 1 and data['task'] == task and data['block'] == block and set(data['arms']) == set(C.ARMS),
             f'{folder}: invalid arm record')
        need(type(data['c0_zone_qualified']) is bool, f'{folder}: missing pre-fork qualification')
        initial, read_flights = {}, {}
        for label, present in (('P0', False), ('P1', True)):
            cases = C.learning_cases(self.seeds, task, block, self.pilot, threat=present)
            d = folder / 'flights/first' / label
            read_flights[str(d.relative_to(folder))] = self.flights(d, cases, allow_late=self.kept_late(folder, d))
            initial[label] = {str((d / c.episode_id).relative_to(folder)) for c in cases}
        usage = self.r.lines(folder / 'usage.jsonl')
        self.expected_usage.add((folder / 'usage.jsonl').resolve())
        calls = {r['call_id']: r for r in usage}
        need(len(calls) == len(usage), f'{folder}: duplicate usage call')
        for row in usage:
            need(isinstance(row['call_id'], str) and row['call_id'] and is_hash(row['request_sha256']),
                 f'{folder}: missing call identity')
            # The driver marks a call real_model_call, and gives served_by only when a model answered. The schema
            # names served_by for every row (notes/PROTOCOL3-SCHEMA-D3-20261109.md, usage.jsonl), so a scored run
            # needs both. A pilot may use scripted replies, which have no served model.
            real, served = row.get('real_model_call'), row.get('served_by')
            need(real is None or type(real) is bool, f'{folder}: invalid real_model_call')
            need(served is None or (isinstance(served, str) and served), f'{folder}: invalid served label')
            need(self.pilot and real is not True or (isinstance(served, str) and served),
                 f'{folder}: a real call has no served-model label')
            for key in ('input_tokens', 'output_tokens', 'list_cost_usd'):
                v = row.get(key)
                need(v is None or (type(v) in (int, float) and math.isfinite(v) and v >= 0), f'{folder}: invalid usage value')
                if key != 'list_cost_usd':
                    need(v is None or type(v) is int, f'{folder}: token count is not an integer')
            if not self.pilot:
                need(row.get('real_model_call') is True, f'{folder}: unreportable/stub call in scored data')
        candidates, requests, receipts_of = {}, {}, {}
        all_requests, request_ids = [], set()
        for d in sorted((folder / 'candidates').iterdir()):
            need(d.is_dir() and not d.is_symlink(), f'{folder}: unexpected candidate evidence')
            cid = d.name
            need(cid in ('c0', 'c1', 'f1', 'f2', 'rC1', 'rC2', 'rD1', 'rD2'), f'{folder}: unscheduled candidate {cid}')
            meta = self.r.json(d / 'candidate.json')
            req = self.r.json(d / 'request.json')
            self.expected_requests.add((d / 'request.json').resolve())
            need(meta['candidate_id'] == req['candidate_id'] == cid and type(meta['format_valid']) is bool, f'{d}: wrong candidate identity')
            need(isinstance(meta['call_ids'], list) and 1 <= len(meta['call_ids']) <= 2
                 and len(meta['call_ids']) == len(set(meta['call_ids'])) and all(k in calls for k in meta['call_ids']),
                 f'{d}: wrong generation/format-call budget')
            need(all(calls[k]['candidate_id'] == cid for k in meta['call_ids']), f'{d}: usage assigned to another candidate')
            # The driver writes request_id as the candidate's own request identity (one for each candidate, so that f1
            # and f2 differ from c0 in identity alone) and gives each API call its own call_id, in usage.jsonl and in
            # candidates/<id>/calls/<k>.json. The schema names both fields and says they are equal nowhere
            # (notes/PROTOCOL3-SCHEMA-D3-20261109.md, candidate and usage records).
            need(isinstance(req['request_id'], str) and req['request_id'] and req['request_id'] not in request_ids,
                 f'{d}: missing or repeated request identity')
            request_ids.add(req['request_id'])
            receipts = self.call_receipts(d, meta, calls)
            receipts_of[cid] = receipts
            first = receipts[0]
            need(first['model_payload_json'] == req['model_payload_json']
                 and first['request_sha256'] == req['request_sha256'] == calls[meta['call_ids'][0]]['request_sha256'],
                 f'{d}: request hash mismatch')
            self.check_payload(d, req['model_payload_json'], req['request_sha256'])
            for k, receipt in enumerate(receipts):
                self.check_payload(d, receipt['model_payload_json'], receipt['request_sha256'])
                requested = self.requested_settings(d, receipt, req if k == 0 else None)
                if requested is not None:
                    self.settings.add(requested)
                all_requests.append({'candidate_id': cid, 'model_payload_json': receipt['model_payload_json']})
            if len(receipts) == 2:
                need(receipts[1]['request_sha256'] != req['request_sha256'], f'{d}: format repair call repeats the first request')
            # Since 13 November 2026 an empty reply uses up its slot with no format repair, and a reply with text that
            # fails the format always gets one (round three, ruling 8, after the leak inspection's finding 2).
            first_text = (receipts[0].get('reply_text') or '').strip()
            if len(receipts) == 2:
                need(first_text, f'{d}: format repair after an empty reply')
            elif not meta['format_valid']:
                need(not first_text, f'{d}: a reply with text failed the format and got no repair call')
            need(req['parent'] == meta['parent'], f'{d}: inconsistent parent')
            if meta['format_valid']:
                need(is_hash(meta['source_sha256']) and hashlib.sha256(self.r.raw(d / 'source.py')).hexdigest() == meta['source_sha256'], f'{d}: source binding differs')
            else:
                need(meta['source_sha256'] is None and not (d / 'source.py').exists(), f'{d}: invalid-format slot has a source')
            candidates[cid], requests[cid] = meta, req
        need('c0' in candidates and 'c1' in candidates, f'{folder}: initial generation missing')
        need(set(calls) == {k for c in candidates.values() for k in c['call_ids']}, f'{folder}: unlinked/extra calls')
        used, seen_trial_dirs, trial_cache = set(), {}, {}
        for arm in C.ARMS:
            a = data['arms'][arm]
            trials = a['trials']
            sequence = {'A': ['c0', 'f1', 'f2'], 'B': ['c0', 'f1', 'f2'], 'C': ['c0', 'rC1', 'rC2'], 'D': ['c1', 'rD1', 'rD2']}[arm]
            need(type(a['adopted']) is bool and 1 <= len(trials) <= 3 and [r['candidate_id'] for r in trials] == sequence[:len(trials)],
                 f'{folder}/{arm}: missing or skipped candidate slots')
            needed_calls = []
            previous = None
            for i, trial in enumerate(trials):
                cid = trial['candidate_id']
                need(cid in candidates, f'{folder}/{arm}: candidate source missing')
                used.add(cid)
                meta, req = candidates[cid], requests[cid]
                need(type(trial['passed']) is bool and trial['trial_list'] == ('matched' if arm == 'A' else 'threat'),
                     f'{folder}/{arm}: wrong trial manipulation')
                shown = self.shown_flights(folder, req, receipts_of[cid])
                if cid.startswith('r'):
                    need(req['parent'] == previous, f'{folder}/{arm}: repair parent is not its preceding candidate')
                    # The repair-context rule (notes/TAKEOVER-20261111.md, "What a second repair sees"): the driver
                    # keeps every flight its learner has seen. A repair may therefore show its arm's first-round
                    # flights and any earlier trial flight of its own arm, and it must show the trial flights of
                    # the previous valid candidate. A candidate that failed its format was never flown.
                    context = set(req['context_flights'])
                    earlier = [c for c in sequence[:i] if (arm, c) in seen_trial_dirs]
                    allowed = set(initial['P1' if arm == 'D' else 'P0']).union(*(seen_trial_dirs[(arm, c)] for c in earlier))
                    need(context.issubset(allowed), f'{folder}/{arm}: repair uses foreign trial/evaluation context')
                    if earlier:
                        need(seen_trial_dirs[(arm, earlier[-1])].issubset(context), f'{folder}/{arm}: repair omits its trial evidence')
                    # What the text shows (notes/TAKEOVER-20261111.md, "What a repair request shows"; the protocol
                    # draft, section 2.2): only trial flights of its own arm, at least one from the trial just flown.
                    # With no earlier trial (every earlier slot failed its format) the learner has only its own
                    # first-round flights to show.
                    shown_allowed = set().union(*(seen_trial_dirs[(arm, c)] for c in earlier)) if earlier \
                        else set(initial['P1' if arm == 'D' else 'P0'])
                    need(shown.issubset(shown_allowed), f'{folder}/{arm}: repair shows foreign or first-round flights')
                    if earlier:
                        need(shown & seen_trial_dirs[(arm, earlier[-1])], f'{folder}/{arm}: repair shows nothing from the trial just flown')
                else:
                    need(req['parent'] is None and set(req['context_flights']) == initial['P1' if cid == 'c1' else 'P0'],
                         f'{folder}/{cid}: wrong first/fresh examples')
                    need(shown.issubset(initial['P1' if cid == 'c1' else 'P0']),
                         f'{folder}/{cid}: a first or fresh request shows flights beyond its own first-round flights')
                if cid in ('f1', 'f2'):
                    need(req['model_payload_json'] == requests['c0']['model_payload_json'], f'{folder}/{cid}: fresh request contains history')
                needed_calls.extend(meta['call_ids'])
                if meta['format_valid']:
                    cases = C.learning_cases(self.seeds, task, block, self.pilot, threat=arm != 'A')
                    d = self.r.inside(folder, trial['flight_dir'])
                    need(d.is_relative_to((folder / 'flights/trial').resolve()), f'{folder}/{arm}: trial reuses initial/foreign flights')
                    identity = (cid, trial['trial_list'])
                    need(d not in self.trial_identities or self.trial_identities[d] == identity,
                         f'{folder}/{arm}: different candidate slots reuse one trial')
                    self.trial_identities[d] = identity
                    key = (d, cid, arm != 'A')
                    if key not in trial_cache:
                        trial_cache[key] = self.flights(d, cases, source=meta['source_sha256'],
                                                        allow_late=self.kept_late(folder, d))
                    records = trial_cache[key]
                    read_flights[trial['flight_dir']] = records
                    seen_trial_dirs.setdefault((arm, cid), set()).update(str((d / c.episode_id).relative_to(folder)) for c in cases)
                    wanted = [{'episode_id': c.episode_id, 'goal_met': records[c.episode_id]['goal_met'], 'end_reason': records[c.episode_id]['end_reason']} for c in cases]
                    self.check_trial(f'{folder}/{arm}/{cid}', trial, wanted, records, task,
                                     self.trial_verdicts(d, cases, records, task))
                else:
                    need(trial['flight_dir'] is None and not trial['outcomes'] and not trial['passed'], f'{folder}/{cid}: invalid source was trialled')
                need(not trial['passed'] or i == len(trials) - 1, f'{folder}/{arm}: continued after adoption')
                previous = cid
            need(a['call_ids'] == list(dict.fromkeys(needed_calls)), f'{folder}/{arm}: wrong standalone call attribution')
            last = trials[-1]
            need(a['adopted'] == last['passed'], f'{folder}/{arm}: adoption flag differs')
            if a['adopted']:
                need(a['candidate_id'] == last['candidate_id'] and a['source_sha256'] == candidates[last['candidate_id']]['source_sha256'], f'{folder}/{arm}: adopted wrong source')
            else:
                need(len(trials) == 3 and a['candidate_id'] is None and a['source_sha256'] is None, f'{folder}/{arm}: incomplete run reported as non-adoption')
        need(set(candidates) == used, f'{folder}: generated unused candidates')
        bt, ct = data['arms']['B']['trials'][0], data['arms']['C']['trials'][0]
        need(bt == ct and data['c0_zone_qualified'] == bt['passed'], f'{folder}: B/C do not share the pre-fork trial')
        forbidden = set()
        for cohort in (self.seeds, self.seeds['pilot']):
            for field in ('threat_evaluation', 'heldout'):
                forbidden.update(seed for row in cohort[field].values() for values in row.values() for seed in values)
        # Every learning seed of both books too, the run's own included: a request names a learning layout only by its
        # alias (leak inspection, finding 1, 13 November 2026), so no seed number may appear in its text.
        for cohort in (self.seeds, self.seeds['pilot']):
            forbidden.update(seed for blocks in cohort['blocks'].values() for block in blocks for seed in block.values())
        for req in all_requests:
            numbers = [float(v) for v in re.findall(r'(?<![A-Za-z0-9_])(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?![A-Za-z0-9_])', req['model_payload_json'])]
            need(not any(math.isfinite(v) and v in forbidden for v in numbers), f'{folder}/{req["candidate_id"]}: reserved seed leaked into request')
        self.late_attempts(folder)
        self.checked['learning blocks'] += 1
        # E2.4: what the analysis needs and the gate did not hand over. The rows of timing.json (calls flown again and
        # flights kept late, by call), or None where the block has none, and the flights read, by the folder they are in.
        rows = None
        if (folder / 'timing.json').exists():
            found = self.r.json(folder / 'timing.json')
            if isinstance(found, list) and all(isinstance(r, dict) for r in found):
                rows = found
        return {'arms_record': data, 'candidates': candidates, 'usage': usage, 'timing': rows, 'flights': read_flights}

    @staticmethod
    def kept_late(folder, d) -> bool:
        """A learning call may hold a late flight only when REFLIGHTS earlier attempts of it were set aside."""
        aside = Path(folder) / LATE_DIR / Path(d).resolve().relative_to(Path(folder).resolve())
        return len([a for a in aside.glob('attempt-*') if a.is_dir()]) == REFLIGHTS

    def late_attempts(self, folder):
        """Round two, ruling 3: a learning call with a late flight was moved, unread, to folder/late/<call>/attempt-<k>
        and flown again. Each set-aside attempt must belong to a call the block kept, with the same source, cases and
        settings; attempts are numbered from 1 with none missing and at most REFLIGHTS of them; each has a flight late
        by the driver's rule; and their protected logs verify. These folders are left out of the sweep of flights and
        of the counts, as the warm-up is."""
        base = Path(folder) / LATE_DIR
        if not base.exists():
            return
        calls, verified = {}, set()
        for a in sorted(base.rglob('attempt-*')):
            if a.is_dir():
                calls.setdefault(a.parent, []).append(a)
        for parent, attempts in calls.items():
            kept = Path(folder) / parent.relative_to(base)
            names = sorted(a.name for a in attempts)
            need(len(attempts) <= REFLIGHTS and names == sorted(f'attempt-{i}' for i in range(1, len(attempts) + 1)),
                 f'{parent}: set-aside attempts misnumbered or too many')
            need((kept / 'run-config.json').is_file(), f'{parent}: set aside for a call the block did not keep')
            want = self.r.json(kept / 'run-config.json')
            for a in attempts:
                need(self.r.json(a / 'run-config.json') == want, f'{a}: not the same call as {kept}')
                outcomes = sorted(a.glob('*/outcome.json'))
                verified.update(o.resolve() for o in outcomes)
                need(outcomes and len(outcomes) == len(want['scenarios']), f'{a}: incomplete set-aside attempt')
                need(any(timing(self.r.json(o))['late'] for o in outcomes), f'{a}: set aside with no late flight')
                for o in outcomes:
                    self.r.log(o.parent / 'episode.log')
                    self.r.log(o.parent / 'broker.log')
                self.checked['learning calls set aside as late and flown again'] += 1
        stray = {o.resolve() for o in base.rglob('outcome.json')} - verified
        need(not stray, f'{base}: flights outside a set-aside attempt: {sorted(map(str, stray))[:3]}')


def evaluation_plan(arms, candidates) -> dict:
    """The evaluation phases of one learning block, as the scheduler plans them (run_scored3.evaluation_jobs) and the driver
    records their roles (scored._evaluated_source): {'threat3': {source: roles}, 'retain3': {source: roles}}.
    Roles are {'arms': the arms that adopted the source, 'includes_c0': whether it is c0's own source}, the same for both
    phases. threat3 flies every adopted source and c0's source even when no arm adopted it. retain3 flies a source only
    when some arm adopted it. So a retain3 phase of c0's own source, where an arm adopted c0, has includes_c0 True. Both
    this and the scheduler read contract3.source_roles with include_c0=True; a test compares the two."""
    roles = C.source_roles(arms, candidates, include_c0=True)
    return {'threat3': dict(roles), 'retain3': {h: r for h, r in roles.items() if r['arms']}}


LEDGER_FILES = ('usage.jsonl', 'claude-usage.jsonl')
GATEWAY_CACHE = 'no-cache,no-store'     # written out here, as the gate's own demand; the provider's note must equal it
RUN_MESSAGE_IDS = 'message-ids.jsonl'   # the provider's file of every message id of the run, in the run root; a test says it equals claude_provider.RUN_MESSAGE_IDS


def ledger_rows(root, reader=None) -> list:
    """Every usage row of the run, as (path, row): the driver's usage.jsonl and the provider's claude-usage.jsonl of each
    learning block in the run root, and of each learning block set aside beside it (set_aside3.set_aside_dir). A row that
    does not parse is refused: a finished run has none. With a reader (the gate's), each file is read through it."""
    from protocol.set_aside3 import set_aside_dir
    root = Path(root)
    paths = []
    for name in LEDGER_FILES:
        paths += sorted(root.glob(f'learn3-*/{name}'))
        paths += sorted(set_aside_dir(root).glob(f'learn3-*-attempt*/learn3-*/{name}'))
    rows = []
    for path in paths:
        for number, line in enumerate((reader.raw(path) if reader else path.read_bytes()).splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line, parse_constant=reject_constant)
            except ValueError as error:
                raise InvalidEvidence(f'{path}: line {number} of a usage file does not parse ({error})') from error
            need(isinstance(row, dict), f'{path}: line {number} of a usage file is not an object')
            rows.append((path, row))
    return rows


def is_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def gateway_route(run) -> bool:
    """True when any of the run's requested settings names the gateway route (via 'gem')."""
    return any(isinstance(x, dict) and x.get('via') == 'gem' for x in (json.loads(blob) for blob in run.settings))


def read_run_message_ids(run) -> list:
    """The ids in ROOT/message-ids.jsonl (the provider's file for the whole run, claude_provider.RUN_MESSAGE_IDS), read through
    the gate's own reader. A line that does not parse as JSON is a claim cut short by a crash: claude_provider.RunMessageIds.claim()
    starts a new line after such a fragment, so it is skipped, counted (run.extra['message_id_file_fragments']) and never
    refused (build G7, ruling 51; a claim is written before its reply is accepted, so a cut claim stands for no accepted reply).
    That covers a fragment in the middle of the file and a final one with no newline after it. Every line that does parse must be
    a JSON object with exactly the keys message_id and block, both text, and an id may be in the file once. No file is no ids.
    Returns the ids in file order."""
    path = Path(run.root) / RUN_MESSAGE_IDS
    if not path.exists():
        return []
    *finished, last = run.r.raw(path).split(b'\n')       # the last part is empty when the file ends in a newline
    ids = []
    for number, line in enumerate([*finished, *([last] if last else [])], 1):
        try:
            row = json.loads(line, parse_constant=reject_constant)
        except ValueError:
            run.extra['message_id_file_fragments'] += 1
            continue
        need(isinstance(row, dict) and set(row) == {'message_id', 'block'},
             f'{path}: line {number} is not an object with exactly the keys message_id and block')
        need(isinstance(row['message_id'], str) and row['message_id'] and isinstance(row['block'], str),
             f'{path}: line {number} has a message_id or a block that is not text')
        ids.append(row['message_id'])
    need(len(ids) == len(set(ids)), f'{path}: a message id is in the file more than once, so two calls claimed it')
    return ids


def check_message_ids(run, rows):
    """E1.2 (ruling 37, point 9), changed by E3.8 (ruling 47, point 2). A message id is minted once for each reply, so one that
    appears for two answered calls is a stored copy of an earlier reply. The gate refuses a run with any, across the run root and
    its set-aside attempts. A provider row the provider logged as copied is a copy that was caught: it is accepted in a learning
    attempt that was set aside (the block was flown again) and counted, and refused anywhere in the kept run. A call is named by
    its call_id (the driver's row) or request_id (the provider's); the same call in both files is one.
    On the gateway route every provider row with a message id must have that id in ROOT/message-ids.jsonl, and the file must be
    sound (read_run_message_ids). An id in the file with no provider row is counted and not refused: a process killed after
    it claimed the id and before it logged the row leaves one.
    Report fields, also given when the gate refuses: message_id_file_fragments (G7), repeated_message_ids, message_ids_seen, rows_logged_as_copied (all copied
    rows), copies_caught (copied rows in set-aside attempts) and message_ids_in_file_with_no_row."""
    from protocol.set_aside3 import set_aside_dir
    aside = Path(set_aside_dir(run.root)).resolve()
    calls_by_id, copied, caught = {}, [], 0
    for path, row in rows:
        if row.get('status') == 'copied':
            if Path(path).resolve().is_relative_to(aside):
                caught += 1
            else:
                copied.append(str(path))
            continue
        mid = row.get('message_id')
        if mid is not None:
            calls_by_id.setdefault(mid, []).append((str(path), row.get('call_id', row.get('request_id'))))
    repeated = sorted(mid for mid, uses in calls_by_id.items()
                      if len({call for _, call in uses}) > 1 or len(uses) > len(set(uses)))
    run.extra['repeated_message_ids'] = len(repeated)
    run.extra['message_ids_seen'] = len(calls_by_id)
    run.extra['rows_logged_as_copied'] = len(copied) + caught
    run.extra['copies_caught'] = caught
    run.extra['message_ids_in_file_with_no_row'] = 0
    run.extra['message_id_file_fragments'] = 0
    run.message_ids = set(calls_by_id)
    need(not copied, f'{len(copied)} usage rows in the kept run are logged as copied, a stored reply and not an answer; first in '
                     f'{copied[0]}' if copied else '')
    need(not repeated, f'{len(repeated)} message ids appear for more than one call (stored copies of earlier replies); '
                       f'first {repeated[0]} in {calls_by_id[repeated[0]][0][0]}' if repeated else '')
    if not gateway_route(run):
        return
    in_file = read_run_message_ids(run)
    claimed = set(in_file)
    run.message_ids |= claimed
    on_rows = {row['message_id'] for path, row in rows if path.name == 'claude-usage.jsonl' and row.get('message_id') is not None}
    run.extra['message_ids_in_file_with_no_row'] = len(claimed - on_rows)
    missing = sorted(on_rows - claimed)
    need(not missing, f'{len(missing)} provider rows have a message id that is not in {RUN_MESSAGE_IDS}, so the claim that would '
                      f'have caught a copy was never made; first {missing[0]}' if missing else '')


def check_ledger_pairing(run, rows):
    """Build G6 (ruling 50, point 3). The provider writes its row (claude-usage.jsonl, request_id) and then the ladder writes
    the spending row (usage.jsonl, call_id) for the same call, in the same block folder. A process killed between the two leaves
    a provider row with no spending row, which the spending stop does not count. Rows are paired by those ids within each
    folder, in the run and in every set-aside attempt.
      - A provider row with no spending row in a block that was set aside is counted, and its list cost and its charge, where it
        has one, are summed. In a kept block it refuses, since a block whose process died is always set aside.
      - A spending row whose requested settings name the gateway route (via 'gem') and that has no provider row refuses
        anywhere: the provider's row is written first, so none can be missing.
    J2: the pairing is one to one by id. A request id with more provider rows than spending rows leaves the rows past the number
    of spending rows (in file order) with no partner, and they are treated as above: refused in a kept block, counted in a
    set-aside block.
    L2: the same in the other direction. A request id with more gateway spending rows than provider rows leaves the spending rows
    past the number of provider rows (in file order) with no partner: refused in a kept block; in a set-aside block counted in
    spending_rows_with_no_provider_row (count, the list cost of those with a price, and how many have none). Their cost is already in
    the set-aside spend, because the spending rows are in it, so it is not added again.
    Report field, also given when the gate refuses: provider_rows_with_no_spending_row, with the count, the list cost of the rows
    that have a price (a known subtotal), rows_without_list_cost (J1: calls of unknown cost), and the charge and the number of
    rows that have one. Rows that do not name an id are not paired and not counted."""
    from protocol.set_aside3 import set_aside_dir
    aside = Path(set_aside_dir(run.root)).resolve()
    by_folder = {}
    for path, row in rows:
        entry = by_folder.setdefault(Path(path).parent, {'spending': {}, 'provider': {}, 'spending_rows': []})
        if path.name == 'usage.jsonl':
            entry['spending_rows'].append(row)
            if isinstance(row.get('call_id'), str):
                entry['spending'][row['call_id']] = entry['spending'].get(row['call_id'], 0) + 1
        elif path.name == 'claude-usage.jsonl' and isinstance(row.get('request_id'), str):
            entry['provider'].setdefault(row['request_id'], []).append(row)
    count, listed, charged, charged_rows, no_price = 0, 0.0, 0.0, 0, 0
    kept_unpaired, gateway_unpaired, kept_surplus = [], [], []
    surplus_count, surplus_listed, surplus_no_price = 0, 0.0, 0
    for folder, entry in sorted(by_folder.items(), key=lambda kv: str(kv[0])):
        for request_id, provider_rows in entry['provider'].items():
            # J2: one provider row pairs with one spending row. The rows with no partner are the ones past the number of
            # spending rows, in the order of the file.
            unpaired_rows = provider_rows[entry['spending'].get(request_id, 0):]
            if not unpaired_rows:
                continue
            if not folder.resolve().is_relative_to(aside):
                kept_unpaired.extend((str(folder), request_id) for _ in unpaired_rows)
                continue
            for row in unpaired_rows:
                count += 1
                if is_number(row.get('cost_usd')):
                    listed += row['cost_usd']
                else:
                    no_price += 1       # J1: a call cut off before its usage arrived has no price; it is not a price of zero
                if is_number(row.get('charged_usd')):
                    charged += row['charged_usd']
                    charged_rows += 1
        seen_ids = {}
        for row in entry['spending_rows']:
            settings = row.get(C.SETTINGS_FIELD)
            gateway = isinstance(settings, dict) and settings.get('via') == 'gem'
            call_id = row.get('call_id')
            if gateway and call_id not in entry['provider']:
                gateway_unpaired.append((str(folder), call_id))
            elif gateway and isinstance(call_id, str):
                # L2: the pairing is one to one in this direction too. The spending rows of an id past the number of provider rows
                # for it, in file order, have no partner.
                seen_ids[call_id] = seen_ids.get(call_id, 0) + 1
                if seen_ids[call_id] > len(entry['provider'][call_id]):
                    if not folder.resolve().is_relative_to(aside):
                        kept_surplus.append((str(folder), call_id))
                    else:
                        surplus_count += 1
                        if is_number(row.get('list_cost_usd')):
                            surplus_listed += row['list_cost_usd']
                        else:
                            surplus_no_price += 1
    run.extra['provider_rows_with_no_spending_row'] = {'count': count, 'list_cost_usd': round(listed, 6),
                                                       'charged_usd': round(charged, 6), 'rows_with_charge': charged_rows,
                                                       'rows_without_list_cost': no_price}
    run.extra['spending_rows_with_no_provider_row'] = {'count': surplus_count, 'list_cost_usd': round(surplus_listed, 6),
                                                       'rows_without_list_cost': surplus_no_price}
    need(not kept_surplus, f'{len(kept_surplus)} spending rows on the gateway route in a kept block have no provider row of their own '
                           f'(more spending rows than provider rows for one request id); first {kept_surplus[0][1]} in {kept_surplus[0][0]}'
         if kept_surplus else '')
    need(not kept_unpaired, f'{len(kept_unpaired)} provider rows in a kept block have no spending row, though a block whose process '
                            f'died is set aside; first {kept_unpaired[0][1]} in {kept_unpaired[0][0]}' if kept_unpaired else '')
    need(not gateway_unpaired, f'{len(gateway_unpaired)} spending rows on the gateway route have no provider row, which is written '
                               f'first; first {gateway_unpaired[0][1]} in {gateway_unpaired[0][0]}' if gateway_unpaired else '')


def check_gateway(run, rows):
    """E1.3 (ruling 37, point 9). When the requested settings name the gateway route (via 'gem'), the settings and every row
    of the provider's log on that route say the request switched off the gateway's store of replies, and a reply's row has
    the gateway's charge as a number or null. The report gives the charge beside the list price."""
    named = [json.loads(blob) for blob in run.settings]
    if not gateway_route(run):
        return
    for x in named:
        need(x.get('via') == 'gem' and x.get('gateway_cache') == GATEWAY_CACHE,
             f'the requested settings name the gateway route but not gateway_cache {GATEWAY_CACHE!r}: {x!r}')
    charged = listed = listed_where_charged = 0.0
    with_charge = without = 0
    provider = [(p, r) for p, r in rows if p.name == 'claude-usage.jsonl']
    for path, row in provider:
        need(row.get('via') == 'gem' and row.get('gateway_cache') == GATEWAY_CACHE,
             f'{path}: a row of a gateway run without gateway_cache {GATEWAY_CACHE!r}: {row.get("request_id")!r}')
        if 'charged_usd' in row:
            need(row['charged_usd'] is None or is_number(row['charged_usd']), f'{path}: charged_usd is neither a number nor null')
        if row.get('message_id') is None:
            continue        # a call that got no reply has no charge to record
        need('charged_usd' in row, f'{path}: a reply row of a gateway run has no charged_usd')
        if is_number(row.get('cost_usd')):
            listed += row['cost_usd']
        if row['charged_usd'] is None:
            without += 1
        else:
            with_charge += 1
            charged += row['charged_usd']
            if is_number(row.get('cost_usd')):
                listed_where_charged += row['cost_usd']
    run.extra['gateway_charge'] = {'provider_rows': len(provider), 'reply_rows': with_charge + without,
                                   'charged_usd_sum': round(charged, 6), 'rows_with_charge': with_charge,
                                   'rows_without_charge': without, 'list_usd_sum_all_replies': round(listed, 6),
                                   'list_usd_sum_where_charged': round(listed_where_charged, 6)}


def frozen_differences(frozen, observed) -> list:
    """What differs between the frozen values and what the run's records and the repository show, as sentences. observed has
    the same keys as protocol/FROZEN-3.json (freeze3.KEYS) with each value as the run shows it; a value that more than one
    manifest could carry differently is given as a list of what was seen."""
    out = []
    if not isinstance(frozen, dict):
        return ['the frozen values file is not an object']
    for key in F.KEYS:
        if key not in frozen:
            out.append(f'{key} is missing from the frozen values')
    for key in F.KEYS:
        if key not in frozen:
            continue
        if key == 'platform':
            want = {k: (frozen[key] or {}).get(k) for k in ('partition', 'node_type', 'cpu_model')}
            if observed[key] != [want]:
                out.append(f'platform: the run shows {observed[key]}, the frozen values {want}')
        elif key == 'source_fingerprint':
            want = {'sha256': (frozen[key] or {}).get('sha256'), 'files': (frozen[key] or {}).get('files')}
            if observed[key] != [want]:
                out.append(f'source_fingerprint: the run shows {observed[key]}, the frozen values {want}')
        elif observed[key] != frozen[key]:
            out.append(f'{key}: the run shows {observed[key]}, the frozen values {frozen[key]}')
    return out


def check_frozen(run, frozen_path=None):
    """E1.6 (ruling 39, point 5). A scored run must match protocol/FROZEN-3.json, which freeze3.py writes once at the freeze.
    The gate refuses when the file is absent or any value differs: the source fingerprint and the platform as every manifest
    records them, the wheel, seed book and protocol text as the gate itself hashed them, and the two expectation files as they
    stand in the repository (no run record holds those two). The platform's node type is the node name without its number."""
    path = Path(frozen_path) if frozen_path else F.FROZEN_PATH
    need(path.is_file(), f'{path} is absent; a scored run is judged against the frozen values, written once at the freeze')
    try:
        run.r.allowed_external.add(path.resolve())
        frozen = json.loads(run.r.raw(path), parse_constant=reject_constant)
    except ValueError as error:
        raise InvalidEvidence(f'{path} cannot be read ({error})') from error
    def file_hash(p):       # the expectation files are read through the reader too, so they are in the record of input hashes
        if not Path(p).is_file():
            return None
        run.r.allowed_external.add(Path(p).resolve())
        return hashlib.sha256(run.r.raw(p)).hexdigest()
    types = {F.node_type(n) for n in run.nodes} or {None}
    platforms = sorted({(part, kind, cpu) for (_, part, cpu) in run.platforms for kind in types}, key=str)
    observed = {
        'source_fingerprint': [{'sha256': a, 'files': b} for a, b in sorted(run.source_fingerprints)],
        'wheel_sha256': run.wheel_hash, 'seeds_sha256': run.seeds['_sha256'], 'protocol_sha256': run.protocol_hash,
        'delay_check_expected_sha256': file_hash(F.DELAY_EXPECTED),
        'pilot_adoption_sha256': file_hash(F.PILOT_ADOPTION),
        'platform': [{'partition': part, 'node_type': kind, 'cpu_model': cpu} for part, kind, cpu in platforms]}
    differences = frozen_differences(frozen, observed)
    run.extra['frozen_values'] = {'file': str(path), 'differences': differences}
    need(not differences, f'the run differs from the frozen values ({path.name}): ' + '; '.join(differences))


def schedule_tasks(root, reader=None):
    """Build H7 (ruling 53). The tasks a run root flies, from the schedule the scheduler wrote at its first start
    (logs/schedule.json, 'tasks', written by run_scored3.py --tasks). Returns (tasks in the order of contract3.TASKS, whether the
    file named them). A root with no schedule file, or one written before --tasks existed, flies all three, as before."""
    path = Path(root) / 'logs' / 'schedule.json'
    if not path.exists():
        return list(C.TASKS), False
    schedule = json.loads(reader.raw(path) if reader else path.read_bytes(), parse_constant=reject_constant)
    need(isinstance(schedule, dict), f'{path} is not an object')
    if 'tasks' not in schedule:
        return list(C.TASKS), False
    tasks = schedule['tasks']
    need(isinstance(tasks, list) and tasks and all(isinstance(x, str) for x in tasks) and len(set(tasks)) == len(tasks)
         and set(tasks) <= set(C.TASKS), f'{path}: tasks must be a list of tasks from {list(C.TASKS)}, each once; got {tasks!r}')
    return [x for x in C.TASKS if x in tasks], True


def session_stops(root, pilot, reader=None, tasks=None) -> dict:
    """E1.5 (ruling 39, point 3). The spending stop of every scheduler session, read from the start and resume events in
    logs/pauses.jsonl, which run_scored3 writes with spend_limit_usd (the stop in force) and spend_limit_from_flag (whether
    --spend-limit set it). Returns {'sessions': [...in order...], 'other': [...]}. A scored run's sessions must all have
    run_scored3.SPEND_LIMIT_USD_3 as their stop; one that does not is listed under 'other' and reported, never refused,
    since a stop that trips late has to be raisable. An event with no such fields, or fields that are not a finite number
    at least 0 and a true or false, is refused in a scored run; in a pilot a missing field is reported as 'unknown'.
    A scored run with no start event at all is refused."""
    from protocol import run_scored3 as R3
    path = Path(root) / 'logs' / 'pauses.jsonl'
    events = []
    if path.exists():
        for number, line in enumerate((reader.raw(path) if reader else path.read_bytes()).splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line, parse_constant=reject_constant)
            except ValueError as error:
                raise InvalidEvidence(f'{path}: line {number} does not parse ({error})') from error
            need(isinstance(row, dict), f'{path}: line {number} is not an object')
            if row.get('event') in ('start', 'resume'):
                events.append(row)
    need(pilot or any(e['event'] == 'start' for e in events), f'{path}: the scheduler logged no start event')
    sessions, other = [], []
    for row in events:
        stop, flag = row.get('spend_limit_usd', 'unknown'), row.get('spend_limit_from_flag', 'unknown')
        for key, value, ok in (('spend_limit_usd', stop, is_number(stop)), ('spend_limit_from_flag', flag, type(flag) is bool)):
            if value == 'unknown' and key not in row:
                need(pilot, f'{path}: a {row["event"]} event at {row.get("time")} has no {key}')
            else:
                need(ok, f'{path}: a {row["event"]} event at {row.get("time")} has {key} {value!r}')
        if tasks is not None and 'tasks' in row:
            need(row['tasks'] == list(tasks), f'{path}: a {row["event"]} event at {row.get("time")} flew the tasks {row["tasks"]!r}, '
                                              f'not the schedule\'s {list(tasks)!r}')
        entry = {'event': row['event'], 'time': row.get('time'), 'spend_limit_usd': stop, 'spend_limit_from_flag': flag}
        sessions.append(entry)
        if not pilot and stop != R3.SPEND_LIMIT_USD_3:
            other.append(entry)
    return {'sessions': sessions, 'other': other}


def set_aside_learning(root, rows, reader=None) -> list:
    """Build E2.4 and E2.6. The learning blocks set aside beside the run root (set_aside3.set_aside_dir), each with its
    receipt's reason and crash evidence and its usage rows: the driver's (usage.jsonl) and the provider's
    (claude-usage.jsonl), from the rows ledger_rows read. An unreadable receipt gives reason None; nothing here refuses."""
    from protocol.set_aside3 import set_aside_dir
    base = set_aside_dir(root)
    out = []
    for attempt in sorted(base.glob('learn3-*-attempt*')):
        phase, _, suffix = attempt.name.rpartition('-attempt')
        if not suffix.isdigit() or not attempt.is_dir():
            continue
        if reader:
            receipt = reader.try_json(attempt / 'receipt.json')
        else:
            try:
                receipt = json.loads((attempt / 'receipt.json').read_bytes(), parse_constant=reject_constant)
            except (OSError, ValueError):
                receipt = None
        receipt = receipt if isinstance(receipt, dict) else {}
        evidence = receipt.get('crash_evidence')
        mine = [(p, r) for p, r in rows if attempt in Path(p).parents]
        out.append({'phase': phase, 'attempt': int(suffix), 'reason': receipt.get('reason'),
                    'crash_evidence_kind': evidence.get('kind') if isinstance(evidence, dict) else None,
                    'usage': [r for p, r in mine if Path(p).name == 'usage.jsonl'],
                    'provider': [r for p, r in mine if Path(p).name == 'claude-usage.jsonl']})
    return sorted(out, key=lambda x: (x['phase'], x['attempt']))


def pilot_blocks(root, book_blocks, reader=None):
    """How many learning blocks of each task a pilot scheduled. A pilot may fly fewer blocks than the development
    book holds (run_scored3.py --pilot --blocks N). The scheduler writes its queue to logs/schedule.json at the first
    start and refuses a later session whose queue differs, so the gate reads the pilot's schedule from there. Without
    that file the whole development book is expected. A scored run never uses this: its schedule is the seed book."""
    path = Path(root) / 'logs' / 'schedule.json'
    if not path.exists():
        return dict(book_blocks)
    schedule = json.loads(reader.raw(path) if reader else path.read_bytes(), parse_constant=reject_constant)
    need(schedule.get('pilot') is True, 'The schedule on file is not a pilot schedule')
    found = {task: [] for task in book_blocks}      # the tasks this root flies (all three, or the one a split run flies)
    for name, _ in schedule['learning']:
        m = re.fullmatch(r'learn3-([a-z0-9]+)-b(\d+)', name)
        need(m is not None and m.group(1) in found, f'Unknown phase in the pilot schedule: {name}')
        found[m.group(1)].append(int(m.group(2)))
    counts = {}
    for task, blocks in found.items():
        need(sorted(blocks) == list(range(len(blocks))) and 1 <= len(blocks) <= book_blocks[task],
             f'The pilot schedule for {task} is not the leading blocks of the development book')
        counts[task] = len(blocks)
    need(len(set(counts.values())) == 1, 'The pilot schedule has different numbers of blocks for the tasks')
    return counts


def load_run(root, *, pilot=False, seed_path=C.SEED_PATH, protocol_path=None, frozen_path=None, judge_frozen=None, allow_partial=False):
    """Return (report, immutable-by-convention verified in-memory snapshot). A scored run (not pilot) is also judged against
    the frozen values (check_frozen); judge_frozen=True asks for that of a pilot too, which only tests do. A root whose schedule
    names fewer than the three tasks (a split run's root, build H7) is refused unless allow_partial is true, which load_runs
    sets and judges the three roots together."""
    judge_frozen = (not pilot) if judge_frozen is None else judge_frozen
    root = Path(root).resolve()
    report = {'ok': False, 'errors': [], 'checked': {}, 'pilot': pilot}
    snapshot = None
    run = None
    try:
        seed_path = Path(seed_path).resolve()
        need(pilot or seed_path == C.SEED_PATH.resolve(), 'Scored checks cannot substitute a smaller seed plan')
        seed_bytes = seed_path.read_bytes()
        seeds = json.loads(seed_bytes, parse_constant=reject_constant)
        check_seed_book(seeds, scan_runs=False)
        protocol_path = Path(protocol_path) if protocol_path else ROOT / ('PROTOCOL-3-DRAFT.md' if pilot else 'PROTOCOL-3.md')
        need(pilot or protocol_path.resolve() == (ROOT / 'PROTOCOL-3.md').resolve(), 'Scored checks require the frozen protocol')
        seeds['_sha256'] = hashlib.sha256(seed_bytes).hexdigest()
        seeds['_path'] = str(seed_path)
        run = Run(root, seeds, pilot, protocol_path)
        run.r.cache[seed_path] = seed_bytes
        seed_key = str(seed_path.relative_to(root)) if seed_path.is_relative_to(root) else '@' + seed_path.name
        run.r.hashes[seed_key] = seeds['_sha256']
        tasks, tasks_on_file = schedule_tasks(root, run.r)
        need(allow_partial or tasks == list(C.TASKS), f'this run root flies only {tasks} (its schedule says so); a split run is judged '
             f'with the roots of the other tasks, all three given together')
        learning, hazard, retention = {t: {} for t in tasks}, {}, {}
        kept_late_eval, evaluation_attempts = {}, []
        cohort = C.book(seeds, pilot)
        blocks = {task: len(cohort['blocks'][task]) for task in tasks}
        if pilot:
            blocks = pilot_blocks(root, blocks, run.r)
        for task in tasks:
            for block in range(blocks[task]):
                learn = run.learn(task, block)
                learning[task][block] = learn
                plan = evaluation_plan(learn['arms_record']['arms'], learn['candidates'])
                for phase, case_fn, target in (('threat3', C.evaluation_cases, hazard), ('retain3', C.retention_cases, retention)):
                    for h, roles in plan[phase].items():
                        folder, flown = run.evaluation(phase, task, block, h, roles, case_fn)
                        marked = run.kept_late_evaluation(folder, phase, h, {c.episode_id for c in flown})
                        records = run.flights(folder / 'flights', flown, source=h, allow_late=marked)
                        if marked:
                            kept_late_eval[(phase, task, block, h)] = sorted(marked)
                        evaluation_attempts += [{'phase': phase, 'task': task, 'block': block, 'source': h, **a}
                                                for a in run.set_aside_attempts(folder.name, [c.episode_id for c in flown])]
                        # Kept in the scheduled order, whatever order the phase flew in.
                        target[(task, block, h)] = {c.episode_id: records[c.episode_id]
                                                    for c in case_fn(run.seeds, task, run.pilot)}
        # A phase's warm-up flight (ardupilot/ladder.py, fly_warmup) is not a flight of the study. Nothing in its folder
        # is counted, matched or verified here.
        def files(pattern):
            return (p for p in root.rglob(pattern) if not in_warmup(root, p) and not in_late(root, p))
        actual_phases = {p.parent.resolve() for p in files('manifest.json')}
        need(actual_phases == run.expected_phases, 'Missing or extra phase manifests')
        actual_flights = {p.parent.resolve() for p in files('outcome.json')}
        need(actual_flights == run.expected_flights, 'Missing or extra actual flights')
        actual_requests = {p.resolve() for p in files('*request.json')}
        need(actual_requests == run.expected_requests, 'Missing or extra candidate requests')
        need({p.resolve() for p in files('usage.jsonl')} == run.expected_usage, 'Unlinked or missing model usage')
        need({p.resolve() for p in root.glob('*/candidates/*/calls/*.json')} == run.expected_calls, 'Missing or extra call receipts')
        need(len(run.bindings) == 1 and len(run.settings) <= 1 and (pilot or len(run.settings) == 1),
             'Mixed protocol/source/core/model settings')
        need(len(run.at_once_values) == 1, f'Mixed at_once values in one run root: {sorted(run.at_once_values)}')
        need(len({x[0] for x in run.platforms}) == 1, f'Mixed platforms in one run root: {sorted(x[0] for x in run.platforms)}')
        need(len(run.routes) == 1, f'Mixed sandbox routes in one run root: {sorted(run.routes)}')
        need(len(run.platforms) == 1, 'Mixed partitions or CPU models in one run root: '
             + ' and '.join(f'partition {x[1]!r}, CPU {x[2]!r}' for x in sorted(run.platforms, key=str)))
        need(run.checked['unique flights'] == len(run.expected_flights), 'A physical flight was counted more than once')
        rows = ledger_rows(root, run.r)
        check_message_ids(run, rows)
        check_ledger_pairing(run, rows)
        check_gateway(run, rows)
        if judge_frozen:
            check_frozen(run, frozen_path)
        stops = session_stops(root, pilot, run.r, tasks)
        run.extra['session_spend_stops'] = stops['sessions']
        run.extra['sessions_with_other_spend_stop'] = stops['other']
        from protocol import run_scored3 as R3
        run.extra['spend_stop_in_protocol_usd'] = R3.SPEND_LIMIT_USD_3
        # Verify partners for every protected file, including unscheduled orphan logs.
        for path in files('*'):
            if path.is_file() and (path.name.endswith('.heads') or path.name == 'heads'):
                log = path.with_name('log') if path.name == 'heads' else path.with_name(path.name[:-5] + 'log')
                run.r.log(log)
            elif path.is_file() and path.name in ('episode.log', 'broker.log', 'gateway.log', 'flight.log', 'log'):
                run.r.log(path)
        report.update(run.extra)
        report.update(tasks=tasks, ok=True, checked=dict(run.checked), scheduled_phases=len(run.expected_phases),
                      platform=sorted(run.platforms, key=str)[0][0], nodes=sorted(run.nodes),
                      route=sorted(run.routes)[0], kernels=sorted(run.kernels))
        aside_learning = set_aside_learning(root, rows, run.r)      # read before the record of input hashes is copied below
        snapshot = {'seeds': seeds, 'pilot': pilot, 'learning': learning, 'hazard': hazard,
                    'retention': retention, 'input_sha256': dict(run.r.hashes),
                    'unique_flights': len(run.expected_flights),
                    'requested_models': sorted({json.loads(s)['model'] for s in run.settings}),
                    # E2.4: the gate's own report fields and the set-aside blocks' rows, for the analysis
                    'gate': dict(run.extra), 'set_aside_learning': aside_learning,
                    # E2.5: the evaluation flights kept late, by phase and source, and what every set-aside attempt of an
                    # evaluation phase flew
                    'kept_late_eval': kept_late_eval, 'evaluation_attempts': evaluation_attempts,
                    # build H7: what the gate compares when it takes three roots as one run
                    'tasks': tasks, 'tasks_on_file': tasks_on_file, 'message_ids': sorted(run.message_ids), 'root': str(root),
                    'identity': {'source_fingerprints': [[a, b] for a, b in sorted(run.source_fingerprints)],
                                 'wheel_sha256': run.wheel_hash, 'seeds_sha256': seeds['_sha256'], 'protocol_sha256': run.protocol_hash,
                                 'platform': sorted(run.platforms, key=str)[0][0], 'route': sorted(run.routes)[0],
                                 'frozen_differences': (run.extra.get('frozen_values') or {}).get('differences'),
                                 'at_once': sorted(run.at_once_values), 'pilot': pilot}}
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        report['errors'].append(str(error))
        if run:
            report['checked'] = dict(run.checked)
            report.update(run.extra)
    return report, snapshot


SPLIT_STOP_USD = 20      # the most a split run's root may have as its spending stop (ruling 52, point 3: three stops of 20 make the 60)
SUM_FIELDS = ('repeated_message_ids', 'message_ids_seen', 'rows_logged_as_copied', 'copies_caught', 'message_ids_in_file_with_no_row',
              'message_id_file_fragments')


def add_numbers(a, b):
    """The sum of two report fields made of numbers, or of dicts of numbers to any depth (a key in one only is kept)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: add_numbers(a[k], b[k]) if k in a and k in b else a.get(k, b.get(k)) for k in {**a, **b}}
    return a + b


def combine_roots(parts, pilot):
    """Build H7 (ruling 53). The three one-task roots of a split run, taken as one run. `parts` is [(root, report, snapshot)], each
    root already judged alone by load_run(allow_partial=True). Raises InvalidEvidence when the three are not one run, and otherwise
    returns the merged (report, snapshot). What is checked:
      - each root's schedule names exactly one task (on file), the three differ, and together they are contract3.TASKS;
      - the same source fingerprint, wheel, seed book, protocol text, platform, sandbox route and number at once, the same
        frozen-values result and the same mode (the roots may be on three nodes);
      - in a pilot, the same number of learning blocks in each root;
      - no message id in two roots (a stored copy of a reply from another task's run is as bad as one inside a run);
      - in a scored run, every session's spending stop was set by --spend-limit and is at most SPLIT_STOP_USD (so that the stops
        add up to what the owner approved)."""
    need(len(parts) == 3, f'a split run has three roots, not {len(parts)}')
    for root, report, snap in parts:
        need(len(snap['tasks']) == 1 and snap['tasks_on_file'], f'{root}: the schedule on file must name exactly one task; it names {snap["tasks"]}'
             + ('' if snap['tasks_on_file'] else ' (no schedule on file says so)'))
    tasks = [snap['tasks'][0] for _, _, snap in parts]
    need(len(set(tasks)) == 3 and set(tasks) == set(C.TASKS), f'the three roots fly {tasks}; they must fly {list(C.TASKS)}, one each')
    first = parts[0][2]['identity']
    for root, _, snap in parts[1:]:
        for key, value in snap['identity'].items():
            need(value == first[key], f'{root}: {key} is {value!r}, but the first root has {first[key]!r}; the three roots are not one run')
    seeds = parts[0][2]['seeds']
    if pilot:
        counts = {snap['tasks'][0]: len(snap['learning'][snap['tasks'][0]]) for _, _, snap in parts}
        need(len(set(counts.values())) == 1, f'the roots hold different numbers of learning blocks: {counts}')
    for i, (root_a, _, a) in enumerate(parts):
        for root_b, _, b in parts[i + 1:]:
            both = set(a['message_ids']) & set(b['message_ids'])
            need(not both, f'{len(both)} message ids are in both {root_a} and {root_b} (first {sorted(both)[0] if both else ""})')
    if not pilot:
        for root, report, snap in parts:
            for s in report['session_spend_stops']:
                need(s['spend_limit_from_flag'] is True and is_number(s['spend_limit_usd']) and s['spend_limit_usd'] <= SPLIT_STOP_USD,
                     f'{root}: the {s["event"]} at {s["time"]} had a spending stop of US${s["spend_limit_usd"]} '
                     f'{"set by --spend-limit" if s["spend_limit_from_flag"] else "not set by --spend-limit"}; a split run\'s stop must be '
                     f'set by --spend-limit and be at most US${SPLIT_STOP_USD}')
    ordered = sorted(parts, key=lambda p: C.TASKS.index(p[2]['tasks'][0]))
    merged_gate = {}
    for _, report, snap in ordered:
        for key, value in snap['gate'].items():
            if key in SUM_FIELDS or key in ('provider_rows_with_no_spending_row', 'spending_rows_with_no_provider_row', 'gateway_charge', 'kept_late_evaluation_flights'):
                merged_gate[key] = add_numbers(merged_gate[key], value) if key in merged_gate else value
            elif key in ('session_spend_stops', 'sessions_with_other_spend_stop'):
                merged_gate.setdefault(key, []).extend({**e, 'task': snap['tasks'][0]} for e in value)
            elif key == 'frozen_values':
                merged_gate.setdefault(key, []).append({**value, 'task': snap['tasks'][0]})
            elif key == 'tasks':
                continue
            else:
                need(key not in merged_gate or merged_gate[key] == value, f'the roots disagree on the report field {key}')
                merged_gate[key] = value
    inputs = {}
    roots = []
    for root, report, snap in ordered:
        own = dict(snap['input_sha256'])
        inputs.update({f'{snap["tasks"][0]}:{k}': v for k, v in own.items()})
        roots.append({'task': snap['tasks'][0], 'root': snap['root'], 'input_sha256': own,
                      'inputs_aggregate_sha256': hashlib.sha256(C.canonical(own)).hexdigest()})
    snapshot = {'seeds': seeds, 'pilot': pilot, 'learning': {}, 'hazard': {}, 'retention': {}, 'input_sha256': inputs,
                'unique_flights': sum(s['unique_flights'] for _, _, s in ordered),
                'requested_models': sorted({m for _, _, s in ordered for m in s['requested_models']}),
                'gate': merged_gate, 'set_aside_learning': sorted([x for _, _, s in ordered for x in s['set_aside_learning']],
                                                                 key=lambda x: (x['phase'], x['attempt'])),
                'kept_late_eval': {}, 'evaluation_attempts': [], 'tasks': list(C.TASKS), 'tasks_on_file': True, 'roots': roots}
    for _, _, snap in ordered:
        snapshot['learning'].update(snap['learning'])
        for key in ('hazard', 'retention', 'kept_late_eval'):
            snapshot[key].update(snap[key])
        snapshot['evaluation_attempts'] += snap['evaluation_attempts']
    checked = Counter()
    for _, report, _ in ordered:
        checked.update(report['checked'])
    report = {'ok': True, 'errors': [], 'pilot': pilot, 'checked': dict(checked), 'roots': roots, 'tasks': list(C.TASKS),
              'scheduled_phases': sum(r['scheduled_phases'] for _, r, _ in ordered),
              'platform': first['platform'], 'nodes': sorted({n for _, r, _ in ordered for n in r['nodes']}),
              'route': first['route'], 'kernels': sorted({k for _, r, _ in ordered for k in r['kernels']}), **merged_gate}
    return report, snapshot


def load_runs(roots, **kwargs):
    """Build H7 (ruling 53). One root is judged as before by load_run. Three roots are a split run, one task each: each is
    judged alone (allowing a root of one task) and then the three are checked as one run (combine_roots). Returns (report,
    snapshot); the snapshot is None when the report is not ok. The report of three roots lists them and their input hashes."""
    roots = [Path(r) for r in (roots if isinstance(roots, (list, tuple)) else [roots])]
    if len(roots) == 1:
        return load_run(roots[0], **kwargs)
    pilot = kwargs.get('pilot', False)
    report = {'ok': False, 'errors': [], 'checked': {}, 'pilot': pilot, 'roots': [str(r) for r in roots]}
    if len(roots) != 3 or len({r.resolve() for r in roots}) != 3:
        report['errors'].append(f'a split run is three different run roots, one for each task; got {len(roots)}')
        return report, None
    parts = []
    for root in roots:
        rep, snap = load_run(root, allow_partial=True, **kwargs)
        if not rep['ok']:
            report['errors'] += [f'{root}: {e}' for e in rep['errors']]
        parts.append((root, rep, snap))
    if report['errors']:
        return report, None
    try:
        return combine_roots(parts, pilot)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
        report['errors'].append(str(error))
        return report, None


def in_warmup(root, path) -> bool:
    """True for a path inside a phase's warm-up folder: root/PHASE/warmup/..."""
    parts = Path(path).relative_to(root).parts
    return len(parts) > 2 and parts[1] == WARMUP_DIR


def in_late(root, path) -> bool:
    """True for a path inside a learning block's set-aside attempts: root/learn3-.../late/... (Run.late_attempts)."""
    parts = Path(path).relative_to(root).parts
    return len(parts) > 2 and parts[0].startswith('learn3-') and parts[1] == LATE_DIR


def validate(root, **kwargs):
    return load_runs(root, **kwargs)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='+', help='one run root, or the three roots of a split run (one task each)')
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    report = validate(args.root, pilot=args.pilot)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()

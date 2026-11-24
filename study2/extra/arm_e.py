"""Arm E of Paper 3's extra experiment (PROTOCOL-EXTRA.md): fresh candidates from a request that shows the failed zone
trial flights and the reason, without the failed code.

Arm C's repair request (ardupilot/ladder.py) carries three things arm B's resent request does not: the refused source,
the trial's one-line reason, and the zone trial flights the refused candidate flew. Arm E keeps the reason and the
flights and leaves out the source. So C - E is what showing the code adds, and E - B is what showing the failure adds.

Arm E runs on each of Study 2's 120 learning blocks, from that block's saved records:

  slot 1   c0, shared with arms A to D: its request, reply, source and zone trial are copied, never drawn or flown again
  slot 2   rE1, tried on the block's threat list, as arm C's rC1
  slot 3   rE2, the same, after rE1

View E is built as view C was. Telohelm's Coordinator sees the block's three matched first flights (P0), and its first
request must equal c0's saved request byte for byte, or the block stops. Before rE1 the view is told of c0's refusal
exactly as view C was (Context.refused, stage 'trial', the same reason), except that the source is None, so the core
leaves the source out of the request's previous attempts. It then sees c0's three zone trial flights under the names
view C gave them. rE2 follows from rE1 the same way. Nothing else in the request changes: the Coordinator, the rules,
the input cap and the token count are Study 2's.

When c0 was not valid there is no source to leave out, so arm E's request is arm C's. A slot whose request is, byte for
byte, arm C's saved request for that slot takes arm C's candidate and its trial, with no call, as arms that send the same
request share a candidate in Study 2 (B and C share c0). If c0 passed its zone trial, arm E adopts c0, as B and C did.

  python -m extra.phase learnE --task reach --block 3 --saved SAVED/learn3-reach-b3 --out ROOT/learnE-reach-b3 \\
      --protocol 3 --instance 10
  python -m extra.arm_e dry SAVED_RUNS WORK OUT.json     # every block's slot 2 request, built with no model call

SAVED_RUNS holds Study 2's run roots scored-20261120-S-<task>/. The dry pass flies nothing and asks no model. It uses
the gateway's token count, which is free, because the core fits each request to the input cap with it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ardupilot import ladder as L  # noqa: E402

E_SLOTS = ('c0', 'rE1', 'rE2')
C_SLOTS = L.ARMS['C'][1]               # ('c0', 'rC1', 'rC2'): arm C's candidate in the same slot
FAMILY = L.ARMS['C'][0]                # 'threat': arm E is tried on the zone layouts, as arm C
# Each candidate has its own attempt number (ladder.CALL_NUMBER), so no request identity repeats one of Study 2's eight.
E_CALL_NUMBER = {'rE1': 9, 'rE2': 10}
STUDY2_RUN = 'scored-20261120-S-{task}'
PROTOCOL_EXTRA = ROOT / 'PROTOCOL-EXTRA.md'


def register() -> None:
    """Add rE1 and rE2 to ladder's tables, which Block.write reads. Their parent is set when each is written, because
    it is the candidate whose failure the request shows: c0 or arm C's rC1 for rE1, and the slot 2 candidate for rE2."""
    for k, v in E_CALL_NUMBER.items():
        if L.CALL_NUMBER.setdefault(k, v) != v:
            raise RuntimeError(f'ladder already gives {k} the attempt number {L.CALL_NUMBER[k]}')


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_candidate(folder: Path) -> dict:
    """A candidate as Block.write keeps it: its record and, if it was valid, its source, checked against the record."""
    record = json.loads((folder / 'candidate.json').read_text())
    source = None
    if record['format_valid']:
        if sha256_file(folder / 'source.py') != record['source_sha256']:
            raise RuntimeError(f'{folder}: source.py does not match its record')
        source = (folder / 'source.py').read_text(encoding='utf-8')
    return {**record, 'source': source}


class BlockE(L.Block):
    """One learning block of arm E, from the saved Study 2 block `saved`."""

    def __init__(self, root, task, block, matched, threat, proposer, provider, *, saved: Path, **kw):
        super().__init__(root, task, block, matched, threat, proposer, provider, **kw)
        self.saved = Path(saved)
        self.saved_arms = json.loads((self.saved / 'arms.json').read_text())
        if (self.saved_arms['task'], self.saved_arms['block']) != (task, block):
            raise RuntimeError(f'{self.saved} is {self.saved_arms["task"]} block {self.saved_arms["block"]}, '
                               f'not {task} block {block}')
        manifest = json.loads((self.saved / 'manifest.json').read_text())['args']['learning_cases']
        mine = {f: [c.episode_id for c in self.cases[f]] for f in ('matched', 'threat')}
        if manifest != mine:
            raise RuntimeError(f'{self.saved} flew {manifest}, not this block\'s layouts {mine}')
        self.copied: set[str] = set()      # trial folders copied from Study 2, read and never flown
        # The label of the model that served c0 in Study 2. Every reply arm E gets from a real model must carry the same
        # label, or the block stops as a fault: the arms would not have been written by the same model.
        first = sorted((self.saved / 'candidates' / 'c0' / 'calls').glob('*.json'))[0]
        self.served_by = json.loads(first.read_text())[L.SERVED_FIELD]

    # -- Study 2's records ------------------------------------------------------------------------------------------

    def copy(self, rel: str) -> Path:
        """A folder of the saved block, copied to the same place in this block."""
        shutil.copytree(self.saved / rel, self.root / rel)
        return self.root / rel

    def take(self, cid: str) -> dict:
        """A Study 2 candidate and, if it was valid, its zone trial, copied with their records."""
        self.copy(f'candidates/{cid}')
        self.candidates[cid] = load_candidate(self.root / 'candidates' / cid)
        if self.candidates[cid]['format_valid']:
            rel = f'flights/trial/{cid}/{FAMILY}'
            self.copy(rel)
            self.copied.add(rel)
        return self.candidates[cid]

    def fly(self, rel: str, sources: list, cases: list) -> dict:
        if rel in self.copied:
            # A saved trial: its outcomes are read, and Block.trial judges them by the rule they were judged by in
            # Study 2. saved_trial_check then compares the verdict with Study 2's record.
            return {c.episode_id: json.loads((self.root / rel / c.episode_id / 'outcome.json').read_text())
                    for c in cases}
        return super().fly(rel, sources, cases)

    def saved_trial_check(self, cid: str) -> None:
        mine = self.trials[(cid, FAMILY)]
        for row in self.saved_arms['arms'].values():
            for t in row['trials']:
                if t['candidate_id'] == cid and t['trial_list'] == FAMILY:
                    if (t['passed'], t['outcomes']) != (mine['passed'], mine['outcomes']):
                        raise RuntimeError(f'{cid}: the saved trial judged again gives {mine["passed"]}, '
                                           f'Study 2 recorded {t["passed"]}')
                    return
        raise RuntimeError(f'Study 2 has no record of {cid} on the {FAMILY} list')

    def write(self, cid: str, context, messages=None, shown=None) -> dict:
        cand = super().write(cid, context, messages, shown)
        for line in self.usage.read_text().splitlines():
            row = json.loads(line)
            if row['candidate_id'] == cid and row[L.REAL_FIELD] and row[L.SERVED_FIELD] != self.served_by:
                raise L.InfrastructureFault(f'{cid} call {row["call"]}: served by {row[L.SERVED_FIELD]!r}, '
                                            f'not {self.served_by!r} as in Study 2')
        return cand

    # -- the view and its requests ------------------------------------------------------------------------------

    def _refuse_previous(self, view, previous: str, family: str) -> None:
        """Arm C's step (ladder.Block._refuse_previous) with the source left out. A candidate that was not valid has
        no source in either arm, so that case is arm C's step unchanged."""
        cand = self.candidates[previous]
        if not cand['format_valid']:
            return super()._refuse_previous(view, previous, family)
        t = self.trials[(previous, family)]
        view.refused('trial', t['why'], None)
        for c in self.cases[family]:
            view.see(c, self.root / t['flight_dir'] / c.episode_id, name=f'{c.episode_id}-{previous}')

    def start(self, name: str = 'E'):
        """A view begun as view C was: the matched first flights, and a first request that must be c0's."""
        if not (self.root / 'flights' / 'first' / 'P0').exists():
            self.copy('flights/first/P0')
        view = L.Context(name, self.root, self.task, self.proposer)
        for c in self.cases['matched']:
            view.see(c, self.root / 'flights' / 'first' / 'P0' / c.episode_id)
        view.begin()
        first = L.payload_json(view.messages())
        saved = json.loads((self.saved / 'candidates' / 'c0' / 'request.json').read_text())['model_payload_json']
        if first != saved:
            raise RuntimeError(f"view {name}'s first request differs from c0's saved request")
        return view

    def next_request(self, view, previous: str) -> tuple:
        self._refuse_previous(view, previous, FAMILY)
        view.begin()
        return view.view()

    def same_as_c(self, slot: int, previous: str, payload: str) -> str | None:
        """Arm C's candidate for this slot if C's saved request for it is this request, byte for byte."""
        cid = C_SLOTS[slot]
        path = self.saved / 'candidates' / cid / 'request.json'
        if not path.exists():
            return None
        saved = json.loads(path.read_text())
        return cid if saved['model_payload_json'] == payload and saved['parent'] == previous else None

    # -- the arm ------------------------------------------------------------------------------------------------

    def run(self) -> dict:
        view = self.start()
        self.take('c0')
        trials, calls, slots, order = [], [], [], []
        for slot, eid in enumerate(E_SLOTS):
            if slot == 0:
                cid, how = 'c0', 'study2'
            else:
                previous = order[-1]
                messages, shown = self.next_request(view, previous)
                payload = L.payload_json(messages)
                cid = self.same_as_c(slot, previous, payload)
                if cid:
                    how = 'study2-arm-C-same-request'
                    self.take(cid)
                else:
                    cid, how = eid, 'drawn'
                    L.PARENT[eid] = previous
                    self.write(eid, view, messages, shown)
            order.append(cid)
            cand = self.candidates[cid]
            slots.append({'slot': slot + 1, 'candidate_id': cid, 'from': how, 'call_ids': list(cand['call_ids'])})
            calls += cand['call_ids']
            if not cand['format_valid']:
                trials.append({'candidate_id': cid, 'trial_list': FAMILY, 'passed': False, 'flight_dir': None,
                               'outcomes': []})
                continue
            t = self.trial(cid, FAMILY)
            if f'flights/trial/{cid}/{FAMILY}' in self.copied:
                self.saved_trial_check(cid)
            trials.append({k: t[k] for k in ('candidate_id', 'trial_list', 'passed', 'flight_dir', 'outcomes')})
            if t['passed']:
                break
        win = trials[-1] if trials and trials[-1]['passed'] else None
        c0_threat = self.trials.get(('c0', FAMILY))
        record = {'schema_version': 1, 'task': self.task, 'block': self.block,
                  'c0_zone_qualified': c0_threat['passed'] if c0_threat else False,
                  'arms': {'E': {'adopted': win is not None, 'candidate_id': win['candidate_id'] if win else None,
                                 'source_sha256': self.candidates[win['candidate_id']]['source_sha256'] if win else None,
                                 'trials': trials, 'call_ids': list(dict.fromkeys(calls))}},
                  'slots': slots,
                  'study2_block': {'folder': self.saved.name, 'arms_sha256': sha256_file(self.saved / 'arms.json')}}
        L._write(self.root / 'arms.json', record)
        return record

    # -- the free dry pass --------------------------------------------------------------------------------------

    def dry(self, count) -> dict:
        """Slot 2's request for arm E, built with no call; and arm C's, rebuilt the same way, which must equal C's saved
        rC1 request byte for byte, so that the rebuilt view is known to be the view Study 2 had."""
        view = self.start('E')
        c0 = self.take('c0')
        out = {'task': self.task, 'block': self.block, 'c0_valid': c0['format_valid']}
        if c0['format_valid']:
            t = self.trial('c0', FAMILY)
            self.saved_trial_check('c0')
            out['c0_passed_zone_trial'] = t['passed']
            if t['passed']:
                out['slot2'] = 'none: arm E adopts c0'
                return out
        messages, shown = self.next_request(view, 'c0')
        payload = L.payload_json(messages)
        saved = json.loads((self.saved / 'candidates' / 'rC1' / 'request.json').read_text())
        view_c = self.start('C-rebuilt')
        L.Block._refuse_previous(self, view_c, 'c0', FAMILY)       # arm C's own step, with the source
        view_c.begin()
        c_messages, c_shown = view_c.view()
        c_payload = L.payload_json(c_messages)
        out.update({
            'slot2': 'arm C rC1 (same request)' if self.same_as_c(1, 'c0', payload) else 'rE1 drawn',
            'c_rebuilt_equals_saved_rC1': c_payload == saved['model_payload_json'],
            'c_rebuilt_shown_equals_saved': c_shown == saved['shown_flights'],
            'e_equals_c': payload == c_payload,
            'e_shown': shown, 'c_shown': c_shown, 'shown_differ': shown != c_shown,
            'e_context_flights': list(view.flights),
            'e_chars': len(payload), 'c_chars': len(c_payload),
            'e_tokens': count(messages), 'c_tokens': count(c_messages),
            'c0_source_in_e': bool(c0['source']) and c0['source'] in payload,
            'c0_source_in_c': bool(c0['source']) and c0['source'] in c_payload,
        })
        return out


def rehearsal_stub(task: str, saved: Path):
    """Scripted replies for a rehearsal (--pilot). rE1 holds still, so it fails its trial and rE2 is asked for. rE2 is
    the procedure arm C adopted in the same Study 2 block, which passed this block's zone trial there, with a comment
    line added so that its source differs from every source Study 2 flew and arm E's own evaluation path is taken. A
    block where arm C adopted nothing gets the first procedure of testdata/adopt-replies.json (ladder.adopt_stub's).
    Every record labels the replies as scripted."""
    from telohelm.runtime.models import ModelResponse
    from ardupilot.demo import HOLD_STILL
    row = json.loads((Path(saved) / 'arms.json').read_text())['arms']['C']
    if row['adopted']:
        source = (Path(saved) / 'candidates' / row['candidate_id'] / 'source.py').read_text(encoding='utf-8')
    else:
        source = json.loads(L.ADOPT_REPLIES.read_text())['sources'][task][0]['source']
    source = '# rehearsal copy\n' + source

    def procedure(text):
        return json.dumps({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': text,
                           'reason': {'code': 'missing_tool', 'text': 'scripted rehearsal reply'}})
    plan = {('rE1', 1): procedure(HOLD_STILL[task]), ('rE2', 1): procedure(source)}

    def reply(label, request):
        text = plan.get(label, '')
        return ModelResponse('answered', text) if text else ModelResponse('failed', '')
    return reply


def phase_learn(argv=None) -> int:
    """One block of arm E: python -m extra.phase learnE ... (the scheduler adds --instance, --protocol and --at-once).
    With --pilot it is a rehearsal: the same block and requests, scripted replies, and every record marked pilot."""
    from ardupilot import scored as S
    from protocol import contract3 as C3
    p = argparse.ArgumentParser(prog='learnE')
    p.add_argument('--task', choices=C3.TASKS, required=True)
    p.add_argument('--block', type=int, required=True)
    p.add_argument('--saved', type=Path, required=True, help="Study 2's learn3 folder of this block")
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--speedup', type=float, default=1.0)
    p.add_argument('--instance', type=int, default=S.SCORED_INSTANCES[0])
    p.add_argument('--protocol', type=int, choices=(3,), default=3)
    p.add_argument('--at-once', type=S.at_once_arg, default=4)
    p.add_argument('--pilot', action='store_true', help='a rehearsal with scripted replies; nothing from it is reported')
    a = p.parse_args(argv)
    S.use_protocol(3)
    S.AT_ONCE = a.at_once
    S.refuse_start(1)
    if not a.pilot and a.speedup != 1.0:
        raise SystemExit('a scored block flies in real time')
    if not PROTOCOL_EXTRA.exists() and not a.pilot:
        raise SystemExit(f'{PROTOCOL_EXTRA.name} is missing; arm E runs only under its protocol')
    register()
    seeds = S.seeds()        # Study 2's own book, in a rehearsal too: arm E runs on Study 2's saved blocks
    matched = C3.learning_cases(seeds, a.task, a.block, threat=False)
    threat = C3.learning_cases(seeds, a.task, a.block, threat=True)
    S.guard(a.out, 'learnE', {'task': a.task, 'block': a.block, 'speedup': a.speedup, 'arm': 'E',
                              'model': S.GEM_MODEL, 'scripted_replies': 'rehearsal' if a.pilot else None,
                              'study2_block': str(a.saved),
                              'study2_arms_sha256': sha256_file(a.saved / 'arms.json'),
                              'protocol_extra_sha256': sha256_file(PROTOCOL_EXTRA) if PROTOCOL_EXTRA.exists() else None,
                              'learning_cases': {'matched': [c.episode_id for c in matched],
                                                 'threat': [c.episode_id for c in threat]},
                              'slots': list(E_SLOTS), 'calls_per_slot': L.CALLS_PER_SLOT, 'late_flights': 'refly'},
            a.pilot, a.instance)
    L.fly_warmup(a.out, a.task, S.warmup_case(C3, seeds, a.task), speedup=a.speedup, instance=a.instance)
    L.P.HOST.update(root=a.out, speedup=a.speedup, instance=a.instance)
    if a.pilot:
        # The scored request path, so the requests are the ones a scored block would send, with scripted replies
        # behind it. The token count is bound to the real provider when the proposer is made, and stays so.
        from telohelm.runtime.models import ScriptedProvider
        proposer, provider = L.make_proposer(a.out, a.task, scored=False, gem_model=S.GEM_MODEL)
        stub = rehearsal_stub(a.task, a.saved)
        provider.inner = ScriptedProvider(lambda request: stub(provider.label, request))
    else:
        proposer, provider = L.make_proposer(a.out, a.task, scored=True, gem_model=S.GEM_MODEL,
                                             run_root=Path(a.out).resolve().parent)
    record = BlockE(a.out, a.task, a.block, matched, threat, proposer, provider, saved=a.saved, speedup=a.speedup,
                    instance=a.instance, late_flights='refly', before_flight=S.flight_gate(Path(a.out))).run()
    S.stop_for_bad_replacement(S.write_route_end(a.out), 'learnE')
    print(json.dumps({'E': record['arms']['E']['candidate_id']}))
    return 0


def proposer_without_calls(root: Path, task: str):
    """The scored request path (make_proposer's gateway branch: input cap, the gateway's free token count) with a
    provider that refuses to send anything. Building and counting requests is all it can do."""
    from ardupilot import scored as S

    proposer, provider = L.make_proposer(root, task, scored=False, gem_model=S.GEM_MODEL)

    def refuse(request):
        raise RuntimeError('the dry pass makes no model call')
    provider.inner.complete = refuse
    return proposer, provider


def dry_main(saved_runs: Path, work: Path, out: Path, blocks: int | None = None) -> int:
    from ardupilot import scored as S
    from protocol import contract3 as C3
    register()
    S.use_protocol(3)
    seeds = S.seeds()
    if sha256_file(S.SEEDS) != json.loads((ROOT / 'protocol' / 'FROZEN-3.json').read_text())['seeds_sha256']:
        raise SystemExit('the seed book is not the frozen one')
    work.mkdir(parents=True)
    rows = []
    for task in C3.TASKS:
        run = saved_runs / STUDY2_RUN.format(task=task)
        for block in range(len(seeds['blocks'][task]) if blocks is None else blocks):
            saved = run / f'learn3-{task}-b{block}'
            root = work / f'learnE-{task}-b{block}'
            root.mkdir()
            matched = C3.learning_cases(seeds, task, block, threat=False)
            threat = C3.learning_cases(seeds, task, block, threat=True)
            proposer, provider = proposer_without_calls(root, task)
            b = BlockE(root, task, block, matched, threat, proposer, provider, saved=saved, speedup=1.0,
                       instance=10, late_flights='refly')
            row = b.dry(provider.count_tokens)
            row['count_basis'] = provider.inner.count_basis
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ('task', 'block', 'c0_valid', 'c0_passed_zone_trial', 'slot2',
                                                       'c_rebuilt_equals_saved_rC1', 'e_equals_c', 'shown_differ',
                                                       'e_tokens', 'c_tokens')}), flush=True)
    out.write_text(json.dumps(rows, indent=1) + '\n')
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='action', required=True)
    q = sub.add_parser('dry')
    q.add_argument('saved_runs', type=Path)
    q.add_argument('work', type=Path)
    q.add_argument('out', type=Path)
    q.add_argument('--blocks', type=int, help='only the first BLOCKS blocks of each task (a quick look)')
    a = p.parse_args(argv)
    return dry_main(a.saved_runs, a.work, a.out, a.blocks)


if __name__ == '__main__':
    raise SystemExit(main())

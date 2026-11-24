"""Offline controls for the protocol-3 learning block (ladder.py). No simulator, no model.

Flights are replaced by copies of six recorded guard-only flights (testdata/ladder-first-round.zip, from the
engineering pilot runs/dev-ladder-c3-20261109-b): a matched list gets the three P0 cases and a threat list the three
P1 cases. Their logs carry no decision by any candidate, so every trial fails, which drives every arm through all
three slots. Replies are scripted per (candidate, call).

Run from paper3/:  .venv/bin/python -m unittest ardupilot.test_ladder
"""
from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

from . import ladder as L
from . import pack as P
from .demo import HOLD_STILL

# The recorded flight P0/matched-close-4000001 has one decision lag of 1.001 s, at native_steps[0] (its median is 0.001 s).
# By the owner's rule (TAKEOVER-20261111.md, line 62: any decision 1 s late or more makes a flight late) that recorded
# flight is late, and test_recorded_flight_is_late_by_the_one_second_rule asserts it. The block tests need on-time
# flights, so fake_fly gives its copy of that one lag the median's value. The fixture file is not changed.
RECORDED_LATE = {'matched-close-4000001': (0, 1.001)}

FIXTURE = Path(__file__).with_name('testdata') / 'ladder-first-round.zip'
TASK = 'reach'


def procedure(source):
    return json.dumps({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': source,
                       'reason': {'code': 'missing_tool', 'text': 'scripted test reply'}})


class Cases:
    """The six recorded cases as scenarios, read back from the fixture's run-config.json files."""

    def __init__(self, root: Path, task: str = TASK):
        from .battle import generate
        self.root = root
        cfg = {k: json.loads((root / k / 'run-config.json').read_text()) for k in ('P0', 'P1')}
        self.ids = {k: [s['episode_id'] for s in cfg[k]['scenarios']] for k in cfg}
        # The scenarios themselves, regenerated from their recorded family, band and seed.
        self.matched = [generate(task, 'matched', int(i.rsplit('-', 1)[1]), gap_stratum=i.split('-')[1])
                        for i in self.ids['P0']]
        self.threat = [generate(task, 'threat', int(i.rsplit('-', 1)[1]), gap_stratum=i.split('-')[1])
                       for i in self.ids['P1']]
        assert [c.episode_id for c in self.matched] == self.ids['P0']
        assert [c.episode_id for c in self.threat] == self.ids['P1']


def plant_text(folder: Path, marker: str) -> None:
    """Put marker into the action record of every second of a flight, as a field the examples would show if the flight
    were ever shown. The broker log is written again through the trusted writer, so its chain and heads still verify."""
    from unittest import mock
    from telohelm.runtime.trusted_log import TrustedLog, verify
    log, heads = folder / 'broker.log', folder / 'broker.heads'
    payloads = [json.loads(line)['payload'] for line in log.read_text().splitlines()]
    log.unlink()
    heads.unlink()
    with mock.patch('os.fsync'):                 # the writer syncs every record, which is slow for a test copy
        out = TrustedLog(log, heads, payloads[0]['run_id'])
        for p in payloads[1:]:
            out.append({**p, 'action': {**p['action'], 'zzmark': marker}} if p.get('kind') == 'action' else p)
        out.close()
    assert verify(log, heads)['ok']


def with_delay(outcome: dict, observation_lag_s: float = 0.0) -> dict:
    """A flight recorded before the fixed delay, given the fields a flight flown with it records (round four, ruling 1):
    command_delay_s, and on each step the observation's own lag and the command's lag at the deadline. decision_lag_s is
    left as recorded, so a test still makes a flight late by setting it."""
    outcome['command_delay_s'] = L.COMMAND_DELAY_S
    for st in outcome.get('native_steps') or []:
        st.setdefault('observation_lag_s', observation_lag_s)
        st.setdefault('command_lag_s', L.COMMAND_DELAY_S)
    return outcome


def delay_fixture(root: Path) -> None:
    """Give every recorded outcome under root the fixed delay's fields, as with_delay does."""
    for f in Path(root).rglob('outcome.json'):
        f.write_text(json.dumps(with_delay(json.loads(f.read_text()))))


def fake_fly(fixture: Path, late: set = frozenset(), marks: bool = False):
    """Block.fly without a simulator: copy the recorded cases for the list's family into rel, with a library holding
    the guard and the sources, as battle.run lays them out. Cases named in late get their lags set to 1 s. With marks,
    every flight carries a marker naming where it was flown: ZQ-P0, ZQ-P1, or ZQ-<candidate>-<list> for a trial."""
    def fly(self, rel, sources, cases):
        from telohelm.runtime.library import Library
        out = self.root / rel
        out.mkdir(parents=True)
        family = 'P0' if cases[0].episode_id.startswith('matched') else 'P1'
        library = Library(out / 'library', pack=P.PACKS[self.task].public)
        for code in sources:
            sha = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': code,
                               'origin': {'imported_from': rel}})
            library.set_status(sha, 'adopted', 'test')
        outcomes = {}
        for c in cases:
            shutil.copytree(fixture / family / c.episode_id, out / c.episode_id)
            o = json.loads((out / c.episode_id / 'outcome.json').read_text())
            if c.episode_id in RECORDED_LATE:
                step, lag = RECORDED_LATE[c.episode_id]
                assert o['native_steps'][step]['decision_lag_s'] == lag
                o['native_steps'][step]['decision_lag_s'] = 0.001
            if c.episode_id in late:
                for s in o['native_steps']:
                    s['decision_lag_s'] = 1.0
            (out / c.episode_id / 'outcome.json').write_text(json.dumps(o))
            if marks:
                # The list's marker, then a marker of this flight alone (its folder, with ~ for /), so a test can tell
                # which flights' moments a request shows and not only which list they came from.
                plant_text(out / c.episode_id, f"{marker_for(rel)} ZF~{rel.replace('/', '~')}~{c.episode_id}")
            t = L.timing(o)
            self.timing.append({'flight': f'{rel}/{c.episode_id}', **t})
            if t['late'] and self.late_flights == 'stop':
                raise L.InfrastructureFault(f'{rel}/{c.episode_id}: late')
            outcomes[c.episode_id] = o
        return outcomes
    return fly


def marker_for(rel: str) -> str:
    parts = rel.split('/')
    return 'ZQ-' + (parts[2] if parts[1] == 'first' else f'{parts[2]}-{parts[3]}')


ALL_CIDS = ('c0', 'c1', 'f1', 'f2', 'rC1', 'rC2', 'rD1', 'rD2')
MARKER = re.compile(r'ZQ-[A-Za-z0-9]+(?:-(?:matched|threat))?')
# Which marked flights each request may show, by the contract and the owner's repair ruling (TAKEOVER:72): a first
# candidate shows its own first-round flights; a repair shows its own arm's first-round flights and the earlier trial
# flights of its own arm. A and B's fresh candidates and A's matched trial are shown to nobody.
ALLOWED = {'c0': {'ZQ-P0'}, 'f1': {'ZQ-P0'}, 'f2': {'ZQ-P0'}, 'c1': {'ZQ-P1'},
           'rC1': {'ZQ-P0', 'ZQ-c0-threat'}, 'rC2': {'ZQ-P0', 'ZQ-c0-threat', 'ZQ-rC1-threat'},
           'rD1': {'ZQ-P1', 'ZQ-c1-threat'}, 'rD2': {'ZQ-P1', 'ZQ-c1-threat', 'ZQ-rD1-threat'}}


def payload_texts(root: Path, cid: str) -> list:
    """Every model-visible text sent for one candidate: the request and each call, format repairs included."""
    folder = root / 'candidates' / cid
    texts = [json.loads((folder / 'request.json').read_text())['model_payload_json']]
    texts += [json.loads(f.read_text())['model_payload_json'] for f in sorted((folder / 'calls').glob('*.json'))]
    return texts


def shown_markers(root: Path, cid: str, extra=()) -> set:
    """The markers (and any extra strings) that appear in anything sent for cid."""
    found = set()
    for text in payload_texts(root, cid):
        found |= set(MARKER.findall(text)) | {x for x in extra if x in text}
    return found


def leaks(root: Path, extra=()) -> dict:
    """Candidate id to the markers its requests show beyond what ALLOWED permits. An empty result means no leak."""
    out = {}
    for cid in ALL_CIDS:
        if (root / 'candidates' / cid).exists():
            bad = shown_markers(root, cid, extra) - ALLOWED[cid]
            if bad:
                out[cid] = bad
    return out


# rC1, rC2, rD1 and rD2 changed on 13 November 2026, when the trial reason began to name the failed trial flight by the
# name each arm's view records it under, so that the core sends its alias in every arm (leak inspection, finding 1).
# The same eight hashes as they were before 16 November 2026, when every protocol 3 request began to carry the delay
# sentence (round five, B5). The requests are checked against both: the current hashes, and these once the sentence is cut
# out of the text, which shows the sentence is the only difference.
GOLDEN_REQUEST_SHA256_BEFORE_DELAY_SENTENCE = {
    'c0': '07661431d6e00d5ad7a6129a17140c6ee2c644ce536ed2e116e3009f84fda912',
    'c1': '9ca9bb91f50be8a7ead457d022776f4264d3252ccd602b4c387afef8ac688f5a',
    'f1': '07661431d6e00d5ad7a6129a17140c6ee2c644ce536ed2e116e3009f84fda912',
    'f2': '07661431d6e00d5ad7a6129a17140c6ee2c644ce536ed2e116e3009f84fda912',
    'rC1': '3a23f1e2889dc92d6e98d0d3912ccd0aed7b827da80192e96af39bfc2da7da5b',
    'rC2': '316628e269a27cd2f525814d3caa0af6811d6c5af4323380e8c2b908a51eeea1',
    'rD1': '622d62f20dbddafab0fb4fc4c6b86f276818079075c9a89702ee6eac2370991b',
    'rD2': 'db93bdec8821558e2a5d44bd5c433e436d05580bf2f47202797ef73476bc91a1'}

# With the delay sentence of ladder.delay_sentence() in the goal text of every request (B5), as it reads at three periods
# (0.3 s); the number comes from the constant, and the text of the sentence is as it was at two periods. Since Build D
# (D1) the system text also holds pack.PROCEDURE_ONLY, after a newline, in every request.
GOLDEN_REQUEST_SHA256 = {
    'c0': '1edaef61e49fc6cf69345c9aa71972dadd52e5d917827469e1923997667cb957',
    'c1': 'b01ef394a85af1bc124995422074d828d7ac31afa7f3e907c8e4bc287282c21b',
    'f1': '1edaef61e49fc6cf69345c9aa71972dadd52e5d917827469e1923997667cb957',
    'f2': '1edaef61e49fc6cf69345c9aa71972dadd52e5d917827469e1923997667cb957',
    'rC1': 'cd4bfea9a2b066159ae919b0e4fc4ce6e0349019d54ad97d087cc06da6983542',
    'rC2': 'b14dc4017ca090ae2df8465faeff305160c334969e944a3bc41d41b423a3bd7b',
    'rD1': 'c60735c82df42a91c130cfad215722e030287d91a57c7fc84382d6e18d0fc2d1',
    'rD2': 'fae04cdfa6d65d1191613817906163108d4bf8ed0b37f153ef2618acd134e513'}


class LadderControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            raise unittest.SkipTest(f'{FIXTURE} is missing')
        cls.tmp = Path(tempfile.mkdtemp(prefix='ladder-test-'))
        with zipfile.ZipFile(FIXTURE) as z:
            z.extractall(cls.tmp / 'fixture')
        delay_fixture(cls.tmp / 'fixture')
        cls.cases = Cases(cls.tmp / 'fixture')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def block(self, name, plan, late=frozenset(), late_flights='stop', marks=False):
        from telohelm.runtime.models import ModelResponse
        root = self.tmp / name
        root.mkdir()
        sent = []

        def reply(label, request):
            sent.append(label)
            r = plan.get(label, procedure(HOLD_STILL[TASK]))
            if isinstance(r, Exception):
                raise r
            if isinstance(r, ModelResponse):
                return r
            return ModelResponse('answered', r) if r else ModelResponse('failed', '')
        proposer, provider = L.make_proposer(root, TASK, scored=False, gem_model=None, stub=reply)
        b = L.Block(root, TASK, 0, self.cases.matched, self.cases.threat, proposer, provider, speedup=10.0,
                    instance=10, late_flights=late_flights)
        b.fly = fake_fly(self.tmp / 'fixture', late, marks).__get__(b)
        return b, root, sent

    def payload(self, root, cid):
        return json.loads((root / 'candidates' / cid / 'request.json').read_text())

    def test_exhaustion_shares_c0_and_keeps_requests_apart(self):
        b, root, sent = self.block('exhaust', {})
        record = b.run()
        arms = record['arms']
        for arm, (family, order) in L.ARMS.items():
            self.assertFalse(arms[arm]['adopted'])
            self.assertEqual([t['candidate_id'] for t in arms[arm]['trials']], list(order))
            self.assertTrue(all(t['trial_list'] == family for t in arms[arm]['trials']))
        # B and C share c0's threat trial; A flies c0 on the matched list.
        self.assertEqual(arms['B']['trials'][0]['flight_dir'], arms['C']['trials'][0]['flight_dir'])
        self.assertEqual(arms['A']['trials'][0]['flight_dir'], 'flights/trial/c0/matched')
        # f1 and f2 send c0's request byte for byte, each as a call of its own; A and B share them.
        c0 = self.payload(root, 'c0')
        for f in ('f1', 'f2'):
            self.assertEqual(self.payload(root, f)['request_sha256'], c0['request_sha256'])
            self.assertNotEqual(self.payload(root, f)['request_id'], c0['request_id'])
        self.assertEqual(arms['A']['trials'][1]['flight_dir'], 'flights/trial/f1/matched')
        self.assertEqual(arms['B']['trials'][1]['flight_dir'], 'flights/trial/f1/threat')
        self.assertEqual(sorted(sent), sorted((c, 1) for c in ('c0', 'c1', 'f1', 'f2', 'rC1', 'rC2', 'rD1', 'rD2')))
        # What each request was built from.
        p0 = [f'flights/first/P0/{i}' for i in self.cases.ids['P0']]
        p1 = [f'flights/first/P1/{i}' for i in self.cases.ids['P1']]
        trial = lambda cid, fam, ids: [f'flights/trial/{cid}/{fam}/{i}' for i in ids]
        self.assertEqual(c0['context_flights'], p0)
        self.assertEqual(self.payload(root, 'c1')['context_flights'], p1)
        self.assertEqual(self.payload(root, 'rC1')['context_flights'], p0 + trial('c0', 'threat', self.cases.ids['P1']))
        self.assertEqual(self.payload(root, 'rD2')['context_flights'],
                         p1 + trial('c1', 'threat', self.cases.ids['P1']) + trial('rD1', 'threat', self.cases.ids['P1']))
        # A repair carries the refused source and Telohelm's one-line trial reason; a fresh sample carries no history.
        user = lambda cid: json.loads(json.loads(self.payload(root, cid)['model_payload_json'])[1][1])
        history = user('rC1')['previous_attempts']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['refused_at'], 'trial')
        self.assertEqual(history[0]['source'], HOLD_STILL[TASK])
        self.assertNotIn('previous_attempts', user('f2'))
        # Standalone call lists: C pays for c0 and its repairs, never for f1.
        calls = {json.loads(line)['candidate_id']: json.loads(line)['call_id']
                 for line in (root / 'usage.jsonl').read_text().splitlines()}
        self.assertEqual(arms['C']['call_ids'], [calls['c0'], calls['rC1'], calls['rC2']])
        self.assertEqual(arms['A']['call_ids'], arms['B']['call_ids'])
        # No reply text leaks into another arm: the repair requests never show an f candidate's source.
        self.assertNotIn('f1', json.dumps(self.payload(root, 'rC2')['context_flights']))

    def test_format_repair_and_lost_slot(self):
        plan = {('f1', 1): 'not a procedure', ('rC1', 1): '', ('rC1', 2): ''}
        b, root, sent = self.block('format', plan)
        b.run()
        f1 = json.loads((root / 'candidates' / 'f1' / 'candidate.json').read_text())
        self.assertTrue(f1['format_valid'])
        self.assertEqual(len(f1['call_ids']), 2)
        repair = json.loads((root / 'candidates' / 'f1' / 'calls' / '2.json').read_text())
        self.assertIn('Fix these problems', repair['model_payload_json'])
        # The initial payload is kept as sent: f1's request.json is still c0's request.
        self.assertEqual(self.payload(root, 'f1')['request_sha256'], self.payload(root, 'c0')['request_sha256'])
        rc1 = json.loads((root / 'candidates' / 'rC1' / 'candidate.json').read_text())
        self.assertFalse(rc1['format_valid'])
        self.assertTrue(rc1['empty_reply'])
        self.assertFalse((root / 'candidates' / 'rC1' / 'source.py').exists())
        arms = json.loads((root / 'arms.json').read_text())['arms']
        self.assertEqual(arms['C']['trials'][1], {'candidate_id': 'rC1', 'trial_list': 'threat', 'passed': False,
                                                  'flight_dir': None, 'outcomes': []})
        # After a lost slot the next repair is told why, and sees no new flights.
        user = json.loads(json.loads(self.payload(root, 'rC2')['model_payload_json'])[1][1])
        self.assertEqual(user['previous_attempts'][-1]['refused_at'], 'no_answer')
        self.assertEqual(self.payload(root, 'rC2')['context_flights'], self.payload(root, 'rC1')['context_flights'])

    def test_transport_failure_stops_the_block(self):
        from telohelm.runtime.models import ModelResponse
        plan = {('c1', 1): ModelResponse('failed', provider_ids={'error': 'APIConnectionError'})}
        b, root, sent = self.block('transport', plan)
        with self.assertRaises(L.InfrastructureFault):
            b.run()
        self.assertFalse((root / 'arms.json').exists())

    def test_a_repeated_message_id_stops_the_block_as_a_fault_of_the_service(self):
        """D3. The real provider, on a stand-in client whose every reply carries one message id: c0's first call is an
        answer, the next call (c1's) is a copy, and the block stops. The copy is in the provider's log as copied and
        is never written as a receipt."""
        from contextlib import contextmanager
        from types import SimpleNamespace
        from .claude_provider import ClaudeProvider
        text = procedure(HOLD_STILL[TASK])

        @contextmanager
        def stream(**kwargs):
            usage = SimpleNamespace(input_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                                    output_tokens=5)
            message = SimpleNamespace(content=[SimpleNamespace(type='text', text=text)], usage=usage,
                                      stop_reason='end_turn', id='msg_same', model=kwargs['model'])
            yield SimpleNamespace(get_final_message=lambda: message, request_id='req_1',
                                  response=SimpleNamespace(headers={}))
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)),
                                 messages=SimpleNamespace(count_tokens=lambda **kw: SimpleNamespace(input_tokens=10)))
        b, root, sent = self.block('repeated-id', {})
        b.provider.inner = ClaudeProvider(root / 'claude-usage.jsonl', client=client,
                                          gem_model='bedrock/au.anthropic.claude-sonnet-5-5')
        with self.assertRaises(L.InfrastructureFault) as caught:
            b.run()
        self.assertIn('RepeatedMessageId', str(caught.exception))
        self.assertFalse((root / 'arms.json').exists())
        logged = [json.loads(x) for x in (root / 'claude-usage.jsonl').read_text().splitlines()]
        self.assertEqual([r['status'] for r in logged], ['end_turn', 'copied'])
        # The copy has a spending row too (build F2), so the spending stop counts it; it has no receipt file.
        self.assertEqual([r['candidate_id'] for r in
                          (json.loads(x) for x in (root / 'usage.jsonl').read_text().splitlines())], ['c0', 'c1'])
        self.assertTrue((root / 'candidates' / 'c0' / 'calls' / '1.json').exists())
        self.assertFalse((root / 'candidates' / 'c1' / 'calls' / '1.json').exists())
        # The settings a call asked for carry the gateway cache fact, so it lands in usage.jsonl.
        row = json.loads((root / 'usage.jsonl').read_text().splitlines()[0])
        self.assertEqual(row['requested_settings']['gateway_cache'], 'no-cache,no-store')
        self.assertEqual(row['requested_settings']['via'], 'gem')

    def test_the_provider_is_given_the_run_root_and_the_blocks_name(self):
        """Build F1. make_proposer passes the run root on, so the provider reads and appends to the run's file of message
        ids; with no run root it is as before."""
        from types import SimpleNamespace
        client = SimpleNamespace()
        root = self.tmp / 'run' / 'learn3-reach-b0'
        root.mkdir(parents=True)
        with mock.patch('ardupilot.claude_provider.gem_client', return_value=client):
            _, provider = L.make_proposer(root, TASK, scored=False, gem_model='bedrock/au.anthropic.claude-sonnet-5-5',
                                          run_root=root.parent)
            self.assertEqual(provider.inner.run_ids.path, root.parent / 'message-ids.jsonl')
            self.assertEqual(provider.inner.run_ids.block, 'learn3-reach-b0')
            other = self.tmp / 'run' / 'learn3-reach-b1'
            other.mkdir()
            _, alone = L.make_proposer(other, TASK, scored=False, gem_model='bedrock/au.anthropic.claude-sonnet-5-5')
            self.assertIsNone(alone.inner.run_ids)

    def ledger_block(self, name, behaviours):
        """Build F2. The real provider on a stand-in client that does one thing per call: 'ok' (a new message id), 'copy'
        (the id of the call before it) or 'fault' (a connection error). Returns the run root, the folder of the block, and
        what the block raised. The block is moved into a run root under a scheduled name, where the spending stop reads it."""
        from contextlib import contextmanager
        from types import SimpleNamespace
        import anthropic
        from .claude_provider import ClaudeProvider
        text = procedure(HOLD_STILL[TASK])
        calls = []

        @contextmanager
        def stream(**kwargs):
            what = behaviours[min(len(calls), len(behaviours) - 1)]
            calls.append(what)
            if what == 'fault':
                raise anthropic.APIConnectionError(request=mock.Mock())
            number = len(calls) - 1 if what == 'copy' else len(calls)
            usage = SimpleNamespace(input_tokens=10 * len(calls), cache_creation_input_tokens=0,
                                    cache_read_input_tokens=0, output_tokens=5)
            message = SimpleNamespace(content=[SimpleNamespace(type='text', text=text)], usage=usage,
                                      stop_reason='end_turn', id=f'msg_{number}', model=kwargs['model'])
            yield SimpleNamespace(get_final_message=lambda: message, request_id=f'req_{len(calls)}',
                                  response=SimpleNamespace(headers={}))
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)),
                                 messages=SimpleNamespace(count_tokens=lambda **kw: SimpleNamespace(input_tokens=10)))
        b, root, sent = self.block(name, {})
        b.provider.inner = ClaudeProvider(root / 'claude-usage.jsonl', client=client,
                                          gem_model='bedrock/au.anthropic.claude-sonnet-5-5')
        raised = None
        try:
            b.run()
        except L.InfrastructureFault as fault:
            raised = fault
        run = self.tmp / (name + '-run')
        run.mkdir()
        shutil.move(str(root), str(run / 'learn3-reach-b0'))
        return run, run / 'learn3-reach-b0', raised

    def ledgers(self, folder):
        read = lambda name: [json.loads(x) for x in (folder / name).read_text().splitlines()]
        return read('claude-usage.jsonl'), read('usage.jsonl')

    def assert_ledgers_agree(self, run, folder, expect_calls):
        """Call for call, in order: the provider's row and the block's spending row name the same call and give the same
        list cost; and the stop's sum counts each call once."""
        from protocol import run_scored3 as R3
        provider, spending = self.ledgers(folder)
        self.assertEqual(len(provider), expect_calls)
        self.assertEqual([r['request_id'] for r in provider], [r['call_id'] for r in spending])
        self.assertEqual([r['cost_usd'] for r in provider], [r['list_cost_usd'] for r in spending])
        listed = round(sum(r['cost_usd'] or 0 for r in provider), 4)
        self.assertGreater(listed, 0)
        self.assertEqual(R3._usage_cost(folder / 'usage.jsonl')[0], sum(r['list_cost_usd'] or 0 for r in spending))
        with mock.patch.object(R3.Runner3, 'note', lambda *a: None):
            self.assertEqual(R3.Runner3(run, True).spent_usd(), listed)
        return provider, spending

    def test_the_two_ledgers_agree_call_for_call_for_a_normal_call(self):
        run, folder, raised = self.ledger_block('ledger-ok', ['ok'])
        self.assertIsNone(raised)
        provider, spending = self.assert_ledgers_agree(run, folder, 8)
        self.assertEqual({r['status'] for r in provider}, {'end_turn'})

    def test_the_two_ledgers_agree_call_for_call_for_a_copy(self):
        run, folder, raised = self.ledger_block('ledger-copy', ['ok', 'copy'])
        self.assertIn('RepeatedMessageId', str(raised))
        provider, spending = self.assert_ledgers_agree(run, folder, 2)
        self.assertEqual([r['status'] for r in provider], ['end_turn', 'copied'])
        self.assertEqual(spending[1]['status'], 'failed')
        # The copy has a list cost, and the stop counts it.
        self.assertGreater(spending[1]['list_cost_usd'], 0)
        self.assertFalse((folder / 'candidates' / 'c1' / 'calls' / '1.json').exists())

    def test_the_two_ledgers_agree_call_for_call_for_a_call_that_ended_in_a_fault(self):
        from protocol import run_scored3 as R3
        run, folder, raised = self.ledger_block('ledger-fault', ['ok', 'fault'])
        self.assertIn('model service failed', str(raised))
        provider, spending = self.ledgers(folder)
        self.assertEqual([r['status'] for r in provider], ['end_turn', 'failed'])
        self.assertEqual([r['request_id'] for r in provider], [r['call_id'] for r in spending])
        self.assertEqual([r['cost_usd'] if 'cost_usd' in r else None for r in provider],
                         [r['list_cost_usd'] for r in spending])
        # A call with no reply has no list cost: counted as US$0 and reported as unknown, once.
        self.assertEqual(R3._usage_cost(folder / 'usage.jsonl'), (spending[0]['list_cost_usd'], 1))

    def test_time_out_stops_the_block(self):
        from telohelm.runtime.models import ModelResponse
        b, root, sent = self.block('timeout', {('c0', 1): ModelResponse('timed_out')})
        with self.assertRaises(L.InfrastructureFault):
            b.run()
        self.assertFalse((root / 'arms.json').exists())

    def test_late_flight_stops_before_any_request(self):
        b, root, sent = self.block('late', {}, late={self.cases.ids['P1'][1]})
        with self.assertRaises(L.InfrastructureFault):
            b.run()
        self.assertEqual(sent, [])
        self.assertFalse((root / 'candidates').exists())

    def real_fly(self, name, late_at, late_flights='refly'):
        """The block's own fly(), with battle.run replaced by a copy of the recorded fixture. late_at: attempt number to
        the episode ids that fly late at that attempt. Returns the block, its folder and the episode ids."""
        root = self.tmp / name
        root.mkdir()
        proposer, provider = L.make_proposer(root, TASK, scored=False, gem_model=None,
                                             stub=lambda label, request: None)
        b = L.Block(root, TASK, 0, self.cases.matched, self.cases.threat, proposer, provider, speedup=10.0,
                    instance=10, late_flights=late_flights)
        fixture, attempts = self.tmp / 'fixture', []

        def run(out, task, source, origin, cases=None, speedup=10.0, instance=0, command_delay_periods=None):
            assert command_delay_periods == L.COMMAND_DELAY_PERIODS
            out = Path(out)
            out.mkdir(parents=True)
            attempts.append(out)
            (out / 'run-config.json').write_text(json.dumps({'origin': origin, 'source': source,
                                                            'scenarios': [c.episode_id for c in cases]}))
            for c in cases:
                shutil.copytree(fixture / 'P0' / c.episode_id, out / c.episode_id)
                o = json.loads((out / c.episode_id / 'outcome.json').read_text())
                for st in o['native_steps']:
                    st['decision_lag_s'] = 1.0 if c.episode_id in late_at.get(len(attempts), ()) else 0.001
                (out / c.episode_id / 'outcome.json').write_text(json.dumps(o))
        return b, root, run

    def test_late_call_is_flown_again_in_place_and_the_late_attempt_kept_aside_unread(self):
        ids = self.cases.ids['P0']
        b, root, run = self.real_fly('refly-once', {1: {ids[1]}})
        with mock.patch('ardupilot.battle.run', run):
            outcomes = b.fly('flights/first/P0', [], self.cases.matched)
        self.assertEqual(sorted(outcomes), sorted(ids))
        self.assertFalse(any(L.timing(o)['late'] for o in outcomes.values()))
        aside = root / L.LATE_DIR / 'flights/first/P0/attempt-1'
        self.assertTrue((aside / ids[1] / 'outcome.json').exists())
        self.assertFalse((root / L.LATE_DIR / 'flights/first/P0/attempt-2').exists())
        rows = json.loads((root / 'timing.json').read_text())
        self.assertEqual([r['attempt'] for r in rows], [1] * len(ids) + [2] * len(ids))
        self.assertEqual(rows[1]['flight'], f'{L.LATE_DIR}/flights/first/P0/attempt-1/{ids[1]}')
        self.assertEqual(rows[1]['set_aside_from'], f'flights/first/P0/{ids[1]}')
        self.assertTrue(rows[1]['late'])
        self.assertTrue(all(isinstance(r['peak_rss_bytes'], int) and r['peak_rss_bytes'] > 0 for r in rows))
        self.assertFalse(any('kept_late' in r for r in rows))

    def test_third_late_attempt_is_kept_and_marked(self):
        ids = self.cases.ids['P0']
        b, root, run = self.real_fly('refly-kept', {1: {ids[0]}, 2: {ids[0]}, 3: {ids[0]}})
        with mock.patch('ardupilot.battle.run', run):
            outcomes = b.fly('flights/first/P0', [], self.cases.matched)
        self.assertTrue(L.timing(outcomes[ids[0]])['late'])
        self.assertEqual(sorted(p.name for p in (root / L.LATE_DIR / 'flights/first/P0').iterdir()),
                         ['attempt-1', 'attempt-2'])
        rows = json.loads((root / 'timing.json').read_text())
        kept = [r for r in rows if r['attempt'] == L.REFLIGHTS + 1]
        self.assertEqual([r['flight'] for r in kept], [f'flights/first/P0/{i}' for i in ids])
        self.assertEqual([r['kept_late'] for r in kept], [i == ids[0] for i in ids])

    def test_on_time_call_flies_once_and_writes_no_late_folder(self):
        b, root, run = self.real_fly('on-time', {})
        with mock.patch('ardupilot.battle.run', run):
            b.fly('flights/first/P0', [], self.cases.matched)
        self.assertFalse((root / L.LATE_DIR).exists())
        rows = json.loads((root / 'timing.json').read_text())
        self.assertEqual({r['attempt'] for r in rows}, {1})
        self.assertFalse(any('set_aside_from' in r or 'kept_late' in r for r in rows))

    def test_refly_through_the_real_battle_run_with_the_load_check(self):
        """The seam: Block.fly in refly mode over the real battle.run, with only the episode itself replaced, so the
        second run into the same path after the move, and before_flight's record in results.jsonl, are exercised."""
        from telohelm.runtime import episode_loop
        ids, flown, gates = self.cases.ids['P0'], [], []

        def episode(scenario, library, models, log, ledger, max_steps=None, broker=None, pack=None):
            flown.append(scenario.episode_id)
            late = len(flown) <= len(ids) and scenario.episode_id == ids[0]      # the first attempt's first flight
            steps = [{'t': i + 1, 'decision_lag_s': 1.0 if late else 0.001, 'observation_lag_s': 0.0,
                      'command_lag_s': 1.0 if late else L.COMMAND_DELAY_S, 'estimate_error_m': 0.1} for i in range(3)]
            return {'outcome': {'goal_met': False, 'end_reason': 'timed_out', 'action_steps': 3, 'native_steps': steps,
                                'closest_threat_m': None, 'events': [], 'command_delay_s': L.COMMAND_DELAY_S}}
        root = self.tmp / 'seam'
        root.mkdir()
        proposer, provider = L.make_proposer(root, TASK, scored=False, gem_model=None, stub=lambda label, request: None)
        b = L.Block(root, TASK, 0, self.cases.matched, self.cases.threat, proposer, provider, speedup=10.0,
                    instance=10, late_flights='refly',
                    before_flight=lambda sc: gates.append(sc.episode_id) or {'load_1min': 1.0, 'waited_s': 0})
        with mock.patch.object(episode_loop, 'run_episode', episode):
            outcomes = b.fly('flights/first/P0', [], self.cases.matched)
        self.assertEqual(flown, ids + ids)
        self.assertEqual(gates, ids + ids)                       # the check ran before every flight of both attempts
        self.assertFalse(any(L.timing(o)['late'] for o in outcomes.values()))
        for folder in (root / 'flights/first/P0', root / L.LATE_DIR / 'flights/first/P0/attempt-1'):
            rows = [json.loads(x) for x in (folder / 'results.jsonl').read_text().splitlines()]
            self.assertEqual([r['before_flight'] for r in rows], [{'load_1min': 1.0, 'waited_s': 0}] * len(ids))
            self.assertTrue((folder / 'library').is_dir() and (folder / 'run-config.json').is_file())
        self.assertEqual(json.loads((root / L.LATE_DIR / 'flights/first/P0/attempt-1' / ids[0] / 'outcome.json')
                                    .read_text())['native_steps'][0]['decision_lag_s'], 1.0)

    def test_stop_mode_still_stops_and_a_scored_block_must_fly_again(self):
        ids = self.cases.ids['P0']
        b, root, run = self.real_fly('stop', {1: {ids[0]}}, late_flights='stop')
        with mock.patch('ardupilot.battle.run', run), self.assertRaises(L.InfrastructureFault):
            b.fly('flights/first/P0', [], self.cases.matched)
        self.assertFalse((root / L.LATE_DIR).exists())
        with self.assertRaises(ValueError):
            L.run_block(self.tmp / 'nowhere', TASK, 0, [], [], speedup=1.0, instance=10, scored=True,
                        gem_model='m', late_flights='stop')

    def test_late_flight_recorded_in_a_pilot(self):
        b, root, sent = self.block('late-pilot', {}, late={self.cases.ids['P0'][0]}, late_flights='record')
        b.run()
        timing = json.loads((root / 'timing.json').read_text()) if (root / 'timing.json').exists() else b.timing
        self.assertTrue(any(t['late'] for t in timing))

    # -- timing -------------------------------------------------------------------------------------------------

    def test_recorded_flight_is_late_by_the_one_second_rule(self):
        o = json.loads((self.tmp / 'fixture' / 'P0' / 'matched-close-4000001' / 'outcome.json').read_text())
        self.assertEqual(o['native_steps'][0]['decision_lag_s'], 1.001)
        self.assertTrue(L.timing(o)['late'])                 # 1.001 s from its observation: a missed deadline too
        t = L.timing_before_delay(o)
        self.assertEqual((t['median_lag_s'], t['max_lag_s'], t['late']), (0.001, 1.001, True))
        self.assertIn('1.001 s late', L.late_reason(t))

    def test_timing_rule_and_its_boundaries(self):
        def flight(lags):
            return {'native_steps': [{'decision_lag_s': x} for x in lags]}
        quiet = [0.001] * 9
        self.assertFalse(L.timing_before_delay(flight(quiet + [0.994]))['late'])        # just under the 0.995 s threshold is on time
        self.assertTrue(L.timing_before_delay(flight(quiet + [0.995]))['late'])         # 'at least' 0.995 s (item 8): late
        self.assertTrue(L.timing_before_delay(flight(quiet + [1.0]))['late'])
        self.assertTrue(L.timing_before_delay(flight(quiet + [1.001]))['late'])         # the pilot's case: median 0.001 s passed it
        self.assertFalse(L.timing_before_delay(flight([0.05] * 9))['late'])             # a median of exactly 0.05 s is on time
        # Lag is read on the 0.1 s telemetry step from 0.005 s below it (item 8), so 0.094 s is no step and 0.095 s one.
        self.assertFalse(L.timing_before_delay(flight([0.094] * 9))['late'])
        self.assertTrue(L.timing_before_delay(flight([0.095] * 9))['late'])
        # More than half the decisions a step late is late; exactly half is on time, whichever of 0.0 or 0.001 s and
        # 0.098, 0.1 or 0.101 s the stamps happen to give (12 November 2026: such a tie read 0.0505 s and was late).
        self.assertTrue(L.timing_before_delay(flight([0.0] * 3 + [0.1] * 5))['late'])
        for low, high in ((0.0, 0.098), (0.001, 0.1), (0.0, 0.101), (0.001, 0.101)):
            self.assertFalse(L.timing_before_delay(flight([low] * 4 + [high] * 4))['late'], (low, high))
        # Exactly half is late when every lag in the late half is two steps or more: the median of 0 and 2 steps is one
        # step. With any one-step lag in the late half the median is half a step, which is on time.
        self.assertTrue(L.timing_before_delay(flight([0.0] * 4 + [0.2] * 4))['late'])
        self.assertTrue(L.timing_before_delay(flight([0.001] * 4 + [0.201, 0.198, 0.3, 0.2]))['late'])
        self.assertFalse(L.timing_before_delay(flight([0.0] * 4 + [0.1, 0.2, 0.2, 0.2]))['late'])
        for bad in ([], [0.0, None, 0.0], [0.0, math.nan], [0.0, math.inf], [0.0, 'x']):
            self.assertTrue(L.timing_before_delay(flight(bad))['late'], bad)
        self.assertTrue(L.timing_before_delay({})['late'])

    def test_recorded_flight_with_five_of_eight_one_step_lags_is_late(self):
        # Recorded on instance 12 in the second timing preflight (runs/timing-preflight-20261112-065219, reach, four at
        # once, 00-threat-close-4100001): (sim_s, decision_lag_s) for each step. Five of eight lags are one step, more
        # than half, so the flight is late as it was flown.
        rec = [(1.098, 0.1), (2.0, 0.098), (3.098, 0.0), (4.0, 0.098), (5.098, 0.0), (6.0, 0.098), (7.0, 0.0), (8.0, 0.098)]
        t = L.timing_before_delay({'native_steps': [{'sim_s': s, 'decision_lag_s': x} for s, x in rec]})
        self.assertEqual((t['median_lag_s'], t['step_median_lag_s'], t['late_share_0_1s'], t['late']),
                         (0.098, 0.1, 0.625, True))

    def test_recorded_tie_is_on_time(self):
        # Recorded on instance 10 in the second preflight (reach, four at once, 05-threat-wide-4100202): four of eight
        # decisions one step late. Recorded median 0.0505 s, called late as flown; read on the step it is 0.05 s.
        rec = [(1.001, 0.0), (2.0, 0.001), (3.001, 0.1), (4.0, 0.101), (5.001, 0.1), (6.0, 0.001), (7.001, 0.1), (8.0, 0.001)]
        t = L.timing_before_delay({'native_steps': [{'sim_s': s, 'decision_lag_s': x} for s, x in rec]})
        self.assertEqual((t['median_lag_s'], t['step_median_lag_s'], t['late_share_0_1s'], t['late']),
                         (0.0505, 0.05, 0.5, False))

    def test_late_share_counts_from_0_095_s(self):
        t = L.timing_before_delay({'native_steps': [{'decision_lag_s': x} for x in (0.0, 0.094, 0.095, 0.098, 0.1)]})
        self.assertEqual(t['late_share_0_1s'], 0.6)

    def test_late_flight_fault_says_which_rule(self):
        t = L.timing_before_delay({'native_steps': [{'decision_lag_s': 0.001}] * 9 + [{'decision_lag_s': 1.2}]})
        self.assertEqual(L.late_reason(t), 'a decision was 1.2 s late')
        self.assertIn('median decision lag 0.3', L.late_reason(L.timing_before_delay({'native_steps': [{'decision_lag_s': 0.3}]})))

    # The rule since 13 November 2026 (round four, ruling 2): a deadline of COMMAND_DELAY_PERIODS telemetry steps from
    # each decision's own observation, and nothing else. The tests above keep the rule of its time for older records.

    def flown(self, lags, seen=None, sent=None, delay=None):
        n = len(lags)
        seen = [0.0] * n if seen is None else seen
        sent = [L.COMMAND_DELAY_S] * n if sent is None else sent
        o = {'native_steps': [{'decision_lag_s': x, 'observation_lag_s': y, 'command_lag_s': z}
                              for x, y, z in zip(lags, seen, sent)],
             'command_delay_s': L.COMMAND_DELAY_S if delay is None else delay}
        return o

    def test_the_deadline_rule_and_its_boundaries(self):
        k = L.COMMAND_DELAY_PERIODS
        self.assertEqual((L.COMMAND_DELAY_PERIODS, L.COMMAND_DELAY_S), (3, 0.3))
        just_in = round(k * 0.1 - 0.006, 3)        # 0.294 s: k - 1 steps, ready in time
        just_out = round(k * 0.1 - 0.005, 3)       # 0.295 s: k steps, the deadline's stamp already read
        # Every decision a step late from its own observation is on time: the slow group no longer makes a flight late.
        t = L.timing(self.flown([0.1] * 9))
        self.assertEqual((t['late'], t['missed_deadlines'], t['off_deadline_commands'], t['step_median_lag_s']),
                         (False, 0, 0, 0.1))
        self.assertFalse(L.timing(self.flown([0.001] * 8 + [just_in]))['late'])
        t = L.timing(self.flown([0.001] * 8 + [just_out], sent=[L.COMMAND_DELAY_S] * 8 + [just_out]))
        self.assertEqual((t['late'], t['missed_deadlines']), (True, 1))
        self.assertIn('missed the 0.3 s deadline', L.late_reason(t))
        self.assertTrue(L.timing(self.flown([0.001] * 8 + [1.2], sent=[L.COMMAND_DELAY_S] * 8 + [1.2]))['late'])

    def test_the_deadline_counts_from_the_observation_not_the_schedule(self):
        # Decision 75 onward: the observation read a step after its schedule (notes/round4-reads-20261113,
        # observation_late.txt). A decision ready two steps after the schedule is then one step after its observation.
        lags = [0.1, 0.2, 0.1, 0.201, 0.098]
        seen = [0.0, 0.1, 0.0, 0.1, 0.0]
        t = L.timing(self.flown(lags, seen))
        self.assertEqual((t['late'], t['observations_late'], t['max_own_lag_s']), (False, 2, 0.101))
        # Three steps from the schedule with the observation a step late is two from the observation: still in time.
        self.assertFalse(L.timing(self.flown([0.3], [0.1]))['late'])
        # Four steps from the schedule with the observation a step late is three from it: missed.
        self.assertTrue(L.timing(self.flown([0.4], [0.1], [0.3]))['late'])

    def test_a_command_off_its_deadline_stamp_is_late(self):
        # Ready in time but sent a stamp after the deadline (a stamp skipped during the hold): should never happen.
        t = L.timing(self.flown([0.001] * 9, sent=[L.COMMAND_DELAY_S] * 8 + [0.4]))
        self.assertEqual((t['late'], t['missed_deadlines'], t['off_deadline_commands']), (True, 0, 1))
        self.assertIn('off their deadline', L.late_reason(t))
        self.assertFalse(L.timing(self.flown([0.001] * 3, sent=[0.298, 0.3, 0.301]))['late'])

    def test_a_flight_without_the_delay_or_a_field_is_late(self):
        on_time = self.flown([0.001] * 9)
        self.assertFalse(L.timing(on_time)['late'])
        for delay in (0.2, 0.0, 'x', math.nan):
            t = L.timing(self.flown([0.001] * 9, delay=delay))
            self.assertTrue(t['late'], delay)
            self.assertIn('without the fixed delay', L.late_reason(t))
        missing = self.flown([0.001] * 9)
        del missing['command_delay_s']
        self.assertTrue(L.timing(missing)['late'])
        # A flight recorded before the delay, with decision_lag_s only, is late by this rule.
        self.assertTrue(L.timing({'native_steps': [{'decision_lag_s': 0.001}] * 9})['late'])
        for field in ('decision_lag_s', 'observation_lag_s', 'command_lag_s'):
            for bad in (None, math.nan, math.inf, 'x'):
                o = self.flown([0.001] * 3)
                o['native_steps'][1][field] = bad
                t = L.timing(o)
                self.assertTrue(t['late'], (field, bad))
                self.assertIn('missing or not finite', L.late_reason(t))
        self.assertTrue(L.timing({'command_delay_s': L.COMMAND_DELAY_S, 'native_steps': []})['late'])
        self.assertTrue(L.timing({})['late'])

    def test_the_reported_fields_compare_with_the_earlier_records(self):
        lags = [0.0, 0.094, 0.095, 0.098, 0.1]
        t = L.timing(self.flown(lags))
        u = L.timing_before_delay({'native_steps': [{'decision_lag_s': x} for x in lags]})
        for k in ('median_lag_s', 'max_lag_s', 'late_share_0_1s', 'step_median_lag_s'):
            self.assertEqual(t[k], u[k], k)

    # -- poisoned-holdout controls ------------------------------------------------------------------------------

    def planted(self, root):
        """An evaluation case and a retention case, each a recorded flight under an id that holds a marker and with the
        marker in its logs, placed inside the block's own folder where a careless driver could find them."""
        out = {}
        for kind, mark in (('eval', 'ZQEVAL5f21'), ('retain', 'ZQRETAIN5f21')):
            case = replace(self.cases.threat[0], episode_id=f'threat-{mark}-9')
            folder = root / 'flights' / kind / case.episode_id
            shutil.copytree(self.tmp / 'fixture' / 'P1' / self.cases.ids['P1'][0], folder)
            plant_text(folder, mark)
            out[kind] = (mark, case, folder)
        return out

    def leaky_run(self, name, patch=None):
        """A marked block with the planted cases present, run with patch(planted) -> (owner, attribute, replacement)
        applied to the driver, if given. Returns the root, the leaks found and the planted cases."""
        from unittest import mock
        b, root, sent = self.block(name, {}, marks=True)
        planted = self.planted(root)
        strings = [x for mark, case, folder in planted.values() for x in (mark, case.episode_id)]
        if patch is None:
            b.run()
        else:
            with mock.patch.object(*patch(planted)):
                b.run()
        return root, leaks(root, strings), planted

    # -- which flights a request shows ----------------------------------------------------------------------------

    FLIGHT_MARKER = re.compile(r'ZF~([A-Za-z0-9~.-]+)')

    @classmethod
    def flights_in(cls, text):
        """The flight folders whose per-flight marker appears in a model-visible text."""
        return {m.replace('~', '/') for m in cls.FLIGHT_MARKER.findall(text)}

    def test_shown_flights_are_the_flights_whose_markers_appear_in_the_text(self):
        root, found, _ = self.leaky_run('shown')
        self.assertEqual(found, {})
        b, root, _ = self.block('shown-marked', {}, marks=True)
        b.run()
        for cid in ALL_CIDS:
            request = self.payload(root, cid)
            with self.subTest(candidate=cid):
                shown = request['shown_flights']
                self.assertEqual(set(shown), self.flights_in(request['model_payload_json']))
                self.assertEqual(len(shown), len(set(shown)))
                self.assertTrue(set(shown) <= set(request['context_flights']))
                self.assertTrue(shown, 'the control would prove nothing if no flight were shown')
                for call in sorted((root / 'candidates' / cid / 'calls').glob('*.json')):
                    receipt = json.loads(call.read_text())
                    self.assertEqual(set(receipt['shown_flights']), self.flights_in(receipt['model_payload_json']))
        # The text shows less than the learner has seen: a repair shows only the flights of the trial just flown.
        rc2 = self.payload(root, 'rC2')
        self.assertTrue(any('flights/first/' in f for f in rc2['context_flights']))
        self.assertEqual(rc2['shown_flights'], [f for f in rc2['context_flights'] if 'flights/trial/rC1/' in f])

    def test_a_format_repair_shows_what_its_request_showed_or_less(self):
        b, root, _ = self.block('shown-repair', {('f1', 1): 'not a procedure'}, marks=True)
        b.run()
        first = json.loads((root / 'candidates' / 'f1' / 'calls' / '1.json').read_text())
        second = json.loads((root / 'candidates' / 'f1' / 'calls' / '2.json').read_text())
        self.assertEqual(first['shown_flights'], self.payload(root, 'f1')['shown_flights'])
        self.assertEqual(set(second['shown_flights']), self.flights_in(second['model_payload_json']))
        self.assertTrue(set(second['shown_flights']) <= set(first['shown_flights']))

    def test_the_text_sent_is_byte_for_byte_what_it_was_before_shown_flights(self):
        """request_sha256 of every candidate in an unmarked run that fails every trial, taken from the driver before
        shown_flights was recorded (main at 80facbc0). Recording the flights must change no request text."""
        b, root, _ = self.block('golden', {})
        b.run()
        got = {cid: self.payload(root, cid)['request_sha256'] for cid in ALL_CIDS}
        self.assertEqual(got, GOLDEN_REQUEST_SHA256)
        # No request names a layout by its case id: the trial reason gives the alias in arm C as in arm D.
        for cid in ALL_CIDS:
            self.assertNotRegex(self.payload(root, cid)['model_payload_json'], r'(matched|threat)-(close|middle|wide)-\d')

    def test_the_delay_sentence_is_the_only_difference_in_every_request(self):
        """B5. Each of the eight requests of a block (every arm's first and repair calls) carries the sentence once, and
        with that sentence cut out its text hashes to what the request's text hashed to before the sentence existed."""
        b, root, _ = self.block('delay-sentence', {})
        b.run()
        sentence = L.delay_sentence()
        procedure_only = json.dumps('\n' + P.PROCEDURE_ONLY)[1:-1]       # as it sits inside the JSON text
        for cid in ALL_CIDS:
            with self.subTest(candidate=cid):
                text = self.payload(root, cid)['model_payload_json']
                self.assertEqual(text.count(sentence), 1)
                self.assertEqual(text.count(procedure_only), 1)
                self.assertEqual(L._sha(text.replace(procedure_only, '').replace(sentence, '')), GOLDEN_REQUEST_SHA256_BEFORE_DELAY_SENTENCE[cid])
                self.assertEqual(L._sha(text), GOLDEN_REQUEST_SHA256[cid])
                # No request gains a time or lag field: the sentence is text in the goal and nothing else is added.
                self.assertEqual(len(json.loads(text)), 2)
                self.assertNotIn('delay', json.loads(json.loads(text)[1][1]))
                self.assertNotIn('lag', json.loads(json.loads(text)[1][1]))

    def test_every_request_carries_the_procedure_only_sentence_once_in_the_system_text(self):
        """D1. The saved request of every candidate kind (c0, c1, f1, f2, rC*, rD*) and the request of every repair call
        carries pack.PROCEDURE_ONLY once in the system message, on its own line, and learn.py uses the same text. The
        core appends extra_rules to its rules and then, with examples on, the example rules after them (learning.py,
        Coordinator.messages), so the sentence is followed by the example rules, as in the fuzz learner's requests."""
        from . import learn
        self.assertIs(learn.PROCEDURE_ONLY, P.PROCEDURE_ONLY)
        b, root, _ = self.block('procedure-only', {})
        b.run()
        for cid in ALL_CIDS:
            with self.subTest(candidate=cid):
                messages = json.loads(self.payload(root, cid)['model_payload_json'])
                self.assertEqual(messages[0][0], 'system')
                self.assertEqual(messages[0][1].count('\n' + P.PROCEDURE_ONLY + '\n'), 1)
                self.assertEqual(sum(P.PROCEDURE_ONLY in m[1] for m in messages), 1)
                for call in (root / 'candidates' / cid / 'calls').glob('*.json'):
                    sent = json.loads(json.loads(call.read_text())['model_payload_json'])
                    self.assertEqual(sent[0][1].count('\n' + P.PROCEDURE_ONLY + '\n'), 1)

    def test_the_sentence_reads_its_number_from_the_constant(self):
        self.assertEqual(L.delay_sentence(), 'Each command you return is sent to the drone 0.3 s after the observation it '
                         'was computed from; until then the drone keeps flying on the previous command. ')
        self.assertIn(f'{L.COMMAND_DELAY_S} s after', L.delay_sentence())
        for periods in (2, 4):
            with mock.patch.object(L, 'COMMAND_DELAY_S', round(periods * L.TELEMETRY_STEP_MS / 1000, 3)):
                self.assertIn(f'drone {periods / 10} s after', L.delay_sentence())
                self.assertIn(L.delay_sentence(), L.protocol3_pack('reach').public.learner_goal)

    # What the core's learner rules hashed to for each task before 16 November 2026. They are what protocol 2 sends as
    # the system text, from the pack as pack.py builds it; the delay sentence is added only to protocol 3's copy.
    PROTOCOL_2_RULES_SHA256 = {
        'reach': '650a96b92bc9b01756c057f2ba9fb59b4b04c1977599fbc388b27e268fb74466',
        'reach3d': 'bc85785d8f605b083764e9393a185f3dfe9f847c5bc379f67b1cce566a223df5',
        'avoid': '8fa775a14c5a95ab6000e64e2fced93e8d91c06812ad19150803139149f887e8',
        'orbit': '5a399b0e8cef44854d82d2172f4193467162ab1bc016e45abc53ff0bc2a7626e',
        'land': '67d4dc8d369cacbfdf255b92a95681bdcc3b7bd03121bd669cf10777e30a86c4',
        'race3d': '51ed048ca443699c3918f8269f79cf577b6a9fbaad830bb15e8ea88690c6aed0'}

    def test_protocol_2_request_text_is_unchanged_byte_for_byte(self):
        from telohelm import learning
        self.assertEqual(set(self.PROTOCOL_2_RULES_SHA256), set(P.TASKS))
        for task, expected in self.PROTOCOL_2_RULES_SHA256.items():
            with self.subTest(task=task):
                rules = learning.render_learner_rules(P.PACKS[task].public, learning.learner_limits())
                self.assertEqual(L._sha(rules), expected)
                self.assertNotIn('sent to the drone', rules)
        # Building protocol 3's copy leaves the shared pack alone.
        before = P.PACKS['reach']
        self.assertIsNot(L.protocol3_pack('reach'), before)
        self.assertIs(P.PACKS['reach'], before)
        self.assertNotIn('sent to the drone', P.PACKS['reach'].public.learner_goal)

    def test_the_golden_requests_hold_through_the_real_fly_in_refly_mode(self):
        """A block with no late flight is unchanged by flying again in place: the block's own Block.fly in refly mode,
        over battle.run replaced by the fixture copy, sends the same eight requests, returns exactly the outcomes in
        the files, and writes no late/ folder (code review of 13 November 2026, finding 2)."""
        from telohelm.runtime.library import Library
        fixture, returned = self.tmp / 'fixture', []
        b, root, _ = self.block('golden-real', {})
        del b.fly                                # the class's own fly, not fake_fly
        b.late_flights = 'refly'

        def battle_run(out, task, source, origin, cases=None, speedup=10.0, instance=0, before_flight=None,
                       command_delay_periods=None):
            assert command_delay_periods == L.COMMAND_DELAY_PERIODS
            out = Path(out)
            out.mkdir(parents=True)
            family = 'P0' if cases[0].episode_id.startswith('matched') else 'P1'
            library = Library(out / 'library', pack=P.PACKS[task].public)
            for code in source:
                sha = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': code,
                                   'origin': {'imported_from': origin}})
                library.set_status(sha, 'adopted', 'test')
            for c in cases:
                shutil.copytree(fixture / family / c.episode_id, out / c.episode_id)
                o = json.loads((out / c.episode_id / 'outcome.json').read_text())
                if c.episode_id in RECORDED_LATE:
                    step, lag = RECORDED_LATE[c.episode_id]
                    o['native_steps'][step]['decision_lag_s'] = 0.001
                (out / c.episode_id / 'outcome.json').write_text(json.dumps(o))

        def fly(rel, sources, cases):
            got = L.Block.fly(b, rel, sources, cases)
            returned.append((rel, got))
            return got
        b.fly = fly
        with mock.patch('ardupilot.battle.run', battle_run):
            b.run()
        got = {cid: self.payload(root, cid)['request_sha256'] for cid in ALL_CIDS}
        self.assertEqual(got, GOLDEN_REQUEST_SHA256)
        self.assertFalse((root / L.LATE_DIR).exists())
        self.assertTrue(returned)
        for rel, outcomes in returned:
            for episode, o in outcomes.items():
                self.assertEqual(o, json.loads((root / rel / episode / 'outcome.json').read_text()))

    def test_clean_driver_shows_no_request_a_foreign_flight(self):
        root, found, planted = self.leaky_run('clean')
        self.assertEqual(found, {})
        # The control can see: each request does show the flights it is allowed to show.
        self.assertIn('ZQ-P0', shown_markers(root, 'c0'))
        self.assertIn('ZQ-P1', shown_markers(root, 'c1'))
        self.assertIn('ZQ-c0-threat', shown_markers(root, 'rC1'))
        self.assertIn('ZQ-c1-threat', shown_markers(root, 'rD1'))
        # The planted evaluation and retention cases are on disk, inside the block, and unread.
        self.assertTrue(all(folder.exists() for _m, _c, folder in planted.values()))

    @staticmethod
    def hand_leak(view_name, folders_for):
        """A patch of Block._refuse_previous under which one view also sees the flights folders_for(block, planted) names,
        each as (scenario, folder, name), as the newest episodes it has seen."""
        def patch(planted):
            orig, done = L.Block._refuse_previous, []

            def leaky(block, view, previous, family):
                orig(block, view, previous, family)
                if view.name == view_name and not done:          # at the view's first repair
                    done.append(1)
                    for scenario, folder, name in folders_for(block, planted):
                        view.see(scenario, folder, name=name)
            return L.Block, '_refuse_previous', leaky
        return patch

    def test_control_fails_when_an_evaluation_case_is_shown_to_a_repair(self):
        patch = self.hand_leak('D', lambda b, pl: [(pl['eval'][1], pl['eval'][2], pl['eval'][1].episode_id)])
        root, found, _ = self.leaky_run('leak-eval', patch)
        self.assertIn('rD1', found)
        self.assertIn('ZQEVAL5f21', found['rD1'])
        self.assertNotIn('rC1', found)

    def test_control_fails_when_a_retention_case_is_shown_to_a_repair(self):
        patch = self.hand_leak('C', lambda b, pl: [(pl['retain'][1], pl['retain'][2], pl['retain'][1].episode_id)])
        root, found, _ = self.leaky_run('leak-retain', patch)
        self.assertIn('ZQRETAIN5f21', found.get('rC1', set()))

    def test_control_fails_when_another_arms_flights_are_shown(self):
        def trial(family, cid):
            return lambda b, pl: [(c, b.root / 'flights' / 'trial' / cid / family / c.episode_id,
                                   f'{c.episode_id}-{cid}x') for c in b.cases[family]]
        zone_first_round = lambda b, pl: [(c, b.root / 'flights' / 'first' / 'P1' / c.episode_id, f'{c.episode_id}-z')
                                          for c in b.cases['threat']]
        for view, folders, cid, marker in (('C', trial('matched', 'c0'), 'rC1', 'ZQ-c0-matched'),   # arm A's trial
                                           ('C', trial('threat', 'f1'), 'rC1', 'ZQ-f1-threat'),     # arm B's trial
                                           ('D', trial('threat', 'c0'), 'rD1', 'ZQ-c0-threat'),     # B and C's trial
                                           ('C', zone_first_round, 'rC1', 'ZQ-P1')):                # arm D's zone flights
            with self.subTest(view=view, marker=marker):
                root, found, _ = self.leaky_run(f'leak-{view}-{marker}', self.hand_leak(view, folders))
                self.assertIn(marker, found.get(cid, set()))

    # -- empty replies, rejected commands, an interrupted block ---------------------------------------------------

    def test_empty_and_blank_replies_use_up_the_slot_without_a_fault(self):
        from telohelm.runtime.models import ModelResponse
        # Since 13 November 2026 an empty reply gets no format-repair call (round three, leak inspection finding 2).
        b, root, sent = self.block('empty-c0', {('c0', 1): '', ('c0', 2): procedure(HOLD_STILL[TASK])})
        record = b.run()
        c0 = json.loads((root / 'candidates' / 'c0' / 'candidate.json').read_text())
        self.assertEqual((c0['format_valid'], c0['empty_reply'], len(c0['call_ids'])), (False, True, 1))
        self.assertNotIn(('c0', 2), sent)
        self.assertFalse(record['c0_zone_qualified'])
        for arm in 'ABC':
            self.assertEqual(record['arms'][arm]['trials'][0],
                             {'candidate_id': 'c0', 'trial_list': L.ARMS[arm][0], 'passed': False, 'flight_dir': None,
                              'outcomes': []})
            self.assertEqual(len(record['arms'][arm]['trials']), 3)
        self.assertFalse((root / 'flights' / 'trial' / 'c0').exists())
        user = json.loads(json.loads(self.payload(root, 'rC1')['model_payload_json'])[1][1])
        self.assertEqual(user['previous_attempts'][-1]['refused_at'], 'no_answer')
        rows = [json.loads(x) for x in (root / 'usage.jsonl').read_text().splitlines()]
        self.assertEqual([r['call'] for r in rows if r['candidate_id'] == 'c0'], [1])
        # A blank answer (whitespace only) is treated the same way.
        b, root, sent = self.block('blank-c0', {('c0', 1): ModelResponse('answered', '   \n')})
        b.run()
        c0 = json.loads((root / 'candidates' / 'c0' / 'candidate.json').read_text())
        self.assertEqual((c0['format_valid'], c0['empty_reply'], len(c0['call_ids'])), (False, True, 1))
        # A non-empty reply that breaks the format still gets its repair call.
        b, root, sent = self.block('bad-c0', {('c0', 1): 'not a procedure', ('c0', 2): procedure(HOLD_STILL[TASK])})
        b.run()
        c0 = json.loads((root / 'candidates' / 'c0' / 'candidate.json').read_text())
        self.assertEqual((c0['format_valid'], len(c0['call_ids'])), (True, 2))

    def test_every_slot_empty_adopts_nothing_and_is_no_fault(self):
        b, root, sent = self.block('empty-all', {(cid, k): '' for cid in ALL_CIDS for k in (1, 2)})
        record = b.run()
        self.assertFalse(any(a['adopted'] for a in record['arms'].values()))
        self.assertEqual(len(sent), 8)            # eight candidates, one call each: no repair after an empty reply
        self.assertTrue((root / 'arms.json').exists())

    def test_a_refused_command_fails_the_trial_even_when_the_goal_is_met(self):
        o = json.loads((self.tmp / 'fixture' / 'P1' / self.cases.ids['P1'][0] / 'outcome.json').read_text())
        n = 20
        met = {**o, 'goal_met': True, 'end_reason': P.TASKS[TASK].success, 'action_steps': n, 'refusals': [],
               'help_requests': []}
        records = [{'decision': 'control', 'method': 'sha', 'goal_version': 1, 'part': {'vn': 0.0, 've': 0.0}, 't': t} for t in range(n)]
        self.assertTrue(P.component_trial('control', 'sha', met, records)['passed'])
        refused = {**met, 'refusals': [{'t': 3, 'why': 'speed over the limit'}]}
        self.assertFalse(P.component_trial('control', 'sha', refused, records)['passed'])
        self.assertFalse(P.component_trial('control', 'sha', {**met, 'help_requests': [{'t': 3}]}, records)['passed'])
        # A second answered by the guard and not by the candidate also fails the trial.
        other = [dict(r, method='guard') if r['t'] == 5 else r for r in records]
        self.assertFalse(P.component_trial('control', 'sha', met, other)['passed'])

    def test_a_refused_command_is_a_failed_trial_not_a_fault(self):
        from unittest import mock
        real = P.component_trial

        def refusing(decision, sha, outcome, records):
            n = len(records)
            fake = {**outcome, 'goal_met': True, 'end_reason': P.TASKS[TASK].success, 'action_steps': n,
                    'refusals': [{'t': 3}], 'help_requests': []}
            return real(decision, sha, fake, [dict(r, method=sha) for r in records if r.get('kind') == 'decision'])
        b, root, sent = self.block('refused', {})
        with mock.patch.object(P, 'component_trial', refusing):
            record = b.run()
        self.assertFalse(any(a['adopted'] for a in record['arms'].values()))
        self.assertEqual(len(record['arms']['C']['trials']), 3)
        self.assertTrue(all(not t['passed'] for a in record['arms'].values() for t in a['trials']))

    def test_an_interrupted_block_leaves_no_record_and_cannot_be_resumed_in_place(self):
        b, root, sent = self.block('interrupted', {('rC1', 1): RuntimeError('machine went to sleep')})
        with self.assertRaises(RuntimeError):
            b.run()
        self.assertFalse((root / 'arms.json').exists())
        self.assertTrue((root / 'candidates' / 'c0' / 'request.json').exists())
        # Every usage row has its call receipt, and nothing is recorded for the call that never returned.
        rows = [json.loads(x) for x in (root / 'usage.jsonl').read_text().splitlines()]
        for r in rows:
            self.assertTrue((root / 'candidates' / r['candidate_id'] / 'calls' / f'{r["call"]}.json').exists())
        self.assertNotIn('rC1', [r['candidate_id'] for r in rows])
        # The driver refuses to start in a folder that already holds a block, so a rerun has to be from scratch.
        with self.assertRaises(FileExistsError):
            L.make_proposer(root, TASK, scored=False, gem_model=None, stub=lambda label, request: None)
        again, root2, _ = self.block('interrupted-again', {})
        again.run()
        self.assertTrue((root2 / 'arms.json').exists())

    # -- receipts and usage rows -----------------------------------------------------------------------------------

    def test_scripted_calls_say_they_were_scripted(self):
        b, root, sent = self.block('receipts-scripted', {})
        b.run()
        rows = [json.loads(x) for x in (root / 'usage.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows), 8)
        for r in rows:
            self.assertIs(r['real_model_call'], False)
            self.assertEqual(r['served_by'], 'scripted')
            self.assertEqual(r['requested_settings']['provider'], 'scripted')
            self.assertEqual(r['requested_settings']['sampling_fields_sent'], [])
            self.assertIn('model', r['requested_settings'])
            receipt = json.loads((root / 'candidates' / r['candidate_id'] / 'calls' / f'{r["call"]}.json').read_text())
            self.assertEqual(receipt['requested_settings'], r['requested_settings'])
            self.assertIs(receipt['real_model_call'], False)

    def test_a_real_provider_is_recorded_with_the_settings_it_was_asked_for(self):
        from telohelm.runtime.models import ModelResponse

        class Real:
            name, model, effort, max_output_tokens = 'anthropic', 'claude-x', 'high', 1000
            cache, fallback, via, reportable, relays = True, False, 'gem', False, False
            calls = 0

            def complete(self, request):
                self.calls += 1
                if self.calls == 2:
                    # As claude_provider does: a refusal is a reply from the model, so it names the model that served it.
                    return ModelResponse('failed', None, provider_ids={'served_by': 'claude-x-served',
                                                                       'stop_reason': 'refusal'})
                return ModelResponse('answered', procedure(HOLD_STILL[TASK]), 5, 7, {'served_by': 'claude-x-served'})
        b, root, sent = self.block('receipts-real', {})
        b.provider.inner = Real()
        b.run()
        rows = [json.loads(x) for x in (root / 'usage.jsonl').read_text().splitlines()]
        answered = [r for r in rows if r['status'] == 'answered']
        failed = [r for r in rows if r['status'] == 'failed']
        self.assertTrue(answered and failed)
        for r in answered:
            self.assertIs(r['real_model_call'], True)
            self.assertEqual(r['served_by'], 'claude-x-served')
            settings = r['requested_settings']
            self.assertEqual({k: v for k, v in settings.items() if k != 'max_output_tokens'},
                             {'provider': 'anthropic', 'via': 'gem', 'model': 'claude-x', 'effort': 'high',
                              'cache_control': True, 'server_fallback': False, 'sampling_fields_sent': []})
            self.assertEqual(settings['max_output_tokens'], 1000)       # the provider's cap is below the request's
        for r in failed:
            self.assertIs(r['real_model_call'], True)                   # a real service replied, with a refusal
            self.assertEqual(r['requested_settings']['model'], 'claude-x')

    def test_a_real_call_with_no_served_label_stops_the_block(self):
        # The owner's ruling on unanswered calls: a real call that no model answered is a fault of the service. It
        # stops the block, which is then set aside and run again, and it never uses up a candidate slot.
        from telohelm.runtime.models import ModelResponse

        class Unlabelled:
            name, model, effort, max_output_tokens = 'anthropic', 'claude-x', 'high', 1000
            cache, fallback, via, reportable, relays = True, False, 'gem', False, False

            def complete(self, request):
                return ModelResponse('failed', None, provider_ids={'stop_reason': 'refusal'})
        b, root, sent = self.block('no-label', {})
        b.provider.inner = Unlabelled()
        with self.assertRaises(L.InfrastructureFault) as stop:
            b.run()
        self.assertIn('served-model label', str(stop.exception))
        self.assertFalse((root / 'arms.json').exists())
        # The call has a spending row (build F2) with no served label, and no receipt file.
        (row,) = [json.loads(x) for x in (root / 'usage.jsonl').read_text().splitlines()]
        self.assertIsNone(row['served_by'])
        self.assertFalse((root / 'candidates' / 'c0' / 'calls' / '1.json').exists())

    def test_the_runner_offers_every_scripted_reply_set(self):
        from . import scored as S
        self.assertEqual(set(S.STUB_CHOICES), set(L.PILOT_STUBS))

    # -- adoption bookkeeping and the scripted adoption set --------------------------------------------------------

    def passing(self, name, passing):
        """A block whose trials of the listed (candidate, list) pairs pass, whatever the recorded flights did."""
        b, root, sent = self.block(name, {})
        original = b.trial

        def trial(cid, family):
            entry = original(cid, family)
            if (cid, family) in passing:
                entry.update(passed=True, why=[])
                for row in entry['outcomes']:
                    row['trial_passed'] = True
            return entry
        b.trial = trial
        return b, root, sent

    def test_c0_passing_its_threat_trial_is_adopted_by_b_and_c_only(self):
        b, root, sent = self.passing('adopt-c0', {('c0', 'threat')})
        record = b.run()
        arms = record['arms']
        self.assertTrue(record['c0_zone_qualified'])
        self.assertEqual([arms[a]['candidate_id'] for a in 'ABCD'], [None, 'c0', 'c0', None])
        self.assertEqual(arms['B']['source_sha256'], arms['C']['source_sha256'])
        self.assertFalse((root / 'candidates' / 'rC1').exists())
        self.assertEqual(len(arms['C']['trials']), 1)
        self.assertEqual(arms['C']['call_ids'], arms['B']['call_ids'])

    def test_scripted_adoption_set_drives_every_arm_to_adopt(self):
        # Trials stand in for flights. Only the candidates the set means to be adopted pass them.
        b, root, sent = self.passing('adopt-set', {('f1', 'matched'), ('f1', 'threat'), ('c1', 'threat'),
                                                   ('rC1', 'threat')})
        stub = L.adopt_stub(TASK)
        b.provider.inner._answer = lambda request: (sent.append(b.provider.label), stub(b.provider.label, request))[1]
        sent.clear()
        record = b.run()
        arms = record['arms']
        self.assertEqual({a: arms[a]['candidate_id'] for a in 'ABCD'}, {'A': 'f1', 'B': 'f1', 'C': 'rC1', 'D': 'c1'})
        self.assertEqual(sorted(set(sent)), [('c0', 1), ('c1', 1), ('f1', 1), ('rC1', 1)])
        shas = {a: arms[a]['source_sha256'] for a in 'ABCD'}
        self.assertEqual(shas['A'], shas['B'])
        self.assertEqual(shas['C'], shas['D'])          # one source reaches C and D, the other A and B
        self.assertNotEqual(shas['A'], shas['C'])

    def test_adoption_replies_are_valid_procedures_for_every_task(self):
        import ast
        from telohelm.local_model import first_object
        from telohelm.runtime.procedures import reply_errors
        data = json.loads(L.ADOPT_REPLIES.read_text())
        self.assertEqual(sorted(data['sources']), ['land', 'reach', 'reach3d'])
        for task, entries in data['sources'].items():
            self.assertEqual(len(entries), 2)
            self.assertNotEqual(entries[0]['source_sha256'], entries[1]['source_sha256'])
            root = self.tmp / f'adopt-valid-{task}'
            root.mkdir()
            proposer, _ = L.make_proposer(root, task, scored=False, gem_model=None, stub=lambda label, request: None)
            context = L.Context('P0', root, task, proposer)
            for e in entries:
                self.assertEqual(hashlib.sha256(e['source'].encode()).hexdigest(), e['source_sha256'])
                ast.parse(e['source'])
                reply = first_object(json.dumps({'kind': 'procedure', 'decision': 'control', 'conditions': [],
                                                 'source': e['source'],
                                                 'reason': {'code': 'missing_tool', 'text': 'x'}}))
                self.assertEqual(reply_errors(reply, pack=context.co.pack) or context.co._scope_errors(reply), [], task)


class WarmupFlight(unittest.TestCase):
    """The warm-up flight (notes/TAKEOVER-20261111.md, 12 November 2026, 9:25 am, ruling 6), with no simulator."""

    def case(self):
        from .battle import generate
        return generate('reach', 'calm', 4200001)

    def fake_run(self, calls, lag_s=0.0, delays=None):
        delays = [] if delays is None else delays
        def run(out, task, source, origin, cases, speedup, instance, command_delay_periods=None):
            calls.append((Path(out), task, source, origin, [c.episode_id for c in cases], speedup, instance))
            delays.append(command_delay_periods)
            for c in cases:
                (Path(out) / c.episode_id).mkdir(parents=True)
                (Path(out) / c.episode_id / 'outcome.json').write_text(json.dumps(with_delay(
                    {'end_reason': 'success', 'goal_met': True,
                     'native_steps': [{'decision_lag_s': lag_s} for _ in range(9)]})))
        return run

    def test_it_flies_the_reference_controller_on_the_given_case_in_its_own_folder(self):
        from unittest import mock
        from . import battle
        from .demo import REFERENCE
        calls = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(battle, 'run', self.fake_run(calls)):
            root = Path(d) / 'phase'
            root.mkdir()
            record = L.fly_warmup(root, 'reach', self.case(), speedup=1.0, instance=11)
            self.assertEqual(calls, [(root / 'warmup', 'reach', REFERENCE['reach'], calls[0][3], ['calm-4200001'], 1.0, 11)])
            self.assertIn('warm-up', calls[0][3])
            self.assertEqual(json.loads((root / 'warmup' / 'warmup.json').read_text()), record)
            self.assertTrue((root / 'warmup' / 'calm-4200001' / 'outcome.json').exists())
            self.assertEqual((record['warmup'], record['case'], record['steps'], record['late']),
                             (True, 'calm-4200001', 9, False))
            self.assertEqual(record['command_delay_s'], L.COMMAND_DELAY_S)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['warmup'])

    def test_a_late_warmup_is_kept_and_stops_nothing(self):
        from unittest import mock
        from . import battle
        with tempfile.TemporaryDirectory() as d, mock.patch.object(battle, 'run', self.fake_run([], lag_s=1.0)):
            record = L.fly_warmup(Path(d) / 'phase', 'reach', self.case(), speedup=1.0, instance=10)
            self.assertTrue(record['late'])
            self.assertEqual(record['max_lag_s'], 1.0)

    def test_a_block_flies_its_warmup_once_before_any_flight_of_its_own(self):
        from unittest import mock
        events = []
        case = self.case()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'block'
            root.mkdir()
            with mock.patch.object(L, 'fly_warmup', lambda *a, **k: events.append(('warmup', a[1], a[2], k))), \
                    mock.patch.object(L.Block, 'run', lambda self: events.append(('block',)) or {'arms': {}}):
                L.run_block(root, 'reach', 0, [], [], speedup=1.0, instance=12, scored=False, gem_model=None,
                            stub=lambda label, request: None, warmup_case=case)
                other = Path(d) / 'block2'
                other.mkdir()
                L.run_block(other, 'reach', 0, [], [], speedup=1.0, instance=12, scored=False, gem_model=None,
                            stub=lambda label, request: None)
        self.assertEqual(events, [('warmup', 'reach', case, {'speedup': 1.0, 'instance': 12}), ('block',), ('block',)])

    def test_the_case_is_the_first_calm_development_case_of_each_task_and_never_a_reserved_seed(self):
        from . import scored
        from protocol import contract3 as C3
        from protocol import timing_preflight3 as T
        seeds = json.loads((Path(__file__).parents[1] / 'protocol' / 'seeds-3.json').read_text())
        for task in ('reach', 'reach3d', 'land'):
            for pilot in (True, False):     # a scored phase still takes its warm-up from the development book
                case = scored.warmup_case(C3, seeds, task)
                self.assertEqual(case.episode_id, f"calm-{seeds['pilot']['heldout'][task]['calm'][0]}")
                self.assertNotIn(int(case.episode_id.rsplit('-', 1)[1]), T.reserved_seeds(seeds))
                self.assertEqual(T.warmup_case(seeds, task).episode_id, case.episode_id)


def on_time_fixture(root: Path) -> None:
    """Give every recorded outcome under root the fields of a flight flown with the fixed delay and on time, whatever
    delay it was recorded with: the pilot blocks these fixtures come from flew at 0.3 s."""
    for f in Path(root).rglob('outcome.json'):
        o = json.loads(f.read_text())
        o['command_delay_s'] = L.COMMAND_DELAY_S
        for st in o.get('native_steps') or []:
            st['observation_lag_s'] = 0.0
            st['command_lag_s'] = L.COMMAND_DELAY_S
            st['decision_lag_s'] = min(st.get('decision_lag_s') or 0.0, 0.1)
        f.write_text(json.dumps(o))


class DelaySentenceInEveryRequest(unittest.TestCase):
    """B5, round five: in all three protocol 3 tasks and every arm, every model-visible text the driver sends, the first
    request of each candidate and each call after it (format repairs included), carries the delay sentence once, and
    with the sentence cut out is the text it was before. Each task's learning block is driven by Block.run over
    recorded first-round flights (testdata/ladder-first-round*.zip: reach from the Mac's first pilot, reach3d and land
    from the blocks of pilot3-scripted-20261113), twice: as built, and with delay_sentence patched to empty text."""

    FIXTURES = {'reach': 'ladder-first-round.zip', 'reach3d': 'ladder-first-round-reach3d.zip',
                'land': 'ladder-first-round-land.zip'}

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='sentence-test-'))
        cls.cases = {}
        for task, name in cls.FIXTURES.items():
            with zipfile.ZipFile(FIXTURE.with_name(name)) as z:
                z.extractall(cls.tmp / task / 'fixture')
            # Reach's fixture is the one LadderControls uses, with its one recorded late lag handled by fake_fly.
            (delay_fixture if task == TASK else on_time_fixture)(cls.tmp / task / 'fixture')
            cls.cases[task] = Cases(cls.tmp / task / 'fixture', task)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def exhaust_stub(task):
        """Every trial fails, so all eight candidates are asked, and format repairs happen in arms A and B (f1), C (rC1)
        and D (c1 and rD2); f2 gets an empty reply, which has no repair."""
        from telohelm.runtime.models import ModelResponse
        plan = {('f1', 1): 'not a procedure', ('c1', 1): '{"kind": "check"}', ('rD2', 1): 'still not json',
                ('rC1', 1): '{"kind": "procedure", "decision": "control"}', ('f2', 1): ''}

        def reply(label, request):
            text = plan.get(label, procedure(HOLD_STILL[task]))
            return ModelResponse('answered', text) if text else ModelResponse('failed', '')
        return reply

    def run_block(self, task, plan, with_sentence):
        """The texts of one block: (candidate, 'request' or 'call<k>') to (text, shown flights)."""
        root = self.tmp / task / f'{plan}-{"on" if with_sentence else "off"}'
        stub = {'exhaust': self.exhaust_stub, 'pilot': L.pilot_stub}[plan](task)
        patch = contextlib.nullcontext() if with_sentence else mock.patch.object(L, 'delay_sentence', return_value='')
        with patch, mock.patch('os.fsync'):
            proposer, provider = L.make_proposer(root, task, scored=False, gem_model=None, stub=stub)
            cases = self.cases[task]
            b = L.Block(root, task, 0, cases.matched, cases.threat, proposer, provider, speedup=10.0, instance=10,
                        late_flights='stop')
            b.fly = fake_fly(self.tmp / task / 'fixture').__get__(b)
            b.run()
        texts = {}
        for folder in sorted((root / 'candidates').iterdir()):
            request = json.loads((folder / 'request.json').read_text())
            texts[(folder.name, 'request')] = (request['model_payload_json'], request['shown_flights'])
            for call in sorted((folder / 'calls').glob('*.json')):
                receipt = json.loads(call.read_text())
                texts[(folder.name, f'call{call.stem}')] = (receipt['model_payload_json'], receipt['shown_flights'])
        return texts

    def test_every_request_and_call_of_every_task_carries_the_sentence_once_and_nothing_else_differs(self):
        sentence = L.delay_sentence()
        for task in self.FIXTURES:
            for plan in ('exhaust', 'pilot'):
                with self.subTest(task=task, plan=plan):
                    on, off = self.run_block(task, plan, True), self.run_block(task, plan, False)
                    self.assertEqual(set(on), set(off))
                    self.assertEqual({k[0] for k in on}, set(ALL_CIDS))
                    for key, (text, shown) in on.items():
                        with self.subTest(text=key):
                            messages = json.loads(text)
                            self.assertEqual(text.count(sentence), 1)
                            self.assertEqual((messages[0][0], messages[0][1].count(sentence)), ('system', 1))
                            self.assertEqual(text.replace(sentence, ''), off[key][0])
                            self.assertEqual(shown, off[key][1])
                    if plan == 'exhaust':
                        # The control would prove little if no format repair were sent: each of these has a call 2.
                        repairs = {k[0] for k in on if k[1] == 'call2'}
                        self.assertEqual(repairs, {'f1', 'c1', 'rD2', 'rC1'})


class FakeSim:
    """A simulator link for Episode.step with no simulator. Telemetry stamps arrive every 0.1 s from t0, except that a
    stamp listed in slip is never seen, as when the host's comparison misses it (round four, point 2). drain() puts the
    clock where the test says the decision became ready; advance_to(t) reads stamps until the clock is at least t."""

    def __init__(self, t0, slip=()):
        self.t0, self.slip = t0, {round(x, 3) for x in slip}
        self.state = dict(t=t0, position_t=t0, north=0.0, east=0.0, down=-10.0, vn=0.0, ve=0.0, vd=0.0,
                          heading_deg=0.0, battery_pct=90, battery_v=12.5, gps_fix=6, gps_sats=10, ekf_flags=831,
                          true_north=0.0, true_east=0.0, true_alt=10.0, true_vn=0.0, true_ve=0.0, true_vd=0.0,
                          truth_t=t0, armed=True, mode='GUIDED')
        self.ready_after = 0.0          # seconds after the observation at which the next decision is ready
        self.sent, self.closed, self.command, self.texts = [], False, ['fake'], []

    def _stamp(self, t):
        self.state.update(t=t, position_t=t, truth_t=t)

    def drain(self):
        target = self.state['t'] + self.ready_after
        k = math.floor(round((target - self.t0) * 10, 6))
        while k > 0 and round(k / 10, 3) in self.slip:
            k -= 1
        self._stamp(max(self.state['t'], round(self.t0 + k / 10, 3)))

    def advance_to(self, t):
        k = math.ceil(round((t - self.t0) * 10, 6))
        while round(k / 10, 3) in self.slip:
            k += 1
        self._stamp(max(self.state['t'], round(self.t0 + k / 10, 3)))

    def command_velocity(self, vn, ve, vd=0.0):
        self.sent.append(round(self.state['t'] - self.t0, 3))

    def close(self):
        self.closed = True


class ExactClockSim(FakeSim):
    """A FakeSim whose drain() puts the clock exactly ready_after past the current clock, between telemetry stamps.
    advance_to still reads whole stamps, as the real link does. With stamp_early_s set, every stamp after the first
    arrives that much before its place on the 0.1 s grid, as a real link's stamps come a millisecond or two off it."""

    stamp_early_s = 0.0

    def drain(self):
        self._stamp(round(self.state['t'] + self.ready_after, 3))

    def advance_to(self, t):
        k = math.ceil(round((t - self.t0 + self.stamp_early_s) * 10, 6))
        self._stamp(max(self.state['t'], round(self.t0 + k / 10 - self.stamp_early_s, 3)))


class EarlyStampSim(ExactClockSim):
    stamp_early_s = 0.002


class FixedDelay(unittest.TestCase):
    """pack.Episode.step with the fixed delay (round four, ruling 1), over a fake simulator link."""

    def episode(self, periods, slip=(), sim_class=FakeSim):
        from unittest import mock
        from .battle import generate
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        host = {**P.HOST, 'root': tmp, 'command_delay_periods': periods}
        patcher = mock.patch.dict(P.HOST, host)
        patcher.start()
        self.addCleanup(patcher.stop)
        ep = P.Episode(generate('reach', 'calm', 4200001))
        ep.sim = sim_class(52.831, slip)
        ep.t0 = ep.observed = ep.sim.state['t']
        ep.last_truth = P.truth(ep.sim.state)
        return ep

    def test_the_command_goes_out_on_the_deadline_stamp_after_its_observation(self):
        ep = self.episode(L.COMMAND_DELAY_PERIODS)
        self.assertEqual(ep.command_delay_s, L.COMMAND_DELAY_S)
        for ready in (0.0, 0.05, 0.1, 0.18, 0.25):
            ep.sim.ready_after = ready
            ep.step({'vn': 1.0, 've': 0.0})
        self.assertEqual(ep.sim.sent, [0.3, 1.3, 2.3, 3.3, 4.3])
        steps = ep.native_steps
        self.assertEqual([s['command_lag_s'] for s in steps], [0.3] * 5)
        self.assertEqual([s['observation_lag_s'] for s in steps], [0.0] * 5)
        self.assertEqual([s['decision_lag_s'] for s in steps], [0.0, 0.0, 0.1, 0.1, 0.2])
        self.assertEqual(ep.outcome()['command_delay_s'], L.COMMAND_DELAY_S)
        self.assertFalse(L.timing(ep.outcome())['late'])

    def test_the_deadline_boundary_with_the_clock_between_stamps(self):
        """The boundary of ruling 8 at three periods (the delay ruling 20's reading returned to). The fake's clock sits exactly at the ready time, between stamps, as a
        real link's can. Ready 0.294 s after the observation is in time: the hold reads the stamp 0.3 s after it and the
        command goes out there. From 0.295 s on the decision has missed: the command goes out at once, with one missed
        deadline and no command off its deadline stamp."""
        self.assertEqual(L.COMMAND_DELAY_PERIODS, 3)
        ep = self.episode(L.COMMAND_DELAY_PERIODS, sim_class=ExactClockSim)
        ep.sim.ready_after = 0.294
        ep.step({'vn': 1.0, 've': 0.0})
        self.assertEqual(ep.sim.sent, [0.3])
        self.assertEqual((ep.native_steps[0]['decision_lag_s'], ep.native_steps[0]['command_lag_s']), (0.294, 0.3))
        t = L.timing(ep.outcome())
        self.assertEqual((t['late'], t['missed_deadlines'], t['off_deadline_commands']), (False, 0, 0))
        # Stamps that arrive 2 ms early: the hold stops at observed + 0.295 s, which the stamp at 0.298 s satisfies. A hold
        # that waited for observed + 0.3 s would pass that stamp and send at 0.398 s, a stamp off its deadline.
        ep = self.episode(L.COMMAND_DELAY_PERIODS, sim_class=EarlyStampSim)
        ep.sim.ready_after = 0.294
        ep.step({'vn': 1.0, 've': 0.0})
        self.assertEqual(ep.sim.sent, [0.298])
        t = L.timing(ep.outcome())
        self.assertEqual((t['late'], t['missed_deadlines'], t['off_deadline_commands']), (False, 0, 0))
        for ready in (0.295, 0.299, 0.3, 0.301):
            with self.subTest(ready=ready):
                ep = self.episode(L.COMMAND_DELAY_PERIODS, sim_class=ExactClockSim)
                ep.sim.ready_after = ready
                ep.step({'vn': 1.0, 've': 0.0})
                self.assertEqual(ep.sim.sent, [ready])
                self.assertEqual((ep.native_steps[0]['decision_lag_s'], ep.native_steps[0]['command_lag_s']),
                                 (ready, ready))
                t = L.timing(ep.outcome())
                self.assertEqual((t['late'], t['missed_deadlines'], t['off_deadline_commands']), (True, 1, 0))

    def test_a_decision_ready_after_its_deadline_stamp_is_sent_at_once_and_is_late(self):
        ep = self.episode(L.COMMAND_DELAY_PERIODS)
        for ready in (0.1, 0.35, 0.1):
            ep.sim.ready_after = ready
            ep.step({'vn': 1.0, 've': 0.0})
        self.assertEqual(ep.sim.sent, [0.3, 1.3, 2.3])          # the late one went out when it was ready
        self.assertEqual(ep.native_steps[1]['command_lag_s'], 0.3)
        self.assertEqual(ep.native_steps[1]['decision_lag_s'], 0.3)
        t = L.timing(ep.outcome())
        self.assertEqual((t['late'], t['missed_deadlines']), (True, 1))

    def test_a_late_observation_moves_the_deadline_with_it(self):
        # The stamp at t0 + 2 s is never seen, so the third observation is read at 2.1 s: its command goes out at 2.4 s.
        ep = self.episode(L.COMMAND_DELAY_PERIODS, slip=[2.0])
        for _ in range(3):
            ep.sim.ready_after = 0.1
            ep.step({'vn': 1.0, 've': 0.0})
        self.assertEqual(ep.sim.sent, [0.3, 1.3, 2.4])
        self.assertEqual([s['observation_lag_s'] for s in ep.native_steps], [0.0, 0.0, 0.1])
        self.assertEqual([s['decision_lag_s'] for s in ep.native_steps], [0.1, 0.1, 0.2])
        self.assertEqual([s['command_lag_s'] for s in ep.native_steps], [0.3, 0.3, 0.3])
        self.assertFalse(L.timing(ep.outcome())['late'])

    def test_a_stamp_skipped_in_the_hold_sends_the_command_a_period_late_and_is_recorded(self):
        ep = self.episode(L.COMMAND_DELAY_PERIODS, slip=[0.3])
        ep.sim.ready_after = 0.1
        ep.step({'vn': 1.0, 've': 0.0})
        self.assertEqual(ep.sim.sent, [0.4])
        t = L.timing(ep.outcome())
        self.assertEqual((t['late'], t['off_deadline_commands']), (True, 1))

    def test_without_the_delay_the_command_goes_out_when_ready_and_nothing_new_is_recorded(self):
        ep = self.episode(None)
        self.assertIsNone(ep.command_delay_s)
        ep.sim.ready_after = 0.1
        ep.step({'vn': 1.0, 've': 0.0})
        self.assertEqual(ep.sim.sent, [0.1])
        self.assertNotIn('command_lag_s', ep.native_steps[0])
        self.assertNotIn('observation_lag_s', ep.native_steps[0])
        self.assertNotIn('command_delay_s', ep.outcome())
        self.assertEqual(ep.native_steps[0]['decision_lag_s'], 0.1)

    def test_battle_run_sets_the_delay_for_its_flights_and_records_it(self):
        from unittest import mock
        from telohelm.runtime import episode_loop
        from . import battle
        seen = []

        def episode(scenario, library, models, log, ledger, max_steps=None, broker=None, pack=None):
            seen.append(P.HOST['command_delay_periods'])
            return {'outcome': with_delay({'goal_met': True, 'end_reason': 'held', 'action_steps': 1,
                                           'native_steps': [{'t': 1, 'decision_lag_s': 0.1, 'estimate_error_m': 0.1}],
                                           'closest_threat_m': None, 'events': []})}
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        case = battle.generate('reach', 'calm', 4200001)
        with mock.patch.object(episode_loop, 'run_episode', episode), mock.patch('os.fsync'):
            battle.run(tmp / 'with', 'reach', [], 'test', cases=[case], speedup=1.0, instance=10,
                       command_delay_periods=L.COMMAND_DELAY_PERIODS)
            battle.run(tmp / 'without', 'reach', [], 'test', cases=[case], speedup=1.0, instance=10)
        self.assertEqual(seen, [L.COMMAND_DELAY_PERIODS, None])
        self.assertEqual(json.loads((tmp / 'with' / 'run-config.json').read_text())['command_delay_periods'],
                         L.COMMAND_DELAY_PERIODS)
        self.assertNotIn('command_delay_periods', json.loads((tmp / 'without' / 'run-config.json').read_text()))

    def test_every_protocol_3_flight_path_passes_the_delay(self):
        """The warm-up, every learning call and every evaluation phase pass COMMAND_DELAY_PERIODS to battle.run; a
        flight flown without it is late by ladder.timing, so the gate would refuse it."""
        import inspect
        from . import scored
        self.assertIn('command_delay_periods=COMMAND_DELAY_PERIODS', inspect.getsource(L.fly_warmup))
        self.assertIn('command_delay_periods=COMMAND_DELAY_PERIODS', inspect.getsource(L.Block.fly))
        self.assertIn('command_delay_periods=COMMAND_DELAY_PERIODS', inspect.getsource(scored.phase_eval3))


if __name__ == '__main__':
    unittest.main()

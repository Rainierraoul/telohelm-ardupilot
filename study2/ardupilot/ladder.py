"""Protocol 3's learning block: four ways of learning from the same three layouts.

Contract: notes/PROTOCOL3-CONTRACT-C3-20261109.md (arms and phases) and notes/PROTOCOL3-SCHEMA-D3-20261109.md (records).

A block is one task's three learning layouts, one in each clearance band. Each layout is flown in two versions, with
its hazard zone (threat) and with the zone removed (matched). A candidate is one procedure the model writes. A trial
flies a candidate, with the guard, on one list of three layouts, and passes only if Telohelm's own trial rule
(pack.component_trial) passes on all three. Four arms learn from the same block:

  arm  first  trial list  after a failed trial
  A    c0     matched     f1, then f2
  B    c0     threat      f1, then f2
  C    c0     threat      rC1, then rC2
  D    c1     threat      rD1, then rD2

c0 is written from the matched layouts flown with the guard alone (P0), and c1 from the threat layouts flown the same
way (P1). f1 and f2 are fresh samples: they send c0's request again, byte for byte, under their own request identity,
and A and B share them. A repair is Telohelm's own next attempt: its request carries the refused source and the trial's
one-line reason, as Coordinator._remember records them. Its examples are flights of its own arm only: trial flights,
with at least one from the trial just flown. Only when no trial has been flown yet in the arm (every earlier slot
failed its format) does it show the arm's first-round flights, the only flights the learner has. Every request is built
by Telohelm's Coordinator, unchanged except for the sentence pack.PROCEDURE_ONLY added to its rules; the driver only chooses
which flights a learner has seen and when it is asked.

Each candidate slot is one call plus at most one format repair. A reply that is still invalid uses up the slot. An arm
stops at its first pass, and after three slots without one it adopts nothing. A trial is flown once per candidate and
list: B and C share c0's threat trial. A model transport failure, a time-out, a reply with no served-model label and a
reply whose message id was seen before (a stored copy) are infrastructure faults: the block stops, and its folder is
never scored. A late flight is not one in a scored block. A late call is moved aside unread and flown again in place,
at most REFLIGHTS times, with no model call; the next attempt is kept, its late flights are marked kept_late in
timing.json, and the block goes on and is scored. A block run in 'stop' mode (not used for scored runs) stops at its first
late flight, and one run in 'record' mode (pilots only) keeps late flights as they were flown.
"""
from __future__ import annotations

import datetime
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics

from . import pack as P

ARMS = {'A': ('matched', ('c0', 'f1', 'f2')), 'B': ('threat', ('c0', 'f1', 'f2')),
        'C': ('threat', ('c0', 'rC1', 'rC2')), 'D': ('threat', ('c1', 'rD1', 'rD2'))}
# The proposer keeps one answer cache and one gateway per attempt number, so each candidate has its own.
CALL_NUMBER = {'c0': 1, 'c1': 2, 'f1': 3, 'f2': 4, 'rC1': 5, 'rC2': 6, 'rD1': 7, 'rD2': 8}
PARENT = {'c0': None, 'c1': None, 'f1': None, 'f2': None, 'rC1': 'c0', 'rC2': 'rC1', 'rD1': 'c1', 'rD2': 'rD1'}
CALLS_PER_SLOT = 2                 # one call and at most one format repair
MAX_MEDIAN_LAG_S = 0.05            # protocol 2's real-time rule, kept
# A lag on a 0.1 s telemetry step is recorded as 0.098, 0.1 or 0.101 s for the same delay, so a threshold is applied
# 0.005 s below its figure (TAKEOVER-20261111.md, item 8, line 234), as protocol/analysis.py line 349 does for 0.1 s.
LATE_DECISION_S = 0.995            # 'a command 1 s or more after its scheduled time' is late (TAKEOVER-20261111.md, lines 62, 216, 234)
LATE_SHARE_FROM_S = 0.095          # a decision counts in late_share_0_1s from here (TAKEOVER-20261111.md, line 234)
TELEMETRY_STEP_MS = 100            # telemetry arrives at stream_hz 10 (vehicle.py), so lag is counted in 0.1 s steps
# The fixed delay (notes/TAKEOVER-20261111.md, round four, rulings 1, 2 and 8, 13 November 2026). Every command of a
# protocol 3 flight is sent COMMAND_DELAY_PERIODS telemetry periods after the stamp its observation was read at, in every
# arm, task and phase. The number is the smallest whole number of periods that holds the slowest decision on the study
# platform's own records, counted from its observation (ruling 8). The records of the cluster's real-time flight of
# 13 November held at three periods. Ruling 20 (round five) named two periods, 0.2 s, as the candidate and fixed how its
# reading would be made. The reading was made on 16 November from the free checks and the pilots flown at two periods on
# the wheel +paper3.2 (jobs 4799236 to 4799239): the pilots had 7 decisions with an own lag of two steps in about
# 19,800, so two periods did not hold and the delay is three. Three is judged in turn by ruling 8, on flights at three.
COMMAND_DELAY_PERIODS = 3
COMMAND_DELAY_S = round(COMMAND_DELAY_PERIODS * TELEMETRY_STEP_MS / 1000, 3)
# The literal field names job 3's gate reads (contract3.SETTINGS_FIELD and the usage-row fields). Do not rename.
SETTINGS_FIELD, REAL_FIELD, SERVED_FIELD = 'requested_settings', 'real_model_call', 'served_by'


# The warm-up flight (TAKEOVER-20261111.md, 12 November 2026, 9:25 am, ruling 6) goes in a folder of this name inside the
# phase or worker folder. Nothing that judges or analyses a study reads it: the gate and the set-aside tool skip it.
WARMUP_DIR = 'warmup'
WARMUP_RECORD = 'warmup.json'

# A late learning flight is flown again in place (TAKEOVER-20261111.md, round two, ruling 3, 12 November 2026, after
# the review's finding 1). When any flight of one flying call is late, the call's folder is moved, before anything reads
# it, to LATE_DIR/<the call's path>/attempt-<k> inside the block folder, and the same source flies the same cases again
# in the same process, with no model call. At most REFLIGHTS flights again; a third late attempt is kept, read by the
# block like any flight and marked kept_late in timing.json. REFLIGHTS is picked (ruling 3, 'Why two'), for Simon.
LATE_DIR = 'late'
REFLIGHTS = 2
LATE_MODES = ('stop', 'record', 'refly')


def peak_rss_bytes() -> int:
    """This process's peak resident size so far. getrusage starts no process; macOS gives bytes and Linux kilobytes."""
    import resource
    import sys
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == 'darwin' else peak * 1024)


class InfrastructureFault(RuntimeError):
    """A failure of the machine or the model service, never of a procedure. The block is rerun from scratch."""


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str) + '\n')


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def payload_json(messages) -> str:
    """The model-visible request as the proposer fingerprints it: the role and text of every message, in order."""
    return json.dumps([list(m) for m in messages])


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def telemetry_steps(lag_s: float) -> int:
    """A lag in whole telemetry steps, each counted from 0.005 s below the step (item 8): 0.094 s is 0, 0.095 s is 1."""
    return (round(lag_s * 1000) + 5) // TELEMETRY_STEP_MS


def timing(outcome: dict) -> dict:
    """Timing of one protocol 3 flight flown with the fixed delay, and whether the flight is late (round four, ruling 2).

    Each step records decision_lag_s (the scheduled observation to the decision being ready), observation_lag_s (the
    scheduled observation to the stamp it was read at) and command_lag_s (that stamp to the command going out). A
    decision's own lag is decision_lag_s less observation_lag_s. All are read on the telemetry step from 0.005 s below it.
    The flight is late if it does not record command_delay_s of COMMAND_DELAY_S; if any of the three lags is missing or
    not finite; if any decision's own lag is COMMAND_DELAY_PERIODS steps or more (a missed deadline); or if a decision
    that was ready in time had its command go out at other than COMMAND_DELAY_PERIODS steps (a telemetry stamp skipped
    during the hold, which should never happen). A flight with no steps is late.

    median_lag_s, max_lag_s, late_share_0_1s and step_median_lag_s are read from decision_lag_s as before, so they
    compare with the earlier records; they no longer decide lateness. Records flown before 13 November 2026 have no
    fixed delay and are read with timing_before_delay."""
    steps = outcome.get('native_steps') or []
    lags = [s.get('decision_lag_s') for s in steps]
    seen = [s.get('observation_lag_s') for s in steps]
    sent = [s.get('command_lag_s') for s in steps]
    delay = outcome.get('command_delay_s')
    delay_ok = _number(delay) and abs(delay - COMMAND_DELAY_S) < 1e-9
    if not (steps and all(_number(x) for x in lags + seen + sent)):
        return {'median_lag_s': None, 'max_lag_s': None, 'late_share_0_1s': None, 'step_median_lag_s': None,
                'command_delay_s': delay, 'max_own_lag_s': None, 'observations_late': None, 'missed_deadlines': None,
                'off_deadline_commands': None, 'late': True}
    own = [round(x - o, 3) for x, o in zip(lags, seen)]
    in_time = [telemetry_steps(x) < COMMAND_DELAY_PERIODS for x in own]
    missed = in_time.count(False)
    off = sum(1 for c, ok in zip(sent, in_time) if ok and telemetry_steps(c) != COMMAND_DELAY_PERIODS)
    step_median = round(statistics.median([telemetry_steps(x) for x in lags]) * TELEMETRY_STEP_MS / 1000, 3)
    return {'median_lag_s': statistics.median(lags), 'max_lag_s': max(lags),
            'late_share_0_1s': round(sum(x >= LATE_SHARE_FROM_S for x in lags) / len(lags), 4),
            'step_median_lag_s': step_median, 'command_delay_s': delay, 'max_own_lag_s': max(own),
            'observations_late': sum(telemetry_steps(o) >= 1 for o in seen), 'missed_deadlines': missed,
            'off_deadline_commands': off, 'late': not delay_ok or missed > 0 or off > 0}


def timing_before_delay(outcome: dict) -> dict:
    """Decision lag of one flight flown before the fixed delay (before 13 November 2026), and whether it was late by the
    rule of that time. Kept for reading those records: the timing preflight tool and its diagnostics use it. It is not
    the rule for protocol 3's flights any more (round four, ruling 2).

    The rule (notes/TAKEOVER-20261111.md, line 62 as revised on 12 November 2026): a flight is late if any lag is
    missing; if the median of its lags, each read on the telemetry step, is above 0.05 s; or if any command is 1 s or
    more behind its schedule, read as a recorded lag of 0.995 s or more (item 8, line 234). A lag is read on the step
    from 0.005 s below it, so 0.098, 0.1 and 0.101 s are all one step and 0.0 and 0.001 s are none (item 8). Read on the
    step, a median above 0.05 s means that more than half the decisions were at least one step late, or exactly half
    when every lag in the late half is two steps or more; exactly half with one-step lags is on time (corrected 12
    November 2026: this said exactly half is on time). A flight with no steps is late.

    median_lag_s, max_lag_s and late_share_0_1s are the recorded lag as before, so they compare with the second
    protocol's figures; step_median_lag_s is the median the rule reads."""
    lags = [s.get('decision_lag_s') for s in outcome.get('native_steps') or []]
    ok = bool(lags) and all(_number(x) for x in lags)
    if not ok:
        return {'median_lag_s': None, 'max_lag_s': None, 'late_share_0_1s': None, 'step_median_lag_s': None,
                'late': True}
    step_median = round(statistics.median([telemetry_steps(x) for x in lags]) * TELEMETRY_STEP_MS / 1000, 3)
    return {'median_lag_s': statistics.median(lags), 'max_lag_s': max(lags),
            'late_share_0_1s': round(sum(x >= LATE_SHARE_FROM_S for x in lags) / len(lags), 4),
            'step_median_lag_s': step_median, 'late': step_median > MAX_MEDIAN_LAG_S or max(lags) >= LATE_DECISION_S}


def fly_warmup(root: Path, task: str, case, *, speedup: float, instance: int) -> dict:
    """Fly one development case with the task's reference controller, as the first flight of a process, and keep its
    timing. The start-up effect on the clock offset strikes a process's first flight, so this flight takes it and the
    study's own flights do not. It goes in root/warmup/ and is not a flight of the study: no gate, no analysis and no
    count of late flights reads it. The record is also written to root/warmup/warmup.json and returned. It never
    stops a phase for being late; the timing is kept so that the effect can be seen, and nothing more is done with it.

    The case is chosen by the caller, from the development book only."""
    from . import demo
    from .battle import run
    out = Path(root) / WARMUP_DIR
    load = [round(x, 2) for x in os.getloadavg()]
    started = datetime.datetime.now().astimezone().isoformat()
    run(out, task, demo.REFERENCE[task], 'authored reference procedure (warm-up flight)', cases=[case],
        speedup=speedup, instance=instance, command_delay_periods=COMMAND_DELAY_PERIODS)
    ended = datetime.datetime.now().astimezone().isoformat()
    outcome = json.loads((out / case.episode_id / 'outcome.json').read_text())
    record = {'warmup': True, 'task': task, 'case': case.episode_id, 'instance': instance, 'started': started,
              'ended': ended, 'load_average_1_5_15_at_start': load, 'end_reason': outcome.get('end_reason'),
              'goal_met': outcome.get('goal_met'), 'steps': len(outcome.get('native_steps') or []), **timing(outcome)}
    _write(out / WARMUP_RECORD, record)
    print(f'warm-up flight {case.episode_id}: median lag {record["median_lag_s"]} s, largest {record["max_lag_s"]} s, '
          f'{record["steps"]} decisions (not counted)', flush=True)
    return record


def late_reason(t: dict) -> str:
    """Which part of the rule a late flight broke, for the fault message."""
    if 'missed_deadlines' in t:
        if t['missed_deadlines'] is None:
            return 'a decision, observation or command lag is missing or not finite'
        delay = t.get('command_delay_s')
        if not (_number(delay) and abs(delay - COMMAND_DELAY_S) < 1e-9):
            return f'flown without the fixed delay of {COMMAND_DELAY_S} s (recorded: {delay})'
        if t['missed_deadlines']:
            return (f'{t["missed_deadlines"]} decisions missed the {COMMAND_DELAY_S} s deadline (own lag up to '
                    f'{t["max_own_lag_s"]} s)')
        return f'{t["off_deadline_commands"]} commands went out off their deadline\'s telemetry stamp'
    if t['median_lag_s'] is None:
        return 'a decision lag is missing or not finite'
    if t['step_median_lag_s'] > MAX_MEDIAN_LAG_S:
        return f'median decision lag {t["median_lag_s"]} s, {t["step_median_lag_s"]} s read on the telemetry step'
    return f'a decision was {t["max_lag_s"]} s late'


class Watched:
    """The provider, with the last response kept so the driver can tell a transport failure from a bad reply, and the
    settings the last call asked for."""

    def __init__(self, provider):
        self.inner, self.last, self.label, self.requested = provider, None, None, None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def settings(self, request) -> dict:
        """What one call asked of the model, read from the provider and the request. claude_provider sends no
        temperature and no sampling seed (read from ClaudeProvider.complete, which passes only the model, max_tokens, the
        system prompt, the messages, the effort, cache control and the fallback, and on the gateway route the body field
        that switches off the gateway's store of replies, named in gateway_cache), so the list of sampling fields sent is
        empty. A provider that sends any other sampling field must say so in a sampling_fields_sent attribute."""
        inner = self.inner
        cap = getattr(inner, 'max_output_tokens', None)
        asked = getattr(request, 'max_output_tokens', None)
        sent = min(x for x in (asked, cap) if x is not None) if (asked, cap) != (None, None) else None
        asked_of_gateway = {'gateway_cache': inner.gateway_cache} if getattr(inner, 'gateway_cache', None) else {}
        return {'provider': getattr(inner, 'name', None), 'via': getattr(inner, 'via', None),
                'model': getattr(inner, 'model', None), 'effort': getattr(inner, 'effort', None),
                'max_output_tokens': sent, 'cache_control': getattr(inner, 'cache', None),
                'server_fallback': getattr(inner, 'fallback', None),
                'sampling_fields_sent': list(getattr(inner, 'sampling_fields_sent', [])), **asked_of_gateway}

    def complete(self, request):
        self.requested = self.settings(request)
        self.last = self.inner.complete(request)
        return self.last


def delay_sentence() -> str:
    """The one sentence of fact about the fixed delay that every protocol 3 request carries (round five, B5). Its number
    is COMMAND_DELAY_S, so a change of the delay changes the text and nothing else needs an edit."""
    return (f'Each command you return is sent to the drone {COMMAND_DELAY_S:g} s after the observation it was computed '
            'from; until then the drone keeps flying on the previous command. ')


def protocol3_pack(task: str):
    """The task's pack with delay_sentence() added at the end of its goal text, which the learner reads in every request.
    pack.PACKS is shared with protocol 2, whose requests must not change, so the sentence is added here, on a copy, and
    never in pack.py. The goal text ends in a space, so the sentence joins on as one more sentence of it."""
    pack = P.PACKS[task]
    return replace(pack, public=replace(pack.public, learner_goal=pack.public.learner_goal + delay_sentence()))


class Context:
    """One learner's view, kept by Telohelm's own Coordinator: the flights it has seen and its refused attempts. It
    never reaches a learning boundary by itself; the driver asks it for a request."""

    def __init__(self, name: str, root: Path, task: str, proposer):
        from telohelm.learning import Coordinator
        from telohelm.runtime.library import Library
        self.name, self.root = name, root
        self.work = root / 'contexts' / name
        self.work.mkdir(parents=True)
        pack = protocol3_pack(task)
        library = Library(self.work / 'library', pack=pack.public)
        guard = library.add({'kind': 'check', 'decision': 'control', 'conditions': [], 'source': P.GUARDS[task],
                             'origin': {'trusted_control_guard': 'designer-supplied velocity format and limits'}})
        library.set_status(guard, 'adopted', 'supplied action-format guard, not learned')
        # The settings scored-2's learning used (demo.run), except that no boundary is ever reached, and that the request
        # carries the procedure-only sentence (pack.PROCEDURE_ONLY). The core's learning.py puts that sentence after its
        # own rules and before its example rules, which it appends when examples=True, so it does not end the request.
        # It sits in the same place in the fuzz learner (learn.py), which also passes examples=True.
        self.co = Coordinator(library, self.work, proposer, lambda scenario: True, None, attempt_every=10 ** 9,
                              trial_set=3, procedures_only=True, candidates=1, flight_pack=pack, examples=True,
                              extra_rules=P.PROCEDURE_ONLY)
        self.flights: list[str] = []       # case folders this learner has seen, relative to the block
        self.folders: dict[str, str] = {}  # the name each flight was recorded under, to its folder
        self.attempts, self.reasons = 0, []

    def see(self, scenario, folder: Path, name: str | None = None) -> None:
        """One flown case, recorded as Telohelm records a live episode, under name (its episode id unless renamed).
        The learner reads its examples from <work>/<episode>/, as demo.run arranges."""
        name = name or scenario.episode_id
        outcome = json.loads((folder / 'outcome.json').read_text())
        mirror = self.work / name
        mirror.mkdir()
        for f in ('episode.log', 'episode.heads', 'broker.log', 'broker.heads'):
            shutil.copy2(folder / f, mirror / f)
        _write(mirror / 'summary.json', {'outcome': outcome})
        self.co.after_episode(replace(scenario, episode_id=name), outcome, complete=outcome['end_reason'] is not None)
        self.flights.append(str(folder.relative_to(self.root)))
        self.folders[name] = self.flights[-1]

    def begin(self) -> None:
        """The next attempt, as Coordinator.attempt starts one: take the queued reasons and choose the examples. With
        nothing new queued (a refused format, no new flights), the last reasons stand, as a re-flight would give."""
        self.attempts += 1
        self.co.attempts = self.attempts
        queued, self.co.queue = self.co.queue, []
        self.reasons = queued or self.reasons
        self.co._select_examples(self.attempts, self.reasons)

    def messages(self, tail=()) -> list:
        return self.view(tail)[0]

    def view(self, tail=()) -> tuple:
        """The messages for one send, and the flight folders whose moments were kept in them. The folders come from the
        core's own record of what it kept (the fitted log that Coordinator.messages fills), so they are what the text
        shows after any dropping to fit the input cap, in the order the learner saw the flights."""
        fitted: dict = {}
        messages = self.co.messages(self.reasons, list(tail), fitted)
        self.co._log_examples(self.attempts, 1 + len(tail) // 2, fitted)
        kept = {self.folders[r['episode']] for r in fitted.get('kept', [])}
        return messages, [f for f in self.flights if f in kept]

    def refused(self, stage: str, why: list[str], source: str | None) -> None:
        """Remember a refused attempt as Coordinator does, for the next request's previous_attempts."""
        if stage == 'trial':
            self.co._remember(self.attempts, 'procedure', 'control', 'trial', why, source)
        else:
            self.co._remember(self.attempts, None, None, stage, why, None)


class Block:
    def __init__(self, root: Path, task: str, block: int, matched: list, threat: list, proposer, provider: Watched,
                 *, speedup: float, instance: int, late_flights: str, before_flight=None):
        self.root, self.task, self.block = Path(root), task, block
        self.cases = {'matched': matched, 'threat': threat}
        self.proposer, self.provider = proposer, provider
        self.speedup, self.instance, self.late_flights = speedup, instance, late_flights
        self.before_flight = before_flight      # scored.flight_gate: the load check before each flight
        self.candidates: dict[str, dict] = {}
        self.trials: dict[tuple, dict] = {}
        self.timing: list[dict] = []
        self.usage = self.root / 'usage.jsonl'

    # -- flights ------------------------------------------------------------------------------------------------

    def fly(self, rel: str, sources: list, cases: list) -> dict:
        """A battle-style run of cases with the guard and sources, checked for lateness before anyone reads it.

        late_flights 'stop' raises on the first late flight; 'record' (pilots only) keeps it; 'refly' moves the whole
        call aside when any of its flights is late and flies it again, at most REFLIGHTS times, keeping the last attempt
        whether or not it is late. Only the timing of each flight is read before that choice is made."""
        from .battle import run
        out = self.root / rel
        for attempt in range(1, REFLIGHTS + 2):
            run(out, self.task, sources, rel, cases=cases, speedup=self.speedup, instance=self.instance,
                command_delay_periods=COMMAND_DELAY_PERIODS,
                **({'before_flight': self.before_flight} if self.before_flight is not None else {}))
            peak = peak_rss_bytes()
            rows, outcomes = [], {}
            for c in cases:
                o = json.loads((out / c.episode_id / 'outcome.json').read_text())
                rows.append({'flight': f'{rel}/{c.episode_id}', **timing(o), 'attempt': attempt,
                             'peak_rss_bytes': peak})
                outcomes[c.episode_id] = o
            late = [r for r in rows if r['late']]
            if late and self.late_flights == 'refly' and attempt <= REFLIGHTS:
                aside = Path(LATE_DIR) / rel / f'attempt-{attempt}'
                (self.root / aside).parent.mkdir(parents=True, exist_ok=True)
                out.rename(self.root / aside)
                for r in rows:
                    r['set_aside_from'], r['flight'] = r['flight'], f"{aside}/{r['flight'].rsplit('/', 1)[1]}"
                self.timing.extend(rows)
                _write(self.root / 'timing.json', self.timing)
                print(f'{rel}: {len(late)} of {len(rows)} flights late at attempt {attempt}; moved to {aside} unread '
                      f'and flown again', flush=True)
                continue
            if late and self.late_flights == 'refly':
                for r in rows:
                    r['kept_late'] = r['late']
            for r in rows:
                self.timing.append(r)
                _write(self.root / 'timing.json', self.timing)
                if r['late'] and self.late_flights == 'stop':
                    raise InfrastructureFault(f"{r['flight']}: {late_reason(r)}")
            return outcomes

    def trial(self, cid: str, family: str) -> dict:
        """Fly a valid candidate on one trial list, once per block, and judge each layout by Telohelm's trial rule."""
        key = (cid, family)
        if key in self.trials:
            return self.trials[key]
        from telohelm.runtime.library import Library
        rel = f'flights/trial/{cid}/{family}'
        source = self.candidates[cid]['source']
        outcomes = self.fly(rel, [source], self.cases[family])
        library = Library(self.root / rel / 'library', pack=P.PACKS[self.task].public)
        sha = [s for s in library.adopted('control', 'procedure')]
        if len(sha) != 1:
            raise RuntimeError(f'{rel}: expected one adopted procedure, found {len(sha)}')
        rows = []
        for c in self.cases[family]:
            folder = self.root / rel / c.episode_id
            records = [p for p in (json.loads(line)['payload'] for line in
                                   (folder / 'episode.log').read_text().splitlines()) if p.get('kind') == 'decision']
            verdict = P.component_trial('control', sha[0], outcomes[c.episode_id], records)
            rows.append({'episode_id': c.episode_id, 'goal_met': bool(outcomes[c.episode_id]['goal_met']),
                         'end_reason': outcomes[c.episode_id]['end_reason'], 'trial_passed': verdict['passed']})
        failed = [r['episode_id'] for r in rows if not r['trial_passed']]
        entry = {'candidate_id': cid, 'trial_list': family, 'passed': not failed, 'flight_dir': rel,
                 'outcomes': rows,
                 # The reason Telohelm feeds back for a failed trial (Monitor.feedback), naming the first failure by the
                 # name the arm's view records the trial flight under (_refuse_previous), so the core gives its alias in
                 # every arm. Before 13 November 2026 it named the bare case id, which view C never saw and so sent raw,
                 # with its seed, family and band, while view D aliased it (leak inspection, finding 1; round three).
                 'why': [f'the procedure did not do its part of the goal in trial episode {failed[0]}-{cid}'] if failed
                 else []}
        self.trials[key] = entry
        return entry

    # -- candidates ---------------------------------------------------------------------------------------------

    def write(self, cid: str, context: Context, messages: list | None = None, shown: list | None = None) -> dict:
        """One candidate slot: the request (built by context unless given, with the flights it shows), a format repair
        if needed, the record."""
        from telohelm.local_model import first_object
        from telohelm.runtime.procedures import reply_errors
        folder = self.root / 'candidates' / cid
        folder.mkdir(parents=True)
        first, first_shown = (messages, shown) if messages is not None else context.view()
        payload = payload_json(first)
        request = {'candidate_id': cid, 'request_id': f'{self.task}-b{self.block}-{cid}', 'parent': PARENT[cid],
                   'context_flights': list(context.flights), 'shown_flights': list(first_shown),
                   'model_payload_json': payload,
                   'request_sha256': _sha(payload), 'call_number': CALL_NUMBER[cid]}
        _write(folder / 'request.json', request)
        tail, calls, reply, errors, text = [], [], None, [], ''
        while len(calls) < CALLS_PER_SLOT:
            sent, sent_shown = (first, first_shown) if not tail else context.view(tail)
            before = len(self.proposer.ledger.calls)
            self.provider.last, self.provider.requested = None, None
            self.provider.label = (cid, len(calls) + 1)
            text = self.proposer(sent, {'attempt': CALL_NUMBER[cid], 'call': len(calls) + 1,
                                        'episode': request['request_id']})
            calls.append(self._receipt(cid, len(calls) + 1, sent, text, before, sent_shown))
            try:
                candidate = first_object(text)
                errors = reply_errors(candidate, pack=context.co.pack) or context.co._scope_errors(candidate)
            except ValueError as e:
                candidate, errors = None, [str(e)]
            if not errors:
                reply = candidate
                break
            if not (text or '').strip():
                # An empty, refused or cut-off reply with no text uses up the slot with no format-repair call: the
                # repair turn would carry an empty assistant message, which the model service is likely to refuse,
                # and the block would then stop as a fault chosen by the model's reply (leak inspection, finding 2;
                # round three). The draft's section 4.1: an empty reply is the model's answer and uses its slot.
                break
            tail = tail + [('assistant', text), ('user', 'Fix these problems and reply again: ' + '; '.join(errors))]
        record = {'candidate_id': cid, 'format_valid': reply is not None, 'parent': PARENT[cid],
                  'call_ids': [c['call_id'] for c in calls], 'errors': errors if reply is None else [],
                  'empty_reply': reply is None and not (text or '').strip()}
        if reply is not None:
            (folder / 'source.py').write_text(reply['source'], encoding='utf-8')
            record['source_sha256'] = hashlib.sha256((folder / 'source.py').read_bytes()).hexdigest()
        else:
            record['source_sha256'] = None
        _write(folder / 'candidate.json', record)
        self.candidates[cid] = {**record, 'source': reply['source'] if reply else None}
        return self.candidates[cid]

    def _receipt(self, cid: str, k: int, messages: list, text: str, before: int, shown: list) -> dict:
        """One API call's usage row and receipt. The usage row is written for every call; the receipt file only for a call
        that was answered. A transport failure, a time-out or a copy stops the block, after its usage row."""
        response = self.provider.last
        rows = [c for c in self.proposer.ledger.calls[before:]]
        if response is None or not rows:
            raise InfrastructureFault(f'{cid} call {k}: the request was not sent (preflight refused or no reply)')
        status = response.status
        call_id = rows[-1].request_id
        usage = self._provider_usage(call_id)
        payload = payload_json(messages)
        requested = self.provider.requested
        scripted = (requested or {}).get('provider') in (None, 'scripted')
        served = usage.get('served_by') or (response.provider_ids or {}).get('served_by') or ('scripted' if scripted else None)
        receipt = {'call_id': call_id, 'candidate_id': cid, 'call': k, 'request_sha256': _sha(payload),
                   'status': status, 'input_tokens': usage.get('input_tokens'),
                   'output_tokens': usage.get('output_tokens'), 'list_cost_usd': usage.get('cost_usd'),
                   SERVED_FIELD: served, SETTINGS_FIELD: requested,
                   # True when a real model service was asked and replied, whatever it said: status says whether the reply
                   # was an answer, a refusal or cut off. A transport failure or time-out stops the block after this row.
                   REAL_FIELD: not scripted}
        # The spending row is written first, for every call the provider logged, whatever became of the reply: a copy, a
        # time-out and a failed call are in the provider's log, so they are here too, and the spending stop
        # (run_scored3.Runner3.spent_usd) and the analysis count each call once (build F2, ruling 45, point 2).
        with self.usage.open('a', encoding='utf-8') as f:
            f.write(json.dumps(receipt, sort_keys=True) + '\n')
        if status == 'timed_out' or (status == 'failed' and 'error' in (response.provider_ids or {})):
            raise InfrastructureFault(f'{cid} call {k}: model service {status}: {response.provider_ids}')
        if served is None:
            # Every reply the model service gives names the model that served it. A real call with no such label was
            # not answered by a model, so it is a fault of the service and never a used candidate slot
            # (notes/TAKEOVER-20261111.md, rulings of 11 November, unanswered calls).
            raise InfrastructureFault(f'{cid} call {k}: the model service gave no served-model label ({status})')
        _write(self.root / 'candidates' / cid / 'calls' / f'{k}.json',
               {**receipt, 'shown_flights': list(shown), 'model_payload_json': payload, 'reply_text': text})
        return receipt

    def _provider_usage(self, call_id: str) -> dict:
        log = self.root / 'claude-usage.jsonl'
        if not log.exists():
            return {}
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        return next((r for r in reversed(rows) if r.get('request_id') == call_id), {})

    # -- the four arms ------------------------------------------------------------------------------------------

    def run(self) -> dict:
        matched, threat = self.cases['matched'], self.cases['threat']
        self.fly('flights/first/P0', [], matched)
        self.fly('flights/first/P1', [], threat)
        views = {name: Context(name, self.root, self.task, self.proposer) for name in ('P0', 'C', 'D')}
        for name, family in (('P0', 'matched'), ('C', 'matched'), ('D', 'threat')):
            first = 'P0' if family == 'matched' else 'P1'
            for c in self.cases[family]:
                views[name].see(c, self.root / 'flights' / 'first' / first / c.episode_id)
        p0, ctx_c, ctx_d = views['P0'], views['C'], views['D']
        p0.begin()
        c0_messages, c0_shown = p0.view()
        ctx_c.begin()
        if payload_json(ctx_c.messages()) != payload_json(c0_messages):
            raise RuntimeError("arm C's first request differs from c0's; the shared candidate would not be shared")
        self.write('c0', p0, c0_messages, c0_shown)
        ctx_d.begin()
        self.write('c1', ctx_d)
        arms = {}
        for arm, (family, order) in ARMS.items():
            trials, used = [], []
            for slot, cid in enumerate(order):
                if cid not in self.candidates:
                    if cid in ('f1', 'f2'):
                        self.write(cid, p0, c0_messages, c0_shown)
                    else:
                        view = ctx_c if arm == 'C' else ctx_d
                        self._refuse_previous(view, order[slot - 1], family)
                        view.begin()
                        self.write(cid, view)
                cand = self.candidates[cid]
                used += cand['call_ids']
                if not cand['format_valid']:
                    trials.append({'candidate_id': cid, 'trial_list': family, 'passed': False, 'flight_dir': None,
                                   'outcomes': []})
                    continue
                t = self.trial(cid, family)
                trials.append({k: t[k] for k in ('candidate_id', 'trial_list', 'passed', 'flight_dir', 'outcomes')})
                if t['passed']:
                    break
            win = trials[-1] if trials and trials[-1]['passed'] else None
            arms[arm] = {'adopted': win is not None, 'candidate_id': win['candidate_id'] if win else None,
                         'source_sha256': self.candidates[win['candidate_id']]['source_sha256'] if win else None,
                         'trials': trials, 'call_ids': list(dict.fromkeys(used))}
        c0_threat = self.trials.get(('c0', 'threat'))
        record = {'schema_version': 1, 'task': self.task, 'block': self.block,
                  'c0_zone_qualified': c0_threat['passed'] if c0_threat else False, 'arms': arms}
        _write(self.root / 'arms.json', record)
        return record

    def _refuse_previous(self, view: Context, previous: str, family: str) -> None:
        """Before a repair: the previous candidate's refusal and, if it flew, its trial flights, into this view."""
        cand = self.candidates[previous]
        if not cand['format_valid']:
            stage = 'no_answer' if cand['empty_reply'] else 'format'
            view.refused(stage, cand['errors'] or ['no reply'], None)
            return
        t = self.trials[(previous, family)]
        view.refused('trial', t['why'], cand['source'])
        for c in self.cases[family]:
            # Renamed, as demo.run renames a re-flown layout, so a layout seen twice is two episodes.
            view.see(c, self.root / t['flight_dir'] / c.episode_id, name=f'{c.episode_id}-{previous}')


def make_proposer(root: Path, task: str, *, scored: bool, gem_model: str | None, stub=None,
                  run_root: Path | None = None):
    """The proposer and provider demo.run uses: Claude through the gateway, or a scripted stub for pilots. run_root is
    the folder that holds the run's blocks; with it, the provider also checks replies against the message ids of every
    block of the run (claude_provider.RunMessageIds)."""
    from telohelm.learning import GatewayProposer
    from telohelm.runtime.models import ScriptedProvider
    work = root / 'learning'
    work.mkdir(parents=True)
    if stub is None:
        from .claude_provider import MAX_OUTPUT_TOKENS, ClaudeProvider
        provider = Watched(ClaudeProvider(root / 'claude-usage.jsonl', model='sonnet', gem_model=gem_model,
                                          scored=scored, run_root=run_root, block=root.name))
        condition = 'gem-scored' if scored else 'gem-development'
        proposer = GatewayProposer('http://127.0.0.1:1', 'Qwen/Qwen3.8-27B', work, f'ardupilot-{task}',
                                   condition=condition, input_cap=32768, max_output_tokens=MAX_OUTPUT_TOKENS,
                                   count_tokens=provider.count_tokens)
    else:
        provider = Watched(None)
        provider.inner = ScriptedProvider(lambda request: stub(provider.label, request))
        proposer = GatewayProposer('http://127.0.0.1:1', 'Qwen/Qwen3.8-27B', work, f'ardupilot-{task}',
                                   condition='authored-reply-demo', input_cap=16384)
    proposer.provider, proposer.model = provider, getattr(provider.inner, 'model', 'scripted')
    return proposer, provider


def run_block(root: Path, task: str, block: int, matched: list, threat: list, *, speedup: float, instance: int,
              scored: bool, gem_model: str | None, stub=None, late_flights: str = 'refly', warmup_case=None,
              before_flight=None, run_root: Path | None = None) -> dict:
    """One learning block into root, which the caller's guard has created with its manifest. run_root is the folder
    that holds the run's blocks, where the run's file of message ids lives (make_proposer). With warmup_case, the
    block's process first flies that case as its warm-up flight (fly_warmup), before any flight of the block."""
    root = Path(root)
    if late_flights not in LATE_MODES:
        raise ValueError(f'late_flights is one of {LATE_MODES}')
    if scored and (stub is not None or late_flights != 'refly'):
        raise ValueError('a scored block uses the model and flies a late call again in place (round two, ruling 3)')
    if warmup_case is not None:
        fly_warmup(root, task, warmup_case, speedup=speedup, instance=instance)
    P.HOST.update(root=root, speedup=speedup, instance=instance)
    proposer, provider = make_proposer(root, task, scored=scored, gem_model=gem_model, stub=stub, run_root=run_root)
    return Block(root, task, block, matched, threat, proposer, provider, speedup=speedup, instance=instance,
                 late_flights=late_flights, before_flight=before_flight).run()


def pilot_stub(task: str):
    """Scripted replies for an engineering pilot, chosen to pass every path once: a valid candidate that fails (hold
    still), a format repair, a slot lost to an empty reply (one call since 13 November 2026), and the designer's reference
    controller. Development
    only; the records are unreportable and say what wrote each candidate."""
    from telohelm.runtime.models import ModelResponse
    from .demo import HOLD_STILL, REFERENCE

    def procedure(source):
        return json.dumps({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': source,
                           'reason': {'code': 'missing_tool', 'text': 'scripted pilot reply'}})
    plan = {('c0', 1): procedure(HOLD_STILL[task]), ('c1', 1): procedure(REFERENCE[task]),
            ('f1', 1): 'not a procedure', ('f1', 2): procedure(HOLD_STILL[task]),
            ('f2', 1): procedure(REFERENCE[task]), ('rC1', 1): '', ('rC1', 2): '',
            ('rC2', 1): procedure(REFERENCE[task]), ('rD1', 1): procedure(REFERENCE[task]),
            ('rD2', 1): procedure(HOLD_STILL[task])}

    def reply(label, request):
        text = plan.get(label, '')
        return ModelResponse('answered', text) if text else ModelResponse('failed', '')
    return reply


ADOPT_REPLIES = Path(__file__).with_name('testdata') / 'adopt-replies.json'


def adopt_stub(task: str):
    """Scripted replies under which every arm should adopt, for an engineering pilot on a quiet machine. c0 holds still
    and fails both trial lists. c1 and rC1 send the first procedure and f1 the second, each a procedure that a model wrote
    in scored-2 and that passed a three-layout threat trial there (testdata/adopt-replies.json holds the sources and where
    each came from). So D should adopt c1, C rC1, and A and B f1; B and C do not adopt c0. That these procedures pass
    protocol 3's layouts is expected, not shown: only a flight can show it. Development only, as pilot_stub."""
    from telohelm.runtime.models import ModelResponse
    from .demo import HOLD_STILL
    first, second = [r['source'] for r in json.loads(ADOPT_REPLIES.read_text())['sources'][task]]

    def procedure(source):
        return json.dumps({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': source,
                           'reason': {'code': 'missing_tool', 'text': 'scripted adoption reply'}})
    plan = {('c0', 1): procedure(HOLD_STILL[task]), ('c1', 1): procedure(first), ('f1', 1): procedure(second),
            ('rC1', 1): procedure(first)}

    def reply(label, request):
        text = plan.get(label, '')
        return ModelResponse('answered', text) if text else ModelResponse('failed', '')
    return reply


PILOT_STUBS = {'pilot': pilot_stub, 'adopt': adopt_stub}

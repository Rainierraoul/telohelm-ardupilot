"""Teach Telohelm from a fuzzer's failures, then test on what it never learned from.

Run from paper3/:
  .venv/bin/python -m ardupilot.learn --task land --from-run runs/gem-sonnet-land-1 \\
      --gem-model bedrock/au.anthropic.claude-sonnet-5-5 --out runs/learn-land-1

Each round screens fresh scenarios with the current procedure, shrinks a few failures to the simplest scenario that
still fails the same way, and hands them to Telohelm's learner with moments from its own flights. A candidate is adopted
only if it passes those failures and keeps earlier successes (the regression set), both judged on the simulator's truth.

Learning sees scenarios with one kind of event. Two test sets stay out of learning and are flown before and after with
fresh seeds: more single-event scenarios, and scenarios combining events, a family learning never sees. Jamming and
radio loss are left out for now, because ArduPilot's failsafes take the vehicle and a procedure has little chance to
act. Development only: the model's records are unreportable.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
import json
from pathlib import Path
import random
import time

from telohelm.demo import _write

from . import battle, fuzz
from . import pack as P

KINDS = ('gust', 'motor', 'spoof', 'threat')
# The core's prompt offers checks and pairs whatever the pack allows, and a refused offer costs a call of the attempt.
PROCEDURE_ONLY = ('In this run reply with one entry of kind "procedure" only. Checks and pairs are not accepted, whatever '
                  'the rules above say about them.')
SCREEN_SEEDS, KNOWN_SEEDS, COMBINED_SEEDS = 200_000, 500_000, 600_000


def kinds(scenario):
    return {e[0] for e in scenario.events}


def single(scenario):
    return len(kinds(scenario)) == 1 and kinds(scenario) <= set(KINDS)


def combined(scenario):
    return len(kinds(scenario)) >= 2 and kinds(scenario) <= set(KINDS)


def only(kind):
    """A scenario holding exactly one event, of this kind. Used when a round learns one capability at a time, so a
    candidate is not asked to fix several unrelated failures at once (../LAND-REFUSAL-DIAGNOSIS.md)."""
    return lambda scenario: kinds(scenario) == {kind}


def drawn(task, wanted, count, first_seed):
    """The first count scenarios from first_seed upwards that wanted accepts."""
    out, seed = [], first_seed
    while len(out) < count:
        scenario = fuzz.draw(task, seed)
        if wanted(scenario):
            out.append(scenario)
        seed += 1
    return out


def by_id(cases):
    return {c.episode_id: c for c in cases}


def row_id(row):
    return f"{row['family']}-{row['seed']}"


def simpler(scenario):
    """Variants one step simpler than a scenario, each with its change named."""
    out = []
    if scenario.wind_ms:
        out.append(('no base wind', replace(scenario, wind_ms=0.0)))
    for i, event in enumerate(scenario.events):
        others = scenario.events[:i] + scenario.events[i + 1:]
        if others:
            out.append((f'without {event[0]}', replace(scenario, events=others)))
        kind, weaker = event[0], list(event)
        if kind == 'spoof':
            weaker[3], weaker[4] = round(event[3] / 2, 1), round(event[4] / 2, 1)
        elif kind == 'gust':
            weaker[3], weaker[4] = round(event[3] / 2, 1), round(event[4] / 2, 1)
        elif kind == 'motor':
            weaker[3] = round((1 + event[3]) / 2, 2)
        elif kind == 'threat':
            weaker[5] = round(event[5] * 0.7, 1)
        if tuple(weaker) != event:
            out.append((f'weaker {kind}', replace(scenario, events=others[:i] + (tuple(weaker),) + others[i:])))
        if kind != 'threat' and event[2] > 4:
            weaker = list(event)
            weaker[2] = event[2] // 2
            out.append((f'shorter {kind}', replace(scenario, events=others[:i] + (tuple(weaker),) + others[i:])))
    return out


def shrink(out, task, source, scenario, ending, workers, speedup, passes=2):
    """The simplest scenario found that still ends the same way, and the steps taken. Each pass flies every one-step
    simplification in parallel and keeps one that still fails alike."""
    steps = []
    for number in range(passes):
        variants = simpler(scenario)
        if not variants:
            break
        cases = [replace(v, episode_id=f'v{i}-{number}') for i, (_, v) in enumerate(variants)]
        rows, _ = fuzz.fly_many(Path(out) / f'pass-{number}', task, source, 'shrinking', cases, workers, speedup)
        alike = {row_id(r) for r in rows if not r['timing_invalid'] and r['end_reason'] == ending}
        keep = next((i for i, c in enumerate(cases) if c.episode_id in alike), None)
        if keep is None:
            break
        steps.append(variants[keep][0])
        scenario = variants[keep][1]
    return scenario, steps


def rates(rows):
    valid = [r for r in rows if not r['timing_invalid']]
    return {'met': sum(r['goal_met'] for r in valid), 'of': len(valid), 'left_out_for_lag': len(rows) - len(valid),
            'endings': dict(Counter(r['end_reason'] for r in valid))}


class Learner:
    """The library, the model and Telohelm's coordinator, with one flight at a time through the ordinary episode loop."""

    def __init__(self, out, task, start_sources, origin, gem_model, claude_model, regression, speedup):
        from telohelm.learning import Coordinator, GatewayProposer
        from telohelm.runtime.library import Library
        from .claude_provider import MAX_OUTPUT_TOKENS, ClaudeProvider
        self.out, self.task, self.pack, self.spec, self.speedup = Path(out), task, P.PACKS[task], P.TASKS[task], speedup
        self.work = self.out / 'learning'
        self.work.mkdir()
        self.library = Library(self.out / 'library', pack=self.pack.public)
        guard = self.library.add({'kind': 'check', 'decision': 'control', 'conditions': [], 'source': P.GUARDS[task],
                                  'origin': {'trusted_control_guard': 'designer-supplied velocity format and limits'}})
        self.library.set_status(guard, 'adopted', 'supplied action-format guard, not learned')
        for code in start_sources:
            entry = self.library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': code,
                                      'origin': {'imported_from': origin}})
            self.library.set_status(entry, 'adopted', f'adopted earlier in {origin}')
        self.provider = ClaudeProvider(self.out / 'claude-usage.jsonl', model=claude_model, gem_model=gem_model)
        proposer = GatewayProposer('http://127.0.0.1:1', 'Qwen/Qwen3.8-27B', self.work, f'learn-{task}',
                                   condition='fuzz-learning', input_cap=32768, max_output_tokens=MAX_OUTPUT_TOKENS,
                                   count_tokens=self.provider.count_tokens)
        proposer.provider, proposer.model = self.provider, self.provider.model
        self.coordinator = Coordinator(self.library, self.work, proposer, lambda scenario: True, None, attempt_every=10**9,
                                       trial_set=1, regression=regression, procedures_only=True, examples=True,
                                       extra_rules=PROCEDURE_ONLY, flight_pack=self.pack)

    def sources(self):
        return [self.library.entry(a)['source'] for a in self.library.adopted('control', 'procedure')]

    def fly(self, scenario):
        from telohelm.runtime.broker import Broker
        from telohelm.runtime.episode_loop import NoModels, run_episode
        from telohelm.runtime.ledger import Ledger
        from telohelm.runtime.trusted_log import TrustedLog
        P.HOST.update(root=self.out, speedup=self.speedup, gcs=False, instance=0, keep_simulators=False)
        name = scenario.episode_id
        folder = self.work / name
        folder.mkdir()
        ledger = Ledger()
        log = TrustedLog(folder / 'episode.log', folder / 'episode.heads', 'fuzz-learning')
        broker_log = TrustedLog(folder / 'broker.log', folder / 'broker.heads', 'fuzz-learning')
        broker = Broker(name, broker_log, ledger, None, condition='fuzz-learning', stream=f'learn-{self.task}',
                        goal=self.pack.goal, tools={})
        try:
            outcome = run_episode(scenario, self.library, NoModels(), log, ledger, max_steps=self.spec.max_ticks,
                                  broker=broker, pack=self.pack)['outcome']
        finally:
            log.close()
            broker_log.close()
        _write(folder / 'summary.json', {'outcome': outcome})
        return outcome

    def attempt_on(self, keepers, failures):
        """Fly the round's episodes, successes first, and make the attempt on the failures after the last of them."""
        coordinator, monitor = self.coordinator, self.coordinator.monitor
        monitor.trial_set_size = len(failures)
        flights = keepers + failures
        coordinator.attempt_every = len(monitor.completed) + len(flights)
        seen = len(coordinator.events)
        for scenario in flights:
            outcome = self.fly(scenario)
            coordinator.after_episode(scenario, outcome, complete=outcome['end_reason'] is not None)
        return [e for e in coordinator.events[seen:] if e['kind'] in ('attempt_result', 'attempt_failed', 'no_attempt')]


def run(args):
    out = Path(args.out).resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; records are never overwritten')
    out.mkdir(parents=True)
    task, started = args.task, time.monotonic()
    origin = str(args.from_run)
    learner = Learner(out, task, [battle.adopted_source(args.from_run)], origin, args.gem_model, args.claude_model,
                      args.regression, args.learn_speedup)
    screen_pred = only(args.kind) if args.kind else single
    known = drawn(task, screen_pred, args.test_count, KNOWN_SEEDS)
    mixed = [] if args.kind else drawn(task, combined, args.test_count, COMBINED_SEEDS)
    _write(out / 'run-config.json', {k: str(v) for k, v in vars(args).items()})
    report = {'task': task, 'origin': origin, 'rounds': [], 'scope': 'development, unreportable'}

    def test(label):
        result = {}
        for name, cases in (('known_families', known), ('combined_families', mixed)):
            if not cases:
                continue
            rows, bad = fuzz.fly_many(out / f'test-{label}' / name, task, learner.sources(), origin, cases, args.workers,
                                      args.speedup)
            result[name] = {**rates(rows), 'worker_failures': bad}
        combined_txt = (f", combined {result['combined_families']['met']} of {result['combined_families']['of']}"
                        if 'combined_families' in result else '')
        print(f"test {label}: single events {result['known_families']['met']} of "
              f"{result['known_families']['of']}{combined_txt}", flush=True)
        return result

    report['before'] = test('before')
    rng = random.Random(f'learn/{task}')
    for number in range(1, args.rounds + 1):
        round_dir = out / f'round-{number}'
        cases = drawn(task, single, args.screen_count, SCREEN_SEEDS + number * 10_000)
        rows, _ = fuzz.fly_many(round_dir / 'screen', task, learner.sources(), origin, cases, args.workers, args.speedup)
        valid = [r for r in rows if not r['timing_invalid']]
        lookup = by_id(cases)
        failed = [r for r in valid if not r['goal_met']]
        entry = {'round': number, 'screen': rates(rows)}
        print(f"round {number}: screen met {entry['screen']['met']} of {entry['screen']['of']} "
              f"{dict(Counter(r['end_reason'] for r in failed))}", flush=True)
        if not failed:
            report['rounds'].append({**entry, 'stopped': 'no failures in the screen'})
            break
        # One failure from each kind of ending and event first, then any others.
        rng.shuffle(failed)
        seen, picks = set(), []
        for row in failed:
            key = (row['end_reason'], tuple(sorted(kinds(lookup[row_id(row)]))))
            if key not in seen:
                seen.add(key)
                picks.append(row)
        picks = (picks + [r for r in failed if r not in picks])[:args.failures]
        failures, shrinks = [], []
        for i, row in enumerate(picks):
            small, steps = shrink(round_dir / f'shrink-{i}', task, learner.sources(), lookup[row_id(row)],
                                  row['end_reason'], args.workers, args.speedup)
            failures.append(replace(small, episode_id=f'r{number}-fail-{i}'))
            shrinks.append({'from': row_id(row), 'ending': row['end_reason'], 'steps': steps,
                            'scenario': asdict(small)})
        good = [r for r in valid if r['goal_met']]
        rng.shuffle(good)
        keepers = [replace(lookup[row_id(r)], episode_id=f'r{number}-ok-{i}') for i, r in enumerate(good[:args.keepers])]
        events = learner.attempt_on(keepers, failures)
        passed = any(e['kind'] == 'attempt_result' and e['passed'] for e in events)
        entry.update(shrinks=shrinks, attempt=[{k: e.get(k) for k in ('kind', 'passed', 'reason')} for e in events],
                     adopted=passed)
        report['rounds'].append(entry)
        _write(out / 'report.json', report)
        print(f"  shrank {[len(s['steps']) for s in shrinks]} steps; attempt {'adopted' if passed else 'refused'}"
              f" {[e.get('reason') for e in events if e['kind'] != 'attempt_result']}", flush=True)
    report['after'] = test('after')
    usage = out / 'claude-usage.jsonl'
    used = [json.loads(line) for line in usage.read_text().splitlines()] if usage.exists() else []
    report.update(model_calls=learner.provider.calls, cost_usd=round(sum(r.get('cost_usd') or 0 for r in used), 4),
                  final_sources=learner.sources(), elapsed_seconds=round(time.monotonic() - started))
    _write(out / 'report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--task', choices=sorted(P.TASKS), required=True)
    parser.add_argument('--kind', choices=KINDS, help='learn one event kind at a time: screen, trial and known-test '
                        'scenarios all hold exactly this event, and the combined-families test is skipped '
                        '(../LAND-REFUSAL-DIAGNOSIS.md)')
    parser.add_argument('--from-run', type=Path, required=True, help='a run folder whose summary has one adopted source')
    parser.add_argument('--gem-model', help="a model name on Deakin's GEM gateway")
    parser.add_argument('--claude-model', choices=('sonnet', 'haiku', 'opus'), default='sonnet')
    parser.add_argument('--rounds', type=int, default=4)
    parser.add_argument('--failures', type=int, default=3, help='failures a candidate must fix each round')
    parser.add_argument('--keepers', type=int, default=3, help="successes flown in each round, for later regression sets")
    parser.add_argument('--regression', type=int, default=4, help='earlier successes a candidate must keep')
    parser.add_argument('--screen-count', type=int, default=32)
    parser.add_argument('--test-count', type=int, default=48)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--speedup', type=float, default=5.0)
    parser.add_argument('--learn-speedup', type=float, default=10.0, help='for flights one at a time')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args)
    print(json.dumps({k: report[k] for k in ('model_calls', 'cost_usd', 'elapsed_seconds')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

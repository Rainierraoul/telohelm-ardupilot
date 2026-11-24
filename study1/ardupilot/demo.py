"""Run Telohelm's unchanged learning core on an ArduPilot copter task, with authored replies by default.

Run from paper3/:  .venv/bin/python -m ardupilot.demo --task reach --out runs/reach-demo
Tasks: reach (fly to a point and hold), avoid (the same, round a no-go zone), orbit (circle a point), land (land on a
point). Add --gcs to watch in QGroundControl (use --speedup 1 to watch at real speed).
Add --claude to have Claude write the procedure instead (Sonnet 5.5 unless --claude-model says otherwise), or
--gem-model MODEL to go through Deakin's GEM gateway (needs GEM_BASE_URL and GEM_API_KEY). Development only.

Generated learning scenarios are first flown with no procedure, and fail. With authored replies the learner then receives a procedure that
holds still, which must fail its trial, and a reference controller, which must pass; this checks that the task can be
solved and that its rules judge flights correctly. With a model, the learner gets one real request. Either way, later
episodes, one in wind, must be flown by the adopted procedure.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import time

from telohelm.demo import _write

from . import pack as P
from .vehicle import ARDUPILOT

CLAMP = ("    lim = 0.9 * g.max_speed_ms\n"
         "    s = math.hypot(vn, ve)\n"
         "    if s > lim:\n"
         "        vn, ve = vn * lim / s, ve * lim / s\n")
REFERENCE = {
    'reach': ("import math\n\ndef decide(ctx):\n    g = ctx.goal\n"
              "    vn = 0.6 * (g.target_north_m - ctx.north_m)\n    ve = 0.6 * (g.target_east_m - ctx.east_m)\n"
              + CLAMP + "    return {'vn': vn, 've': ve}\n"),
    # Go straight unless the straight path passes too close to the zone; then slide round the zone on the side the
    # target lies, keeping a margin.
    'avoid': ("import math\n\ndef decide(ctx):\n    g = ctx.goal\n"
              "    px, py = ctx.north_m, ctx.east_m\n"
              "    dx, dy = g.target_north_m - px, g.target_east_m - py\n"
              "    cx, cy = g.zone_north_m, g.zone_east_m\n"
              "    keep = g.zone_radius_m + 5.0\n"
              "    length = math.hypot(dx, dy)\n"
              "    blocked = False\n"
              "    if length > 1e-6:\n"
              "        u = max(0.0, min(1.0, ((cx - px) * dx + (cy - py) * dy) / (length * length)))\n"
              "        blocked = math.hypot(px + u * dx - cx, py + u * dy - cy) < keep\n"
              "    if blocked:\n"
              "        rx, ry = px - cx, py - cy\n"
              "        r = math.hypot(rx, ry) or 1e-6\n"
              "        side = 1.0 if rx * dy - ry * dx > 0 else -1.0\n"
              "        speed = 0.8 * g.max_speed_ms\n"
              "        push = 0.8 * max(0.0, keep - r)\n"
              "        vn = speed * (-ry / r) * side + push * rx / r\n"
              "        ve = speed * (rx / r) * side + push * ry / r\n"
              "    else:\n"
              "        vn, ve = 0.6 * dx, 0.6 * dy\n" + CLAMP + "    return {'vn': vn, 've': ve}\n"),
    # Fly the tangent clockwise seen from above, with a correction towards the circle.
    'orbit': ("import math\n\ndef decide(ctx):\n    g = ctx.goal\n"
              "    rx, ry = ctx.north_m - g.centre_north_m, ctx.east_m - g.centre_east_m\n"
              "    r = math.hypot(rx, ry) or 1e-6\n"
              "    ux, uy = rx / r, ry / r\n"
              "    pull = max(-2.0, min(2.0, 0.6 * (g.orbit_radius_m - r)))\n"
              "    vn = 3.0 * -uy + pull * ux\n    ve = 3.0 * ux + pull * uy\n"
              + CLAMP + "    return {'vn': vn, 've': ve}\n"),
    # Move over the point, then descend, slowing near the ground.
    'land': ("import math\n\ndef decide(ctx):\n    g = ctx.goal\n"
             "    dn, de = g.target_north_m - ctx.north_m, g.target_east_m - ctx.east_m\n"
             "    vn, ve = 0.6 * dn, 0.6 * de\n" + CLAMP +
             "    vd = 0.0\n"
             "    if math.hypot(dn, de) < 0.8:\n"
             "        vd = min(0.9 * g.max_vertical_ms, 0.3 + 0.2 * ctx.alt_m)\n"
             "    return {'vn': vn, 've': ve, 'vd': vd}\n"),
    # Fly to the point in three dimensions: horizontal towards it, vertical towards its height (vd positive descends).
    'reach3d': ("import math\n\ndef decide(ctx):\n    g = ctx.goal\n"
                "    vn = 0.6 * (g.target_north_m - ctx.north_m)\n    ve = 0.6 * (g.target_east_m - ctx.east_m)\n"
                + CLAMP +
                "    vd = 0.6 * (ctx.alt_m - g.target_alt_m)\n"
                "    vlim = 0.9 * g.max_vertical_ms\n"
                "    vd = max(-vlim, min(vlim, vd))\n"
                "    return {'vn': vn, 've': ve, 'vd': vd}\n"),
}
# Head for the next gate from where the drone will be in 0.4 s, at a speed that brakes at 2 m/s/s to arrive at about
# 2 m/s, and cancel any sideways drift relative to the gate. Two simpler versions failed (runs/race3d-authored-1,
# runs/race3d-ref-probe-1): a constant full-speed pursuit circles the gates, and braking without the look-ahead still
# overshoots, because ArduPilot answers a velocity command about half a second late. Only a check that the race is
# solvable; the learner never sees it.
REFERENCE['race3d'] = ('import math\n'
                       '\n'
                       'def decide(ctx):\n'
                       '    g = ctx.goal\n'
                       '    gate = g.gates[min(ctx.gates_passed, len(g.gates) - 1)]\n'
                       '    cn, ce, cu = ctx.vn_ms, ctx.ve_ms, -ctx.vd_ms\n'
                       '    # where the drone will be when this command takes hold\n'
                       '    pn, pe, pa = ctx.north_m + 0.4 * cn, ctx.east_m + 0.4 * ce, ctx.alt_m + 0.4 * cu\n'
                       '    dn, de, up = gate.north_m - pn, gate.east_m - pe, gate.alt_m - pa\n'
                       '    d = math.sqrt(dn * dn + de * de + up * up) or 1e-6\n'
                       '    un, ue, uu = dn / d, de / d, up / d\n'
                       '    v = min(0.9 * g.max_speed_ms, math.sqrt(4.0 + 4.0 * d))\n'
                       '    along = cn * un + ce * ue + cu * uu\n'
                       '    sn, se, su = cn - along * un, ce - along * ue, cu - along * uu\n'
                       '    vn, ve, vu = v * un - sn, v * ue - se, v * uu - su\n'
                       '    h = math.hypot(vn, ve)\n'
                       '    if h > 0.9 * g.max_speed_ms:\n'
                       '        k = 0.9 * g.max_speed_ms / h\n'
                       '        vn, ve = vn * k, ve * k\n'
                       '    lim = 0.9 * g.max_vertical_ms\n'
                       '    if abs(vu) > lim:\n'
                       '        vu = lim if vu > 0 else -lim\n'
                       "    return {'vn': vn, 've': ve, 'vd': -vu}\n")
HOLD_STILL = {name: "def decide(ctx):\n    return {" + ', '.join(f"'{f}': 0.0" for f in task.fields) + "}\n"
              for name, task in P.TASKS.items()}


def scenario_sets(task, learn, long_courses=False):
    """Learning scenarios (calm, seeds 1 to learn) and unseen test scenarios: two calm and one in steady wind.
    long_courses (race3d only): the same from the long families, 10 to 16 gates a course."""
    from .battle import generate
    calm, wind = ('long', 'longwind') if long_courses else ('calm', 'wind')
    return ([generate(task, calm, seed) for seed in range(1, learn + 1)],
            [generate(task, calm, 101), generate(task, calm, 102), generate(task, wind, 103)])


def git(*args, cwd):
    return subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True).stdout.strip()


def run(out, task='reach', speedup=10.0, gcs=False, claude=False, claude_model='sonnet', gem_model=None,
        attempts=3, trial_scenarios=3, instance=0, seed_reach3d_run=None, examples=False, seed_race3d_run=None,
        stage_pace=None, long_courses=False, scenarios=None, scored=False):
    """seed_reach3d_run: start a race3d library from that run's adopted reach3d procedure, retargeted to the next gate
    (retarget.py), so learning improves a working skill. examples: show the learner moments from its own flights, as
    learn.py does."""
    claude = claude or gem_model is not None
    from telohelm.learning import Coordinator, GatewayProposer
    from telohelm.runtime.broker import Broker
    from telohelm.runtime.episode_loop import NoModels, run_episode
    from telohelm.runtime.ledger import Ledger
    from telohelm.runtime.library import Library
    from telohelm.runtime.models import ModelResponse, ScriptedProvider
    from telohelm.runtime.trusted_log import TrustedLog, verify

    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; records are never overwritten')
    out.mkdir(parents=True)
    P.HOST.update(root=out, speedup=speedup, gcs=gcs, instance=instance)
    started = time.monotonic()
    pack, spec = P.PACKS[task], P.TASKS[task]
    if stage_pace is not None:
        if task != 'race3d':
            raise ValueError('a stage pace is only for the race3d task')
        from . import battle as B
        B.STAGE_PACE_MS = stage_pace
    if long_courses and task != 'race3d':
        raise ValueError('long courses are only for the race3d task')
    # scenarios: explicit (learning, tests) lists from paper 3's reserved seeds (scored.py); tests may be empty.
    learning, tests = scenarios if scenarios is not None else scenario_sets(task, trial_scenarios, long_courses)
    if scored and not claude:
        raise ValueError('a scored run needs the learning model')
    sources = (HOLD_STILL[task], REFERENCE[task])
    library = Library(out / 'library', pack=pack.public)
    guard = library.add({'kind': 'check', 'decision': 'control', 'conditions': [], 'source': P.GUARDS[task],
                         'origin': {'trusted_control_guard': 'designer-supplied velocity format and limits'}})
    library.set_status(guard, 'adopted', 'supplied action-format guard, not learned')
    seed = None
    if seed_race3d_run:
        from .battle import adopted_source
        if task != 'race3d':
            raise ValueError('a race3d seed is only for the race3d task')
        seed = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [],
                            'source': adopted_source(Path(seed_race3d_run)),
                            'origin': {'imported_from': str(seed_race3d_run)}})
        library.set_status(seed, 'adopted', f'adopted earlier in {seed_race3d_run}; learning continues from it')
    if seed_reach3d_run:
        from .battle import adopted_source
        from .retarget import reach3d_to_race3d
        if task != 'race3d':
            raise ValueError('a reach3d seed is only for the race3d task')
        seed_source = reach3d_to_race3d(adopted_source(Path(seed_reach3d_run)))
        seed = library.add({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': seed_source,
                            'origin': {'imported_from': str(seed_reach3d_run),
                                       'retargeted_by': 'designer: target fields read from the next gate (retarget.py)'}})
        library.set_status(seed, 'adopted', f'reach3d skill from {seed_reach3d_run}, retargeted to race3d; not learned here')
    work = out / 'learning'
    work.mkdir()
    condition = ((('gem-scored' if scored else 'gem-development') if gem_model else
                  ('claude-scored' if scored else 'claude-development')) if claude else 'authored-reply-demo')
    repo = Path(__file__).resolve().parents[2]
    _write(out / 'run-config.json', {
        'mode': condition, 'task': task, 'speedup': speedup, 'tick_s': spec.tick_s, 'max_ticks': spec.max_ticks,
        'ardupilot': {'commit': git('rev-parse', 'HEAD', cwd=ARDUPILOT),
                      'local_changes': git('diff', '--stat', cwd=ARDUPILOT) or None},
        'telohelm_commit': git('rev-parse', 'HEAD', cwd=repo),
        'telohelm_uncommitted': git('status', '--short', '--', 'paper2/telohelm', 'paper3', cwd=repo) or None,
        'learning_model': (f"{gem_model or claude_model} ({'scored' if scored else 'development, unreportable'})"
                           if claude else 'authored replies'),
        'trial_scenarios': trial_scenarios, 'scenarios': [asdict(s) for s in learning + tests],
        'stage_pace_ms': stage_pace, 'long_courses': long_courses,
        'seed': {'from_run': str(seed_reach3d_run or seed_race3d_run), 'source_sha256': hashlib.sha256(
            library.entry(seed)['source'].encode()).hexdigest()} if seed else None,
        'examples': examples})
    receipts = []

    def reply(request):
        number = len(receipts)
        source = sources[number] if number < len(sources) else None
        text = json.dumps({'kind': 'procedure', 'decision': 'control', 'conditions': [], 'source': source,
                           'reason': {'code': 'missing_tool', 'text': 'Authored software control'}}) if source else ''
        receipts.append({'request_id': request.request_id, 'fingerprint': request.fingerprint,
                         'source_sha256': hashlib.sha256(source.encode()).hexdigest() if source else None,
                         'real_model_call': False})
        _write(out / 'authored-calls.json', receipts)
        return ModelResponse('answered' if text else 'failed', text)

    if claude:
        from .claude_provider import MAX_OUTPUT_TOKENS, ClaudeProvider
        provider = ClaudeProvider(out / 'claude-usage.jsonl', model=claude_model, gem_model=gem_model, scored=scored)
        proposer = GatewayProposer('http://127.0.0.1:1', 'Qwen/Qwen3.8-27B', work, f'ardupilot-{task}',
                                   condition=condition, input_cap=32768, max_output_tokens=MAX_OUTPUT_TOKENS,
                                   count_tokens=provider.count_tokens)
        proposer.provider, proposer.model = provider, provider.model
    else:
        proposer = GatewayProposer('http://127.0.0.1:1', 'Qwen/Qwen3.8-27B', work, f'ardupilot-{task}',
                                   condition=condition, input_cap=16384)
        proposer.provider = ScriptedProvider(reply)
    attempts = attempts if claude else 1
    # An attempt follows each round of the learning scenarios, and a candidate must pass the trial on all of them.
    coordinator = Coordinator(library, work, proposer, lambda scenario: True, None, attempt_every=len(learning),
                              trial_set=len(learning),
                              max_attempts=attempts, procedures_only=True, candidates=1 if claude else 2,
                              flight_pack=pack, examples=examples)
    rows = []

    def fly(scenario):
        name = scenario.episode_id
        folder = out / name
        folder.mkdir()
        ledger = Ledger()
        log = TrustedLog(folder / 'episode.log', folder / 'episode.heads', condition)
        broker_log = TrustedLog(folder / 'broker.log', folder / 'broker.heads', condition)
        broker = Broker(name, broker_log, ledger, None, condition=condition, stream=f'ardupilot-{task}',
                        goal=pack.goal, tools={})
        try:
            result = run_episode(scenario, library, NoModels(), log, ledger, max_steps=spec.max_ticks,
                                 broker=broker, pack=pack)
        finally:
            log.close()
            broker_log.close()
        outcome = result['outcome']
        _write(folder / 'outcome.json', outcome)
        if examples:
            # The learner reads its examples from <workdir>/<episode>/ (summary.json and episode.log), where learn.py
            # writes its flights; without this copy every example is silently dropped. The logs are hash-chained and copied whole.
            mirror = work / name
            mirror.mkdir()
            for f in ('episode.log', 'episode.heads', 'broker.log', 'broker.heads'):
                (mirror / f).write_bytes((folder / f).read_bytes())
            _write(mirror / 'summary.json', {'outcome': outcome})
        decisions = [json.loads(line)['payload'] for line in (folder / 'episode.log').read_text().splitlines()]
        used = [e for e in decisions if e.get('kind') == 'decision' and e.get('source') == 'procedure']
        steps = outcome['native_steps']
        row = {'episode': name, 'params': dict(scenario.params), 'wind_ms': scenario.wind_ms,
               'goal_met': outcome['goal_met'], 'end_reason': outcome['end_reason'],
               'seconds': outcome['action_steps'], 'procedure_steps': len(used),
               'max_decision_lag_s': max(s['decision_lag_s'] for s in steps) if steps else None,
               'sources_used': sorted({hashlib.sha256(library.entry(e['method'])['source'].encode()).hexdigest()
                                       for e in used})}
        rows.append(row)
        _write(out / 'episodes.json', rows)
        print(f"{task}/{name}: goal={row['goal_met']} ({row['end_reason']}), {row['seconds']} s, "
              f"procedure steps={row['procedure_steps']}", flush=True)
        return row, outcome

    # Learn: fly every learning scenario, then let the learner try; after a failed attempt fly them again, with the
    # refused attempt fed back, until a procedure is adopted or the attempts run out. Then test on unseen scenarios.
    for round_number in range(1, attempts + 1):
        for scenario in learning:
            if round_number > 1:
                scenario = replace(scenario, episode_id=f'{scenario.episode_id}-r{round_number}')
            row, outcome = fly(scenario)
            seen = len(coordinator.events)
            coordinator.after_episode(scenario, outcome, complete=outcome['end_reason'] is not None)
            for e in coordinator.events[seen:]:
                if e['kind'] == 'attempt_result':
                    print(f"  trial on {len(learning)} scenarios: {'passed' if e['passed'] else 'failed'}", flush=True)
                elif e['kind'] == 'attempt_failed':
                    print(f"  attempt failed: {e.get('reason')}", flush=True)
        if [a for a in library.adopted('control', 'procedure') if a != seed]:
            break
    learned = len(rows)
    for scenario in tests:
        fly(scenario)

    trials = [e for e in coordinator.events if e['kind'] == 'attempt_result']
    chains = {}
    for heads in out.rglob('*heads'):
        path = heads.with_name(heads.name[:-5] + 'log')
        if path.exists():
            verdict = verify(path, heads)
            if not verdict.get('ok'):
                chains[str(path.relative_to(out))] = verdict
    adopted = library.adopted('control', 'procedure')
    adopted_sources = sorted(hashlib.sha256(library.entry(a)['source'].encode()).hexdigest() for a in adopted)
    if claude:
        controller = adopted_sources[0] if len(adopted_sources) == 1 else None
        learning = {'candidate_passed_trial_and_adopted': bool(trials) and trials[-1]['passed']
                    and controller is not None and seed not in adopted}
    else:
        controller = hashlib.sha256(REFERENCE[task].encode()).hexdigest()
        learning = {'hold_still_failed_trial': len(trials) == 2 and not trials[0]['passed'],
                    'reference_passed_trial': len(trials) == 2 and trials[1]['passed']}
    checks = {
        'learning_scenarios_failed_without_procedure': not any(r['goal_met'] for r in rows[:len(learning)]),
        **learning,
        'later_episodes_flown_by_adopted_source': all(
            r['goal_met'] and r['procedure_steps'] == r['seconds'] and r['sources_used'] == [controller]
            for r in rows[learned:]),
        'protected_chains_valid': not chains}
    usage = out / 'claude-usage.jsonl'
    used_rows = [json.loads(line) for line in usage.read_text().splitlines()] if usage.exists() else []
    summary = {'passed': all(checks.values()), 'task': task, 'checks': checks, 'episodes': rows, 'trials': trials,
               'learning_attempts': len([e for e in coordinator.events if e['kind'] == 'attempt_start']),
               'task_contract': pack.public.fingerprint({}), 'scope': condition,
               'real_model_calls': provider.calls if claude else 0,
               'claude_cost_usd': round(sum(r.get('cost_usd') or 0 for r in used_rows), 4) if used_rows else None,
               'gateway_charged_usd': round(sum(r.get('charged_usd') or 0 for r in used_rows), 4) if used_rows else None,
               'adopted_sources': [library.entry(a)['source'] for a in adopted],
               'chain_errors': chains, 'elapsed_seconds': round(time.monotonic() - started, 1),
               'limitations': ('A scored learning run under paper 3\'s protocol (PROTOCOL.md); results are '
                               'reported only through the frozen analysis. ' if scored else
                               'One model request, three fixed scenarios, one simulator run each. Development only: '
                               'the records are unreportable, and nothing here is a learning, benchmark or cost result. '
                               if claude else
                               'Two authored replies, three fixed scenarios, one simulator run each. No model learning, '
                               'benchmark, cost, generalisation or real-time claim. ')
                              + 'The simulator runs freely at its speed-up, so decision time costs simulated time; '
                                'decision_lag_s records it.'}
    _write(out / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--task', choices=sorted(P.TASKS), default='reach')
    parser.add_argument('--speedup', type=float, default=10.0)
    parser.add_argument('--gcs', action='store_true', help='send telemetry to QGroundControl on UDP 14550')
    parser.add_argument('--claude', action='store_true', help='Claude writes the procedure (development only)')
    parser.add_argument('--claude-model', choices=('sonnet', 'haiku', 'opus'), default='sonnet')
    parser.add_argument('--gem-model', help="a model name on Deakin's GEM gateway (see ardupilot.gem_probe)")
    parser.add_argument('--attempts', type=int, default=3, help='learning attempts (model modes)')
    parser.add_argument('--trial-scenarios', type=int, default=3, help='learning scenarios a candidate must pass')
    parser.add_argument('--instance', type=int, default=0, help='simulator instance (its own ports)')
    parser.add_argument('--seed-reach3d-run', type=Path,
                        help='race3d only: start from this run\'s reach3d procedure, retargeted to the next gate')
    parser.add_argument('--examples', action='store_true', help='show the learner moments from its own flights')
    parser.add_argument('--seed-race3d-run', type=Path, help='race3d only: start from this run\'s adopted race3d procedure')
    parser.add_argument('--stage-pace', type=float, help='race3d only: a practice stage\'s pace in m/s (the task asks for 3)')
    parser.add_argument('--long-courses', action='store_true', help='race3d only: practise and test on 10 to 16 gates')
    args = parser.parse_args(argv)
    summary = run(args.out, task=args.task, speedup=args.speedup, gcs=args.gcs, claude=args.claude,
                  claude_model=args.claude_model, gem_model=args.gem_model,
                  attempts=args.attempts, trial_scenarios=args.trial_scenarios, instance=args.instance,
                  seed_reach3d_run=args.seed_reach3d_run, examples=args.examples,
                  seed_race3d_run=args.seed_race3d_run, stage_pace=args.stage_pace, long_courses=args.long_courses)
    print(f"ArduPilot {args.task} development checks: " + ('passed' if summary['passed'] else 'FAILED'))
    for name, ok in summary['checks'].items():
        print(f"  {'ok ' if ok else 'NO '} {name}")
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

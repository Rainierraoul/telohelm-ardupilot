"""Check what an adopted procedure could have copied: training-scenario numbers, the designer's reference, test courses.

Three checks on a learning run, from its saved records only:

1. Memorisation scan. Every number written in the adopted procedure's code is compared with every number in the
   scenarios it learned from (goal positions, gate coordinates, time limits, wind). A match is not proof of copying,
   since small round numbers turn up everywhere, but a coordinate from a training scenario inside the code would be.
   Numbers that are also task defaults (limits, radii) are reported separately, as the learner was told those.
2. Reference leak. The designer's authored reference controller for the task (demo.REFERENCE) must not appear in any
   model request or reply in the run's hash-chained gateway logs.
3. Test leak. The run's test scenarios must not appear in any model request: none of their scenario-specific numbers
   with a decimal part (positions, gates) may occur in the request text.

No saved learning run yet sent the model flight examples (the 3D run's requests held only the task and its
failures), so the run checks have had nothing to find. --self-test plants a leak in made-up text to show they find one.

Run from paper3/:
  .venv/bin/python -m ardupilot.attribution --run runs/reach3d-demo
  .venv/bin/python -m ardupilot.attribution --self-test
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from . import battle, demo
from . import pack as P


def numbers_in(value, out=None):
    """Every number inside a nested structure of lists, tuples and dicts."""
    out = set() if out is None else out
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)):
        out.add(float(value))
    elif isinstance(value, dict):
        for v in value.values():
            numbers_in(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            numbers_in(v, out)
    return out


def code_numbers(source: str):
    """Numeric literals in the code, with their line numbers. A minus sign in front is kept."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) \
                and isinstance(node.operand.value, (int, float)) and not isinstance(node.operand.value, bool):
            found.append((-float(node.operand.value), node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            found.append((float(node.value), node.lineno))
    return found


def scenario_numbers(scenario: dict):
    """The numbers that make a scenario specific: its params and wind. Task defaults are kept apart."""
    return numbers_in([scenario.get('params'), scenario.get('wind_ms'), scenario.get('wind_from_deg'),
                       scenario.get('events')])


def requests(run: Path):
    """Model requests and replies from every gateway log in the run, as text."""
    out = []
    for log in sorted(run.rglob('gateway.log')):
        for line in log.read_text().splitlines():
            payload = json.loads(line).get('payload', {})
            if payload.get('kind') in ('model_start', 'model_end'):
                out.append((str(log.relative_to(run)), payload.get('kind'), json.dumps(payload)))
    return out


def check(run: Path, tests: list | None = None) -> dict:
    """tests: scenario dicts to check for leaks, when the held-out tests are not in the run's own config (paper 3's
    scored learning runs fly their tests separately, from protocol/seeds.json)."""
    run = Path(run)
    config = json.loads((run / 'run-config.json').read_text())
    task = config['task']
    learn_n = config.get('trial_scenarios', 3)
    learning, own_tests = config['scenarios'][:learn_n], config['scenarios'][learn_n:]
    tests = own_tests if tests is None else tests
    source = battle.adopted_source(run)
    defaults = numbers_in(P.TASKS[task].goal({}))

    trained = set().union(*(scenario_numbers(s) for s in learning)) if learning else set()
    literal = code_numbers(source)
    from_training = sorted({(v, line) for v, line in literal if v in trained and v not in defaults and v != 0})
    from_defaults = sorted({(v, line) for v, line in literal if v in defaults})

    texts = requests(run)
    # Lines of every task's reference controller (and the hold-still comparator), not only this task's.
    reference_body = sorted({ln.strip() for src in (*demo.REFERENCE.values(), *demo.HOLD_STILL.values())
                             for ln in src.splitlines() if len(ln.strip()) > 25})
    # A reference line in a request is a leak only if the model had not already written it: from the second request
    # of a conversation on, the model's own earlier reply is sent back to it (pilot reach run, 2 Nov 2026).
    reference_hits, written = [], []
    by_model = {}
    for where, kind, text in texts:
        lines = [ln for ln in reference_body if ln in text]
        if kind == 'model_end':
            by_model.setdefault(where, set()).update(lines)
            if lines:
                written.append({'where': where, 'lines': lines})
        else:
            leaked = [ln for ln in lines if ln not in by_model.get(where, set())]
            if leaked:
                reference_hits.append({'where': where, 'lines': leaked})
    test_specific = set().union(*(scenario_numbers(s) for s in tests)) - trained - defaults if tests else set()
    # Only numbers with a decimal part count, matched as whole numbers: whole numbers such as 21 occur in any request
    # (step counts, times), so they say nothing about a leak.
    telling = {v for v in test_specific if v != int(v)}
    request_texts = [text for where, kind, text in texts if kind == 'model_start']
    pattern = lambda v: re.compile(r'(?<![\d.])' + re.escape(f'{v:g}') + r'(?![\d])')
    test_hits = sorted(v for v in telling if any(pattern(v).search(text) for text in request_texts))

    return {
        'run': str(run), 'task': task, 'adopted_procedure_lines': len(source.splitlines()),
        'numbers_in_code': sorted({v for v, _ in literal}),
        'numbers_matching_training_scenarios': [{'value': v, 'line': line} for v, line in from_training],
        'numbers_matching_task_defaults': [{'value': v, 'line': line} for v, line in from_defaults],
        'model_messages_checked': len(texts),
        'reference_lines_in_requests': reference_hits,
        'reference_lines_written_by_model': written,
        'test_scenario_numbers_checked': len(telling),
        'test_scenario_numbers_found_in_requests': test_hits,
    }


def self_test() -> dict:
    """Show the two leak checks can find a leak, on made-up text, since no saved run yet sends the model examples."""
    reference = demo.REFERENCE['race3d']
    body = [ln.strip() for ln in reference.splitlines() if len(ln.strip()) > 25]
    leaked = json.dumps({'messages': [['user', 'Here is a controller:\n' + reference]]})
    clean = json.dumps({'messages': [['user', 'Fly to north 12.5, east -3.0.']]})
    pattern = lambda v: re.compile(r'(?<![\d.])' + re.escape(f'{v:g}') + r'(?![\d])')
    return {'reference_found_when_present': any(ln in leaked for ln in body),
            'reference_found_when_absent': any(ln in clean for ln in body),
            'test_number_found_when_present': bool(pattern(12.5).search(clean)),
            'test_number_found_inside_other_number': bool(pattern(2.5).search(clean))}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--run', type=Path)
    p.add_argument('--self-test', action='store_true', help='show the leak checks can find a planted leak')
    args = p.parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(), indent=1))
        return 0
    print(json.dumps(check(args.run), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

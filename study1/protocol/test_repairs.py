"""Checks for the repairs of Codex's review of draft 3 (A1 to A4, 3 November 2026), with no simulator or model.

A stand-in simulator (FakeSitl) moves the drone by the commanded velocity each step, so the course runners' records,
protected logs, run times and missing-truth handling can be checked quickly. The validation gate (A4) is checked on
synthetic run folders built in a temporary directory.

Run from paper3/:  .venv/bin/python -m pytest -q protocol/test_repairs.py
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ardupilot import pack as P                      # noqa: E402
from ardupilot.vehicle import MissingTruth, TRUTH_FIELDS   # noqa: E402


def state(**kw):
    s = dict(t=10.0, position_t=10.0, north=0.0, east=0.0, down=-0.1, vn=0.0, ve=0.0, vd=0.0, heading_deg=0.0,
             battery_pct=100, battery_v=12.6, gps_fix=3, gps_sats=10, ekf_flags=0, true_north=0.0, true_east=0.0,
             true_alt=0.1, true_vn=0.0, true_ve=0.0, true_vd=0.0, truth_t=10.0, armed=True, mode='GUIDED')
    s.update(kw)
    return s


LAND_GOAL = {'target_north_m': 0.0, 'target_east_m': 0.0, 'radius_m': 1.5, 'ground_alt_m': 0.3,
             'touchdown_speed_ms': 1.0}


# A1: the landing judge follows the true descent speed, and missing truth is refused.

def test_land_judge_follows_true_descent():
    slow_estimate_fast_truth = state(vd=0.2, true_vd=2.0)
    fast_estimate_slow_truth = state(vd=2.0, true_vd=0.2)
    assert P.judge_land(P.truth(slow_estimate_fast_truth), LAND_GOAL, {}) == 'hard_landing'
    assert P.judge_land(P.truth(fast_estimate_slow_truth), LAND_GOAL, {}) == 'landed'


def test_judge_uses_true_position_and_altitude():
    s = state(north=0.0, east=0.0, down=-0.1, true_north=5.0, true_east=0.0, true_alt=0.1)
    assert P.judge_land(P.truth(s), LAND_GOAL, {}) == 'landed_off_point'
    s = state(down=-0.1, true_alt=4.0)          # the estimate says on the ground, the truth says 4 m up
    assert P.judge_land(P.truth(s), LAND_GOAL, {}) is None


@pytest.mark.parametrize('field', TRUTH_FIELDS)
def test_missing_truth_is_refused(field):
    with pytest.raises(MissingTruth):
        P.truth(state(**{field: None}))


# A3: run times of the procedure and of the guard, kept apart.

def test_run_times_keep_procedure_and_guard_apart():
    tried = [{'procedure': 'a', 'status': 'ok', 'wall_seconds': 0.031, 'cpu_seconds': 0.012, 'accepted': True,
              'checks': [{'check': 'g', 'status': 'ok', 'wall_seconds': 0.024, 'cpu_seconds': 0.009,
                          'accepted': True}]}]
    t = P.run_times(tried)
    assert t == {'procedure_wall_s': 0.031, 'procedure_cpu_s': 0.012, 'guard_wall_s': 0.024, 'guard_cpu_s': 0.009,
                 'attempts': 1}
    assert P.run_times([])['procedure_wall_s'] is None


# A stand-in simulator for the course runners.

class FakeSitl:
    drop_truth_after = None          # set on the class for a test: truth disappears after this many advances

    def __init__(self, folder, vehicle, speedup, **kw):
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.state = state(t=0.0, position_t=0.0, down=0.0, true_alt=0.0, truth_t=0.0)
        self.params_seen, self.command, self.texts = {}, ['fake'], []
        self.v = (0.0, 0.0, 0.0)
        self.advances = 0

    def prepare(self, alt_m=10.0):
        s = self.state
        s.update(down=-alt_m, true_alt=alt_m, t=5.0, position_t=5.0, truth_t=5.0)

    def command_velocity(self, vn, ve, vd=0.0):
        self.v = (vn, ve, vd)

    def drain(self):
        pass

    def advance_to(self, t):
        s, dt = self.state, t - self.state['t']
        vn, ve, vd = self.v
        s.update(north=s['north'] + vn * dt, east=s['east'] + ve * dt, down=s['down'] + vd * dt,
                 vn=vn, ve=ve, vd=vd, t=t, position_t=t)
        s.update(true_north=s['north'], true_east=s['east'], true_alt=-s['down'], true_vn=vn, true_ve=ve,
                 true_vd=vd, truth_t=t)
        self.advances += 1
        if self.drop_truth_after is not None and self.advances > self.drop_truth_after:
            s['true_vd'] = None

    def close(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    from ardupilot import course_run, vehicle
    monkeypatch.setattr(course_run, 'Sitl', FakeSitl)
    monkeypatch.setattr(vehicle, 'Sitl', FakeSitl)
    FakeSitl.drop_truth_after = None
    yield FakeSitl
    FakeSitl.drop_truth_after = None


def records(log: Path):
    return [json.loads(line)['payload'] for line in log.read_text().splitlines()]


def tamper(log: Path, kind: str):
    """Change one value inside the first record of a kind, keeping the line's hash fields as they were."""
    lines = log.read_text().splitlines()
    for i, line in enumerate(lines):
        rec = json.loads(line)
        if rec['payload'].get('kind') == kind:
            rec['payload']['tampered'] = True
            lines[i] = json.dumps(rec)
            break
    log.write_text('\n'.join(lines) + '\n')


def fly_flat(out: Path):
    from ardupilot import course as C, demo
    from ardupilot.course_run import fly_course
    course = C.generate(900000, False, gate_radius=2.0)
    return fly_course(course, demo.REFERENCE['reach'], 'designer reference controller', out, speedup=1.0,
                      instance=10, pass_rule='path')


def fly_3d(out: Path):
    from ardupilot import course3d as C3, demo
    from ardupilot.course3d_run import fly_course
    course = C3.generate(910000, gate_radius=2.0)
    return fly_course(course, demo.REFERENCE['reach3d'], 'designer reference controller', out, speedup=1.0,
                      instance=10, pass_rule='path')


# A2: flat-course flights write a verifiable protected flight log; edits to a step or the end are detected.

def test_flat_course_has_protected_log(fake, tmp_path):
    from telohelm.runtime.trusted_log import verify
    rec = fly_flat(tmp_path / 'flat')
    log, heads = tmp_path / 'flat' / 'flight.log', tmp_path / 'flat' / 'flight.heads'
    assert rec['provenance']['flight_log_verified']['ok'] is True
    rows = records(log)
    kinds = [r['kind'] for r in rows if r.get('kind') != 'anchor']
    assert kinds[0] == 'flight_start' and kinds[-1] == 'flight_end' and kinds.count('step') == len(rec['native_steps'])
    start, end = rows[1] if rows[0].get('kind') == 'anchor' else rows[0], rows[-1]
    assert start['procedure_sha256'] == rec['provenance']['procedure_sha256'] and start['pass_rule'] == 'path'
    assert start['course'] == json.loads(json.dumps(rec['course'])) and start['procedure_source']
    assert end['gates_passed'] == rec['gates_passed'] and end['end_reason'] == rec['end_reason']
    assert all('command' in r and 'truth' in r for r in rows if r.get('kind') == 'step')
    for kind in ('step', 'flight_end'):
        copy = tmp_path / f'copy-{kind}'
        shutil.copytree(tmp_path / 'flat', copy)
        tamper(copy / 'flight.log', kind)
        assert verify(copy / 'flight.log', copy / 'flight.heads')['ok'] is False, kind


# A3: every course step keeps the chooser's attempts with their run times, apart from the decision lag.

@pytest.mark.parametrize('flyer', [fly_flat, fly_3d])
def test_course_steps_keep_run_times(fake, tmp_path, flyer):
    rec = flyer(tmp_path / 'c')
    steps = rec['native_steps']
    assert steps and all(s['procedure_wall_s'] is not None and s['guard_wall_s'] is not None for s in steps)
    assert all('lag_s' in s and s['procedure_wall_s'] != s['lag_s'] or s['lag_s'] == 0 for s in steps)
    logged = [r for r in records(tmp_path / 'c' / 'flight.log') if r.get('kind') == 'step']
    for r in logged:
        a = r['tried'][0]
        assert a['wall_seconds'] is not None and a['cpu_seconds'] is not None
        assert a['checks'][0]['wall_seconds'] is not None
        assert 'lag_s' in r


# A1 in the course runners: missing truth stops the flight as a fault, with the log kept and no result written.

@pytest.mark.parametrize('flyer,result', [(fly_flat, 'course-flight.json'), (fly_3d, 'course3d-flight.json')])
def test_course_missing_truth_is_a_fault(fake, tmp_path, flyer, result):
    from telohelm.runtime.trusted_log import verify
    fake.drop_truth_after = 3
    with pytest.raises(MissingTruth):
        flyer(tmp_path / 'c')
    assert not (tmp_path / 'c' / result).exists()
    assert verify(tmp_path / 'c' / 'flight.log', tmp_path / 'c' / 'flight.heads')['ok'] is True
    end = records(tmp_path / 'c' / 'flight.log')[-1]
    assert end['kind'] == 'flight_end' and end['end_reason'] == 'fault' and 'MissingTruth' in end['fault']


# A4: the validation gate rejects incomplete, duplicated, damaged or mismatched records, and the scheduler reports
# failures. The positive fixture is a complete development run of the repaired scheduler (pilot mode, reusing the
# pilot's libraries, no model calls); set PAPER3_FIXTURE to use another.

import os                                            # noqa: E402

FIXTURE = Path(os.environ.get('PAPER3_FIXTURE', ROOT / 'runs' / 'pilot-repair-20261103'))
FIXTURE_ARGS = dict(tasks=['reach', 'reach3d', 'land'], reuse=ROOT / 'runs' / 'pilot-20261102-c', pilot=True)
LEARN_FIXTURE = ROOT / 'runs' / 'pilot-learn4-reach'
needs_fixture = pytest.mark.skipif(not (FIXTURE / 'logs' / 'scheduler.log').exists()
                                   or 'finished' not in (FIXTURE / 'logs' / 'scheduler.log').read_text(),
                                   reason='the positive fixture run has not finished')


def gate(root, **kw):
    sys.path.insert(0, str(ROOT / 'protocol'))
    from validate import validate
    return validate(root, **{**FIXTURE_ARGS, **kw})


@pytest.fixture(scope='module')
def fixture_copy(tmp_path_factory):
    """A copy of the positive fixture without the simulators' own working folders, which the gate does not read."""
    dst = tmp_path_factory.mktemp('fx') / 'root'
    shutil.copytree(FIXTURE, dst, ignore=shutil.ignore_patterns('simulators', 'analysis'))
    return dst


def fresh(fixture_copy, tmp_path):
    dst = tmp_path / 'root'
    shutil.copytree(fixture_copy, dst)
    return dst


@needs_fixture
def test_gate_passes_complete_fixture(fixture_copy):
    r = gate(fixture_copy)
    assert r['ok'], r['errors'][:10]
    assert r['checked']['task flights'] > 0 and r['checked']['course flights'] > 0


def test_gate_rejects_empty_root(tmp_path):
    assert not gate(tmp_path)['ok']
    assert not gate(tmp_path / 'absent')['ok']


def test_gate_rejects_missing_learning_run(tmp_path):
    (tmp_path / 'logs').mkdir()
    r = gate(tmp_path, tasks=['reach'], reuse=None, pilot=True)
    assert any('learn-reach-0: learning run missing' in e for e in r['errors'])


def first_battle(root):
    return sorted(root.glob('heldout-*-reference/flights'))[0]


@needs_fixture
def test_gate_rejects_dropped_and_duplicated_rows(fixture_copy, tmp_path):
    for change in ('drop', 'duplicate'):
        root = fresh(fixture_copy, tmp_path / change)
        f = first_battle(root) / 'results.jsonl'
        lines = f.read_text().splitlines()
        f.write_text('\n'.join(lines[1:] if change == 'drop' else lines + lines[:1]) + '\n')
        assert not gate(root)['ok'], change


@needs_fixture
def test_gate_rejects_row_that_disagrees_with_records(fixture_copy, tmp_path):
    root = fresh(fixture_copy, tmp_path)
    f = first_battle(root) / 'results.jsonl'
    rows = [json.loads(line) for line in f.read_text().splitlines()]
    rows[0]['goal_met'] = not rows[0]['goal_met']
    f.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    assert any('disagrees' in e for e in gate(root)['errors'])


@needs_fixture
def test_gate_rejects_course_copies_changed_together(fixture_copy, tmp_path):
    """Changing both plain JSON copies of a course result still disagrees with the protected flight log."""
    root = fresh(fixture_copy, tmp_path)
    phase = root / 'courses-flat-reference'
    rows = json.loads((phase / 'rows.json').read_text())
    seed = rows[0]['seed']
    rows[0]['completed'] = not rows[0]['completed']
    (phase / 'rows.json').write_text(json.dumps(rows))
    rec_file = phase / f'seed-{seed}' / 'course-flight.json'
    rec = json.loads(rec_file.read_text())
    rec['completed'] = rows[0]['completed']
    rec_file.write_text(json.dumps(rec))
    assert any('protected flight log' in e for e in gate(root)['errors'])


@needs_fixture
def test_gate_rejects_damaged_and_missing_logs(fixture_copy, tmp_path):
    root = fresh(fixture_copy, tmp_path / 'edit')
    log = sorted(first_battle(root).glob('*/episode.log'))[0]
    log.write_text(log.read_text().replace('"goal_met"', '"goal_met" ', 1))
    assert any('does not verify' in e for e in gate(root)['errors'])
    root = fresh(fixture_copy, tmp_path / 'gone')
    sorted(first_battle(root).glob('*/episode.log'))[0].unlink()
    assert any('protected log missing' in e for e in gate(root)['errors'])


@needs_fixture
def test_gate_rejects_mixed_source(fixture_copy, tmp_path):
    root = fresh(fixture_copy, tmp_path)
    m = sorted(root.glob('*/manifest.json'))[0]
    man = json.loads(m.read_text())
    man['git']['source']['sha256'] = '0' * 64
    m.write_text(json.dumps(man))
    assert any('source fingerprint' in e for e in gate(root)['errors'])


@pytest.mark.skipif(not LEARN_FIXTURE.exists(), reason='no learning fixture')
def test_chains_include_bare_trial_logs(tmp_path):
    sys.path.insert(0, str(ROOT / 'protocol'))
    from collections import Counter
    from validate import check_chains
    root = tmp_path / 'learn'
    shutil.copytree(LEARN_FIXTURE, root, ignore=shutil.ignore_patterns('simulators'))
    errors = []
    check_chains(root, errors, Counter())
    assert errors == []
    trial = sorted(root.rglob('trial-evidence/**/log'))[0]
    trial.chmod(0o644)                                  # trial evidence is saved read-only
    trial.write_text(trial.read_text().replace('"decision"', '"decision" ', 1))
    check_chains(root, errors, Counter())
    assert any('does not verify' in e for e in errors)
    errors = []
    trial.unlink()
    check_chains(root, errors, Counter())
    assert any('protected log missing' in e for e in errors)


def test_scheduler_reports_worker_exception_and_failed_analysis(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    r = S.Runner(tmp_path / 'w', pilot=True)
    def boom(name, args, instance):
        raise RuntimeError('worker broke')
    monkeypatch.setattr(r, 'one', boom)
    r.pool([('phase-a', ['heldout'])], [10])
    assert r.failed == ['phase-a']
    # A failed analysis (the gate, or a crash) makes the run's exit status a failure.
    monkeypatch.setattr(S.Runner, 'pool', lambda self, jobs, instances: None)
    monkeypatch.setattr(S.subprocess, 'run', lambda *a, **k: S.subprocess.CompletedProcess(a, 7))
    code = S.main(['run', str(tmp_path / 'a'), '--pilot', '--libraries', str(ROOT / 'runs' / 'pilot-20261102-c'),
                   '--tasks', 'reach'])
    assert code == 1
    assert 'analysis exited 7' in (tmp_path / 'a' / 'logs' / 'scheduler.log').read_text()


def test_scheduler_holds_learning_at_spend_limit(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    out = tmp_path / 'w'
    r = S.Runner(out, pilot=True)
    started = []
    def fake_run(cmd, **k):                     # a stand-in learning run writes its summary, as a real one does
        started.append(cmd)
        if 'learn' in cmd:
            run = Path(cmd[cmd.index('--out') + 1]) / 'run'
            run.mkdir(parents=True)
            (run / 'summary.json').write_text(json.dumps({'claude_cost_usd': 0.0}))
        return S.subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(S.subprocess, 'run', fake_run)
    def finished(name, cost):
        (out / name / 'run').mkdir(parents=True)
        (out / name / 'run' / 'summary.json').write_text(json.dumps({'claude_cost_usd': cost}))
        (out / 'logs' / f'{name}.done').write_text('done\n')
    job = lambda name: (name, ['learn', '--task', 'reach', '--run', '0', '--out', str(out / name)])
    finished('learn-reach-0', 6.0)
    finished('learn-reach-1', 3.99)
    r.one(*job('learn-reach-2'), 10)           # US$9.99 spent: starts
    assert len(started) == 1 and r.failed == []
    finished('learn-reach-3', 0.01)
    r.one(*job('learn-reach-4'), 10)           # US$10.00 spent: held, not started
    assert len(started) == 1 and r.failed == ['learn-reach-4']
    assert 'HOLD learn-reach-4' in (out / 'logs' / 'scheduler.log').read_text()
    r.one('heldout-reach-reference', ['heldout', '--out', str(out / 'h')], 10)   # flight phases are not held
    assert len(started) == 2


def test_spend_counts_only_finished_runs_and_faults_bad_records(tmp_path):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    out = tmp_path / 'w'
    r = S.Runner(out, pilot=True)
    (out / 'learn-reach-0' / 'run').mkdir(parents=True)
    (out / 'learn-reach-0' / 'run' / 'summary.json').write_text('{"claude_cost_usd": 4')   # still being written
    assert r.spent_usd() == 0.0
    (out / 'learn-reach-0' / 'run' / 'summary.json').write_text('{"claude_cost_usd": 4.5}')
    (out / 'logs' / 'learn-reach-0.done').write_text('done\n')
    assert r.spent_usd() == 4.5
    (out / 'learn-reach-1' / 'run').mkdir(parents=True)
    (out / 'learn-reach-1' / 'run' / 'summary.json').write_text('{"checks": {}}')           # finished, no cost
    (out / 'logs' / 'learn-reach-1.done').write_text('done\n')
    with pytest.raises(KeyError):
        r.spent_usd()
    r.pool([('learn-reach-2', ['learn', '--out', str(out / 'learn-reach-2')])], [10])
    assert r.failed == ['learn-reach-2']                                     # held as a fault, never counted as zero


def test_gate_accepts_moved_records_but_not_another_library(tmp_path):
    from validate import same_library
    old, new = '/a/runs/scored/learn-reach-0/run', str(tmp_path / 'copy' / 'learn-reach-0' / 'run')
    assert same_library(old, old)
    assert same_library(old, new)                                      # the same records, moved
    assert not same_library('/a/runs/scored/learn-reach-1/run', new)    # another learning run
    assert not same_library('', new)


# Next-protocol analysis additions (4 November 2026): processor seconds, per-library course differences, and billed
# cost reported as unavailable when the gateway sends no charge.

def test_paired_difference_per_library_counts_each_course_once():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import paired_difference
    d = paired_difference({1: 1, 2: 1, 3: 0}, {1: 1, 2: 0, 3: 1, 4: 1})
    assert d['n'] == 3 and d['difference'] == 0.0 and d['a_only'] == 1 and d['b_only'] == 1


@needs_fixture
def test_analysis_adds_processor_seconds_course_differences_and_charge_availability(fixture_copy):
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import analyse
    r = analyse(fixture_copy, include_pilot=True)
    for phase, t in r['run_times'].items():
        assert {'procedure_cpu_s', 'guard_cpu_s'} <= set(t), phase
        # Processor seconds come from the same decisions as wall time, so there are never more of them. A phase the
        # fixture did not fly has no summary (None) for either.
        if t['procedure_wall_s'] is None:
            assert t['procedure_cpu_s'] is None, phase
        else:
            assert t['procedure_cpu_s']['n'] <= t['procedure_wall_s']['n'], phase
    per_library = [v for k, v in r['courses'].items() if 'reference' not in k and 'pooled' not in k]
    assert per_library and all(v['learned_minus_reference'].get('n') for v in per_library)
    for task, v in r['learning'].items():
        # No call in the fixture carries a gateway charge, so billed cost is unavailable, never 0.
        assert v['gateway_charged_usd'] is None and v['calls_with_gateway_charge'] == 0, task


# Second protocol, Study 2 (4 November 2026): the calm arm learns on the threat layouts with the zone removed.

@pytest.mark.parametrize('task', ['reach', 'reach3d', 'land'])
def test_matched_calm_differs_from_its_threat_scenario_only_in_the_threat(task):
    from ardupilot.battle import generate
    for seed in (9301, 9321, 40001):
        threat, calm = generate(task, 'threat', seed), generate(task, 'matched', seed)
        assert calm.episode_id == f'matched-{seed}' and calm.events == ()
        assert [e[0] for e in threat.events] == ['threat']
        assert (calm.task, calm.params, calm.wind_ms, calm.wind_from_deg) == \
            (threat.task, threat.params, threat.wind_ms, threat.wind_from_deg)
        # A plain calm scenario with the same seed is a different place (its own random stream).
        assert generate(task, 'calm', seed).params != calm.params


def test_billed_cost_is_a_total_only_when_every_call_has_a_charge():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import billed_cost
    none = billed_cost([{'charged_usd': None}, {}])
    assert none['gateway_charged_usd'] is None and none['gateway_charged_known_subtotal_usd'] is None
    part = billed_cost([{'charged_usd': 0.02}, {'charged_usd': None}])
    assert part['gateway_charged_usd'] is None and part['gateway_charged_known_subtotal_usd'] == 0.02
    assert (part['calls_with_gateway_charge'], part['calls_recorded']) == (1, 2)
    full = billed_cost([{'charged_usd': 0.02}, {'charged_usd': 0.03}])
    assert full['gateway_charged_usd'] == 0.05
    assert billed_cost([])['gateway_charged_usd'] is None


def test_late_share_only_on_lag_summaries():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import lag_quantiles, quantiles
    assert 'share_at_least_0.1s' not in quantiles([0.0, 0.1, 12.0])
    assert lag_quantiles([0.0, 0.1, 0.0, 0.2])['share_at_least_0.1s'] == 0.5


def _blocks(threat, calm, scenarios=10):
    """outcomes for matched_block_difference: threat[b] and calm[b] are each block's goal rates over the scenarios."""
    out = {}
    for b, (t, c) in enumerate(zip(threat, calm)):
        for sc in range(scenarios):
            out[(b, sc)] = (int(sc < t * scenarios), int(sc < c * scenarios))
    return out


def test_matched_blocks_carry_uncertainty_from_either_arm():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import matched_block_difference as diff
    width = lambda r: r['high'] - r['low']
    # Both arms identical in every block: no difference and no spread.
    same = diff(_blocks([0.5] * 6, [0.5] * 6))
    assert same['difference'] == 0 and width(same) == 0
    # Calm fixed, threat varying across blocks: the interval opens.
    threat_varies = diff(_blocks([1, 0, 1, 0, 1, 0], [0.5] * 6))
    # Threat fixed, calm varying across blocks: it opens too, so the calm arm is not treated as a fixed reference.
    calm_varies = diff(_blocks([0.5] * 6, [1, 0, 1, 0, 1, 0]))
    assert width(threat_varies) > 0 and width(calm_varies) > 0
    # More spread in one arm, same means: a wider interval.
    calm_wilder = diff(_blocks([0.5] * 6, [1, 0, 1, 0, 1, 0]))
    calm_milder = diff(_blocks([0.5] * 6, [0.6, 0.4, 0.6, 0.4, 0.6, 0.4]))
    assert width(calm_wilder) > width(calm_milder)


def test_matched_blocks_count_non_adoption_and_need_full_crossing():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import matched_block_difference as diff
    # Block 1's threat run did not adopt: the caller enters 0 on every scenario, and the effect falls with it.
    r = diff(_blocks([1, 0], [0.5, 0.5]))
    assert r['threat_mean'] == 0.5 and r['difference'] == 0.0
    with pytest.raises(ValueError):
        diff({(0, 0): (1, 0), (0, 1): (1, 1), (1, 0): (0, 0)})


def test_scheduler_pause_finishes_running_phase_and_resumes_from_done_marks(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    out = tmp_path / 'w'
    started = []
    def fake_run(cmd, **k):
        started.append(cmd[cmd.index('--out') + 1])
        if len(started) == 1:                    # a pause asked for while the first phase flies
            (out / 'logs' / 'PAUSE').write_text('now\n')
        Path(cmd[cmd.index('--out') + 1]).mkdir(parents=True)
        return S.subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(S.subprocess, 'run', fake_run)
    jobs = [(f'p{i}', ['heldout', '--out', str(out / f'p{i}')]) for i in range(3)]
    r = S.Runner(out, pilot=True)
    r.pausable = True
    r.pool(jobs, [10])
    # The running phase finished and was marked done; nothing else started.
    assert started == [str(out / 'p0')] and (out / 'logs' / 'p0.done').exists() and r.paused
    # Resuming: the pause is cleared and the done phase is skipped.
    (out / 'logs' / 'PAUSE').unlink()
    r2 = S.Runner(out, pilot=True)
    r2.pausable = True
    r2.pool(jobs, [10])
    assert started == [str(out / f'p{i}') for i in range(3)] and not r2.paused
    # Learning is never paused.
    (out / 'logs' / 'PAUSE').write_text('now\n')
    r3 = S.Runner(out, pilot=True)
    r3.pool([('learn-x', ['learn', '--out', str(out / 'learn-x')])], [10])
    monkeypatch.setattr(S.Runner, 'spent_usd', lambda self: 0.0)
    assert not r3.paused


def test_second_protocol_schedule_interleaves_matched_arms():
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    out = Path('/nonexistent/root')
    learn = S.learning_jobs_2(out, S.TASKS, range(S.BLOCKS))
    names = [n for n, _ in learn]
    assert len(names) == len(set(names)) == 3 * S.BLOCKS * 2 + 2 * len(S.RUNS)
    orders = set()
    for t in S.STUDY2_TASKS:
        for b in range(S.BLOCKS):
            pair = [n for n in names if n.startswith(f'learn-{t}-b{b}-')]
            assert sorted(pair) == [f'learn-{t}-b{b}-matched', f'learn-{t}-b{b}-threat']
            assert abs(names.index(pair[0]) - names.index(pair[1])) == 1   # the two arms of a block run together
            orders.add(pair[0].rsplit('-', 1)[1])
    assert orders == {'matched', 'threat'}            # neither arm always goes first
    # Block by block: block 0's runs all come before block 1's.
    assert max(names.index(n) for n in names if '-b0-' in n) < min(names.index(n) for n in names if '-b1-' in n)
    # The order is fixed by the recorded seed.
    assert names == [n for n, _ in S.learning_jobs_2(out, S.TASKS, range(S.BLOCKS))]
    # Each block's learning runs get matching layouts: the same --block for both arms.
    args = dict(learn)
    assert args['learn-land-b3-threat'][args['learn-land-b3-threat'].index('--block') + 1] == '3'
    assert args['learn-land-b3-matched'][args['learn-land-b3-matched'].index('--block') + 1] == '3'


def test_second_protocol_skips_a_non_adopted_arm_and_runner_passes_the_protocol(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    lib = tmp_path / 'lib'
    study2 = {('reach', 0, 'matched'): lib, ('reach', 0, 'threat'): None}
    jobs = [n for n, _ in S.study2_jobs(tmp_path, study2)]
    assert jobs == ['threat-reach-b0-matched']        # a non-adoption has no evaluation flights
    seen = []
    monkeypatch.setattr(S.subprocess, 'run', lambda cmd, **k: (seen.append(cmd), Path(cmd[cmd.index('--out') + 1]).mkdir(parents=True), S.subprocess.CompletedProcess(cmd, 0))[2])
    r = S.Runner(tmp_path / 'w', pilot=True)
    r.protocol = 2
    r.one('heldout-reach-reference', ['heldout', '--task', 'reach', '--reference', '--out', str(tmp_path / 'w' / 'h')], 10)
    assert seen[0][-2:] == ['--protocol', '2']


def test_scored_second_protocol_gate_refuses_fewer_blocks(tmp_path):
    sys.path.insert(0, str(ROOT / 'protocol'))
    from validate import validate
    r = validate(tmp_path, protocol=2, blocks=5)
    assert not r['ok'] and any('checked at 8 blocks' in e for e in r['errors'])


# D3's review of the second protocol's draft 1 (4 November 2026): three reporting repairs before the freeze.

def test_pooled_interval_keeps_the_common_scenario_draw():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import clustered_difference, crossed_difference
    # D3's invented control: every library has the same two scenario differences, 0 and 1.
    one = {('a', 's0'): (1, 1), ('a', 's1'): (1, 0)}
    eight = {(lib, sc): v for lib in 'abcdefgh' for (_, sc), v in one.items()}
    assert (crossed_difference(one)['low'], crossed_difference(one)['high']) == (0.0, 1.0)
    r = crossed_difference(eight)
    # Copying the same two scenarios across eight libraries adds no independent draws of them.
    assert (r['low'], r['high'], r['libraries'], r['scenarios'], r['n_pairs']) == (0.0, 1.0, 8, 2, 16)
    old = clustered_difference(eight)
    assert old['low'] > 0.0 and old['high'] < 1.0    # the first protocol's reader narrows it
    assert crossed_difference({}) == {'n': 0}


def test_selected_pairs_draw_over_every_scheduled_course_and_library():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import crossed_difference
    # Course steps where both completed: library b completed none, a completed one of three courses.
    r = crossed_difference({('a', 2): (40, 30)}, scenarios={1, 2, 3}, libraries={'a', 'b'})
    assert (r['n_pairs'], r['libraries'], r['scenarios'], r['difference']) == (1, 2, 3, 10)
    assert r['empty_resamples'] > 0 and r['low'] == r['high'] == 10


def test_list_cost_and_tokens_are_totals_only_when_every_call_has_them():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import list_usage, usage_totals
    ok = {'cost_usd': 0.06, 'input_tokens': 5000, 'output_tokens': 4000}
    failed = {'cost_usd': None, 'input_tokens': None, 'output_tokens': None, 'status': 'failed'}  # as in the land-1 pilot
    part = list_usage([ok, failed], 0.06)
    assert part['cost_usd_list'] is None and part['cost_usd_list_known_subtotal'] == 0.06
    assert (part['calls_with_list_cost'], part['calls_with_token_counts']) == (1, 1)
    assert part['input_tokens'] is None and part['input_tokens_known_subtotal'] == 5000
    full = list_usage([ok, ok], 0.12)
    assert full['cost_usd_list'] == 0.12 and full['output_tokens'] == 8000
    runs = [{**part, 'calls_recorded': 2}, {**full, 'calls_recorded': 2}]
    t = usage_totals(runs)
    assert t['cost_usd_list_total'] is None and t['cost_usd_list_known_subtotal'] == 0.18
    assert t['calls_without_list_cost'] == 1
    assert usage_totals([{**full, 'calls_recorded': 2}])['cost_usd_list_total'] == 0.12


def _no_adoption(task, blocks=8):
    return [{'block': b, 'arm': arm, 'adopted': False, 'model_calls': 4, 'attempts': 3, 'cost_usd_list': 0.1,
             'cost_usd_list_known_subtotal': 0.1, 'calls_with_list_cost': 4, 'calls_recorded': 4}
            for b in range(blocks) for arm in ('threat', 'matched')]


def test_study2_keeps_planned_denominators_when_no_run_adopts():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from collections import defaultdict
    from analysis import load, study2
    seeds = load(ROOT / 'protocol' / 'seeds-2.json')
    r = study2(defaultdict(list), {'reach': _no_adoption('reach')}, seeds, pilot=False)['reach']
    g, t, h = r['threat_goal_threat_minus_calm'], r['capped_time_s_threat_minus_calm'], r['heldout_threat_minus_calm']
    assert (g['blocks'], g['scenarios'], g['difference'], g['threat_mean']) == (8, 20, 0.0, 0.0)
    # Every flight counts at reach's 90 s limit in both arms.
    assert (t['blocks'], t['scenarios'], t['threat_mean'], t['calm_mean']) == (8, 20, 90.0, 90.0)
    # The whole held-out set, 20 calm and 10 wind, with no successes.
    assert (h['blocks'], h['scenarios'], h['threat_mean']) == (8, 30, 0.0)
    assert r['threat']['cost_usd_list_total'] == 0.8


def test_study2_still_refuses_an_adopted_arm_without_its_flights():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from collections import defaultdict
    from analysis import load, study2
    seeds = load(ROOT / 'protocol' / 'seeds-2.json')
    runs = _no_adoption('land', blocks=1)
    runs[1]['adopted'] = True
    with pytest.raises(ValueError, match='adopted, but its threat flights'):
        study2(defaultdict(list), {'land': runs}, seeds, pilot=False)


def test_pause_during_the_last_phase_stops_before_the_analysis(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import argparse
    import run_scored as S
    out = tmp_path / 'w'
    started = []
    def fake_run(cmd, **k):
        if '--out' in cmd and 'analysis.py' not in str(cmd[1]):
            started.append(Path(cmd[cmd.index('--out') + 1]).name)
            if started[-1] == 'gz':               # the pause lands while the last phase of the last stage flies
                (out / 'logs' / 'PAUSE').write_text('now\n')
            Path(cmd[cmd.index('--out') + 1]).mkdir(parents=True)
        else:
            started.append('analysis')
        return S.subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(S.subprocess, 'run', fake_run)
    flights = [('s1-last', ['heldout', '--out', str(out / 's1-last')])]
    gazebo = [('gz', ['gazebo', '--out', str(out / 'gz')])]
    monkeypatch.setattr(S, 'jobs_2', lambda *a, **k: ({}, {}, [], flights, gazebo))
    a = argparse.Namespace(action='run', pilot=True, blocks=1, spend_limit=None)
    assert S.main_2(a, out, ['reach'], reuse=tmp_path / 'libs') == 2
    assert started == ['s1-last', 'gz']           # the analysis did not start
    # Resuming skips the done phases and runs the analysis.
    assert S.main_2(a, out, ['reach'], reuse=tmp_path / 'libs') == 0
    assert started == ['s1-last', 'gz', 'analysis']


# Fable's review of draft 2 (4 November 2026).

def test_analysis_after_a_failed_gate_goes_to_a_new_folder(tmp_path):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    assert S.analysis_folder(tmp_path) == tmp_path / 'analysis'
    (tmp_path / 'analysis').mkdir()
    assert S.analysis_folder(tmp_path) == tmp_path / 'analysis'      # an empty folder holds no analysis yet
    (tmp_path / 'analysis' / 'analysis.json').write_text('{}')
    assert S.analysis_folder(tmp_path) == tmp_path / 'analysis-2'
    (tmp_path / 'analysis-2').mkdir()
    (tmp_path / 'analysis-2' / 'analysis.json').write_text('{}')
    assert S.analysis_folder(tmp_path) == tmp_path / 'analysis-3'


def test_second_protocol_failed_gate_computes_no_outcome(tmp_path):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import analysis as A
    out = tmp_path / 'out'
    (tmp_path / 'root').mkdir()
    assert A.main([str(tmp_path / 'root'), '--out', str(out), '--protocol', '2', '--include-pilot']) == 3
    r = json.loads((out / 'analysis.json').read_text())
    assert r['outcomes_withheld'] and not r['validation']['ok']
    assert not {'learning', 'heldout', 'study2', 'courses', 'disturbance'} & set(r)
    assert 'no outcome was computed' in (out / 'report.md').read_text()


def test_spend_limit_argument_moves_the_stop_without_touching_the_source(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import run_scored as S
    monkeypatch.setattr(S.Runner, 'spent_usd', lambda self: 13.0)
    ran = []
    monkeypatch.setattr(S.subprocess, 'run', lambda cmd, **k: (ran.append(cmd), Path(cmd[cmd.index('--out') + 1]).mkdir(parents=True), S.subprocess.CompletedProcess(cmd, 0))[2])
    r = S.Runner(tmp_path / 'w', pilot=True)
    r.protocol = 2
    r.one('learn-reach-b0-threat', ['learn', '--out', str(tmp_path / 'w' / 'a')], 10)
    assert not ran and r.failed == ['learn-reach-b0-threat']     # held at the protocol's US$12
    r2 = S.Runner(tmp_path / 'w2', pilot=True)
    r2.protocol, r2.spend_limit = 2, 20.0
    r2.one('learn-reach-b0-threat', ['learn', '--out', str(tmp_path / 'w2' / 'a')], 10)
    assert len(ran) == 1 and not r2.failed


def test_token_subtotals_count_each_field_on_its_own():
    sys.path.insert(0, str(ROOT / 'protocol'))
    from analysis import list_usage
    u = list_usage([{'cost_usd': 0.01, 'input_tokens': 100, 'output_tokens': None},
                    {'cost_usd': 0.02, 'input_tokens': 200, 'output_tokens': 50}], 0.03)
    assert u['input_tokens'] == 300 and u['output_tokens'] is None and u['output_tokens_known_subtotal'] == 50
    # D3's closure case: each field reduced on its own, and a known zero counts as known.
    d = list_usage([{'cost_usd': 0.01, 'input_tokens': 100, 'output_tokens': None},
                    {'cost_usd': 0.01, 'input_tokens': None, 'output_tokens': 20},
                    {'cost_usd': 0.0, 'input_tokens': 0, 'output_tokens': 0}], 0.02)
    assert (d['input_tokens'], d['output_tokens']) == (None, None)
    assert (d['input_tokens_known_subtotal'], d['output_tokens_known_subtotal']) == (100, 20)
    assert (d['calls_with_input_tokens'], d['calls_with_output_tokens'], d['calls_with_token_counts']) == (2, 2, 1)


def test_no_second_reading_after_a_gated_one_and_zero_spend_limit_is_kept(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'protocol'))
    import argparse
    import run_scored as S
    out = tmp_path / 'w'
    (out / 'analysis').mkdir(parents=True)
    (out / 'analysis' / 'analysis.json').write_text(json.dumps({'validation': {'ok': False}}))   # a diagnostic
    assert S.gated_reading(out) is None
    (out / 'analysis-2').mkdir()
    (out / 'analysis-2' / 'analysis.json').write_text(json.dumps({'validation': {'ok': True}}))
    assert S.gated_reading(out) == out / 'analysis-2'
    ran = []
    monkeypatch.setattr(S.subprocess, 'run', lambda cmd, **k: (ran.append(cmd), S.subprocess.CompletedProcess(cmd, 0))[1])
    monkeypatch.setattr(S, 'jobs_2', lambda *a, **k: ({}, {}, [], [], []))
    a = argparse.Namespace(action='run', pilot=True, blocks=1, spend_limit=None)
    assert S.main_2(a, out, ['reach'], reuse=tmp_path / 'libs') == 0 and not ran   # nothing analysed again
    # An explicit stop of 0 holds learning; it does not fall back to the protocol's.
    monkeypatch.setattr(S.Runner, 'spent_usd', lambda self: 0.0)
    r = S.Runner(tmp_path / 'z', pilot=True)
    r.protocol, r.spend_limit = 2, 0.0
    r.one('learn-reach-b0-threat', ['learn', '--out', str(tmp_path / 'z' / 'a')], 10)
    assert not ran and r.failed == ['learn-reach-b0-threat']

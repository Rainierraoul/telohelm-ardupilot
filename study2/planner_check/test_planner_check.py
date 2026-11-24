"""Offline tests of the planner check. No simulator is started: a stand-in simulator takes its place.

Run from paper3/:  .venv/bin/python -B -m pytest planner_check/test_planner_check.py -q
"""
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

import planner_check                                   # first, so that MAVLink 2 is on before pymavlink loads
from planner_check import episode as E, fly, settings as S, summarise
from ardupilot import pack as P, scored
from ardupilot.battle import generate
from ardupilot.vehicle import HOME, Sitl
from protocol import contract3 as C3

HERE = Path(__file__).resolve().parent
EXPECTED_FINGERPRINT = '8700e012b2d85b7f57bfd8c5d2958aa80edcfd9ab3e515527ae7f3de60563afa'


@pytest.fixture
def book():
    scored.use_protocol(3)
    return scored.seeds()


@pytest.fixture
def host(tmp_path):
    saved = dict(P.HOST)
    P.HOST.update(root=tmp_path, speedup=1.0, gcs=False, instance=10, keep_simulators=True, command_delay_periods=3)
    yield tmp_path
    P.HOST.clear()
    P.HOST.update(saved)


# 1. The scored build's fingerprint does not change with this folder present.
def test_fingerprint_is_unchanged_with_the_folder_present():
    assert (HERE / 'fly.py').exists()
    scored.use_protocol(3)
    f = scored.source_fingerprint()
    assert (f['sha256'], f['files']) == (EXPECTED_FINGERPRINT, 86)


# 2. Each defaults file holds exactly its setting's values and the fixed ones.
@pytest.mark.parametrize('s', S.SETTINGS, ids=lambda s: f'setting{s.number}')
def test_defaults_file_holds_exactly_the_settings_values(s, tmp_path):
    path = tmp_path / 'd.parm'
    S.write_defaults(s, path)
    got = S.read_defaults(path)
    want = {'OA_TYPE': s.oa_type, 'OA_MARGIN_MAX': s.margin_m, 'OA_BR_LOOKAHEAD': s.lookahead_m,
            **{k: v for k, (v, _) in S.FIXED.items()}}
    if s.oa_type != 1:       # BendyRuler's parameters exist only when BendyRuler does
        want = {k: v for k, v in want.items() if k not in S.BENDYRULER_ONLY}
    assert got == {k: float(v) for k, v in want.items()}
    assert len(path.read_text().splitlines()) == len(want)
    with pytest.raises(FileExistsError):
        S.write_defaults(s, path)               # a file is never written over


def test_bendyruler_parameters_are_expected_only_when_bendyruler_is_in_use():
    for s in S.SETTINGS:
        names = [n for n in S.expected(s) if n.startswith('OA_BR_')]
        if s.oa_type == 1:
            assert sorted(names) == sorted(S.BENDYRULER_ONLY) and S.expected_absent(s) == ()
        else:
            assert names == [] and S.expected_absent(s) == S.BENDYRULER_ONLY
    assert S.expected(S.SETTINGS[4])['OA_BR_LOOKAHEAD'] == 5.0


def test_the_fallbacks_defaults_switch_the_fence_off_and_nothing_else_changes():
    for s in S.SETTINGS:
        a, b = S.defaults(s), S.defaults(s, preloaded=True)
        assert b['FENCE_ENABLE'] == 0 and a['FENCE_ENABLE'] == 1
        assert {k: v for k, v in a.items() if k != 'FENCE_ENABLE'} == {k: v for k, v in b.items() if k != 'FENCE_ENABLE'}
        assert S.expected(s, True)['FENCE_ENABLE'] == 0


def test_the_speed_limits_are_the_comparators_own_object():
    from ardupilot import autopilot_modes
    assert S.LIMITS is autopilot_modes.LIMITS


def test_the_seven_settings_are_the_designs_table():
    table = [(s.oa_type, s.margin_m) for s in S.SETTINGS]
    assert table == [(0, 5.0), (2, 5.0), (2, 2.0), (1, 5.0), (1, 5.0), (1, 2.0), (1, 2.0)]
    assert [s.lookahead_m for s in S.SETTINGS[3:]] == [15.0, 5.0, 15.0, 5.0]
    assert S.HEADLINE == 1
    assert S.FIXED['FENCE_ENABLE'][0] == 1 and S.FIXED['GUID_OPTIONS'][0] == 64
    assert S.expected(S.SETTINGS[1])['WP_SPD'] == 5.0 and S.expected(S.SETTINGS[1])['WP_SPD_UP'] == 2.0


# 3. PlannerSitl's start command is Sitl's with one more defaults file.
def test_planner_sitl_command_is_sitls_with_one_more_defaults_file(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: mock.MagicMock())
    monkeypatch.setattr(Sitl, '_connect', lambda self, port: mock.MagicMock())
    plain = Sitl(tmp_path / 'a', 'copter', 1.0, instance=11, gcs=False, params={'WP_SPD': 5.0}, stream_hz=10)
    extra = tmp_path / 'setting.parm'
    mine = E.PlannerSitl(tmp_path / 'b', extra, {}, 'copter', 1.0, instance=11, gcs=False, params={'WP_SPD': 5.0},
                         stream_hz=10)
    i, j = plain.command.index('--defaults'), mine.command.index('--defaults')
    assert i == j and plain.command[:i] == mine.command[:j] and plain.command[i + 2:] == mine.command[j + 2:]
    assert mine.command[j + 1] == plain.command[i + 1] + ',' + str(extra)
    assert plain.command[i + 1].count(',') == 0


# 4. With a stand-in simulator: the target goes once, a zone is loaded at the first command after the observation that
# first lists it and never before, and LAND comes only within 0.5 m.
class StandIn:
    """A simulator that flies in a straight line to its target at a fixed speed, and records what it is sent."""
    speed = 2.0

    def __init__(self, folder, defaults_file, expect, **kw):
        self.folder, self.command, self.texts, self.read_back_values = folder, ['stand-in'], [], dict(expect)
        self.episode = None
        t = 100.0
        self.state = dict(t=t, position_t=t, north=0.0, east=0.0, down=-10.0, vn=0.0, ve=0.0, vd=0.0,
                          heading_deg=0.0, battery_pct=90, battery_v=12.0, gps_fix=3, gps_sats=10, ekf_flags=831,
                          true_north=0.0, true_east=0.0, true_alt=10.0, true_vn=0.0, true_ve=0.0, true_vd=0.0,
                          truth_t=t, armed=True, mode='GUIDED')
        self.target = None
        self.positions, self.modes, self.uploads, self.enables = [], [], [], []
        self.kw = kw
        self.read_back_absent, self.preload_record, self.fence_enabled_record = {}, None, None

    def prepare(self, alt_m=10.0):
        pass

    def drain(self):
        pass

    def command_position(self, n, e, alt, yaw_deg=None):
        self.target = (n, e, alt)
        self.positions.append((self.episode.t, self.state['t'], n, e, alt))

    def set_mode(self, mode):
        s = self.state
        self.modes.append((mode, math.hypot(s['north'] - self.target[0], s['east'] - self.target[1])))
        s['mode'] = mode

    def upload_exclusion_circles(self, circles, deadline_t):
        self.uploads.append({'step': self.episode.t, 'sim_t': self.state['t'], 'zones_on': len(self.episode.threats),
                             'circles': list(circles), 'deadline_t': deadline_t})
        return {'started_t': self.state['t'], 'acknowledged_t': self.state['t'] + 0.05, 'deadline_t': deadline_t,
                'items': []}

    def enable_fence(self, deadline_t):
        self.enables.append({'step': self.episode.t, 'sim_t': self.state['t'], 'zones_on': len(self.episode.threats)})
        return {'sent_t': self.state['t'], 'acknowledged_t': self.state['t'] + 0.05, 'deadline_t': deadline_t}

    def advance_to(self, t):
        s, dt = self.state, t - self.state['t']
        if self.target is not None and dt > 0:
            dn, de = self.target[0] - s['north'], self.target[1] - s['east']
            d = math.hypot(dn, de)
            go = min(d, self.speed * dt)
            if d > 0:
                s['north'] += dn / d * go
                s['east'] += de / d * go
            s['true_north'], s['true_east'] = s['north'], s['east']
        s['t'] = s['position_t'] = s['truth_t'] = t

    def close(self):
        pass


def episode_with_stand_in(monkeypatch, scenario, setting=1, route='midflight'):
    made = []

    def make(folder, defaults_file, expect, **kw):
        made.append(StandIn(folder, defaults_file, expect, **kw))
        return made[0]

    monkeypatch.setattr(E, 'make_sim', make)
    ep = E.PlannerEpisode(scenario, S.setting(setting), Path('unused.parm'), route)
    ep.reset()
    made[0].episode = ep
    return ep, made[0]


def test_target_goes_once_and_a_zone_is_loaded_after_the_observation_that_lists_it(host, monkeypatch):
    ep, sim = episode_with_stand_in(monkeypatch, generate('reach', 'threat', 4100001, gap_stratum='close'))
    on_step = None
    for _ in range(60):
        if ep.end_reason is not None or (sim.uploads and ep.t > sim.uploads[0]['step'] + 1):
            break
        ep.step({})
        if on_step is None and ep.threats:
            on_step = ep.t - 1                      # the step that began with the zone on
            assert not sim.uploads                  # and the observation after it is the first to list it
            assert [dict(z) for z in ep.threats] == ep.listed
    assert on_step is not None and len(sim.uploads) == 1
    up = sim.uploads[0]
    assert up['step'] == on_step + 1                # the first command after that observation
    assert up['zones_on'] == 1 and len(up['circles']) == 1
    zone = ep.threats[0]
    assert up['circles'] == [(zone['north_m'], zone['east_m'], zone['radius_m'])]
    assert up['sim_t'] >= ep.t0 + (on_step + 1) + 0.29        # held to 0.3 s past the observation, as a procedure's is
    assert len(sim.positions) == 1 and sim.positions[0][0] == 0      # the target goes once, at the first command
    g = ep.goal
    assert sim.positions[0][2:] == (g['target_north_m'], g['target_east_m'], 10.0)
    assert ep.target_sent['step'] == 0 and ep.uploads[0]['new_zones'] == [zone]


def test_fallback_loads_the_zone_before_take_off_and_enables_the_fence_at_the_moment(host, monkeypatch):
    sc = generate('reach', 'threat', 4100001, gap_stratum='close')
    ep, sim = episode_with_stand_in(monkeypatch, sc, route='preloaded')
    zone = [(e[3], e[4], e[5]) for e in sc.events if e[0] == 'threat']
    assert sim.kw['preload'] == zone and zone                      # loaded at start-up, before take-off
    assert sim.kw['expect']['FENCE_ENABLE'] == 0 if 'expect' in sim.kw else True
    on_step = None
    for _ in range(60):
        if ep.end_reason is not None or (sim.enables and ep.t > sim.enables[0]['step'] + 1):
            break
        ep.step({})
        if on_step is None and ep.threats:
            on_step = ep.t - 1
            assert not sim.enables
    assert on_step is not None and len(sim.enables) == 1 and not sim.uploads     # no upload in flight
    assert sim.enables[0]['step'] == on_step + 1 and sim.enables[0]['sim_t'] >= ep.t0 + (on_step + 1) + 0.29
    assert ep.uploads[0]['route'] == 'preloaded'
    midflight = episode_with_stand_in(monkeypatch, sc)[1]
    assert midflight.kw['preload'] is None


def test_reach3d_target_keeps_its_own_height(host, monkeypatch):
    ep, sim = episode_with_stand_in(monkeypatch, generate('reach3d', 'threat', 4110001, gap_stratum='close'))
    ep.step({})
    assert sim.positions[0][4] == ep.goal['target_alt_m']


def test_land_is_set_only_within_half_a_metre(host, monkeypatch):
    from dataclasses import replace
    sc = replace(generate('land', 'threat', 4120001, gap_stratum='close'), events=())
    ep, sim = episode_with_stand_in(monkeypatch, sc)
    for _ in range(100):
        if ep.end_reason is not None or ep.stage == 'land':
            break
        ep.step({})
    assert ep.stage == 'land' and len(sim.modes) == 1
    assert sim.modes[0][0] == 'LAND' and sim.modes[0][1] < E.LAND_WITHIN_M
    assert len(sim.positions) == 1 and sim.positions[0][4] == 10.0       # over the point, at the height held


class FakeLink:
    """The autopilot's end of the fence upload: it asks for each item in turn and then acknowledges. The simulated
    clock moves 0.1 s a message."""

    def __init__(self, answer=True, ack_type=0):
        self.sent, self.items, self.answer, self.ack_type, self.ms = [], [], answer, ack_type, 5000
        self.target_system, self.target_component = 1, 1
        self.mav = SimpleNamespace(mission_count_send=lambda ts, tc, n, kind: self.sent.append(('count', n, kind)),
                                   mission_item_int_send=lambda *a: self.items.append(a))

    def recv_match(self, blocking=False, timeout=None):
        if not self.answer or not self.sent:
            return None
        self.ms += 100
        if len(self.items) < self.sent[0][1]:
            return SimpleNamespace(get_type=lambda: 'MISSION_REQUEST_INT', seq=len(self.items), time_boot_ms=self.ms,
                                   mission_type=E.FENCE)
        return SimpleNamespace(get_type=lambda: 'MISSION_ACK', type=self.ack_type, time_boot_ms=self.ms,
                               mission_type=E.FENCE)


def bare_sitl(link, wall_limit_s=5.0):
    sim = object.__new__(E.PlannerSitl)
    sim.conn, sim._mission_events, sim.wall_limit_s = link, [], wall_limit_s
    sim.process = SimpleNamespace(poll=lambda: None)
    sim.state = dict(t=5.0, armed=True, mode='GUIDED')
    sim.texts, sim.params_seen, sim.params_absent, sim._acks, sim.absent = [], {}, set(), [], ()
    sim.sensors_enabled = 0
    return sim


def test_fence_upload_turns_back_into_the_zones_within_a_centimetre():
    zones = [(27.31, -12.07, 7.4), (-3.5, 40.2, 6.0)]
    link = FakeLink()
    record = bare_sitl(link).upload_exclusion_circles(zones, deadline_t=9.0)
    assert link.sent == [('count', 2, E.FENCE)]
    assert len(link.items) == 2
    for (n, e, r), item in zip(zones, link.items):
        seq, frame, command, param1, lat_e7, lon_e7, kind = item[2], item[3], item[4], item[7], item[11], item[12], item[14]
        assert command == E.FENCE_CIRCLE_EXCLUSION and kind == E.FENCE and param1 == r
        back_n, back_e = E.latlon_zone(lat_e7, lon_e7)
        assert abs(back_n - n) < 0.01 and abs(back_e - e) < 0.01
    assert record['started_t'] == 5.0 and record['acknowledged_t'] <= 9.0
    lat, lon = E.zone_latlon(0.0, 0.0)
    assert (lat, lon) == (HOME[0], HOME[1])


def test_fence_upload_not_acknowledged_in_time_is_a_fault():
    with pytest.raises(E.PlannerFault):
        bare_sitl(FakeLink(answer=False), wall_limit_s=0.3).upload_exclusion_circles([(1.0, 2.0, 3.0)], deadline_t=6.0)
    with pytest.raises(E.PlannerFault):              # the acknowledgement arrives, but after the end of the step
        bare_sitl(FakeLink()).upload_exclusion_circles([(1.0, 2.0, 3.0)], deadline_t=5.15)
    with pytest.raises(E.PlannerFault):              # the autopilot refuses the fence
        bare_sitl(FakeLink(ack_type=1)).upload_exclusion_circles([(1.0, 2.0, 3.0)], deadline_t=9.0)


def test_read_back_names_a_parameter_that_differs():
    sim = bare_sitl(FakeLink())
    sim.expect = {'OA_TYPE': 2.0, 'OA_MARGIN_MAX': 5.0}
    sim.conn.mav.param_request_read_send = lambda *a: None
    sim.wait = lambda done, limit: setattr(sim, 'params_seen', {'OA_TYPE': 2.0, 'OA_MARGIN_MAX': 2.0})
    with pytest.raises(E.PlannerFault, match='OA_MARGIN_MAX'):
        sim.read_back()
    sim.wait = lambda done, limit: setattr(sim, 'params_seen', {'OA_TYPE': 2.0, 'OA_MARGIN_MAX': 5.0})
    assert sim.read_back() == {'OA_TYPE': 2.0, 'OA_MARGIN_MAX': 5.0}


def test_read_back_asks_again_once_for_a_name_that_got_no_answer_and_records_absent_names():
    sim = bare_sitl(FakeLink())
    sim.expect, sim.absent = {'OA_TYPE': 2.0, 'FENCE_ENABLE': 1.0}, ('OA_BR_TYPE',)
    asked, rounds = [], []
    sim.conn.mav.param_request_read_send = lambda ts, tc, name, idx: asked.append(name.decode())

    def wait(done, limit):
        rounds.append(len(asked))
        if len(rounds) == 1:
            sim.params_seen['OA_TYPE'] = 2.0                  # FENCE_ENABLE's request was dropped
        elif len(rounds) == 2:
            sim.params_seen['FENCE_ENABLE'] = 1.0
        else:
            sim.params_absent.add('OA_BR_TYPE')               # the autopilot says it does not exist
        return True
    sim.wait = wait
    assert sim.read_back() == {'OA_TYPE': 2.0, 'FENCE_ENABLE': 1.0}
    assert asked == ['OA_TYPE', 'FENCE_ENABLE', 'FENCE_ENABLE', 'OA_BR_TYPE']
    assert sim.read_back_absent == {'OA_BR_TYPE': 'absent'}


def test_read_back_is_within_the_autopilots_request_queue():
    assert all(len(S.expected(s)) + len(S.expected_absent(s)) <= 20 for s in S.SETTINGS)
    assert max(len(S.expected(s)) for s in S.SETTINGS) < 20


def test_enable_fence_waits_for_the_acknowledgement_then_the_geofence_bit_in_sys_status():
    def msg(kind, **kw):
        return SimpleNamespace(get_type=lambda: kind, **kw)
    bit = E.mavutil.mavlink.MAV_SYS_STATUS_GEOFENCE
    ack = msg('COMMAND_ACK', command=E.mavutil.mavlink.MAV_CMD_DO_FENCE_ENABLE, result=0, time_boot_ms=5100)

    def link(queue):
        sent = []
        return sent, SimpleNamespace(target_system=1, target_component=1,
                                     recv_match=lambda blocking=False, timeout=None: queue.pop(0) if queue else None,
                                     mav=SimpleNamespace(command_long_send=lambda *a: sent.append(a)))
    sent, conn = link([ack, msg('SYS_STATUS', onboard_control_sensors_enabled=0, time_boot_ms=5200,
                                voltage_battery=12000, battery_remaining=90),
                       msg('SYS_STATUS', onboard_control_sensors_enabled=bit | 1, time_boot_ms=5300,
                           voltage_battery=12000, battery_remaining=90)])
    record = bare_sitl(conn).enable_fence(deadline_t=6.0)
    assert sent[0][2:5] == (E.mavutil.mavlink.MAV_CMD_DO_FENCE_ENABLE, 0, 1)
    assert record['geofence_bit_seen_t'] == 5.3 and 'fence_enable_read' not in record    # not read from FENCE_ENABLE
    # the bit appears only after the end of the step: a fault
    late = [ack, msg('SYS_STATUS', onboard_control_sensors_enabled=bit, time_boot_ms=6500, voltage_battery=1, battery_remaining=1)]
    with pytest.raises(E.PlannerFault, match='geofence'):
        bare_sitl(link(late)[1]).enable_fence(deadline_t=6.0)
    # the bit never appears
    with pytest.raises(E.PlannerFault, match='geofence'):
        bare_sitl(link([ack])[1], wall_limit_s=0.2).enable_fence(deadline_t=6.0)
    with pytest.raises(E.PlannerFault):                  # no acknowledgement before the end of the step
        bare_sitl(link([])[1], 0.2).enable_fence(6.0)


# 5. The episode uses the study's step, judge and outcome, and defines none of its own.
def test_planner_episode_uses_the_studys_step_judge_and_outcome():
    assert issubclass(E.PlannerEpisode, P.Episode)
    for name in ('step', 'outcome', 'measure_progress'):
        assert name not in vars(E.PlannerEpisode)
        assert getattr(E.PlannerEpisode, name) is getattr(P.Episode, name)
    own = set(vars(E.PlannerEpisode))
    assert not any('judge' in name or 'outcome' in name for name in own)
    assert {n for n in own if not n.startswith('__')} == {'_bundle', 'reset', '_alt', 'send_command', '_load_new_zones',
                                                             '_zone_circles'}
    source = (HERE / 'episode.py').read_text() + (HERE / 'fly.py').read_text()
    assert 'def step' not in source and 'def outcome' not in source and 'def judge' not in source


def test_reset_is_the_studys_reset_apart_from_the_simulator_line():
    import ast
    import inspect
    import textwrap

    def statements(fn):
        body = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0].body
        body = [n for n in body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]   # the docstring
        return [ast.dump(n) for n in body
                if not (isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'self.sim')]            # the simulator line
    assert statements(E.PlannerEpisode.reset) == statements(P.Episode.reset)


# 6. The flight lists are the 72 evaluation cases and the 18 development cases, and nothing else.
def test_flight_lists_hold_only_the_listed_seeds(book):
    for pilot, scenarios in ((False, 72), (True, 18)):
        items = fly.flight_list(book, pilot, 1)
        assert len(items) == scenarios * 7
        seeds = {i.seed for i in items}
        assert len(seeds) == scenarios and seeds == fly.allowed_seeds(book, pilot)
        assert not seeds & set(range(5000, 5100))
        assert {i.setting for i in items} == set(range(7))
        assert all(sum(1 for i in items if i.seed == s) == 7 for s in seeds)
        for i in items:
            fly.refuse_unlisted(i, fly.allowed_seeds(book, pilot))
    evaluation = {i.seed for i in fly.flight_list(book, False, 1)}
    assert set(range(3100001, 3100009)) <= evaluation and set(range(3120201, 3120209)) <= evaluation
    development = {i.seed for i in fly.flight_list(book, True, 1)}
    assert {4100001, 4100002, 4100101, 4100102, 4100201, 4100202, 4110001, 4120202} <= development
    assert not development & evaluation


def test_passes_are_each_others_reverse_and_workers_share_them_without_overlap(book):
    one, two = fly.flight_list(book, False, 1), fly.flight_list(book, False, 2)
    assert two == one[::-1] and len(set(one)) == len(one)
    keys = [(C3.TASKS.index(i.task), C3.BANDS.index(i.band), i.seed, i.setting) for i in one]
    assert keys == sorted(keys)
    for items in (one, two):
        shares = [fly.worker_items(items, k) for k in range(4)]
        assert [x for share in shares for x in share].count(items[0]) == 1
        assert {x for share in shares for x in share} == set(items) and sum(map(len, shares)) == len(items)
        assert shares[1][0] == items[1] and shares[1][1] == items[5]
    assert C3.FLIGHT_INSTANCES == (10, 11, 12, 13) and fly.WORKERS == 4


def test_seeds_that_are_not_listed_or_are_reserved_are_refused(book):
    allowed = fly.allowed_seeds(book, False)
    with pytest.raises(SystemExit, match='5000 to 5099'):
        fly.refuse_unlisted(fly.Item(1, 'reach', 'close', 5050), allowed)
    with pytest.raises(SystemExit, match='not in the evaluation list'):
        fly.refuse_unlisted(fly.Item(1, 'reach', 'close', 4100001), allowed)


def test_scenarios_are_the_studys_own_evaluation_cases(book):
    for task in C3.TASKS:
        theirs = {c.episode_id: c for c in C3.evaluation_cases(book, task)}
        mine = {fly.scenario(i).episode_id: fly.scenario(i) for i in fly.flight_list(book, False, 1) if i.task == task}
        assert mine == theirs and len(mine) == 24


# 7. The summary counts a hand-made set of outcomes correctly, faults apart.
def make_flight(root, pass_number, name, setting, task, band, seed, end, met, rows=None):
    folder = root / f'pass{pass_number}' / 'worker0' / 'flights' / name
    folder.mkdir(parents=True)
    (folder / 'outcome.json').write_text(json.dumps({'end_reason': end, 'goal_met': met}))
    (folder / 'planner.json').write_text(json.dumps({'setting': setting, 'task': task, 'band': band, 'seed': seed,
                                                     'planner_rows': rows or {'dijkstra_rows': 0, 'bendyruler_rows': 0}}))


def test_summary_counts_hand_made_outcomes_and_keeps_faults_apart(tmp_path):
    for p in (1, 2):
        (tmp_path / f'pass{p}' / 'worker0').mkdir(parents=True)
    acting = {'dijkstra_rows': 12, 'bendyruler_rows': 0}
    make_flight(tmp_path, 1, 'a', 1, 'reach', 'close', 1, 'held', True, acting)
    make_flight(tmp_path, 1, 'b', 1, 'reach', 'close', 2, 'entered_threat', False, acting)
    make_flight(tmp_path, 1, 'c', 1, 'reach', 'close', 3, 'timed_out', False)
    make_flight(tmp_path, 1, 'd', 1, 'reach', 'wide', 201, 'held', True)
    make_flight(tmp_path, 1, 'e', 1, 'land', 'middle', 101, 'landed', True)
    make_flight(tmp_path, 2, 'a', 1, 'reach', 'close', 1, 'held', True, acting)
    make_flight(tmp_path, 2, 'b', 1, 'reach', 'close', 2, 'timed_out', False)
    make_flight(tmp_path, 2, 'd', 1, 'reach', 'wide', 201, 'held', True)
    # seed 3 of pass 2 faulted three times and never flew; seed 4 of pass 1 faulted once and then flew
    rows = [{'setting': 1, 'task': 'reach', 'band': 'close', 'seed': 3, 'attempt': a, 'status': 'fault',
             'error': 'PlannerFault: x'} for a in (1, 2, 3)]
    (tmp_path / 'pass2' / 'worker0' / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    make_flight(tmp_path, 1, 'f', 1, 'reach', 'close', 4, 'held', True)
    (tmp_path / 'pass1' / 'worker0' / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in (
        {'setting': 1, 'task': 'reach', 'band': 'close', 'seed': 4, 'attempt': 1, 'status': 'fault', 'error': 'x'},
        {'setting': 1, 'task': 'reach', 'band': 'close', 'seed': 4, 'attempt': 2, 'status': 'flown'})))
    s = summarise.summarise(tmp_path)
    close = s['cells']['pass1']['setting1']['reach']['close']
    assert (close['flown'], close['met_goal'], close['entered_threat']) == (4, 2, 1)
    assert close['other_end_reasons'] == {'timed_out': 1} and close['planner_acted'] == 2
    distant = s['cells']['pass1']['setting1']['reach']['distant']
    assert (distant['flown'], distant['met_goal'], distant['entered_threat']) == (1, 1, 0)
    assert s['cells']['pass1']['setting1']['land']['distant']['met_goal'] == 1
    everything = s['cells']['pass1']['setting1']['all']['all']
    assert (everything['flown'], everything['met_goal']) == (6, 4)
    two = s['cells']['pass2']['setting1']['reach']['close']
    assert (two['flown'], two['met_goal'], two['entered_threat']) == (2, 1, 0)      # the faulted seed is in no count
    assert s['faults'] == [{'pass': 2, 'setting': 1, 'task': 'reach', 'band': 'close', 'seed': 3, 'attempts': 3,
                            'error': 'PlannerFault: x'}]
    assert s['pass_agreement']['setting1'] == {'scenarios_flown_in_both_passes': 3, 'same_end_reason': 2}
    text = summarise.table(s)
    assert 'PlannerFault: x' in text and '2 of 3' in text


# 8. Nothing in the folder loads the model provider or reads the scoring-seeds variable.
def test_nothing_loads_a_model_provider_or_the_scoring_seeds_switch():
    provider, switch = 'claude' + '_provider', 'TELOHELM_ALLOW' + '_SCORING_SEEDS'
    assert f'ardupilot.{provider}' not in sys.modules
    for path in sorted(HERE.glob('*.py')):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text()
        assert provider not in text and switch not in text, path.name


def test_planner_rows_reports_an_unreadable_log_as_unknown(tmp_path):
    (tmp_path / 'logs').mkdir()
    (tmp_path / 'logs' / '00000001.BIN').write_bytes(b'\x00' * 10)
    with mock.patch.object(E.mavutil, 'mavlink_connection', side_effect=OSError('cut off')):
        rows = E.planner_rows(tmp_path)
    assert rows['dijkstra_rows'] is None and 'cut off' in rows['note']
    assert E.planner_rows(tmp_path / 'nothing')['dijkstra_rows'] is None


def test_planner_rows_counts_dijkstra_errors_and_their_codes(tmp_path):
    (tmp_path / 'logs').mkdir()
    (tmp_path / 'logs' / '00000001.BIN').write_bytes(b'x')
    rows = [SimpleNamespace(get_type=lambda: 'OADJ', State=2, Err=0), SimpleNamespace(get_type=lambda: 'OADJ', State=1, Err=3),
            SimpleNamespace(get_type=lambda: 'OADJ', State=1, Err=3), SimpleNamespace(get_type=lambda: 'OABR', Act=1),
            SimpleNamespace(get_type=lambda: 'OABR', Act=0), SimpleNamespace(get_type=lambda: 'OADJ', State=0, Err=0)]
    log = SimpleNamespace(recv_match=lambda type: rows.pop(0) if rows else None, close=lambda: None)
    with mock.patch.object(E.mavutil, 'mavlink_connection', return_value=log):
        got = E.planner_rows(tmp_path)
    assert (got['dijkstra_rows'], got['dijkstra_error_rows'], got['dijkstra_error_codes'], got['bendyruler_rows']) == (1, 2, {'3': 2}, 1)


def test_a_flown_flights_outcome_is_written_before_its_log_is_read(host, monkeypatch, tmp_path):
    out = tmp_path / 'planner-check-x'
    (out / 'defaults').mkdir(parents=True)
    # a flight whose episode ends at once; the log reader raises, which must not lose the outcome
    class Done(E.PlannerEpisode):
        def reset(self):
            self.sim = StandIn(self.folder, None, {})
            self.sim.episode = self
            self.end_reason = 'held'
            self.t = 1
        def outcome(self):
            return {'goal_met': True, 'end_reason': 'held', 'native_steps': []}
    monkeypatch.setattr(fly.E, 'PlannerEpisode', Done)
    monkeypatch.setattr(fly.E, 'planner_rows', lambda folder: (_ for _ in ()).throw(RuntimeError('log')))
    with pytest.raises(RuntimeError):
        fly.fly_one(fly.Item(1, 'reach', 'close', 4100001), out, 1)
    assert json.loads((out / 'flights' / 'reach-s1-threat-close-4100001' / 'outcome.json').read_text())['end_reason'] == 'held'


def test_evaluation_seeds_are_refused_until_the_protocol_is_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(scored, 'ROOT', tmp_path)           # use_protocol(3) now looks for PROTOCOL-3.md here
    try:
        assert fly.refuse_unless_frozen(True) == {'frozen_protocol': None}      # the shake-down needs no freeze
        with pytest.raises(SystemExit, match='fly only after the freeze'):
            fly.refuse_unless_frozen(False)
        with pytest.raises(SystemExit, match='fly only after the freeze'):
            fly.fly_worker(tmp_path / 'planner-check-t' / 'pass1' / 'worker0', 1, 0, pilot=False, speedup=1.0)
        (tmp_path / 'PROTOCOL-3.md').write_text('frozen')
        monkeypatch.setattr(scored, 'git_state', lambda: {'commit': 'abc'})
        got = fly.refuse_unless_frozen(False)
        assert got['frozen_protocol'] == 'PROTOCOL-3.md' and got['commit'] == 'abc' and len(got['frozen_protocol_sha256']) == 64
    finally:
        monkeypatch.undo()
        scored.use_protocol(3)


def test_the_freeze_guard_refuses_in_a_fresh_process_with_no_protocol_3_file():
    """A fresh process starts on protocol 1, whose PROTOCOL.md exists; the guard must look for PROTOCOL-3.md."""
    paper3 = HERE.parent
    if (paper3 / 'PROTOCOL-3.md').exists():
        pytest.skip('PROTOCOL-3.md exists: the freeze has happened, and this test is for the time before it')
    code = ('import planner_check.fly as f\n'
            'try:\n    f.refuse_unless_frozen(False)\nexcept SystemExit as e:\n    print("REFUSED", e)\nelse:\n    print("PASSED")\n')
    out = subprocess.run([sys.executable, '-B', '-c', code], cwd=paper3, capture_output=True, text=True, timeout=120)
    assert out.stdout.startswith('REFUSED') and 'PROTOCOL-3.md' in out.stdout, out.stdout + out.stderr


def test_out_must_be_inside_a_planner_check_folder(tmp_path):
    fly.refuse_out_outside_planner_check(tmp_path / 'runs' / 'planner-check-20261121' / 'pass1' / 'worker0')
    with pytest.raises(SystemExit, match='planner-check'):
        fly.refuse_out_outside_planner_check(tmp_path / 'runs' / 'scored-x-reach' / 'worker0')
    with pytest.raises(SystemExit):
        fly.fly_worker(tmp_path / 'elsewhere', 1, 0, pilot=True, speedup=1.0)
    assert not (tmp_path / 'elsewhere').exists()

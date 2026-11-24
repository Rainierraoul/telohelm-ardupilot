"""Zone entries counted again from ArduPilot's onboard logs, which hold the simulator's true position 400 times a second.

Exploratory, written after the results were read, for a referee's question. The judge checks the zone on the true
position once a second (Online Resource 1, S7), so a flight can cross the zone's edge between two checks and still be
scored clear. Every simulated flight also left ArduPilot's own log (logs/00000001.BIN in the flight's simulator folder,
kept in the simulator-log ZIPs of the deposit). Its SIM2 message records the simulator's true position, in metres north
(PN) and east (PE) of home, 400 times a second.

    python3 -I zone_entries_onboard_logs.py STUDY2_RUNS STUDY2_LOGS EXTRA_SAVED EXTRA_LOGS TAG SEEDS_3_JSON OUT_JSONL [STUDY1_RUNS]

STUDY2_RUNS holds Study 2's run roots scored-20261120-S-<task>/ and STUDY2_LOGS its ZIPs
study2-simulator-logs-scored-20261120-S-<task>.zip. EXTRA_SAVED holds the additions' run roots
extra-TAG-<task>/runs/extra-TAG-<task>/ and extra-TAG-all/runs/yard-TAG/, and EXTRA_LOGS their packed folders
extra-TAG-<task>/ and extra-TAG-all/ with the simulator-log ZIPs inside.

Which flights. For arms A to E, every unseen zone flight (24 a block) of each procedure the arm adopted, counted once for
each arm that adopted it, as in the rates of Online Resource 1, S7 and S19. A procedure's record and log are read from
Study 2's runs when Study 2 flew it, and otherwise from the additions' runs (this is how the rates were computed: six
Study 2 procedures were flown again beside arm E for the platform check, and those second flights are not used here).
Also the hand-written controller's 24 unseen zone flights at each task and margin, and, when STUDY1_RUNS (Study 1's run
folder runs/scored-2, with its simulator folders unzipped in place) is given, Study 1's 145 zone flights: the five of each
procedure for reach, reach3d, land and avoid.

For each flight:
  1. Read the log's SIM2 messages (TimeUS, PN, PE).
  2. Line up the log's clock with the record's. The record's native_steps give the true position the judge used
     (north_m, east_m) at sim_s seconds after the flight began. The offset between the clocks is the one at which the
     log's positions lie closest to those (smallest mean horizontal distance), searched on a 0.05 s grid and then on a
     0.001 s grid around the best point. The largest distance left at any check is reported for every flight, so a
     poor match would show.
  3. Each zone counts from the check at which it was switched on (the native step whose t is the zone's start in
     event_starts, or the flight's start when that is step 0) to the zone's end or the flight's last check, whichever
     came first. The log's smallest gap between the true position and the zone's edge over that window; negative
     means inside. The window opens at the check before the zone was switched on, by up to one decision's time, so it
     can only add entries.

A flight the judge scored as entering the zone ended at that check, so its log's deepest point is how far in it was when
it was stopped, which says nothing about how far it would have gone.

Writes one JSON line per flight to OUT_JSONL and prints the summary. Each line names its flight's record in `outcome`,
relative to the folder given for its `source` (record_path below), so the file names no folder of the machine it was
written on. Reads the records and the ZIPs and changes neither.
"""
import hashlib
import json
import math
import os
import re
import statistics
import sys
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from pymavlink import DFReader

TASKS = ('reach', 'reach3d', 'land')
BANDS = ('close', 'middle', 'wide')
MARGINS = (1, 2, 3, 4, 5)
SEEDS_SHA256 = '1d39a62cf7ee7d23076b2c2878162457d555a86cd965ab7d7e17a312b876a64c'
LOG = re.compile(r'(?:^|/)(?P<phase>(?:threat3|yard3)-[^/]+)/flights/simulators/(?P<flight>threat-[a-z]+-\d+)-\d+-\d+/'
                 r'logs/00000001\.BIN$')


def index_logs(zips):
    """(source, phase, flight) -> (zip path, member), refusing any flight with two logs."""
    out = {}
    for source, path in zips:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if '.set-aside/' in name:
                    continue
                m = LOG.search(name)
                if m:
                    key = (source, m['phase'], m['flight'])
                    assert key not in out, f'two logs for {key}'
                    out[key] = (str(path), name)
    return out


def read_sim2(zip_path, member):
    """The log's SIM2 messages, from a member of a ZIP, or from a file on disk when zip_path is None."""
    with tempfile.TemporaryDirectory() as tmp:
        if zip_path is None:
            f = Path(member)
        else:
            f = Path(tmp) / 'log.BIN'
            with zipfile.ZipFile(zip_path) as z:
                f.write_bytes(z.read(member))
        r = DFReader.DFReader_binary(str(f))
        T, N, E = [], [], []
        while True:
            m = r.recv_match(type='SIM2')
            if m is None:
                break
            T.append(m.TimeUS / 1e6)
            N.append(m.PN)
            E.append(m.PE)
    return np.array(T), np.array(N), np.array(E)


def align(T, N, E, ss, sn, se):
    """Clock offset at which the log's positions best match the record's; returns (offset, mean m, max m)."""
    def errors(offsets):
        i = np.clip(np.searchsorted(T, ss[None, :] + offsets[:, None]), 0, len(T) - 1)
        return np.hypot(N[i] - sn[None, :], E[i] - se[None, :])
    hi = T[-1] - ss[-1]
    coarse = np.arange(T[0], hi + 1e-9, 0.05)
    best = coarse[np.argmin(errors(coarse).mean(axis=1))]
    fine = np.arange(max(T[0], best - 0.06), min(hi, best + 0.06) + 1e-9, 0.001)
    err = errors(fine)
    k = int(np.argmin(err.mean(axis=1)))
    return float(fine[k]), float(err[k].mean()), float(err[k].max())


def measure(job):
    """One flight: the judge's verdict and closest gap from the record, and the log's smallest gap."""
    outcome_path, zip_path, member = job
    o = json.loads(Path(outcome_path).read_text())
    steps = o['native_steps']
    ss = np.array([s['sim_s'] for s in steps])
    sn = np.array([s['north_m'] for s in steps])
    se = np.array([s['east_m'] for s in steps])
    T, N, E = read_sim2(zip_path, member)
    off, mean_err, max_err = align(T, N, E, ss, sn, se)
    at = {s['t']: s['sim_s'] for s in steps}
    at[0] = 0.0
    gap = last = math.inf
    for i, e in enumerate(o['events']):
        if e[0] != 'threat':
            continue
        start = o['event_starts'].get(str(i), e[1])
        if isinstance(start, str) or start not in at:
            continue
        lo = off + at[start]
        end = start + e[2]
        hi = off + (at[end] if end in at else ss[-1])
        w = (T >= lo) & (T <= hi)
        if w.any():
            g = np.hypot(N[w] - e[3], E[w] - e[4]) - e[5]
            gap = min(gap, float(g.min()))
            last = min(last, float(g[-1]))
    return {'outcome': outcome_path, 'entered': o['end_reason'] == 'entered_threat', 'goal_met': o['goal_met'],
            'judge_gap_m': o['closest_threat_m'], 'log_gap_m': gap, 'log_gap_last_check_m': last, 'align_mean_m': mean_err,
            'align_max_m': max_err, 'log_samples': int(len(T))}


def record_path(row, runs, saved, study1=None):
    """The flight record a row of the output names. `outcome` is relative to STUDY2_RUNS for source s2, to EXTRA_SAVED
    for ex (arm E) and yard (the hand-written controller), and to STUDY1_RUNS for s1."""
    return {'s2': runs, 'ex': saved, 'yard': saved, 's1': study1}[row['source']] / row['outcome']


def main(runs, logs, saved, extra_logs, tag, seeds, out, study1=None):
    raw = seeds.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SEEDS_SHA256, 'not the frozen seed book'
    book = json.loads(raw)['threat_evaluation']
    zips = [('s2', logs / f'study2-simulator-logs-scored-20261120-S-{t}.zip') for t in TASKS]
    zips += [('ex', p) for t in TASKS for p in sorted((extra_logs / f'extra-{tag}-{t}').glob('*simulator-logs*.zip'))]
    zips += [('yard', p) for p in sorted((extra_logs / f'extra-{tag}-all').glob(f'*simulator-logs-yard-{tag}.zip'))]
    index = index_logs(zips)
    groups = {}          # group name -> list of flight keys, a key once per arm that adopted it
    jobs = {}            # flight key -> (outcome path, zip, member)
    for task in TASKS:
        s2 = runs / f'scored-20261120-S-{task}'
        ex = saved / f'extra-{tag}-{task}' / 'runs' / f'extra-{tag}-{task}'
        names = [f'threat-{band}-{seed}' for band in BANDS for seed in book[task][band]]
        for block in range(40):
            arms = json.loads((s2 / f'learn3-{task}-b{block}' / 'arms.json').read_text())['arms']
            arms['E'] = json.loads((ex / f'learnE-{task}-b{block}' / 'arms.json').read_text())['arms']['E']
            for a in 'ABCDE':
                if not arms[a]['adopted']:
                    continue
                phase = f'threat3-{task}-b{block}-{arms[a]["source_sha256"]}'
                source, root = ('s2', s2) if (s2 / phase).is_dir() else ('ex', ex)
                for name in names:
                    key = (source, phase, name)
                    jobs[key] = (str(root / phase / 'flights' / name / 'outcome.json'),) + index[key]
                    groups.setdefault(f'arm {a}', []).append(key)
        yard = saved / f'extra-{tag}-all' / 'runs' / f'yard-{tag}'
        for margin in MARGINS:
            phase = f'yard3-{task}-m{margin}'
            for name in names:
                key = ('yard', phase, name)
                jobs[key] = (str(yard / phase / 'flights' / name / 'outcome.json'),) + index[key]
                groups.setdefault(f'controller {task} {margin} m', []).append(key)
    if study1 is not None:
        # Study 1: each procedure's five zone flights for reach, reach3d, land and avoid, with the logs on disk.
        phases = [f'disturb-{t}-learned-b{b}-matched' for t in TASKS for b in range(8)]
        phases += [f'disturb-avoid-learned-{r}' for r in range(5)]
        for phase in phases:
            task = phase.split('-')[1]
            sims = study1 / phase / 'flights' / 'simulators'
            for record in sorted((study1 / phase / 'flights').glob('threat-*/outcome.json')):
                name = record.parent.name
                logs = [p for p in sims.glob(f'{name}-*/logs/00000001.BIN')
                        if re.fullmatch(rf'{re.escape(name)}-\d+-\d+', p.parts[-3])]
                assert len(logs) == 1, f'{phase} {name}: {len(logs)} logs'
                key = ('s1', phase, name)
                jobs[key] = (str(record), None, str(logs[0]))
                groups.setdefault(f'Study 1 {task}', []).append(key)
    keys = sorted(jobs)
    workers = max(1, (os.cpu_count() or 2) - 2)
    with ProcessPoolExecutor(workers) as pool:
        results = dict(zip(keys, pool.map(measure, [jobs[k] for k in keys], chunksize=8)))
    assert out.suffix == '.jsonl' and out.name != 'outcome.json', out
    # Each row names its flight's record relative to the folder given for its source (see relative_outcome), so the
    # file names no folder of the machine it was written on.
    bases = {'s2': runs, 'ex': saved, 'yard': saved, 's1': study1}
    with open(out, 'w') as f:
        for k in keys:
            row = {'source': k[0], 'phase': k[1], 'flight': k[2], **results[k]}
            row['outcome'] = Path(row['outcome']).relative_to(bases[k[0]]).as_posix()
            f.write(json.dumps(row) + '\n')

    every = list(results.values())
    stop = [abs(r['judge_gap_m'] - r['log_gap_last_check_m']) for r in every if r['entered']]
    T = max(stop)
    print(f'Flights read: {len(every)}; log samples per flight {min(r["log_samples"] for r in every)} to '
          f'{max(r["log_samples"] for r in every)}; largest distance between the log and the record at any check '
          f'{max(r["align_max_m"] for r in every):.3f} m (median of the flights\' largest '
          f'{statistics.median(r["align_max_m"] for r in every):.3f} m)')
    print(f'On the {len(stop)} flights the judge scored as entering, the largest difference between the judge\'s depth and '
          f'the log\'s at the check that stopped the flight: {T:.4f} m. This measured disagreement is the threshold T '
          f'below: a crossing shallower than T is within what the two measurements disagree by. Scored entries that the '
          f'log puts outside the zone: {sum(r["log_gap_m"] >= 0 for r in every if r["entered"])}, all within T: '
          + str(all(r['log_gap_m'] > -T for r in every if r['entered'] and r['log_gap_m'] >= 0)))
    unique = {k for ks in groups.values() for k in ks if k[0] != 's1' and k[0] != 'yard'}
    for depth, label in ((0.0, 'any depth'), (T, f'deeper than T')):
        n = sum(1 for k in unique if not results[k]['entered'] and results[k]['log_gap_m'] < -depth)
        print(f'Distinct Study 2 and arm E flights scored clear but inside the zone in the log, {label}: {n} of '
              f'{sum(1 for k in unique if not results[k]["entered"])} scored clear')
    print('Per group: flights; scored as entering; scored clear but inside the zone in the log at any depth and deeper '
          'than T, how many of those met the goal, and how deep; depth of the scored entries (judge at the check that '
          'stopped them, log at its deepest before the stop)')
    for g, ks in groups.items():
        rs = [results[k] for k in ks]
        entered = [r for r in rs if r['entered']]
        missed = [r for r in rs if not r['entered'] and r['log_gap_m'] < 0]
        beyond = [r for r in missed if r['log_gap_m'] < -T]
        depths = sorted(-r['log_gap_m'] for r in missed)
        line = (f'  {g}: {len(rs)} flights; scored as entering {len(entered)}; clear at the checks but inside in the '
                f'log {len(missed)} ({sum(r["goal_met"] for r in missed)} met the goal), deeper than T {len(beyond)} '
                f'({sum(r["goal_met"] for r in beyond)} met the goal)')
        if depths:
            line += f', depth median {statistics.median(depths):.2f} m, deepest {depths[-1]:.2f} m'
        if entered:
            line += (f'; scored entries\' depth median {statistics.median(-r["judge_gap_m"] for r in entered):.2f} m '
                     f'(log {statistics.median(-r["log_gap_m"] for r in entered):.2f} m), deepest '
                     f'{max(-r["judge_gap_m"] for r in entered):.2f} m (log {max(-r["log_gap_m"] for r in entered):.2f} m)')
        print(line)


if __name__ == '__main__':
    a = sys.argv[1:]
    main(Path(a[0]), Path(a[1]), Path(a[2]), Path(a[3]), a[4], Path(a[5]), Path(a[6]),
         Path(a[7]) if len(a) > 7 else None)

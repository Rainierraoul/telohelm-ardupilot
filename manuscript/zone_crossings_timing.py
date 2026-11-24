"""Where in the zone's window each crossing found by zone_entries_onboard_logs.py lies.

Exploratory, written after the results were read, to check that the crossings between checks are not artefacts of the
window's ends or of the clock alignment. For each distinct unseen zone flight of Study 2 and arm E that the judge scored
as clear and whose log puts the vehicle deeper than T inside the zone (T found as zone_entries_onboard_logs.py finds it),
the script reads the log again, aligns it as that script does, and prints how long after the window opened and before it
closed the deepest point came, how long the vehicle stayed deeper than T, and how far the deepest point was in time from
the nearest check.

    python3 -I zone_crossings_timing.py MANUSCRIPT_DIR ONBOARD_JSONL STUDY2_RUNS STUDY2_LOGS EXTRA_SAVED EXTRA_LOGS TAG

MANUSCRIPT_DIR is the folder that holds zone_entries_onboard_logs.py, whose functions it uses. The other folders are
those given to that script; each row of ONBOARD_JSONL names its flight's record relative to STUDY2_RUNS or EXTRA_SAVED.
Reads the records and the ZIPs and writes nothing.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, sys.argv[1])
import zone_entries_onboard_logs as Z  # noqa: E402

jsonl, runs, logs, saved, extra_logs, tag = (Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]),
                                             Path(sys.argv[6]), sys.argv[7])
rows = [json.loads(line) for line in jsonl.read_text().splitlines()]
T = max(abs(r['judge_gap_m'] - r['log_gap_last_check_m']) for r in rows if r['entered'])
seen, cross = set(), []
for r in rows:
    if r['source'] in ('s2', 'ex') and not r['entered'] and r['log_gap_m'] < -T and (r['phase'], r['flight']) not in seen:
        seen.add((r['phase'], r['flight']))
        cross.append(r)
zips = [('s2', logs / f'study2-simulator-logs-scored-20261120-S-{t}.zip') for t in Z.TASKS]
zips += [('ex', p) for t in Z.TASKS for p in sorted((extra_logs / f'extra-{tag}-{t}').glob('*simulator-logs*.zip'))]
index = Z.index_logs(zips)
out = []
for r in cross:
    zp, member = index[(r['source'], r['phase'], r['flight'])]
    o = json.loads(Z.record_path(r, runs, saved).read_text())
    steps = o['native_steps']
    ss = np.array([s['sim_s'] for s in steps])
    sn = np.array([s['north_m'] for s in steps])
    se = np.array([s['east_m'] for s in steps])
    Tt, N, E = Z.read_sim2(zp, member)
    off, _, _ = Z.align(Tt, N, E, ss, sn, se)
    at = {s['t']: s['sim_s'] for s in steps}
    at[0] = 0.0
    best = None
    for i, e in enumerate(o['events']):
        if e[0] != 'threat':
            continue
        start = o['event_starts'].get(str(i), e[1])
        if isinstance(start, str) or start not in at:
            continue
        lo = off + at[start]
        end = start + e[2]
        hi = off + (at[end] if end in at else ss[-1])
        w = (Tt >= lo) & (Tt <= hi)
        g = np.hypot(N[w] - e[3], E[w] - e[4]) - e[5]
        k = int(np.argmin(g))
        tk = Tt[w][k]
        inside = Tt[w][g < -T]
        checks = off + ss
        if best is None or g[k] < best[0]:
            best = (float(g[k]), float(tk - lo), float(hi - tk), float(inside.max() - inside.min()) if len(inside) else 0.0,
                    float(np.min(np.abs(checks - tk))))
    out.append(best)
    print(f"{-best[0]:.3f} m deep; {best[1]:.2f} s after the window opens, {best[2]:.2f} s before it closes; "
          f"deeper than T for {best[3]:.2f} s; {best[4]:.2f} s from the nearest check; {r['phase'][:28]} {r['flight']}")
a = np.array(out)
print(f'crossings {len(a)}; seconds after window opens: min {a[:, 1].min():.2f}; seconds before it closes: min '
      f'{a[:, 2].min():.2f}, under 0.5 s: {(a[:, 2] < 0.5).sum()}; time deeper than T: median {np.median(a[:, 3]):.2f} s, '
      f'max {a[:, 3].max():.2f} s; time from nearest check: median {np.median(a[:, 4]):.2f} s, min {a[:, 4].min():.2f} s')

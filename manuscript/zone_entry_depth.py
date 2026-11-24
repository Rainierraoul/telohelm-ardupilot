"""Depth of the zone entries of arms C and D in Study 2 (Online Resource 1, Table S7d).

Usage: python3 -I zone_entry_depth.py <study2-records.zip>

For each task and block, reads arms.json, takes the source hash of the procedure arm C (then arm D)
adopted, and reads that procedure's 24 held-out zone flights from
threat3-<task>-b<N>-<hash>/flights/threat-<band>-<seed>/outcome.json, leaving out attempts set aside
under the timing rule. A flight entered the zone if its end_reason is entered_threat; its depth is
-closest_threat_m, the distance inside the zone's edge at the step that ended the flight.
"""
import collections, json, statistics, sys, zipfile

Z = zipfile.ZipFile(sys.argv[1])
flights = collections.defaultdict(list)
for x in Z.namelist():
    if '.set-aside' in x or not x.endswith('outcome.json') or '/threat3-' not in x or '/flights/threat-' not in x:
        continue
    _, task, block, sha = x.split('/')[2].split('-', 3)
    flights[(task, block, sha)].append(x)
for arm in 'CD':
    flown, depths, bands = 0, [], collections.Counter()
    for task in ('reach', 'reach3d', 'land'):
        for n in range(40):
            a = json.loads(Z.read(f'runs/scored-20261120-S-{task}/learn3-{task}-b{n}/arms.json'))['arms'][arm]
            if not a['adopted']:
                continue
            fl = flights[(task, f'b{n}', a['source_sha256'])]
            assert len(fl) == 24, (task, n, len(fl))
            for path in fl:
                o = json.loads(Z.read(path))
                flown += 1
                if o['end_reason'] == 'entered_threat':
                    depths.append(-o['closest_threat_m'])
                    bands[path.split('/')[-2].split('-')[1]] += 1
    q = statistics.quantiles(depths, n=4)
    print(f"arm {arm}: {len(depths)} entries of {flown} flights; median {statistics.median(depths):.2f} m; "
          f"middle half {q[0]:.2f} to {q[2]:.2f} m; deepest {max(depths):.2f} m; deeper than 1 m {sum(d > 1 for d in depths)}; "
          f"close, middle, wide {bands['close']}, {bands['middle']}, {bands['wide']}")

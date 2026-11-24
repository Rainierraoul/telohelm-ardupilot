"""When did the zone switch on in Study 2's held-out zone flights? Tabulates event_starts and the event rule
for arm A's adopted procedures (and all arms), from the study2 records zip. Usage: python3 -I zone_start_times.py <zip>"""
import collections, json, sys, zipfile
Z = zipfile.ZipFile(sys.argv[1])
names = Z.namelist()
adopt = collections.defaultdict(set)
for p in names:
    if p.endswith('/arms.json') and '.set-aside' not in p:
        b = json.loads(Z.read(p))
        for arm, a in b['arms'].items():
            if a['adopted']:
                adopt[(b['task'], b['block'], a['source_sha256'])].add(arm)
starts = {k: collections.Counter() for k in 'ABCD'}
rules = collections.Counter()
for p in names:
    if '.set-aside' in p or not p.endswith('outcome.json') or '/threat3-' not in p or '/flights/threat-' not in p:
        continue
    _, task, block, sha = p.split('/')[2].split('-', 3)
    key = (task, int(block[1:]), sha)
    if key not in adopt:
        continue
    o = json.loads(Z.read(p))
    rules[o['events'][0][1]] += 1
    t = o['event_starts'].get('0')
    for arm in adopt[key]:
        starts[arm][t] += 1
print('rules', dict(rules))
for arm in 'ABCD':
    print(arm, sorted(starts[arm].items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))

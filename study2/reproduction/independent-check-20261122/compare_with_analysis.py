"""Compares the independent check's RESULT.json with the scored analysis's analysis.json, by the rule fixed in ruling 105,
point 4, before any outcome was read: each point estimate equal, each section 6.4 key the same, each interval end within 0.01.
Written by the coordinating session after the independent check had finished. It computes no statistic.

  python3 -I compare_with_analysis.py RESULT.json ANALYSIS.json > COMPARISON.md
"""
import hashlib, json, sys
res_path, ana_path = sys.argv[1], sys.argv[2]
R = json.load(open(res_path)); A = json.load(open(ana_path))
TOL_EST, TOL_END = 1e-9, 0.01
rows = []
def key_of(a): return a['classification']['class']
def add(label, designation, r, a):
    d_est = abs(r['estimate'] - a['estimate'])
    ends = [abs(r['ci95'][i] - a['ci95'][i]) for i in (0, 1)] + [abs(r['ci90'][i] - a['ci90'][i]) for i in (0, 1)]
    same_key = r['key'] == key_of(a)
    extra = (r['four_way_table'].get('useful_gain'), r['four_way_table'].get('useful_loss')) == \
            (a['classification'].get('useful_gain'), a['classification'].get('useful_loss'))
    ok = d_est <= TOL_EST and same_key and extra and max(ends) <= TOL_END
    rows.append((label, designation, r, a, d_est, max(ends), same_key and extra, ok))
for step in ('C-B', 'B-A', 'D-C'):
    add(f'pooled {step}', 'primary', R['pooled_steps'][step], A['primary'][f'pooled:{step}'])
for task in ('reach', 'reach3d', 'land'):
    for band, akey in (('close', 'close'), ('distant', 'middle-wide')):
        add(f'{task} D-A {band}', 'secondary (RQ4)', R['rq4'][task][band], A['secondary_intervals'][f'{task}:D-A:{akey}'])
for step in ('C-B', 'B-A', 'D-C'):
    for task in ('reach', 'reach3d', 'land'):
        add(f'{task} {step}', 'per-task step', R['per_task_steps'][step][task], A['primary'][f'pooled:{step}']['per_task'][task])
def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
def f(x): return f'{x:+.6f}'
print('# The independent check compared with the scored analysis\n')
print(f'Independent result: `{res_path.split("/")[-1]}`, SHA-256 {sha(res_path)}.')
print(f'Scored analysis: `analysis.json`, SHA-256 {sha(ana_path)}.\n')
print('The rule for a match, fixed before any outcome was read: point estimates equal (to 1e-9), the section 6.4 key and the')
print('larger-than-the-margin label the same, and each end of the 95% and 90% intervals within 0.01.\n')
print('| Contrast | Kind | Estimate, independent | Estimate, analysis | 95% interval, independent | 95% interval, analysis | 90% interval, independent | 90% interval, analysis | Key, both | Largest difference of an interval end | Match |')
print('|---|---|---:|---:|---|---|---|---|---|---:|---|')
for label, des, r, a, d_est, d_end, same, ok in rows:
    print(f"| {label} | {des} | {f(r['estimate'])} | {f(a['estimate'])} | {f(r['ci95'][0])}, {f(r['ci95'][1])} | {f(a['ci95'][0])}, {f(a['ci95'][1])} | "
          f"{f(r['ci90'][0])}, {f(r['ci90'][1])} | {f(a['ci90'][0])}, {f(a['ci90'][1])} | {r['key'] if same else r['key'] + ' / ' + key_of(a)} | {d_end:.6f} | {'yes' if ok else 'NO'} |")
nine = [x for x in rows if x[1] != 'per-task step']
print(f"\nThe nine intervals of the protocol (three primary, six for RQ4): {sum(x[7] for x in nine)} of {len(nine)} match.")
print(f"The nine per-task steps beside them: {sum(x[7] for x in rows if x[1] == 'per-task step')} of 9 match.")
print(f"Largest difference of any point estimate: {max(x[4] for x in rows):.2e}. Largest difference of any interval end: {max(x[5] for x in rows):.6f}.")
# pooled-step reading: task dependence and per-task signs
for step in ('C-B', 'B-A', 'D-C'):
    a = A['pooled_ladder_steps'][step]
    print(f"Pooled {step}: analysis task_dependent={a.get('task_dependent')}, answer status: {a.get('answer', {}).get('status') if isinstance(a.get('answer'), dict) else a.get('answer')}.")
# arm means and adoption
bad = 0
for task in ('reach', 'reach3d', 'land'):
    for arm in 'ABCD':
        r = R['arm_means'][task][arm]
        if abs(r['mean'] - A['tasks'][task]['arm_means'][arm]) > 1e-9 or r['blocks_adopted'] != A['tasks'][task]['adoption'][arm]['adopted']: bad += 1
print(f"Arm means and blocks adopted, 12 task-arm pairs: {12 - bad} of 12 equal.")

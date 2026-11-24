"""Two checks on manuscript/repair_changes/rules.py (read-only import by path):
1. Of the repairs whose distance is 'set from the target's distance to the zone', how many give the same value
   at every Study 2 gap (3 to 21 m), so the tie never acts on a Study 2 layout?
2. How many repairs still keep a distance at least as large as the close gap (target on or inside their circle)?
3. Among the 83 compared pairs, how many first candidates used each method, and what was recorded for field ones.
Usage: python3 -I repair_rule_checks.py <repair_changes dir>"""
import csv, importlib.util, json, sys, os
D = sys.argv[1]
spec = importlib.util.spec_from_file_location('rules_ro', os.path.join(D, 'rules.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
R = m.R
rows = [r for r in csv.DictReader(open(os.path.join(D, 'classification.csv'))) if r['excluded'] == '0']
keys = [r['block'] for r in rows]
gaps = [3.0 + 0.1 * i for i in range(11)] + [9 + 0.1 * i for i in range(21)] + [19 + 0.1 * i for i in range(21)]
tt = [k for k in keys if R[k][0] == 'target']
never = [k for k in tt if len({round(R[k][1](g), 6) for g in gaps}) == 1]
close_only = [k for k in tt if len({round(R[k][1](g), 6) for g in [3.0 + 0.1 * i for i in range(11)]}) > 1]
print('target-tied', len(tt), '| same value at every Study 2 gap:', len(never), never)
print('target-tied whose value varies within the close band 3-4 m:', len(close_only))
for g in (3.0, 3.5, 4.0):
    inside = [k for k in keys if R[k][1](g) >= g]
    print(f'gap {g}: repairs keeping >= gap (target on/inside circle): {len(inside)}', inside)
k2 = [r['block'] for r in rows if r['K2'] == '1']
print('K2 count', len(k2), '| K2 types', {t: sum(1 for k in k2 if R[k][0] == t) for t in ('target','switch','fixed','vehicle','speed')})
print('c0 methods', {mm: sum(1 for r in rows if r['c0_method'] == mm) for mm in sorted({r['c0_method'] for r in rows})})

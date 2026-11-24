"""Extract c0 and arm C's adopted source for given blocks from the Study 2 records zip, as text files only.
Usage: python3 -I extract_pairs.py <zip> <outdir> task-bN ..."""
import json, sys, zipfile, os
Z = zipfile.ZipFile(sys.argv[1]); out = sys.argv[2]
names = set(Z.namelist())
for key in sys.argv[3:]:
    task, b = key.split('-b')
    base = f'runs/scored-20261120-S-{task}/learn3-{task}-b{b}'
    arms = json.loads(Z.read(base + '/arms.json'))['arms']
    cid = arms['C']['candidate_id']
    for c in ('c0', cid):
        p = f'{base}/candidates/{c}/source.py'
        if p not in names:
            print('missing', p); continue
        dst = os.path.join(out, f'{key}-{c}.py.txt')
        open(dst, 'wb').write(Z.read(p))
        print(key, c, len(Z.read(p)))

import json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules import R
B=os.path.dirname(os.path.abspath(__file__))
recs=[json.loads(l) for l in open(os.path.join(B,'records.jsonl'))]
rows={f"{r['task']}-b{r['N']}":r for r in json.load(open(os.path.join(B,'blocks.json')))}
task=lambda k:k.split('-')[0]
inc=[r for r in recs if not r.get('excluded')]
print('pairs',len(recs),'classified',len(inc))
K=['K1','K2','K3','K4','K5','K6','K7','K8','K9','K10']
for k in K:
    c=Counter(task(r['k']) for r in inc if k in r['kinds'])
    print(k, sum(c.values()), dict(c))
print('by task n', Counter(task(r['k']) for r in inc))
# judgement
j=[(r['k'],r.get('judge')) for r in inc if r.get('judge')]
print('judgement pairs',len(j)); [print(' ',x) for x in j]
# methods
print('c0 method',Counter(r['m0'] for r in inc)); print('rep method',Counter(r['m1'] for r in inc))
print('method pairs',Counter((r['m0'],r['m1']) for r in inc).most_common())
# keep-outs
k0=[r['keep0'] for r in inc]
print('c0 keep: n',len(k0),'min',min(k0),'max',max(k0),Counter(k0).most_common())
for t in ['reach','reach3d','land']:
    v=[r['keep0'] for r in inc if task(r['k'])==t]; print(' ',t,min(v),max(v),sorted(Counter(v).items()))
typ=Counter(R[r['k']][0] for r in inc); print('repair keep type',typ)
print('repair keep type by task',{t:dict(Counter(R[r['k']][0] for r in inc if task(r['k'])==t)) for t in ['reach','reach3d','land']})
for g in (3.0,4.0,9.0,11.0,19.0,21.0):
    v=[R[r['k']][1](g) for r in inc]
    print('gap',g,'repair keep min %.2f max %.2f median %.2f'%(min(v),max(v),sorted(v)[len(v)//2]))
# K1 check vs numbers at close gap
for r in inc:
    k1=R[r['k']][1](3.5) < r['keep0']
    if k1 != ('K1' in r['kinds']): print('K1 mismatch',r['k'],r['keep0'],R[r['k']][1](3.5),r['kinds'])
# fixed values
fx=[R[r['k']][1](0) for r in inc if R[r['k']][0] in ('fixed','vehicle','speed','switch')]
print('non-target-tied repair keep values',sorted(fx))
tt=[r for r in inc if R[r['k']][0]=='target']
caps=[R[r['k']][1](30) for r in tt]; print('target-tied caps (value when target is far)',sorted(caps))
print('target-tied value at gap 3',sorted(round(R[r['k']][1](3),2) for r in tt))
print('target-tied value at gap 4',sorted(round(R[r['k']][1](4),2) for r in tt))
# shrink ratio
print('c0 keep minus repair keep at gap 3.5: ', sorted(round(r['keep0']-R[r['k']][1](3.5),1) for r in inc))
# c0 failures
lay=['close','middle','wide']
pat=Counter(); per=defaultdict(Counter); bytask=defaultdict(Counter)
for r in recs:
    row=rows[r['k']]; t0=[t for t in row['trials'] if t['cid']=='c0'][0]
    if not t0['ends']:
        pat['never flew (format refused)']+=1; continue
    ends=t0['ends']; pat[tuple(ends)]+=1
    for L,e in zip(lay,ends): per[L][e]+=1
    bytask[task(r['k'])][tuple(ends)]+=1
print('c0 end patterns'); [print(' ',p,c) for p,c in pat.most_common()]
print('per layout',{L:dict(per[L]) for L in lay})
for t in bytask: print(t,dict(bytask[t]))
# failed layouts
fl=Counter()
for r in recs:
    row=rows[r['k']]; t0=[t for t in row['trials'] if t['cid']=='c0'][0]
    if t0['ends']:
        bad=tuple(L for L,e in zip(lay,t0['ends']) if e not in ('held','landed'))
        fl[bad]+=1
print('failed layouts',fl.most_common())
# which failure types
ty=Counter()
for r in recs:
    row=rows[r['k']]; t0=[t for t in row['trials'] if t['cid']=='c0'][0]
    s=set(e for e in t0['ends'] if e not in ('held','landed'))
    ty[tuple(sorted(s))]+=1
print('c0 failure-reason sets',ty.most_common())
# kinds per pair
print('kinds per pair',Counter(len(r['kinds']) for r in inc))

"""Read Dijkstra's planner rows and the vehicle's position from the onboard logs of the planner check's
Dijkstra flights (settings 1 and 2). Reads only; writes one JSON line per flight to stdout."""
import glob, json, os, sys
from pymavlink import mavutil
root = sys.argv[1]
for worker in sorted(glob.glob(f'{root}/pass*/worker*')):
    rows = [json.loads(l) for l in open(f'{worker}/results.jsonl') if l.strip()]
    sims = sorted(os.listdir(f'{worker}/simulators'), key=lambda s: int(s.rsplit('-', 1)[1]))
    flown = [r for r in rows]
    if len(sims) != len(flown):
        print(json.dumps({'worker': worker, 'error': f'{len(sims)} simulators, {len(flown)} rows'})); continue
    for r, sim in zip(flown, sims):
        if r['setting'] not in (1, 2):
            continue
        ep = r['name'].split('-', 2)[2]
        out = {'pass': r['pass'], 'worker': r['worker'], 'name': r['name'], 'sim': sim, 'episode_match': sim.startswith(ep)}
        logs = sorted(glob.glob(f'{worker}/simulators/{sim}/logs/*.BIN'))
        if not logs:
            out['error'] = 'no log'; print(json.dumps(out)); continue
        m = mavutil.mavlink_connection(logs[-1])
        oadj, pos, fence, msgs = [], [], [], []
        while (x := m.recv_match(type=['OADJ', 'POS', 'MSG', 'ORGN'])) is not None:
            d = x.to_dict(); t = d.get('TimeUS')
            if x.get_type() == 'OADJ':
                oadj.append(d)
            elif x.get_type() == 'POS':
                pos.append([t, d['Lat'], d['Lng']])
            elif x.get_type() == 'MSG':
                msgs.append([t, d.get('Message')])
            else:
                fence.append(d)
        out.update(oadj=oadj, pos=pos[::5], msgs=[mm for mm in msgs if any(k in str(mm[1]) for k in ('ence', 'OA', 'ijkstra', 'Path', 'path'))], origin=fence[:1])
        print(json.dumps(out, default=str))

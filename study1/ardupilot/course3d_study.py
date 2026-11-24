"""Measure how well the learned reach3d procedure generalises to unseen, certified 3D building courses.

The 3D counterpart of course_study.py (PAPER-DRAFT.md, 5.1). The reach3d procedure, learned only to reach and hold a
single 3D point, is flown with no model calls through many building courses it never saw, each certified flyable first.
Reports completion, gates passed, failures and a repeatability check, with denominators.

Run from paper3/ (when SITL is free):
  .venv/bin/python -m ardupilot.course3d_study --from-run runs/reach3d-demo --seeds 600000 600020 \
      --repeat-seeds 600000 600004 --repeats 3 --instance 4 --out runs/course3d-study-1
"""
from __future__ import annotations
import argparse, json, time
from collections import Counter
from pathlib import Path
from . import battle, course3d as C3
from .course3d_run import fly_course


def _write(out, rows, args, started, repeat):
    flown=[r for r in rows if r.get('certified')]
    completed=sum(r.get('completed',False) for r in flown)
    gp=sum(r.get('gates_passed',0) for r in flown); gt=sum(r.get('gates',0) for r in flown)
    (out/'rows.json').write_text(json.dumps(rows,indent=1))
    (out/'summary.json').write_text(json.dumps({
        'scope':'development system, held-out 3D building courses; PAPER-DRAFT.md 5.1',
        'from_run':str(args.from_run),'seed_range':[args.seeds[0],args.seeds[1]],
        'seeds_tried':args.seeds[1]-args.seeds[0],'certified':len(flown),
        'completed':completed,'completion_rate':round(completed/len(flown),3) if flown else None,
        'gates_passed':gp,'gates_total':gt,'gate_rate':round(gp/gt,3) if gt else None,
        'gate_radius_m':args.gate_radius,
        'model_calls_total':sum(r.get('model_calls',0) for r in flown),   # the runner has no model; zero by construction
        'control_steps':sum(r.get('steps') or 0 for r in flown),
        'steps_without_procedure':sum(r.get('steps_without_procedure') or 0 for r in flown),
        'courses_with_wind':sum(1 for r in flown if (r.get('wind_ms') or 0)>0),
        'end_reasons':dict(Counter(r.get('end_reason') for r in flown)),
        'repeatability':repeat,'elapsed_seconds':round(time.monotonic()-started)},indent=1))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--from-run',type=Path,required=True)
    p.add_argument('--seeds',nargs=2,type=int,required=True,metavar=('LO','HI'))
    p.add_argument('--repeat-seeds',nargs=2,type=int,metavar=('LO','HI'))
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--gate-radius',type=float,default=C3.GATE_RADIUS_M)
    p.add_argument('--speedup',type=float,default=10.0)
    p.add_argument('--instance',type=int,default=4)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    out=Path(args.out).resolve()
    if out.exists(): raise FileExistsError('use a new output directory')
    out.mkdir(parents=True)
    source=battle.adopted_source(args.from_run); started=time.monotonic(); rows=[]
    lo,hi=args.seeds
    for seed in range(lo,hi):
        c=C3.generate(seed, gate_radius=args.gate_radius); cert=C3.certify(c)
        if not cert['certified']:
            rows.append({'seed':seed,'certified':False,'reason':cert['reason']}); continue
        rec=fly_course(c,source,str(args.from_run),out/f'seed-{seed}',speedup=args.speedup,instance=args.instance)
        rows.append({'seed':seed,'certified':True,'completed':rec['completed'],'gates':rec['gates'],
                     'gates_passed':rec['gates_passed'],'end_reason':rec['end_reason'],
                     'model_calls':rec['provenance']['model_calls'],
                     'steps':rec['provenance'].get('control_steps'),
                     'steps_without_procedure':rec['provenance'].get('steps_without_procedure'),
                     'wind_ms':c.wind_ms,'gate_radius_m':args.gate_radius})
        done=[r for r in rows if r.get('certified')]
        print(f"seed {seed}: {'completed' if rec['completed'] else rec['end_reason']} "
              f"({rec['gates_passed']}/{rec['gates']}); running {sum(r.get('completed',False) for r in done)}/{len(done)}",flush=True)
        _write(out,rows,args,started,None)
    repeat=None
    if args.repeat_seeds:
        rlo,rhi=args.repeat_seeds; repeat=[]
        for seed in range(rlo,rhi):
            c=C3.generate(seed, gate_radius=args.gate_radius)
            if not C3.certify(c)['certified']: continue
            endings=[fly_course(c,source,str(args.from_run),out/f'repeat-{seed}-{k}',speedup=args.speedup,
                                instance=args.instance)['end_reason'] for k in range(args.repeats)]
            agree=max(Counter(endings).values())
            repeat.append({'seed':seed,'endings':endings,'agreement':f'{agree}/{len(endings)}'})
            print(f"repeat {seed}: {endings} agree {agree}/{len(endings)}",flush=True)
    _write(out,rows,args,started,repeat)
    return 0


if __name__=='__main__':
    raise SystemExit(main())

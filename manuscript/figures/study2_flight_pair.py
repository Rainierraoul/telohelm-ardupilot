"""Figure 4: one unseen zone flight flown twice, by a block's first candidate and by the repair arm C adopted.

The pair is fixed by a rule and not chosen. The block is the lowest-numbered reach block in which arm C adopted a
repair. The flight is the close-band unseen zone flight in that block with the lowest seed. The rule gives block 0
and flight threat-close-3100001, and the two records it leads to are named below with their SHA-256.

Each panel is seen from above: home, the zone, the target with its goal circle, the flown path, the point where the
zone switched on and the point where the flight ended. A path joins the simulator's true positions, one a second,
with straight lines. Positions are metres north and east of home, so home is the origin; the first recorded position
is one second into the flight.

A plain run reads the two outcome files and nothing else, refuses a file whose hash differs from the one below, and
prints the paths, the hashes and how each flight ended. Nothing is computed beyond reading the records.

  .venv/bin/python -I manuscript/figures/study2_flight_pair.py [RUNS_ROOT] [--out FILE.svg]

With --check-rule the script draws nothing. It applies the rule to the blocks' arms.json files and the manifests of
their unseen flights, prints what it finds block by block, and fails if the result is not the pair named below.

  .venv/bin/python -I manuscript/figures/study2_flight_pair.py [RUNS_ROOT] --check-rule
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

DEFAULT_ROOT = Path('/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-20261120-S-extract/data/runs')
RUN, TASK, BLOCK, FLIGHT = 'scored-20261120-S-reach', 'reach', 0, 'threat-close-3100001'
# (what flew, the hash of its source, which names its folder of unseen flights, and the hash of the outcome file)
FIRST = ('first candidate', '125734dec34bbe51bebd7c297d5298a4e5423e8c3bcb0e1e78c8d33f5b734afe',
         'cdc1f8739c8791872fd36a6090ed2cbede2f67bf83fc9d254275deafd7b2c62b')
REPAIR = ('repair adopted by arm C', '1385255ebd59fbc14d91484a8acc8dbaf31c6eaec0f85a3e034147ffa12cee04',
          'eaa9437799a7bfb8a51b287127dfcfebb7244ab15dcec1723a19e0d75ed919ff')

INK, MUTED, SURFACE, ZONE = '#0b0b0b', '#52514e', '#ffffff', '#e4e3df'   # ink and greys of the other figures
PATH = {FIRST[0]: '#2a78d6', REPAIR[0]: '#eb6834'}   # categorical slots 1 and 2, as in the other figures
ENDED = {'timed_out': 'time ran out', 'held': 'goal met', 'entered_threat': 'entered the zone'}

# Page geometry, in inches. The figure is 174 mm wide, the two-column width of the journal, and is saved at that
# size, so the type prints at the sizes set here (7 pt and above).
WIDTH = 174 / 25.4
LEFT, BETWEEN, RIGHT, TOP, BOTTOM = 0.47, 0.14, 0.06, 0.26, 0.42
SMALL, BODY, LETTER = 7.0, 7.5, 8.5
PAD_M, ROUND_M = 4.0, 5.0     # room around everything drawn, and the step the axis limits are rounded out to


def outcome_file(root: Path, source_sha256: str) -> Path:
    return root / RUN / f'threat3-{TASK}-b{BLOCK}-{source_sha256}' / 'flights' / FLIGHT / 'outcome.json'


def load(root: Path) -> dict:
    """The two records, each checked against its hash, with the checks that they are one flight flown twice."""
    recs = {}
    for name, source, expected in (FIRST, REPAIR):
        path = outcome_file(root, source)
        raw = path.read_bytes()
        got = hashlib.sha256(raw).hexdigest()
        print(f'{name}: {path}\n  sha256 {got}')
        assert got == expected, f'{path} is not the file the rule selected (expected sha256 {expected})'
        recs[name] = json.loads(raw)
    first, repair = recs[FIRST[0]], recs[REPAIR[0]]
    for field in ('task', 'goal', 'events', 'event_starts'):
        assert first[field] == repair[field], f'the two flights differ in {field}'
    assert first['task'] == TASK and len(first['events']) == 1 and first['events'][0][0] == 'threat', first['events']
    on = first['event_starts']['0']
    for name, rec in recs.items():
        steps = rec['native_steps']
        assert [s['t'] for s in steps] == list(range(1, len(steps) + 1)), f'{name}: a second is missing'
        assert len(steps) == rec['ended_at'], name
        # The zone switches on at the start of the step after second `on`, so the row at `on` is where the drone
        # was, and the next row is the first with the zone active.
        assert steps[on - 1]['threats'] == 0 and steps[on]['threats'] == 1, f'{name}: zone start does not match'
        assert rec['end_reason'] in ENDED, rec['end_reason']
    return recs


def report(recs: dict) -> None:
    rec = recs[FIRST[0]]
    _, _, _, north, east, radius = rec['events'][0]
    goal, on = rec['goal'], rec['event_starts']['0']
    at = rec['native_steps'][on - 1]
    print(f'layout, the same in both files: zone centre {north} m north and {east} m east of home, radius {radius} m; '
          f"target {goal['target_north_m']!r} m north and {goal['target_east_m']!r} m east; "
          f"goal circle {goal['radius_m']} m, to be held for {goal['hold_s']} s within {goal['time_limit_s']:.0f} s")
    print(f"the zone switched on at second {on}, with the drone {at['north_m']} m north and {at['east_m']} m east")
    for name, rec in recs.items():
        last = rec['native_steps'][-1]
        print(f"{name}: end_reason {rec['end_reason']}, ended_at {rec['ended_at']} s, goal_met {rec['goal_met']}, "
              f"closest_threat_m {rec['closest_threat_m']}, {len(rec['native_steps'])} positions, "
              f"last at {last['north_m']} m north and {last['east_m']} m east")


def limits(recs: dict):
    """Axis limits that hold everything drawn in either panel, rounded outward. East, then north."""
    rec = recs[FIRST[0]]
    _, _, _, zn, ze, zr = rec['events'][0]
    g = rec['goal']
    east = [0.0, ze - zr, ze + zr, g['target_east_m'] - g['radius_m'], g['target_east_m'] + g['radius_m']]
    north = [0.0, zn - zr, zn + zr, g['target_north_m'] - g['radius_m'], g['target_north_m'] + g['radius_m']]
    for r in recs.values():
        east += [s['east_m'] for s in r['native_steps']]
        north += [s['north_m'] for s in r['native_steps']]
    def out(values):
        return (math.floor((min(values) - PAD_M) / ROUND_M) * ROUND_M,
                math.ceil((max(values) + PAD_M) / ROUND_M) * ROUND_M)
    return out(east), out(north)


def note(ax, text, xy, xytext, ha='center', va='center'):
    """A label in the plot's own metres, joined to what it names by a thin line."""
    ax.annotate(text, xy=xy, xytext=xytext, ha=ha, va=va, fontsize=SMALL, color=INK, zorder=7,
                arrowprops={'arrowstyle': '-', 'color': MUTED, 'lw': 0.6, 'shrinkA': 1.5, 'shrinkB': 3.5})


def draw(ax, name: str, rec: dict) -> None:
    _, _, _, zn, ze, zr = rec['events'][0]
    g, on, steps = rec['goal'], rec['event_starts']['0'], rec['native_steps']
    tn, te = g['target_north_m'], g['target_east_m']
    colour = PATH[name]
    ax.add_patch(Circle((ze, zn), zr, facecolor=ZONE, edgecolor=MUTED, lw=0.8, zorder=1))
    ax.text(ze, zn, 'zone', ha='center', va='center', fontsize=SMALL, color=INK, zorder=2)
    ax.add_patch(Circle((te, tn), g['radius_m'], fill=False, edgecolor=INK, lw=0.8, zorder=5))
    ax.plot([te], [tn], marker='+', ms=3.6, mew=0.8, color=INK, ls='', zorder=2)   # under the path
    ax.plot([s['east_m'] for s in steps], [s['north_m'] for s in steps], color=colour, lw=1.1, marker='o', ms=1.9,
            zorder=3)
    ax.plot([0], [0], marker='s', ms=4.4, color=INK, ls='', zorder=4)
    at, last = steps[on - 1], steps[-1]
    ax.plot([at['east_m']], [at['north_m']], marker='o', ms=4.8, markerfacecolor=SURFACE, markeredgecolor=INK,
            mew=0.9, ls='', zorder=6)
    ax.plot([last['east_m']], [last['north_m']], marker='o', ms=4.8, markerfacecolor=colour, markeredgecolor=INK,
            mew=0.9, ls='', zorder=4)
    # Where the labels sit, in metres, was set for this layout. The hashes above pin the layout, so a run that
    # gets this far draws the same picture.
    ax.text(0, 2.6, 'home', ha='center', va='bottom', fontsize=SMALL, color=INK)
    note(ax, f'zone switched on ({on} s)', (at['east_m'], at['north_m']), (-17.5, -2.4))
    note(ax, f"target and its\n{g['radius_m']:.0f} m goal circle", (te, tn - g['radius_m']), (-53.5, -0.6))
    ended = f"{ENDED[rec['end_reason']]} ({rec['ended_at']} s)"
    if rec['goal_met']:
        note(ax, ended, (te - g['radius_m'], tn), (te - 7.5, tn + 1.5), ha='right')
    else:
        note(ax, ended, (last['east_m'], last['north_m']), (last['east_m'], 46.0))


def check_rule(root: Path) -> None:
    """Apply the selection rule to the records and compare its result with the pair this script draws."""
    run = root / RUN
    blocks = sorted(int(m[1]) for d in run.iterdir() if (m := re.fullmatch(rf'learn3-{TASK}-b(\d+)', d.name)))
    print(f'{len(blocks)} {TASK} blocks, {blocks[0]} to {blocks[-1]}')
    for b in blocks:
        arm_c = json.loads((run / f'learn3-{TASK}-b{b}' / 'arms.json').read_text())['arms']['C']
        repaired = bool(arm_c['adopted']) and arm_c['candidate_id'] != 'c0'
        print(f"block {b}: arm C adopted {arm_c['adopted']}, candidate {arm_c['candidate_id']}")
        if not repaired:
            continue
        assert re.fullmatch(r'rC\d', arm_c['candidate_id']), arm_c['candidate_id']
        folders = sorted(run.glob(f'threat3-{TASK}-b{b}-*'))
        of_c0 = [d for d in folders if json.loads((d / 'manifest.json').read_text())['args'].get('includes_c0')]
        if len(of_c0) != 1:
            print(f'block {b}: the first candidate has no unseen flights here, so the rule moves to the next block')
            continue
        c0 = of_c0[0].name.rsplit('-', 1)[1]
        seeds = sorted(int(m[1]) for d in (of_c0[0] / 'flights').iterdir()
                       if (m := re.fullmatch(r'threat-close-(\d+)', d.name)))
        flight = f'threat-close-{seeds[0]}'
        print(f'block {b} is the lowest-numbered block in which arm C adopted a repair\n'
              f'  first candidate, source sha256 {c0}\n  repair, source sha256 {arm_c["source_sha256"]}\n'
              f'  close-band unseen zone flights: seeds {seeds}; the lowest is {flight}')
        assert (b, flight, c0, arm_c['source_sha256']) == (BLOCK, FLIGHT, FIRST[1], REPAIR[1]), 'not the pair drawn'
        for _, source, _ in (FIRST, REPAIR):
            assert outcome_file(root, source).is_file(), outcome_file(root, source)
        print('this is the pair the script draws')
        return
    raise SystemExit('the rule selected no block')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('root', type=Path, nargs='?', default=DEFAULT_ROOT)
    p.add_argument('--out', type=Path, default=Path(__file__).with_name('study2-flight-pair.svg'))
    p.add_argument('--check-rule', action='store_true', help='apply the selection rule and draw nothing')
    a = p.parse_args(argv)
    if a.check_rule:
        return check_rule(a.root)
    recs = load(a.root)
    report(recs)

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'pdf.fonttype': 42, 'svg.hashsalt': 'paper3-study2-flight-pair'})
    (e0, e1), (n0, n1) = limits(recs)
    plot_w = (WIDTH - LEFT - BETWEEN - RIGHT) / 2
    plot_h = plot_w * (n1 - n0) / (e1 - e0)          # one scale for east and north
    height = TOP + plot_h + BOTTOM
    fig = plt.figure(figsize=(WIDTH, height))
    fig.patch.set_facecolor(SURFACE)
    for i, (letter, (name, _, _)) in enumerate(zip('ab', (FIRST, REPAIR))):
        left = LEFT + i * (plot_w + BETWEEN)
        ax = fig.add_axes((left / WIDTH, BOTTOM / height, plot_w / WIDTH, plot_h / height))
        ax.set_xlim(e0, e1)
        ax.set_ylim(n0, n1)
        ax.set_aspect('equal')
        ax.set_xticks(range(math.ceil(e0 / 20) * 20, int(e1) + 1, 20))
        ax.set_yticks(range(math.ceil(n0 / 20) * 20, int(n1) + 1, 20))
        ax.tick_params(colors=MUTED, labelsize=SMALL, length=3, width=0.8, labelleft=i == 0)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            ax.spines[side].set_color(MUTED)
        ax.set_xlabel('East of home (m)', fontsize=BODY, color=INK, labelpad=3)
        if i == 0:
            ax.set_ylabel('North of home (m)', fontsize=BODY, color=INK, labelpad=3)
        draw(ax, name, recs[name])
        y = (height - 0.045) / height
        fig.text(left / WIDTH, y, f'({letter})', fontsize=LETTER, fontweight='bold', color=INK, va='top')
        fig.text((left + 0.26) / WIDTH, y - 0.006 / height, name[0].upper() + name[1:], fontsize=BODY, color=INK,
                 va='top')

    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, facecolor=SURFACE, metadata={'Date': None})
    fig.savefig(a.out.with_suffix('.png'), dpi=300, facecolor=SURFACE)
    fig.savefig(a.out.with_suffix('.pdf'), facecolor=SURFACE, metadata={'CreationDate': None})
    print(f'wrote {a.out}, .png and .pdf, {WIDTH * 25.4:.0f} mm by {height * 25.4:.0f} mm')


if __name__ == '__main__':
    main()

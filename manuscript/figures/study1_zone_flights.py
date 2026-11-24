"""Figure 2: Study 1's reach zone flights, all 40 of them, and how each ended.

Study 1 adopted eight procedures for reach, one from each learning run, numbered 0 to 7. None of their test flights
held a zone. Each then flew the same five flights in which a no-fly zone switched on. Panel (a) draws the five
flights of run 4, the procedure the paper prints as Listing 1, one flight to a panel. Panel (b) draws all 40, the
five flights of each procedure in one small panel.

Every flight is seen from above and turned about home, with no mirror image, so that the line from home to the
target runs left to right. It is then moved along that line so that the target sits at the same place in every
panel. The zone's centre lies on the same line, to within the 0.1 m its coordinates are recorded to. A path joins
the simulator's true positions, one a second, with straight lines; the first recorded position is one second into
the flight. Every panel has the same scale.

How a flight ended is read from its record by these tests, in this order:

  1. goal_met is true                                         -> met the goal
  2. end_reason is entered_threat                             -> entered the zone
  3. the last position is within NEAR_M of the target         -> stopped beside the target
  4. it moved less than REST_M over its last LAST_S seconds   -> hovered far from the target
  5. otherwise                                                -> kept flying until the time ran out

Tests 3 to 5 apply only to flights whose end_reason is timed_out. The script prints the values either side of
each threshold, so a reader can see how far the thresholds could move without changing a count.

The script reads the 40 outcome records and nothing else. It prints each file's path and SHA-256, one hash taken
over those 40 lines, and the count of each ending. It refuses to draw if that one hash differs from the one held
below, because the labels were placed for these flights. No flight is selected or left out.

  .venv/bin/python -I manuscript/figures/study1_zone_flights.py [RUN_FOLDER] [--out FILE.svg]
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
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402
from matplotlib.text import Text  # noqa: E402

DEFAULT_ROOT = Path('/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-2')
RUNS, LISTING_RUN, FLIGHTS_PER_RUN = range(8), 4, 5
# One SHA-256 over the 40 lines 'relative path, two spaces, the file's SHA-256, newline', in the order printed.
EXPECTED = '3c7b29fc2dd010fe2114fae60edf4411f2ddda68031233e68df0bdbd648918c6'

NEAR_M, REST_M, LAST_S = 3.0, 1.0, 10     # the thresholds of tests 3 and 4; Supplement S14 uses the 3 m and the 10 s

INK, MUTED, SURFACE, ZONE = '#0b0b0b', '#52514e', '#ffffff', '#e4e3df'   # ink and greys of the other figures
PATH = '#2a78d6'                          # categorical slot 1, the colour Figure 4 gives a procedure learned
#                                           without the zone
# The five endings in the order of the key: the name the paper uses, and the mark that ends the path.
ENDINGS = (('met', 'met the goal', 'o'),
           ('flying', 'kept flying until the 90 s ran out', '^'),
           ('hovered', 'hovered far from the target', 'D'),
           ('stalled', 'stopped beside the target', 'v'),
           ('entered', 'entered the zone', 'X'))
NAME = {key: name for key, name, _ in ENDINGS}
MARK = {key: mark for key, _, mark in ENDINGS}
SIZE = {'o': 4.6, '^': 4.9, 'D': 4.0, 'v': 4.9, 'X': 5.2}     # so that the five marks look the same size

# Page geometry, in inches. The figure is 174 mm wide, the two-column width of the journal, and is saved at that
# size, so the type prints at the sizes set here (7 pt and above).
WIDTH = 174 / 25.4
SIDE, GAP, TOP, BOTTOM = 0.03, 0.07, 0.05, 0.04
HEAD, LINE, TITLE_GAP = 0.20, 0.125, 0.035   # a panel letter's line, one line of a small panel's title, and the gap
BETWEEN, KEY_ROW, KEY_GAP, KEY_ROWS = 0.13, 0.16, 0.09, 3
SMALL, BODY, LETTER = 7.0, 7.5, 8.5
PAD_M = 2.5                                  # room around everything drawn in a panel
BAR_M = 20                                   # the scale bar


def records(root: Path):
    """The 40 records in order of run and seed, with every check that they are what the figure says they are."""
    flights, lines = [], []
    for run in RUNS:
        folder = root / f'disturb-reach-learned-b{run}-matched' / 'flights'
        found = sorted(folder.glob('threat-*/outcome.json'))
        assert len(found) == FLIGHTS_PER_RUN, f'run {run}: {len(found)} zone flights, not {FLIGHTS_PER_RUN}'
        for path in found:
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            lines.append(f'{path.relative_to(root)}  {sha}\n')
            seed = int(re.fullmatch(r'threat-(\d+)', path.parent.name)[1])
            flights.append({'run': run, 'seed': seed, 'path': path, 'sha256': sha, 'rec': json.loads(raw)})
    assert len(flights) == len(RUNS) * FLIGHTS_PER_RUN == 40, len(flights)
    seeds = [f['seed'] for f in flights if f['run'] == 0]
    for f in flights:
        rec, first = f['rec'], next(g['rec'] for g in flights if g['seed'] == f['seed'])
        assert [g['seed'] for g in flights if g['run'] == f['run']] == seeds, 'the runs did not fly the same seeds'
        assert rec['task'] == 'reach' and rec['model_calls'] == 0, f['path']
        assert len(rec['events']) == 1 and rec['events'][0][0] == 'threat', rec['events']
        assert rec['goal'] == first['goal'] and rec['events'] == first['events'], 'one seed, two layouts'
        assert (rec['goal']['radius_m'], rec['goal']['time_limit_s']) == (2.0, 90.0), rec['goal']
        steps = rec['native_steps']
        assert [s['t'] for s in steps] == list(range(1, len(steps) + 1)), f'{f["path"]}: a second is missing'
        assert len(steps) == rec['ended_at'], f['path']
        on = rec['event_starts']['0']
        assert steps[on - 1]['threats'] == 0 and steps[on]['threats'] == 1, f'{f["path"]}: zone start'
        assert rec['end_reason'] in ('held', 'timed_out', 'entered_threat'), rec['end_reason']
        assert (rec['end_reason'] == 'held') == rec['goal_met'], f['path']
        assert rec['end_reason'] != 'timed_out' or rec['ended_at'] == rec['goal']['time_limit_s'], f['path']
    return flights, hashlib.sha256(''.join(lines).encode()).hexdigest(), lines


def turn(f: dict) -> None:
    """Add the flight's geometry in the figure's frame: metres along the line from home to the target, measured
    from the target, and metres across it, positive to the left of the direction of flight."""
    rec = f['rec']
    goal, (_, _, _, zone_n, zone_e, zone_r) = rec['goal'], rec['events'][0]
    target_n, target_e = goal['target_north_m'], goal['target_east_m']
    length = math.hypot(target_n, target_e)
    un, ue = target_n / length, target_e / length

    def frame(north, east):
        return north * un + east * ue - length, north * ue - east * un

    f['home'] = (-length, 0.0)
    f['zone'] = (*frame(zone_n, zone_e), zone_r)
    f['goal_r'] = goal['radius_m']
    f['xy'] = [frame(s['north_m'], s['east_m']) for s in rec['native_steps']]
    f['on'] = rec['event_starts']['0']
    f['past'] = math.hypot(target_n - zone_n, target_e - zone_e) - zone_r     # target beyond the zone's edge
    steps = [math.dist(a, b) for a, b in zip(f['xy'], f['xy'][1:])]
    f['to_target'] = math.hypot(*f['xy'][-1])
    f['moved'] = sum(steps[-LAST_S:])
    f['flown'] = sum(steps)
    f['speed'] = [math.hypot(s['velocity_applied']['vn'], s['velocity_applied']['ve']) for s in rec['native_steps']]
    if rec['goal_met']:
        f['ending'] = 'met'
    elif rec['end_reason'] == 'entered_threat':
        f['ending'] = 'entered'
    elif f['to_target'] <= NEAR_M:
        f['ending'] = 'stalled'
    elif f['moved'] < REST_M:
        f['ending'] = 'hovered'
    else:
        f['ending'] = 'flying'


def report(flights, digest, lines) -> dict:
    print(''.join(lines), end='')
    print(f'one sha256 over the {len(lines)} lines above: {digest}')
    by_seed = {f['seed']: f for f in flights if f['run'] == 0}
    print('the five layouts, the same for every run:')
    for seed, f in by_seed.items():
        zx, zy, zr = f['zone']
        print(f'  seed {seed}: target {-f["home"][0]:.2f} m from home; zone radius {zr} m, its centre {-zx:.2f} m '
              f'short of the target and {zy:+.3f} m off the line; target {f["past"]:.2f} m past its edge; '
              f'zone on at second {f["on"]}')
    print('each flight: ending; distance from the target at the end; metres moved in the last '
          f'{LAST_S} s; metres flown; commanded speed, least and greatest, whole flight and last {LAST_S} s')
    for f in flights:
        rec, v = f['rec'], f['speed']
        print(f'  run {f["run"]} seed {f["seed"]}: {f["ending"]:8s} end_reason {rec["end_reason"]:14s} '
              f'ended_at {rec["ended_at"]:2d} s  {f["to_target"]:6.2f} m  {f["moved"]:6.2f} m  {f["flown"]:6.1f} m  '
              f'{min(v):.2f} to {max(v):.2f} m/s, {min(v[-LAST_S:]):.2f} to {max(v[-LAST_S:]):.2f} m/s')
    late = [f for f in flights if f['rec']['end_reason'] == 'timed_out']
    near = sorted(f['to_target'] for f in late)
    far = [f for f in late if f['ending'] != 'stalled']
    print(f'test 3, within {NEAR_M} m of the target: of the {len(late)} flights that timed out, the nearest ended '
          + ', '.join(f'{d:.2f}' for d in near[:4]) + ' m from it')
    print(f'test 4, moved less than {REST_M} m in the last {LAST_S} s: the {len(far)} flights left by test 3 moved '
          f'{max(f["moved"] for f in far if f["ending"] == "hovered"):.2f} m at most (hovered) and '
          f'{min(f["moved"] for f in far if f["ending"] == "flying"):.2f} m at least (kept flying); '
          f'the stalled moved ' + ' and '.join(f'{f["moved"]:.2f}' for f in late if f['ending'] == 'stalled') + ' m')
    tally = {key: sum(f['ending'] == key for f in flights) for key, _, _ in ENDINGS}
    print('endings: ' + '; '.join(f'{name} {tally[key]}' for key, name, _ in ENDINGS) + f'; in all {sum(tally.values())}')
    for run in RUNS:
        mine = [f['ending'] for f in flights if f['run'] == run]
        print(f'  run {run}: ' + ', '.join(f'{name} {mine.count(key)}' for key, name, _ in ENDINGS if key in mine))
    return tally


def limits(flights):
    """Limits in metres that hold everything drawn for these flights, with room around it."""
    xs, ys = [], []
    for f in flights:
        zx, zy, zr = f['zone']
        xs += [f['home'][0], zx - zr, zx + zr, f['goal_r']] + [x for x, _ in f['xy']]
        ys += [zy - zr, zy + zr, -f['goal_r'], f['goal_r']] + [y for _, y in f['xy']]
    return (min(xs) - PAD_M, max(xs) + PAD_M), (min(ys) - PAD_M, max(ys) + PAD_M)


def end_mark(ax, x, y, ending, zorder=6):
    mark = MARK[ending]
    ax.plot([x], [y], marker=mark, ms=SIZE[mark], markerfacecolor=PATH, markeredgecolor=INK, mew=0.7, ls='',
            zorder=zorder, clip_on=False)


def draw(ax, mine, detail: bool) -> None:
    """One small panel: the flights given, each with its own home, zone and path, and the one goal circle."""
    for f in mine:
        zx, zy, zr = f['zone']
        ax.add_patch(Circle((zx, zy), zr, facecolor=ZONE, edgecolor='none', zorder=1))
    for f in mine:
        zx, zy, zr = f['zone']
        ax.add_patch(Circle((zx, zy), zr, fill=False, edgecolor=MUTED, lw=0.6, zorder=2))
    ax.add_patch(Circle((0, 0), mine[0]['goal_r'], fill=False, edgecolor=INK, lw=0.7, zorder=7))
    ax.plot([0], [0], marker='+', ms=3.0, mew=0.7, color=INK, ls='', zorder=7)
    for f in mine:
        xs, ys = [x for x, _ in f['xy']], [y for _, y in f['xy']]
        if detail:
            ax.plot(xs, ys, color=PATH, lw=0.9, marker='o', ms=1.5, zorder=3)
        else:
            ax.plot(xs, ys, color=PATH, lw=0.55, zorder=3)
        ax.plot([f['home'][0]], [0], marker='s', ms=3.6, markerfacecolor=INK, markeredgecolor=SURFACE, mew=0.5,
                ls='', zorder=4)
    if detail:
        for f in mine:
            x, y = f['xy'][f['on'] - 1]
            ax.plot([x], [y], marker='o', ms=3.8, markerfacecolor=SURFACE, markeredgecolor=INK, mew=0.8, ls='',
                    zorder=5)
    for f in mine:
        end_mark(ax, *f['xy'][-1], f['ending'])


def panel(fig, height, left, top, xlim, ylim, scale):
    """An axes with one scale for both directions. `left` and `top` are in inches from the figure's edges."""
    w, h = (xlim[1] - xlim[0]) * scale, (ylim[1] - ylim[0]) * scale
    ax = fig.add_axes((left / WIDTH, (height - top - h) / height, w / WIDTH, h / height))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_color(ZONE)
        side.set_linewidth(0.8)
    return ax


def key(fig, height, top, tally, scale, on):
    """What the marks mean, drawn with the marks themselves, in rows across the figure."""
    h = KEY_ROWS * KEY_ROW
    ax = fig.add_axes((0, (height - top - h) / height, 1, h / height))
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(h, 0)
    ax.set_aspect('equal')
    ax.axis('off')
    renderer = fig.canvas.get_renderer()

    def label(x, y, words, **kw):
        """Write a label and return the x at which it ends, in inches."""
        t = ax.text(x, y, words, fontsize=SMALL, color=INK, va='center', **kw)
        return x + t.get_window_extent(renderer).width / fig.dpi

    first, mark_w, after = SIDE + 0.07, 0.10, 0.24      # the first mark, a mark to its label, a label to the next mark
    y = KEY_ROW / 2
    x = first
    ax.plot([x], [y], marker='s', ms=3.6, markerfacecolor=INK, markeredgecolor=SURFACE, mew=0.5, ls='')
    x = label(x + mark_w, y, 'home') + after
    ax.add_patch(Circle((x, y), 0.055, facecolor=ZONE, edgecolor=MUTED, lw=0.6))
    x = label(x + mark_w, y, 'zone') + after
    ax.add_patch(Circle((x, y), 2.0 * scale, fill=False, edgecolor=INK, lw=0.7))
    ax.plot([x], [y], marker='+', ms=3.0, mew=0.7, color=INK, ls='')
    x = label(x + mark_w, y, 'target and its 2 m goal circle') + after + 0.06
    ax.plot((x - 0.09, x + 0.09), (y, y), color=PATH, lw=0.9, marker='o', ms=1.5)
    x = label(x + mark_w + 0.05, y, 'path, one position a second') + after
    ax.plot([x], [y], marker='o', ms=3.8, markerfacecolor=SURFACE, markeredgecolor=INK, mew=0.8, ls='')
    x = label(x + mark_w, y, f'zone switched on ({on} s), in (a)')
    assert x < WIDTH - SIDE, 'the first row of the key runs off the figure'
    indent = label(first - 0.05, 1.5 * KEY_ROW, 'How a flight ended:') + 0.14
    for i, row in enumerate((ENDINGS[:3], ENDINGS[3:])):
        x, y = indent, (i + 1.5) * KEY_ROW
        for ending, name, mark in row:
            ax.plot([x], [y], marker=mark, ms=SIZE[mark], markerfacecolor=PATH, markeredgecolor=INK, mew=0.7, ls='')
            x = label(x + mark_w, y, f'{name}, {tally[ending]}') + after
        assert x - after < WIDTH - SIDE, 'a row of the key runs off the figure'
    bar = BAR_M * scale                                  # the scale bar, at the right of the last row
    x = WIDTH - SIDE - 0.03 - bar
    ax.plot((x, x + bar), (y, y), color=INK, lw=0.9, solid_capstyle='butt')
    for end in (x, x + bar):
        ax.plot((end, end), (y - 0.03, y + 0.03), color=INK, lw=0.9)
    ax.text(x - 0.06, y, f'{BAR_M} m in every panel', ha='right', fontsize=SMALL, color=INK, va='center')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('root', type=Path, nargs='?', default=DEFAULT_ROOT)
    p.add_argument('--out', type=Path, default=Path(__file__).with_name('study1-zone-flights.svg'))
    a = p.parse_args(argv)
    flights, digest, lines = records(a.root)
    for f in flights:
        turn(f)
    tally = report(flights, digest, lines)
    assert EXPECTED is None or digest == EXPECTED, f'these are not the 40 files the figure was drawn for ({EXPECTED})'

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'pdf.fonttype': 42,
                         'svg.hashsalt': 'paper3-study1-zone-flights'})
    listing = [f for f in flights if f['run'] == LISTING_RUN]
    xa, ya = limits(listing)
    xb, _ = limits(flights)
    yb = [limits([f for f in flights if f['run'] // 4 == row])[1] for row in (0, 1)]   # each row of (b) its own
    wide = WIDTH - 2 * SIDE
    scale = min((wide - 4 * GAP) / (5 * (xa[1] - xa[0])), (wide - 3 * GAP) / (4 * (xb[1] - xb[0])))   # inches a metre
    ha, hb = (ya[1] - ya[0]) * scale, [(lo_hi[1] - lo_hi[0]) * scale for lo_hi in yb]
    top_a = TOP + HEAD + 2 * LINE + TITLE_GAP
    top_b = top_a + ha + BETWEEN + HEAD + LINE + TITLE_GAP
    top_b2 = top_b + hb[0] + LINE + 2 * TITLE_GAP
    top_key = top_b2 + hb[1] + KEY_GAP
    height = top_key + KEY_ROWS * KEY_ROW + BOTTOM
    fig = plt.figure(figsize=(WIDTH, height))
    fig.patch.set_facecolor(SURFACE)

    def words(x, top, text, **kw):
        fig.text(x / WIDTH, (height - top) / height, text, va='top', color=INK, **kw)

    words(SIDE, TOP, '(a)', fontsize=LETTER, fontweight='bold')
    words(SIDE + 0.26, TOP + 0.006, 'The five zone flights of the procedure in Listing 1',
          fontsize=BODY)
    step = (xa[1] - xa[0]) * scale + (wide - 5 * (xa[1] - xa[0]) * scale) / 4
    for i, f in enumerate(listing):
        left = SIDE + i * step
        ax = panel(fig, height, left, top_a, xa, ya, scale)
        draw(ax, [f], detail=True)
        zx, zy, zr = f['zone']
        ax.text(zx, zy + 0.45 * zr, 'zone', ha='center', va='center', fontsize=SMALL, color=INK, zorder=2)
        if f['ending'] == 'met':
            ended = f'met the goal in {f["rec"]["ended_at"]} s'
        else:
            ended = NAME[f['ending']].replace('the target', 'it')
        words(left, TOP + HEAD, f'Target {f["past"]:.1f} m past the zone', fontsize=SMALL)
        words(left, TOP + HEAD + LINE, ended, fontsize=SMALL)

    words(SIDE, top_a + ha + BETWEEN, '(b)', fontsize=LETTER, fontweight='bold')
    words(SIDE + 0.26, top_a + ha + BETWEEN + 0.006,
          'All 40 flights: one panel for each of the eight procedures, with its five flights', fontsize=BODY)
    step = (xb[1] - xb[0]) * scale + (wide - 4 * (xb[1] - xb[0]) * scale) / 3
    for run in RUNS:
        row, col = divmod(run, 4)
        left, top = SIDE + col * step, (top_b, top_b2)[row]
        ax = panel(fig, height, left, top, xb, yb[row], scale)
        draw(ax, [f for f in flights if f['run'] == run], detail=False)
        words(left, top - LINE - TITLE_GAP, ('Listing 1' if run == LISTING_RUN else f'Procedure {run + 1}'),
              fontsize=SMALL)
        # the run's own count of each ending, written with the marks, at the right of its title line
        x, y = left + (xb[1] - xb[0]) * scale - 0.02, top - TITLE_GAP - 0.062
        mine = [f['ending'] for f in flights if f['run'] == run]
        for ending, _, mark in reversed(ENDINGS):
            if ending in mine:
                fig.text(x / WIDTH, (height - y) / height, str(mine.count(ending)), ha='right', va='center',
                         fontsize=SMALL, color=INK)
                x -= 0.135
                fig.add_artist(Line2D([x / WIDTH], [(height - y) / height], marker=mark, ms=SIZE[mark],
                                      markerfacecolor=PATH, markeredgecolor=INK, mew=0.7, ls='',
                                      transform=fig.transFigure))
                x -= 0.16
    on = {f['on'] for f in flights}
    assert len(on) == 1, f'the zone switched on at different seconds: {sorted(on)}'
    key(fig, height, top_key, tally, scale, on.pop())

    small = [t for t in fig.findobj(Text) if t.get_text().strip() and t.get_fontsize() < SMALL]
    assert not small, [(t.get_text(), t.get_fontsize()) for t in small]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, facecolor=SURFACE, metadata={'Date': None})
    fig.savefig(a.out.with_suffix('.png'), dpi=300, facecolor=SURFACE)
    fig.savefig(a.out.with_suffix('.pdf'), facecolor=SURFACE, metadata={'CreationDate': None})
    print(f'wrote {a.out}, .png and .pdf, {WIDTH * 25.4:.0f} mm by {height * 25.4:.0f} mm, '
          f'{scale * 25.4:.3f} mm to the metre')


if __name__ == '__main__':
    main()

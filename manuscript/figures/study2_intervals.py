"""Figure 3: Study 2's answers in one picture, the three primary steps and RQ4's six intervals.

Panel (a) is a forest plot of the three primary steps in the order B - A, C - B and D - C, the order of the engineer's questions. Each step has four rows:
the step pooled over the three tasks, then the same step within reach, reach3d and land. Panel (b) gives RQ4's six
secondary intervals, D - A on close and on distant targets for each task. A row shows the point estimate as a marker,
the 95% interval as a thin line and the 90% interval as a thick line. In each group of rows a solid vertical line
marks zero, and a shaded band with dashed edges marks the margin either side of zero.

The script reads the frozen analysis output and nothing else. It prints that file's SHA-256 and every number it
plots. It computes no statistic: every estimate, every interval end and the margin are copied from the file.

  .venv/bin/python -I manuscript/figures/study2_intervals.py [ANALYSIS_JSON] [--out FILE.svg]
"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

DEFAULT_ANALYSIS = Path('/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-20261120-S-results/analysis.json')
INK, MUTED, SURFACE = '#0b0b0b', '#52514e', '#ffffff'   # the ink and grey of the other figures
BAND = '#e4e3df'                                         # their grid grey, here the fill of the margin band
TASKS = ('reach', 'reach3d', 'land')
STEPS = (('B-A', 'Testing against the zone'),
         ('C-B', 'Repair instead of a fresh candidate'),
         ('D-C', 'Showing the zone first'))
BANDS = (('close', 'close targets'), ('middle-wide', 'distant targets'))
TOTAL = 'All three together'

# Page geometry, in inches. The figure is 174 mm wide, the two-column width of the journal, and is saved at that
# size, so the type prints at the sizes set here (7 pt and above).
WIDTH = 174 / 25.4
PITCH = 0.185          # height of one row
LEFT, LABELS_A, LABELS_B, PLOT, BETWEEN = 0.06, 0.64, 0.97, 2.42, 0.30
TOP, BOTTOM = 0.27, 0.46
INDENT = 0.11
XLIM = (-0.45, 0.85)
XTICKS = (-0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.8)
SMALL, BODY, LETTER = 7.0, 7.5, 8.5


def minus(text: str) -> str:
    """'C-B' as 'C − B', with a true minus sign."""
    return text.replace('-', ' − ')


def row(label: str, rec: dict, pooled: bool = False) -> dict:
    est, (lo95, hi95), (lo90, hi90) = rec['estimate'], rec['ci95'], rec['ci90']
    assert lo95 <= lo90 <= est <= hi90 <= hi95, (label, rec)
    assert XLIM[0] < lo95 and hi95 < XLIM[1], f'{label}: the interval runs off the axis'
    return {'label': label, 'estimate': est, 'ci95': (lo95, hi95), 'ci90': (lo90, hi90), 'pooled': pooled}


def read(out: dict):
    """The rows of each panel, in the order drawn, straight from the analysis output."""
    boot = out['bootstrap']
    assert boot['direction_coverage'] == 0.95 and boot['equivalence_coverage'] == 0.9, boot
    panel_a = []
    for step, words in STEPS:
        p = out['primary'][f'pooled:{step}']
        assert set(p['per_task']) == set(TASKS), sorted(p['per_task'])
        rows = [row('pooled', p, pooled=True)] + [row(task, p['per_task'][task]) for task in TASKS]
        panel_a.append((f'{words} ({minus(step)})', rows))
    assert len(out['secondary_intervals']) == len(TASKS) * len(BANDS), sorted(out['secondary_intervals'])
    panel_b = [(task, [row(words, out['secondary_intervals'][f'{task}:D-A:{band}']) for band, words in BANDS])
               for task in TASKS]
    return boot['margin'], panel_a, panel_b


def report(margin, panel_a, panel_b) -> None:
    def line(name, r):
        print(f"  {name:28s} estimate {r['estimate']!r:>16}  95% {r['ci95'][0]!r} to {r['ci95'][1]!r}"
              f"  90% {r['ci90'][0]!r} to {r['ci90'][1]!r}")
    print(f'margin {margin!r} (bootstrap.margin); lines at 0 and at plus and minus the margin')
    print('panel (a), primary steps (primary[pooled:STEP] and its per_task):')
    for (step, _), (_, rows) in zip(STEPS, panel_a):
        for r in rows:
            line(f"{step} {r['label']}", r)
    print('panel (b), RQ4 (secondary_intervals[TASK:D-A:BAND]):')
    for task, rows in panel_b:
        for (band, _), r in zip(BANDS, rows):
            line(f'D-A {task} {band}', r)


def layout_a(groups):
    """Each group is a heading line and its rows beneath; y counts rows downward from the top."""
    items, y = [], 0.0
    for heading, rows in groups:
        items.append(('heading', y, heading))
        items.append(('block', y + 0.5, y + len(rows) + 0.5))
        items += [('row', y + 1 + i, r) for i, r in enumerate(rows)]
        y += len(rows) + 1.6
    return items, y - 1.6 + 0.5


def layout_b(tasks):
    """One heading for the panel, then each task's name and its two rows."""
    items, y = [('heading', 0.0, f"{TOTAL} ({minus('D-A')})")], 1.0
    for task, rows in tasks:
        items.append(('task', y, task))
        items.append(('block', y + 0.5, y + len(rows) + 0.5))
        items += [('row', y + 1 + i, r) for i, r in enumerate(rows)]
        y += len(rows) + 1.25
    return items, y - 1.25 + 0.5


def interval(ax, y, r):
    ax.plot(r['ci95'], (y, y), color=INK, lw=0.9, solid_capstyle='butt', zorder=3)
    ax.plot(r['ci90'], (y, y), color=INK, lw=2.8, solid_capstyle='butt', zorder=4)
    ax.plot([r['estimate']], [y], marker='D' if r['pooled'] else 'o', ms=6.4 if r['pooled'] else 5.0, color=INK,
            markeredgecolor=SURFACE, markeredgewidth=0.8, ls='', zorder=5)


def band(ax, y0, y1, margin):
    ax.add_patch(Rectangle((-margin, y0), 2 * margin, y1 - y0, facecolor=BAND, edgecolor='none', zorder=1))
    ax.plot((0, 0), (y0, y1), color=MUTED, lw=0.8, zorder=2)
    for x in (-margin, margin):
        ax.plot((x, x), (y0, y1), color=MUTED, lw=0.7, ls=(0, (3, 2)), zorder=2)


def panel(fig, height, left, labels, items, bottom_row, letter, margin):
    """One forest plot. `left` is where its label column starts and `labels` that column's width, in inches."""
    h = (bottom_row + 0.75) * PITCH
    ax = fig.add_axes(((left + labels) / WIDTH, (height - TOP - h) / height, PLOT / WIDTH, h / height))
    ax.set_xlim(*XLIM)
    ax.set_ylim(bottom_row + 0.25, -0.5)
    ax.set_yticks([])
    for side in ('left', 'top', 'right'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color(MUTED)
    ax.set_xticks(XTICKS)
    ax.set_xticklabels(['0' if x == 0 else f'{x:.1f}'.replace('-', '−') for x in XTICKS])
    ax.tick_params(axis='x', colors=MUTED, labelsize=SMALL, length=3, width=0.8)
    ax.set_xlabel('difference in success on unseen zone flights', fontsize=BODY, color=INK, labelpad=3)
    across = ax.get_yaxis_transform()        # x in fractions of the plot's width, y in rows
    x_heading, x_row = -labels / PLOT, -(labels - INDENT) / PLOT
    for kind, y, *rest in items:
        if kind == 'heading':
            ax.text(x_heading, y, rest[0], transform=across, fontsize=BODY, fontweight='bold', color=INK, va='center')
        elif kind == 'task':
            ax.text(x_heading, y, rest[0], transform=across, fontsize=BODY, color=INK, va='center')
        elif kind == 'block':
            band(ax, y, rest[0], margin)
        else:
            ax.text(x_row, y, rest[0]['label'], transform=across, fontsize=BODY, color=INK, va='center')
            interval(ax, y, rest[0])
    fig.text(left / WIDTH, (height - 0.045) / height, letter, fontsize=LETTER, fontweight='bold', color=INK, va='top')
    return ax, h


def key(fig, height, left, top, margin):
    """What the marks mean, drawn with the marks themselves. `left` and `top` are in inches from the figure's edges."""
    w, h = PLOT + LABELS_B, 3 * PITCH
    ax = fig.add_axes((left / WIDTH, (height - top - h) / height, w / WIDTH, h / height))
    ax.set_xlim(0, w)
    ax.set_ylim(3, 0)
    ax.axis('off')
    text = dict(fontsize=SMALL, color=INK, va='center')
    # line 1: the two markers
    ax.plot([0.14], [0.5], marker='D', ms=6.4, color=INK, markeredgecolor=SURFACE, markeredgewidth=0.8, ls='')
    ax.text(0.30, 0.5, 'pooled over the three tasks', **text)
    ax.plot([1.94], [0.5], marker='o', ms=5.0, color=INK, markeredgecolor=SURFACE, markeredgewidth=0.8, ls='')
    ax.text(2.08, 0.5, 'one task', **text)
    # line 2: the two intervals
    ax.plot((0.02, 0.26), (1.5, 1.5), color=INK, lw=2.8, solid_capstyle='butt')
    ax.text(0.30, 1.5, '90% interval', **text)
    ax.plot((1.20, 1.44), (1.5, 1.5), color=INK, lw=0.9, solid_capstyle='butt')
    ax.text(1.48, 1.5, '95% interval', **text)
    # line 3: the band
    ax.add_patch(Rectangle((0.02, 2.14), 0.24, 0.72, facecolor=BAND, edgecolor='none'))
    for x in (0.02, 0.26):
        ax.plot((x, x), (2.14, 2.86), color=MUTED, lw=0.7, ls=(0, (3, 2)))
    ax.text(0.30, 2.5, f'within the margin, −{margin:.2f} to +{margin:.2f}', **text)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('analysis', type=Path, nargs='?', default=DEFAULT_ANALYSIS)
    p.add_argument('--out', type=Path, default=Path(__file__).with_name('study2-intervals.svg'))
    a = p.parse_args(argv)
    raw = a.analysis.read_bytes()
    print(f'{a.analysis}  sha256 {hashlib.sha256(raw).hexdigest()}')
    margin, panel_a, panel_b = read(json.loads(raw))
    report(margin, panel_a, panel_b)

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'pdf.fonttype': 42, 'svg.hashsalt': 'paper3-study2-intervals'})
    items_a, last_a = layout_a(panel_a)
    items_b, last_b = layout_b(panel_b)
    height = TOP + (last_a + 0.75) * PITCH + BOTTOM
    fig = plt.figure(figsize=(WIDTH, height))
    fig.patch.set_facecolor(SURFACE)
    panel(fig, height, LEFT, LABELS_A, items_a, last_a, '(a)', margin)
    left_b = LEFT + LABELS_A + PLOT + BETWEEN
    _, h_b = panel(fig, height, left_b, LABELS_B, items_b, last_b, '(b)', margin)
    key(fig, height, left_b, TOP + h_b + BOTTOM + 0.12, margin)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, facecolor=SURFACE, metadata={'Date': None})
    fig.savefig(a.out.with_suffix('.png'), dpi=300, facecolor=SURFACE)
    fig.savefig(a.out.with_suffix('.pdf'), facecolor=SURFACE, metadata={'CreationDate': None})
    print(f'wrote {a.out}, .png and .pdf, {WIDTH * 25.4:.0f} mm by {height * 25.4:.0f} mm')


if __name__ == '__main__':
    main()

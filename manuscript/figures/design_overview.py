"""Figure 1: the design. Telohelm's learning loop on ArduPilot, one Study 2 layout, and one block of Study 2.

Panel (a) is the loop. The language model writes a candidate procedure, the monitor flies it on the test flights
and adopts it only if it passes them all, and a failed test puts its flights into the next request. The monitor,
the guard and the judge are fixed code that the model cannot change, drawn with a heavy outline. Beneath a
procedure lie the guard, ArduPilot's guided mode and the simulated vehicle. An adopted procedure flies on the same
stack with no model.

Panel (b) is one Study 2 layout seen from above and drawn to scale: home, the zone on the line to the target, and
the three bands beyond the zone's far edge in which the target may lie. The zone is drawn at the middle of each of
its ranges (MIDDLE below). The dashed arc is the part, on the home side, of the ring that lies TRIGGER_M from the
zone's edge; the zone switches on at the first one-second step that begins with the drone inside that ring.

Panel (c) is one block: its three layouts, the five arms as five rows, and the unseen zone flights. A grey cell
differs from arm A's. A cell with a heavy outline differs from the arm the row is compared with (the arm above it, or
arm B for arm E, which was added after the four-arm analysis), and carries that comparison's name.

The figure holds no data and the script reads no file. Every number in it is a design fact, given below with the
place it was taken from: the frozen protocol (PROTOCOL-3.md) or the paper's draft.

  .venv/bin/python -I manuscript/figures/design_overview.py [--out FILE.svg]
"""
import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Rectangle  # noqa: E402
from matplotlib.text import Text  # noqa: E402

# Design facts, in metres. PROTOCOL-3.md section 2.1 ('Zone' row) and section 3; the draft's Sections 3 and 4.4.
EDGE_M = (24.0, 30.0)        # the zone's near edge, from home
RADIUS_M = (6.0, 9.0)        # the zone's radius
TRIGGER_M = 19.0             # the zone switches on when the drone first comes within this of its edge
BANDS_M = (('close', 3.0, 4.0), ('middle', 9.0, 11.0), ('wide', 19.0, 21.0))   # beyond the zone's far edge
MIDDLE = (sum(EDGE_M) / 2, sum(RADIUS_M) / 2)     # what panel (b) draws: near edge 27 m from home, radius 7.5 m
LAYOUTS, CANDIDATES, HELD_OUT, PER_BAND = 3, 3, 24, 8   # PROTOCOL-3.md sections 1.1, 4.1 and 4.2
# The five arms, as Table 1 of the draft gives them, and the arm each is compared with (PROTOCOL-3.md for A to D,
# PROTOCOL-EXTRA.md for E).
ARMS = (('A', 'flights without the zone', 'test without the zone', 'a fresh candidate'),
        ('B', 'flights without the zone', 'zone test', 'a fresh candidate'),
        ('C', 'flights without the zone', 'zone test', 'a repair'),
        ('D', 'flights with the zone', 'zone test', 'a repair'),
        ('E', 'flights without the zone', 'zone test', 'a fresh candidate shown the failure'))
COMPARED_WITH = {'B': 'A', 'C': 'B', 'D': 'C', 'E': 'B'}
COLUMNS = ('First request shows', 'Adoption test', 'After a failed test')

INK, MUTED, SURFACE, GREY = '#0b0b0b', '#52514e', '#ffffff', '#e4e3df'   # ink and greys of the other figures
THIN, HEAVY, LINE = 0.8, 1.9, 0.9                  # outline of a box, of a fixed part, and an arrow, in points
SMALL, BODY, LETTER = 7.0, 7.5, 8.5

# Page geometry, in millimetres from the figure's top left corner. The figure is 174 mm wide, the two-column
# width of the journal, and is saved at that size, so the type prints at the sizes set here (7 pt and above).
WIDTH, HEIGHT = 174.0, 163.0
PT = 25.4 / 72                                     # one point in millimetres
ROW = 1.3 * SMALL * PT                             # the pitch of lines of small type


class Page:
    """One axes over the whole figure, in millimetres with y downward, and the checks that text stays in place."""

    def __init__(self):
        self.fig = plt.figure(figsize=(WIDTH / 25.4, HEIGHT / 25.4))
        self.fig.patch.set_facecolor(SURFACE)
        self.ax = self.fig.add_axes((0, 0, 1, 1))
        self.ax.set_xlim(0, WIDTH)
        self.ax.set_ylim(HEIGHT, 0)
        self.ax.axis('off')
        self.inside = []       # (text, x0, y0, x1, y1): the text must lie within the rectangle

    def text(self, x, y, words, size=SMALL, bold=False, ha='left', va='top', within=None, colour=INK, **kw):
        t = self.ax.text(x, y, words, fontsize=size, fontweight='bold' if bold else 'normal', ha=ha, va=va,
                         color=colour, linespacing=1.3, zorder=5, **kw)
        if within:
            self.inside.append((t, *within))
        return t

    def extent(self, t):
        """A text's box in millimetres: left, top, right, bottom."""
        box = t.get_window_extent(self.fig.canvas.get_renderer())
        (x0, y0), (x1, y1) = self.ax.transData.inverted().transform([(box.x0, box.y1), (box.x1, box.y0)])
        return x0, y0, x1, y1

    def box(self, x, y, w, h, heavy=False, fill=SURFACE, edge=None, zorder=2):
        lw = HEAVY if heavy else THIN
        self.ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=edge or (INK if heavy else MUTED),
                                    linewidth=lw, zorder=zorder + (1 if heavy else 0), joinstyle='miter'))
        return x, y, x + w, y + h

    def part(self, x, y, w, h, title, body='', heavy=False):
        """A labelled box: a bold title and lines of body text beneath it."""
        rect = self.box(x, y, w, h, heavy=heavy)
        self.text(x + 1.6, y + 1.5, title, bold=True, within=rect)
        if body:
            self.text(x + 1.6, y + 1.5 + ROW, body, within=rect)
        return rect

    def layer(self, x, y, w, h, title, body, heavy=False):
        """A box one line high: a bold title, then its body on the same line."""
        rect = self.box(x, y, w, h, heavy=heavy)
        t = self.text(x + 1.6, y + h / 2, title, bold=True, va='center', within=rect)
        self.text(self.extent(t)[2] + 1.2, y + h / 2, body, va='center', within=rect)
        return rect

    def arrow(self, a, b, colour=INK):
        self.ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=7, linewidth=LINE, color=colour,
                                          shrinkA=0, shrinkB=0, zorder=4))

    def line(self, xs, ys, colour=INK, lw=0.7, **kw):
        self.ax.plot(xs, ys, color=colour, lw=lw, solid_capstyle='butt', zorder=kw.pop('zorder', 3), **kw)

    def letter(self, y, letter, words):
        self.text(0.8, y, f'({letter})', size=LETTER, bold=True)
        self.text(7.6, y + 0.15, words, size=BODY)

    def check(self):
        """No text may leave the box it was written for, and none may be under 7 pt."""
        for t, x0, y0, x1, y1 in self.inside:
            a0, b0, a1, b1 = self.extent(t)
            assert x0 + 0.6 <= a0 and a1 <= x1 - 0.6 and y0 + 0.4 <= b0 and b1 <= y1 - 0.4, \
                f'{t.get_text()!r} leaves its box: {a0:.1f} {b0:.1f} {a1:.1f} {b1:.1f} in {x0} {y0} {x1} {y1}'
        for t in self.fig.findobj(Text):
            if t.get_text().strip():
                assert t.get_fontsize() >= SMALL, (t.get_text(), t.get_fontsize())
                a0, b0, a1, b1 = self.extent(t)
                assert 0 <= a0 and a1 <= WIDTH and 0 <= b0 and b1 <= HEIGHT, f'{t.get_text()!r} leaves the figure'


def loop(p: Page, top: float) -> None:
    """Panel (a): the learning loop, the fixed parts, and what lies beneath a procedure."""
    p.letter(top + 1.0, 'a', 'Telohelm on ArduPilot: how a procedure is found, and what it flies on')
    y = top + 7.0
    model = p.part(1, y, 28, 17, 'Language model', 'writes a candidate\nprocedure')
    monitor = p.part(60, y, 37, 17, 'Monitor (fixed)',
                     'flies the candidate on the\ntest flights and adopts it\nonly if it passes them all', heavy=True)
    judge = p.part(60, y + 27, 37, 15, 'Judge (fixed)',
                   "reads the simulator's true\nstate and decides whether\na flight met its goal", heavy=True)
    candidate = p.part(102.5, y, 34.5, 13, 'Candidate procedure', 'in a test flight')
    adopted = p.part(142.5, y, 30.5, 13, 'Adopted procedure', 'flies with no model\nin the loop')
    stack = adopted[2] - candidate[0]
    p.layer(candidate[0], y + 14.2, stack, 6.6, 'Guard (fixed)', 'accepts or refuses each command', heavy=True)
    p.layer(candidate[0], y + 22.0, stack, 6.6, "ArduPilot's guided mode", 'flies the command')
    vehicle = p.part(candidate[0], y + 29.8, stack, 12.2, 'Simulated vehicle',
                     "ArduPilot's software-in-the-loop\nsimulator (both studies)")
    # the loop between the model and the monitor
    between = (model[2], monitor[0])
    p.arrow((between[0], y + 4.5), (between[1], y + 4.5))
    p.text(sum(between) / 2, y + 3.4, 'candidate procedure', ha='center', va='bottom',
           within=(between[0], y - 1, between[1], y + 4.5))
    p.arrow((between[1], y + 12.5), (between[0], y + 12.5))
    p.text(sum(between) / 2, y + 13.8, 'after a failed test,\nthe next request shows\nthe flights that failed',
           ha='center', within=(between[0], y + 12.5, between[1], judge[1]))
    # the monitor flies the candidate; an adopted procedure flies on the same stack
    p.arrow((monitor[2], y + 6.5), (candidate[0], y + 6.5))
    p.arrow((candidate[2], y + 6.5), (adopted[0], y + 6.5))
    # the judge reads the simulator and tells the monitor
    p.arrow((vehicle[0], judge[1] + 9), (judge[2], judge[1] + 9))
    x = judge[0] + 12
    p.arrow((x, judge[1]), (x, monitor[3]))
    p.text(x + 1.8, (judge[1] + monitor[3]) / 2, 'goal met\nor not', va='center')
    # what the heavy outline means
    p.box(1.4, y + 30.6, 5.2, 3.6, heavy=True)
    p.text(8.8, y + 29.6, 'Heavy outline: fixed code,\noutside the reach of the model.\nThe model cannot change it.',
           within=(8, y + 28, judge[0] - 1, y + 42))


def layout(p: Page, top: float) -> None:
    """Panel (b): one layout from above, to scale."""
    edge, radius = MIDDLE
    p.letter(top + 1.0, 'b', 'One Study 2 layout, seen from above and to scale, the zone drawn at the middle of '
                             'each of its ranges')
    scale, home, y = 2.05, 14.0, top + 24.6         # millimetres to the metre; where home is drawn; the line's height

    def mm(metres):
        return home + scale * metres

    centre, far = edge + radius, edge + 2 * radius
    last = far + BANDS_M[-1][2]
    p.line((mm(0), mm(last) + 4), (y, y), colour=MUTED, lw=0.8, zorder=3)          # the line through the centre
    p.ax.add_patch(Circle((mm(centre), y), radius * scale, facecolor=GREY, edgecolor=MUTED, lw=0.8, zorder=1))
    p.ax.plot([mm(0)], [y], marker='s', ms=4.4, color=INK, ls='', zorder=4)
    p.text(mm(0), y + 2.6, 'home', ha='center')
    p.text(mm(centre), y - 2.4, 'zone', ha='center', va='bottom')
    p.text(mm(centre), y + 2.4, f'radius {RADIUS_M[0]:g} to {RADIUS_M[1]:g} m', ha='center')
    # the ring at which the zone switches on: the arc on the home side
    ring, half = (radius + TRIGGER_M) * scale, 16.0   # the arc is drawn `half` millimetres above and below the line
    angle = math.degrees(math.asin(half / ring))
    p.ax.add_patch(Arc((mm(centre), y), 2 * ring, 2 * ring, theta1=180 - angle, theta2=180 + angle, edgecolor=INK,
                       lw=0.8, ls=(0, (3, 2)), zorder=3))
    # two measures along the line: home to the near edge above it, the ring to the near edge below it
    for y_dim, start in ((y - 4.6, 0.0), (y + 4.6, edge - TRIGGER_M)):
        p.line((mm(start), mm(edge)), (y_dim, y_dim), lw=0.6)
        for x in (mm(start), mm(edge)):
            p.line((x, x), (y_dim - 0.9, y_dim + 0.9), lw=0.6)
    mid = (mm(edge - TRIGGER_M) + mm(edge)) / 2 + 1.0
    p.text(mid, y - 5.9, f'near edge {EDGE_M[0]:g} to {EDGE_M[1]:g} m\nfrom home', ha='center', va='bottom')
    p.text(mid, y + 5.9, f'the zone switches on when\nthe drone first comes\nwithin {TRIGGER_M:g} m of its edge',
           ha='center')
    # the three bands beyond the far edge
    for name, lo, hi in BANDS_M:
        p.ax.add_patch(Rectangle((mm(far + lo), y - 2.3), (hi - lo) * scale, 4.6, facecolor=INK, edgecolor='none',
                                 zorder=4))
        p.text(mm(far + (lo + hi) / 2), y - 3.4, f'{name}\n{lo:g} to {hi:g} m', ha='center', va='bottom')
    p.line((mm(far), mm(far)), (y - 2.3, y + 5.5), lw=0.6)
    p.line((mm(far), mm(last)), (y + 4.6, y + 4.6), lw=0.6)
    for _, lo, hi in BANDS_M:
        for x in (mm(far + lo), mm(far + hi)):
            p.line((x, x), (y + 3.7, y + 5.5), lw=0.6)
    p.text(mm(far) + 1.6, y + 6.6, "the target lies in one of three bands,\nmeasured from the zone's far edge")
    x0, x1 = mm(far + BANDS_M[1][1]) - 3.6, mm(far + BANDS_M[2][2]) + 3.6       # middle and wide together
    p.line((x0, x0, x1, x1), (y - 11.2, y - 12.4, y - 12.4, y - 11.2), lw=0.6)
    p.text((x0 + x1) / 2, y - 13.2, 'distant targets', ha='center', va='bottom')
    # the scale bar
    bar = 10
    x1 = WIDTH - 2.5
    x0 = x1 - bar * scale
    p.line((x0, x1), (y + 12.6, y + 12.6), lw=0.9)
    for end in (x0, x1):
        p.line((end, end), (y + 11.7, y + 13.5), lw=0.9)
    p.text((x0 + x1) / 2, y + 11.2, f'{bar} m', ha='center', va='bottom')


def block(p: Page, top: float) -> None:
    """Panel (c): one block."""
    p.letter(top + 1.0, 'c', 'One block of Study 2')
    y = top + 6.6
    t = p.text(1.2, y + 2.2, f"The block's {('', 'one', 'two', 'three')[LAYOUTS]} layouts, one target in each band:",
               va='center')
    x = p.extent(t)[2] + 2.0
    for name, _, _ in BANDS_M:
        rect = p.box(x, y, 15.5, 4.4)
        p.text(x + 7.75, y + 2.2, name, ha='center', va='center', within=rect)
        x += 17.0
    p.text(x + 0.6, y + 2.2, 'All five arms search on them.', va='center')
    # the grid: one row an arm
    cols, widths, head, row = [1.0], (10.0, 37.0, 30.0, 60.0), 5.4, 5.6
    for w in widths:
        cols.append(cols[-1] + w)
    y += 6.4
    p.text(cols[0] + 1.6, y + head / 2, 'Arm', bold=True, va='center')
    for i, name in enumerate(COLUMNS):
        p.text(cols[i + 1] + 1.6, y + head / 2, name, bold=True, va='center')
    y += head
    grid_top = y
    steps = []
    by_name = {a[0]: a for a in ARMS}
    for r, (arm, *cells) in enumerate(ARMS):
        p.text(cols[0] + 1.6, y + row / 2, arm, bold=True, va='center')
        other = COMPARED_WITH.get(arm)
        for c, words in enumerate(cells):
            first = ARMS[0][c + 1]
            rect = p.box(cols[c + 1], y, widths[c + 1], row, fill=SURFACE if words == first else GREY)
            p.text(cols[c + 1] + 1.6, y + row / 2, words, va='center', within=rect)
            if other and words != by_name[other][c + 1]:
                steps.append((rect, f'{arm} − {other}'))
        y += row
    for rect, name in steps:                         # drawn last, over the thin outlines
        p.box(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1], heavy=True, fill='none', zorder=4)
        p.text(rect[2] - 1.6, (rect[1] + rect[3]) / 2, name, bold=True, ha='right', va='center', within=rect)
    assert [name for _, name in steps] == ['B − A', 'C − B', 'D − C', 'E − B'], steps
    # then the unseen zone flights
    x = cols[-1]
    p.arrow((x + 0.8, (grid_top + y) / 2), (x + 7.0, (grid_top + y) / 2))
    rect = p.box(x + 7.0, grid_top - head, WIDTH - 1.0 - x - 7.0, y - grid_top + head)
    p.text(rect[0] + 1.6, rect[1] + 1.6,
           f'Then, with no\nmodel, every\nadopted procedure\nflies the {HELD_OUT} unseen\nzone flights, '
           f'{PER_BAND} in\neach band, on\nlayouts that no\nsearch used.', within=rect)
    # what the fills and outlines mean, and what the column heads stand for
    y += 2.0
    p.box(1.4, y, 5.2, 3.2, fill=GREY)
    t = p.text(8.2, y + 1.6, "differs from arm A's", va='center')
    x = p.extent(t)[2] + 5.0
    p.box(x, y, 5.2, 3.2, heavy=True)
    p.text(x + 6.8, y + 1.6, 'differs from the arm it is compared with: the one choice that the named comparison changes',
           va='center')
    y += 5.2
    three = ('', 'one', 'two', 'three')
    p.text(1.2, y, f"First request: the block's layouts flown with no procedure in control. Adoption test: the "
                   f"candidate flies the {three[LAYOUTS]} layouts\nand must pass all {three[LAYOUTS]}. Each arm has "
                   f"up to {three[CANDIDATES]} candidates and stops at its first adoption.\nA repair revises the latest "
                   f"failed candidate. Arm E's request shows that candidate's failed flights without its code.\n"
                   f"Arm E was added after the four-arm analysis.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--out', type=Path, default=Path(__file__).with_name('design-overview.svg'))
    a = p.parse_args(argv)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'pdf.fonttype': 42, 'svg.hashsalt': 'paper3-design-overview'})
    page = Page()
    loop(page, 0.0)
    layout(page, 51.5)
    block(page, 95.0)
    page.check()
    edge, radius = MIDDLE
    print(f'panel (b) draws the near edge {edge:g} m from home and the radius {radius:g} m, the middle of '
          f'{EDGE_M[0]:g} to {EDGE_M[1]:g} m and of {RADIUS_M[0]:g} to {RADIUS_M[1]:g} m; the ring is '
          f'{TRIGGER_M:g} m from the edge; bands ' + ', '.join(f'{n} {lo:g} to {hi:g} m' for n, lo, hi in BANDS_M))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    page.fig.savefig(a.out, facecolor=SURFACE, metadata={'Date': None})
    page.fig.savefig(a.out.with_suffix('.png'), dpi=300, facecolor=SURFACE)
    page.fig.savefig(a.out.with_suffix('.pdf'), facecolor=SURFACE, metadata={'CreationDate': None})
    print(f'wrote {a.out}, .png and .pdf, {WIDTH:.0f} mm by {HEIGHT:.0f} mm')


if __name__ == '__main__':
    main()

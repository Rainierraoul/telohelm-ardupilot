"""Draw the experiment and one index-selected illustration from saved outcomes.

Read the frozen analysis and seeds; select reach pair 0 and the lowest common
evaluation seed before reading either outcome. Require identical goals/events,
contiguous true-position samples, and consistent activation/first-sight records.
Draw both paths with equal axes. On the right panel, draw the avoidance margin
written in the adopted source of the run learned without the zone (zone radius
plus a constant read from that source). The figure illustrates one case; no
population estimate is inferred. Save source hashes with the figure inputs.

Usage: python manuscript/figures/flight_evidence.py --records FOLDER
FOLDER contains runs/scored-2, as in the data archive. No experimental import,
simulator, model call or original-record write occurs.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(fig, stem):
    fig.savefig(HERE / (stem + '.svg'), metadata={'Date': None, 'Creator': 'Simon Vajda'})
    fig.savefig(HERE / (stem + '.png'), dpi=300, metadata={'Author': 'Simon Vajda'})
    plt.close(fig)


def design():
    fig, ax = plt.subplots(figsize=(7.2, 3.25))
    ax.set(xlim=(0, 10), ylim=(0, 4.3))
    ax.axis('off')
    ax.text(5, 4.1, 'Same task text, layouts, model settings and three-attempt limit',
            ha='center', va='center', fontsize=10)
    def box(x, y, width, height, label):
        ax.add_patch(Rectangle((x, y), width, height, facecolor='white', edgecolor='0.2', lw=1))
        ax.text(x + width / 2, y + height / 2, label, ha='center', va='center', fontsize=10)
    for y, label in ((2.35, 'Learned with the zone\nZone active in all three\nlearning scenarios'),
                     (0.6, 'Learned without the zone\nSame three layouts,\nzone removed')):
        box(0.05, y, 3.6, 1.25, label)
        ax.add_patch(FancyArrowPatch((3.7, y + .625), (4.4, 2.1), arrowstyle='-|>', mutation_scale=12, color='0.25'))
    box(4.45, 1.45, 2.7, 1.3, 'Adopted procedures\nfly the same 20 fresh\nthreat-zone scenarios')
    ax.add_patch(FancyArrowPatch((7.2, 2.1), (7.8, 2.1), arrowstyle='-|>', mutation_scale=12, color='0.25'))
    box(7.85, 1.45, 2.1, 1.3, 'Goal met: 1\nOtherwise: 0')
    ax.text(7.15, .65, 'Nothing adopted: 20 zeros', ha='center', fontsize=10)
    fig.subplots_adjust(left=.015, right=.99, top=.98, bottom=.03)
    save(fig, 'acquisition-design')


def example(records):
    seeds_file = ROOT / 'protocol/seeds-2.json'
    seeds = json.loads(seeds_file.read_text())
    candidates = seeds['threat_evaluation']
    if isinstance(candidates, dict):
        candidates = candidates['reach']
    seed = min(candidates)
    assert seed == 44001
    files = {arm: records / 'runs/scored-2' / f'threat-reach-b0-{arm}' / 'flights' / f'threat-{seed}' / 'outcome.json'
             for arm in ('threat', 'matched')}
    data = {arm: json.loads(path.read_text()) for arm, path in files.items()}
    left, right = data['threat'], data['matched']
    assert left['goal'] == right['goal'] and left['events'] == right['events']
    assert left['event_starts'] == right['event_starts'] == {'0': 4}
    zone = left['events'][0]
    assert zone[:2] == ['threat', 'g19']
    north, east, radius = zone[3:]
    target_north, target_east = (left['goal'][name] for name in ('target_north_m', 'target_east_m'))
    run = records / 'runs/scored-2/learn-reach-b0-matched/run/library'
    adopted = json.loads((run / 'index.json').read_text())
    sources = sorted((run / 'content').glob('*.json'))
    margin_src = [s for s in sources if 'safe = th.radius_m + ' in json.loads(s.read_text()).get('source', '')]
    assert len(margin_src) == 1
    code = json.loads(margin_src[0].read_text())['source']
    extra = float(code.split('safe = th.radius_m + ')[1].split()[0])
    assert extra == 6.0
    margin = radius + extra
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.95), sharex=True, sharey=True)
    upper = math.ceil((max(s[k] for d in data.values() for s in d['native_steps']
                           for k in ('north_m', 'east_m')) + 3) / 10) * 10
    facts = {}
    for ax, arm, title in zip(axes, ('threat', 'matched'), ('Learned with the zone', 'Learned without the zone')):
        outcome = data[arm]
        steps = outcome['native_steps']
        assert [s['t'] for s in steps] == list(range(1, len(steps) + 1))
        assert all('north_m' in s and 'east_m' in s for s in steps)
        assert min(s['t'] for s in steps if s['threats']) == 5
        ax.add_patch(Circle((east, north), radius, facecolor='0.92', edgecolor='0.45', hatch='///', lw=.9, zorder=0))
        if arm == 'matched':
            ax.add_patch(Circle((east, north), margin, fill=False, edgecolor='0.35', ls=(0, (4, 3)), lw=1, zorder=1))
            ax.text(east + margin * 0.72, north - margin * 0.72 - 1.5, 'margin in\nits code', ha='left', va='top', fontsize=8.5)
        ax.plot([s['east_m'] for s in steps], [s['north_m'] for s in steps], color='0.1', lw=1.4, zorder=2)
        ax.scatter([steps[0]['east_m']], [steps[0]['north_m']], marker='o', s=22, facecolor='white', edgecolor='0.1', zorder=3)
        ax.scatter([target_east], [target_north], marker='x', s=45, color='0.1', lw=1.5, zorder=4)
        if arm == 'matched':
            ax.text(target_east + 1.5, target_north - 1.2, 'target', fontsize=9, va='top',
                    bbox={'facecolor':'white', 'edgecolor':'none', 'pad':0.8})
        else:
            ax.text(target_east + 1.5, target_north + 1.5, 'target', fontsize=9)
        ax.text(east, north - 1, 'threat\nzone', ha='center', va='center', fontsize=9, bbox={'facecolor':'white','edgecolor':'none','pad':1.3})
        label = f"Completed ({outcome['ended_at']} s)" if outcome['goal_met'] else f"Time limit ({outcome['ended_at']} s)"
        ax.set_title(title + '\n' + label, fontsize=11, pad=8)
        ax.set(xlim=(-2, upper), ylim=(-2, upper), xticks=range(0, upper + 1, 10),
               yticks=range(0, upper + 1, 10), xlabel='East of home (m)')
        ax.set_aspect('equal')
        ax.tick_params(labelsize=9)
        ax.spines[['top', 'right']].set_visible(False)
        facts[arm] = {'source':str(files[arm].relative_to(records)), 'sha256':sha(files[arm]),
                      'samples':len(steps), 'end_reason':outcome['end_reason'], 'ended_at':outcome['ended_at'],
                      'goal_met':outcome['goal_met'], 'first_visible_step':5}
    axes[0].set_ylabel('North of home (m)')
    fig.text(.5, .025, 'Lines join recorded true positions; open circles mark the first sample (1 s). Dashed circle: zone radius + 6 m.', ha='center', fontsize=9)
    fig.subplots_adjust(left=.09, right=.99, top=.83, bottom=.16, wspace=.12)
    save(fig, 'hazard-flight-example')
    return {'selection':'reach; lowest pair 0; lowest scheduled shared seed, chosen before inspecting paths',
            'seed':seed, 'seeds_sha256':sha(seeds_file), 'zone_north_east_radius':[north,east,radius],
            'target_north_east':[target_north,target_east], 'activation_step':4, 'flights':facts,
            'margin_m':margin, 'margin_source':str(margin_src[0].relative_to(records)), 'margin_source_sha256':sha(margin_src[0])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=Path, default=ROOT)
    args = parser.parse_args()
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'svg.hashsalt':'paper3-scientific-figures'})
    design()
    facts = example(args.records.resolve())
    facts['script_sha256'] = sha(Path(__file__))
    (HERE / 'FIGURE-EVIDENCE.json').write_text(json.dumps(facts, indent=2) + '\n')
    print('Wrote acquisition design and recorded-flight illustration')


if __name__ == '__main__':
    main()

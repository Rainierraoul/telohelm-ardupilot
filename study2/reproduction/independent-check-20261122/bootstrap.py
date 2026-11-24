"""Independent check, step 2: point estimates, crossed-bootstrap intervals and names.

Input: outcomes.json, written by build_table.py from the raw records.
Output: RESULT.json.

Every implementation choice the protocol leaves open is in CHOICES below and was
fixed before the first run. Nothing here was taken from any other program.
"""
import json
import os
import platform
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = ["reach", "reach3d", "land"]     # generator index 0, 1, 2 (protocol 6.2)
ARMS = ["A", "B", "C", "D"]
BANDS = ["close", "middle", "wide"]
N_BLOCKS = 40
PER_BAND = 8
N_BOOT = 10_000
BOOT_SEED = 20261112
MARGIN_NUM, MARGIN_DEN = 1, 5            # the margin 0.20 as an exact fraction
STEPS = [("C", "B"), ("B", "A"), ("D", "C")]   # C - B is reported first (6.3)

# The five sets of draws, in the protocol's order: all bands, each band, then
# the middle and wide bands together. Each entry: (name, bands drawn).
SETS = [
    ("all", ["close", "middle", "wide"]),
    ("close", ["close"]),
    ("middle", ["middle"]),
    ("wide", ["wide"]),
    ("distant", ["middle", "wide"]),
]

CHOICES = {
    "generator": "numpy.random.default_rng([20261112, 0, task_index]); task_index 0 reach, "
                 "1 reach3d, 2 land. One generator per task, used for nothing else.",
    "sets": "Five complete sets of 10,000 resamples are drawn one after another from the task's "
            "generator: all bands; close; middle; wide; middle and wide together. A set is "
            "finished before the next begins. The middle-only and wide-only sets are drawn and "
            "not used.",
    "calls_within_a_set": "Main reading (per resample): for each resample, first "
                          "rng.integers(0, 40, size=40) for the blocks, then for each band of the "
                          "set in the order close, middle, wide one rng.integers(0, 8, size=8) "
                          "for that band's scenarios.",
    "alternate_calls_within_a_set": "Sensitivity only (set at once): rng.integers(0, 40, "
                                    "size=(10000, 40)) for the blocks of all resamples, then for "
                                    "each band of the set rng.integers(0, 8, size=(10000, 8)).",
    "index_order": "Block index i is block number i. Scenario index j within a band is the j-th "
                   "smallest seed number of that band.",
    "statistic": "A resample's arm mean is the mean over its 40 drawn blocks and its drawn "
                 "scenarios (8 per band, so the bands have equal weight). A contrast is the "
                 "difference of two arm means from the same resample.",
    "pooling": "The pooled contrast of resample r is the mean of the three tasks' contrasts at "
               "resample r of their all-band sets. Every task has 960 cells per arm, so this "
               "equals the difference of means over the 2,880 cells taken together.",
    "which_set_feeds_which_interval": "Per-task steps and pooled steps: the all-band set. "
                                      "D - A close: the close set. D - A distant: the set of "
                                      "middle and wide together.",
    "percentiles": "numpy.percentile with its default linear interpolation, at 2.5 and 97.5 for "
                   "the 95% interval and at 5 and 95 for the 90% interval.",
    "exact_comparisons": "Each resample's contrast is kept as a whole-number numerator over a "
                         "fixed denominator (960 per task, 320 close, 640 distant, 2,880 pooled). "
                         "The percentiles are taken on the numerators, and the strict "
                         "comparisons with 0 and with 0.20 are made on numerators (0.20 is 192, "
                         "64, 128 and 576 of those denominators), so no rounding of a division "
                         "can decide a name.",
    "order_of_naming_rules": "First the three names for nothing to compare, tested on the cells. "
                             "Then, for a pooled step, task-dependence from the three per-task "
                             "95% intervals of the all-band set. Then the four-way table, with "
                             "the larger-than-the-margin label.",
}


def draw_set_per_resample(rng, bands):
    """One set of N_BOOT resamples. Returns block counts (N_BOOT x 40) and scenario
    counts (N_BOOT x 24, zero outside the set's bands)."""
    w = np.zeros((N_BOOT, N_BLOCKS), dtype=np.int64)
    v = np.zeros((N_BOOT, 3 * PER_BAND), dtype=np.int64)
    for r in range(N_BOOT):
        blocks = rng.integers(0, N_BLOCKS, size=N_BLOCKS)
        w[r] = np.bincount(blocks, minlength=N_BLOCKS)
        for band in bands:
            off = BANDS.index(band) * PER_BAND
            scen = rng.integers(0, PER_BAND, size=PER_BAND)
            v[r, off:off + PER_BAND] = np.bincount(scen, minlength=PER_BAND)
    return w, v


def draw_set_at_once(rng, bands):
    """The alternate call order, for the sensitivity check only."""
    blocks = rng.integers(0, N_BLOCKS, size=(N_BOOT, N_BLOCKS))
    w = np.zeros((N_BOOT, N_BLOCKS), dtype=np.int64)
    v = np.zeros((N_BOOT, 3 * PER_BAND), dtype=np.int64)
    rows = np.arange(N_BOOT)[:, None]
    np.add.at(w, (rows, blocks), 1)
    for band in bands:
        off = BANDS.index(band) * PER_BAND
        scen = rng.integers(0, PER_BAND, size=(N_BOOT, PER_BAND))
        np.add.at(v, (rows, off + scen), 1)
    return w, v


def resample_numerators(tables, draw, stream=0):
    """tables: task -> arm -> 40x24 int array. Returns task -> set -> arm -> N_BOOT ints,
    the number of successes among the resampled cells. stream is the middle entry of the
    seed: 0 is the protocol's; any other value is used only by the stream check."""
    out = {}
    for ti, task in enumerate(TASKS):
        rng = np.random.default_rng([BOOT_SEED, stream, ti])
        out[task] = {}
        for name, bands in SETS:
            w, v = draw(rng, bands)
            assert (w.sum(axis=1) == N_BLOCKS).all()
            assert (v.sum(axis=1) == PER_BAND * len(bands)).all()
            out[task][name] = {a: np.einsum("rb,bs,rs->r", w, tables[task][a], v) for a in ARMS}
            if draw is draw_set_per_resample and name == "all" and stream == 0:
                # keep the first resamples' counts for a direct-indexing spot check
                out[task]["_spot"] = (w[:200].copy(), v[:200].copy())
    return out


def pct(x):
    lo95, hi95, lo90, hi90 = np.percentile(np.asarray(x, dtype=np.float64), [2.5, 97.5, 5.0, 95.0])
    return float(lo95), float(hi95), float(lo90), float(hi90)


def classify(lo95, hi95, lo90, hi90, den):
    """Section 6.4's four-way table. All arguments are numerators over den."""
    m = MARGIN_NUM * den / MARGIN_DEN
    assert float(m).is_integer()
    above, below = lo95 > 0, hi95 < 0
    different = above or below
    equivalent = (lo90 > -m) and (hi90 < m)
    if different and not equivalent:
        key = "different_not_equivalent"
        name = "a gain" if above else "a loss"
    elif different and equivalent:
        key = "different_and_equivalent"
        name = ("a gain" if above else "a loss") + " smaller than the margin"
    elif equivalent:
        key = "equivalent_not_different"
        name = "no gain or loss as large as the margin"
    else:
        key = "unresolved"
        name = "unresolved"
    useful_gain = lo95 > m
    useful_loss = hi95 < -m
    if useful_gain:
        name = "a gain larger than the margin"
    if useful_loss:
        name = "a loss larger than the margin"
    return {"key": key, "name": name, "useful_gain": bool(useful_gain),
            "useful_loss": bool(useful_loss)}


def classify_float(lo95, hi95, lo90, hi90):
    """The same table on the divided values, to show whether division could change a name."""
    m = 0.20
    above, below = lo95 > 0, hi95 < 0
    different = above or below
    equivalent = (lo90 > -m) and (hi90 < m)
    if different and not equivalent:
        return "different_not_equivalent"
    if different and equivalent:
        return "different_and_equivalent"
    if equivalent:
        return "equivalent_not_different"
    return "unresolved"


def nothing_to_compare(x_cells, y_cells, n_blocks):
    """The three names for nothing to compare, on the cells that enter the contrast."""
    x = np.asarray(x_cells)
    y = np.asarray(y_cells)
    if not x.any() and not y.any():
        return {"key": "no_success_in_either_arm", "name": "no success in either arm"}
    if x.all() and y.all():
        return {"key": "every_flight_succeeded_in_both_arms",
                "name": "every flight succeeded in both arms"}
    if (x == y).all():
        return {"key": "identical_outcomes",
                "name": f"identical outcomes in all {n_blocks} blocks",
                "n_blocks": n_blocks, "bound_on_share_of_differing_blocks": 1 - 0.05 ** (1 / n_blocks)}
    return None


def interval_record(point_num, boot_num, den, x_cells, y_cells, n_blocks):
    lo95, hi95, lo90, hi90 = pct(boot_num)
    rec = {
        "estimate": point_num / den,
        "estimate_numerator": int(point_num),
        "denominator": int(den),
        "ci95": [lo95 / den, hi95 / den],
        "ci90": [lo90 / den, hi90 / den],
        "ci95_numerators": [lo95, hi95],
        "ci90_numerators": [lo90, hi90],
        "bootstrap_mean": float(np.mean(boot_num)) / den,
        "bootstrap_sd": float(np.std(boot_num, ddof=1)) / den,
        "n_blocks": n_blocks,
    }
    ntc = nothing_to_compare(x_cells, y_cells, n_blocks)
    table = classify(lo95, hi95, lo90, hi90, den)
    rec["four_way_table"] = table
    rec["four_way_key_from_divided_values"] = classify_float(*rec["ci95"], *rec["ci90"])
    rec["division_changes_the_key"] = rec["four_way_key_from_divided_values"] != table["key"]
    if ntc is not None:
        rec["key"], rec["name"] = ntc["key"], ntc["name"]
        rec["nothing_to_compare"] = ntc
    else:
        rec["key"], rec["name"] = table["key"], table["name"]
    # The smallest move of one interval end, across 0 or across +-0.20, that would change
    # the four-way key or the larger-than-the-margin label. Found by trying each move.
    m = MARGIN_NUM * den / MARGIN_DEN
    here = [lo95, hi95, lo90, hi90]
    now = (table["key"], table["useful_gain"], table["useful_loss"])
    best = None
    for i in range(4):
        for thr in (0.0, m, -m):
            for side in (-0.5, 0.5):          # half a cell to either side of the threshold
                moved = list(here)
                moved[i] = thr + side
                t2 = classify(*moved, den)
                if (t2["key"], t2["useful_gain"], t2["useful_loss"]) != now:
                    d = abs(here[i] - thr)
                    best = d if best is None else min(best, d)
    rec["nearest_threshold_distance"] = best / den
    return rec


def sign(n):
    return "+" if n > 0 else ("-" if n < 0 else "0")


def compute(tables, boots):
    res = {"pooled_steps": {}, "per_task_steps": {}, "rq4": {}}
    den_task = N_BLOCKS * 3 * PER_BAND          # 960
    close = slice(0, PER_BAND)
    distant = slice(PER_BAND, 3 * PER_BAND)

    for x, y in STEPS:
        label = f"{x}-{y}"
        per_task = {}
        pooled_boot = np.zeros(N_BOOT, dtype=np.int64)
        pooled_point = 0
        for task in TASKS:
            bx, by = boots[task]["all"][x], boots[task]["all"][y]
            point = int(tables[task][x].sum() - tables[task][y].sum())
            per_task[task] = interval_record(point, bx - by, den_task,
                                             tables[task][x], tables[task][y], N_BLOCKS)
            pooled_boot += bx - by
            pooled_point += point
        res["per_task_steps"][label] = per_task

        xs = np.concatenate([tables[t][x] for t in TASKS])
        ys = np.concatenate([tables[t][y] for t in TASKS])
        rec = interval_record(pooled_point, pooled_boot, 3 * den_task, xs, ys, 3 * N_BLOCKS)

        # task-dependence: one task's 95% interval wholly above 0 and another's wholly below
        above = [t for t in TASKS if per_task[t]["ci95_numerators"][0] > 0]
        below = [t for t in TASKS if per_task[t]["ci95_numerators"][1] < 0]
        task_dependent = bool(above) and bool(below)
        signs = {t: sign(per_task[t]["estimate_numerator"]) for t in TASKS}
        signs_differ = "+" in signs.values() and "-" in signs.values()
        rec["per_task_95_wholly_above_0"] = above
        rec["per_task_95_wholly_below_0"] = below
        rec["task_dependent"] = task_dependent
        rec["per_task_signs"] = signs
        rec["per_task_signs_differ"] = signs_differ
        rec["pooled_name_before_task_dependence"] = rec["name"]
        if "nothing_to_compare" in rec:
            reading = rec["name"]
        elif task_dependent:
            rec["key"], rec["name"] = "task_dependent", "task-dependent"
            if not signs_differ:
                raise SystemExit(f"{label}: task-dependent with per-task signs that do not differ")
            up = [t for t in TASKS if signs[t] == "+"]
            down = [t for t in TASKS if signs[t] == "-"]
            reading = f"the step raised success on {', '.join(up)} and lowered it on {', '.join(down)}"
        elif rec["key"] in ("different_not_equivalent", "different_and_equivalent"):
            word = "gain" if rec["ci95_numerators"][0] > 0 else "loss"
            reading = f"a pooled {word} over these three tasks"
            if signs_differ:
                other = "-" if word == "gain" else "+"
                odd = [t for t in TASKS if signs[t] == other]
                reading += f"; {', '.join(odd)} has the other sign and is named beside it with its interval"
        elif rec["key"] == "equivalent_not_different":
            if signs_differ:
                reading = ("not settled: the average is near zero while the tasks' estimates point "
                           "in opposite directions")
            else:
                reading = "no pooled gain or loss as large as the margin over these three tasks"
        else:
            reading = "unresolved" + (", with per-task signs that differ" if signs_differ else "")
        rec["reading_with_per_task_estimates"] = reading
        res["pooled_steps"][label] = rec

    for task in TASKS:
        d, a = tables[task]["D"], tables[task]["A"]
        bc = boots[task]["close"]
        bd = boots[task]["distant"]
        res["rq4"][task] = {
            "close": interval_record(int(d[:, close].sum() - a[:, close].sum()),
                                     bc["D"] - bc["A"], N_BLOCKS * PER_BAND,
                                     d[:, close], a[:, close], N_BLOCKS),
            "distant": interval_record(int(d[:, distant].sum() - a[:, distant].sum()),
                                       bd["D"] - bd["A"], N_BLOCKS * 2 * PER_BAND,
                                       d[:, distant], a[:, distant], N_BLOCKS),
        }
    return res


def walk_intervals(res):
    for label, rec in res["pooled_steps"].items():
        yield f"pooled {label}", rec
    for label, per_task in res["per_task_steps"].items():
        for task, rec in per_task.items():
            yield f"{task} {label}", rec
    for task, pair in res["rq4"].items():
        for band, rec in pair.items():
            yield f"{task} D-A {band}", rec


def main():
    with open(os.path.join(HERE, "outcomes.json"), "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    tables = {}
    arm_means = {}
    for task in TASKS:
        t = raw[task]
        assert t["bands"] == [b for b in BANDS for _ in range(PER_BAND)]
        tables[task] = {a: np.array(t["cells"][a], dtype=np.int64) for a in ARMS}
        arm_means[task] = {}
        for a in ARMS:
            y = tables[task][a]
            assert y.shape == (N_BLOCKS, 3 * PER_BAND) and set(np.unique(y)) <= {0, 1}
            ad = t["adopted"][a]
            # an arm that adopted nothing has 0 in all 24 cells of its block
            assert all(ad[b] or not y[b].any() for b in range(N_BLOCKS))
            arm_means[task][a] = {
                "mean": int(y.sum()) / y.size,
                "successes": int(y.sum()),
                "cells": int(y.size),
                "blocks_adopted": int(sum(ad)),
                "blocks": N_BLOCKS,
                "mean_close": int(y[:, :8].sum()) / (N_BLOCKS * 8),
                "successes_close": int(y[:, :8].sum()),
                "mean_distant": int(y[:, 8:].sum()) / (N_BLOCKS * 16),
                "successes_distant": int(y[:, 8:].sum()),
            }

    boots = resample_numerators(tables, draw_set_per_resample)

    # spot check: the first 200 all-band resamples by direct indexing of the cells
    for task in TASKS:
        w, v = boots[task].pop("_spot")
        for r in range(200):
            bi = np.repeat(np.arange(N_BLOCKS), w[r])
            si = np.repeat(np.arange(3 * PER_BAND), v[r])
            for a in ARMS:
                assert tables[task][a][np.ix_(bi, si)].sum() == boots[task]["all"][a][r]

    res = compute(tables, boots)

    # sensitivity to the one choice that moves the random stream: the call order in a set
    alt = compute(tables, resample_numerators(tables, draw_set_at_once))
    main_iv = dict(walk_intervals(res))
    alt_iv = dict(walk_intervals(alt))
    shifts = {}
    name_changes = []
    for k, rec in main_iv.items():
        other = alt_iv[k]
        ends = rec["ci95"] + rec["ci90"]
        ends_alt = other["ci95"] + other["ci90"]
        shifts[k] = max(abs(p - q) for p, q in zip(ends, ends_alt))
        if rec["key"] != other["key"] or rec["name"] != other["name"]:
            name_changes.append({"interval": k, "main": rec["name"], "alternate": other["name"]})
    largest = max(shifts.values())
    near = [k for k, rec in main_iv.items()
            if "nothing_to_compare" not in rec and rec["nearest_threshold_distance"] <= largest]
    sensitivity = {
        "what": "The same analysis with the alternate call order inside a set (CHOICES: "
                "alternate_calls_within_a_set). Same seed, same sets, same percentiles.",
        "largest_shift_of_any_interval_end": largest,
        "shift_by_interval": shifts,
        "names_that_change": name_changes,
        "intervals_with_an_end_nearer_a_threshold_than_the_largest_shift": near,
        "alternate_intervals": {k: {"ci95": v["ci95"], "ci90": v["ci90"], "name": v["name"],
                                    "key": v["key"]} for k, v in alt_iv.items()},
    }

    # How far can an interval end move when only the random stream changes? Twenty other
    # streams, seeded [20261112, 1001..1020, task_index], main call order. These are not
    # the protocol's draws and replace nothing; they show the size of the resampling noise
    # that two correct programs with different random-number calls would differ by.
    n_streams = 20
    ends = {k: [] for k in main_iv}
    names = {k: {} for k in main_iv}
    for s in range(1001, 1001 + n_streams):
        other = dict(walk_intervals(compute(tables, resample_numerators(
            tables, draw_set_per_resample, stream=s))))
        for k, rec in other.items():
            ends[k].append(rec["ci95"] + rec["ci90"])
            names[k][rec["name"]] = names[k].get(rec["name"], 0) + 1
    stream_check = {
        "what": "The same analysis on 20 other random streams, seeds [20261112, 1001..1020, "
                "task_index]. For each interval: the lowest and highest value each end took, "
                "and how many streams gave each name.",
        "streams": n_streams,
        "by_interval": {},
        "intervals_whose_name_is_not_the_same_on_every_stream": [],
    }
    for k in main_iv:
        e = np.array(ends[k])
        stream_check["by_interval"][k] = {
            "ci95_low_range": [float(e[:, 0].min()), float(e[:, 0].max())],
            "ci95_high_range": [float(e[:, 1].min()), float(e[:, 1].max())],
            "ci90_low_range": [float(e[:, 2].min()), float(e[:, 2].max())],
            "ci90_high_range": [float(e[:, 3].min()), float(e[:, 3].max())],
            "largest_distance_of_an_end_from_the_main_run": float(np.abs(
                e - np.array(main_iv[k]["ci95"] + main_iv[k]["ci90"])).max()),
            "names": names[k],
        }
        if list(names[k]) != [main_iv[k]["name"]]:
            stream_check["intervals_whose_name_is_not_the_same_on_every_stream"].append(k)

    out = {
        "what": "Independent recomputation of the nine intervals of PROTOCOL-3 sections 6.2 to "
                "6.4 from the raw records of scored-20261120-S.",
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "platform": platform.platform()},
        "choices": CHOICES,
        "outcome_field": "goal_met in each flight's outcome.json",
        "margin": 0.20,
        "resamples": N_BOOT,
        "seed": BOOT_SEED,
        "arm_means": arm_means,
        "pooled_steps": res["pooled_steps"],
        "per_task_steps": res["per_task_steps"],
        "rq4": res["rq4"],
        "division_changes_any_key": any(r["division_changes_the_key"] for r in main_iv.values()),
        "sensitivity_to_call_order": sensitivity,
        "stream_check": stream_check,
    }
    with open(os.path.join(HERE, "RESULT.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    def row(k, r):
        return (f"{k:22s} {r['estimate']:+.4f}  95% [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}]  "
                f"90% [{r['ci90'][0]:+.4f}, {r['ci90'][1]:+.4f}]  {r['name']}")
    for task in TASKS:
        for a in ARMS:
            m = arm_means[task][a]
            print(f"{task:8s} {a}  {m['mean']:.4f} ({m['successes']}/960)  adopted {m['blocks_adopted']}/40")
    for k, r in main_iv.items():
        print(row(k, r))
    for label, r in res["pooled_steps"].items():
        print(label, "| task-dependent:", r["task_dependent"], "| signs:", r["per_task_signs"],
              "|", r["reading_with_per_task_estimates"])
    print("largest shift under the alternate call order:", largest)
    print("names that change:", name_changes)
    print("ends nearer a threshold than that shift:", near)
    print("division changes any key:", out["division_changes_any_key"])
    print("stream check, names not constant:",
          {k: stream_check["by_interval"][k]["names"]
           for k in stream_check["intervals_whose_name_is_not_the_same_on_every_stream"]})
    print("stream check, largest distance of any end from the main run:",
          max(v["largest_distance_of_an_end_from_the_main_run"]
              for v in stream_check["by_interval"].values()))
    print("nearest threshold distance by interval:")
    for k, r in main_iv.items():
        print(f"  {k:22s} {r['nearest_threshold_distance']:.4f}")


if __name__ == "__main__":
    sys.exit(main())

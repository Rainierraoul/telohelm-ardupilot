"""Independent check, step 3: recompute by a second, simpler route and compare.

Part 1, point estimates. Plain counting with whole numbers and fractions, no numpy and
no array from the first route. It reads arms.json and each evaluation folder's
summary.json (the band counts), where the first route read every flight's outcome.json.

Part 2, intervals. The cells are read again, this time from results.jsonl. The same
random-number calls are made, but each resample is scored by picking the drawn rows and
columns out of the table and counting, where the first route multiplied count vectors.
The percentiles are computed by hand from the sorted values.

Compares both parts with RESULT.json and writes SELFCHECK.json.
"""
import json
import math
import os
import sys
from fractions import Fraction

DATA = ("/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/"
        "scored-20261120-S-extract/data/runs")
HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = ["reach", "reach3d", "land"]
ARMS = "ABCD"
BANDS = ["close", "middle", "wide"]


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def part1(result):
    """Point estimates by plain counting from summary.json."""
    mismatches = []
    checked = 0
    count = {}       # (task, arm, 'close'|'distant') -> successes
    adopted = {}     # (task, arm) -> blocks adopted
    for task in TASKS:
        root = os.path.join(DATA, "scored-20261120-S-" + task)
        for arm in ARMS:
            count[task, arm, "close"] = 0
            count[task, arm, "distant"] = 0
            adopted[task, arm] = 0
        for block in range(40):
            arms = load(os.path.join(root, "learn3-%s-b%d" % (task, block), "arms.json"))["arms"]
            for arm in ARMS:
                if arms[arm]["adopted"] is not True:
                    continue                      # adopted nothing: 0 on all 24 flights
                adopted[task, arm] += 1
                folder = "threat3-%s-b%d-%s" % (task, block, arms[arm]["source_sha256"])
                fam = load(os.path.join(root, folder, "flights", "summary.json"))["families"]
                for band in BANDS:
                    if fam["threat-" + band]["of"] != 8:
                        raise SystemExit("%s: %s is not of 8" % (folder, band))
                count[task, arm, "close"] += fam["threat-close"]["met"]
                count[task, arm, "distant"] += fam["threat-middle"]["met"] + fam["threat-wide"]["met"]

    def same(label, mine, theirs):
        nonlocal checked
        checked += 1
        if isinstance(mine, Fraction):
            ok = Fraction(theirs["estimate_numerator"], theirs["denominator"]) == mine \
                and abs(float(mine) - theirs["estimate"]) < 1e-15
        else:
            ok = mine == theirs
        if not ok:
            mismatches.append({"what": label, "second_route": str(mine), "first_route": theirs})

    table = {}
    for task in TASKS:
        for arm in ARMS:
            total = count[task, arm, "close"] + count[task, arm, "distant"]
            first = result["arm_means"][task][arm]
            same("%s arm %s successes" % (task, arm), total, first["successes"])
            same("%s arm %s blocks adopted" % (task, arm), adopted[task, arm], first["blocks_adopted"])
            checked += 1
            if abs(float(Fraction(total, 960)) - first["mean"]) > 1e-15:
                mismatches.append({"what": "%s arm %s mean" % (task, arm)})
            table["%s %s" % (task, arm)] = {"successes": total, "of": 960,
                                           "mean": float(Fraction(total, 960)),
                                           "blocks_adopted": adopted[task, arm]}

    def mean(task, arm, part):
        if part == "all":
            return Fraction(count[task, arm, "close"] + count[task, arm, "distant"], 960)
        return Fraction(count[task, arm, part], 320 if part == "close" else 640)

    estimates = {}
    for x, y in (("C", "B"), ("B", "A"), ("D", "C")):
        label = "%s-%s" % (x, y)
        pooled = sum(mean(t, x, "all") - mean(t, y, "all") for t in TASKS) / 3
        same("pooled " + label, pooled, result["pooled_steps"][label])
        estimates["pooled " + label] = float(pooled)
        for t in TASKS:
            d = mean(t, x, "all") - mean(t, y, "all")
            same("%s %s" % (t, label), d, result["per_task_steps"][label][t])
            estimates["%s %s" % (t, label)] = float(d)
    for t in TASKS:
        for part in ("close", "distant"):
            d = mean(t, "D", part) - mean(t, "A", part)
            same("%s D-A %s" % (t, part), d, result["rq4"][t][part])
            estimates["%s D-A %s" % (t, part)] = float(d)
    return {"values_compared": checked, "mismatches": mismatches,
            "arm_table": table, "estimates": estimates}


def percentile(sorted_values, q):
    """Linear interpolation between the two nearest order statistics."""
    h = (len(sorted_values) - 1) * q / 100.0
    lo = math.floor(h)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (h - lo) * (sorted_values[hi] - sorted_values[lo])


def part2(result):
    """Intervals by direct selection of the drawn cells."""
    import numpy as np
    n_boot = 10000
    sets = [("all", [0, 1, 2]), ("close", [0]), ("middle", [1]), ("wide", [2]), ("distant", [1, 2])]
    diffs = {}       # (task, set, 'X-Y') -> list of numerators
    for ti, task in enumerate(TASKS):
        root = os.path.join(DATA, "scored-20261120-S-" + task)
        # the table, from results.jsonl
        y = {arm: np.zeros((40, 24), dtype=np.int64) for arm in ARMS}
        for block in range(40):
            arms = load(os.path.join(root, "learn3-%s-b%d" % (task, block), "arms.json"))["arms"]
            for arm in ARMS:
                sha = arms[arm]["source_sha256"]
                if sha is None:
                    continue
                path = os.path.join(root, "threat3-%s-b%d-%s" % (task, block, sha),
                                    "flights", "results.jsonl")
                with open(path, "r", encoding="utf-8") as fh:
                    rows = [json.loads(line) for line in fh if line.strip()]
                by_band = {b: sorted((r["seed"], r["goal_met"]) for r in rows
                                     if r["family"] == "threat-" + b) for b in BANDS}
                col = 0
                for b in BANDS:
                    if len(by_band[b]) != 8:
                        raise SystemExit("%s: %d rows in band %s" % (path, len(by_band[b]), b))
                    for _seed, met in by_band[b]:
                        y[arm][block, col] = 1 if met is True else 0
                        col += 1
        rng = np.random.default_rng([20261112, 0, ti])
        for name, bands in sets:
            acc = {"C-B": [], "B-A": [], "D-C": [], "D-A": []}
            for _ in range(n_boot):
                blocks = rng.integers(0, 40, size=40)
                cols = []
                for b in bands:
                    cols.extend((8 * b + rng.integers(0, 8, size=8)).tolist())
                s = {arm: int(y[arm][blocks][:, cols].sum()) for arm in ARMS}
                acc["C-B"].append(s["C"] - s["B"])
                acc["B-A"].append(s["B"] - s["A"])
                acc["D-C"].append(s["D"] - s["C"])
                acc["D-A"].append(s["D"] - s["A"])
            for k, v in acc.items():
                diffs[task, name, k] = v

    def ends(values, den):
        v = sorted(values)
        return [percentile(v, q) / den for q in (2.5, 97.5, 5.0, 95.0)]

    mismatches = []
    largest = 0.0
    compared = 0
    out = {}

    def same(label, mine, rec):
        nonlocal largest, compared
        theirs = rec["ci95"] + rec["ci90"]
        gap = max(abs(a - b) for a, b in zip(mine, theirs))
        largest = max(largest, gap)
        compared += 4
        out[label] = {"ci95": mine[:2], "ci90": mine[2:]}
        if gap > 1e-12:
            mismatches.append({"what": label, "second_route": mine, "first_route": theirs})

    for step in ("C-B", "B-A", "D-C"):
        pooled = [sum(diffs[t, "all", step][r] for t in TASKS) for r in range(n_boot)]
        same("pooled " + step, ends(pooled, 2880), result["pooled_steps"][step])
        for t in TASKS:
            same("%s %s" % (t, step), ends(diffs[t, "all", step], 960),
                 result["per_task_steps"][step][t])
    for t in TASKS:
        same("%s D-A close" % t, ends(diffs[t, "close", "D-A"], 320), result["rq4"][t]["close"])
        same("%s D-A distant" % t, ends(diffs[t, "distant", "D-A"], 640), result["rq4"][t]["distant"])
    return {"interval_ends_compared": compared, "largest_difference": largest,
            "mismatches": mismatches, "intervals": out}


def main():
    result = load(os.path.join(HERE, "RESULT.json"))
    p1 = part1(result)
    p2 = part2(result)
    out = {"point_estimates_by_plain_counting": p1, "intervals_by_direct_selection": p2,
           "agree": not p1["mismatches"] and not p2["mismatches"]}
    with open(os.path.join(HERE, "SELFCHECK.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("part 1: %d values compared, %d mismatches" % (p1["values_compared"], len(p1["mismatches"])))
    print("part 2: %d interval ends compared, largest difference %.3g, %d mismatches"
          % (p2["interval_ends_compared"], p2["largest_difference"], len(p2["mismatches"])))
    for m in p1["mismatches"] + p2["mismatches"]:
        print("  MISMATCH", m)
    print("agree:", out["agree"])


if __name__ == "__main__":
    sys.exit(main())

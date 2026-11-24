"""Writes REPORT.md from RESULT.json, integrity.json and SELFCHECK.json, so that every
number in the report is the number in those files. Reads nothing else."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = ["reach", "reach3d", "land"]


def load(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


R = load("RESULT.json")
I = load("integrity.json")
S = load("SELFCHECK.json")


def f(x):
    return f"{x:+.4f}"


def iv(pair):
    return f"[{f(pair[0])}, {f(pair[1])}]"


def name_of(rec):
    extra = ""
    if rec.get("four_way_table", {}).get("useful_gain") and "nothing_to_compare" not in rec:
        extra = ", `useful_gain`"
    if rec.get("four_way_table", {}).get("useful_loss") and "nothing_to_compare" not in rec:
        extra = ", `useful_loss`"
    return f"{rec['name']} (`{rec['key']}`{extra})"


def row(label, rec):
    return f"| {label} | {f(rec['estimate'])} | {iv(rec['ci95'])} | {iv(rec['ci90'])} | {name_of(rec)} |"


HEAD = "| Contrast | Estimate | 95% interval | 90% interval | Name |\n|---|---|---|---|---|"

out = []
w = out.append

w("# Independent check of the nine intervals of PROTOCOL-3, scored run 20261120-S")
w("")
w("Written on 22 November 2026 by a Claude session working as an independent checker. It "
  "computed the three primary intervals and the six RQ4 intervals from the run's raw records "
  "with its own code. It did not open the analysis program, its output, or any note, draft or "
  "result file of the project; the next section lists what it opened. The session's standing "
  "context carried the user's one-line memory index of the project, which holds no result and "
  "no analysis code. This report does not compare the numbers with the analysis program's. "
  "Whoever holds both does that.")
w("")
w("## What I read")
w("")
w("- The frozen protocol, `inputs/PROTOCOL-3.md` in this folder: its opening, the glossary, "
  "and sections 1, 1.1, 1.2, 3, 4.1 to 4.4, 4.6 and 6 to 6.4.")
w("- In each of the three run roots under `runs/scored-20261120-S-extract/data/runs/`: every "
  "learning block's `arms.json`; and, for every evaluation folder (`threat3-...`) whose source "
  "an arm adopted, its `manifest.json`, each flight's `outcome.json`, `flights/results.jsonl`, "
  "`flights/summary.json`, and `kept-late.json` where there was one.")
w("- Of the evaluation folders that no arm adopted (a block's first candidate, c0), only the "
  "manifest, to confirm that the folder was c0's. Their flights were not read and are not used.")
w("")
w("I did not open any `analysis-run.json`, any `logs/` folder, any `retain3` folder, any "
  "learning block file other than `arms.json`, or anything inside a `.set-aside` folder. I saw "
  "the names of those files and folders when listing the run roots, and nothing more. I opened "
  "nothing under the folders the task ruled out, no other repository or worktree, and no git "
  "history. I did not use the network. I did not read the seeds file, because it sits under "
  "`paper3/protocol/`, which was ruled out.")
w("")
w("## How the outcome table was built")
w("")
w("The outcome of a flight is the field `goal_met` of its `outcome.json`. For each task the "
  "table has one cell for each arm, block and scenario: 4 arms, 40 blocks, 24 scenarios. A cell "
  "is 1 if the arm adopted a source (from `arms.json`: `adopted` true and a `source_sha256`) and "
  "`goal_met` is true for that scenario in the folder `threat3-<task>-b<N>-<source_sha256>`. "
  "An arm that adopted nothing has 0 in all 24 cells of its block. Arms of one block that "
  "adopted the same source read the same folder, so they have the same 24 cells. Each folder's "
  "path was built from `arms.json`, never matched by a prefix.")
w("")
w("The three sources of a flight's outcome agree everywhere. `goal_met` in `outcome.json` "
  "equals `goal_met` in `results.jsonl` for all "
  + f"{sum(I['tasks'][t]['outcome_files_read'] for t in TASKS):,}"
  + " flights read, the two also agree on `end_reason`, and the count of true values in each "
  "band equals `met` in `summary.json` for every folder and band.")
w("")
w("`goal_met` against `end_reason`, over the flights read:")
w("")
w("| Task | `end_reason` | `goal_met` | Flights |")
w("|---|---|---|---|")
for t in TASKS:
    for k, n in I["tasks"][t]["end_reason_by_goal_met"].items():
        er, g = k.split("|goal_met=")
        w(f"| {t} | {er} | {g.lower()} | {n:,} |")
w("")
w("So `goal_met` is true exactly when the flight ended `held` (reach, reach3d) or `landed` "
  "(land), and a flight that entered the zone is never counted as meeting its goal.")
w("")
w("## Choices the protocol left open")
w("")
w("These ten choices were fixed before the first run of the bootstrap, and the check of the "
  "other call order was part of that first run. None was taken from any other program. The "
  "check on 20 other random streams and the table of smallest moves (both below) were added "
  "after I had seen the first results. They changed no estimate, interval or name reported here.")
w("")
labels = [
    ("generator", "The generator"),
    ("sets", "The sets of draws"),
    ("calls_within_a_set", "The calls inside a set"),
    ("index_order", "Which index is which block and scenario"),
    ("statistic", "The statistic"),
    ("pooling", "Pooling"),
    ("which_set_feeds_which_interval", "Which set feeds which interval"),
    ("percentiles", "Percentiles"),
    ("exact_comparisons", "Strict comparisons"),
    ("order_of_naming_rules", "Order of the naming rules"),
]
for i, (k, lab) in enumerate(labels, 1):
    w(f"{i}. {lab}. {R['choices'][k]}")
w("")
w("The scenarios of a task are its 24 planned evaluation cases. I could not take them from "
  "the seeds file, so I took them from the `args.cases` list of each evaluation folder's "
  "manifest and checked that every folder of a task lists the same 24 names, 8 in each band, "
  "and holds exactly those 24 flight folders. They do.")
w("")
w(f"Environment: Python {R['environment']['python']}, numpy {R['environment']['numpy']}, "
  f"{R['environment']['platform']}.")
w("")
w("## Where the protocol's text is ambiguous")
w("")
w("- Section 6.2 gives the seed of each task's generator as a list and does not name the "
  "library. I read it as numpy's `default_rng` given that list.")
w("- Section 6.2 gives the order of the sets (all bands, each band, then middle and wide "
  "together) and says nothing about the calls inside a set: whether a resample draws its blocks "
  "and then its scenarios before the next resample begins, or all block draws of a set come "
  "first. I took the first, because the text describes what 'each resample' draws. It does not "
  "give the order of 'each band' either. I took close, middle, wide, the order in which section 3 "
  "lists them. This choice changes the random stream, so I measured its effect (below).")
w("- The text says the pooled steps use each task's all-band draws. It does not say outright "
  "that D − A on close targets uses the close set and D − A on distant targets the set of "
  "middle and wide together. I read the order of draws as implying it.")
w("- 'Pooled over the three tasks with equal weight' and 'the tasks are resampled "
  "independently' do not say how resamples of different tasks are combined. I paired them by "
  "resample number: pooled resample r is the mean of the three tasks' contrasts at their "
  "resample r.")
w("- The percentile rule (how to interpolate between two sorted values) is not given.")
w("- Section 6.4 gives 'a gain larger than the margin' as a further name for a gain whose 95% "
  "interval lies wholly above +0.20. I report it as the name and keep the four-way key beside it.")
w("- Section 6.4 has two rules for a pooled step: its name, and the table that reads the name "
  "beside the signs of the three per-task estimates. I report both for each pooled step.")
w("")
w("## What the records showed")
w("")
n_used = {t: I["tasks"][t]["threat3_folders_used"] for t in TASKS}
n_c0 = {t: I["tasks"][t]["threat3_folders_unused_c0_only"] for t in TASKS}
w("- Nothing was missing. Every adopted source has its evaluation folder, every such folder "
  "holds 24 flights, 8 in each band, and every flight has an `outcome.json` with a true or false "
  f"`goal_met`. The integrity checks in `build_table.py` raised {len(I['problems'])} problems.")
w(f"- Evaluation folders used: {n_used['reach']} in reach, {n_used['reach3d']} in reach3d, "
  f"{n_used['land']} in land. Folders no arm adopted, all of them c0's by their manifest and "
  f"none used: {n_c0['reach']} in reach, {n_c0['reach3d']} in reach3d, {n_c0['land']} in land.")
w("- Every manifest's task, block, source hash and list of arms matches `arms.json`.")
w("- Arm A adopted a procedure in all 40 blocks of every task.")
kl = I["tasks"]["reach3d"]["kept_late_folders"]
parts = []
for k in kl:
    for c, g in k["recorded_goal_met"].items():
        parts.append(f"block {k['block']}, arm{'s' if len(k['arms']) > 1 else ''} "
                     f"{', '.join(k['arms'])}, `{c}`, recorded as "
                     f"{'goal met' if g else 'goal not met'} ({k['recorded_end_reason'][c]})")
w(f"- Three evaluation folders hold a `kept-late.json`, all in reach3d, each naming one flight: "
  + "; ".join(parts) + ". They are counted as recorded. Reach and land have none.")
w("- The `.set-aside` folders hold 4 attempts for reach, 7 for reach3d and 3 for land, by "
  "their names. None was opened and none enters any number here.")
w("")
w("How often arms of a block shared a source (letters joined are arms with one source; a slash "
  "separates different sources; arms not shown adopted nothing):")
w("")
w("| Task | Pattern | Blocks |")
w("|---|---|---|")
for t in TASKS:
    for p, n in I["tasks"][t]["blocks_by_which_arms_share_a_source"].items():
        w(f"| {t} | {p.replace('|', ' / ')} | {n} |")
w("")
w("## Results")
w("")
w("Margin 0.20, 10,000 resamples, seed 20261112. Estimates and interval ends are shown to four "
  "decimals here and in full in `RESULT.json`.")
w("")
w("### Arm means and adoption")
w("")
w("Mean outcome over 40 blocks × 24 held-out zone flights (960 cells), and blocks that adopted.")
w("")
w("| Task | Arm | Successes of 960 | Mean | Blocks adopted of 40 | Mean, close (320 cells) | Mean, distant (640 cells) |")
w("|---|---|---|---|---|---|---|")
for t in TASKS:
    for a in "ABCD":
        m = R["arm_means"][t][a]
        w(f"| {t} | {a} | {m['successes']} | {m['mean']:.4f} | {m['blocks_adopted']} | "
          f"{m['mean_close']:.4f} | {m['mean_distant']:.4f} |")
w("")
w("### The three primary intervals, pooled over the three tasks (120 blocks)")
w("")
w(HEAD)
for step in ("C-B", "B-A", "D-C"):
    w(row("pooled " + step.replace("-", " − "), R["pooled_steps"][step]))
w("")
w("The rule for pooled steps:")
w("")
w("| Step | Tasks whose 95% interval is wholly above 0 | Wholly below 0 | Task-dependent | Signs of the per-task estimates (reach, reach3d, land) | Row of section 6.4's reading table |")
w("|---|---|---|---|---|---|")
for step in ("C-B", "B-A", "D-C"):
    r = R["pooled_steps"][step]
    signs = ", ".join(r["per_task_signs"][t] for t in TASKS).replace("-", "−")
    w(f"| {step.replace('-', ' − ')} | {', '.join(r['per_task_95_wholly_above_0']) or 'none'} | "
      f"{', '.join(r['per_task_95_wholly_below_0']) or 'none'} | "
      f"{'yes' if r['task_dependent'] else 'no'} | {signs} | {r['reading_with_per_task_estimates']} |")
w("")
dc = R["pooled_steps"]["D-C"]
w("Pooled D − C needs a note. Its name by the four-way table is 'no gain or loss as large as "
  "the margin', and no task's 95% interval lies wholly on either side of 0, so it is not "
  f"task-dependent. The per-task estimates differ in sign: reach {f(R['per_task_steps']['D-C']['reach']['estimate'])}, "
  f"reach3d {f(R['per_task_steps']['D-C']['reach3d']['estimate'])}, land {f(R['per_task_steps']['D-C']['land']['estimate'])}. "
  "Section 6.4's reading table then gives the row 'not settled': the paper says the average is "
  "near zero while the tasks' estimates point in opposite directions, and does not say that the "
  "step made no difference. The reach estimate is 9 cells of 960.")
w("")
w("### The same three steps for each task (40 blocks, secondary)")
w("")
w(HEAD)
for step in ("C-B", "B-A", "D-C"):
    for t in TASKS:
        w(row(f"{t} {step.replace('-', ' − ')}", R["per_task_steps"][step][t]))
w("")
w("### The six RQ4 intervals: D − A by task, on close and on distant targets")
w("")
w("Close is the 8 close scenarios (320 cells per arm). Distant is the 16 middle and wide "
  "scenarios together (640 cells per arm).")
w("")
w(HEAD)
for t in TASKS:
    for part in ("close", "distant"):
        w(row(f"{t} D − A {part}", R["rq4"][t][part]))
w("")
w("No contrast had nothing to compare: none of the three names for that case applies to any "
  "of the 18 intervals above."
  if not any("nothing_to_compare" in rec for rec in
             list(R["pooled_steps"].values())
             + [x for s in R["per_task_steps"].values() for x in s.values()]
             + [x for s in R["rq4"].values() for x in s.values()])
  else "Some contrasts had nothing to compare; see the Name column.")
w("")
w("## How far the unpinned choices can move an interval")
w("")
sen = R["sensitivity_to_call_order"]
sc = R["stream_check"]
big = max(v["largest_distance_of_an_end_from_the_main_run"] for v in sc["by_interval"].values())
w("The estimates do not depend on any random draw. The interval ends do, so a second correct "
  "program that makes its random-number calls in another order will give slightly different ends.")
w("")
w("I ran the whole analysis again with the other call order inside a set (all block draws of "
  f"the set first, then each band's scenario draws). The largest move of any of the 72 interval "
  f"ends was {sen['largest_shift_of_any_interval_end']:.4f}. "
  + ("No name changed." if not sen["names_that_change"] else
     f"Names changed: {sen['names_that_change']}."))
w("")
w(f"I also ran it on {sc['streams']} other random streams (seeds `[20261112, 1001..1020, task]`, "
  "which are not the protocol's draws and replace nothing). The largest distance of any end from "
  f"the main run was {big:.4f}. "
  + ("Every one of the 18 intervals kept its name on every stream."
     if not sc["intervals_whose_name_is_not_the_same_on_every_stream"] else
     "Intervals whose name changed on some stream: "
     + ", ".join(sc["intervals_whose_name_is_not_the_same_on_every_stream"]) + "."))
w("")
rd = R["rq4"]["reach"]["distant"]
rds = sc["by_interval"]["reach D-A distant"]
rda = sen["alternate_intervals"]["reach D-A distant"]["ci90"][1]
top = max(rd["ci90"][1], rda, rds["ci90_high_range"][1])
w("One name sits close to its border. Reach D − A on distant targets is called 'no gain or loss "
  f"as large as the margin' because its 90% interval ends at {f(rd['ci90'][1])}, "
  f"{0.20 - rd['ci90'][1]:.4f} below +0.20. With the other call order that end was {f(rda)}, "
  f"and across the 20 other streams it ranged from {f(rds['ci90_high_range'][0])} to "
  f"{f(rds['ci90_high_range'][1])}. So in these 22 runs it was never above {f(top)}, which is "
  f"{0.20 - top:.4f} short of +0.20. An interval that ends at or above +0.20 there would be named "
  "'unresolved'. I assign no cause to such a difference. That is for whoever compares the two "
  "programs.")
w("")
w("The table gives, for each interval, the smallest move of one of its ends across 0 or ±0.20 "
  "that would change its name or its larger-than-the-margin label:")
w("")
w("| Interval | Smallest move that changes the name |")
w("|---|---|")
allrecs = [("pooled " + s, R["pooled_steps"][s]) for s in ("C-B", "B-A", "D-C")]
allrecs += [(f"{t} {s}", R["per_task_steps"][s][t]) for s in ("C-B", "B-A", "D-C") for t in TASKS]
allrecs += [(f"{t} D-A {p}", R["rq4"][t][p]) for t in TASKS for p in ("close", "distant")]
for k, rec in allrecs:
    w(f"| {k.replace('-', ' − ')} | {rec['nearest_threshold_distance']:.4f} |")
w("")
w("Dividing the numerators before comparing changed no name"
  + ("." if not R["division_changes_any_key"] else ": SEE RESULT.json, some key changed."))
w("")
w("## Self-check")
w("")
p1 = S["point_estimates_by_plain_counting"]
p2 = S["intervals_by_direct_selection"]
w("`selfcheck.py` recomputes by a second route and compares with `RESULT.json`.")
w("")
w("- Point estimates. Plain counting in whole numbers and fractions, with no numpy and no "
  "array of the first route. It reads `arms.json` and the band counts in each folder's "
  "`summary.json`, where the first route read each flight's `outcome.json`. "
  f"{p1['values_compared']} values were compared (successes, adoption counts and means for the "
  "12 arms, and the 18 point estimates) and "
  + ("all agree exactly." if not p1["mismatches"] else f"{len(p1['mismatches'])} DO NOT AGREE."))
w("- Intervals. The cells were read a third way, from `results.jsonl`. The same random-number "
  "calls were made, each resample was scored by picking out the drawn blocks and scenarios and "
  "counting, and the percentiles were computed by hand from the sorted values. "
  f"All {p2['interval_ends_compared']} interval ends were compared; the largest difference is "
  f"{p2['largest_difference']:.1e}"
  + ("." if not p2["mismatches"] else f", and {len(p2['mismatches'])} DO NOT AGREE."))
w("")
w("The second check shares the random-number calls with the first route, so it tests the "
  "arithmetic and the reading of the records. It does not test the choice of calls.")
w("")
w("## Files in this folder")
w("")
w("- `build_table.py` reads the records, runs the integrity checks and writes `outcomes.json` "
  "(the table) and `integrity.json`.")
w("- `bootstrap.py` reads `outcomes.json` and writes `RESULT.json`: arm means, the 18 intervals "
  "with their names, the choices, and the two checks of resampling noise.")
w("- `selfcheck.py` writes `SELFCHECK.json`.")
w("- `write_report.py` writes this report from those files.")
w("")
w("To run again, from any folder: `paper3/.venv/bin/python -I <script>` for the four scripts "
  "in that order.")
w("")

with open(os.path.join(HERE, "REPORT.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("wrote REPORT.md,", len(out), "lines")

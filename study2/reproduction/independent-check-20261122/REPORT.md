# Independent check of the nine intervals of PROTOCOL-3, scored run 20261120-S

Written on 22 November 2026 by a Claude session working as an independent checker. It computed the three primary intervals and the six RQ4 intervals from the run's raw records with its own code. It did not open the analysis program, its output, or any note, draft or result file of the project; the next section lists what it opened. The session's standing context carried the user's one-line memory index of the project, which holds no result and no analysis code. This report does not compare the numbers with the analysis program's. Whoever holds both does that.

## What I read

- The frozen protocol, `inputs/PROTOCOL-3.md` in this folder: its opening, the glossary, and sections 1, 1.1, 1.2, 3, 4.1 to 4.4, 4.6 and 6 to 6.4.
- In each of the three run roots under `runs/scored-20261120-S-extract/data/runs/`: every learning block's `arms.json`; and, for every evaluation folder (`threat3-...`) whose source an arm adopted, its `manifest.json`, each flight's `outcome.json`, `flights/results.jsonl`, `flights/summary.json`, and `kept-late.json` where there was one.
- Of the evaluation folders that no arm adopted (a block's first candidate, c0), only the manifest, to confirm that the folder was c0's. Their flights were not read and are not used.

I did not open any `analysis-run.json`, any `logs/` folder, any `retain3` folder, any learning block file other than `arms.json`, or anything inside a `.set-aside` folder. I saw the names of those files and folders when listing the run roots, and nothing more. I opened nothing under the folders the task ruled out, no other repository or worktree, and no git history. I did not use the network. I did not read the seeds file, because it sits under `paper3/protocol/`, which was ruled out.

## How the outcome table was built

The outcome of a flight is the field `goal_met` of its `outcome.json`. For each task the table has one cell for each arm, block and scenario: 4 arms, 40 blocks, 24 scenarios. A cell is 1 if the arm adopted a source (from `arms.json`: `adopted` true and a `source_sha256`) and `goal_met` is true for that scenario in the folder `threat3-<task>-b<N>-<source_sha256>`. An arm that adopted nothing has 0 in all 24 cells of its block. Arms of one block that adopted the same source read the same folder, so they have the same 24 cells. Each folder's path was built from `arms.json`, never matched by a prefix.

The three sources of a flight's outcome agree everywhere. `goal_met` in `outcome.json` equals `goal_met` in `results.jsonl` for all 7,536 flights read, the two also agree on `end_reason`, and the count of true values in each band equals `met` in `summary.json` for every folder and band.

`goal_met` against `end_reason`, over the flights read:

| Task | `end_reason` | `goal_met` | Flights |
|---|---|---|---|
| reach | entered_threat | false | 391 |
| reach | held | true | 1,838 |
| reach | timed_out | false | 315 |
| reach3d | entered_threat | false | 229 |
| reach3d | held | true | 2,278 |
| reach3d | timed_out | false | 301 |
| land | entered_threat | false | 557 |
| land | hard_landing | false | 17 |
| land | landed_off_point | false | 35 |
| land | landed | true | 1,412 |
| land | timed_out | false | 163 |

So `goal_met` is true exactly when the flight ended `held` (reach, reach3d) or `landed` (land), and a flight that entered the zone is never counted as meeting its goal.

## Choices the protocol left open

These ten choices were fixed before the first run of the bootstrap, and the check of the other call order was part of that first run. None was taken from any other program. The check on 20 other random streams and the table of smallest moves (both below) were added after I had seen the first results. They changed no estimate, interval or name reported here.

1. The generator. numpy.random.default_rng([20261112, 0, task_index]); task_index 0 reach, 1 reach3d, 2 land. One generator per task, used for nothing else.
2. The sets of draws. Five complete sets of 10,000 resamples are drawn one after another from the task's generator: all bands; close; middle; wide; middle and wide together. A set is finished before the next begins. The middle-only and wide-only sets are drawn and not used.
3. The calls inside a set. Main reading (per resample): for each resample, first rng.integers(0, 40, size=40) for the blocks, then for each band of the set in the order close, middle, wide one rng.integers(0, 8, size=8) for that band's scenarios.
4. Which index is which block and scenario. Block index i is block number i. Scenario index j within a band is the j-th smallest seed number of that band.
5. The statistic. A resample's arm mean is the mean over its 40 drawn blocks and its drawn scenarios (8 per band, so the bands have equal weight). A contrast is the difference of two arm means from the same resample.
6. Pooling. The pooled contrast of resample r is the mean of the three tasks' contrasts at resample r of their all-band sets. Every task has 960 cells per arm, so this equals the difference of means over the 2,880 cells taken together.
7. Which set feeds which interval. Per-task steps and pooled steps: the all-band set. D - A close: the close set. D - A distant: the set of middle and wide together.
8. Percentiles. numpy.percentile with its default linear interpolation, at 2.5 and 97.5 for the 95% interval and at 5 and 95 for the 90% interval.
9. Strict comparisons. Each resample's contrast is kept as a whole-number numerator over a fixed denominator (960 per task, 320 close, 640 distant, 2,880 pooled). The percentiles are taken on the numerators, and the strict comparisons with 0 and with 0.20 are made on numerators (0.20 is 192, 64, 128 and 576 of those denominators), so no rounding of a division can decide a name.
10. Order of the naming rules. First the three names for nothing to compare, tested on the cells. Then, for a pooled step, task-dependence from the three per-task 95% intervals of the all-band set. Then the four-way table, with the larger-than-the-margin label.

The scenarios of a task are its 24 planned evaluation cases. I could not take them from the seeds file, so I took them from the `args.cases` list of each evaluation folder's manifest and checked that every folder of a task lists the same 24 names, 8 in each band, and holds exactly those 24 flight folders. They do.

Environment: Python 3.12.13, numpy 2.5.4, macOS-27.2.1-arm64-arm-64bit.

## Where the protocol's text is ambiguous

- Section 6.2 gives the seed of each task's generator as a list and does not name the library. I read it as numpy's `default_rng` given that list.
- Section 6.2 gives the order of the sets (all bands, each band, then middle and wide together) and says nothing about the calls inside a set: whether a resample draws its blocks and then its scenarios before the next resample begins, or all block draws of a set come first. I took the first, because the text describes what 'each resample' draws. It does not give the order of 'each band' either. I took close, middle, wide, the order in which section 3 lists them. This choice changes the random stream, so I measured its effect (below).
- The text says the pooled steps use each task's all-band draws. It does not say outright that D − A on close targets uses the close set and D − A on distant targets the set of middle and wide together. I read the order of draws as implying it.
- 'Pooled over the three tasks with equal weight' and 'the tasks are resampled independently' do not say how resamples of different tasks are combined. I paired them by resample number: pooled resample r is the mean of the three tasks' contrasts at their resample r.
- The percentile rule (how to interpolate between two sorted values) is not given.
- Section 6.4 gives 'a gain larger than the margin' as a further name for a gain whose 95% interval lies wholly above +0.20. I report it as the name and keep the four-way key beside it.
- Section 6.4 has two rules for a pooled step: its name, and the table that reads the name beside the signs of the three per-task estimates. I report both for each pooled step.

## What the records showed

- Nothing was missing. Every adopted source has its evaluation folder, every such folder holds 24 flights, 8 in each band, and every flight has an `outcome.json` with a true or false `goal_met`. The integrity checks in `build_table.py` raised 0 problems.
- Evaluation folders used: 106 in reach, 117 in reach3d, 91 in land. Folders no arm adopted, all of them c0's by their manifest and none used: 0 in reach, 0 in reach3d, 7 in land.
- Every manifest's task, block, source hash and list of arms matches `arms.json`.
- Arm A adopted a procedure in all 40 blocks of every task.
- Three evaluation folders hold a `kept-late.json`, all in reach3d, each naming one flight: block 34, arm A, `threat-close-3110004`, recorded as goal not met (timed_out); block 37, arms A, B, C, `threat-close-3110008`, recorded as goal met (held); block 39, arm A, `threat-wide-3110202`, recorded as goal met (held). They are counted as recorded. Reach and land have none.
- The `.set-aside` folders hold 4 attempts for reach, 7 for reach3d and 3 for land, by their names. None was opened and none enters any number here.

How often arms of a block shared a source (letters joined are arms with one source; a slash separates different sources; arms not shown adopted nothing):

| Task | Pattern | Blocks |
|---|---|---|
| reach | A | 2 |
| reach | ABC / D | 6 |
| reach | A / B | 1 |
| reach | A / B / C / D | 6 |
| reach | A / C | 4 |
| reach | A / C / D | 16 |
| reach | A / D | 5 |
| reach3d | ABC | 1 |
| reach3d | ABC / D | 4 |
| reach3d | A / B / C | 3 |
| reach3d | A / B / C / D | 5 |
| reach3d | A / B / D | 2 |
| reach3d | A / C | 2 |
| reach3d | A / C / D | 23 |
| land | A | 6 |
| land | AB | 1 |
| land | ABC / D | 1 |
| land | A / B / C / D | 1 |
| land | A / C | 8 |
| land | A / C / D | 16 |
| land | A / D | 7 |

## Results

Margin 0.20, 10,000 resamples, seed 20261112. Estimates and interval ends are shown to four decimals here and in full in `RESULT.json`.

### Arm means and adoption

Mean outcome over 40 blocks × 24 held-out zone flights (960 cells), and blocks that adopted.

| Task | Arm | Successes of 960 | Mean | Blocks adopted of 40 | Mean, close (320 cells) | Mean, distant (640 cells) |
|---|---|---|---|---|---|---|
| reach | A | 447 | 0.4656 | 40 | 0.1406 | 0.6281 |
| reach | B | 272 | 0.2833 | 13 | 0.2562 | 0.2969 |
| reach | C | 668 | 0.6958 | 32 | 0.6687 | 0.7094 |
| reach | D | 677 | 0.7052 | 33 | 0.7156 | 0.7000 |
| reach3d | A | 533 | 0.5552 | 40 | 0.1875 | 0.7391 |
| reach3d | B | 339 | 0.3531 | 15 | 0.3406 | 0.3594 |
| reach3d | C | 864 | 0.9000 | 38 | 0.8719 | 0.9141 |
| reach3d | D | 750 | 0.7812 | 34 | 0.7594 | 0.7922 |
| land | A | 304 | 0.3167 | 40 | 0.0875 | 0.4313 |
| land | B | 64 | 0.0667 | 3 | 0.0531 | 0.0734 |
| land | C | 567 | 0.5906 | 26 | 0.5406 | 0.6156 |
| land | D | 542 | 0.5646 | 25 | 0.5813 | 0.5563 |

### The three primary intervals, pooled over the three tasks (120 blocks)

| Contrast | Estimate | 95% interval | 90% interval | Name |
|---|---|---|---|---|
| pooled C − B | +0.4944 | [+0.3983, +0.5861] | [+0.4135, +0.5719] | a gain larger than the margin (`different_not_equivalent`, `useful_gain`) |
| pooled B − A | -0.2115 | [-0.2868, -0.1316] | [-0.2747, -0.1455] | a loss (`different_not_equivalent`) |
| pooled D − C | -0.0451 | [-0.1358, +0.0472] | [-0.1208, +0.0316] | no gain or loss as large as the margin (`equivalent_not_different`) |

The rule for pooled steps:

| Step | Tasks whose 95% interval is wholly above 0 | Wholly below 0 | Task-dependent | Signs of the per-task estimates (reach, reach3d, land) | Row of section 6.4's reading table |
|---|---|---|---|---|---|
| C − B | reach, reach3d, land | none | no | +, +, + | a pooled gain over these three tasks |
| B − A | none | reach, reach3d, land | no | −, −, − | a pooled loss over these three tasks |
| D − C | none | none | no | +, −, − | not settled: the average is near zero while the tasks' estimates point in opposite directions |

Pooled D − C needs a note. Its name by the four-way table is 'no gain or loss as large as the margin', and no task's 95% interval lies wholly on either side of 0, so it is not task-dependent. The per-task estimates differ in sign: reach +0.0094, reach3d -0.1187, land -0.0260. Section 6.4's reading table then gives the row 'not settled': the paper says the average is near zero while the tasks' estimates point in opposite directions, and does not say that the step made no difference. The reach estimate is 9 cells of 960.

### The same three steps for each task (40 blocks, secondary)

| Contrast | Estimate | 95% interval | 90% interval | Name |
|---|---|---|---|---|
| reach C − B | +0.4125 | [+0.2521, +0.5625] | [+0.2781, +0.5396] | a gain larger than the margin (`different_not_equivalent`, `useful_gain`) |
| reach3d C − B | +0.5469 | [+0.3615, +0.7125] | [+0.3927, +0.6875] | a gain larger than the margin (`different_not_equivalent`, `useful_gain`) |
| land C − B | +0.5240 | [+0.3635, +0.6771] | [+0.3906, +0.6562] | a gain larger than the margin (`different_not_equivalent`, `useful_gain`) |
| reach B − A | -0.1823 | [-0.3250, -0.0292] | [-0.3031, -0.0531] | a loss (`different_not_equivalent`) |
| reach3d B − A | -0.2021 | [-0.3417, -0.0479] | [-0.3198, -0.0750] | a loss (`different_not_equivalent`) |
| land B − A | -0.2500 | [-0.3510, -0.1510] | [-0.3354, -0.1667] | a loss (`different_not_equivalent`) |
| reach D − C | +0.0094 | [-0.1375, +0.1615] | [-0.1156, +0.1375] | no gain or loss as large as the margin (`equivalent_not_different`) |
| reach3d D − C | -0.1187 | [-0.2563, +0.0219] | [-0.2344, -0.0042] | unresolved (`unresolved`) |
| land D − C | -0.0260 | [-0.2073, +0.1573] | [-0.1760, +0.1250] | no gain or loss as large as the margin (`equivalent_not_different`) |

### The six RQ4 intervals: D − A by task, on close and on distant targets

Close is the 8 close scenarios (320 cells per arm). Distant is the 16 middle and wide scenarios together (640 cells per arm).

| Contrast | Estimate | 95% interval | 90% interval | Name |
|---|---|---|---|---|
| reach D − A close | +0.5750 | [+0.4156, +0.7281] | [+0.4406, +0.7031] | a gain larger than the margin (`different_not_equivalent`, `useful_gain`) |
| reach D − A distant | +0.0719 | [-0.0688, +0.2141] | [-0.0453, +0.1906] | no gain or loss as large as the margin (`equivalent_not_different`) |
| reach3d D − A close | +0.5719 | [+0.3937, +0.7312] | [+0.4250, +0.7063] | a gain larger than the margin (`different_not_equivalent`, `useful_gain`) |
| reach3d D − A distant | +0.0531 | [-0.1000, +0.1984] | [-0.0766, +0.1766] | no gain or loss as large as the margin (`equivalent_not_different`) |
| land D − A close | +0.4938 | [+0.3219, +0.6594] | [+0.3500, +0.6312] | a gain larger than the margin (`different_not_equivalent`, `useful_gain`) |
| land D − A distant | +0.1250 | [-0.0781, +0.3187] | [-0.0437, +0.2906] | unresolved (`unresolved`) |

No contrast had nothing to compare: none of the three names for that case applies to any of the 18 intervals above.

## How far the unpinned choices can move an interval

The estimates do not depend on any random draw. The interval ends do, so a second correct program that makes its random-number calls in another order will give slightly different ends.

I ran the whole analysis again with the other call order inside a set (all block draws of the set first, then each band's scenario draws). The largest move of any of the 72 interval ends was 0.0063. No name changed.

I also ran it on 20 other random streams (seeds `[20261112, 1001..1020, task]`, which are not the protocol's draws and replace nothing). The largest distance of any end from the main run was 0.0094. Every one of the 18 intervals kept its name on every stream.

One name sits close to its border. Reach D − A on distant targets is called 'no gain or loss as large as the margin' because its 90% interval ends at +0.1906, 0.0094 below +0.20. With the other call order that end was +0.1906, and across the 20 other streams it ranged from +0.1906 to +0.1953. So in these 22 runs it was never above +0.1953, which is 0.0047 short of +0.20. An interval that ends at or above +0.20 there would be named 'unresolved'. I assign no cause to such a difference. That is for whoever compares the two programs.

The table gives, for each interval, the smallest move of one of its ends across 0 or ±0.20 that would change its name or its larger-than-the-margin label:

| Interval | Smallest move that changes the name |
|---|---|
| pooled C − B | 0.1983 |
| pooled B − A | 0.0684 |
| pooled D − C | 0.0472 |
| reach C − B | 0.0521 |
| reach3d C − B | 0.1615 |
| land C − B | 0.1635 |
| reach B − A | 0.0292 |
| reach3d B − A | 0.0479 |
| land B − A | 0.0490 |
| reach D − C | 0.0625 |
| reach3d D − C | 0.0219 |
| land D − C | 0.0240 |
| reach D − A close | 0.2156 |
| reach D − A distant | 0.0094 |
| reach3d D − A close | 0.1938 |
| reach3d D − A distant | 0.0234 |
| land D − A close | 0.1219 |
| land D − A distant | 0.0781 |

Dividing the numerators before comparing changed no name.

## Self-check

`selfcheck.py` recomputes by a second route and compares with `RESULT.json`.

- Point estimates. Plain counting in whole numbers and fractions, with no numpy and no array of the first route. It reads `arms.json` and the band counts in each folder's `summary.json`, where the first route read each flight's `outcome.json`. 54 values were compared (successes, adoption counts and means for the 12 arms, and the 18 point estimates) and all agree exactly.
- Intervals. The cells were read a third way, from `results.jsonl`. The same random-number calls were made, each resample was scored by picking out the drawn blocks and scenarios and counting, and the percentiles were computed by hand from the sorted values. All 72 interval ends were compared; the largest difference is 5.6e-17.

The second check shares the random-number calls with the first route, so it tests the arithmetic and the reading of the records. It does not test the choice of calls.

## Files in this folder

- `build_table.py` reads the records, runs the integrity checks and writes `outcomes.json` (the table) and `integrity.json`.
- `bootstrap.py` reads `outcomes.json` and writes `RESULT.json`: arm means, the 18 intervals with their names, the choices, and the two checks of resampling noise.
- `selfcheck.py` writes `SELFCHECK.json`.
- `write_report.py` writes this report from those files.

To run again, from any folder: `paper3/.venv/bin/python -I <script>` for the four scripts in that order.

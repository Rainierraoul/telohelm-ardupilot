# Protocol 3 analysis

protocol3 scored analysis

## Primary intervals (the three pooled steps)

| Primary contrast | Estimate | 95% interval | Result | Key in analysis.json |
|---|---:|---|---|---|
| pooled:C-B | +0.4944 | +0.3979, +0.5868 | a useful gain | different_not_equivalent |
| pooled:B-A | -0.2115 | -0.2868, -0.1330 | a loss | different_not_equivalent |
| pooled:D-C | -0.0451 | -0.1365, +0.0458 | no pooled gain or loss as large as the margin over these three tasks | equivalent_not_different |

## Secondary intervals: D - A for each task, close and distant (RQ4's answer, ruling 88)

The six per-task D - A intervals are secondary. They are computed from the same draws as before and reported in full. The protocol said before the run that most were expected to be unresolved; an unresolved interval is not evidence of no difference.

| Secondary contrast | Estimate | 95% interval | Result | Key in analysis.json |
|---|---:|---|---|---|
| reach:D-A:close | +0.5750 | +0.4188, +0.7281 | a useful gain | different_not_equivalent |
| reach:D-A:middle-wide | +0.0719 | -0.0688, +0.2125 | no gain or loss as large as the margin | equivalent_not_different |
| reach3d:D-A:close | +0.5719 | +0.4000, +0.7344 | a useful gain | different_not_equivalent |
| reach3d:D-A:middle-wide | +0.0531 | -0.1016, +0.2016 | no gain or loss as large as the margin | equivalent_not_different |
| land:D-A:close | +0.4938 | +0.3187, +0.6594 | a useful gain | different_not_equivalent |
| land:D-A:middle-wide | +0.1250 | -0.0781, +0.3203 | unresolved | unresolved |

Intervals are pointwise. Direction and equivalence are distinct; see analysis.json.
When the two arms of a contrast are equal cell for cell, or both 0 in every cell, or both 1 in every cell, the bootstrap has nothing to resample. The result is then named for that and not by section 6.4. For a pooled step the cells of the three tasks are taken together and N counts the blocks of all three.

## RQ1: the answer for each pooled step

Each answer comes from the pooled result and the signs of the three per-task point estimates (ruling 38, point 3). A task whose estimate is exactly 0 has no sign and differs from neither.

### C-B

Pooled result: a useful gain. Per-task signs: reach +, reach3d +, land + (they do not differ).

Answer: A pooled gain over these three tasks.

| Task | Estimate | 95% interval | Result |
|---|---:|---|---|
| reach | +0.4125 | +0.2521, +0.5656 | a useful gain |
| reach3d | +0.5469 | +0.3635, +0.7135 | a useful gain |
| land | +0.5240 | +0.3635, +0.6781 | a useful gain |

### B-A

Pooled result: a loss. Per-task signs: reach -, reach3d -, land - (they do not differ).

Answer: A pooled loss over these three tasks.

| Task | Estimate | 95% interval | Result |
|---|---:|---|---|
| reach | -0.1823 | -0.3240, -0.0302 | a loss |
| reach3d | -0.2021 | -0.3458, -0.0531 | a loss |
| land | -0.2500 | -0.3510, -0.1490 | a loss |

### D-C

Pooled result: no pooled gain or loss as large as the margin over these three tasks. Per-task signs: reach +, reach3d -, land - (they differ).

Answer (not settled): Not settled. The average is near zero while the tasks' estimates point in opposite directions. Each is given with its interval. This does not show that the step made no difference.

| Task | Estimate | 95% interval | Result |
|---|---:|---|---|
| reach | +0.0094 | -0.1417, +0.1604 | no gain or loss as large as the margin |
| reach3d | -0.1187 | -0.2573, +0.0167 | unresolved |
| land | -0.0260 | -0.2052, +0.1594 | no gain or loss as large as the margin |

## RQ4: D - A on close targets minus D - A on distant targets (descriptive, no section 6.4 name)

For each task, from one set of resamples shared by the close and distant parts. These resamples are not the ones that made the primary intervals. The sample-size work did not plan this difference's resolution.

| Task | Close D - A | Distant D - A | Close minus distant | 95% interval |
|---|---:|---:|---:|---|
| reach | +0.5750 | +0.0719 | +0.5031 | +0.3391, +0.6594 |
| reach3d | +0.5719 | +0.0531 | +0.5188 | +0.3688, +0.6687 |
| land | +0.4938 | +0.1250 | +0.3688 | +0.2328, +0.5016 |

## Evaluation flights kept late and evaluation phases flown again

An evaluation phase with a late flight is set aside and flown again, up to two times. The third attempt is kept whatever its timing, and each late flight in it is kept late.

Flights kept late: 3 (threat3 3). Cells of the nine intervals that belong to them: 5.

| Arm | Hazard cells kept late | Retention cells kept late |
|---|---:|---:|
| A | 3 | 0 |
| B | 1 | 0 |
| C | 1 | 0 |
| D | 0 | 0 |

The kept-late cells decide a bound only through the arms of the contrast. For the lower bound of X - Y, each kept-late cell of X is taken as 0 (a failure) and each of Y as 1 (a success); for the upper bound the reverse. A flight that both arms share is one flight and cancels, so both cells are set to 0. The six D - A intervals share one pair of fills (D low and A high, then the reverse), and each pooled step has its own. The draws are the primaries' own. Each cell below is the interval, then the name of section 6.4 under that fill. All nine intervals are filled: the three pooled steps are primary and the six per-task D - A intervals are secondary (ruling 88).

| Contrast | Designation | As kept | Lower fill | Upper fill |
|---|---|---|---|---|
| reach:D-A:close | secondary | +0.5750 (+0.4188, +0.7281), a useful gain | +0.5750 (+0.4188, +0.7281), a useful gain | +0.5750 (+0.4188, +0.7281), a useful gain |
| reach:D-A:middle-wide | secondary | +0.0719 (-0.0688, +0.2125), no gain or loss as large as the margin | +0.0719 (-0.0688, +0.2125), no gain or loss as large as the margin | +0.0719 (-0.0688, +0.2125), no gain or loss as large as the margin |
| reach3d:D-A:close | secondary | +0.5719 (+0.4000, +0.7344), a useful gain | +0.5687 (+0.3906, +0.7312), a useful gain | +0.5750 (+0.4031, +0.7344), a useful gain |
| reach3d:D-A:middle-wide | secondary | +0.0531 (-0.1016, +0.2016), no gain or loss as large as the margin | +0.0531 (-0.1016, +0.2016), no gain or loss as large as the margin | +0.0547 (-0.1000, +0.2047), no gain or loss as large as the margin |
| land:D-A:close | secondary | +0.4938 (+0.3187, +0.6594), a useful gain | +0.4938 (+0.3187, +0.6594), a useful gain | +0.4938 (+0.3187, +0.6594), a useful gain |
| land:D-A:middle-wide | secondary | +0.1250 (-0.0781, +0.3203), unresolved | +0.1250 (-0.0781, +0.3203), unresolved | +0.1250 (-0.0781, +0.3203), unresolved |
| pooled:C-B | primary | +0.4944 (+0.3979, +0.5868), a useful gain | +0.4944 (+0.3979, +0.5868), a useful gain | +0.4944 (+0.3979, +0.5868), a useful gain |
| pooled:B-A | primary | -0.2115 (-0.2868, -0.1330), a loss | -0.2118 (-0.2868, -0.1333), a loss | -0.2111 (-0.2865, -0.1326), a loss |
| pooled:D-C | primary | -0.0451 (-0.1365, +0.0458), no pooled gain or loss as large as the margin over these three tasks | -0.0451 (-0.1365, +0.0458), no pooled gain or loss as large as the margin over these three tasks | -0.0448 (-0.1361, +0.0458), no pooled gain or loss as large as the margin over these three tasks |

The name is the as-kept name under both fills for every contrast.

Evaluation phases flown again: 11. Attempts set aside: 14. Cells compared with the attempt kept: 308, of which 2 differ.

| Phase | Attempt set aside | Reason | Cells | Cells differing from the attempt kept | Cells with no outcome |
|---|---:|---|---:|---:|---:|
| threat3-reach-b0-125734dec34bbe51bebd7c297d5298a4e5423e8c3bcb0e1e78c8d33f5b734afe | 1 | late | 24 | 0 | 0 |
| threat3-reach-b0-80d56c0ff82cc3977b4787590b92d2294928b23dc559fe2935182f23ecb75bdd | 1 | late | 24 | 1 | 0 |
| threat3-reach-b1-36c247d95efbb81605b035326c80c63bbd6c25228fccda091561b960ccb3f5b4 | 1 | late | 24 | 0 | 0 |
| retain3-reach-b1-36c247d95efbb81605b035326c80c63bbd6c25228fccda091561b960ccb3f5b4 | 1 | late | 10 | 0 | 0 |
| threat3-reach3d-b34-2d669a2968434af865746c9612bbff6dd12f18c4e47ab879a1ffd6efef4a2e90 | 1 | late | 24 | 0 | 0 |
| threat3-reach3d-b34-2d669a2968434af865746c9612bbff6dd12f18c4e47ab879a1ffd6efef4a2e90 | 2 | late | 24 | 0 | 0 |
| threat3-reach3d-b37-ed35838d9990e1fde0f337b627235eeb0e7660578101ba37ab38ba3866069f2d | 1 | late | 24 | 0 | 0 |
| threat3-reach3d-b37-ed35838d9990e1fde0f337b627235eeb0e7660578101ba37ab38ba3866069f2d | 2 | late | 24 | 0 | 0 |
| threat3-reach3d-b39-bdb9eede7bdeeb1e7ccf696959ee253c00a4195833b1775c3aad237a767c551f | 1 | late | 24 | 1 | 0 |
| threat3-reach3d-b39-bdb9eede7bdeeb1e7ccf696959ee253c00a4195833b1775c3aad237a767c551f | 2 | late | 24 | 0 | 0 |
| threat3-reach3d-b39-296ae154ba4c3c2708fe8b3de8fdcfc8357c26037fa1401a4d795e3423d7ccd9 | 1 | late | 24 | 0 | 0 |
| threat3-land-b35-93d2a6dc3e63fac768536600fe7af73ef25beb1246194ac10493f6b4bd3b768a | 1 | late | 24 | 0 | 0 |
| threat3-land-b35-31897bf96fe50f66c306fa51f426c0207ec88bb3d75a44659895f72c32f1e777 | 1 | late | 24 | 0 | 0 |
| retain3-land-b35-93d2a6dc3e63fac768536600fe7af73ef25beb1246194ac10493f6b4bd3b768a | 1 | late | 10 | 0 | 0 |


## The spending stop of each session, and learning blocks set aside

The stop is a test made when a block is about to start. Blocks already running go on spending after it trips. It counts list price, and the gateway has charged more than list price.

The scored run flew as three runs, one task each. Every session had a spending stop set by --spend-limit; the highest of each run was US$20 for reach, US$20 for reach3d, US$20 for land, US$60 in all (the protocol's whole-run stop is US$60).

| Session event | Time | Stop (US$) | Set by the flag |
|---|---|---:|---|
| start | 2026-11-20 19:59:10 | 20.0 | True |
| resume | 2026-11-22 03:28:39 | 20.0 | True |
| start | 2026-11-20 19:59:10 | 20.0 | True |
| resume | 2026-11-22 05:56:33 | 20.0 | True |
| resume | 2026-11-22 07:15:24 | 20.0 | True |
| start | 2026-11-20 19:59:12 | 20.0 | True |
| resume | 2026-11-22 02:41:57 | 20.0 | True |

Learning blocks set aside and flown again: 0.

## Spend by run root, list price

| Root (task) | Unique calls (US$) | Blocks set aside (US$) |
|---|---:|---:|
| reach | 10.6821 | 0.0000 |
| reach3d | 9.4804 | 0.0000 |
| land | 11.7187 | 0.0000 |

In total: US$31.8813. List price of the unique calls and of the blocks set aside, without the calls that never reached a spending row.


## Secondary estimates

These sit beside the primary intervals and do not override them.

### The candidate at which each arm adopted, and how often it adopted nothing

- Arm A: c0 109, f1 10, f2 1
- Arm B: c0 12, f1 11, f2 8, nothing 89
- Arm C: c0 12, nothing 24, rC1 45, rC2 39
- Arm D: c1 27, nothing 28, rD1 35, rD2 30

### Fresh candidates whose source equals their block's c0

0 of 202 valid fresh candidates (205 fresh slots in all). Share of valid fresh candidates: 0.0000. Share of all fresh slots: 0.0000.

### Candidate slots by kind

Valid at the first call, valid after the format repair (a second call for the same slot), or not valid.

| Kind | Valid at the first call | Valid after the format repair | Not valid |
|---|---:|---:|---:|
| c0 | 106 | 10 | 4 |
| c1 | 109 | 9 | 2 |
| fresh | 190 | 12 | 3 |
| repair | 299 | 21 | 2 |

### C - B in the blocks where c0 was valid and failed its threat trial

| Task | Blocks | Blocks left out because c0 was not valid | Estimate | 95% interval | Result |
|---|---:|---:|---:|---|---|
| reach | 31 | 3 | +0.5000 | +0.3145, +0.6747 | a useful gain |
| reach3d | 34 | 1 | +0.6140 | +0.4167, +0.7904 | a useful gain |
| land | 39 | 0 | +0.5374 | +0.3750, +0.6912 | a useful gain |

### c0 on the evaluation scenarios

A block whose c0 was not valid counts as 0 in every cell, as an arm that adopted nothing does. Blocks whose c0 was not valid: 4 of 120.

| Task | Mean over all blocks | Mean over blocks with a valid c0 | Blocks with c0 not valid |
|---|---:|---:|---:|
| reach | 0.4198 | 0.4538 | 3 |
| reach3d | 0.5458 | 0.5598 | 1 |
| land | 0.2552 | 0.2552 | 0 |

### Timing by arm (section 4.6)

Pooled over the decisions of the arm's flights. A flight that two arms share counts for both. Lags are in seconds, call times are the wall time of one sandboxed call.

Learning trial flights.

| Arm | Flights | Median lag | Largest lag | Share of decisions 0.1 s late | Largest own lag | Observations a step late | Missed deadlines | First sight, median m | Procedure call, median and largest | Guard call, median and largest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| A | 384 | 0.000 | 0.201 | 0.1670 | 0.201 | 0 | 0 | none | 0.0421 and 0.1189 | 0.0409 and 0.1623 |
| B | 954 | 0.001 | 0.300 | 0.2689 | 0.200 | 4809 | 0 | 12.32 | 0.0421 and 0.1593 | 0.0408 and 0.1596 |
| C | 858 | 0.001 | 0.300 | 0.3385 | 0.200 | 2851 | 0 | 12.38 | 0.0424 and 0.1593 | 0.0408 and 0.1257 |
| D | 804 | 0.001 | 0.300 | 0.3811 | 0.200 | 2269 | 0 | 12.27 | 0.0426 and 0.1618 | 0.0409 and 0.1573 |

Evaluation flights, hazard.

| Arm | Flights | Median lag | Largest lag | Share of decisions 0.1 s late | Largest own lag | Observations a step late | Missed deadlines | First sight, median m | Procedure call, median and largest | Guard call, median and largest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| A | 2880 | 0.001 | 0.900 | 0.2949 | 0.899 | 14214 | 3 | 11.71 | 0.0421 and 0.1675 | 0.0405 and 0.1562 |
| B | 744 | 0.001 | 0.300 | 0.1927 | 0.299 | 284 | 1 | 11.55 | 0.0420 and 0.1555 | 0.0404 and 0.1553 |
| C | 2304 | 0.001 | 0.300 | 0.3858 | 0.299 | 712 | 1 | 11.96 | 0.0427 and 0.1584 | 0.0405 and 0.1592 |
| D | 2208 | 0.001 | 0.201 | 0.3486 | 0.201 | 422 | 0 | 11.89 | 0.0427 and 0.1552 | 0.0405 and 0.1542 |

Evaluation flights, retention.

| Arm | Flights | Median lag | Largest lag | Share of decisions 0.1 s late | Largest own lag | Observations a step late | Missed deadlines | First sight, median m | Procedure call, median and largest | Guard call, median and largest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| A | 1200 | 0.001 | 0.201 | 0.2450 | 0.201 | 0 | 0 | none | 0.0424 and 0.1598 | 0.0407 and 0.1522 |
| B | 310 | 0.000 | 0.101 | 0.1919 | 0.101 | 0 | 0 | none | 0.0421 and 0.0647 | 0.0405 and 0.0471 |
| C | 960 | 0.001 | 0.201 | 0.3749 | 0.200 | 0 | 0 | none | 0.0427 and 0.1584 | 0.0406 and 0.1642 |
| D | 920 | 0.001 | 0.201 | 0.3104 | 0.200 | 0 | 0 | none | 0.0426 and 0.1506 | 0.0405 and 0.1803 |

### Calls flown again and flights kept late in learning

| Arm | Calls flown again | Attempts set aside as late | Flights kept late |
|---|---:|---:|---:|
| A | 0 | 0 | 0 |
| B | 1 | 1 | 0 |
| C | 0 | 0 | 0 |
| D | 0 | 0 | 0 |

In the run, each call counted once: 1 calls flown again, 1 attempts set aside, 0 flights kept late. Blocks with no timing.json: 0.

### Spend (list price)

Unique spend of the blocks kept: 830 calls, US$31.8813. Blocks set aside: 0, 0 calls, US$0.0000 (the provider's charge on 0 of 0 rows: US$0.0000). Together, with the list cost of the provider rows that have no spending row: US$31.8813.

### Message ids

Message ids that appear for more than one call: 0 (the gate requires 0; it saw 830).

Copies caught (replies the gateway returned from its store that the provider logged as copied, in learning blocks that were set aside and flown again): 0. Message ids in the run's file with no provider row (a process killed between the claim and the row): 0. Provider rows with no spending row (a process killed between the provider's row and the ladder's): 0, list cost US$0.0000, charge US$0.0000 on 0 rows. Their list cost is added to the spend of the blocks set aside above. Lines of the run's file of message ids cut short by a crash and skipped: 0.


## Descriptive counts (no interval)

Counts and means of the fresh zone flights (the hazard evaluation), with no interval and no resampling. A block that adopted nothing counts as 0 in every cell, as in arm_means, except in the fields marked adopting_blocks.

Fields in analysis.json under descriptive_counts.by_task[task][arm]: blocks, successes, flights_possible, adopting_blocks, adopting_blocks_successes, adopting_blocks_flights_possible, adopting_blocks_mean, mean_by_band, flights_possible_by_band.

| Task | Arm | Successes of flights possible | Adopting blocks | Successes in adopting blocks, of flights possible | Mean in adopting blocks | Mean close | Mean middle | Mean wide |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| reach | A | 447 of 960 | 40 of 40 | 447 of 960 | 0.4656 | 0.1406 | 0.5687 | 0.6875 |
| reach | B | 272 of 960 | 13 of 40 | 272 of 312 | 0.8718 | 0.2562 | 0.2906 | 0.3031 |
| reach | C | 668 of 960 | 32 of 40 | 668 of 768 | 0.8698 | 0.6687 | 0.7000 | 0.7188 |
| reach | D | 677 of 960 | 33 of 40 | 677 of 792 | 0.8548 | 0.7156 | 0.6937 | 0.7063 |
| reach3d | A | 533 of 960 | 40 of 40 | 533 of 960 | 0.5552 | 0.1875 | 0.6188 | 0.8594 |
| reach3d | B | 339 of 960 | 15 of 40 | 339 of 360 | 0.9417 | 0.3406 | 0.3500 | 0.3688 |
| reach3d | C | 864 of 960 | 38 of 40 | 864 of 912 | 0.9474 | 0.8719 | 0.9000 | 0.9281 |
| reach3d | D | 750 of 960 | 34 of 40 | 750 of 816 | 0.9191 | 0.7594 | 0.7656 | 0.8187 |
| land | A | 304 of 960 | 40 of 40 | 304 of 960 | 0.3167 | 0.0875 | 0.4156 | 0.4469 |
| land | B | 64 of 960 | 3 of 40 | 64 of 72 | 0.8889 | 0.0531 | 0.0719 | 0.0750 |
| land | C | 567 of 960 | 26 of 40 | 567 of 624 | 0.9087 | 0.5406 | 0.6219 | 0.6094 |
| land | D | 542 of 960 | 25 of 40 | 542 of 600 | 0.9033 | 0.5813 | 0.5656 | 0.5469 |

No scored conclusion may be drawn from a development/pilot analysis.

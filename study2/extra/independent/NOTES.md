# Notes on the independent recomputation of arm E's comparisons

Written 23 November 2026 by the checking session. The program is `recompute_e.py` in this folder, and its printed
output is `RESULTS.txt`. Run it with `python3 -I recompute_e.py <output folder>`. It needs numpy only (2.5.5 was used,
with Python 3.15.2). It reads the records and writes nothing into them. It also writes `opened-files.txt`, the full list
of every file it opened and every folder it listed.

## What the program does

For each task it builds a table of 4 arms (A, B, C, E) by 40 blocks by 24 zone evaluation flights. The 24 flights are
named from the seed book as `threat-<band>-<seed>`, close then middle then wide, 8 in each. A cell is 1 if the arm
adopted a source in that block and that source's flight of that scenario has `goal_met` true in its `outcome.json`,
and 0 otherwise. An arm that adopted nothing has 24 zeros in that block.

Arms A, B and C are read from Study 2's `learn3-<task>-b<N>/arms.json`, and arm E from `learnE-<task>-b<N>/arms.json`.
The flights of an adopted source are read from `threat3-<task>-b<N>-<source sha256>/flights/`. For arm E the program
looks in Study 2's run first and uses arm E's run only when Study 2 has no phase of that source in that block.

Before any number is computed it stops if any of these fail:

- the seed book's SHA-256 starts 1d39a62c;
- every one of the 120 Study 2 blocks and 120 arm E blocks has its done mark;
- each arm E block names its Study 2 block, and the SHA-256 it records for that block's `arms.json` equals the hash of
  the file the program read;
- every scored evaluation phase has its done mark, a manifest that names the same task, block and source, and exactly
  the 24 seed-book flight folders;
- each phase that arms A, B or C are scored from lists that arm in its manifest;
- each phase scored from arm E's run lists arms `["E"]` in its manifest and is not in the control list;
- the arm E phases left unscored are exactly the `control` list of that task's `logs/schedule.json`, two per task, and
  each is a re-flight of a phase Study 2 also has;
- in every resample, E − B plus C − E equals C − B exactly (the sums are kept as integers until the last division);
- for the first 200 resamples of each task and comparison, the fast weighted sum equals the same statistic computed by
  indexing the table directly.

It also reports, without stopping: the source text in each phase's `run-config.json` hashes to the folder's name in all
281 scored phases; where c0 passed its zone trial (12 blocks), arm E adopted that same c0; and which scored phases hold a
`kept-late.json` (checked for existence only, not opened).

The bootstrap, per task: draw 40 blocks with replacement (a block's four arms move together), and draw 8 scenarios with
replacement inside each band, one scenario draw shared by every block and arm. The resample's value is the mean of
X − Y over the drawn blocks and drawn scenarios, repeats counted. The pooled value of resample r is the mean of the three
tasks' values of resample r. Point estimates are the differences of arm means over the full table, and the pooled point
estimate is the mean of the three tasks' estimates. Intervals are percentiles of the 10,000 resampled values.

## Seed

Primary: `numpy.random.default_rng([20261112, 0, task index])`, task index 0 for reach, 1 for reach3d and 2 for land.
This is the seed entropy PROTOCOL-3.md section 6.2 names. A second run with `default_rng([777, 0, task index])` is
printed as a Monte Carlo check only. Between the two seeds no interval end moves by more than 0.0063.

## Where the protocols were ambiguous, and how I read them

1. Order of draws inside the generator. PROTOCOL-3.md 6.2 fixes the seed entropy and says the all-band draws come first,
   then each band, then middle and wide together. It does not say whether block or scenario draws come first, whether
   they are drawn resample by resample or as whole arrays, or which numpy call is used. I draw all 10,000 × 40 block
   indices first with `rng.integers(0, 40, size=(10000, 40))`, then the close, middle and wide scenario indices in turn
   with `rng.integers(0, 8, size=(10000, 8))`. I make none of the later per-band draws, since nothing here needs them.
   So even with the same seed entropy, my draws need not equal Study 2's analysis or arm E's analysis. Interval ends can
   then differ from another program's by Monte Carlo noise, of the size the two-seed check shows. Point estimates do not
   depend on the draws and should agree exactly.

2. Percentile method. The protocols say "percentile intervals" and no more. I used numpy's default (linear
   interpolation) at 2.5 and 97.5 for 95%, and 5 and 95 for 90%.

3. Equal weight for bands. Each band has 8 scenarios in the table and 8 in every resample, so the plain mean over the 24
   drawn scenarios already gives each band one third of the weight. No extra weighting was applied.

4. The pooled interval. "Tasks are resampled independently" (6.3) and "the pooled steps use each task's all-band draws"
   (6.2) are read as: each task has its own generator, and the pooled value of resample r averages the three tasks'
   values of resample r. The 120 blocks are not drawn as one pool.

5. Where an arm E source is flown. PROTOCOL-EXTRA.md section 4 says a source Study 2 already flew in the same block is
   scored on Study 2's flights. I applied that as a rule on (block, source hash): Study 2's phase if it exists, otherwise
   arm E's phase. In every block where arm E took c0 or arm C's rC1 the phase was in Study 2's run (7 in reach, 5 in
   reach3d, 1 in land). No drawn rE1 or rE2 had the same source hash as a Study 2 phase of its block.

6. Platform control re-flights. Arm E's run holds six phases with Study 2's own phase names (reach b0 and b2, reach3d b0
   and b1, land b3 and b4). They are re-flights of arm C's adopted source and are not scored. In two of these blocks,
   reach b2 and reach3d b1, c0 passed its zone trial, so arms B, C and E all adopted c0 and the control re-flew that same
   c0. There the source exists in both runs, and by rule 5 arm E is scored on Study 2's flights, as B and C are. The
   program prints, as a diagnostic only, what scoring the re-flight instead would have changed: nothing. Both re-flights
   gave the same 24 cells as Study 2's flights (17 of 24 met in reach b2, 24 of 24 in reach3d b1). So this reading cannot
   move any number here, but a program that looked in arm E's run first would be scoring the wrong flights.

7. Kept-late evaluation flights. PROTOCOL-3.md 6.2 keeps the recorded outcome of a kept-late flight in the main estimate
   and bounds it in a separate sensitivity analysis. I kept the recorded outcomes and did not compute the fills, which
   were not asked for. Three scored phases hold `kept-late.json`, all in reach3d: b34 and b39 (scored for arm A only, so
   they can touch only reach3d's B − A and, through it, the pooled B − A) and b37 (scored for all four arms, so it
   cancels in all four comparisons). No `.set-aside` folder sits beside arm E's runs, so no arm E attempt had to be told
   apart from a kept one.

8. Blocks left out. PROTOCOL-EXTRA.md section 8 leaves a block out of all arms if arm E could not complete it. All 120
   arm E blocks have their done marks and an `arms.json`, so no block was left out.

9. Arm E counts. "Its adopted procedures' flights" is read as the 24 scored flights of each block in which arm E
   adopted, counted block by block (so 24 × adopting blocks). "Met the goal" is `goal_met` true. "Ended by entering the
   zone" is `end_reason` equal to `entered_threat`. These are the only end reasons in the records: held, landed,
   entered_threat, timed_out, hard_landing and landed_off_point, and `goal_met` is true exactly for held and landed.

10. The source of truth for a flight. I took `goal_met` from each flight's `outcome.json`. I did not recompute success
    from the simulator's true positions, and I did not check hash-chained logs, timing or the platform. Those are the
    gate's checks.

11. The 90% intervals. PROTOCOL-EXTRA.md section 4 names only 95% intervals for arm E but reads the 90% interval "as in
    Study 2", and the brief asked for both, so both are printed for all four comparisons.

12. PROTOCOL-EXTRA.md section 4 says arm E's intervals come from Study 2's own bootstrap function, so that arms A, B and
    C get Study 2's draws. I did not use or open that function. My intervals are therefore my own resamples throughout,
    for B − A and C − B as well as for the arm E comparisons.

## Every file I opened

By hand, during orientation:

- `/Users/s.vajda/Development/telohelm-worktrees/p3-extra-arm/paper3/PROTOCOL-EXTRA.md`, all of it.
- `/Users/s.vajda/Development/telohelm-worktrees/p3-extra-arm/paper3/PROTOCOL-3.md`: a search for its headings, then
  lines 1 to 320 and 477 to 746 (sections 1 to 4.5, and 5 to 7).
- `/Users/s.vajda/Development/telohelm-worktrees/p3-extra-arm/paper3/protocol/contract3.py`, all of it.
- `/Users/s.vajda/Development/telohelm-worktrees/p3-extra-arm/paper3/protocol/seeds-3.json`: its SHA-256 and its
  structure (`threat_evaluation`, `blocks`, `heldout` and the header fields).
- In Study 2's runs: `learn3-<task>-b<N>/arms.json` of the six control blocks, to see what arms C and E adopted there.
- In Study 2's reach run: `learn3-reach-b0/arms.json`, and in
  `threat3-reach-b0-125734dec34bbe51bebd7c297d5298a4e5423e8c3bcb0e1e78c8d33f5b734afe/` the `manifest.json`,
  `flights/run-config.json` and `flights/threat-close-3100001/outcome.json`.
- In arm E's runs: `learnE-reach-b0/arms.json`; `logs/schedule.json` of reach; the `manifest.json` of the first
  `threat3-` phase in each task's run (reach b0 1385255e, a control phase; reach3d b0 3ba2a4f9; land b0 b453e604); the
  `manifest.json` of `learnE-<task>-b0` for each task (keys only); and `learnE-<task>-b<N>/arms.json` for all 120 blocks.
- A survey script opened every `outcome.json` under every `threat3-*/flights/` folder of the six run roots (Study 2's
  three and arm E's three), to list the end reasons. That included the six control re-flight phases and Study 2 phases
  that no scored arm uses (c0 where no arm adopted it, and arm D's sources). Nothing from that survey was scored.

Folders listed by hand, one level each (names only): `paper3/`, `paper3/protocol/`, Study 2's `records/runs/` root,
each Study 2 task run, its `logs/`, its `.set-aside/` folder, one `threat3` phase folder and its `flights/`, a
`find` to depth 4 inside that phase (which also showed the file names in its `warmup/` folder), and the one flight
folder `flights/threat-close-3100001/`; arm E's
`extra-e1/` root, each task folder, its `runs/`, each task run and its `logs/`, and `learnE-reach-b0/`.

By the program (full list in `opened-files.txt`; Study 2's run is `S2`, arm E's is `EX`):

| Count | File |
|---|---|
| 1 | `paper3/protocol/seeds-3.json` |
| 120 | `S2/scored-20261120-S-<task>/learn3-<task>-b<N>/arms.json` |
| 222 | `S2/.../threat3-<task>-b<N>-<sha>/manifest.json` |
| 222 | `S2/.../threat3-<task>-b<N>-<sha>/flights/run-config.json` |
| 5,328 | `S2/.../threat3-<task>-b<N>-<sha>/flights/threat-<band>-<seed>/outcome.json` |
| 120 | `EX/extra-e1-<task>/runs/extra-e1-<task>/learnE-<task>-b<N>/arms.json` |
| 3 | `EX/.../logs/schedule.json` |
| 61 | `EX/.../threat3-<task>-b<N>-<sha>/manifest.json` |
| 61 | `EX/.../threat3-<task>-b<N>-<sha>/flights/run-config.json` |
| 1,464 | `EX/.../threat3-<task>-b<N>-<sha>/flights/threat-<band>-<seed>/outcome.json` |

Of the arm E phases, 59 are scored and 2 are the control re-flights of reach b2 and reach3d b1, read only for the
diagnostic in point 6. The program listed each task run's top folder and `logs/` in both runs, and the `flights/`
folder of each phase it opened.

## The files I was told not to open

I opened none of the files listed under "Do not open". I did not open, read, search, run or import any file named
analysis3.py, analysis_e.py, rates_e.py, exploratory_rates.py, validate3.py or sensitivity3.py; anything under a
manuscript/ or publication/ folder; any PAPER-DRAFT-* or SUPPLEMENT-DRAFT-* file; any analysis.json, analysis-e.json,
report-e.md, rates-e1.txt or COMPARISON.md; anything under /private/tmp/claude-504/ other than this output folder; or
anything under scored-20261120-S-analysis/ or scored-20261120-S-sensitivity/.

Some of those names appeared in directory listings: `analysis3.py`, `validate3.py` and `sensitivity3.py` in the
listing of `paper3/protocol/`; the `manuscript/`, `publication/` and `extra/` folders in the listing of `paper3/`; and
the `scored-20261120-S-analysis/` and `scored-20261120-S-sensitivity/` folders in the listing of Study 2's runs root.
Seeing a name in a listing is all that happened. I also left closed several files that are not on the list but could
carry another analysis's output: `analysis-run.json` in each Study 2 task run, `scored-20261120-S-analysis.log`,
`scored-20261120-S-gate.json` and `.err`, every phase and scheduler log, the `.set-aside/` attempts, `paper3/extra/`,
`paper3/results/` and the `protocol/test_*.py` files.

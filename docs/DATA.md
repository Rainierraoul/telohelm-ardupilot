# Study records

This guide describes the records behind 'Code that never ran: testing and repairing flight procedures that a language model writes for ArduPilot in simulation' (Simon Vajda). They are in a data record at https://doi.org/10.5281/zenodo.24022883, released under [CC BY 4.0](../LICENSE-data). The [README](../README.md) describes the code that reads them.

## The files

| File | Holds | Files | ZIP size | Unzipped |
|---|---|---|---|---|
| `study2-interval-records.zip` | Study 2: for every block's search and every set of unseen flights, the manifest, the record of what each arm adopted, every flight's outcome, the summaries and the timing rows | 21,767 | 58 MB | 0.41 GB |
| `study2-analysis-output-records.zip` | Study 2: the analysis output (`analysis.json`, `report.md`), the validation check's report and the sensitivity analysis | 7 | 26 MB | 0.11 GB |
| `study2-records.zip` | Study 2: every record outside the simulator folders, which adds every request sent to the model and every reply in full, the candidate procedures, the hash-chained logs of every flight and the scheduler's logs | 120,294 | 1.05 GB | 4.04 GB |
| `study2-simulator-logs-scored-20261120-S-reach.zip`, `-reach3d.zip`, `-land.zip` | Study 2: ArduPilot's own output for every simulated flight, one ZIP for each task | 25,080, 27,505 and 23,895 | 6.59, 7.40 and 6.46 GB | 17.0, 19.0 and 16.6 GB |
| `planner-check-pass1-records.zip`, `planner-check-pass2-records.zip` | the check of ArduPilot's planner: the outcome and the planner record of every flight in each of its two passes | 1,197 each | 2 MB each | 13 MB each |
| `planner-check-summary-both.json`, `planner-check-oadj-pass1.jsonl`, `planner-check-oadj-pass2.jsonl` | the check of ArduPilot's planner: its counts over both passes, and the planner's own rows read from each flight's onboard log | 3 | not zipped | 1.9 MB |
| `extra-e1-reach-records.zip`, `extra-e1-reach3d-records.zip`, `extra-e1-land-records.zip` | the fifth arm, arm E, and the platform control: every record outside the simulator folders, with every request sent to the model and every reply in full | 8,969, 10,087 and 9,773 | 0.07, 0.09 and 0.09 GB | 0.28, 0.34 and 0.36 GB |
| `extra-e1-reach-simulator-logs-extra-e1-reach.zip`, and the same for reach3d and land | arm E and the platform control: ArduPilot's own output for every simulated flight | 4,555, 5,570 and 4,825 | 1.30, 1.60 and 1.62 GB | 3.35, 4.10 and 4.15 GB |
| `extra-e1-all-records.zip` | the reference controller (the second protocol's hand-written controller): the records of its preliminary flights and its scored flights | 3,995 | 0.05 GB | 0.18 GB |
| `extra-e1-all-simulator-logs-yard-dev-e1.zip`, `extra-e1-all-simulator-logs-yard-e1.zip` | the reference controller: ArduPilot's own output for its preliminary flights and for its scored flights | 1,425 and 1,875 | 0.45 and 0.59 GB | 1.14 and 1.50 GB |
| `extra-e1-analysis-e.json`, `extra-e1-report-e.md` | the analysis output of arm E's two comparisons and of the platform control | 2 | not zipped | 0.06 MB |
| `zone-entries-onboard-logs.jsonl` and six `.txt` files | the zone entries counted again from ArduPilot's onboard logs, and the other exploratory counts of the supplement (sections S5, S7 and S14), as the paper's scripts printed them | 7 | not zipped | 6 MB |
| `scored-2-records.zip` | Study 1 and the earlier comparison: the run folder without the simulator folders, with every request and reply in full | 32,978 | 282 MB | 1.1 GB |
| `scored-2-simulator-logs.zip` | Study 1 and the earlier comparison: ArduPilot's own output for every simulated flight | 25,565 | 7.2 GB | 18.3 GB |

Each ZIP comes with a file named after it and ending `CONTENTS-SHA256SUMS.txt`, which lists the SHA-256 of every file inside it (the two `scored-2` ZIPs share one), and `SHA256SUMS` gives the SHA-256 of the ZIPs themselves. Check the downloads against `SHA256SUMS` first.

The files of `study2-interval-records.zip` are also in `study2-records.zip`, at the same paths and with the same bytes. The small ZIP exists so that the paper's main results can be checked from a 58 MB download.

## Study 2

Study 2 flew on Deakin University's computing cluster between 20 and 22 November 2026, one job for each task. The records therefore have three run folders, `runs/scored-20261120-S-reach`, `-reach3d` and `-land`. Inside a run folder:

- `learn3-<task>-b<N>/` is one block's search, one shared set of test layouts on which all four arms searched. The code and the records call the search for a passing procedure learning, and the preliminary run the pilot, so folder names keep those words; the paper calls them search and the preliminary run. `arms.json` says what each arm adopted. In the full records it also holds each candidate's source, the request that produced it, the model's reply and the test flights.
- `threat3-<task>-b<N>-<hash>/` holds the 24 unseen zone flights of one adopted procedure, named by the SHA-256 of its source. Arms that adopted the same procedure share one folder.
- `retain3-<task>-b<N>-<hash>/` holds the same procedure's flights with no zone.
- `logs/` holds the schedule and, in the full records, the scheduler's log.

A flight's `outcome.json` gives the goal, the zone, how the flight ended and the vehicle's true position once a second. A folder whose name ends in `.set-aside` holds attempts that were stopped by a fault or flown again because a decision was late; the protocol's section 7 says when that happens, and the analysis reads only what the protocol says it reads.

A hash-chained log is one in which each record carries a hash of the one before it, so a later edit shows. The validation check verifies every such log before the analysis computes anything.

Each run folder holds `analysis-run.json`, which the analysis wrote when it ran. The analysis program refuses to run on a folder that holds one, because the protocol allows one analysis of the scored run. `reproduce.py` explains how it reruns the same computation without it.

## The planner check

The two ZIPs hold what the counts for ArduPilot's planner in the paper and its supplement are made from: each flight's `outcome.json` and `planner.json`. `study2/planner_check/summarise.py` in the code repository counts them, and `planner-check-summary-both.json` is its output. The two `oadj` files hold the rows that ArduPilot's planner wrote to each flight's onboard log, read out by `manuscript/planner_logs/read_oadj.py`; the supplement's statement in S16 about how quickly the planner found a route rests on them. The onboard logs themselves are not in this deposit.

## The two additions after Study 2

Both additions flew on the same cluster on 23 November 2026, under a second protocol written before any of their model calls or flights (`study2/PROTOCOL-EXTRA.md` in the code repository). Arm E is a fifth way of producing a procedure. Its records have one run folder for each task, `runs/extra-e1-reach`, `-reach3d` and `-land`. Inside a run folder:

- `learnE-<task>-b<N>/` is arm E's search in block N, on the same test layouts as Study 2's block N. `arms.json` says what arm E adopted, and `contexts/E/` holds what each of its requests showed the model.
- `threat3-<task>-b<N>-<hash>/` holds the 24 unseen zone flights of a procedure arm E adopted that Study 2 had not flown, in the same form as Study 2's folders. A procedure Study 2 had flown is read from Study 2's records. A `threat3` folder whose name is also in Study 2's records belongs to the platform control: six of arm C's procedures, flown again beside arm E to see whether the simulation still gave Study 2's results.
- `message-ids.jsonl` lists the ids of every reply Study 2 accepted. A reply repeating one of them would have stopped its block.

The reference controller has two run folders. `runs/yard-dev-e1` holds its preliminary flights (18 for each task and keep-out distance), on which its keep-out distance was chosen, and `runs/yard-e1` holds its 24 unseen zone flights for each task and each of its five keep-out distances, with `yard-choice.json`, the record of the distance chosen.

The derived files are the output of the paper's exploratory scripts in `manuscript/` of the code repository, run on the records above and on Study 2's. `zone-entries-onboard-logs.jsonl` has one row for every flight it read: whether the judge scored the flight as entering a zone, and the deepest point inside a zone that ArduPilot's own log shows, with the paths of the flight's record relative to the folders the script was given. The paper's zone entries counted with the onboard logs, and the sensitivity analysis that counts a crossing between two checks as a failed flight, are computed from it.

## Study 1 and the earlier comparison

One run under the second protocol, made on one Mac between 4 and 6 November 2026, produced both. It has 254 phases (58 searches and 196 flight phases) in `runs/scored-2`. `scored-2-records.zip` holds each phase's manifest, hash-chained logs, outcomes and summaries, and for each search every request and reply, the candidates, the trial flights and the library. Under section 7 of `study1/PROTOCOL-2.md`, a phase interrupted by a fault was moved out of the run folder and flown again under its scheduled name; those interrupted attempts are not in the deposit.

## Byte-identical records, and what they name

Every file is byte-identical to the original record, so every hash recorded inside the records can still be checked. The packing tool compared each file with the sums written when the run was saved, and read every member back from the finished ZIP.

The records name the folders they were written in. Study 1's name `/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-2` on the author's Mac. Study 2's and the additions' name folders under `/scratch/svajda` and `/dev/shm/svajda-...` and the cluster nodes `l40s-f-01` to `l40s-f-04`. `reproduce.py` maps the folder you unzipped into to the original name before it compares anything.

Before packing, every file was scanned for keys, tokens, passwords and e-mail addresses. The scans of Study 2's full records and of the additions' records found no key, token, password or e-mail address in any text file. Inside ArduPilot's binary onboard logs a few byte sequences match those patterns by chance, among them 4 that begin 'sk-' and 3 shaped like a web address with a password; they lie inside binary numbers and are not text.

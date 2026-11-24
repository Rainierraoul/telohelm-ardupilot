Superseded on 17 November 2026 by draft 2, `protocol/drafts/PROTOCOL-3-draft-2.md`; this draft is kept unchanged below for the record.
# Paper 3 protocol, third version: which parts of learning with a hazard present help

Draft 1, written on 11 November 2026 by Claude, the AI model that holds the protocol-3 work as its single owner (`notes/TAKEOVER-20261111.md`). It is not frozen and nothing has been run under it. It is written from four notes agreed between C3 and D3, the two AI sessions that designed this protocol, and from the owner's rulings on what they left open. C3 was a Claude session. D3 was a session of Codex, a separate AI agent that reviews this project's protocols and code. The notes are `notes/REWORK-DESIGN-C3-20261108.md` (DESIGN below), `notes/PROTOCOL3-CONTRACT-C3-20261109.md` (CONTRACT), `notes/PROTOCOL3-SCHEMA-D3-20261109.md` (SCHEMA) and `notes/SAMPLE-SIZE-C3-20261109.md` (SIZE). A number after a colon is a line. Paths are relative to `paper3/`.

The second protocol, `PROTOCOL-2.md`, was frozen on 4 November 2026 and run once (`runs/scored-2`). It stays as it was, with its code and its results. This protocol adds a new hazard study. The paper will report Study 1 from the second protocol and the hazard study from this one.

Simon Vajda, the researcher who leads the project, made the decisions that shape this version. On 8 November 2026 he ruled that 'the experiment as it was run is inconclusive and is not a publishable result' and that experimentation 'needs to be reworked and continued ... until we have a result' (`notes/D3-C3-HANDOFF.md`:730). At 4:20 pm on 11 November 2026 he was asked for 'a yes to a US$4 development sample, a yes to the scored spend, and the quiet Mac'. He answered 'yes to all 3. its 4:20pm, i hope to leave this here for 36 hours'. The coordinating Claude session relayed that answer to the owner (`notes/TAKEOVER-20261111.md`, 'Simon's approvals').

## Open before the freeze

A reader should know what is still missing before reading the rest. Each gap is marked in the text as [GAP n] and must be filled, with its source, before this text is frozen.

1. The load limit, `LOAD_LIMIT_1MIN`, from the timing preflight (section 4.6).
2. Whether the lateness rule holds on quiet flights. Scored-2 has been counted: none of its 920 hazard flights or 213 first-round learning flights is late, 7 of its 213 trial flights are, and 124 of its 3,125 held-out, disturbance and repeat flights are, all flown between 9 am and 6 pm on 5 November (corrected 12 November 2026, 9 pm: this first counted only the hazard and first-round flights). The first two preflights had late flights, and the rule was revised on 12 November 2026 for reasons given in section 4.6. The third preflight, flown under the revised rule, had 4 late flights of 150 and set no limit. What follows from it is under review (`notes/TAKEOVER-20261111.md`, 12 November 2026, 9 pm).
3. Filled on 11 November: the corrected planning simulation confirms N at 32 blocks (section 6.6).
4. Filled on 11 November: how often the task-dependent rule fires and misses, and the choice of rule (section 6.4).
5. Measured times for a learning block and for each evaluation phase, from the development sample, and the forecast of flying hours corrected from them (section 9).
6. What the development sample showed against the checks written before it was read: the rates the simulation assumed, the fresh candidates and how often arm B adopted on reach (section 8.4).
7. The spend forecast corrected from the development sample's calls and costs (section 4.5).
8. The freeze record: the commit of this text and of the code, the source fingerprint, the hashes, the number of tests and the reviews (the header and section 9).
9. The result of the scripted pilot through the scheduler, the gate and the analysis (section 8.3).
10. The quiet periods after the first, which need Simon (section 4.5).
11. Whether pooled B − A stays a primary interval. The simulation expects it to be task-dependent, and the owner would have made it secondary (section 6.4). Simon is away until the morning of 13 November and the freeze cannot wait for him. The coordinating Claude session decided on 11 November to keep the nine primary intervals, because that is the set C3, D3 and the design agreed and this text says in advance what to expect of pooled B − A. The decision is open to Simon until the freeze.
12. Whether every process that flies starts with one warm-up flight that is not counted (section 4.6). Simon must decide. It is built into the preflight and every phase before the third preflight, or into none of them.
13. The rulings of rounds two and three in `notes/TAKEOVER-20261111.md` (12 and 13 November) are not yet written into this text, except rulings 7 and 8 of round three, which are in sections 2.1, 3, 4.1 and 6.7. Sections 4.1, 4.6 and 7.2 still say that a late learning flight stops its block; since round two's ruling 3 the call is flown again in place, at most twice, and the third attempt is kept.

Some numbers in this design were chosen. They are neither measured nor derived, and the text marks each as [PICKED n].

1. The margin of 0.20, with 0.10 reported beside it. Both sessions call it 'an explicit planning assumption' (DESIGN:140).
2. The rule that fixed N: each primary interval resolves in at least 80% of simulated runs (SIZE:61).
3. The two wider clearance bands, 9 to 11 m and 19 to 21 m. D3 chose 10 m and 20 m for a development pilot (`experiments/feedback_repair/DESIGN.md`:19). The close band, 3 to 4 m, repeats scored-2's geometry.
4. Twenty-four evaluation scenarios per task, 8 in each band, and 10 retention scenarios, cut from 30 'to keep the run within days' (DESIGN:42 and 85).
5. One extra call to repair a reply's format in each candidate slot (SCHEMA:30).
6. The spending stop of US$60, which C3 set above the forecast (`protocol/run_scored3.py`:38–42).
7. Four development blocks per task (DESIGN:77).
8. The limit of 1 s behind schedule for any one command. It is one decision period, and it is the owner's ruling, still to be checked against the preflight's flights (gap 2).
9. Equal weight for each band and for each task, and the grouping of the middle and wide bands into one primary interval (DESIGN:48 and 142, SCHEMA:40).

Everything this text describes is now built. The gate has read a block that the driver built offline from recorded flights. It has not yet read a flown run or the evaluation of an adopted source (section 8.3).

## 1. Questions

Telohelm is a system in which a language model writes a short control procedure, a monitor flies the procedure in simulation, and the procedure is adopted only if it passes. An adopted procedure then flies with no model. The vehicle is a copter flown by ArduPilot in its software-in-the-loop simulator (SITL), as in the second protocol.

A threat zone is a circular area the drone must keep out of, which switches on during the flight. Entering it fails the flight. The task text tells the model that zones may appear, in every condition of this study (`SHARED_GOAL` in `ardupilot/pack.py`).

The second protocol found that procedures learned with a zone present met the goal on fresh zone flights more often than procedures learned on the same layouts with the zone removed. The differences were 0.681 for reach, 0.313 for reach3d and 0.506 for land, with 8 pairs of learning runs per task and wide intervals (`manuscript/PAPER.md`:5). That comparison changed three things together: the flights shown to the model before its first attempt, the test a candidate had to pass and the failures fed back to it. Most targets also lay about 3 m past the zone.

This protocol asks one question in three parts, and a fourth about geometry.

- RQ1, testing. Does testing candidates against the zone before adoption, with nothing else changed, alter success on fresh zone flights?
- RQ2, revision. When a candidate fails its zone test, does revising it from its failed zone flights do better than writing a fresh candidate from the original request, with the same number of candidates allowed?
- RQ3, first examples. Does seeing the zone in the flights shown before the first candidate add to success, when testing and revision are already in place?
- RQ4, geometry. Does the total gain from learning with the zone hold when the target lies well clear of the zone?

Success always means the same thing: a learning run adopted a procedure, and that procedure met the goal on a fresh zone flight. A run that adopts nothing has not supplied a working procedure, so it counts as a failure on every flight.

### 1.1 The four arms

These terms are used throughout.

- A layout is one flight set-up: its target, wind, heading and zone. A layout is flown in two versions. The threat version has the zone. The matched version is the same layout with the zone removed.
- A block is one task's set of 3 learning layouts. Every arm of a block learns on the same 3 layouts.
- A candidate is one procedure the model writes.
- A trial list is the 3 layouts a candidate must fly, in the threat or the matched version. A candidate is adopted only if it passes on all 3 (section 2).
- An arm is one way of learning within a block. There are four.

Each block makes two first requests to the model. Before either, the block's layouts are flown with no procedure in control, so the drone holds its position and does not meet the goal. These are the first-round flights, and moments from them are the examples a first request shows. P0 is the first request whose examples come from the matched first-round flights. P1 is the first request whose examples come from the threat first-round flights, in which the zone switches on at half the time limit. The candidate written from P0 is called c0, and the candidate from P1 is c1.

| Arm | First candidate | Trial list | After a failed trial |
|---|---|---|---|
| A | c0 | matched | a fresh candidate from P0, then one more |
| B | c0 | threat | a fresh candidate from P0, then one more |
| C | c0 | threat | a repair, then a repair of that |
| D | c1 | threat | a repair, then a repair of that |

A fresh candidate is the reply to P0 sent again, byte for byte, with nothing about the failure in it. Arms A and B draw their fresh candidates from one stream for the block, called f1 and f2, and each arm tests a fresh candidate on its own trial list. A repair is Telohelm's own next attempt. Its request carries the refused candidate's source, a reason for each flight that failed, and moments from the failed flights of the trial just flown (section 2.2). The repairs are called rC1 and rC2 in arm C, and rD1 and rD2 in arm D.

Arms B and C share c0 and its threat trial. If c0 passes that trial, both adopt c0 and are identical. They part only when c0 fails.

### 1.2 What differs between neighbouring arms

Each research question is one step between two arms.

- B − A answers RQ1. The two arms have the same first candidate and the same fresh candidates. Only the trial list differs: A tests on the matched layouts and B on the threat layouts.
- C − B answers RQ2. The two arms have the same first candidate, the same trial list and the same number of candidate slots. They differ in what follows a failed trial: C repairs and B samples afresh.
- D − C answers RQ3. Both arms test on the threat layouts and repair. They differ in the first candidate: D's is written from flights that show the zone.
- D − A is the total, and answers RQ4 when it is read separately for close and for distant targets.

The steps are comparisons in one fixed order, the order in which the parts would be added in practice (DESIGN:38 and 115). They are not the main effects of a factorial design. Seeing the zone without being tested against it is not an arm, and the interactions left out are not estimated.

Three limits belong with these contrasts and are repeated in section 10.

- In the planning simulation, arm B adopts nothing in 93% to 100% of reach blocks (SIZE:77). In scored-2 every reach procedure learned without the zone failed with the target 3 m past it, so a fresh candidate from P0 rarely passes a trial that includes a 3 m layout. If the scored run agrees, C − B on reach is close to arm C's own success rate, and B − A on reach measures what a strict test costs when nothing repairs the failures.
- Arm C is the first arm in which the model sees any flight with a zone in it. C − B therefore carries two things together: the evidence in the failed zone flights, and the revision of the failed candidate. This protocol does not separate them. The published comparison this step follows has the same form. In Olausson et al. (2024), the repair step is conditioned on the specification, the failed program, its error message and feedback on it (their section 3.1). Their baseline 'is simply i.i.d. sampling from the corresponding model' (their section 4), and the two are compared at an equal number of samples or tokens (their section 3.2 and Appendix A).
- A step pooled over the three tasks can hide effects that point in opposite directions (section 6.4).

## 2. What is fixed

- The learning core: the built Telohelm wheel that the second protocol used, SHA-256 `bb2c6e779b7526c85fb6ced29bd0db01f0d30a88a16e2252f2f058cab3ce2f8c`. A wheel is a built Python package file, and a SHA-256 is a fingerprint of a file's bytes. The runner checks the installed package against the wheel and refuses to start if they differ.
- The task packs, the autopilot, the judge on the simulator's true state and the velocity guard are those of the second protocol (`PROTOCOL-2.md`, section 2), at the freeze commit of this one.
- The learning model: Claude Sonnet 5.5 through Deakin's GEM gateway, requested as `bedrock/au.anthropic.claude-sonnet-5-5` (`ardupilot/scored.py`:62), with effort `high` and up to 64,000 output tokens (`ardupilot/claude_provider.py`:25–26). The provider sends no temperature and no sampling seed, so every call uses the service's default sampling, and that setting is part of the protocol (CONTRACT:23). The settings requested and the model label each reply reports are recorded for every call. The label is the gateway's own name for the model and cannot reveal a substituted model.
- The driver. `ardupilot/ladder.py` runs one block's four arms. Every request is built by Telohelm's own Coordinator, unchanged. The driver chooses only which flights a learner has seen and when it is asked.
- Candidate slots. Each arm has 3 candidate slots, the second protocol's limit of 3 attempts (`PROTOCOL-2.md`:64). A slot is one model call, and one further call if the reply breaks the core's format rules [PICKED 5]. A reply that is still invalid uses up its slot (`ardupilot/ladder.py`:23, SCHEMA:30). An arm stops at its first adoption. An arm with no adoption after 3 slots has adopted nothing.
- The adoption test. A candidate is adopted when it passes Telohelm's trial rule on all 3 layouts of its arm's trial list (`component_trial` in `ardupilot/pack.py`:535–547). On each layout the candidate must have issued the command at every step and the flight must have met the goal, with no command refused by the guard and no help requested. This is the rule scored-2 adopted by. The earlier notes' wording, 'meeting the goal on all three' (CONTRACT:7), was shorthand for it, and the owner ruled that the full rule stands. In scored-2 the two never differed: none of its 213 first-round learning flights, 213 trial flights and 920 hazard flights has a refused command or a help request, and no trial flight met the goal while failing the trial rule (trial flights added 12 November 2026, 9 pm). The gate recomputes the rule for every trial flight from its protected decision log and requires the driver's verdict to equal it. A candidate and a trial list are flown once in a block, so arms that reach the same candidate on the same list share that trial.
- Real time. Every scored flight runs in real time, as the second protocol's speed rule requires (`PROTOCOL-2.md`:66). Up to four simulators fly at once, on instances 10 to 13.
- Protocol version 3. The runner is started with `--protocol 3`. It reads `protocol/seeds-3.json` and requires `PROTOCOL-3.md` for scored phases. Every phase writes a manifest, a file that records the protocol version, the protocol file and its hash, the seeds file and its hash, the source fingerprint, the simulator instance and the machine's load.
- Source fingerprint: one hash over the executed source. For this protocol it covers the Python files in `ardupilot/`, the Gazebo files, `protocol/run_scored.py`, the three seed files, `protocol/contract3.py` and `protocol/run_scored3.py` (`source_files` in `ardupilot/scored.py`). The analysis and the gate record their own hashes in the analysis record.

### 2.1 Numbers that decide an outcome

| Number | Value | Source |
|---|---|---|
| Blocks per task | 32 | Planning simulation as rerun, `notes/SAMPLE-SIZE-RERUN-20261111.md`, Table 1 |
| Candidate slots per arm | 3 | `PROTOCOL-2.md`:64, kept |
| Calls per slot | 1, and 1 more for a format repair after a reply with text (none after an empty reply, 13 November 2026) | SCHEMA:30 [PICKED 5] |
| Trial layouts | 3, one in each band, all to be passed | DESIGN:42; `component_trial` |
| Clearance bands | 3 to 4 m, 9 to 11 m, 19 to 21 m | `ardupilot/battle.py`:95 [PICKED 3] |
| Evaluation scenarios | 24 per task, 8 in each band | DESIGN:42 [PICKED 4] |
| Retention scenarios | 10 per task, 5 calm and 5 in wind | DESIGN:85, SCHEMA:7 [PICKED 4] |
| Reach goal | within 2 m for 5 s, inside 90 s | `ardupilot/pack.py`:209 |
| Reach3d goal | within 2.5 m for 3 s, inside 120 s | `ardupilot/pack.py`:216–217 |
| Land goal | down within 1.5 m of the point at 1 m/s or slower, inside 120 s | `ardupilot/pack.py`:248–249 |
| Zone | near edge 24 to 30 m from home, radius 6 to 9 m, switched on within 19 m | `PROTOCOL-2.md`:85 |
| Decision period | 1 s | `PROTOCOL-2.md`:66 |
| Median lag limit | 0.05 s, applied to the recorded lags read on the telemetry step | 5% of the 1 s decision period, `PROTOCOL-2.md`:66; the reading of section 4.6, ruled on 12 November 2026 |
| Limit for any one command | 1 s behind schedule, read as a recorded lag of 0.995 s or more | One decision period [PICKED 8] [GAP 2]; the 0.005 s as in `protocol/analysis.py`:349 |
| A decision counted as at least 0.1 s late | recorded lag of 0.095 s or more | `protocol/analysis.py`:349, the second protocol's frozen analysis |
| Load limit | [GAP 1] | Measured in the preflight's four-at-once flights by the procedure in section 4.6 |
| Bootstrap | 10,000 resamples, seed 20261112 | `protocol/contract3.py`:17–18; 10,000 as in `PROTOCOL-2.md`:189 |
| Interval for direction | 95% | Lakens (2017); DESIGN:155 |
| Interval for equivalence | 90% | Lakens (2017), note 2: two one-sided tests at the 0.05 level |
| Margin | 0.20, with 0.10 beside it | DESIGN:140 [PICKED 1] |
| Task order seed | 20261113 | `protocol/run_scored3.py`:37 |
| Spending stop | US$60 | `protocol/run_scored3.py`:42 [PICKED 6] |

### 2.2 What each request shows the model

What a request shows is fixed by Telohelm's unchanged core, and this section is the definition. It was read from the core's code (`telohelm/examples.py` and `telohelm/learning.py` in the wheel) and from the text of requests built offline with a marker in every flight (`ardupilot/test_ladder.py`).

A request holds four things:

- the reasons, one for each flight that failed since the learner's previous request;
- example moments from those failed flights;
- a list of the learner's earlier refused attempts;
- the guard's source, with the names of the fields a procedure can read.

Two of these need defining.

- Examples come only from the failed flights named in the reasons. Each flight gives 3 moments: halfway, three-quarters of the way through and its last second. At most 7 are shown, the newest flight first. If an earlier flight of the same learner met its goal, moments from the most recent such flight are added as a contrast, to at most 8 in all. If the request is too long for the input limit, the oldest moments are dropped first.
- The earlier attempts are the last 3, each with the stage that refused it and a one-line reason. Only the most recent carries its source.

| Request | Reasons and examples come from | Earlier attempts listed |
|---|---|---|
| c0, f1, f2 | the 3 matched first-round flights | none |
| c1 | the 3 threat first-round flights | none |
| rC1 | c0's failed threat trial flights | c0, with its source |
| rC2 | rC1's failed threat trial flights | c0 and rC1, with rC1's source |
| rD1 | c1's failed threat trial flights | c1, with its source |
| rD2 | rD1's failed threat trial flights | c1 and rD1, with rD1's source |

Three things follow. A repair does not show the first-round flights again, because they were the reasons for the first request and not for this one. A second repair shows the flights of the candidate just before it, and what it keeps of the first candidate's failure is a one-line reason. If the candidate just before was an invalid reply and never flew, the reasons and examples are those of the trial before it. If no candidate of the arm has flown yet, because every earlier reply was invalid, they are still those of the first request, and the repair shows the arm's own first-round flights.

C3's contract describes a repair this way (CONTRACT:18–19). D3's schema adds 'their corresponding initial examples' (SCHEMA:26), which the core does not show. The owner ruled that the driver stands, because it is the unchanged core and the learner that scored-2 measured.

For the contrasts this means the following. C − B compares a candidate written from the failed zone trial, with the refused source and the reasons, against a candidate written again from the matched first-round flights. After the first candidate, arms C and D build their repairs in the same way from their own failed zone trials, and neither is shown first-round flights again. D − C therefore differs in the first candidate alone and in what follows from it. The zone in P1's first-round flights reaches the model through c1 and through nothing else.

The driver keeps two lists for every request and every call. `context_flights` holds every flight the learner had seen, which is more than a request shows. `shown_flights` holds the flights whose moments the text kept, taken from the core's own record of what it kept after any dropping. The gate checks the second list: a first or fresh request shows only its own first-round flights, and a repair shows only trial flights of its own arm, with at least one from the last trial flown. A repair before any flown trial may show only its own first-round flights.

## 3. Tasks and scenarios

The tasks are reach, reach3d and land, as the second protocol defines them (`PROTOCOL-2.md`, section 3). Reach flies to a point at fixed height and holds there. Reach3d does the same with a target height. Land comes down on a point slowly enough.

A scenario is one flight set-up. Its zone, the rule that switches the zone on, its wind and its heading are those of the second protocol's threat family for the same seed. The zone lies across the straight path and switches on at the first step that begins with the drone within 19 m of its near edge, or at half the time limit if that has not happened.

One thing is new. The target is placed at a set clearance beyond the zone, on the line from home through the zone's centre. Its distance from home is the distance of the zone's centre, plus the zone's radius, plus the clearance (`generate` in `ardupilot/battle.py`:88–107, with `gap_stratum`). The clearance is drawn evenly from one of three bands: close, 3 to 4 m; middle, 9 to 11 m; wide, 19 to 21 m [PICKED 3]. Without the option the generator gives exactly the second protocol's scenarios. All 667 of its reserved scenarios were compared and matched (`reproduction/protocol3-generator-regression-20261108.json`).

A target that is further from the zone is also further from home, so the flight is longer. The bands are therefore families of geometry. A difference between bands cannot be put down to clearance alone (DESIGN:129).

The matched version of a scenario has the same target, wind and heading and no zone. Episode names such as `threat-close-<seed>` never reach the model: the driver names every flight a request mentions by its alias, in all four arms, the second protocol's checks of the request apply (`PROTOCOL-2.md`, section 3), and the gate searches every request for the seed numbers of both seed books, the learning seeds included (section 6.7). Until 13 November 2026 a repair request of arm C named its failed trial layout by its raw name and seed; the leak inspection found it (`notes/LEAK-INSPECTION-20261112.md`, finding 1) and the driver was changed before the development sample.

## 4. Design

### 4.1 Learning

Each task has 32 blocks, numbered 0 to 31. A block's 3 layouts have one seed in each band (`blocks[task][b]` in `protocol/seeds-3.json`). One learning phase, `learn3`, runs the whole block in one process:

1. It flies the 3 matched and the 3 threat first-round flights.
2. It asks the model for c0 from P0 and for c1 from P1.
3. It runs the four arms. A fresh candidate or a repair is requested only when an arm needs it.
4. It writes the block's records (section 4.4).

If any flight in the block is late (section 4.6), or a model call fails in transport, times out or comes back with no served-model label, the block stops at once and is a fault (section 7). Every reply the service gives names the model that served it, so a call without that label was not answered by a model. It never uses up a candidate slot, and a finished block never holds one. A late first-round or trial flight is caught before any request uses it. A reply that is empty or breaks the format rules is the model's answer. It is recorded and uses its slot. A reply with text that breaks the format gets one format-repair call. An empty reply, or one refused or cut off with no text, gets none, since the repair would send the model service an empty assistant turn, which it is likely to refuse (13 November 2026; `notes/LEAK-INSPECTION-20261112.md`, finding 2).

The four arms run in one sitting, so no arm of a block learns at a different time from the others.

### 4.2 Evaluation on fresh zone flights

After learning, each distinct adopted source in a block flies that task's 24 evaluation scenarios, 8 in each band, with learning off and no model available (phase `threat3`). A source is the text of a procedure, identified by its SHA-256. The block's c0 flies them too, even if no arm adopted it, to give the success of a single unrevised attempt.

Arms of one block that adopted the same source share its flights: the source flies each scenario once and the outcome counts for each of those arms. This coupling is fixed here in advance. It does not rest on any claim that the simulator repeats a flight exactly. Two blocks never share flights, even if their sources are identical (CONTRACT:54).

### 4.3 Retention on ordinary flights

Each distinct adopted source also flies 10 ordinary held-out scenarios with no zone, 5 calm and 5 in steady wind (phase `retain3`). This is a secondary check that learning with the zone did not cost ordinary flying. With 10 scenarios and no stated margin it cannot show that nothing was lost.

### 4.4 Records

A learning block's folder holds:

- its manifest;
- `arms.json`, which records for each arm whether it adopted, the adopted candidate and its source hash, the candidates tried in order and each trial's outcome on each layout;
- one folder for each candidate, with its source, its request, the flights the request showed and a receipt for every model call;
- the first-round and trial flights, with their hash-chained logs;
- `warmup/`, the process's warm-up flight and its timing (section 4.6). An evaluation phase's folder has one too. It is not a flight of the study.
- `usage.jsonl`, with one row for each model call.

A hash-chained log is a record in which each line carries the hash of the line before, so an edit shows. The layout of these records is in CONTRACT:42–64 and SCHEMA:9–28, as amended by the rule in the takeover note for fields the schema does not name.

### 4.5 Order, pausing and spending

The run is one fixed schedule (`protocol/run_scored3.py`).

- Learning comes first: block 0 for all three tasks, then block 1, and so on to block 31. Within a block number the three tasks are queued in an order drawn from seed 20261113 (`task_order`).
- What is fixed is this queue: the list of phases and their order. Four workers, one for each simulator instance, take phases from it in that order. Neighbours in the queue therefore fly at the same time, and the moment each starts depends on which worker is free and on the wait for the load. A resumed run takes the remaining phases from the same queue. The scheduler writes the queue to `logs/schedule.json` at the first start and refuses a later session whose queue differs.
- Evaluation follows in the same order of blocks: for each finished block, a `threat3` phase for every source it must fly and a `retain3` phase for every adopted source.
- The gate and the analysis run once, at the end (section 6).

The order is fixed before launch so that all model use falls as early and as close together as the machine allows, and so that the flights left after learning need no model.

Pausing. The run needs many more hours than one quiet period gives (section 9), so it is made over several. It remains one run under these rules.

- A pause may be asked for at any time. It takes effect at a phase boundary: phases in flight finish and no new phase starts. A learning block is one phase, so a block is never split, and its four arms always learn together.
- A pause may be asked for because a quiet period is ending, because the machine is needed or because of a fault. It may never be asked for because of anything the study has measured: no outcome, no adoption count and no tally of any kind.
- A pause is asked for with a reason, and a later session must give a reason for resuming. The scheduler writes each start, each request for a pause, each pause taking effect and each resume to `logs/pauses.jsonl` with its time and reason. The paper reports how many there were and when.
- The scheduler is stopped only by a pause. If its process dies, the phases it started may still be flying. Nothing starts again until each folder without a done mark has been set aside (section 7.3).
- A resume uses the frozen code, seeds, protocol file and model settings. The gate requires one source fingerprint, one protocol hash, one seeds hash, one wheel and one set of model settings across the whole run, and fails otherwise (section 6.7). If the model label in the replies changes between sittings, the paper reports it.
- Pausing adds no block and removes none. The run ends when every scheduled phase has its done mark.
- While the run is incomplete, nobody runs the gate or the analysis, and nobody tabulates outcomes. The people and agents who operate the run read the scheduler's log, exit codes and timing fields. A phase log is opened only for a phase that failed.

A partial run is never analysed as this study's result (section 7.4).

Spending. Model cost is counted at the provider's list price from the recorded token counts. The forecast is 4.4 to 7.8 calls per block at US$0.033 to US$0.054 a call, which for 96 blocks is about US$14 to US$40 (SIZE:91) [GAP 7]. The scheduler starts no further learning block once the blocks that have ended have cost US$60 (`SPEND_LIMIT_USD_3`) [PICKED 6]. The count covers finished blocks, blocks that stopped on a fault and blocks set aside, over every sitting. Blocks still in flight are not read, as in the second protocol (`PROTOCOL-2.md`:98), so the stop is a guard on known spending. At most 4 blocks are in flight, each with at most 16 calls. A block held by the stop waits for Simon, and raising the stop is his decision. Simon approved the scored spend on 11 November 2026, in the words quoted in the header. The approval is taken to cover spending up to this stop and no further. The development sample of section 8.4, about US$4 (DESIGN:77), was approved in the same answer. The quiet periods after the first are not yet arranged [GAP 10].

### 4.6 Timing and the machine

Decision lag is the simulated time from the scheduled observation to the command. A late decision changes what the vehicle does. On 9 November 2026, with the machine heavily loaded, decisions arrived more than 4 s late. A procedure that had met its goal on the same scenario in 3 earlier flights then entered the zone (`reproduction/dev-timing-c3-20261109.json`).

How lag is recorded. At each step the runner reads the telemetry waiting on the link and records the lag as the newest telemetry stamp it has read minus the step's scheduled time (`ardupilot/pack.py`, `Episode.step`). Telemetry arrives ten times a second, so lag is counted in steps of 0.1 s and is recorded as, for example, 0.098, 0.1 or 0.101 s for the same one-step delay. After each command the runner reads telemetry until the first stamp at or after the next scheduled time, and the next observation is taken there. Lag is measured against the flight's schedule, the start plus one second for each step (`ardupilot/pack.py`:486–487), and the simulator does not wait while Telohelm decides. A flight that falls a whole period behind therefore stays behind, and 1 s of lag can be the sum of several slow decisions.

A recorded lag of one step has two sources. Every decision runs the procedure and the guard check as two new sandboxed processes, and these took a median of 0.072 s in scored-2's hazard flights, so the turnaround sits just below the 0.1 s step. Host lag arises when the turnaround crosses the next stamp. A clock offset arises when the stamp nearest the scheduled time falls a millisecond or two before it: the runner then waits for the next stamp, the procedure is given an observation already about 0.1 s past its schedule, and its command, after the same two calls, leaves about 0.18 s after the schedule. Either way the command reaches the vehicle up to one step later than an on-time one. The offset can be read from the previous step's simulated time (`sim_s`), but the rule counts both sources alike.

The first flight of a process. Early clock offsets come with the first flight that a process flies. In decisions two to eight they struck 24 of the 46 first flights of a scored-2 hazard phase and none of the 874 later flights, and 24 of the 30 first flights of a preflight worker and none of the 268 later ones (`reproduction/timing-diagnostic-split-20261112-091824.json`). Their cause is not known. Such a flight is a step late on three or four of its first eight decisions before any host lag (corrected 12 November 2026, 9 pm: this first said about half), and if it is short, one more late step makes it late under the rule. Every scored phase is a new process and every hazard phase opens on a close-band flight, which ends after about eight decisions when the procedure enters the zone. Without a remedy, whether a phase is ruled late would depend in part on what its procedure did. The remedy proposed is one warm-up flight at the start of every process that flies, in the preflight and in every phase: a development case flown with the task's reference controller, kept in its own folder, reported, and read by no gate and no analysis [GAP 12]. The code does this. The case is the first calm retention case of the task's development seed book, which lasts well past the first eight decisions with the reference controller and is never a reserved seed. The flight is written to `warmup/` inside the phase's folder (or the preflight worker's), with its timing in `warmup/warmup.json`. It is in no timing row, no count of flights or late flights and no outcome. The gate, the set-aside tool and the analysis do not read it.

A flight is late if any of these holds:

- a lag is missing or is not a finite number;
- the median of the flight's lags, each counted in whole telemetry steps, is above half a step, which corresponds to 0.05 s, 5% of the decision period (`PROTOCOL-2.md`:66); this means that more than half the decisions were at least one step late, or exactly half when every lag in the late half is two steps or more (corrected 12 November 2026, 9 pm: this first said exactly half is always on time);
- any command is issued 1 s or more after its scheduled time [PICKED 8].

Each lag is read on the step from 0.005 s below it, as the second protocol's frozen analysis reads its threshold (`protocol/analysis.py`:349), so 0.098, 0.1 and 0.101 s are one step and 0.0 and 0.001 s are none. A decision counts as at least 0.1 s late from a recorded lag of 0.095 s, and a command as 1 s behind from 0.995 s. The rule is one function, `timing` in `ardupilot/ladder.py`, which the driver, the evaluation phases, the gate, the set-aside tool and the preflight all use.

The third rule exists because a median can hide a few very late commands (DESIGN:157). A command one whole period behind means the vehicle flew an extra period on its previous command.

Why the median rule reads the lag on the step. The owner's first rule took the median of the recorded lag. Two timing preflights on 11 and 12 November 2026 had late flights under it, and the rule was revised before the freeze for one reason about the rule's own consistency (`notes/TAKEOVER-20261111.md`, sections of 12 November 2026, 9 am, 9:05 am and 9:25 am). The three recorded values of one step are one delay, as every other threshold here already reads them, so a flight with half its decisions one step late had a median between 0.049 and 0.0505 s and its verdict turned on a millisecond of jitter. Read on the step, its median is 0.05 s, which is not above the threshold. A second change, leaving the clock offset out, was written and then withdrawn the same morning, because a command after an offset reaches the vehicle as late as one after host lag. In the preflights, the flights the first rule called late flew within 0.26 m of on-time flights of the same seed at every step, and ended as they did, while on-time flights of one seed differed by up to 2.28 m. At the 5 m/s speed limit, one step of 0.1 s is at most 0.5 m of further travel on the previous command. Neither of the first two preflights sets the load limit, because the rule was revised after both were seen.

Scored-2 under the rule. None of its 920 hazard flights and 213 first-round learning flights is late, as under the first rule. Its 213 trial flights have 7 late under both rules, and its 3,125 held-out, disturbance and repeat flights have 124 late under this rule and 133 under the first. Every one of those 124 was flown between 9 am and 6 pm on 5 November 2026, and none of the 3,347 evaluation flights that a procedure flew between 6 pm and 9 am was late. The largest lag is 0.201 s (`reproduction/timing-preflight-20261111.json`; the owner's read-only counts, `notes/TAKEOVER-20261111.md`, 12 November 2026, 9 pm). (Corrected 12 November 2026, 9 pm: this first said none of scored-2's learning flights is late, counting only the first-round flights, and it left out the held-out, disturbance and repeat flights.) The second protocol had no rule for single flights, so none of its figures changes. The recorded median, the largest lag and the share at least 0.1 s late are computed as before and compare with scored-2's, and the median read on the step is reported beside them. The shares of host lag and of clock offset are reported for both studies from the split diagnostic.

[GAP 2: the count for the third preflight's flights under this rule.]

Lateness is read from the timing fields alone. A late flight is an infrastructure fault and is never a failed procedure (section 7.2). For every flight the records keep the median lag, the largest lag, the share of decisions at least 0.1 s late, the median read on the telemetry step and, for zone flights, the true distance at which the procedure first saw the zone. These are reported and, apart from the rules above, are not part of any gate.

The load limit. The one-minute load average is the operating system's count of processes running or waiting to run, averaged over a minute. The phase guard refuses to start a scored phase when it is above `LOAD_LIMIT_1MIN` (`load_check` in `ardupilot/scored.py`), and the scheduler waits and looks again each minute. Every manifest records the three load averages and the limit.

The limit is measured, by this procedure (`protocol/timing_preflight3.py`). On a machine left to itself, the development evaluation and retention scenarios of all three tasks are flown in real time with each task's authored reference controller: 10 flights for each task one at a time on instance 10, then 40 for each task on instances 10 to 13 together. In the four-at-once stage each simulator flies the ten scenarios in its own order and the four start a quarter of a second apart, so that no two fly the same scenario at the same moment, as in the scored run, where the four simulators fly different phases. The first two preflights flew the same scenario on all four together. That made the four decisions of every second start their sandboxed processes at the same instant, which alone takes 42.5% of them past one step (`reproduction/timing-diagnostic-sandbox-20261112-082315.json`). If every flight of both stages is on time, the limit is the highest one-minute load average recorded at the start of any four-at-once flight. A load at which only one simulator was flying has not been checked with four, so the one-at-a-time flights do not set the limit. If any flight is late there is no limit: the machine is made quieter and the preflight is flown again, and every attempt is kept. In the loads seen so far, 1.20 to 4.95 four at once and 0.84 to 4.98 one at a time, start load did not separate late flights from on-time ones, so the limit guards against starting at a load nobody has checked and does not predict lateness below it. The limit is [GAP 1], from `reproduction/` [GAP 1: file]. [Under review, 12 November 2026, 11:30 pm: the fourth preflight, flown at night on 12 November, passed under this rule and gives a limit of 4.89 from `reproduction/timing-preflight-flights-20261112-214408.json`. Rulings 2 to 5 of the round-two section of `notes/TAKEOVER-20261111.md` set the conditions for flying and what happens to a late learning flight. This section and section 7.3 are brought into line after a fresh reviewer has read those rulings and the code.]

The reference controllers ignore the zone, so the preflight's hazard flights end when the drone enters it. That does not affect lag, which does not depend on what the command is. Whether those flights met their goals is evidence of nothing.

The guard checks the load when a phase starts and cannot protect a phase already flying. The machine must therefore stay quiet for as long as any flight is in the air:

- no test suite, script or other shell command runs, in this repository or any other, because each decision starts two processes and anything else that starts processes or uses the processor competes with them;
- no other simulator and no other heavy job runs, and the phase guard refuses to start if a simulator outside instances 10 to 13 is running;
- no software update is installed and Spotlight does not index `paper3/runs`;
- the machine is on mains power and awake.

Agents may read and write files while flights are in the air. A session that waits on a run waits on its process number with a single time limit and does not poll. The preflight is flown with the same sessions open as the scored run will have.

## 5. Seeds

All scored seeds are reserved in `protocol/seeds-3.json`, written by `protocol/make_seeds_3.py` on 9 November 2026 before any use. The reservation holds 456 seed numbers. A scan of the run records and of the first two protocols' reservations checked 1,193 earlier numbers and found no clash (`reproduction/seeds3-reservation-d3-20261109.json`). No seed number is shared by two tasks, bands, roles or cohorts. The four arms of a block deliberately use the same layouts.

- Learning blocks, 3 seeds each, one for each band: reach 3000001 to 3003103, reach3d 3010001 to 3013103 and land 3020001 to 3023103, in steps of 100 for each block.
- Evaluation, 8 seeds in each band: reach 3100001 to 3100208, reach3d 3110001 to 3110208 and land 3120001 to 3120208.
- Retention, 5 calm and 5 wind: reach 3200001 to 3200105, reach3d 3210001 to 3210105 and land 3220001 to 3220105.
- Development seeds, used only before the freeze, lie from 4000001 to 4220102 in the same pattern: 4 blocks per task, 2 evaluation seeds in each band, and 2 calm and 2 wind retention seeds.

No scored seed is flown or shown to a model before the freeze. Offline tests build scenarios from the seed book and fly nothing.

## 6. Analysis

The analysis script (`protocol/analysis3.py`) and the gate (`protocol/validate3.py`) are frozen with this protocol. The analysis runs once, on a run the gate has passed, and refuses to write into a folder that already holds an analysis.

### 6.1 The outcome

For each task the analysis builds one table of outcomes with a cell for every arm, block and evaluation scenario: 4 arms by 32 blocks by 24 scenarios. A cell is 1 if the arm adopted a source and that source met the goal on the scenario, and 0 otherwise. An arm that adopted nothing has 0 in all 24 cells of its block. The scenarios are the planned ones, taken from the seeds file, so nothing drops out when an arm fails to adopt.

### 6.2 Intervals

A contrast between two arms is the difference of their means over the cells in question. Its interval comes from a crossed bootstrap with 10,000 resamples and seed 20261112. Each resample draws blocks with replacement, keeping a block's four arms together. It also draws scenarios with replacement within each band, and the same scenario draw applies to every block and arm. The bands keep equal weight. Intervals are percentile intervals. Each is a pointwise interval for its own contrast, and the nine primary intervals together make no claim of joint coverage.

### 6.3 The nine primary intervals

- For each of the three tasks, D − A on the 8 close scenarios.
- For each of the three tasks, D − A on the 16 middle and wide scenarios together.
- B − A, C − B and D − C, each over all 24 scenarios and pooled over the three tasks with equal weight. The tasks are resampled independently.

C − B is the central contrast and is reported first. Each pooled step is printed beside its three per-task estimates and intervals. The per-task steps are secondary.

What each can be read as, and what it cannot.

- D − A, close targets. The difference, for one task, between learning with the zone shown, tested and repaired, and learning by test and selection with no zone, on fresh flights with the target 3 to 4 m past the zone. It includes failures to adopt. It cannot be read as the effect of any one part, as the effect of telling the model about zones, since every arm is told, or as success given adoption. It is also not a repeat of scored-2's comparison: arm A samples afresh where scored-2's arm repaired, and every candidate here must pass on all three bands.
- D − A, distant targets. The same total with the target 9 to 21 m past the zone. A difference from the close band shows that the total depends on this family of geometry. It cannot be put down to clearance alone (section 3).
- B − A. What changes when the adoption test includes the zone and nothing else does. It can be negative, because a stricter test adopts less often. It cannot be read as the value of testing in a system that also repairs.
- C − B. What revision from the failed zone flights adds over sampling afresh without them, from the same first candidate, under the same test and the same number of slots. It cannot be read as the effect of revision alone or of feedback alone (section 1.2). Where arm B adopts nothing in a task, that task's C − B is arm C's own success rate.
- D − C. What seeing the zone before the first candidate adds when the zone test and repair are already present. It cannot be read as the effect of zone examples without testing, which is not an arm.
- Every pooled step is an average over these three tasks. It says nothing about other tasks.

### 6.4 What each result is called

Each primary interval is given one of four names, fixed here. The names combine a test of difference from 0, read from the 95% interval, with a test of equivalence within the margin, read from the 90% interval. Lakens (2017) sets out the 4 combinations and uses a 90% interval for the equivalence test because it is two one-sided tests at the 0.05 level. The intervals here are bootstrap intervals and not that article's t tests. The margin is 0.20 [PICKED 1].

| The 95% interval | The 90% interval | The result is called | Key in `analysis.json` |
|---|---|---|---|
| lies wholly above 0, or wholly below | does not lie wholly inside −0.20 to +0.20 | a gain, or a loss | `different_not_equivalent` |
| lies wholly above 0, or wholly below | lies wholly inside −0.20 to +0.20 | a gain, or a loss, smaller than the margin | `different_and_equivalent` |
| includes 0 | lies wholly inside −0.20 to +0.20 | no gain or loss as large as the margin | `equivalent_not_different` |
| includes 0 | does not lie wholly inside −0.20 to +0.20 | unresolved (Lakens's 'undetermined') | `unresolved` |

A gain whose 95% interval lies wholly above +0.20 also carries the label useful gain, and a loss wholly below −0.20 the label useful loss. The same table is reported with a margin of 0.10. The margin is a planning assumption. This protocol makes no claim about what a gain of a given size is worth.

'No gain or loss as large as the margin' supports the absence of an effect that large. It does not show that there is no effect. An unresolved interval is reported as unresolved.

A fifth name applies to the pooled steps. When one task's 95% interval for a step lies wholly above 0 and another's lies wholly below, the step is called task-dependent and its pooled name is not used (SIZE:71). Task-dependent is a result. It says that the step raised success on one task and lowered it on another, each shown by that task's own interval.

Pooled B − A is expected to be task-dependent. In the corrected simulation its three task values have opposite signs in every combination, because arm B adopts almost nothing on reach and does adopt on the other two tasks (`notes/SAMPLE-SIZE-RERUN-20261111.md`, Tables 2 and 3). At 32 blocks the rule names it task-dependent in about 51% of simulated runs when distant targets are no easier than close ones. The share is 75% to 77% in the middle case and 13% to 14% when distant targets are easy.

The rule is weak, because it needs two per-task intervals to exclude 0. In the middle case the task values are −0.34, +0.12 and +0.16. In 17% to 19% of those runs the rule stays silent and the pooled step is named 'no gain or loss as large as the margin'. That name is then true of the average and misleading about testing. Three rules of reporting follow.

- RQ1 is answered from the three per-task estimates of B − A, which are always printed with their intervals.
- The pooled name is always worded 'no pooled gain or loss as large as the margin over these three tasks'.
- When the per-task estimates of a pooled step differ in sign, the paper says so beside the pooled name, whatever the intervals show.

A rule on the difference between two tasks was tried in the simulation. It catches B − A in 77% to 100% of runs. It also fires in up to 33.5% of C − B runs and 36.1% of D − C runs in which the tasks agree in sign, where the present rule fires in at most 1.2% and 4.5%. It would take the pooled name away from the central contrast in about one run in three, so the present rule stays.

Whether pooled B − A should remain a primary interval is open item 11. The owner would have made it secondary and answered RQ1 from the per-task estimates, leaving eight primary intervals: a pooled mean of effects that the design itself expects to have opposite signs answers no question a designer has. The coordinating session decided to keep the nine as agreed, and this text is written for the nine. The decision is open to Simon until the freeze.

### 6.5 Secondary estimates

Named in advance (DESIGN:50–55) and reported with the same intervals where they are contrasts:

- every contrast in each band, and every step for each task;
- C − B within the blocks where c0 failed its threat trial, since that failure comes before the two arms part;
- model calls, tokens and list cost, given twice: the unique spend of the experiment, and each arm's cost as if it had run alone, charged in full for any request or trial it shares;
- the candidate at which each arm adopted, and how often each arm adopted nothing;
- how flights ended, by arm;
- the success of c0 on the evaluation scenarios;
- retention on the ordinary scenarios, by arm;
- the share of fresh candidates whose source is identical to their block's c0;
- lag, largest lag, the share of late decisions and first-sight distance (section 4.6).

Precedence: the primary intervals lead the paper's answer. Secondary estimates are reported beside them and do not override them. If they point the other way, the paper says so.

### 6.6 Sample size

N is 32 blocks per task and is fixed before the freeze. It is not changed after any scored outcome exists, and neither are the margin or the set of primary intervals (SCHEMA:44). The run is never extended.

N came from a simulation that draws procedures from scored-2's outcomes and sweeps what is unknown (SIZE:17–25). The unknowns are how much easier distant targets are and how good a repair is, including a repair that does worse than a fresh sample. The rule was the smallest N at which each primary interval is resolved, meaning not unresolved, in at least 80% of simulated runs in every combination [PICKED 2] (SIZE:61). At 32 blocks the weakest intervals stood at 0.80 and 0.81 (SIZE:89).

Two faults were found in that simulation. It was fitted to 15 first-candidate adoptions in 24 and 7 rescues in 9, where scored-2's records give 16 in 24 and 6 in 8 (`manuscript/PAPER.md`:162; `reproduction/ladder-planning-audit-d3-20261109.json`). It also named results from one 95% interval, where section 6.4 uses two. The second fault can only have made it resolve less often, because the 90% interval lies inside the 95% one.

The simulation was corrected and run again on 11 November 2026, with 2,000 simulated runs for each combination (`notes/SAMPLE-SIZE-RERUN-20261111.md`, Table 1). The counts are read from the 24 scored-2 summaries, and every name comes from `analysis3.classify`, the function the analysis itself uses. At 32 blocks the weakest interval resolves in 83.0% of runs (D − A on reach at 10 to 20 m) and the next in 83.2% (D − A on land at 10 to 20 m). Every other interval is at 96.8% or more. The standard error of a share near 83% is about 0.8 points. At 24 blocks the weakest is 72.0%, and at 40 blocks 87.2%. N therefore stays at 32.

A run in which a pooled step is named task-dependent counts as resolved, because that name is a definite result (section 6.4). Counted otherwise, pooled B − A would resolve in 23.3% of runs at 32 blocks and 15.2% at 40, so no N would change it, while C − B and D − C would stay at 93% or more.

The rerun has three limits of its own. It uses 2,000 bootstrap resamples where the analysis uses 10,000. The scored-2 outcome files behind its pools are not hashed. The success rates at 10 and 20 m are assumed, and the two weakest intervals are the ones that depend on them.

The 80% is the chance for one interval taken alone, under the simulation's assumptions. It is not the chance that all nine resolve (DESIGN:153). A run that ends with unresolved intervals is reported as it is.

### 6.7 The gate

Before any outcome is computed, the gate checks the whole run and fails closed. It derives the schedule from the seeds file: 96 learning blocks, then the evaluation and retention phases implied by which sources were adopted. It then requires that:

- every scheduled phase is present with its done mark, and there is no extra phase;
- every phase holds exactly its scheduled scenarios, each once, with the scheduled parameters;
- every hash-chained log checks against its heads file, and every result agrees with its flight's own record and log;
- every success agrees with the simulator's true positions and speeds;
- no flight is late (section 4.6), and every phase started at or below the load limit;
- within a block, the candidates, requests, trials and adoption agree with `arms.json`; a fresh request is identical to c0's; a first request shows only its own first-round flights; a repair shows only trial flights of its own arm, with at least one from the last trial flown;
- each trial passed exactly when all 3 of its layouts passed the trial rule, as the gate recomputes it from each flight's protected decision log, and no layout is recorded as passed against its flight's record;
- every model call of a scored run is a real call with a served-model label, and all calls requested the same settings;
- no request contains a seed number of either seed book: evaluation, retention and, since 13 November 2026, learning;
- a format repair follows only a reply with text, and a slot that failed the format with one call had an empty reply;
- all phases share one protocol hash, one seeds hash, one wheel, one source fingerprint and one set of model settings, and no scored phase ran with uncommitted source.

A learning block that finished with an arm adopting nothing is a completed non-adoption and supplies planned zeros. A block that is missing or stopped is a fault, never a zero. If any check fails, the analysis computes no outcome.

Operating rule: nobody reads flight outcomes before the gate passes on the complete run. Phase logs print outcomes as flights land, so for the logs this is a rule and not something the code enforces. It binds every agent that operates or reviews the study, and Simon.

No expectation is stated for the direction or size of any step. The simulation's ranges are planning inputs and not predictions to be confirmed.

## 7. Faults, late flights and reruns

### 7.1 Faults

A fault is a failure of the machine or the model service, and never of a procedure. The faults are: the simulator failed to start, the connection to it dropped, the simulator's true state was missing, the runner crashed, a model call failed in transport or timed out, or a flight was late. A phase with a fault does not get its done mark. The scheduler holds it and lists it, and never reruns it by itself.

### 7.2 Late flights

Lateness is decided from the timing fields of a flight, and from nothing else. In a learning block the driver checks each flight as it lands and stops the block at the first late one, before any request can use that flight. In an evaluation phase the phase ends with a failure if any of its flights was late.

### 7.3 Setting a phase aside and flying it again

The unit is the whole phase. One flight is never replaced.

- The owner of the run decides that a held phase is set aside, using the set-aside tool (`protocol/set_aside3.py`), with one of two reasons. `late` means a flight in the phase was late. `crashed` means any other fault of section 7.1 that left the folder without a done mark.
- For `late` the tool opens one file, the phase's `timing.json`, reads six named timing fields of each flight, and refuses unless a flight is recorded late. For `crashed` it reads nothing in the phase. It never opens an outcome, a flight record, `arms.json` or the phase log.
- The tool refuses a phase that has a done mark, so a finished phase cannot be removed once its result exists. It refuses while a scheduler is running on the run, and while any process still names the phase's folder.
- The tool writes a receipt: the phase, the attempt number, the reason, the time, the timing fields it read and the SHA-256 of `timing.json`. It moves the phase's folder and its log to a folder beside the run root, `<run>.set-aside/<phase>-attempt<n>`, where they are kept. This is the second protocol's treatment of a crashed phase (`PROTOCOL-2.md`:219–221).
- The phase is then run again under its scheduled name with the same seeds. A learning block makes new model calls.
- The gate sees one folder for each scheduled phase. The paper lists every phase set aside, with its receipt, and the model calls of a block set aside are counted in the spend. Each is also entered in the deviations file.
- A phase that is late a second time on a machine under the load limit goes to Simon before anything more is done, because the procedure itself may be slow.

### 7.4 The gate has no exception path

If a phase cannot be completed under these rules, the study has no gated result. Simon decides what follows.

A partial run is not analysed as this study's result, whatever its size. If Simon asks for a reading of an incomplete run, it is a deviation analysis and is labelled as one. It uses the leading block numbers that are complete for all three tasks, as the schedule of section 4.5 fixes them, with no choice by anyone. It is not given the names of section 6.4. Such a reading is unbiased only if the stop did not depend on outcomes, and the paper would say that this is assumed.

## 8. Development evidence

This section records what led to the design. Nothing in it is reported as a result of this protocol.

### 8.1 The second protocol's run

`runs/scored-2` passed its gate on 6 November 2026. Its Study 2 differences are those quoted in section 1. Learning with the zone adopted the first candidate in 16 of 24 runs, the second in 5 and the third in 1, and 2 runs adopted nothing. Learning without the zone adopted the first candidate in all 24 (`manuscript/PAPER.md`:162).

### 8.2 Development flights, 8 and 9 November, no model

- D3 flew 9 flights on one development reach layout with clearances of 3, 10 and 20 m. An old reach procedure learned without the zone timed out at 3 m and met the goal at 10 m and 20 m. An old procedure learned with the zone and an authored reference met the goal at all three. Two of the 9 flights had a median lag above 0.05 s (`reproduction/dev-geometry-d3-20261108.json`).
- One procedure flown twice on one scenario ended the same way both times, with median lags of 0.198 s and 0.151 s (`reproduction/dev-repeat-d3-20261109.json`).
- The same two flights were repeated under load. At a one-minute load of 18 to 58 the median lag was 4.2 to 4.7 s and one flight entered the zone. At 6.5 to 7.7 it was 0.1 s (`reproduction/dev-timing-c3-20261109.json` and `dev-timing-c3-20261109-b.json`). Scored-2's hazard flights had a median of 0.001 s.

### 8.3 The driver and the gate

One block was run with scripted replies and no model on 9 November, at ten times real speed and a load average of 75. Every trial flight was late, with lags of 3 to 875 s. Those lags are the flight falling behind its schedule step after step: at ten times real speed a decision that takes 0.2 s lets 2 s of simulated time pass. No model is called inside a flight. The block showed that the driver runs to the end and writes its records, and nothing else (`runs/dev-ladder-c3-20261109-b`; `notes/TAKEOVER-20261111.md`, rulings of 5:05 pm).

On 11 November the driver and the gate, which had been written apart, were brought together. A block that the driver built offline from recorded flights passes the gate's learning check, and all 123 offline tests pass. The gate has not yet read a flown run, and no adopted source has been through it. [GAP 9: the scripted pilot at real time on a quiet machine, one block per task through the scheduler, the gate and the analysis, with scripted replies under which arms adopt, and the number of phases and flights the gate passed.]

### 8.4 The development sample

Four blocks per task on development seeds, with real model calls, about US$4 [PICKED 7]. It checks that the design can be flown and that what it shows lies inside the ranges the simulation assumed. Four blocks cannot estimate a rate, and the sample is not a test of any step (DESIGN:77, SIZE:95).

The checks were fixed before any sample existed. The table of what the sample may show is `notes/SAMPLE-SIZE-RERUN-20261111.md`, Table 4, written at 5:18 pm on 11 November 2026. For each count the sample will produce, it gives the range that simulated samples took over the whole grid, in two forms.

- A count outside the full range is one that no simulated sample produced. The simulation's model is then wrong for it. The simulation is corrected and run again, and N is looked at again before the freeze.
- A count outside the central 95% range and inside the full range is reported as rare. It changes nothing by itself, because with about 30 counts a few will fall there by chance.

Six further checks, none of them a test of a step.

- If every fresh candidate requested in the sample has the same source as its block's c0, arm B is c0 repeated and the design returns to Simon.
- The gate and the analysis pass on the sample.
- Each repair request showed what section 2.2 says, read from the record of flights shown.
- The number of trials in which every goal was met and the trial rule still failed.
- The number of blocks stopped by a fault, by kind, and whether each was set aside and flown again cleanly.
- No flight was late, and how long phases waited for the load.

[GAP 6: what the sample showed against each check, including how often arm B adopted on reach. GAP 5: the measured times.]

### 8.5 Timing preflights and diagnostics, 11 and 12 November, no model

- The first preflight (`reproduction/timing-preflight-flights-20261111-212412.json`) stopped after 108 flights when macOS installed an update and restarted the machine. Twelve four-at-once flights of reach were late under the first rule, all between 9:39 and 9:46 pm. It sets no limit.
- The second preflight (`reproduction/timing-preflight-flights-20261112-065219.json`) finished its 150 flights. Four four-at-once flights were late under the first rule, two of them ties at a median of 0.0505 s. It sets no limit.
- Under the revised rule of section 4.6 the first would have ten late flights and the second two. Neither is used for the limit.
- Both preflights flew the same scenario on all four simulators together. A diagnostic with no simulator timed a decision's two sandboxed calls: a median of 0.081 s for one process and for four spread a quarter of a second apart, with none reaching 0.1 s, and 0.099 s for four at the same instant, with 42.5% reaching it (`reproduction/timing-diagnostic-sandbox-20261112-082315.json`).
- A diagnostic on 12 November flew the four-at-once stage of reach with each simulator in its own order and the four started a quarter of a second apart (`reproduction/timing-diagnostic-rotated-20261112-085816.json`). Host lag struck four of the 432 decisions after the first, against 11.7% and 38.8% when the same stage was flown together. Two flights were late, both the first flight of their simulator (section 4.6, the first flight of a process).

## 9. Order of work and the freeze

Before the freeze, in this order:

1. the code jobs of the takeover note, each reviewed by an agent that did not write it;
2. the timing preflight, which sets the load limit;
3. the scripted pilot;
4. the development sample;
5. the completion of this text;
6. two cold reviews, by Fable and by a fresh session that has seen none of the design.

Cold means read by a reviewer who has not seen the work before. Fable is a Claude model used as a cold reviewer. If Codex is available, it reviews the text and the code as it did for the second protocol.

What the freeze fixes:

- this text, as `PROTOCOL-3.md`;
- `protocol/seeds-3.json`;
- the executed source, through the source fingerprint of section 2, which includes the load limit in `ardupilot/scored.py` and the scheduler's order and stop;
- `protocol/analysis3.py`, `protocol/validate3.py` and `protocol/contract3.py`;
- the learning-core wheel and the model settings.

How it is recorded. The final draft is copied to `PROTOCOL-3.md` with the freeze edits made, and committed. The header then gives [GAP 8]:

- the date and time of the freeze;
- the commit of the text and the commit of the code;
- the SHA-256 of `PROTOCOL-3.md`, of `seeds-3.json`, of the wheel and of the three analysis files;
- the source fingerprint;
- the number of offline tests that pass;
- the reviews, with their files.
 The runner refuses a scored phase without `PROTOCOL-3.md` or with uncommitted source (`guard` in `ardupilot/scored.py`), and writes the protocol's path and hash into every manifest. `PROTOCOL-3-DRAFT.md` is not changed while any pilot is running, because pilots record its hash.

After the freeze this file is never edited. Any departure is recorded in `PROTOCOL-3-DEVIATIONS.md` with its date, its reason, who decided it and the phases it affects. Simon decides each deviation, on a proposal from the owner or a reviewer. Entries are added and never changed or removed, and the paper reports every one.

Operating rule: between the launch and the end of the analysis, nobody edits the fingerprinted files, the analysis files or `PROTOCOL-3.md`. The rule binds every agent working in this repository, and Simon.

Launch, from `paper3/`:

`nohup caffeinate -i .venv/bin/python protocol/run_scored3.py run runs/scored-3 > runs/scored-3-launch.log 2>&1 &`

The plan is 96 learning blocks, then the evaluation and retention phases, four at a time, then the gate and the analysis. The forecast is 90 to 124 flights for each block, 8,600 to 11,900 in all. At scored-2's rate of 126 flights an hour that is 68 to 94 hours of flying, apart from pauses (DESIGN:144, SIZE:91). [GAP 5: the forecast corrected from the development sample's measured times.]

## 10. What this protocol cannot show

- It cannot say what the model's revision adds apart from the evidence in the failed zone flights. C − B carries both.
- It cannot say what seeing the zone adds without testing against it. That arm does not exist, and the interactions between the parts are not estimated.
- On a task where arm B rarely adopts, it cannot compare revision with a working alternative. There, C − B is arm C's success, and B − A is the cost of a strict test.
- A pooled step can hide task effects that point in opposite directions. The per-task estimates are printed for that reason, and they are wide.
- It cannot attribute a difference between bands to clearance, because mission length changes with it.
- It cannot show that learning with the zone costs nothing in ordinary flight. Retention has 10 scenarios and no margin.
- 'No gain or loss as large as the margin' is a statement about 0.20, a planning assumption. It is not a statement that an effect is absent, or that 0.20 is the size that matters.
- The nine intervals are pointwise. The design gives each about an 80% chance of resolving under its assumptions, and no assurance that all will.
- The results hold for one model, one learning core, three tasks, one kind of hazard and simulated flight. The model label cannot reveal a substituted model.
- Thirty-two blocks per task come from one served model over the days of the run. If the service changes the model between sittings, the labels may not show it.
- Procedures do not perceive the zone. It arrives as coordinates.

## References

Lakens D (2017) Equivalence tests: a practical primer for t tests, correlations, and meta-analyses. Social Psychological and Personality Science 8(4):355–362. The 4 outcomes and note 2 on the 90% interval were read at https://pmc.ncbi.nlm.nih.gov/articles/PMC5502906/ on 11 November 2026.

Olausson TX, Inala JP, Wang C, Gao J, Solar-Lezama A (2024) Is self-repair a silver bullet for code generation? ICLR 2024. arXiv:2306.09896v5. Sections 3.1, 3.2 and 4 and Appendix A were read at https://arxiv.org/html/2306.09896v5 on 11 November 2026.

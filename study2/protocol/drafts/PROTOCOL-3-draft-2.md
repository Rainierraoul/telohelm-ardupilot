# Paper 3 protocol, third version: which parts of learning with a hazard present help

Draft 2, written on 17 November 2026 by a Claude session from draft 1 (`protocol/drafts/PROTOCOL-3-draft-1.md`) and from the rulings taken since it in `notes/TAKEOVER-20261111.md` (the note, below), with `cluster/README.md` and the code as the sources of every number. That session wrote in decisions that had already been taken, each with its source, and decided nothing. Where the note leaves something open, this text says so and says to whom. Draft 1 was written on 11 November 2026 by Claude, the AI model that then held the protocol-3 work as its single owner. It was written from four notes agreed between C3 and D3, the two AI sessions that designed this protocol, and from the owner's rulings on what they left open. C3 was a Claude session. D3 was a session of Codex, a separate AI agent that reviews this project's protocols and code. The notes are `notes/REWORK-DESIGN-C3-20261108.md` (DESIGN below), `notes/PROTOCOL3-CONTRACT-C3-20261109.md` (CONTRACT), `notes/PROTOCOL3-SCHEMA-D3-20261109.md` (SCHEMA) and `notes/SAMPLE-SIZE-C3-20261109.md` (SIZE). The first owner's session ended on 13 November, and a new Claude session took the work over as owner on 16 November (the note, round five). The coordinating Claude session, which submits every job to the cluster, took rulings 23 to 25 and 27 to 35 under the same delegation. After the writer handed this draft back, the coordinating session checked it, took rulings 31 to 33 and wrote them in, which filled gaps 9 and 10 and most of gap 8 (`protocol/drafts/CHANGES-PROTOCOL-3-draft-2.md`, Part 3). The note's rulings are cited by round and number. Round two has rulings 1 to 5, round three 1 to 8 and round four 1 to 15, and round five carries on from 16 to 35, so a number from 16 up names its ruling alone. This text is not frozen, and no scored flight has flown under it. The rehearsal of record passed on 16 November, and the development sample has not flown (section 8). A number after a colon is a line. Paths are relative to `paper3/`.

The second protocol, `PROTOCOL-2.md`, was frozen on 4 November 2026 and run once (`runs/scored-2`). It stays as it was, with its code and its results. This protocol adds a new hazard study. The paper will report Study 1 from the second protocol and the hazard study from this one.

Simon Vajda, the researcher who leads the project, made the decisions that shape this version. On 8 November 2026 he ruled that 'the experiment as it was run is inconclusive and is not a publishable result' and that experimentation 'needs to be reworked and continued ... until we have a result' (`notes/D3-C3-HANDOFF.md`:730). At 4:20 pm on 11 November 2026 he was asked for 'a yes to a US$4 development sample, a yes to the scored spend, and the quiet Mac'. He answered 'yes to all 3. its 4:20pm, i hope to leave this here for 36 hours'. The coordinating Claude session relayed that answer to the owner (`notes/TAKEOVER-20261111.md`, 'Simon's approvals').

He delegated the rest. The owner and the coordinating session decide as he would and bring him only what needs him, and every ruling they take that way is open to him until the freeze (the note, round two and round five, opening). On 13 November he said yes to model keys on the cluster (round four, opening), and his key is copied there (`cluster/README.md`). On 16 November he decided that Paper 3 flies as CPU-only jobs on the gpu partition of Deakin's cluster while its cpu partition is full: "do it, we need to get this paper out" (ruling 22). The same day he renewed his yes to the US$4 development sample: 'Still a yes - need to get this work out asap' (round five, decision 6). That evening, with the rehearsal being prepared, he said "it is most vitally important that we do good science first and foremost". The note reads this as meaning that no gate is loosened to make the rehearsal pass, and that the development sample is read before the freeze for whether any arm can adopt at 0.3 s (ruling 27).

## Open before the freeze

A reader should know what is still missing before reading the rest. Each gap is marked in the text as [GAP n] and must be filled, with its source, before this text is frozen. Draft 1's gaps are renumbered here, and what became of each is listed after the new list.

1. What the development sample showed against the checks written before it was read: the rates the simulation assumed, the fresh candidates and how often arm B adopted on reach (sections 6.6 and 8.4). The sample has not flown. It waits for the model key to work again, which is Simon's to settle (ruling 29).
2. Measured times for a learning block and for each evaluation phase on the platform of record, from the development sample, and the forecast of flying hours corrected from them (sections 8.4 and 9.2).
3. The spend forecast corrected from the development sample's calls and costs (section 4.5).
4. Whether any arm can adopt at the delay of 0.3 s in reach and land. The scripted candidates no longer pass a threat trial there, so the development sample is the first test of it, and it is read before the freeze (sections 6.6, 8.4, 8.9 and 10; ruling 26, point 2; ruling 27).
5. How much of the room between one step of own lag and the three-step deadline a procedure written by a model uses, read from the development sample's own lags, and the count of the sample's sandboxed calls by `cluster/read_calls.py` (sections 4.7, 8.4 and 10; ruling 28, points 3 and 6).
6. The freeze record: the commit of this text and of the code, the source fingerprint, the hashes, the number of tests and the reviews. Also which checking tools and files outside the source fingerprint the freeze fixes, which no ruling yet says (section 9.2). And whether the gate reads set-aside attempts for their route state in the scored run, which today only the pilot's pass script does (section 7.3; ruling 32, point 7).
7. How the scored run is flown on the cluster: its batch jobs, the time limit of each and the command that starts it. No ruling sets these. Round four's ruling 7 asks only that a job's time limit hold its longest phase, taken from measured phase times (sections 4.5 and 9.2). Open to the owner.
8. Built and reviewed on 17 November, and not yet tried on the gateway: a check of the model key at the start of the chain and again just before its paid step, so that a refused key stops the chain with its own status (sections 7.1 and 9.1; ruling 29, point 5; ruling 32). The request is a token count. On 17 November the key answered again, and the check's first request was answered with a count, from the Mac and then from the node at the start of the chain that carries the sample (ruling 35). What the gateway returns to a blocked key's count has not been seen.
9. Filled on 17 November from records already made: the three measurements of the L40S nodes that ruling 22 asks for, which are the clock speed and governor, a sandboxed call's time on the new wheel, and the memory a four-at-once job peaks at (section 4.7; ruling 31, point 4). The memory figure is for the whole job, the files it keeps in memory included, and no whole sample has flown yet.
10. Filled on 17 November: a job asks for 16 cores and 32 GB, as every job on the platform of record flew (section 4.7; ruling 31, point 3). The ruling is the coordinating session's, and it is open to the owner and to Simon.
11. Whether pooled B − A stays a primary interval. The simulation expects it to be task-dependent, and the owner would have made it secondary (section 6.4). Simon was away when this arose, and the freeze could not wait for him. The coordinating Claude session decided on 11 November to keep the nine primary intervals, because that is the set C3, D3 and the design agreed and this text says in advance what to expect of pooled B − A. Settled on 17 November by ruling 34: it stays primary. Either choice is sound if fixed before the freeze. The text already names a pooled step whose tasks point opposite ways task-dependent and prints each task's interval, so the pooled interval hides nothing, and keeping nine changes nothing that is built, where moving to eight would change the analysis, a check of the pass script and the sample-size reasoning. Simon's order of that day (science, then rigour, then the direct route, then deciding as he would, then asking him) leaves such a choice to the session. The ruling is open to him until the freeze, and this is no longer a gap that waits.
12. Whether the Mac is still the fallback platform. Round four's ruling 7 made it the fallback, flying the same delay, if the free check failed on the cluster for a reason that could not be put right. Ruling 22 replaced that ruling's first point and did not say whether the fallback stands (section 4.7). Open to the owner. If the Mac flies, two of its rules are open as well: whether it must also be at home, which waits on Simon (round two, ruling 5), and whether agents may still read and write files while flights are in the air, as draft 1 allowed, beside round two's rule that no agent session runs commands on it.

What became of draft 1's gaps:

1. The load limit: filled. `LOAD_LIMIT_1MIN` is 4.89, from the fourth timing preflight (`reproduction/timing-preflight-flights-20261112-214408.json`; round two, ruling 4). It applies on the Mac only. On the cluster no load limit applies (round four, ruling 7; section 4.7).
2. Whether the lateness rule holds on quiet flights: overtaken. Under the rule of 12 November the third preflight had 4 late flights of 150 and the fourth had none (round two, ruling 4). For this protocol's flights that rule is replaced by the fixed delay and its deadline (round four, ruling 2; section 4.6). Scored-2's counts under it are in section 8.5.
3. Filled on 11 November: the corrected planning simulation confirms N at 32 blocks (section 6.6).
4. Filled on 11 November: how often the task-dependent rule fires and misses, and the choice of rule (section 6.4).
5. Now gap 2.
6. Now gap 1.
7. Now gap 3.
8. Now gap 6.
9. The scripted pilot through the scheduler, the gate and the analysis: filled by the rehearsal of record of 16 November, which passed (section 8.10; ruling 28).
10. The quiet periods after the first: overtaken. The cluster has no hours and no quiet periods (round four, ruling 7). They would come back only if the Mac flew (gap 12).
11. Now gap 11.
12. The warm-up flight: ruled by the owner at 9:25 am on 12 November (the note, item 6 of that section), built into every process that flies, and kept with the delay (round four, ruling 2; section 4.6). Simon has still to confirm it, and it is in the list below.
13. The rulings of rounds two to five: written in, in sections 2, 2.1, 2.2, 4.1, 4.2, 4.4 to 4.9, 6.5 to 6.7, 7, 8, 9 and 10.

Open to Simon. Every ruling taken since 11 November by the owner or the coordinating session is taken under his delegation and is open to him until the freeze. The note names these for him, and they are gathered here.

- The decisions of 13 November, which the coordinating session told him it would take and to which he did not object: one network namespace for each driver and a new session keyring for each sandboxed call, in a build of the telohelm wheel made for Paper 3; how that wheel is built; fewer simulators at once not taken as the remedy, with `--at-once` kept at 4; the delay set from records on the changed sandbox; the model told of the delay; and nothing paid before a passed rehearsal and a repeated leak inspection (round five, decisions 1 to 6).
- The filter inside each sandboxed call that refuses the key system calls and the creation of sockets. It goes beyond what he was told on 13 November. If he prefers, the key part comes out, and its residue is accepted and reported (rulings 18 and 23; 'For Simon', item 1).
- Whether the sandbox change is offered to the public telohelm core. Nothing goes there now ('For Simon', item 3).
- At 0.3 s the scripted procedures fail their threat trials in reach and land, so adoption after a threat trial in those tasks is first tested by the development sample ('For Simon', item 5; ruling 26, point 2).
- A rehearsal that fails on one flipped scripted case and nothing else flies once more before the sample, so the passed rehearsal that his yes asked for may be the second one ('For Simon', item 6; ruling 26, point 4).
- The model key: why the gateway has blocked it, and having it unblocked. A change of key, account or route to the model is his as well (ruling 29, point 6).
- Pooled B − A as a primary interval, settled by ruling 34 and open to him like every ruling.
- Round four's rulings, all taken after the data: the fixed delay and what is late (rulings 1, 2 and 8), the free check and the pilot's pass rule (rulings 4 and 5), what the model is told and what the paper says (rulings 6 and 10), the platform (ruling 7, as ruling 22 changed it), the chain (ruling 9) and the network namespace (ruling 11). Round five's rulings 16 to 35, all taken after the data.
- From round two, each taken after the data: the spaced launches, the load check before each flight and `scored.guard` left as it is (ruling 2); a late learning call flown again in place at most twice, and kept after that (ruling 3); the load limit of 4.89 (ruling 4); and the Mac's conditions and hours (ruling 5), with the question it leaves to him of whether the Mac must also be at home. The load limit, the checks of load and the hours apply on the Mac only.
- From round three: arm C's repair requests name the failed layout by alias, which changes what arm C is sent compared with scored-2 (ruling 7); no format repair after an empty reply (ruling 8); a phase waits for the load instead of being refused (ruling 6); and the scheduler's own pause (ruling 5).
- From 12 November: the warm-up (item 6 at 9:25 am), the preflight's arrangement (item 2), deferring updates and keeping Spotlight out of the run folder on the Mac (item 4), and the lateness rule as it stood at 9:05 am (item 1), which for this protocol's flights has since been replaced (round four, ruling 2).
- The values marked [PICKED n] below.

Some numbers in this design were chosen. They are neither measured nor derived, and the text marks each as [PICKED n].

1. The margin of 0.20, with 0.10 reported beside it. Both sessions call it 'an explicit planning assumption' (DESIGN:140).
2. The rule that fixed N: each primary interval resolves in at least 80% of simulated runs (SIZE:61).
3. The two wider clearance bands, 9 to 11 m and 19 to 21 m. D3 chose 10 m and 20 m for a development pilot (`experiments/feedback_repair/DESIGN.md`:19). The close band, 3 to 4 m, repeats scored-2's geometry.
4. Twenty-four evaluation scenarios per task, 8 in each band, and 10 retention scenarios, cut from 30 'to keep the run within days' (DESIGN:42 and 85).
5. One extra call to repair a reply's format in each candidate slot (SCHEMA:30).
6. The spending stop of US$60, which C3 set above the forecast (`SPEND_LIMIT_USD_3` in `protocol/run_scored3.py`).
7. Four development blocks per task (DESIGN:77).
8. Equal weight for each band and for each task, and the grouping of the middle and wide bands into one primary interval (DESIGN:48 and 142, SCHEMA:40).
9. Two flights again before a late learning call is kept (`REFLIGHTS` in `ardupilot/ladder.py`). The note gives its reasons and says that the number itself is picked (round two, ruling 3, 'Why two').
10. On the Mac only: the hours of 6 pm to 7 am, and the scheduler's pause at 4:30 am, which stands in for a rule that a phase starts only if it fits before 7 am (round two, ruling 5; round three, ruling 5; listed as picked in round two, 'What Simon must confirm before the freeze').

Draft 1's eighth picked value, the limit of 1 s behind schedule for any one command, is withdrawn with the rule it belonged to (round four, ruling 2). The fixed delay of 0.3 s is set by the owner's rule in round four, ruling 8: the smallest whole number of telemetry periods that held the slowest decision on the platform's own records (section 4.6). The note does not list it among the picked values, and it is not marked here.

Everything this text describes is built. The key check, the restart guard and the chain's note of its memory were built and reviewed on 17 November (section 8.12; ruling 32), and the key check has not yet made a request to the gateway. The gate has read flown runs: the scripted pilots on the cluster, and the rehearsal of record, where it exited 0 (section 8.10). No source written by a model has been through it, because no model has yet answered a request in this study (section 8.4).

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

- The learning core: a build of the Telohelm wheel made for this protocol, `protocol/telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl`, version `0.1.0.dev0+paper3.2`, SHA-256 `36d36b86028643cdec9c3bbc5c90b6e6abe5dcdf31e5877367c38df995ab34b5`. A wheel is a built Python package file, and a SHA-256 is a fingerprint of a file's bytes. It is made from the wheel that the second protocol used, SHA-256 `bb2c6e779b7526c85fb6ced29bd0db01f0d30a88a16e2252f2f058cab3ce2f8c`, and one patch to one file, the sandbox that runs each procedure (`protocol/wheel3/sandbox.patch`). A script anyone can run again makes it (`protocol/wheel3/build_wheel3.py`) and records the hashes of the old wheel, the patch and the new wheel in `protocol/wheel3/WHEEL3.json`. The two wheels differ only in `telohelm/runtime/sandbox.py`, the version and the files that name it, and the sandbox on macOS is unchanged (round five, decisions 1 and 2; rulings 17, 19 and 23). Section 4.8 says what changed on Linux and why. The runner checks the installed package against the wheel, file by file and by version, and refuses to start if they differ (`core_check` in `ardupilot/scored.py`).
- The task packs, the autopilot, the judge on the simulator's true state and the velocity guard are those of the second protocol (`PROTOCOL-2.md`, section 2), at the freeze commit of this one. The task text gains one sentence about the fixed delay in this protocol (section 2.2).
- The learning model: Claude Sonnet 5.5 through Deakin's GEM gateway, requested as `bedrock/au.anthropic.claude-sonnet-5-5` (`GEM_MODEL` in `ardupilot/scored.py`), with effort `high` and up to 64,000 output tokens (`EFFORT` and `MAX_OUTPUT_TOKENS` in `ardupilot/claude_provider.py`). The provider sends no temperature and no sampling seed, so every call uses the service's default sampling, and that setting is part of the protocol (CONTRACT:23). The settings requested and the model label each reply reports are recorded for every call. The label is the gateway's own name for the model and cannot reveal a substituted model. The route to the model through the gateway is part of this protocol, so a change of it is Simon's decision (ruling 29, point 6).
- The driver. `ardupilot/ladder.py` runs one block's four arms. Every request is built by Telohelm's own Coordinator, unchanged. The driver chooses only which flights a learner has seen and when it is asked.
- Candidate slots. Each arm has 3 candidate slots, the second protocol's limit of 3 attempts (`PROTOCOL-2.md`:64). A slot is one model call, and one further call if the reply breaks the core's format rules [PICKED 5]. A reply that is still invalid uses up its slot (the module text of `ardupilot/ladder.py`; SCHEMA:30). An arm stops at its first adoption. An arm with no adoption after 3 slots has adopted nothing.
- The adoption test. A candidate is adopted when it passes Telohelm's trial rule on all 3 layouts of its arm's trial list (`component_trial` in `ardupilot/pack.py`). On each layout the candidate must have issued the command at every step and the flight must have met the goal, with no command refused by the guard and no help requested. This is the rule scored-2 adopted by. The earlier notes' wording, 'meeting the goal on all three' (CONTRACT:7), was shorthand for it, and the owner ruled that the full rule stands. In scored-2 the two never differed: none of its 213 first-round learning flights, 213 trial flights and 920 hazard flights has a refused command or a help request, and no trial flight met the goal while failing the trial rule. The gate recomputes the rule for every trial flight from its protected decision log and requires the driver's verdict to equal it. A candidate and a trial list are flown once in a block, so arms that reach the same candidate on the same list share that trial.
- Real time, with a fixed delay. Every scored flight runs in real time, as the second protocol's speed rule requires (`PROTOCOL-2.md`:66). Every command is sent to the vehicle 0.3 s of simulated time after the observation it was computed from, three telemetry periods, in every arm, task and phase (section 4.6). Up to four simulators fly at once, on instances 10 to 13. How many fly at once is a setting of the scheduler and the free check, `--at-once`, from 1 to 4 with 4 the default, named in every manifest and the same throughout a run (round four, ruling 11; ruling 16).
- Protocol version 3. The runner is started with `--protocol 3`. It reads `protocol/seeds-3.json` and requires `PROTOCOL-3.md` for scored phases. Every phase writes a manifest, a file that records the protocol version, the protocol file and its hash, the seeds file and its hash, the source fingerprint, the learning core's check, the simulator instance, the number flying at once, the process's nice value, the machine's load, the platform and the sandbox route (sections 4.7 and 4.8).
- Source fingerprint: one hash over the executed source. For this protocol it covers the Python files in `ardupilot/`, the Gazebo files, `protocol/run_scored.py`, the three seed files, `protocol/contract3.py`, `protocol/run_scored3.py`, the Paper 3 wheel and its build record `protocol/wheel3/WHEEL3.json` (`source_files` in `ardupilot/scored.py`). So no flight on one wheel can share a fingerprint with a flight on another (ruling 19). At the head that flew the rehearsal of record it is `0dc7e3aa225e8a736cc28dfbca8db8e3799c22bcf085629545678a42eb04a48d` (ruling 27, point 5). The rehearsal's checking tools (`protocol/pilot_pass3.py`, `protocol/delay_check3.py` and `protocol/set_aside3.py`), its two expectation files and the cluster's batch scripts lie outside it. The analysis and the gate record their own hashes in the analysis record.

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
| Reach goal | within 2 m for 5 s, inside 90 s | `TASKS` in `ardupilot/pack.py` |
| Reach3d goal | within 2.5 m for 3 s, inside 120 s | `TASKS` in `ardupilot/pack.py` |
| Land goal | down within 1.5 m of the point at 1 m/s or slower, inside 120 s | `TASKS` in `ardupilot/pack.py` |
| Zone | near edge 24 to 30 m from home, radius 6 to 9 m, switched on within 19 m | `PROTOCOL-2.md`:85 |
| Decision period | 1 s | `PROTOCOL-2.md`:66 |
| Telemetry step | 0.1 s | `TELEMETRY_STEP_MS` in `ardupilot/ladder.py` |
| Command delay | 0.3 s of simulated time after the observation, three telemetry steps | `COMMAND_DELAY_PERIODS` and `COMMAND_DELAY_S` in `ardupilot/ladder.py`; round four, rulings 1 and 8; ruling 26, point 1 |
| Deadline for a decision | an own lag under three telemetry steps, so ready less than 0.295 s after its observation | `timing` in `ardupilot/ladder.py`; round four, ruling 2 |
| Reading a lag on the step | from 0.005 s below it | `telemetry_steps` in `ardupilot/ladder.py`; as in `protocol/analysis.py`:349 |
| A decision counted as at least 0.1 s late | recorded lag of 0.095 s or more | `protocol/analysis.py`:349, the second protocol's frozen analysis |
| Attempts of a late learning call | at most 3: two set aside and flown again, the third kept | `REFLIGHTS` in `ardupilot/ladder.py`; round two, ruling 3 [PICKED 9] |
| Simulators at once | 4, on instances 10 to 13 | `--at-once`; round four, ruling 11; ruling 16 |
| Spacing of phase launches | at least 0.25 s | `START_SPACING_S` in `protocol/run_scored3.py`; round two, ruling 2 |
| Cores for each simulator, on the cluster | at least 3 | `MIN_CORES_PER_SIMULATOR` in `ardupilot/scored.py`; round four, ruling 7; ruling 22 |
| What a job asks for, on the cluster | 16 cores and 32 GB, for four simulators at once | ruling 31, point 3; `cluster/README.md`, section of 17 November |
| Load limit | on the Mac, a one-minute load of 4.89; on the cluster, none | `LOAD_LIMIT_1MIN` in `ardupilot/scored.py`; round two, ruling 4; round four, ruling 7 |
| Bootstrap | 10,000 resamples, seed 20261112 | `BOOT_N` and `BOOT_SEED` in `protocol/contract3.py`; 10,000 as in `PROTOCOL-2.md`:189 |
| Interval for direction | 95% | Lakens (2017); DESIGN:155 |
| Interval for equivalence | 90% | Lakens (2017), note 2: two one-sided tests at the 0.05 level |
| Margin | 0.20, with 0.10 beside it | DESIGN:140 [PICKED 1] |
| Task order seed | 20261113 | `ORDER_SEED` in `protocol/run_scored3.py` |
| Spending stop | US$60 | `SPEND_LIMIT_USD_3` in `protocol/run_scored3.py` [PICKED 6] |
| Spending stop of the development sample | US$4 | `--spend-limit 4`; round four, ruling 9; Simon's yes of 11 and 16 November |

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

Every request also carries the task's text. In this protocol that text ends with one sentence of fact about the fixed delay of section 4.6, the same in every task and arm, with no advice on what to do about it: 'Each command you return is sent to the drone 0.3 s after the observation it was computed from; until then the drone keeps flying on the previous command.' Its number is read from `COMMAND_DELAY_S`. The sentence is added to a copy of the task's pack, so the second protocol's requests do not change (`delay_sentence` and `protocol3_pack` in `ardupilot/ladder.py`). No request carries a time or a lag field (round four, ruling 6; round five, decision 5, and Build B, step B5). The model is told because the free check showed that the delay changes how procedures written without it fly near a zone. Left untold, the delay would be something that arms with richer feedback could find out and others could not, a difference between arms that the design did not plan (round four, ruling 6). The repeated leak inspection found every request at this delay to be the text it had read before with only the sentence's number changed, and asked that this section say that every request carries the sentence (ruling 25).

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

A block flies in calls: the first-round flights of each list, then one candidate's trial on one list at a time. If any flight of a call is late (section 4.6), the block moves that call's folder, before anything reads it, to `late/<the call's path>/attempt-<k>` inside the block folder, and flies the same source on the same cases again at once, in the same process, with no model call. It does this at most twice [PICKED 9]. If the third attempt is late as well, it is kept: the block reads it as it reads any flight, and its rows in `timing.json` are marked `kept_late`. The sandbox allows a procedure 2 s of processor time a decision, so a procedure written by a model could be slow enough to miss its deadline at every attempt, and this is how its slowness is charged to it (round two, ruling 3; round four, ruling 2). No block is set aside for a late flight, so nothing can choose blocks by how many repairs they needed. A late first-round or trial flight is set aside before any request uses it.

If a model call fails in transport, times out, is refused by the gateway or comes back with no served-model label, the block stops at once and is a fault (section 7). Every reply the service gives names the model that served it, so a call without that label was not answered by a model. It never uses up a candidate slot, and a finished block never holds one. A reply that is empty or breaks the format rules is the model's answer. It is recorded and uses its slot. A reply with text that breaks the format gets one format-repair call. An empty reply, or one refused or cut off with no text, gets none, since the repair would send the model service an empty assistant turn, which it is likely to refuse (13 November 2026; `notes/LEAK-INSPECTION-20261112.md`, finding 2).

The four arms run in one sitting, so no arm of a block learns at a different time from the others.

### 4.2 Evaluation on fresh zone flights

After learning, each distinct adopted source in a block flies that task's 24 evaluation scenarios, 8 in each band, with learning off and no model available (phase `threat3`). A source is the text of a procedure, identified by its SHA-256. The block's c0 flies them too, even if no arm adopted it, to give the success of a single unrevised attempt.

Arms of one block that adopted the same source share its flights: the source flies each scenario once and the outcome counts for each of those arms. This coupling is fixed here in advance. It does not rest on any claim that the simulator repeats a flight exactly. Two blocks never share flights, even if their sources are identical (CONTRACT:54).

Each evaluation phase flies its scheduled cases in the order set for its simulator instance: simulator k of the four starts k quarters of the way down the list and wraps round, so that no two simulators fly the same case at the same moment (`flight_order` in `protocol/contract3.py`; round two, ruling 2). The manifest records the order flown, and the gate checks it against the instance. Order cannot change an outcome. Each flight starts a new simulator, flying does not change the library, every decision runs in a fresh sandboxed process and each flight's episode memory is new (round two, ruling 2). A late evaluation flight holds the phase (section 7.2).

### 4.3 Retention on ordinary flights

Each distinct adopted source also flies 10 ordinary held-out scenarios with no zone, 5 calm and 5 in steady wind (phase `retain3`). This is a secondary check that learning with the zone did not cost ordinary flying. With 10 scenarios and no stated margin it cannot show that nothing was lost.

### 4.4 Records

A learning block's folder holds:

- its manifest, which also names the platform and the sandbox route (sections 4.7 and 4.8);
- `arms.json`, which records for each arm whether it adopted, the adopted candidate and its source hash, the candidates tried in order and each trial's outcome on each layout;
- one folder for each candidate, with its source, its request, the flights the request showed and a receipt for every model call;
- the first-round and trial flights, with their hash-chained logs;
- `late/`, the set-aside attempts of any call flown again for lateness (section 4.1), each with its flights and their logs;
- `timing.json`, with a row for every flight of every attempt, naming the call and the attempt and giving the flight's timing fields (section 4.6), whether it was kept late, and the block process's peak resident size (round two, ruling 3);
- `warmup/`, the process's warm-up flight and its timing (section 4.6). An evaluation phase's folder has one too. It is not a flight of the study.
- `usage.jsonl`, with one row for each model call;
- `sandbox-end.json`, the sandbox route's state when the phase ended: its count of calls and every replacement of its holder (section 4.8). An evaluation phase's folder has one too.

A hash-chained log is a record in which each line carries the hash of the line before, so an edit shows. The layout of these records is in CONTRACT:42–64 and SCHEMA:9–28, as amended by the rule in the takeover note for fields the schema does not name.

### 4.5 Order, pausing and spending

The run is one fixed schedule (`protocol/run_scored3.py`).

- Learning comes first: block 0 for all three tasks, then block 1, and so on to block 31. Within a block number the three tasks are queued in an order drawn from seed 20261113 (`task_order`).
- What is fixed is this queue: the list of phases and their order. Four workers, one for each simulator instance, take phases from it in that order, and no more than the number set by `--at-once` fly at a time (section 2). Phases are launched at least 0.25 s apart, and on the Mac phases that waited for the load are released the same way, one at a time (round two, ruling 2). Neighbours in the queue therefore fly at the same time, and the moment each starts depends on which worker is free and, on the Mac, on the wait for the load. A resumed run takes the remaining phases from the same queue. The scheduler writes the queue to `logs/schedule.json` at the first start and refuses a later session whose queue differs, or which asks for another number at once (round four, ruling 11).
- Evaluation follows in the same order of blocks: for each finished block, a `threat3` phase for every source it must fly and a `retain3` phase for every adopted source.
- The gate and the analysis run once, at the end (section 6).
- A phase that fails does not stop the scheduler. It holds that phase, lists it and goes on to start the phases after it, and evaluation is planned from the blocks that finished (`protocol/run_scored3.py`; ruling 29, point 3).

The order is fixed before launch so that all model use falls as early and as close together as the machine allows, and so that the flights left after learning need no model.

Pausing. The run needs many hours of flying (section 9.2), and it may be made over several sittings or batch jobs [GAP 7]. It remains one run under these rules.

- A pause may be asked for at any time. It takes effect at a phase boundary: phases in flight finish and no new phase starts. A learning block is one phase, so a block is never split, and its four arms always learn together.
- A pause may be asked for because a quiet period is ending on the Mac, because the machine is needed or because of a fault. It may never be asked for because of anything the study has measured: no outcome, no adoption count and no tally of any kind.
- A pause is asked for with a reason, and a later session must give a reason for resuming. The scheduler writes each start, each request for a pause, each pause taking effect and each resume to `logs/pauses.jsonl` with its time and reason. The paper reports how many there were and when.
- On the Mac the scheduler can ask for its own pause at a set time (`--pause-at`), so that no command is typed while flights are in the air. A typed pause is for an emergency only, and its use is reported (round three, ruling 5). The cluster has no hours, so no timed pause is given there (round four, ruling 7).
- The scheduler is stopped only by a pause. If its process dies, the phases it started may still be flying. Nothing starts again until each folder without a done mark has been set aside (section 7.3).
- A resume uses the frozen code, seeds, protocol file and model settings. The gate requires one source fingerprint, one protocol hash, one seeds hash, one wheel, one set of model settings, one platform with one partition and processor model, one sandbox route and one number flying at once across the whole run, and fails otherwise (section 6.7). If the model label in the replies changes between sittings, the paper reports it.
- Pausing adds no block and removes none. The run ends when every scheduled phase has its done mark.
- While the run is incomplete, nobody runs the gate or the analysis, and nobody tabulates outcomes. The people and agents who operate the run read the scheduler's log, exit codes and timing fields. A phase log is opened only for a phase that failed.

A partial run is never analysed as this study's result (section 7.4).

Spending. Model cost is counted at the provider's list price from the recorded token counts. The forecast is 4.4 to 7.8 calls per block at US$0.033 to US$0.054 a call, which for 96 blocks is about US$14 to US$40 (SIZE:91) [GAP 3]. The scheduler starts no further learning block once the blocks that have ended have cost US$60 (`SPEND_LIMIT_USD_3`) [PICKED 6]. The count covers finished blocks, blocks that stopped on a fault and blocks set aside, over every sitting. Blocks still in flight are not read, as in the second protocol (`PROTOCOL-2.md`:98), so the stop is a guard on known spending. At most 4 blocks are in flight, each with at most 16 calls. A block held by the stop waits for Simon, and raising the stop is his decision. Simon approved the scored spend on 11 November 2026, in the words quoted in the header. The approval is taken to cover spending up to this stop and no further. The development sample of section 8.4, about US$4 (DESIGN:77), was approved in the same answer, and Simon renewed that yes on 16 November (header). The sample's own limit is `--spend-limit 4`, given on every start and every resume, and the US$60 stop does not change (round four, ruling 9). The stop counts list prices from recorded token counts, so it cannot see spending that the records miss. After the sample's first calls the session therefore reads the spend record, and if replies come back while it stays at zero or empty, the job is cancelled (ruling 28, point 5). A refused key shows in the same records: on 16 November every first call was refused and no row had a cost (section 8.4). The chain is to check the key before it flies and again before the sample [GAP 8].

### 4.6 Timing: the fixed delay and its deadline

Decision lag is the simulated time from a step's scheduled observation to the moment its command is ready. A late decision changes what the vehicle does. On 9 November 2026, with the machine heavily loaded, decisions arrived more than 4 s late. A procedure that had met its goal on the same scenario in 3 earlier flights then entered the zone (`reproduction/dev-timing-c3-20261109.json`).

On 13 November the design was changed, at Simon's direction, so that the time a decision takes cannot change what the vehicle does unless it takes longer than a fixed time. Every command is applied at a fixed time after the observation it was computed from (the note, round four, opening and ruling 1). That time is three telemetry periods, 0.3 s of simulated time, in every flight of this protocol, in every arm, task and phase, warm-ups included.

How the hold works. Telemetry arrives ten times a second. The episode keeps the simulated time at which each observation was read: the start for the first decision, and for later ones the clock when the step before ended. Once the procedure and the guard have returned a command, the episode reads the telemetry waiting on the link. If the clock is still less than three telemetry steps after the observation, it reads on until the clock is at least the observation plus 0.295 s and then sends the command, so the command goes out just after the third telemetry stamp after the observation. The wait stops 0.005 s short of 0.3 s, as every threshold on a telemetry step is read, so a stamp 1 ms early cannot slip a whole step. If the clock is already three steps or more past the observation when the decision is ready, the deadline was missed: the command goes out at once and the flight is late (`Episode.step` in `ardupilot/pack.py`; round four, ruling 1). After each command the runner waits, as in the second protocol, until the first stamp at or after the next scheduled time, the start plus one second for each step, and takes the next observation there. The simulator does not wait while Telohelm decides. The delay is a setting of `battle.run`, off unless given, so the second protocol's code paths fly as before.

What each step records. Beside what it recorded before, each step of a flight flown with the delay records `observation_lag_s`, the observation's simulated time less its schedule; `command_lag_s`, the simulated time from the observation to the command going out, which is 0.298 to 0.301 s when the command went out on the deadline's stamp; and `decision_lag_s`, as before the time from the schedule to the moment the decision was ready, so that it compares with the older records. A decision's own lag is `decision_lag_s` less `observation_lag_s`. The outcome records `command_delay_s`, 0.3, and the flight's `run-config.json` records the number of periods (round four, ruling 1).

Why the deadline is counted from the observation. In every long flight on record, scored-2's included, the observation itself is read a step after its schedule in 49% to 60% of decisions from about decision 75 on, against 0% to 3% before it. The host waits until the simulator's clock is at least the scheduled time, and from then on the stamp that should meet it fails the comparison, so the host takes the next one, 0.1 s later. A likely cause, not shown, is floating-point rounding once the start time plus t passes 128 s (round four, 'What the records show', point 2). Counted from the schedule, every two-step lag in the Mac's records came from this pattern. Counted from the observation, none did (point 3). The scheduled wait itself was left as it is, because every record the free check compares against has this pattern, and the paper discloses it (round four, ruling 1).

What a late flight is. A flight of this protocol is late if any of these holds (`timing` in `ardupilot/ladder.py`; round four, ruling 2):

- it does not record `command_delay_s` of 0.3;
- it has no steps, or a step lacks a finite `decision_lag_s`, `observation_lag_s` or `command_lag_s`;
- any decision's own lag reads three telemetry steps or more, which is a missed deadline: the decision was ready 0.295 s or more after its observation;
- any decision that was ready in time had its command go out at other than three steps. This should never happen. It would mean that a telemetry stamp was skipped during the hold.

Each lag is read on the step from 0.005 s below it, as the second protocol's frozen analysis reads its threshold (`protocol/analysis.py`:349), so 0.098, 0.1 and 0.101 s are one step and 0.0 and 0.001 s are none (`telemetry_steps` in `ardupilot/ladder.py`). The driver, the evaluation phases, the gate and the set-aside tool all apply the one function, so they cannot disagree. Draft 1's rule, a median lag above half a step or any command 1 s or more behind its schedule, no longer applies to this protocol's flights. It is kept as `timing_before_delay` for reading the records flown before 13 November, and the timing preflight tool uses it (round four, ruling 2; section 8.5).

What follows from a late flight. In a learning block the call is flown again, at most twice, and a third late attempt is kept (section 4.1). An evaluation phase with a late flight is held, set aside and flown again from its start (section 7). A missed deadline is rare but not ruled out. On the platform of record a decision takes about 100 ms, so it has to wait about 195 ms more than usual to miss (ruling 24). Lateness is read from the timing fields alone. A late flight is an infrastructure fault and never a failed procedure, except a learning call kept late after two flights again, which is charged to its procedure.

How the delay was set. The rule is the owner's (round four, ruling 8, as ruling 20 restates it): the delay is the smallest whole number of telemetry periods that holds the slowest decision on the platform's own records, counted from its observation, on the build that will fly. A slow decision caused by the run's own work counts. Only a failure that the batch system records against the node or the job does not (ruling 20).

- On the Mac the own lag was at most one step in all 21,029 protocol 3 decisions on record, so two periods would have held there (round four, 'What the records show', point 1).
- On the cluster, a real-time flight on 13 November had one decision in 53 recorded at 0.201 s, whose own lag was most likely two steps. Three periods is the smallest number that holds it, and the delay was set at three (round four, ruling 8).
- Four periods were not adopted. Three of the five slowest decisions then in the cluster's records had an own lag of four steps, which four periods would not hold either, and their cause was the sandbox's network namespace (round four, rulings 8 and 11; section 4.8).
- After the sandbox change, two periods were tried again on the platform of record. Seven decisions of about 19,800 in the two scripted pilots had an own lag of two steps, so two periods do not hold (ruling 24).
- At three periods, in the free checks and pilots flown again on 16 November, no decision had an own lag of three steps. The largest own lags were 0.200 s and 0.201 s, one decision each, so each decision of two steps met its deadline with about 95 ms to spare. Three periods hold, and the delay is 0.3 s (ruling 26, point 1).

The rehearsal of record is read by the same rule (section 9.1). Its pilot had no decision with an own lag of two steps (ruling 28, point 2).

The first flight of a process. Early clock offsets come with the first flight that a process flies. In decisions two to eight they struck 24 of the 46 first flights of a scored-2 hazard phase and none of the 874 later flights, and 24 of the 30 first flights of a preflight worker and none of the 268 later ones (`reproduction/timing-diagnostic-split-20261112-091824.json`). Their cause is not known. Such a flight is a step late on three or four of its first eight decisions before any host lag. Under draft 1's rule that made whether a phase was ruled late depend in part on what its procedure did, because every hazard phase opens on a close-band flight, which ends after about eight decisions when the procedure enters the zone. The remedy, ruled by the owner on 12 November (9:25 am, item 6) and still to be confirmed by Simon, is one warm-up flight at the start of every process that flies: in every phase, in every worker of the free check and in the late-call check. It stays under the fixed delay and is flown with it (round four, ruling 2). It is a development case flown with the task's reference controller, kept in its own folder, reported, and read by no gate and no analysis. The case is the first calm retention case of the task's development seed book, which lasts well past the first eight decisions with the reference controller and is never a reserved seed. The flight is written to `warmup/` inside the phase's folder (or the worker's), with its timing in `warmup/warmup.json`. It is in no timing row, no count of flights or late flights and no outcome. The gate, the set-aside tool and the analysis do not read it. In the free checks of 16 November at three periods no warm-up decision had an own lag over one step (ruling 26, point 1).

What is recorded and reported. For every flight the records keep the median recorded lag, the largest recorded lag, the share of decisions at least 0.1 s late (from a recorded lag of 0.095 s), the median read on the telemetry step, the largest own lag, the number of observations read a step or more late, the number of missed deadlines, the number of commands sent off the deadline and, for zone flights, the true distance at which the procedure first saw the zone. The first four are read from `decision_lag_s` as before, so they compare with scored-2's, and they no longer decide anything (`timing` in `ardupilot/ladder.py`). Apart from the rule above, none of these is part of any gate. The paper reports them by arm (sections 4.9 and 6.5).

### 4.7 The platform

Every flight that is checked or counted flies on one platform: the free check, the late-call check, the pilot, the development sample and the scored run. That platform is the L40S nodes of the gpu partition of Deakin's cluster, l40s-f-01 to l40s-f-04, each with 64 cores of the Intel Xeon Gold 6448Y, flown as batch jobs that use the processors and ask for no GPU (round four, ruling 7; rulings 22 and 24). One platform flies all of them because a flight's path depends on the simulator build and on the host's timing, and the pilot and the sample are only worth what they show about the run that follows them (round four, ruling 7). The flights moved from the Mac to the cluster on 13 November (`cluster/README.md`). On 16 November the cpu partition was full, and Simon decided that Paper 3 flies on the gpu partition (ruling 22). The L40S nodes are the only node type there whose Python start is close to that of the cpu partition's fast nodes (ruling 22). They became the platform of record by a reading fixed before their flights: two prototype free checks with no late flight, no decision of two steps, every call 'ok' and no reference controller changed, F0 passed on every node and F1 on two of them (rulings 22 and 24; section 8.8).

One node type for a whole run root. The platform of record is one partition and one processor model, on nodes that the start probe finds in one speed group, named with each node in every manifest and record (ruling 22). The four L40S nodes start Python from memory in 14.3 to 15.1 ms, so they are one speed group, and l40s-f-03 is the slowest of them (`cluster/README.md`). Their kernel releases differ, 5.15.0-176 on l40s-f-01 and 5.15.0-143 on the others (ruling 24). So the kernel release is recorded in every record and reported, and it is not gated. Instead the sandbox route's tests and the package's containment tests (F0) must pass on every node of the type before any flight there counts (rulings 19 and 22). The simulator is one binary, built once on the cluster from ArduPilot at commit fb77356, whose SHA-256 begins adad8e2377659f74. It runs on the L40S nodes, and every run root names the same build (ruling 22; `cluster/README.md`). Nothing flown on one node type stands for another, and if the type of record ever changes, the measurements of this section are made again on the new type (ruling 22). A run flown on any other platform or node type is therefore not a run of this study as written. Whether the Mac is still the fallback is open [GAP 12].

How a job flies. Each job flies from an archive packed on the Mac from a reviewed commit by `protocol/package_for_cluster.py`. The archive's SHA-256 is printed on the Mac and given on the job's command line, and the job refuses to start unless the archive matches it. The value is not read from inside the archive, because a file inside it could change together with the record that vouches for it (round four, ruling 9). The job unpacks the archive into the node's memory (`/dev/shm`), with a copy of the Python interpreter and the packages it installs there. The run files stay in memory while it flies, and are copied to shared storage after each step, every 15 minutes and at the end (`cluster/chain.sbatch`; `cluster/README.md`). Memory is used because the network disks stalled decisions in the smoke runs of 13 November (round four, ruling 7). The job runs in bash, not zsh, so that nothing is lowered in priority, and the scheduler and the free check refuse to start at a nice value other than 0 (round four, ruling 7). The platform is named in `PAPER3_PLATFORM`, as `cluster` or `mac`, and is never guessed (`platform_name` in `ardupilot/scored.py`). Each simulator a job flies needs at least 3 cores, one each for the driver, the simulator and the sandboxed child, the most that can be busy at once, and a process refuses to start with fewer (`MIN_CORES_PER_SIMULATOR` and `start_refusal` in `ardupilot/scored.py`). One scheduler job flies on a node at a time, because the simulators' ports come from the instance numbers (round four, ruling 7; ruling 22).

A job asks for 16 cores and 32 GB and flies four simulators at once (ruling 31, point 3). The sources disagreed. Ruling 22 gives 12 cores for four simulators at three a simulator, and the note's list 'What flies after the build' says that F1 to F4 fly four at once on 12 cores. Every job flew on 16: the chain of record of 13 November (round four, ruling 7), the second round (ruling 25), and the rehearsal of record, which was submitted with 16 cores and 32 GB (`cluster/README.md`). Sixteen stands because the delay was set and both expectation files were made from records flown on 16 cores, and a job on 12 would be a condition none of those records measured. Twelve is the least the code accepts. `cluster/chain.sbatch` asks for 16 cores and 48 GB in its own lines, which the command line overrides, and its own lines now ask for 32 GB on an L40S node of the gpu partition (ruling 32).

Memory was to be set from the free check's measured peak, `sacct`'s MaxRSS, and recorded with the figure (round four, ruling 7). The readings are 1.8 GiB for a job that flew the two free checks, 2.7 GiB for a job that flew a scripted pilot, and 4.5 GiB for the rehearsal of record with the first 28 minutes of the sample's step (`cluster/README.md`, section of 17 November). The request is about seven times the largest. The figures are for the whole job, the files it keeps in memory included: a trial job that held one 300 MB file in memory and no large process had a MaxRSS of 308,504 K (`cluster/README.md`, section of 17 November, job 4800657). One limit applies to them, that no whole sample has flown. The chain prints, at the end of each step, the size of its folder in memory and the memory its cgroup has in use at that moment (ruling 32). The nodes' kernel keeps no peak for a cgroup, so the peak stays `sacct`'s to give (ruling 31, point 4).

What replaces the quiet Mac. Each job flies on cores the batch system gives it alone, and the deadline rule of section 4.6 is the test of whether the machine kept time. On the cluster there is no load limit, no wait for the load, no hours, no timed pause and no check of the power source, because a node's load counts other users' jobs on other cores and the limit of 4.89 is a Mac figure (round four, ruling 7). Phases are still launched 0.25 s apart. A job's time limit must hold its longest phase, taken from the pilot's phase times (round four, ruling 7).

A shared node. Other users' jobs run on the same node, on cores of their own. When the rehearsal of record started, 10 of its node's 64 processors were given to other users' jobs (`cluster/README.md`). The call time on a shared node moves by a few per cent with the node's other work. In the rehearsal a procedure call took about 5% more processor time at the start of the pilot than at its end, and than in the afternoon's pilot on the same node. Another user's job was on the node for part of that time, which is a coincidence in time and not a shown cause (ruling 28, point 3). A decision's two calls took 85 to 89 ms together that evening, against about 82 ms in the afternoon, and one telemetry step is 100 ms, so a few per cent decides whether a decision has one step of own lag. In the rehearsal 28% of decisions had one, against 3% and 6% in the afternoon's pilots (ruling 28, point 3; `cluster/README.md`). That came nowhere near the deadline: no decision of the rehearsal had an own lag of two steps, and the fixed delay absorbs any own lag under three. How much of that room a procedure written by a model uses is to be read from the development sample [GAP 5].

What each phase records about the platform. Every manifest records under `platform` the platform's name, the SHA-256 of the simulator binary and the ArduPilot commit, and on the cluster the node, the batch job and its partition, the processor model, the cores the process may use, the one-minute load at its start and the Python version (`platform_record` in `ardupilot/scored.py`). It also records the process's nice value and the number flying at once, and on the Mac the power source and the load with its limit. The gate requires on the cluster the node's name, at least 3 allowed cores and a nice value of 0, with no load limit applied, and on the Mac that the one-minute load was at or below the limit when the phase started (`check_platform` in `protocol/validate3.py`).

What was measured on the L40S nodes, and what was not. Measured: the Python start; the start of the sandbox's namespaces, made for each call and nested; the keyring fix; and that the simulator binary runs (ruling 22). Also F0 on every node (section 8.8), and the free checks, scripted pilots and rehearsal of record of sections 8.9 and 8.10, which give every decision's own lag and every sandboxed call's status and wall time. Three more that ruling 22 asked for were read on 17 November from records already made, with no new job (ruling 31, point 4; `cluster/README.md`, section of 17 November). The clock speed and governor: each of the 13 jobs flown on the four nodes on 16 November printed a median of 2100 MHz and no frequency governor at its start, which are the readings `cluster/node_probe.sh` takes. A sandboxed call's wall time on the new wheel: the bench, `cluster/bench_cluster.py`, was not run, because every flight on the wheel times each of its calls with the route, 12,024 of them in the rehearsal of record (section 8.10), and those are the calls the delay has to hold. A job's memory peak: `sacct`'s MaxRSS, given above with its limits. The timing preflights and the load limit are Mac figures with no use on the cluster, and they are not measured again (round four, ruling 7).

On the Mac. The Mac flew this protocol's development work until 13 November. Round four's ruling 7 kept it as the fallback, flying the same delay, if the free check failed on the cluster for a reason that could not be put right. Ruling 22 replaced that ruling's first point and did not say whether the fallback stands [GAP 12]. If the Mac flies, these rules apply to it, and none of them applies on the cluster:

- counted flights fly only while the Mac is on mains power with its lid open, nobody uses it, no agent session runs commands on it, and the flying processes run at a nice value of 0 (round two, ruling 5; round four, ruling 7, 'Priority'). Whether the Mac must also be at home waits on Simon's answer about where it was on 5 November (round two, ruling 5);
- phases start between 6 pm and 7 am [PICKED 10], and the scheduler pauses itself at 4:30 am (`--pause-at`). The pause stands in for a rule, not yet built, that a phase starts only when its longest duration fits before 7 am (round two, ruling 5; round three, ruling 5);
- the one-minute load limit is 4.89 (`LOAD_LIMIT_1MIN`). A phase checks the load when it starts and before every counted flight, and waits a minute at a time while the load is above the limit; after a wait the phases are released one at a time, 0.25 s apart (round two, rulings 2 and 4; round three, ruling 6). Every manifest records the three load averages and the limit;
- no other simulator and no other heavy job runs, and the phase guard refuses to start if a simulator outside instances 10 to 13 is running;
- no software update is installed and Spotlight does not index `paper3/runs` (12 November, 9 am, item 4).

Agents may read and write files while flights are in the air. A session that waits on a run waits on its process number with a single time limit and does not poll. The preflight is flown with the same sessions open as the scored run will have. Round two's ruling 5, which came after this rule, says that no agent session runs commands on the Mac while counted flights fly, and does not say whether reading and writing files is still allowed [GAP 12].

The limit was measured by this procedure (`protocol/timing_preflight3.py`). On a machine left to itself, the development evaluation and retention scenarios of all three tasks are flown in real time with each task's authored reference controller: 10 flights for each task one at a time on instance 10, then 40 for each task on instances 10 to 13 together. In the four-at-once stage each simulator flies the ten scenarios in its own order and the four start a quarter of a second apart, so that no two fly the same scenario at the same moment, as in the scored run, where the four simulators fly different phases. The first two preflights flew the same scenario on all four together. That made the four decisions of every second start their sandboxed processes at the same instant, which alone takes 42.5% of them past one step (`reproduction/timing-diagnostic-sandbox-20261112-082315.json`). If every flight of both stages is on time, the limit is the highest one-minute load average recorded at the start of any four-at-once flight. A load at which only one simulator was flying has not been checked with four, so the one-at-a-time flights do not set the limit. If any flight is late there is no limit: the machine is made quieter and the preflight is flown again, and every attempt is kept. In the loads on record by 11:30 pm on 12 November, 1.20 to 4.95 four at once and 0.84 to 4.98 one at a time, start load did not separate late flights from on-time ones, so the limit guards against starting at a load nobody has checked and does not predict lateness below it. The fourth preflight, flown at night on 12 November with nobody at the Mac and no agent running, had none of its 150 flights late and gives the limit, the highest one-minute start load of a four-at-once flight (`reproduction/timing-preflight-flights-20261112-214408.json`; round two, ruling 4). The limit guards only against sustained overload, such as the loads of 6.5 and more on 9 November. It cannot catch a burst of tens of seconds (round two, ruling 4). The third and fourth preflights were judged by draft 1's rule, which section 8.5 gives.

The reference controllers ignore the zone, so the preflight's hazard flights end when the drone enters it. That does not affect lag, which does not depend on what the command is. Whether those flights met their goals is evidence of nothing.

### 4.8 The sandbox route and the Paper 3 wheel

Every decision runs the procedure and the guard check as two sandboxed calls, each a new process, allowed 2 s of processor time and 5 s of wall time (round three, ruling 1). On Linux the second protocol's wheel made a network namespace, the kernel's separate copy of the network, for every call and destroyed it afterwards. On the cluster on 13 November that sometimes stalled a call. Three calls took 262 to 367 ms, each waiting 217 to 321 ms with nothing computing, and one made its decision four steps late, which no delay up to four periods holds (round four, ruling 11, and 'What the cluster showed this morning', point 3). A probe of the sandbox's start traced the stall to the network namespace: without it, the largest start among four callers took 5.3 ms. The likely mechanism, not shown, is that the kernel tears these namespaces down in batches under a lock the whole node shares (point 4). Fewer simulators at once did not remove the stall (ruling 16).

The route. The Paper 3 wheel gives each driver process one network namespace. A holder process, `unshare --user --map-root-user --net cat`, makes it once, and every call the driver makes joins it through `nsenter --target H --user --net --preserve-credentials` in front of the call's own command. Each call still makes its own user, process-ID, mount, IPC and host-name namespaces inside the holder's, and runs in the same empty read-only root with the same drop of privileges and the same limits as before. It still has no network. The shared namespace has only a loopback, which is down, and no call can bring it up (ruling 17). Each driver process starts its own holder before anything in it makes a call, and makes one trusted call through it, so a node where the route cannot run refuses before any flight. No two processes share a holder, and a holder ends when its process ends (ruling 17). The new wheel has no command that makes a network namespace for each call, so it cannot fall back to the old route, and which route a run is on is set by which wheel is installed (ruling 17). The route is named `netns-per-process+keyring-per-call/2`. On macOS the sandbox is `sandbox-exec`, unchanged.

The session keyring. On Linux every call used to inherit the driver's session keyring, a store of small secrets the kernel keeps for a login session. In a batch job on the cluster that keyring belongs to the batch system's own service and is shared by every job on the node. A probe found that without a fix a call could find, read and link a key in it and add one, and that a key one call left was found by the next (round four, ruling 15; ruling 18; job 4799098). In the new wheel each call joins a new, empty session keyring before its program starts, and the call's first lines check that it is empty. If the join fails, the call is not made and the flight stops (ruling 18). Each call keeps a user namespace of its own, because the kernel keeps a user keyring for each user namespace, which the session keyring does not cover (ruling 18).

The filter. The call's first lines then install a seccomp filter, a short program the kernel runs on every system call the process makes. It refuses the three key system calls (`add_key`, `request_key` and `keyctl`), so that a call cannot even see that a key of the same user exists by guessing its number. It refuses `socket`, `socketpair` and `io_uring_setup`, so that a call can create nothing in the network namespace it shares with later calls. And it kills a process that makes a system call as another machine type (rulings 18 and 23). The socket part was added after the review of the first build found that a call could pass 16 bits to the next through IPv6 flow labels, which outlive a call, are not sockets, and were in no table the route counted. That first build, `+paper3.1`, is never flown of record (ruling 23). On the rebuilt wheel the reviewer's probe was refused at `socket()` and passed nothing (ruling 23; jobs 4799229 and 4799230). No procedure needs a key or a socket, and the source check refuses any import other than `math` before the sandbox is reached (ruling 18). The filter goes beyond what Simon was told on 13 November, and it is on his list (header).

When a holder is spent, replaced or dead. A call that the parent has to stop, at the wall-clock limit, for a reply too large or breaking the channel's framing, or after an exception in the parent during the call, marks the holder spent, because something the stopped call did may outlive the kill. The next call ends a spent holder and starts a new one. After every call that ended normally the route also counts the lines of the holder's socket tables and of its IPv6 flow-label table, and any change from the counts read when the holder was ready marks it spent. Each replacement is recorded with the call's number, its status and its reason: 'stopped', or 'residue' with the table named (rulings 17 and 23; Build A, A2). Before and after each call the route checks that the holder is alive, still in the network namespace recorded when it started, and owned by this process. If it is not, the call raises `RouteError`, nothing catches it, and the flight stops. A dead holder that is not spent is never replaced, since that would hide a fault (ruling 17). Scripted and reference procedures are never stopped and leave nothing behind, so the free check and the pass script fail any run in which a holder was replaced (Build B, B2).

What each phase records, and what the gate asks. Every phase's manifest records the route under `sandbox`: its name, the holder's process number, its user and network namespaces, the driver's process number, the kernel release, the machine type, whether keyrings were joined, how the route started and the counts of the socket tables. At its end each phase writes `sandbox-end.json` with the number of calls and every replacement (Build A, A2; Build B, B1). The free check and the late-call check record the same. The gate refuses a phase whose manifest names no route, or a route other than its platform's: `netns-per-process+keyring-per-call/2` on the cluster and `sandbox-exec` on the Mac, written out in `EXPECTED_ROUTE` in `ardupilot/scored.py` so that an old wheel cannot meet them. It refuses a cluster phase that names no kernel release, that has no `sandbox-end.json`, or that replaced a holder for a reason other than 'stopped' or 'residue' or because the holder died. It refuses a run root whose phases name more than one route, and it lists the kernel releases without gating them (`check_route` in `protocol/validate3.py`). A phase that finds a replacement the gate would refuse stops at once, so the chain does not fly on, and the set-aside tool refuses to set such a phase aside (ruling 25). A run therefore carries four marks of its wheel: the wheel's hash in the core check, the installed version, the route and the source fingerprint (ruling 19).

Where the cost now falls. A phase that ends lets its holder go, which destroys a network namespace, and a phase that starts makes one. While the kernel does either, a call of another phase on the same node that is joining its own namespace waits, in the pilots at two periods for 50 to 125 ms. Sixteen of the 17 calls over 85 ms in those pilots came 1 to 3 s after one phase ended and the next started on the node (ruling 24). Three periods take a wait of this size: a decision of about 100 ms needs about 195 ms more to miss its deadline, and the largest call seen then was 165.4 ms. Two phase boundaries falling together could make a longer wait, and a flight late for that reason is handled like any late flight. A remedy at the source, starting and ending holders only while nothing flies on the node, would need the scheduler to fly its phases in waves, and it is not built (ruling 24).

Containment was inspected again. The repeated leak inspection found no path by which a held-out flight, another arm's flights or procedures, or anything in the route's records reaches a request or a token-count body (ruling 25; `notes/LEAK-INSPECTION-20261116.md`). It stands for any head whose source fingerprint is still 0dc7e3aa, because its harness is to be run again after any change to `ladder.py` or the wheel, and the fingerprint covers both (ruling 26, point 5). What the wheel's second review left open lies outside the network namespace and is the same in the old wheel: timing through the node's page cache or processor, which needs `open` and a clock, both refused by the source check (ruling 23).

### 4.9 What the paper says about timing, the platform and the sandbox

The paper must say these things (round four, ruling 6, with the additions named):

- that every command in every flight of this protocol was applied three telemetry periods, 0.3 s of simulated time, after the observation it was computed from, in every arm, task and phase;
- why: on the Mac that flew the earlier work, a decision's two sandboxed calls took 74 to 76 ms at best and 94 to 100 ms in a slow group, against about 80 ms that fitted inside one period, on a managed machine whose security software inspects every program start and could not be changed; on the cluster, before the sandbox change, they took 128 to 133 ms at the median in a real-time flight and 183 ms at the worst, so that a decision there could take two periods;
- that the cause of the Mac's slow group was not found;
- that scored-2 sent each command as soon as it was decided, so the two protocols' flights differ in this, and any comparison across them says so;
- that the deadline was counted from the observation's own telemetry stamp, that from decision 75 of a flight the observation itself was read a step after its schedule in about half the decisions, in both protocols, and the likely cause;
- that at the 5 m/s speed limit 0.3 s is up to 1.5 m more on the previous command, and that this mattered: the two scripted sources, procedures the model wrote in scored-2 for commands that took effect at once, passed 1.1 to 2.7 m from a zone's edge without the delay; with it, 1 of their 18 threat flights ended differently at 0.2 s, 6 and then 7 at 0.3 s and 10 at 0.4 s, most by entering the zone and a few by landing hard, while every reference flight ended as before;
- how many decisions missed the deadline, how they were handled, and by arm the number of calls flown again and of flights kept late (round two, ruling 3);
- that the sample-size planning was fitted to scored-2's adoption rates, from flights without the delay;
- which platform flew which flights, and that the sandbox around each procedure differs by platform, namespaces and a changed root directory on Linux and `sandbox-exec` on macOS, so a call's waiting time is not comparable across them;
- that from the sandbox change every Linux flight of this protocol ran each sandboxed call in a user, process-ID, mount, IPC and host-name namespace of its own, inside one network namespace with no network for each driver process, with a new empty session keyring, and with the key system calls and the creation of sockets refused; why; that a stopped call's namespace was never joined again; and that the first build of the wheel let a call pass a few bits to the next through IPv6 flow labels, which its review found before any procedure written by a model had run in it (ruling 17);
- where the network namespace's cost now falls, at the boundaries between phases (ruling 24);
- that arm C's repair requests name the failed layout by alias, which changes what arm C is sent compared with scored-2, wherever the paper sets the two studies side by side (round three, ruling 7).

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

A contrast between two arms is the difference of their means over the cells in question. Its interval comes from a crossed bootstrap with 10,000 resamples and seed 20261112. Each resample draws blocks with replacement, keeping a block's four arms together. It also draws scenarios with replacement within each band, and the same scenario draw applies to every block and arm. The bands keep equal weight [PICKED 8]. Intervals are percentile intervals. Each is a pointwise interval for its own contrast, and the nine primary intervals together make no claim of joint coverage.

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

Whether pooled B − A should remain a primary interval was gap 11, and ruling 34 settles it: it remains one, for the reason given in the list of gaps. The owner would have made it secondary and answered RQ1 from the per-task estimates, leaving eight primary intervals: a pooled mean of effects that the design itself expects to have opposite signs answers no question a designer has. The coordinating session decided to keep the nine as agreed, and this text is written for the nine. The decision is open to Simon until the freeze.

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
- by arm, the timing figures of section 4.6: the median recorded lag, the largest recorded lag, the share of decisions at least 0.1 s late, the largest own lag, the observations read a step or more late, the missed deadlines and the first-sight distance; and the number of calls flown again and of flights kept late, with the procedure's and the guard's call times (round two, ruling 3; round four, ruling 6).

Precedence: the primary intervals lead the paper's answer. Secondary estimates are reported beside them and do not override them. If they point the other way, the paper says so.

### 6.6 Sample size

N is 32 blocks per task and is fixed before the freeze. It is not changed after any scored outcome exists, and neither are the margin or the set of primary intervals (SCHEMA:44). The run is never extended.

N came from a simulation that draws procedures from scored-2's outcomes and sweeps what is unknown (SIZE:17–25). The unknowns are how much easier distant targets are and how good a repair is, including a repair that does worse than a fresh sample. The rule was the smallest N at which each primary interval is resolved, meaning not unresolved, in at least 80% of simulated runs in every combination [PICKED 2] (SIZE:61). At 32 blocks the weakest intervals stood at 0.80 and 0.81 (SIZE:89).

Two faults were found in that simulation. It was fitted to 15 first-candidate adoptions in 24 and 7 rescues in 9, where scored-2's records give 16 in 24 and 6 in 8 (`manuscript/PAPER.md`:162; `reproduction/ladder-planning-audit-d3-20261109.json`). It also named results from one 95% interval, where section 6.4 uses two. The second fault can only have made it resolve less often, because the 90% interval lies inside the 95% one.

The simulation was corrected and run again on 11 November 2026, with 2,000 simulated runs for each combination (`notes/SAMPLE-SIZE-RERUN-20261111.md`, Table 1). The counts are read from the 24 scored-2 summaries, and every name comes from `analysis3.classify`, the function the analysis itself uses. At 32 blocks the weakest interval resolves in 83.0% of runs (D − A on reach at 10 to 20 m) and the next in 83.2% (D − A on land at 10 to 20 m). Every other interval is at 96.8% or more. The standard error of a share near 83% is about 0.8 points. At 24 blocks the weakest is 72.0%, and at 40 blocks 87.2%. N therefore stays at 32.

A run in which a pooled step is named task-dependent counts as resolved, because that name is a definite result (section 6.4). Counted otherwise, pooled B − A would resolve in 23.3% of runs at 32 blocks and 15.2% at 40, so no N would change it, while C − B and D − C would stay at 93% or more.

The rerun has three limits of its own. It uses 2,000 bootstrap resamples where the analysis uses 10,000. The scored-2 outcome files behind its pools are not hashed. The success rates at 10 and 20 m are assumed, and the two weakest intervals are the ones that depend on them.

The 80% is the chance for one interval taken alone, under the simulation's assumptions. It is not the chance that all nine resolve (DESIGN:153). A run that ends with unresolved intervals is reported as it is.

The simulation was fitted to scored-2's adoption rates, which come from flights without the delay (round four, ruling 6). The delay changes how procedures fly near a zone. At 0.3 s the scripted sources, which the model wrote in scored-2, no longer pass a threat trial in reach and land (section 8.9). Whether procedures written under the delay adopt at rates inside the simulation's ranges is first read from the development sample, by the checks of section 8.4 [GAP 1] [GAP 4].

### 6.7 The gate

Before any outcome is computed, the gate checks the whole run and fails closed. It derives the schedule from the seeds file: 96 learning blocks, then the evaluation and retention phases implied by which sources were adopted. It then requires that:

- every scheduled phase is present with its done mark, and there is no extra phase;
- every phase holds exactly its scheduled scenarios, each once, with the scheduled parameters;
- every hash-chained log checks against its heads file, and every result agrees with its flight's own record and log;
- every success agrees with the simulator's true positions and speeds;
- every flight it counts was flown in real time with the fixed delay, its run configuration naming three periods and its outcome 0.3 s, and is on time by `ladder.timing` (section 4.6); the one exception is a learning flight kept late, which is accepted only beside exactly two set-aside attempts of the same call, and every set-aside attempt is checked in turn;
- each evaluation phase flew its cases in the order its instance fixes (`flight_order` in `protocol/contract3.py`);
- each phase's platform is recorded as section 4.7 says: on the Mac it started at or below the load limit, and on the cluster it names its node, had at least 3 cores, recorded a nice value of 0 and applied no load limit; on both a recorded nice value other than 0 is refused, and the number flying at once is from 1 to 4 and equals the scheduler's limit (`check_platform` in `protocol/validate3.py`);
- each phase names its platform's sandbox route, and a cluster phase names its kernel release and has a `sandbox-end.json` in which no holder was replaced for a reason other than 'stopped' or 'residue', and none had died (`check_route` in `protocol/validate3.py`; section 4.8);
- within a block, the candidates, requests, trials and adoption agree with `arms.json`; a fresh request is identical to c0's; a first request shows only its own first-round flights; a repair shows only trial flights of its own arm, with at least one from the last trial flown;
- each trial passed exactly when all 3 of its layouts passed the trial rule, as the gate recomputes it from each flight's protected decision log, and no layout is recorded as passed against its flight's record;
- every model call of a scored run is a real call with a served-model label, and all calls requested the same settings;
- no request contains a seed number of either seed book: evaluation, retention and, since 13 November 2026, learning;
- a format repair follows only a reply with text, and a slot that failed the format with one call had an empty reply;
- all phases share one protocol hash, one seeds hash, one wheel, one source fingerprint and one set of model settings, one platform with one partition and processor model, one sandbox route and one number flying at once, and no scored phase ran with uncommitted source. The kernel releases the phases name are listed and not gated (section 4.7).

A learning block that finished with an arm adopting nothing is a completed non-adoption and supplies planned zeros. A block that is missing or stopped is a fault, never a zero. If any check fails, the analysis computes no outcome.

Operating rule: nobody reads flight outcomes before the gate passes on the complete run. Phase logs print outcomes as flights land, so for the logs this is a rule and not something the code enforces. It binds every agent that operates or reviews the study, and Simon.

No expectation is stated for the direction or size of any step. The simulation's ranges are planning inputs and not predictions to be confirmed.

## 7. Faults, late flights and reruns

### 7.1 Faults

A fault is a failure of the machine, of the sandbox's route or of the model service, and never of a procedure. The faults are: the simulator failed to start, the connection to it dropped, the simulator's true state was missing, the runner crashed, the sandbox's route failed and raised `RouteError` (section 4.8), a model call failed in transport, timed out, was refused by the gateway or came back with no served-model label, or an evaluation flight was late. A phase with a fault does not get its done mark. The scheduler holds it and lists it, goes on to the phases after it, and never reruns it by itself (section 4.5).

A refused key is a fault of this kind. On 16 November the gateway refused the model key at the first call of every learning block of the development sample, each block stopped as a fault, and nothing was spent (ruling 29; section 8.10). Since such a fault strikes every block alike, the chain checks the key before it flies and again before its paid step (section 9.1; ruling 32) [GAP 8].

### 7.2 Late flights

Lateness is decided from the timing fields of a flight, by the rule of section 4.6, and from nothing else. In a learning block the driver checks each call's flights as they land. A call with a late flight is set aside unread and flown again in place, at most twice, with no model call, and a third late attempt is kept and charged to its procedure (section 4.1). The block does not stop. In an evaluation phase the phase ends with a failure if any of its flights was late, and the scheduler holds it.

### 7.3 Setting a phase aside and flying it again

The unit is the whole phase. One flight is never replaced.

- A held phase is set aside with the set-aside tool (`protocol/set_aside3.py`), with one of two reasons. `late` means a flight in the phase was late. `crashed` means any other fault of section 7.1 that left the folder without a done mark. In the chain of record (section 9.1) the chain itself sets aside, once, each evaluation phase the scheduler holds, with the reason `late`, and then runs the scheduler again. A held learning block, a refusal by the tool or a second hold stops the chain (round four, ruling 9; `cluster/chain.sbatch`). Elsewhere the owner of the run decides.
- For `late` the tool opens the phase's `timing.json`, copies only the named timing fields of each flight into the receipt (`TIMING_FIELDS`), and refuses unless a flight is recorded late. Where the phase has a `sandbox-end.json`, which is the route's record and holds no outcome, the tool reads it too, and then reads the platform from the phase's manifest to judge that record. A phase with no route record is set aside without its manifest being opened. It refuses a phase whose route record the gate would refuse, so the chain stops there and does not fly the phase again only for the gate to refuse it again (ruling 25; ruling 30, point 3). For `crashed` it reads nothing in the phase. It never opens an outcome, a flight record, `arms.json` or the phase log.
- The tool refuses a phase that has a done mark, so a finished phase cannot be removed once its result exists. It refuses while a scheduler is running on the run, and while any process still names the phase's folder.
- The tool writes a receipt: the phase, the attempt number, the reason, the time, the timing fields it read, the SHA-256 of `timing.json`, and every file it opened in the phase, in order (ruling 32). It moves the phase's folder and its log to a folder beside the run root, `<run>.set-aside/<phase>-attempt<n>`, where they are kept. This is the second protocol's treatment of a crashed phase (`PROTOCOL-2.md`:219–221).
- The phase is then run again under its scheduled name with the same seeds. A learning block makes new model calls.
- The gate sees one folder for each scheduled phase. The paper lists every phase set aside, with its receipt, and the model calls of a block set aside are counted in the spend. Each is also entered in the deviations file.
- A second hold of the same phase goes to the owner before anything more is done, because the procedure itself may be slow (round four, ruling 2), and the chain of record stops there.

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

On 11 November the driver and the gate, which had been written apart, were brought together. A block that the driver built offline from recorded flights passed the gate's learning check, and all 123 offline tests passed. Since then the gate has read flown runs. On the Mac, in the night of 12 to 13 November, it printed `ok` for a scripted pilot that failed its pass rule, because the gate checks that records are well formed and not that a pilot passed, and that is why the pass script of section 9.1 exists (round four, ruling 5). On the cluster it read the scripted pilots of sections 8.7 and 8.9, and the rehearsal of record of section 8.10, where it exited 0 (ruling 28). No adopted source written by a model has been through it, because the development sample has not flown (section 8.4).

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
- No phase was held, or each held phase was set aside once and flown again, with its receipt ('The development sample', check 7, in the note; round two, ruling 5). The sample also reports, by arm, the calls flown again, the flights kept late and the timing figures of section 4.6, and the position test, which is reported only (round two, ruling 5; round four, ruling 2 and 'The position test').

Owed from the sample before the freeze, and not a pass mark: how much of the room between one step of own lag and the three-step deadline its procedures use, read from the sample's own lags, and the count of its sandboxed calls by `cluster/read_calls.py` (ruling 28, points 3 and 6) [GAP 5].

The sample has not flown. It started on 16 November as step 7 of the chain that flew the rehearsal of record. Each of its first four learning blocks flew its warm-up and its first-round flights, which make no model call, and its first call was then refused by the gateway with HTTP 401: "Authentication Error, Key is blocked." Each block stopped as a fault. Eight requests were sent, no model answered them and no row of the usage records has a cost, so nothing was spent. The job was cancelled and its approval file removed (ruling 29, points 1 and 3; section 8.10). The sample cannot fly until the key works again, which is Simon's to settle. It then needs a whole chain, about three hours of free flights before the paid step, because the chain has no way to fly the sample alone (ruling 29, points 4 and 6).

[GAP 1: what the sample showed against each check, including how often arm B adopted on reach. GAP 2: the measured times. GAP 4: whether any arm adopts at 0.3 s in reach and land.]

### 8.5 Timing preflights and diagnostics, 11 and 12 November, no model

- The first preflight (`reproduction/timing-preflight-flights-20261111-212412.json`) stopped after 108 flights when macOS installed an update and restarted the machine. Twelve four-at-once flights of reach were late under the first rule, all between 9:39 and 9:46 pm. It sets no limit.
- The second preflight (`reproduction/timing-preflight-flights-20261112-065219.json`) finished its 150 flights. Four four-at-once flights were late under the first rule, two of them ties at a median of 0.0505 s. It sets no limit.
- Under the revised rule of 12 November, given below, the first would have ten late flights and the second two. Neither is used for the limit.
- Both preflights flew the same scenario on all four simulators together. A diagnostic with no simulator timed a decision's two sandboxed calls: a median of 0.081 s for one process and for four spread a quarter of a second apart, with none reaching 0.1 s, and 0.099 s for four at the same instant, with 42.5% reaching it (`reproduction/timing-diagnostic-sandbox-20261112-082315.json`).
- A diagnostic on 12 November flew the four-at-once stage of reach with each simulator in its own order and the four started a quarter of a second apart (`reproduction/timing-diagnostic-rotated-20261112-085816.json`). Host lag struck four of the 432 decisions after the first, against 11.7% and 38.8% when the same stage was flown together. Two flights were late, both the first flight of their simulator (section 4.6, the first flight of a process).
- The third preflight (`reproduction/timing-preflight-flights-20261112-102327.json`) flew complete on 12 November from 10:23 to 11:37 am. Under the revised rule it had four late counted flights, all in the four-at-once stage of reach and late on the median alone, with a largest lag of 0.101 s. All of that stage's host lag fell in three windows of 20 to 40 s, the first two with desktop use and git commands on the Mac. It sets no limit (round two, ruling 4).
- The fourth preflight (`reproduction/timing-preflight-flights-20261112-214408.json`) was flown at night on 12 November, from 9:44 to 10:58 pm, with nobody at the Mac and no agent running. None of its 150 flights was late. It gives the load limit of 4.89, the highest one-minute start load of a four-at-once flight (round two, ruling 4).
- Start load did not separate late flights from on-time ones in the first three preflights or the rotated diagnostic. One at a time, none of 88 flights was late at loads of 0.84 to 4.98 (round two, ruling 4).

The revised rule of 12 November is draft 1's rule, kept as `timing_before_delay` in `ardupilot/ladder.py` (section 4.6). A flight was late under it if a lag was missing or not finite, if the median of its lags, each read on the telemetry step, was above half a step, 0.05 s, which is 5% of the decision period (`PROTOCOL-2.md`:66), or if any command was issued 1 s or more after its schedule. It counted every lag from the step's schedule, and a recorded lag of one step then had two sources. Every decision runs the procedure and the guard check as two new sandboxed processes, and these took a median of 0.072 s in scored-2's hazard flights, so the turnaround sits just below the 0.1 s step. Host lag arises when the turnaround crosses the next stamp. A clock offset arises when the stamp nearest the scheduled time falls a millisecond or two before it: the runner then waits for the next stamp, the procedure is given an observation already about 0.1 s past its schedule, and its command, after the same two calls, leaves about 0.18 s after the schedule. Under the fixed delay a clock offset is the observation's own lag, and it does not count against the decision (section 4.6).

The owner's first rule took the median of the recorded lag. It was revised on 12 November to read each lag on the step, because the three recorded values of one step are one delay, and a flight with half its decisions one step late had a median between 0.049 and 0.0505 s, so its verdict turned on a millisecond of jitter (the note, 12 November 2026, 9 am, 9:05 am and 9:25 am). In the first two preflights, the flights the first rule called late flew within 0.26 m of on-time flights of the same seed at every step, and ended as they did, while on-time flights of one seed differed by up to 2.28 m.

Scored-2 under the rule of 12 November. None of its 920 hazard flights and 213 first-round learning flights is late, as under the first rule. Its 213 trial flights have 7 late under both rules, and its 3,125 held-out, disturbance and repeat flights have 124 late under this rule and 133 under the first. Every one of those 124 was flown between 9 am and 6 pm on 5 November 2026, and none of the 3,347 evaluation flights that a procedure flew between 6 pm and 9 am was late. The largest lag is 0.201 s (`reproduction/timing-preflight-20261111.json`; the owner's read-only counts in the note, 12 November 2026, 9 pm). Read for own lag, 15 of scored-2's 150,379 decisions had an own lag of two steps or more, 11 at two and 4 at three or four, in 11 of 4,258 flights (round four, 'What the records show', point 4). The second protocol had no rule for single flights, so none of its figures changes.

### 8.6 What the Mac's records showed, read on 13 November, no model

- Read on the telemetry step, a decision's own lag was at most one step in every one of the 21,029 protocol 3 decisions on record on the Mac: the five timing runs of 11 and 12 November, the scripted pilot's learning and evaluation flights, a lone reach block and every warm-up. The late-call check, made late on purpose, is left out (round four, 'What the records show', point 1).
- Counted from the schedule, 179 learning decisions of the scripted pilot in 18 flights, 4 of its evaluation decisions in 3 flights and 64 decisions of the lone block in 10 flights were two steps late, all at decision 75 or later in flights that ran to their time limit. Counted from the observation, none was (point 3).
- No protocol 3 decision tried more than one procedure (point 5; round four, ruling 3).
- Repeated flights ended the same way. The reference controllers flew 30 development cases 628 times across the five timing runs, and every case ended for one reason in all its flights. Of the 54 combinations of task, candidate, list and case that the scripted candidates flew, 45 were flown more than once, and each of those ended for one reason every time (point 6).
- The scripted pilot of that night ran at a nice value of 5, because its launcher was a zsh script and zsh lowers background jobs. Round two's ruling 5 asked for normal priority, so the night broke it. The scheduler and the free check now refuse to start at a nice value other than 0 (round four, ruling 7, 'Priority').

### 8.7 The cluster on 13 November, no model

These flights were free and not of record, on nodes of the cpu partition (AMD EPYC 7742 for every free check and pilot below), on earlier code and on the second protocol's wheel. They are why the platform, the delay and the sandbox are as sections 4.6 to 4.8 say.

- A real-time flight of the demo on cpu-f-08: one decision of 53 had a recorded lag of 0.201 s, most likely an own lag of two steps, and a decision's two calls took 128 to 133 ms at the median and 183 ms at the worst. This set the delay at three periods (round four, ruling 8).
- The first chain of record (job 4726527, cpu-f-04, commit 6eaa9fb9). The free check without the delay passed. With the delay no flight was late, all 30 reference flights ended as on record, and six of the scripted sources' 18 threat flights did not: in land, two hard landings and two entries into the zone, and in reach, two entries. Without the delay these six had passed 1.1 to 2.7 m from the zone's edge. The chain stopped with status 32 (round four, ruling 10, and 'What the cluster showed this morning', points 1 and 2).
- The same free check at other delays, all four at once. At 0.3 s again (job 4726567) seven scripted flights changed, the six and reach3d's first source on threat-close-4010001, which therefore ended two ways at 0.3 s. At 0.2 s (job 4726569) one scripted flight changed. At 0.4 s (job 4726536) ten changed. No reference controller changed at any delay (points 5 and 7).
- Stalls. Without the delay, three calls took 262 to 367 ms, each waiting 217 to 321 ms with nothing computing, and one counted decision was four steps late. A probe of the sandbox's start traced the stall to making a network namespace for each call (round four, ruling 11, and 'What the cluster showed this morning', points 3, 4 and 8).
- The scripted pilot at three periods, four at once (job 4726546): 7 late flights in 132, from 7 decisions of three steps in about 8,300. Only arm A adopted in reach and land, and arms A and B in reach3d, all of f1 (point 6). The same pilot at one at once (jobs 4726588 and 4726589) had 12 and 5 decisions of three steps or more, so flying fewer simulators at once did not remove the stall (ruling 16; `cluster/README.md`). The pilot at four at once also found a fault in the set-aside tool's path, fixed at 22defda7 (point 6).
- A prototype of one network namespace for each driver (jobs 4726673 at three periods and 4726674 at two): no late flight, no decision of two steps or more, and no call over 48.5 ms in about 5,000 (round four, ruling 14; round five, 'What the records of 13 November show'). The same work found that every sandboxed call inherited the driver's session keyring (round four, ruling 15).

### 8.8 The new wheel and the platform, 16 November, no model

- The session keyring. In a batch job a call could find, read and link a key in the session keyring and add one, and a key one call left was found by the next. With the join of a new session keyring in each call, neither the next call nor the parent found a key a call had left. The join cost 0.1 ms a call (ruling 18; job 4799098).
- The gpu partition's node types, probed with four callers in a flight's pattern, 1,600 starts each. With a network namespace made for each call, the V100 types had starts of up to 545 ms and 9,732 ms. In the nested form of the new route the largest start on any type was 21.8 ms. The L40S nodes started Python from memory in 14.3 to 15.1 ms (ruling 22; `cluster/README.md`, jobs 4799108 to 4799111, 4799133 and 4799134).
- Prototype free checks at two periods on l40s-f-04 and l40s-f-01 (jobs 4799123 and 4799124): no flight late, own lags of at most one step, every call 'ok', the largest 55.1 ms and 47.5 ms, and no reference controller changed (ruling 22).
- The first build of the wheel, `+paper3.1`, let a call pass 16 bits to the next through IPv6 flow labels (job 4799199). It is never flown of record. On the rebuilt `+paper3.2` the reviewer's probe was refused at `socket()` and passed nothing (jobs 4799229 and 4799230; ruling 23).
- F0 on `+paper3.2`: on all four L40S nodes the package's containment tests reported 31 passed against each wheel, and the unit suites ran 382 tests, OK, with 6 skipped, none of them a test of the route (jobs 4799220 to 4799227; `cluster/README.md`).
- F1, the free check without the delay on the rebuilt wheel, passed on l40s-f-03 and l40s-f-01 (jobs 4799236 and 4799237): every flight ended as on record, none was late and every call was 'ok' (ruling 24).

With these, the L40S nodes met the reading fixed for them, and they became the platform of record (rulings 22 and 24).

### 8.9 The delay at two and three periods, and the expectation files, 16 November, no model

All four at once, in memory, on the platform of record, with scripted replies.

- Two periods (archive of eb38bbfa, jobs 4799236 to 4799239). The free checks with the delay had no flight late and own lags of at most one step. In the two scripted pilots 7 decisions of about 19,800 had an own lag of two steps, 5 on l40s-f-02 and 2 on l40s-f-04, so two periods did not hold. Each was one sandboxed call that took 125 to 165 ms of wall time with its usual 38 to 40 ms of processor time. Sixteen of the 17 calls over 85 ms in the two pilots came 1 to 3 s after one phase ended and the next started on the node (ruling 24; section 4.8). At two periods reach and reach3d adopted in all four arms, and land in arms A and C, and D on l40s-f-04 (ruling 26, point 2; `cluster/README.md`).
- Three periods (archive of 5b47e871, source fingerprint 0dc7e3aa, jobs 4799688 to 4799691). In the free checks with the delay, own lags were 0 steps in 976 decisions and 1 in 53 on l40s-f-03, and 966 and 52 on l40s-f-01, with no flight late. In the pilots, 7,730 decisions at 0 steps, 268 at 1 and 1 at 2 on l40s-f-02, and 7,498, 463 and 1 on l40s-f-04, warm-ups included. The largest own lags were 0.200 s and 0.201 s, one decision each. Every call was 'ok', no holder was replaced, and no phase was held. Three periods hold (ruling 26, point 1).
- End reasons at three periods. Six scripted cases ended otherwise than without the delay on both nodes, and reach3d's first source on threat-close-4010001 entered the zone on one node and held on the other. No reference controller's ending changed (`cluster/README.md`, section of 6:45 pm).
- Adoption at three periods, on both pilots: in reach and in land only arm A adopted, f1; in reach3d arms A and B adopted f1 and arm D c1, and arm C adopted rC1 on l40s-f-04 only. So the scripted candidates, written before there was a delay, now fail their threat trials in reach and land, and the rehearsal can show adoption after a threat trial only in reach3d. In reach and land that is first tested by the development sample, whose procedures are written under the delay (ruling 26, point 2; round four, ruling 10).
- The two expectation files of section 9.1 were made from these records and reviewed: the delay file from jobs 4799688 and 4799689, the adoption file from jobs 4799690 and 4799691 (rulings 25 to 27).

### 8.10 The rehearsal of record, 16 November

The rehearsal of record is the chain of section 9.1 flown on the archive, node type, number at once and judges the sample will use, with scripted replies and so with no model call until its paid step (ruling 26, point 2). It flew as job 4800153 on l40s-f-04, from the archive `p3-b39a78cb.tgz` of commit b39a78cb, SHA-256 `902b1fc78363481806d182de27ebf0f62e66715922bf914ed915f9259539a2a3`, source fingerprint 0dc7e3aa (ruling 27, point 5). It started at 8:33 pm, submitted with 16 cores and 32 GB and with `PAID` given as yes. When it started, the node's load was 2.0, and 10 of its 64 processors were given to other users' jobs (`cluster/README.md`). It passed (ruling 28, point 1).

| Step | Ended | Result |
|---|---|---|
| 1, the free check without the delay | 20:55:22, exit 0 | 57 flights; own lag in telemetry steps {0: 980, 1: 31}; passed |
| 2, the free check with the delay | 21:17:59, exit 0 | 57 flights; {0: 740, 1: 281}; passed against the delay file, with its one unjudged case (reach3d/first/threat-close-4010001) |
| 3, the scripted pilot | 22:45:16, exit 0 | 14 phases, 130 counted flights, 14 warm-up flights, nothing set aside |
| 4, the pass script | 22:45:24, exit 0 | all 11 checks |
| 5, records for reading | 22:45:33 | gate exit 0, analysis exit 0, position test exit 0 |
| 6, the late-call check | 23:22:27, exit 0 | its 6 checks passed |

(`cluster/README.md`, section of 11:25 pm.)

- Every judged arm adopted as the adoption file says: arm A f1 in reach and in land, and arms A and B f1 in reach3d. The two arms not judged, reach3d's C and D, adopted rC1 and c1. The 36 trial flights compared with the free check's flights differ in none (ruling 28, point 1).
- The pilot's 7,732 decisions had own lags of 0 steps in 5,532 and 1 step in 2,200, and none of two or three, so the reading of its decisions for the delay was clean. 1,098 observations were read a step or more late. The 144 flights, warm-ups included, made 12,024 sandboxed calls, all 'ok', with a median wall time of 42.2 ms, 51.2 ms at the 99.9th percentile and 135.6 ms at most (ruling 28, point 2; `cluster/README.md`).
- 28% of the pilot's decisions had one step of own lag, against 3% and 6% in the afternoon's pilots. The calls' processor time was about 5% higher at the start of the pilot and back at the afternoon's level by its end. Section 4.7 gives what this shows and what it does not (ruling 28, point 3).
- The approval file for the archive was written at 22:53:47, by ruling 27, point 6, after the pilot had been read (ruling 28, point 5). The sample then started as step 7 and did not fly, because the gateway refused the key (section 8.4; ruling 29).

The chain's records are kept on the cluster and copied whole to `runs/cluster-20261116/chain-F4-4800153/` on the Mac, with the job's log and the readings of the pilot (`cluster/README.md`).

### 8.11 The checking tools fixed, 17 November, no flight

The two reviews of 16 November left the checking tools one more pass before the freeze (ruling 27, point 4). It was made, reviewed and merged on 17 November. Every change is in `protocol/pilot_pass3.py`, `protocol/delay_check3.py` and `protocol/set_aside3.py`, their tests and one new file of test data (ruling 30, point 1).

- The source fingerprint is still 0dc7e3aa, so no flight, request, gate or analysis differs. The makers write the two expectation files again byte for byte from the second round's records, and the pass script at the merged head passes the rehearsal of record from its copy on the Mac, all 11 checks (ruling 30, point 2).
- The tools now refuse a delay file with an empty entry or an entry its maker could not have written; an adoption file with a judged arm that is not what every pilot it was made from adopted, a task in which no judged arm adopts, or a scripted candidate whose source is not the reply set's or that flew with no record; and set-aside attempts whose folders, receipts or route records are not as the tools write them. `protocol/set_aside3.py` judges a phase's route record as the gate does on each platform (ruling 30, point 3).
- Check 10 now requires, on the cluster, that the free check flew in the batch job that every phase of the pilot names. The second-round pilots then fail check 10 and nothing else, and the rehearsal of record still passes (ruling 30, point 4). The Mac's copies of the two-period pilots, which were copied without their receipts, fail it too. None of these is a record of record (ruling 30, point 7).
- An adoption file edited by hand to mark an arm as not judged still passes, so the approval file is written only when the pass script's two printed hashes are those named in section 9.1 (ruling 30, point 5).
- The first pass was read by a separate reviewer. The second pass and the last commit were read in full by the coordinating session, and by no separate reviewer. No chain has yet flown on the cluster with these tools as its judges (ruling 30, point 6).

### 8.12 The key check and the restart guard, 17 November, no flight and no request to the gateway

Ruling 29 asked for a free check of the key in the chain, and it was built, with the changes of section 9.1 that go with it (ruling 32).

- All of it is outside the source fingerprint, which is still 0dc7e3aa. Both expectation files are unchanged, their makers write them again byte for byte, and the pass script at the merged head passes the rehearsal of record, all 11 checks.
- A separate reviewer read it twice, and in its first reading also read the second pass of section 8.11, which until then only the coordinating session had read. It found nothing loosened there and two holes that needed a record edited by hand, both now closed (section 9.1, check 10).
- Its findings on the key check were fixed: a 200 with no count had counted as an answer, and a job started again by the batch system would have reused its approval file. The last fixes were read by the coordinating session alone (ruling 32, point 4).
- Every test ran against a stand-in server on the Mac with a made-up key. Nothing was sent to the gateway.
- Two one-core jobs on l40s-f-04 tried the memory note and showed that the batch system's memory figure counts a job's files in memory (section 4.7).
- The late-call check's calibration changed after the rehearsal of record. Step 6 of the rehearsal calibrated its slow loop on the process's clock. A tests job on 17 November showed that clock to be wrong inside a process whose numerical library has worker threads running, and the calibration now reads the calling thread's clock. In the check's own fresh process the two clocks agree, so the rehearsal's step 6 stands. The changed check has flown in no chain yet (ruling 33).

## 9. Order of work and the freeze

Done before this draft:

1. the code jobs of the takeover note, each reviewed by an agent that did not write it, and the builds of rounds four and five, each reviewed at a fixed commit before anything flew on it (round five, 'The build'). The last fixes to the checking tools were read in full by the coordinating session and by no separate reviewer (ruling 30, point 6);
2. the timing preflight, which set the load limit of 4.89 on the Mac (section 8.5). On the cluster the free check and the deadline rule take its place (round four, ruling 7);
3. the scripted pilot, flown on the cluster as the rehearsal of record, which passed on 16 November (section 8.10).

Still to do before the freeze, in this order:

1. the key check's first request to the gateway [GAP 8], in the next chain, once the model key works again (ruling 29, points 5 and 6; ruling 32). Until Simon says the key works, a chain is submitted only without its paid step, because a chain with it now sends that request in its first minute. If Simon is given a new key, the copy on the cluster is stale and is replaced from the Mac's file before a chain is submitted, with the two files' hashes compared first; his yes of 13 November to that copy stands (ruling 29, point 6);
2. the development sample, in a whole chain of section 9.1, whose free steps fly again and are read again before an approval file is written for its archive (ruling 27, point 6; ruling 29, points 3 and 4);
3. the reading of the sample against the checks of section 8.4 [GAP 1] [GAP 4] [GAP 5], with the times and the spend corrected from it [GAP 2] [GAP 3];
4. the completion of this text, every gap filled with its source;
5. two cold reviews, by Fable and by a fresh session that has seen none of the design.

Cold means read by a reviewer who has not seen the work before. Fable is a Claude model used as a cold reviewer. If Codex is available, it reviews the text and the code as it did for the second protocol.

### 9.1 The chain of record

The chain of record is one batch job, `cluster/chain.sbatch`, flown from one archive (section 4.7), so every step flies one source (round four, ruling 9). On the cluster its free check and its pilot must come from the same batch job (check 10 below; ruling 30, point 4). The job is given the archive, its SHA-256 as printed on the Mac, a date tag and `PAID`. Each step starts only if the step before it exited 0, and the chain's exit status says where it stopped. A job is never flown twice: the cluster starts a job again under the same job id after a node failure, so the script asks not to be requeued and, if it is started again anyway, stops at once with status 25 before it does anything (ruling 32, point 2).

| Step | What | Exit status of a chain that stops there |
|---|---|---|
| 0 | unpack the archive into memory, check its SHA-256, build the Python environment | 20, 21 or 22 |
| 0a | only if `PAID` is yes: the key check, one free token count asked of the gateway | 23 if the key is refused; 24 if there is no usable answer |
| 1 | the free check without the delay | 31 |
| 2 | the free check with the delay | 32 |
| 3 | the scripted pilot; each evaluation phase held for lateness is set aside once and the scheduler run again | 33 |
| 4 | the pass script, `protocol/pilot_pass3.py`, with step 2's record | 34 |
| 5 | the gate, the analysis and the position test on the pilot, for reading only | none; these do not gate |
| 6 | the late-call check, which flies one call made late on purpose and checks that it is flown again twice and then kept (round three, ruling 1) | 36 |
| 6a | only if `PAID` is yes and the approval file exists: the key check again | 0 before it if either is missing; 38 if the key is refused; 39 if there is no usable answer |
| 7 | the development sample, with `--spend-limit 4` | 37 |
| 8 | the gate, the analysis, the development check and the position test on the sample, for reading only, with no model call | none |

Each step has a time limit several times its time on record, and a step that passes it is stopped, which stops the chain. No step before step 7 makes a model call. With `PAID` yes the chain sends the gateway one free request before step 1 and one before step 7, each a token count; with `PAID` no it sends the gateway nothing (`cluster/chain.sbatch`; `cluster/key_check.py`).

The key check (`cluster/key_check.py`). It asks for a token count of a short fixed text for the study's model, through the provider's own client. An answer is an HTTP 200 that came through no redirect and carries a whole number of input tokens above 0. HTTP 401 or 403 is a refusal, after one request. Anything else is no usable answer, after three tries 20 s apart. What the gateway returns to this request has not yet been seen, for a working key or a blocked one [GAP 8] (ruling 32, points 1 and 7).

The free check (`protocol/delay_check3.py`). For each task it flies the reference controller on ten development cases, and the two scripted sources on development block 0's layouts. The scripted sources are procedures the model wrote in scored-2, kept in `ardupilot/testdata/adopt-replies.json`. That is 19 flights a task, 57 in all, as many at once as the pilot, each worker first flying its warm-up (round four, ruling 4). Without the delay every flight must end as it did on record. With the delay each reference controller must end as on record and each scripted case as the delay file says. In both, every flight must be on time, no sandboxed call may end 'timeout', 'crashed' or 'bad_reply', and no holder may be replaced (Build B, B2). A reference controller that ends another way would mean the delay had changed what a task demands, and that goes to the owner (round four, ruling 4).

The two expectation files. Both are made by their tools from records of two different batch jobs on the source fingerprint 0dc7e3aa, each was recomputed by a reviewer, and neither is edited by hand (rulings 25 to 27).

- `protocol/delay-check3-expected-3p.json`, SHA-256 `7fc375dc8959e838f70f00a26dc8633f0468b662ca05330f1bb6a762639eb259`, the delay file. It gives each scripted task, source and case the ending that its flights with the delay shared, read from the free checks of jobs 4799688 and 4799689. A case whose flights ended two ways has no expected ending, and the free check reports it without judging it. One case is in that state, reach3d's first source on threat-close-4010001 (ruling 21; ruling 26, point 4).
- `protocol/pilot3-adoption-3p.json`, SHA-256 `734d51284a6890fc7f6c1cb7aa2f22ac587b028f28fa204365c11db1f7f064f3`, committed at 910253b2, the adoption file. It gives each task and arm whether it adopts and which candidate, read from the pilots of jobs 4799690 and 4799691. An arm is judged only if every pilot read agrees on it and every layout its trials flew has an expected ending in the delay file. It judges arm A adopting f1 in every task, arm B adopting f1 in reach3d, and arms B, C and D adopting nothing in reach and land. Reach3d's arms C and D are not judged. No arm may adopt c0, judged or not (rulings 21, 25 and 27; section 8.9).

When the files may be made again. They are made again only under ruling 26, point 4. A flipped case is one task, one scripted source and one layout whose flight in a rehearsal ended otherwise than the delay file expects, on time, in a run where every call was 'ok' or 'error' and no holder was replaced. If a rehearsal fails on one flipped case and on nothing else, either at step 2 or at step 4 with check 3 failing only for arms whose trials flew that case, the rehearsal stays failed and nothing paid follows it. The case has then ended two ways at 0.3 s, so it loses its expected ending. The file concerned is made again by its tool from the records the ruling names, a fresh reviewer recomputes it, and the whole rehearsal flies once more from the commit with the remade file, whose source fingerprint must still be 0dc7e3aa. The owner is told, and Simon with him, of two or more flipped cases in one rehearsal, a flipped case together with any other failure, a second rehearsal that fails, a flip that would leave a task with no judged case or arm, a flip that touches reach3d's arm B, and a remade adoption file in which some task has no judged arm that adopts (ruling 26, point 4).

The pass script (`protocol/pilot_pass3.py`). It exits 0 only when all eleven of its checks pass, and it prints each that fails. The gate's own exit status cannot stand in for it, because the gate checks that records are well formed and not that a pilot passed (round four, ruling 5). The checks, as the script names them:

1. the scheduler finished with no phase needing a decision;
2. a pilot schedule of one learning block for each task;
3. every arm judged by the expected adoption adopted as it says, with the evaluation folders its adoptions call for;
4. the gate is ok, with 3 learning blocks and its phases equal to the folders;
5. the analysis is development only, with 9 primary intervals;
6. no learning flight kept late;
7. no phase set aside more than once;
8. every counted flight carried the 0.3 s delay and met every deadline;
9. one committed source for every phase, the one this script runs from;
10. the free check passed with the delay on the same source and platform, as many at once;
11. no sandboxed call of the run or its set-aside attempts timed out, crashed or replied badly.

Check 3 asks, for each task, for a `threat3` folder for every source the adoptions call for, c0's included, and a `retain3` folder for each of those that an arm adopted, with none missing and none extra (ruling 26, point 3). Check 10 also asks for the same processor model, wheel and route, no holder replaced in the free check or the pilot, and, on the cluster, a free check flown in the batch job that every phase of the pilot names, a phase that names no job counting against it (Build B, B2 and B3; ruling 30, point 4; ruling 32). A late attempt set aside must name the pilot's route (ruling 32). The script prints the SHA-256 of both expectation files.

The approval file. The paid step looks for a file named `paid-approved-`, the archive's SHA-256, `-job` and the chain's own job id, in the folder on the cluster that holds the archives, and runs only if it is there (`cluster/chain.sbatch`; `cluster/README.md`). Because the name carries the job, a file written for one chain can start no other (ruling 32, point 3). The coordinating session writes it only when all of these hold: steps 1 to 4 have exited 0; the gate and the analysis of step 5 have exited 0; the pilot's decisions have been read by ruling 20's fifth bullet, so that no decision has an own lag of three steps or more, or else every call over 85 ms behind such a decision came within 3 s after a phase boundary; and the pass script's two printed hashes are those of the two files above, or of files remade under ruling 26, point 4, and named in a ruling (ruling 27, point 6; ruling 30, point 5). After the sample's first calls the session reads the spend record, and cancels the job if replies come back while the record stays at zero or empty (ruling 28, point 5). If the reading is not clean, no file is written and the matter goes to Simon. If the session is gone, no file is written, and the chain stops before step 7 with status 0, so nothing paid flies on a rehearsal that nobody has read. A file serves the one chain that was read for it, and a later chain needs its own (ruling 29, point 3). The chain has no way to fly the sample alone, so a rehearsal that passed without the file means the sample waits for another whole chain (ruling 27, point 6).

### 9.2 The freeze

What the freeze fixes:

- this text, as `PROTOCOL-3.md`;
- `protocol/seeds-3.json`;
- the executed source, through the source fingerprint of section 2, which includes the fixed delay in `ardupilot/ladder.py`, the load limit in `ardupilot/scored.py` and the scheduler's order and stop, and the Paper 3 wheel with its build record;
- `protocol/analysis3.py`, `protocol/validate3.py` and `protocol/contract3.py`;
- the model settings, with the route to the model through the gateway (section 2).

Which of the tools and files outside the source fingerprint the freeze also fixes, the checking tools, the two expectation files and the cluster's batch scripts among them, no ruling yet says [GAP 6].

How it is recorded. The final draft is copied to `PROTOCOL-3.md` with the freeze edits made, and committed. The header then gives [GAP 6]:

- the date and time of the freeze;
- the commit of the text and the commit of the code;
- the SHA-256 of `PROTOCOL-3.md`, of `seeds-3.json`, of the wheel and of the three analysis files;
- the source fingerprint;
- the number of offline tests that pass;
- the reviews, with their files.

The runner refuses a scored phase without `PROTOCOL-3.md` or with uncommitted source (`guard` in `ardupilot/scored.py`), and writes the protocol's path and hash into every manifest. Until the freeze a pilot records the hash of `PROTOCOL-3-DRAFT.md`. That file is a placeholder of 12 lines at the root of `paper3/`, and is not this draft or any other. The manifests of the rehearsal of record carry its SHA-256, which begins 979f35e9. It is not changed while any pilot is running, and it stays as it is until the freeze, so that the gate at a later head still reads the records already flown and the development sample's manifests carry the same hash as its rehearsal's (ruling 31, point 2).

After the freeze this file is never edited. Any departure is recorded in `PROTOCOL-3-DEVIATIONS.md` with its date, its reason, who decided it and the phases it affects. Simon decides each deviation, on a proposal from the owner or a reviewer. Entries are added and never changed or removed, and the paper reports every one.

Operating rule: between the launch and the end of the analysis, nobody edits the fingerprinted files, the analysis files or `PROTOCOL-3.md`. The rule binds every agent working in this repository, and Simon.

Launch. The scored run flies on the platform of record (section 4.7). How it is split into batch jobs, the time limit of each and the command that starts it are not yet set [GAP 7]. No launch command for the Mac is written (round four, 'What runs next, in order'), and whether the Mac is still a fallback is open [GAP 12].

The plan is 96 learning blocks, then the evaluation and retention phases, as many at a time as `--at-once` allows, then the gate and the analysis. The forecast is 90 to 124 flights for each block, 8,600 to 11,900 in all. At scored-2's rate of 126 flights an hour that is 68 to 94 hours of flying, apart from pauses (DESIGN:144, SIZE:91). Scored-2 flew on the Mac without the delay, and no rate of flying has yet been measured on the cluster with procedures written by a model [GAP 2: the forecast corrected from the development sample's measured times].

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
- Every command reaches the vehicle 0.3 s after its observation, and scored-2 sent each command as soon as it was decided. A comparison of the two studies' flights carries that difference, and the paper says so (round four, ruling 6).
- The planning simulation was fitted to scored-2's adoption rates, from flights without the delay. At 0.3 s the scripted candidates fail their threat trials in reach and land, so the rehearsal tested adoption after a threat trial only in reach3d. Whether any arm can adopt at 0.3 s in reach and land is first tested by the development sample, which is read before the freeze (ruling 26, point 2; ruling 27) [GAP 4].
- Every flight of record flies on one node type, the L40S nodes of one cluster. Nothing flown there stands for another node type or for the Mac, and a call's waiting time is not comparable across platforms (ruling 22; round four, ruling 6).
- The nodes are shared with other users' jobs on other cores. The time of a sandboxed call moves by a few per cent with the node's other work, enough to change how many decisions have one step of own lag, though in the rehearsal not enough to come near the deadline. The cause was not shown (ruling 28, point 3) [GAP 5].

## References

Lakens D (2017) Equivalence tests: a practical primer for t tests, correlations, and meta-analyses. Social Psychological and Personality Science 8(4):355–362. The 4 outcomes and note 2 on the 90% interval were read at https://pmc.ncbi.nlm.nih.gov/articles/PMC5502906/ on 11 November 2026.

Olausson TX, Inala JP, Wang C, Gao J, Solar-Lezama A (2024) Is self-repair a silver bullet for code generation? ICLR 2024. arXiv:2306.09896v5. Sections 3.1, 3.2 and 4 and Appendix A were read at https://arxiv.org/html/2306.09896v5 on 11 November 2026.

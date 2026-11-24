# Designer knowledge given to Telohelm in paper 3

This ledger records what the designer tells Telohelm, or builds into the worlds it learns in, beyond the bare task. It follows the rule Simon set for paper 2 on 21 October 2026 (decision D42): record every change, do not block on it, and review afterwards. Paper 2 keeps its own ledger in `paper2/notes/DESIGNER-KNOWLEDGE-LEDGER.md`.

A task's contract fingerprint (`pack.PACKS[task].public.fingerprint({})`) changes whenever its learner text, readings or action fields change. Each entry gives the fingerprint after the change. The ledger starts on 1 November 2026. Earlier paper 3 task text (reach, reach3d, avoid, orbit, land) is in the git history of `ardupilot/pack.py`, and the reach3d contract has not changed since `runs/reach3d-demo` (fingerprint fb18162fd562…).

## 1 November 2026: the race3d task

The task was added after the rate study in `SYSTEM1-SPEED.md` showed that the learned reach3d procedure brakes into every gate, so it was written in response to an observed weakness. The aim is a skill that keeps its speed through gates.

What the learner is told, beyond the text shared with the other tasks:

- The gates to pass, in order, as a list in the goal, and a reading `gates_passed` that counts the gates passed so far. The text says the next gate is `ctx.goal.gates[ctx.gates_passed]`. With reach3d the runner handed over one gate at a time. Here the procedure picks the gate itself.
- The pass rule: a gate is passed when the path flown comes within the gate radius of its centre.
- "There is no need to stop or hold at a gate." The judge has no hold rule, so this sentence is true of the task. It also points away from the braking approach the reach3d procedure learned, so it counts as a hint and is disclosed here.
- The step length is given as `ctx.step_duration_s` (0.2 s) where the other tasks say each step is one second.

What shapes the world without being told:

- The time limit is the straight-line path between gates at 3 m/s, plus 3 s. It was calibrated on the designer's own reference controller (`demo.REFERENCE['race3d']`), which flew six scenarios at 2.7 to 3.1 m/s along that path. The first limit, 4 m/s, was beyond that reference and was dropped. The learner never sees the reference.
- The goal allows 10 m/s horizontally and 3 m/s vertically. ArduPilot's guided-mode limits are raised to WP_SPD_UP 5 m/s, WP_SPD_DN 3 m/s, WP_ACC 5 m/s² and WP_ACC_Z 3 m/s².
- Gates are generated three to five at a time, with legs of 7 to 15 m, turns up to 110 degrees, heights of 1.5 to 7 m and sometimes a gate directly below the one before (`battle.race_gates`).

Contract fingerprint: race3d 65c4c2ec7856eb801335a7406fb69c5ff677a825238962bb855edd84e3930556.

## 1 November 2026: race3d learning starts from the reach3d skill, with flight examples

The first race3d learning run (`runs/race3d-learn-1`) started from an empty library and refused all three candidates (five model calls, US$0.14). The first two flew at full speed straight at the next gate, passed two or three gates, then circled one it had overshot until time ran out. With no adopted procedure the practice flights held no actions to show the learner, and the demo runner had flight examples switched off (learn.py switches them on), so each request held only the task, the failure label and, after the first, the refused code with 'did not do its part of the goal'.

The second run (`runs/race3d-learn-2`) changes two things, both decided by the designer after that failure:

- The library starts with the reach3d procedure from `runs/reach3d-demo`, rewritten by `ardupilot/retarget.py` to read its target from the next gate. Gains, limits, threat and fence handling are unchanged. It is a working but slow skill: in the baseline it met the race time limit in one of six check scenarios. Whatever the learner adopts replaces it.
- Flight examples are on, as in learn.py: the learner sees moments from its own completed flights.

The race3d contract fingerprint is unchanged by this (the task text, readings and fields are the same).

Correction, same night: in `runs/race3d-learn-2` the examples did not reach the model. The learner reads examples from its own work folder, where learn.py writes each flight, and the demo runner wrote its flights elsewhere, so every example was dropped without an error. That run therefore starts from the reach3d skill with no examples; the model sees the skill's code and the failure labels. demo.py now copies each flight's record into the work folder when examples are on, and `runs/race3d-learn-3` repeats the run with examples reaching the model.

## 1 November 2026, late: a staged time limit (one test, then stop)

After nine refused candidates in `runs/race3d-learn-1` to `-3`, one staged sequence tests the world-modeller's graded practice. These are practice stages, not a change to the task: the race3d task's own limit stays the straight-line path at 3 m/s plus 3 s.

- Stage A (`runs/race3d-stage-a`): practice races at 2.5 m/s plus 3 s, starting from the retarget.py reach3d skill, with examples. The aim is to adopt a candidate that overshoots but finishes, so that its own flights become the next stage's examples.
- Stage B (`runs/race3d-stage-b`), only if stage A adopts: the task's own 3 m/s, starting from stage A's adopted procedure, with examples.

Nothing else changes: same task text, readings, guard, judge and scenarios apart from the time limit. The sequence runs once whatever the outcome.

Attribution note on `runs/race3d-stage-a` (checked with `ardupilot/attribution.py`): the model's requests contain one line of the designer's reference controller, `gate = g.gates[min(ctx.gates_passed, len(g.gates) - 1)]`. It is the next-gate lookup, which the designer wrote both in the reference and in `retarget.py`, and it reached the model inside the seed procedure shown in the library. No speed, braking or pacing line of the reference appears. The memorisation scan flags 1.6 as a training number (calm-1's first gate is at east 1.6 m); in the adopted code 1.6 multiplies the remaining path over the time left, a pacing factor, so the match is a coincidence.

## 2 November 2026: long practice courses for the racing skill

Simon asked for the racing skill to practise further. On the 19-gate Split-S the skill adopted in `runs/race3d-stage-b` fell behind its time limit, then its pacing rule raised its speed and it overshot tight turns. Its practice courses had three to five gates, so pacing over a whole course never mattered there.

The practice worlds change and the task does not:

- Two new race3d families, `long` and `longwind`, generate 10 to 16 gates by the same rules as `calm` and `wind` (`battle.RACE_GATE_COUNTS`). The time limit rule is unchanged: the straight-line path at 3 m/s plus 3 s. Existing calm and wind courses are generated exactly as before (checked against the six courses in `runs/race3d-stage-b`).
- The Split-S stays out of learning so it remains an unseen test. The long courses are shorter than it (105 to 182 m of straight-line path against its 190 m, from its 66.3 s limit).
- The race3d step cap rises from 40 s to 120 s, so a long race ends at its own time limit and not at the cap. The judge already ends every race at its limit, so short races are unaffected.
- The learning run starts from stage B's adopted procedure, with flight examples on, at the task's own pace (no stage pace).

Contract fingerprint unchanged: race3d 65c4c2ec7856eb801335a7406fb69c5ff677a825238962bb855edd84e3930556.

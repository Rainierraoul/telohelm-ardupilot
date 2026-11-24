# Paper 3, extra experiment: protocol

Written 23 November 2026, before any model call or flight of the experiment. It is not part of Study 2's frozen
protocol (PROTOCOL-3.md), which is unchanged. Everything here is exploratory and is reported as such.

## 1. Why, and the yes

Study 2 found that returning a failed candidate to the model for repair (arm C) raised the share of unseen zone flights
that met the goal by 0.49 (95% interval 0.40 to 0.59) over sending the same request again (arm B). Arm C's repair
request differs from arm B's in three ways: it carries the failed code, the one-line reason the candidate was refused,
and the candidate's three zone trial flights, which were the first zone flights that view of the learner ever saw. So
Study 2 cannot say whether the gain came from revising the code or from seeing the failure. Both referees asked for the
arm that separates the two. A second referee also asked for a hand-written yardstick, to show whether the procedures'
results are good or poor for this slow control loop.

Simon Vajda was told the extra arm would cost about US$12 to 13 at list price plus the gateway's 10%, and that the
yardstick needs cluster time only. His answer, 23 November 2026: "do the experiments, i say yes, i say yes for the cost,
just make it happen".

## 2. What runs, and on what code

Everything Study 2 ran is used unchanged, at commit a970d1a4 (source fingerprint 8700e012, seed book 1d39a62c, wheel
telohelm 0.1.0.dev0+paper3.2). The new code is in paper3/extra/ and touches nothing that the fingerprint covers:
arm_e.py (arm E's blocks), yardstick.py (the controller and its flights), phase.py, run_extra.py (Study 2's scheduler
with these phases), analysis_e.py and extra.sbatch. The flights run on the Deakin cluster, on the node type Study 2 flew
on, one job per task for arm E and one job for the yardstick. The model is Study 2's (the gateway's
bedrock/au.anthropic.claude-sonnet-5-5) with Study 2's settings.

## 3. Arm E

Arm E writes fresh candidates from a request that shows the failed zone trial flights and the reason, without the
failed code. It runs on Study 2's 120 learning blocks (40 for each of reach, reach3d and land), from each block's saved
records.

Slot 1 is c0, the candidate every arm of Study 2 shared. Its request, reply, source and zone trial are copied from
Study 2 and never drawn or flown again. If c0 passed its zone trial, arm E adopts it, as arms B and C did.

Slots 2 and 3 are rE1 and rE2. Each is tried on the block's three zone layouts with Telohelm's trial rule, as arm C's
rC1 and rC2 were, and the arm stops at the first pass. A slot is one call and at most one format repair, as in Study 2.

The request is built by Telohelm's own Coordinator exactly as arm C's was, with one change. The learner sees the block's
three zone-free first flights, and its first request must equal c0's saved request byte for byte, or the block stops.
Before rE1 it is told of c0's refusal with the same stage and reason that arm C's learner was told, and it then sees
c0's three zone trial flights under the same names. The source of the refused candidate is left out, which is what the
core itself does for a refusal that has no source (a format failure). The rules text is unchanged, so it still says
that the latest attempt's source is included; in arm E it is not. rE2 follows from rE1 the same way.

Where arm E's request for a slot is byte for byte arm C's saved request for that slot, arm E takes arm C's candidate
and its trial instead of drawing, as Study 2's arms share a candidate when they send the same request. This happens only
where c0 was not valid, since then there is no source to leave out.

A free dry pass, made before this protocol was written, rebuilt every block's slot 2 request with no model call. In all
108 blocks that need one, arm C's request rebuilt the same way equals Study 2's saved rC1 request byte for byte, and
arm E's request shows the same flights as arm C's and differs from it only in the missing source (435 to 1,019 fewer
input tokens, median 664). So 12 blocks adopt c0, 4 take arm C's rC1, and 104 draw rE1.

Every reply must name the model that served c0 in Study 2, and its message id must be new, counting the ids of every
reply Study 2 accepted, or the block stops as a fault.

## 4. Outcome and comparisons

The outcome is Study 2's: for each block and each of the task's 24 zone evaluation flights (8 in each distance band),
1 if the arm adopted a procedure and it met the goal on that flight, else 0. Arm E's adopted source is flown on the
same 24 flights by Study 2's evaluation phase, unchanged. A source that Study 2 already flew in the same block (c0, or a
candidate shared with arm C) is scored on Study 2's flights.

There are two comparisons, both paired by block: E − B (what showing the failure adds to sending the same request again)
and C − E (what showing the code adds to showing the failure). For every resample, E − B plus C − E equals C − B.

The intervals are 95% percentile intervals from Study 2's own crossed bootstrap (analysis3.bootstrap, 10,000 resamples)
on an array of the arms A, B, C and E, with each task's generator seeded as Study 2's primary pass seeds it. The draws
depend only on the array's shape and the generator, so arms A, B and C get the draws they had in Study 2, and the
script checks that its C − B and B − A, per task and pooled, equal Study 2's analysis.json to the last digit before it
reports anything about arm E. The pooled value is the mean of the three tasks. The 90% interval and the 0.20 margin are
read as in Study 2.

## 5. Readings, fixed now

- E − B with its pooled 95% interval above 0: showing the failed flights and the reason, without the code, raised
  success over sending the same request again.
- C − E with its pooled 95% interval above 0: showing the code added to showing the failure.
- C − E with an interval that includes 0: no added effect of showing the code was detected. If its 90% interval also
  lies within −0.20 to 0.20, any effect of showing the code was smaller than Study 2's margin.
- C − E with its interval below 0: showing the code lowered success.
- Each task's estimate is reported with its interval. A task whose interval excludes 0 on the other side of the pooled
  result is named.

Also reported, with no test: adoption in each arm; for arm E's drawn candidates and arm C's repairs in the same blocks,
the slots used, the candidates that were valid and the trials passed; goals met among the flights the adopted procedures
flew; zone entries among them; calls and cost; and E − B and C − E over the 104 blocks where c0 was valid and failed its
zone trial, from the generator Study 2 used for its C − B over the same blocks, which the script also checks against
Study 2's.

## 6. The platform control

Arm E flies three days after Study 2. To see whether the platform still gives Study 2's results, each task's job also
flies again Study 2's zone evaluation of arm C's adopted source in the first two blocks where arm C adopted one (reach
blocks 0 and 2, reach3d 0 and 1, land 3 and 4; chosen from arms.json alone). These six phases fly in the same pool as
arm E's evaluation phases, four simulators at once as in Study 2. Their 144 flights are compared one by one with Study 2's
flights of the same source and layout. If an exact McNemar test on goal met gives p below 0.05, the
platform is judged to have changed, and arm E's comparisons are reported with that finding beside them. Agreement in
how each flight ended is reported too, beside Study 2's own repeats: its evaluation attempts that were set aside for a
late flight and flown again.

This controls the flying, not the model. Arm E's replies are drawn three days after arm C's, from a gateway whose model
label names no snapshot. Every reply must carry the label Study 2's replies carried, but a change of the model behind
the same label would not be seen. That is a limitation of the comparison and is reported as one.

## 7. The yardstick

The yardstick is the designer's reference controller for the avoid task (demo.REFERENCE['avoid']) with two changes. It
reads the zone from ctx.threats, the zones active now, as Study 2's procedures had to, and it adds the vertical command
of the task's own reference controller (towards the target's height for reach3d; a descent within 0.8 m of the point for
land). The margin it keeps beyond the zone's edge is the one number left to choose. The grid is 1, 2, 3, 4 and 5 m (the
reference keeps 5 m).

The margin is chosen on development flights only: the pilot seed book's zone flights, which no study scored (its 6
evaluation flights and the zone layouts of its 4 learning blocks, 18 a task). For each task the margin under which most
development flights met the goal is chosen, a tie going to the larger margin. The choice is written to file before any
scored flight. All five margins then fly the 72 scored zone evaluation flights, and the chosen one is the yardstick; the
others are a sensitivity check. The yardstick's goals met and zone entries are reported beside those of the procedures
arms C and D adopted. No test is made.

## 8. Faults, late flights and the spending stop

Within a block, Study 2's rules apply unchanged: a transport failure, a time-out, a reply with no served-model label or
a repeated message id stops the block, and a late flight in learning is flown again in place. A block that stops is not
scored. Once a block has stopped, or been held by the spending stop, no further block starts in that job; the blocks
already finished are evaluated and the job ends, so that a refused key costs one block's calls. A refused key is
reported to Simon before anything else runs. Otherwise a further job resumes the run: it sets the stopped block aside
with set_aside3's own function and runs it again from the start, at most twice for each block, and the calls of every
attempt count in the spend. A block that cannot be completed is left out of all four arms alike, and the analysis says
so. An evaluation phase with a late flight is set aside and flown again by Study 2's rule, keeping its third attempt.

Arm E may spend US$13 at list price in all. Each task's job stops starting new blocks at US$4.33 at list (a block
already flying can add up to four calls). If a task's stop holds blocks while the three tasks together have spent less
than US$13, the held blocks run in a further job whose stop is what remains of the US$13. Spending beyond that is
Simon's decision.

## 9. What is checked

Study 2's evidence gate (validate3) reads Study 2's own phase names and is not run on these records. Instead: every
phase's manifest records the commit, the frozen source fingerprint and seed book, and the platform; the scheduler
refuses to start unless the fingerprint and seed book are the frozen ones; each arm E block checks that its first
request equals c0's saved request, that its layouts are the saved block's, and that every saved zone trial judged again
gives Study 2's verdict; every reply's model label and message id are checked as the block runs; and the analysis
checks that each scored phase holds exactly its 24 scheduled flights and a done mark, and that it reproduces Study 2's
intervals before it reports arm E's.

## 10. Reporting

Both comparisons, the control and the yardstick are reported whatever they show, in the paper as an exploratory
addition after Study 2's results, with this protocol and the records deposited with the rest.

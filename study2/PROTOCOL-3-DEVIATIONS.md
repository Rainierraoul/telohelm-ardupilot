# Paper 3, protocol 3: deviations

This file records every departure from the frozen protocol in `paper3/PROTOCOL-3.md` (SHA-256 06fbf29de34f5a8dd5e520a879df45d65ea344392f9cd4929b509182698710b7), as its section 9.2 requires. Each entry has its date, its reason, who decided it and the phases it affects. Simon decides each deviation. Entries are added and never changed or removed, and the paper reports every one.

## 1. The independent check of the nine intervals was made by a separate agent, not by Codex

Date: 22 November 2026.

What the protocol says: section 6.2 names Codex as the one who reproduces the three primary intervals and the six D − A intervals of RQ4 from the scored records with its own code, before the paper states them, and who reproduces what `protocol/sensitivity3.py` computes.

What was done: a separate Claude agent, started by the coordinating session, made the check. It was given the frozen protocol's text and the run's record files (21,767 files, each checked against the combined run's SHA256SUMS) and nothing else from the project. It was told not to open `protocol/analysis3.py`, `protocol/sensitivity3.py`, their tests, the analysis output or any note written after the freeze, and it reports that it opened none. It wrote its own code. The rule for a match was fixed before any outcome was read: point estimates equal, names the same, interval ends within 0.01 (ruling 105, point 4). All nine intervals matched, and so did the nine per-task steps beside them: every point estimate equal, every name the same, and no interval end further than 0.00625 from the analysis's (`reproduction/independent-check-20261122/COMPARISON.md`). The sensitivity script had nothing to compute on this run, because no learning call was kept late and no learning block was flown again, so there was no fill to reproduce.

Reason: Codex was at 6% of its weekly usage limit on 22 November and could not be relied on to finish. It was asked for this one job all the same (telohelm-swarm, `HANDOFF-TO-CODEX.md`, 2cb34fdc), and if it reports, its result is added below as a further entry.

What this changes: the check is made by an agent of the same maker as the tool that coordinated the study and wrote the analysis, where the protocol named another maker's tool. It did not see the analysis code or its output. No estimate, interval or name is affected.

Who decided: Simon, on 22 November 2026, told that Codex was near its limit: "we cant rely on it. You, with fable, will need to get the result". The coordinating session told him the same hour that the paper would then rely on the separate agent and say so.

Phases affected: none. No flight, learning block or evaluation phase is touched.

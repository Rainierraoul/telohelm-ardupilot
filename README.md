# Telohelm on ArduPilot

This repository holds the code, protocols and analysis for 'Code that never ran: testing and repairing flight procedures that a language model writes for ArduPilot in simulation' by Simon Vajda, Applied Artificial Intelligence Initiative, Deakin University. Paper status: in preparation. The study records are a separate deposit, described below.

Telohelm has a language model write a short Python procedure that flies a multirotor under the ArduPilot autopilot. A monitor that the model cannot change flies each procedure on test flights in simulation and adopts it only if it meets the goal on every one. An adopted procedure then flies with no model. The learning core is a separate release, Telohelm 0.1.0 (https://doi.org/10.5281/zenodo.23993336, https://github.com/Rainierraoul/telohelm).

The paper reports two studies. Study 1 learned procedures for five flight tasks and flew them on unseen flights, including flights in which a no-fly zone switched on that no test flight had held. Study 2, the main experiment, compares four ways of producing a procedure on 40 shared sets of test layouts for each of three tasks, and measures success on unseen flights in which a zone switches on. Two additions were flown after Study 2 under a second written protocol: a fifth way of producing a procedure, and an avoidance controller that uses no model, on the same unseen flights. The paper calls that controller the reference controller, and the second protocol calls it the hand-written controller. Both additions are reported in the paper and in section S19 of its supplement. An earlier comparison from the same run as Study 1, and a check of ArduPilot's own path planner on Study 2's flights, are reported in the supplement, and the paper gives their main results. All flights are simulated. The paper gives the results, and this repository does not restate them.

## What is in the repository

The two studies flew different versions of the same code, and each run recorded a fingerprint of the files it executed, one SHA-256 over all of them. Each study therefore has its own folder, holding the code exactly as that study flew it.

| Folder or file | Holds |
|---|---|
| `study2/PROTOCOL-3.md` | Study 2's protocol, frozen on 20 November 2026 before the main experiment; `study2/protocol/FROZEN-3.json` holds the values the run had to match, and `study2/protocol/drafts/` the protocol's three earlier versions |
| `study2/PROTOCOL-3-DEVIATIONS.md` | the one recorded departure from that protocol |
| `study2/ardupilot/`, `study2/protocol/` | the 86 fingerprinted files (task definitions, flight runners, the four ways of learning in `ardupilot/ladder.py`, the scheduler, every seed in `protocol/seeds-3.json`, the study's build of the learning core), then the validation check (`validate3.py`), the analysis (`analysis3.py`), the sensitivity analysis (`sensitivity3.py`) and their tests |
| `study2/results/scored-20261120-S/` | the analysis report as the run wrote it, and the SHA-256 of the full analysis output, which is in the data record |
| `study2/reproduction/independent-check-20261122/` | a second program, written from the protocol's text and the records alone, that recomputes the paper's nine intervals, with its output |
| `study2/PROTOCOL-EXTRA.md`, `study2/extra/` | the two additions after Study 2: their protocol, written on 23 November 2026 before any of their model calls or flights, and their code (`arm_e.py` and `phase.py` for the fifth arm, `yardstick.py` for the controller, `run_extra.py` and `extra.sbatch` to run them, `analysis_e.py` for the two comparisons, `rates_e.py` and `paired_e.py` for the exploratory rates and the comparison in the same blocks, `reply_search_e.py` for the search of the replies), with `extra/independent/`, a separate program written from the protocols that recomputes the comparisons, its output, its notes and the list of every file it opened. The code runs on Study 2's code in `study2/`, unchanged |
| `study2/reproduction/codex-check-20261122/` | a third program, written later by Codex from the protocol's text, with the nine results it recorded before opening the analysis output (Online Resource 1, S11); it was run from the project's frozen tree, so its path to the seed book is that tree's |
| `manuscript/` | the paper's four figures with the scripts that draw them, the reader that takes the supplement's counts from the records (`supplement21_records.py`), the exploratory totals over all flights and the Bonferroni-adjusted 98.3% intervals of supplement section S4 (`total_gain_all_flights.py`), the exploratory rates with intervals in the paper's Results and Table S7b (`exploratory_rates.py`), the counts read from the records for the paper's Results and supplement sections S5, S7 and S14 (`zone_entry_depth.py`, `first_candidate_zone_test.py`, `zone_start_times.py`, `repair_changes/`) the zone crossings counted from ArduPilot's logs and the sensitivity analysis built on them (`zone_entries_onboard_logs.py`, `zone_entry_rates_onboard.py`, `zone_entries_sensitivity.py`, `zone_crossings_timing.py`), and the reader of the planner's rows in the onboard logs |
| `study2/protocol/ladder_sim3.py`, `ladder_pooled3.py`, `study2/reproduction/ladder-*.json` | the planning simulation that set the number of blocks, with its output |
| `study2/planner_check/`, `study2/notes/PLANNER-CHECK-DESIGN-20261120.md` | the code and the design of the check of ArduPilot's planner |
| `study1/` | Study 1 and the earlier comparison: the 77 fingerprinted files, the two earlier protocols (`PROTOCOL-2.md` is the one that run followed), the analysis, its archived output and tables, an independent reader, and the script that counts the targets Study 1's generator moved out to 3 m beyond the zone (`study1/manuscript/study1_target_clearance.py`) |
| `reproduce.py` | checks the paper's results from the study records, for either study |
| `docs/` | `DATA.md`, a guide to the study records, and `SETUP.md`, for flying the studies again |

Files under `study1/` were written before the main experiment existed. Where they say 'Study 2' they mean the earlier comparison, which the paper reports in Supplement S13.

## Check the paper's results from the study records

This needs Python 3.12 and numpy, and no simulator or model. From the data record (https://doi.org/10.5281/zenodo.24022883) download `study2-interval-records.zip` (58 MB), `study2-analysis-output-records.zip` (26 MB) and the two `CONTENTS-SHA256SUMS` files that go with them, and unzip both ZIPs into one empty folder. Then, from the root of this repository:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install numpy==2.5.4
.venv/bin/python reproduce.py study2 --records <folder> --sums <first sums file> --sums <second sums file>
```

The script compares every record file with its SHA-256, checks that the analysis output is the one the paper was written from, runs the independent recomputation again on the outcome records, and compares it with the deposited analysis. It prints one line for each check, and it says which checks it did not run. It took about two minutes on the author's Mac.

One check needs more. Running the frozen analysis itself again requires the full records, because its validation check reads every log of every flight. Download `study2-records.zip` as well, unzip it into the same folder, and install the study's own packages first:

```sh
.venv/bin/python -m pip install --no-deps study2/protocol/telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl
.venv/bin/python -m pip install --no-deps -r study2/cluster/requirements-mac.txt
```

The docstring at the top of `reproduce.py` lists every check exactly.

For Study 1 and the earlier comparison, download `scored-2-records.zip` and `scored-2-CONTENTS-SHA256SUMS.txt`, unzip into an empty folder, install `study1/protocol/telohelm-0.1.0.dev0-py3-none-any.whl` and `study1/requirements-tested.txt` in the same way, each with `--no-deps`, and run `reproduce.py study1 --records <folder> --sums <file>`. Use a separate environment for each study, because the two studies use different builds of the learning core.

The scripts in `manuscript/` name the author's own folders as defaults. Each takes the folder or file it reads on its command line, as its header says, so the figures and the supplement's counts can be made again from the unzipped records.

## The source that flew

Every phase of Study 2 recorded the fingerprint `8700e012b2d85b7f57bfd8c5d2958aa80edcfd9ab3e515527ae7f3de60563afa` over 86 files, and every phase of Study 1 recorded `2e02a6e11b9f6e6e4117112195c734fc26cd5759262a3ff252bcf19ec6195ace` over 77 files. The files in `study2/` and `study1/` give those values (`source_files()` in each `ardupilot/scored.py` lists them), so you can check that this code is the code that flew. Study 2's frozen protocol has SHA-256 `06fbf29de34f5a8dd5e520a879df45d65ea344392f9cd4929b509182698710b7`.

Some files name folders on the author's computer or on the university cluster. They are unchanged because the fingerprints cover them.

## Fly the studies again

You can, with limits: it needs ArduPilot built for simulation, a model endpoint and a long run, and a new run makes new model calls, so it will not give the paper's numbers. [docs/SETUP.md](docs/SETUP.md) says what each study used.

## Licences

The code is released under the [MIT licence](LICENSE). Documentation, the protocols, figures and the analysis output are released under [CC BY 4.0](LICENSE-data). The [NOTICE](NOTICE) file lists third-party material that keeps its own terms, which are in `LICENSES/`. ArduPilot and Gazebo are not included.

## How to cite

GitHub's 'Cite this repository' button reads [CITATION.cff](CITATION.cff). The code is archived at https://doi.org/10.5281/zenodo.24022881 and the study records at https://doi.org/10.5281/zenodo.24022883. Please cite the paper and Telohelm 0.1.0 as well.

## Use of AI

Claude Code (Anthropic) and Codex (OpenAI) wrote and reviewed the software, the protocols, the analyses and drafts of the paper under Simon Vajda's direction. He set the questions and the scope, made the design and resource decisions and is responsible for the claims. The paper's section on the use of AI gives the account. The learning model inside the experiments is separate from these tools. The protocols and the deviations record were written for the project and name its internal decision records ('rulings') and working notes, which are not part of this release.

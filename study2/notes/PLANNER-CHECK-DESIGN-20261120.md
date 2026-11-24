# ArduPilot's own planner on Study 2's zone flights: design of an exploratory check

Written 20 November 2026, before any scored result exists, on branch `claude/paper3-planner` cut from `claude/paper3-n40-expect` at 6e8fa110. Nothing has been flown for it. It answers ruling 97, point 2: Copter's object avoidance flies the same zone flights as the study, with no model call, as an exploratory check reported apart from the scored comparisons, and its design is fixed before the scored run's results are read.

Two terms are used throughout. The planner is ArduPilot Copter's path planner, selected by the parameter `OA_TYPE`. A setting is one complete set of planner parameters, flown on every scenario. Other words (scenario, band, zone, the fixed delay) mean what the protocol's glossary says (`protocol/drafts/PROTOCOL-3-draft-3.md` on `claude/paper3-protocol-d3`).

## 1. What the check asks

Study 2 compares procedures learned by Telohelm with each other. A reader will ask how often the autopilot's own tool for this job, given the same zone at the same moment, reaches the goal and keeps out of the zone. The check answers that by description. It gives the planner's rate of success and of `entered_threat` on the 72 zone scenarios the arms are evaluated on, by task and by distance band, for each of seven settings. It makes no test against any arm, and nothing in it can move a scored interval.

## 2. What ArduPilot does, read in the version the study flies

The study flies ArduPilot Copter 4.7.2, commit fb77356 (`ArduCopter/version.h`; `cluster/README.md`, line 9). Each fact below was read in that commit's source and, where the wiki covers it, in the wiki pages for the Dijkstra and BendyRuler planners (ardupilot.org/copter/docs/common-oa-dijkstras.html and common-oa-bendyruler.html, read 20 November 2026). File paths are relative to the ArduPilot checkout.

1. The planner works toward a waypoint in Auto and RTL, and toward a position target in Guided only when `GUID_OPTIONS` bit 6 is set. With the default `GUID_OPTIONS` of 0, a Guided position target goes straight to the position controller and the planner never sees it (`ArduCopter/mode_guided.cpp`, lines 380 and 670; the parameter's bitmask in `ArduCopter/Parameters.cpp`, line 826). The Dijkstra page says: "For use in Guided mode, set GUID_OPTIONS bit 6 (e.g. 64)." Ruling 92's sentence "toward a waypoint in Auto, RTL and Guided" needs this condition added.
2. The planner does not act on velocity commands. It runs inside the waypoint controller (`AC_WPNav_OA::update_wpnav` in `libraries/AC_WPNav/AC_WPNav_OA.cpp`), and a Guided velocity command does not use that controller. This part of ruling 92 holds.
3. A second, simpler ArduPilot feature does act on velocity commands. Simple avoidance (`AVOID_ENABLE`, default 3, whose bit 0 means "use fence") slows or stops a Guided velocity command short of an enabled fence, exclusion circles included (`ArduCopter/mode_guided.cpp`, line 852; `AC_AVOID_DEFAULT` in `libraries/AC_Avoidance/AC_Avoid.h`, line 19; `adjust_velocity_exclusion_circles` in `AC_Avoid.cpp`, line 1074). The study ran with the fence off (`FENCE_ENABLE` 0, the default), so it never acted. Wherever the paper says ArduPilot's avoidance does not act on the procedures' velocity commands, it should say this of the path planner only, and add that simple fence avoidance would act on them if the zone were loaded as an enabled fence. This check does not fly simple avoidance, because that would mean flying learned procedures with a fence on, which changes the study's own flights. It is a possible later check.
4. `OA_TYPE` is read only when the autopilot starts ("Dijkstra OA requires reboot", `libraries/AC_Avoidance/AP_OAPathPlanner.cpp`, lines 133 to 145). The settings therefore go in a defaults file given to the simulator at start-up. Setting them over the link after start, as the study's `Sitl` class does for wind, would leave the planner off.
5. A fence can be loaded during flight. The fence upload code has no check on whether the vehicle is armed or flying (`libraries/GCS_MAVLink/MissionItemProtocol.cpp`). Dijkstra notices a changed exclusion circle on its next cycle and plans again from where the vehicle is (`AP_OADijkstra.cpp`, line 90 and `calc_shortest_path`). BendyRuler reads the fence afresh on every cycle. This is read from the code and has not been flown; the shake-down flights of section 9 confirm it.
6. The planner runs in its own thread once a second and ignores results more than 3 s old (`OA_UPDATE_MS` and `OA_TIMEOUT_MS`, `AP_OAPathPlanner.cpp`, lines 34 and 35). While the target is unchanged the waypoint controller may keep using a recent result during a fence update (`AP_OAPathPlanner.cpp`, lines 228 to 253). It brakes only when the planner reports that it is still working out a new plan, and then only if `OA_OPTIONS` bit 2 is clear (`AC_WPNav_OA.cpp`, lines 169 to 187). The default `OA_OPTIONS` is 1, which leaves that bit clear.
7. Sending a destination, even the same one again, resets the waypoint controller's avoidance state (`AC_WPNav_OA::set_wp_destination_NED_m`, lines 41 to 50). Dijkstra separately compares the destination's coordinates before it throws its path away (`AP_OADijkstra.cpp`, lines 154 to 164). The study's existing comparator (`ardupilot/autopilot_modes.py`) sends its position target every second, which with the planner on would restart the planner every second. The check therefore sends each target once. A Guided position target does not time out (`ArduCopter/mode_guided.cpp`, line 760 stops only the yaw).
8. Dijkstra turns each exclusion circle into a hexagon whose corners lie about 1.155 × (radius + `OA_MARGIN_MAX`) from the centre (`AP_OADijkstra.cpp`, lines 553 to 563), and tests path segments against the circle's own radius (lines 660 to 671). So a target 3 m outside the zone can be reached even when the margin is larger than 3 m.
9. BendyRuler prefers a direction whose look-ahead path keeps more than `OA_MARGIN_MAX` from the fence. When no direction passes both of its checks it still returns the best one it found (`AP_OABendyRuler.cpp`, `search_xy_path`, lines 223 to 246). Every close-band target lies 3.0 to 4.0 m past the zone's edge (section 5), inside the default margin of 5 m. This is why the margin is one of the two values swept.
10. With `OA_TYPE` 3 and no proximity sensor, BendyRuler is asked only about sensed objects, finds none, and Dijkstra makes every decision (`AP_OAPathPlanner.cpp`, the case at line 357, with `proximity_only` starting true, `AP_OAPathPlanner.h`, line 135; `calc_margin_from_object_database` returns false on an empty database). Type 3 therefore flies as type 2 here and is not flown separately.
11. The zone scenarios have no wind. The threat family sets the wind to 0 in all 72 evaluation scenarios (`generate` in `ardupilot/battle.py`; checked offline from the seed book). The simulator's scaling of wind by the square root of height over 60 m below 60 m (ruling 92, point 4) is therefore true of these flights but changes nothing in them.

## 3. The settings flown

Seven settings fly. Setting 0 is the planner switched off, which shows what the same autopilot does when it flies straight at the target. Settings 1 to 6 sweep the two planners and the values that ArduPilot's code and wiki give for the two parameters that decide how close the planner lets the vehicle come to the zone (fact 9) and how far ahead BendyRuler looks.

| Setting | `OA_TYPE` | `OA_MARGIN_MAX` (m) | `OA_BR_LOOKAHEAD` (m) |
|---|---|---|---|
| 0 | 0, off | 5, not used | 15, not used |
| 1 | 2, Dijkstra | 5 | not used |
| 2 | 2, Dijkstra | 2 | not used |
| 3 | 1, BendyRuler | 5 | 15 |
| 4 | 1, BendyRuler | 5 | 5 |
| 5 | 1, BendyRuler | 2 | 15 |
| 6 | 1, BendyRuler | 2 | 5 |

Where the values come from:

- `OA_TYPE` 0, 1 and 2 are the parameter's documented values (`AP_OAPathPlanner.cpp`, line 42). Type 3 is left out by fact 10.
- `OA_MARGIN_MAX` 5 is the code's default (`OA_MARGIN_MAX_DEFAULT`, `AP_OAPathPlanner.cpp`, line 31). 2 is the wiki's value: "2m is a typical value" (BendyRuler page).
- `OA_BR_LOOKAHEAD` 15 is the code's default (`OA_BENDYRULER_LOOKAHEAD_DEFAULT`, `AP_OABendyRuler.cpp`, line 28). 5 is the wiki's value: "5m is typical" (BendyRuler page).

Setting 1 is named now as the headline setting, so that the discussion cannot later choose the best one. It is Dijkstra, which the wiki names for this job ("path planning around fences and stay-out zones"), with its default planning margin of 5 m. Several flight settings in the table below differ from ArduPilot's defaults, among them `GUID_OPTIONS` and `FENCE_ENABLE`, because the planner cannot act without them. The paper reports all seven settings and gives the headline with the range across settings 1 to 6.

These parameters are the same in every setting:

| Parameter | Value | Source |
|---|---|---|
| `FENCE_ENABLE` | 1 | needed for either planner to read a fence: Dijkstra returns "not required" unless the polygon fence type is enabled (`AP_OADijkstra.cpp`, `some_fences_enabled`), and BendyRuler skips circles in the same case (`AP_OABendyRuler.cpp`, line 609) |
| `FENCE_TYPE` | 7, default for Copter: altitude, circle round home, polygons and circles | `AC_FENCE_TYPE_DEFAULT`, `libraries/AC_Fence/AC_Fence.cpp`, line 26 |
| `FENCE_RADIUS` | 150 m | the simulator's own Copter defaults file, `Tools/autotest/default_params/copter.parm`, which the study already loads |
| `FENCE_ALT_MAX` | 100 m, default | `AC_Fence.cpp`, line 30 |
| `FENCE_MARGIN` | 2 m, default | `AC_Fence.cpp`, line 35 |
| `FENCE_ACTION` | 1, default: RTL or land on a breach | `AC_Fence.cpp`, line 75 |
| `GUID_OPTIONS` | 64 | fact 1 and the Dijkstra page |
| `OA_OPTIONS` | 1, default | `AP_OAPathPlanner.cpp`, line 32 |
| `OA_BR_CONT_RATIO`, `OA_BR_CONT_ANGLE`, `OA_BR_TYPE` | 1.5, 75, 1, defaults | `AP_OABendyRuler.cpp`, lines 29 to 31 |
| `AVOID_ENABLE` | 3, default | `AC_Avoid.h`, line 19; it does not act in the waypoint controller (fact 3) |
| `WP_SPD`, `WP_SPD_UP`, `WP_SPD_DN` | 5, 2 and 2 m/s | the procedures' own limits, `max_speed_ms` and `max_vertical_ms` in `ardupilot/pack.py`, as the existing comparator sets them (`LIMITS` in `ardupilot/autopilot_modes.py`) |
| everything else, the wind included | as in the study's flights | `Episode.reset` in `ardupilot/pack.py` |

In setting 0 the fence is still enabled and still loaded when the zone switches on, so that settings 0 and 1 differ only in `OA_TYPE`.

The home circle of 150 m and the altitude limit of 100 m are fences the procedures do not have; their own rule is 120 m from home (`FENCE_M` in `ardupilot/pack.py`). The furthest evaluation target is 66.9 m from home and the highest is 28.1 m up. That says where the goals lie, not where the vehicle went; whether any flight came near either fence is read from its recorded track.

Before take-off each flight reads back from the autopilot every parameter in these two tables that exists in the setting, and records the values. A value that differs from the setting's is a fault (section 6). The four BendyRuler parameters (`OA_BR_LOOKAHEAD`, `OA_BR_CONT_RATIO`, `OA_BR_CONT_ANGLE`, `OA_BR_TYPE`) exist in 4.7.2 only when `OA_TYPE` is 1, because the autopilot creates BendyRuler only then; in settings 0 to 2 they are not written to the defaults file and not expected, and the flight asks for them anyway and records whether the autopilot reports them absent. (Amended 20 November 2026, after the build's review, before any scored result.)

## 4. What the planner is told, and when

The rule is that the planner gets what a procedure gets, at the same moment, and nothing more.

The goal. A procedure reads its target from `ctx.goal` at every step. The planner gets the same target once, as a Guided position target, at the first command stamp of the flight (the observation of step 0 plus the fixed delay of 0.3 s).

- Reach: the target's north and east, at the height the drone holds at that moment, which is the take-off height of 10 m. This is the existing comparator's rule (`autopilot_modes.py`).
- Reach3d: the target's north, east and height.
- Land: the target's north and east at the height held at that moment. When the autopilot's own estimate puts the drone within 0.5 m of the point across the ground, the check switches the autopilot to LAND, which comes straight down and lands at 0.5 m/s (`LAND_SPD_MS_DEFAULT`, `ArduCopter/config.h`, line 322), under the 1 m/s touchdown limit. This is again the existing comparator's rule. LAND joins GUIDED as a mode that does not end the flight, as in the comparator.

Neither side is told the hold time or the radius as such. A procedure reads them from `ctx.goal`; the autopilot holds at its target once there, and descends in LAND, which meets them or not.

The zone. A procedure does not see a zone at the instant it switches on. The zone switches on at the start of a step (`Episode.step`, `ardupilot/pack.py`), the observation at the end of that step is the first that lists it in `ctx.threats`, and the first command that can take it into account reaches the vehicle 0.3 s after that observation. The planner gets the zone at that same moment. When the check's episode sends its command for a step, which happens after the same hold to 0.3 s past the observation, it uploads as an exclusion circle every zone that the last observation listed and that it has not yet uploaded. The circle's centre is the zone's north and east turned into latitude and longitude with the study's own constants (`HOME` and `M_PER_DEG_LAT` in `ardupilot/vehicle.py`), and its radius is the zone's radius. The flight is judged against the zone from the moment it switched on, exactly as a procedure's is, because the check uses the study's own `Episode.step` unchanged.

The switch-on rule is the study's: the first step that begins with the drone within 19 m of the zone's edge, or half the time limit if that comes first. It runs unchanged in the planner's flights, but the planner's own path decides when the drone crosses 19 m, as a procedure's does.

Each flight therefore uses the same rule to reveal the zone. A procedure can first respond with its next command, and on the planner's flights the check starts sending the zone to ArduPilot at that point. This gives the planner no head start. It does not make the two receive the zone at the same instant, because the autopilot must still accept the upload and its planner must then read the new fence. What still differs between the two sides:

1. The planner controls the vehicle many times a second through the autopilot's own controllers. A procedure commands a velocity once a second. This is a difference in how each side flies, not in what it knows.
2. The planner thinks once a second in its own thread and brakes while it does (fact 6). A procedure's command waits a fixed 0.3 s. The planner's own reaction time is part of what is measured.
3. The upload itself takes a few messages between the check and the autopilot. Each flight records the simulated time at which the upload started and the time the autopilot acknowledged it.
4. Once the fence is loaded, the autopilot also polices it: if its own position estimate enters the circle it switches to RTL (`FENCE_ACTION` 1). A procedure has no such fallback. If RTL cannot start, the fence code lands instead (`ArduCopter/fence.cpp`, lines 72 to 81). A flight in which this happens ends as `autopilot_rtl`, or as `entered_threat` if the true position is inside the zone at that step, because the study's judge checks the zone first. The land task allows LAND, so an end reason alone does not find every fence action; the autopilot's recorded reason for each mode change is used for that.
5. The procedures are told in their task text that zones may appear. The planner has no notion of zones to come. Neither side knows where a zone will be before it switches on.

If the shake-down shows that ArduPilot will not accept a fence during flight, the check uses this fallback instead, fixed now. The fence is uploaded before take-off with `FENCE_ENABLE` 0, and at the moment described above the check sends `MAV_CMD_DO_FENCE_ENABLE`. While the fence is disabled neither planner reads it (`some_fences_enabled` in Dijkstra, line 609 in BendyRuler) and simple avoidance does not act. The difference from the study's trial is then that the zone's data sits in the autopilot's memory from the start of the flight, unread by any code that steers the vehicle until it is enabled. The note is amended to say which way was flown before any scored result is read.

## 5. Scenarios, seeds and flights

The check flies the study's 72 evaluation scenarios, the same held-out zone flights on which every arm's success is counted (`threat_evaluation` in `protocol/seeds-3.json`, SHA-256 1d39a62c…; `evaluation_cases` in `protocol/contract3.py`):

- reach 3100001 to 3100008 (close), 3100101 to 3100108 (middle), 3100201 to 3100208 (wide);
- reach3d 3110001 to 3110208 and land 3120001 to 3120208, in the same pattern.

The protocol's bands are close, 3 to 4 m past the zone's edge, middle, 9 to 11 m, and wide, 19 to 21 m. The paper's distant targets, "10 to 20 m", are the middle and wide bands together, as in RQ4. Read offline from the seed book, the close targets lie 3.0 to 4.0 m past the edge and 40.0 to 50.3 m from home, and the zones' near edges lie 24.0 to 30.0 m from home with radii of 6.0 to 9.0 m.

No learning seed, retention seed or seed from 5000 to 5099 is flown, and `TELOHELM_ALLOW_SCORING_SEEDS` is never set. The evaluation seeds are scored seeds, so the check flies them only after the freeze (protocol section 5). The shake-down of section 9 flies the development evaluation seeds instead (`pilot.threat_evaluation`: reach 4100001, 4100002, 4100101, 4100102, 4100201 and 4100202, and the same pattern from 4110001 for reach3d and from 4120001 for land).

Each setting flies each scenario once in a pass, as each adopted source flies each scenario once in the study (protocol section 4.2). The check flies two passes. The second is identical to the first and measures how often the simulator alone changes a flight's end reason, which the reader needs to judge the planner's rates; two is the fewest passes that measure it.

| | Close | Distant (middle and wide) | All |
|---|---|---|---|
| Flights per task, setting and pass | 8 | 16 | 24 |
| Flights per task, all 7 settings, both passes | 112 | 224 | 336 |
| Flights in all | 336 | 672 | 1,008 |

Order. A pass lists every pair of setting and scenario sorted by task, band, seed and setting, and deals them in turn to four workers on simulator instances 10 to 13 (`FLIGHT_INSTANCES` in `protocol/contract3.py`): worker k flies items k, k + 4, k + 8 and so on. The second pass deals the list in reverse order, so that a drift in the node's speed over a job falls on different settings in the two passes. Each worker first flies the study's own warm-up flight (`fly_warmup` in `ardupilot/ladder.py`, on the case `warmup_case` in `ardupilot/scored.py` names), which is not a flight of the check. Flights run in real time, speed-up 1, as the study's do, with the study's fixed delay of three telemetry steps (`COMMAND_DELAY_PERIODS` in `ardupilot/ladder.py`), so that every command and upload goes out on the stamp a procedure's would.

Cluster time, on one L40S node with 16 cores and 32 GB and four simulators at once, the size of a scored job (ruling 31, point 3). In the second development sample a flight took 55 s of wall time beyond its flown seconds, median and largest alike, over 155 evaluation flights (`threat3-*/flights/results.jsonl` in `runs/cluster-20261119/chain-4802829/runs/dev3-sample-20261118-R2/`, read from the `before_flight` times). If every flight ran to its time limit, a reach flight would take 145 s and a reach3d or land flight 175 s, so one setting's pass takes at most 3.3 simulator-hours and the whole check at most 46 simulator-hours, about 11.6 hours on the node. At the sample's median of 1.36 minutes for an evaluation flight it takes about 23 simulator-hours, about 5.7 hours on the node. Each pass is its own job of at most 5.8 hours. The shake-down takes at most 1.4 hours (126 flights). The check may run on a node the scored run leaves free (ruling 97, point 2), never on a node a scored job is using.

## 6. Scoring

The check scores every flight with the study's own judge, unchanged. Its episode is a subclass of `Episode` in `ardupilot/pack.py` that changes only how the simulator is started (to pass the defaults file) and how each step's command reaches the autopilot (`send_command`, the hook that `autopilot_modes.py` already uses). `step`, the judge on the simulator's true state, the zone switch-on, `entered_threat`, the fence of 120 m, the time limits and `outcome` are the study's own code, imported and not copied.

A flight's success is what an evaluation cell's success is in the analysis: `goal_met` in its `outcome.json` (`protocol/analysis3.py`, line 749), which is true only when the end reason is the task's success (`held` for reach and reach3d, `landed` for land). A zone entry is the end reason `entered_threat`, as in `actual_flight_endings_by_arm`. The adoption rule (`component_trial`) does not apply, because the planner is not a candidate and issues no procedure command.

A fault is a flight that stops without an outcome: a simulator error, missing truth, a parameter that reads back wrong, or a fence upload not acknowledged before the end of its step. A fault is kept in a `faults/` folder and the flight is flown again at the end of its worker's list, at most three attempts in all, the study's limit for a late call (`REFLIGHTS` in `ardupilot/ladder.py`). A flight that faults three times is reported as a fault, never as a failure or a success. The study's timing fields are recorded for every flight (`timing` in `ardupilot/ladder.py`) and reported. No flight is flown again for lateness, since there is no procedure whose slowness could be charged.

Each flight also records whether the planner acted: the number of planner rows in the flight's onboard log in which Dijkstra returned a path or BendyRuler was active (the `OADJ` and `OABR` messages in the simulator's `.BIN` log, read with pymavlink). A planner setting that never acts on a scenario whose straight path crosses the zone shows up in these counts.

## 7. Records, and how they stay apart from the scored run

The check writes to its own run root, `paper3/runs/planner-check-<date>/` at home and its own folder under `/scratch` on the cluster, never inside a scored run's root. The scored run's gate and analysis never read it, and it writes nothing into a scored root: no `message-ids.jsonl`, no manifest a scored phase would read, no seed reservation. It imports no model provider and makes no model call.

Its manifest records the ArduPilot commit, the SHA-256 of each setting's defaults file, the settings table, the seed book's hash, the source fingerprint of the scored build for reference (8700e012…, 86 files), the SHA-256 of each of the check's own files, the node, the job number and the order flown. Each flight folder holds `outcome.json`, a hash-chained `episode.log` as the comparator writes it, the fence uploads with their times, the parameters read back and the planner counts.

## 8. How it is reported

The check is exploratory and descriptive. The paper gives it its own short subsection after the scored results, says it was designed after Study 2 was fixed and before its results were read, and keeps it out of the abstract's results. For each task, and for close and distant targets, it gives each setting's successes and zone entries as counts out of flights flown ("k of 16"), the other end reasons, the faults, and the agreement between the two passes ("the two passes gave the same end reason on k of 72 scenarios"). There are no intervals and no tests.

Beside these, the discussion may place each arm's own descriptive figures that the analysis already writes (protocol section 6.5): success over all its cells, success among blocks that adopted, and zone entries out of `flights_possible`. It says plainly that the denominators differ. An arm's rate counts a block that adopted nothing as failing every flight; the planner's rate is per flight of one fixed controller. Neither rate is set against the other in a test, and no claim of better or worse rests on them.

## 9. Building it

The code is new and lives in a new folder, `paper3/planner_check/`, outside the source fingerprint. The fingerprint covers `ardupilot/*.py` at the top level only, the Gazebo files, the seed books and five named files in `protocol/` (`source_files` in `ardupilot/scored.py`), so a new top-level folder cannot change it. No file of the scored build is edited. The branch is not merged into the scored build's branch before the scored run's archive is made, and the check flies from its own archive.

The fingerprint was run from `paper3/` on this branch before the note was written and after it was committed, with the command `scored.use_protocol(3); scored.source_fingerprint()`. Both times it gave 8700e012b2d85b7f57bfd8c5d2958aa80edcfd9ab3e515527ae7f3de60563afa over 86 files. The builder runs it again after each commit, and the reviewer once more.

Files:

- `planner_check/settings.py`: the seven settings and the fixed parameters of section 3, each with its source, and a function that writes a setting's defaults file.
- `planner_check/episode.py`: `PlannerSitl`, the study's `Sitl` with the setting's defaults file added to `--defaults` and the parameter read-back; and `PlannerEpisode(pack.Episode)`, whose `send_command` sends the target once, uploads new zones as exclusion circles over the mission protocol with mission type FENCE (`MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION`, MAVLink 2), and switches to LAND for the land task. While waiting for the upload's acknowledgement it passes every other message to `Sitl._handle`, so the state stays current. `Sitl.__init__` builds its command inside the constructor, so `PlannerSitl` repeats that code with the one extra file, and a test shows the two commands differ only there.
- `planner_check/fly.py`: one worker of one pass, from the seed book's evaluation cases or, with `--shakedown`, the development ones. It refuses any seed that is not in that list, refuses seeds 5000 to 5099, and refuses to write into an existing folder.
- `planner_check/summarise.py`: the counts of section 8 from the flight folders, with the pass agreement and the planner counts, as JSON and as a table.
- `planner_check/planner_check.sbatch`: one pass on one node, four workers, 16 cores and 32 GB, after the pattern of the study's batch scripts in `cluster/`.
- `planner_check/test_planner_check.py`: offline tests, with no simulator.

The offline tests show that:

1. the source fingerprint is 8700e012… over 86 files with the folder present;
2. each defaults file holds exactly its setting's values and the fixed ones;
3. `PlannerSitl`'s command is `Sitl`'s with one more defaults file;
4. with a stand-in simulator, the target is sent once, a zone is uploaded at the first command after the observation that first lists it, and never before, its latitude, longitude and radius turn back into the zone's north, east and radius within 1 cm, and LAND is set only within 0.5 m;
5. `PlannerEpisode` uses `Episode.step`, the judge and `outcome` from `ardupilot/pack.py` and defines none of its own;
6. the flight lists are the 72 evaluation cases and the 18 development cases, with no other seed, and the two passes' orders are each other's reverse;
7. the summary counts a hand-made set of outcomes correctly, faults apart;
8. nothing in the folder imports `ardupilot.claude_provider` or reads `TELOHELM_ALLOW_SCORING_SEEDS`.

Order of work:

1. A Sonnet builder writes the files and tests on this branch, edits nothing outside `paper3/planner_check/` and this note, flies nothing, and reports the test counts and the fingerprint.
2. A fresh Opus reviewer checks the code against this note at a fixed commit. Nothing changes on the branch during the review; fixes come as a second pass.
3. The coordinating session flies the shake-down on a free node: all seven settings on the 18 development scenarios, once, 126 flights. It passes if every flight arms with the setting's parameters read back correctly, every upload is acknowledged before the end of its step, and settings 1 to 6 each show planner rows in at least one flight. Its successes and zone entries are not used to choose or change any setting. If it fails, the cause and the change, the fallback of section 4 among them, are written into this note before any scored result is read.
4. After the freeze, the two passes fly as two jobs on a node the scored run leaves free.
5. The summary is made, and the paper's subsection is written from it.

## 10. What the check cannot show

It describes seven settings of one autopilot on 72 scenarios. It cannot say how the planner would do with other settings, with sensed obstacles, with wind, or on zones of other shapes. It does not say whether a learned procedure should replace the planner, which the paper already says the zone was never meant to test (ruling 94, point 4). Because the planner and the procedures control the vehicle in different ways, a difference in their rates cannot be put down to what each was told, and the check never claims one.

## 11. The shake-down, flown 20 November 2026

Amended after the fact, before any scored result exists. The shake-down of section 9, step 3, flew as job 4869830 on node l40s-f-02, on commit 0573c2c3 and the primary route (the fence loaded in flight). It flew all seven settings on the 18 development evaluation cases, once: 126 flights, on four simulators at once. The scored build's fingerprint in the manifest was 8700e012b2d85b7f57bfd8c5d2958aa80edcfd9ab3e515527ae7f3de60563afa over 86 files, and the ArduPilot commit was fb77356. The records are in `runs/planner-check-20261120/S1-pass1-shakedown/`. Every figure below was counted from the flight folders (`planner.json`, `outcome.json`, `results.jsonl`, `manifest.json`).

What was checked, and what it showed:

1. Every flight armed and ended with an outcome on its first attempt. There were no faults and no flight was flown again.
2. The parameters read back. All 126 flights read back every expected parameter at the setting's value, with no mismatch. In settings 4 and 6 `OA_BR_LOOKAHEAD` read 5, and in settings 3 and 5 it read 15, so the defaults file's late reload reached the planner. In the 54 flights of settings 0 to 2 the autopilot reported all four BendyRuler parameters absent.
3. The fence upload. Each of the 126 flights made exactly one upload and had it acknowledged. The acknowledgement came at the simulated time the upload began, to the 0.1 s the clock gives, and the smallest margin before the end of the step was 0.70 s.
4. Planner rows. All 126 onboard logs were read. Each of the 108 flights of settings 1 to 6 had planner rows (Dijkstra paths or active BendyRuler rows); the 18 flights of setting 0 had none.
5. Timing. No flight was late by the study's rule.

Dijkstra's error rows. Dijkstra logged an error in 15 flights, 8 of setting 1 and 7 of setting 2, with a single row each, and the code was 8 every time. In 4.7.2 (`AP_OADijkstra.h`) the error codes count from zero in this order: none, out of memory, overlapping polygon points, failed to build inner polygon, overlapping polygon lines, fence disabled, too many fence points, no position estimate, could not find path. Code 8 is `DIJKSTRA_ERROR_COULD_NOT_FIND_PATH`: in `AP_OADijkstra.cpp` it is set in the shortest-path search when a node visible from the starting point cannot be found by its identifier. While Dijkstra reports an error the vehicle does not steer round the zone by its path. The summary counts these flights separately from the flights where the planner acted (`dijkstra_failed_flights`), and the paper reports them.

End reasons over the 126 flights: entered_threat 53, held 44, landed 19, timed_out 7, autopilot_rtl 3. By setting, entered_threat was 18 of 18 for setting 0 and 8, 11, 3, 2, 6 and 5 for settings 1 to 6. The three autopilot_rtl flights were in settings 2, 3 and 3; the seven timed_out were in settings 3, 4 and 6. These are development cases and are reported here only because they are in the records. The rule of section 9 holds: the successes and zone entries of the shake-down chose nothing and changed nothing. No setting, parameter, route or rule of this note was picked or altered because of them. The changes made after the build were the review's, made from the code and the ArduPilot source before the shake-down flew.

The shake-down passed the three conditions of section 9, step 3. The fallback of section 4 was built and tested offline and was not flown, because the primary route worked.

## 12. Corrections from Codex's review, made 20 November 2026, 2:17 pm

Codex reviewed this note at 3b0970bb and the code at c6908316 against the ArduPilot 4.7.2 source (`paper3/notes/REVIEW-CODEX-PLANNER-DESIGN-20261120.md` on `codex/paper3-review-planner-20261120`, 131185b2). Its one code finding, that the fallback read the stored `FENCE_ENABLE` where the in-flight command changes only the active fence mask, was already fixed at d24bfa2d, which reads the geofence bit of `SYS_STATUS`. Its corrections to the description are made in place in facts 6 to 9, the naming of the headline setting in section 3, the sentence on how far the goals lie from home, and the account of when each side learns of the zone in section 4. The fence's landing fallback and the use of the recorded mode-change reason are added to point 4 of section 4. No setting, parameter, route, rule or line of code changed. The shake-down's results played no part in these edits, and no scored result existed.

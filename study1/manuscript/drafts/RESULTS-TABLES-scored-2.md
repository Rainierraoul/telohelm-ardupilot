# Paper 3 results tables

From `runs/scored-2/analysis/analysis.json` (phase folders read 254, hash-chain errors 0).

Table 1. Learning (RQ1). Adoption over learning runs with Wilson 95% interval; model calls and list-price cost per run, median (range), the cost from recorded token counts at list price (the gateway reports no billed charge, so billed cost is unavailable); wall-clock minutes per run.

| Task | Adopted | Model calls | Cost, US$ | Minutes |
|---|---|---|---|---|
| reach | 8/8 (1.00; 0.68 to 1.00) | 2.0 (2 to 2) | 0.063 (0.058 to 0.074) | 11 to 12 |
| reach3d | 8/8 (1.00; 0.68 to 1.00) | 2.0 (2 to 2) | 0.068 (0.065 to 0.075) | 13 to 13 |
| avoid | 5/5 (1.00; 0.57 to 1.00) | 2 (2 to 2) | 0.086 (0.079 to 0.101) | 13 to 14 |
| orbit | 5/5 (1.00; 0.57 to 1.00) | 2 (2 to 5) | 0.073 (0.065 to 0.210) | 16 to 45 |
| land | 8/8 (1.00; 0.68 to 1.00) | 2.0 (2 to 3) | 0.079 (0.070 to 0.116) | 13 to 14 |

Table 2. Held-out scenarios (RQ2). Goal met, k/n (rate; Wilson 95% interval). Learned libraries pooled; differences are learned minus comparator on the same scenarios, with the crossed bootstrap 95% interval (libraries and one common draw of scenarios). Avoid has no autopilot-mode comparator.

| Task | Learned | Reference | ArduPilot modes | Hold still | Learned - reference | Learned - modes |
|---|---|---|---|---|---|---|
| reach | 240/240 (1.00; 0.98 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 0/30 (0.00; 0.00 to 0.11) | +0.00 (+0.00 to +0.00) | +0.00 (+0.00 to +0.00) |
| reach3d | 240/240 (1.00; 0.98 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 0/30 (0.00; 0.00 to 0.11) | +0.00 (+0.00 to +0.00) | +0.00 (+0.00 to +0.00) |
| avoid | 150/150 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) |  | 0/30 (0.00; 0.00 to 0.11) | +0.00 (+0.00 to +0.00) |  |
| orbit | 150/150 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 0/30 (0.00; 0.00 to 0.11) | +0.00 (+0.00 to +0.00) | +0.00 (+0.00 to +0.00) |
| land | 240/240 (1.00; 0.98 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | 0/30 (0.00; 0.00 to 0.11) | +0.00 (+0.00 to +0.00) | +0.00 (+0.00 to +0.00) |

Table 2a. Held-out scenarios per library.

| Task | Library | Goal met | Learned - reference |
|---|---|---|---|
| reach | learn-reach-b0-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach | learn-reach-b1-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach | learn-reach-b2-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach | learn-reach-b3-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach | learn-reach-b4-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach | learn-reach-b5-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach | learn-reach-b6-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach | learn-reach-b7-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b0-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b1-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b2-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b3-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b4-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b5-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b6-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| reach3d | learn-reach3d-b7-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| avoid | learn-avoid-0 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| avoid | learn-avoid-1 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| avoid | learn-avoid-2 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| avoid | learn-avoid-3 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| avoid | learn-avoid-4 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| orbit | learn-orbit-0 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| orbit | learn-orbit-1 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| orbit | learn-orbit-2 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| orbit | learn-orbit-3 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| orbit | learn-orbit-4 | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b0-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b1-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b2-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b3-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b4-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b5-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b6-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| land | learn-land-b7-matched | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |

Table 3. Transfer with learning off (RQ3). Courses completed and gates passed by the learned libraries, pooled; the reference controller on the same courses; learned minus reference on the same courses with the crossed bootstrap 95% interval (libraries and one common draw of scenarios).

| Test | Learned, completed | Learned, gates | Reference, completed | Learned - reference |
|---|---|---|---|---|
| Flat courses (reach) | 240/240 (1.00; 0.98 to 1.00) | 1176/1176 (1.00; 1.00 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | +0.00 (+0.00 to +0.00) |
| Building courses (reach3d) | 160/160 (1.00; 0.98 to 1.00) | 960/960 (1.00; 1.00 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | +0.00 (+0.00 to +0.00) |
| Split-S, SITL (reach3d) | 40/40 (1.00; 0.91 to 1.00) | 760/760 (1.00; 0.99 to 1.00) | 5/5 (1.00; 0.57 to 1.00) |  |
| Split-S, Gazebo (reach3d) | 24/24 (1.00; 0.86 to 1.00) | 456/456 (1.00; 0.99 to 1.00) | 3/3 (1.00; 0.44 to 1.00) |  |

Table 3a. Transfer per library and for the reference controller. The subset column is secondary: courses completed among those the reference controller completed; the headline counts every course.

| Test | Controller | Completed | Gates | Completed where reference completed | Courses the reference failed |
|---|---|---|---|---|---|
| Building courses | learn-reach3d-b0-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | learn-reach3d-b1-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | learn-reach3d-b2-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | learn-reach3d-b3-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | learn-reach3d-b4-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | learn-reach3d-b5-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | learn-reach3d-b6-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | learn-reach3d-b7-matched | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) | 20/20 (1.00; 0.84 to 1.00) | none |
| Building courses | Reference controller | 20/20 (1.00; 0.84 to 1.00) | 120/120 (1.00; 0.97 to 1.00) |  | none |
| Flat courses | learn-reach-b0-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | learn-reach-b1-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | learn-reach-b2-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | learn-reach-b3-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | learn-reach-b4-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | learn-reach-b5-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | learn-reach-b6-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | learn-reach-b7-matched | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) | 30/30 (1.00; 0.89 to 1.00) | none |
| Flat courses | Reference controller | 30/30 (1.00; 0.89 to 1.00) | 147/147 (1.00; 0.97 to 1.00) |  | none |
| Split-S, SITL | learn-reach3d-b0-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, SITL | learn-reach3d-b1-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, SITL | learn-reach3d-b2-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, SITL | learn-reach3d-b3-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, SITL | learn-reach3d-b4-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, SITL | learn-reach3d-b5-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, SITL | learn-reach3d-b6-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, SITL | learn-reach3d-b7-matched | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b0-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b1-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b2-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b3-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b4-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b5-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b6-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | learn-reach3d-b7-matched | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, Gazebo | Reference controller | 3/3 (1.00; 0.44 to 1.00) | 57/57 (1.00; 0.94 to 1.00) |  |  |
| Split-S, SITL | Reference controller | 5/5 (1.00; 0.57 to 1.00) | 95/95 (1.00; 0.96 to 1.00) |  |  |

Table 2b. Capped seconds on held-out scenarios (secondary): seconds to meet the goal, a failed flight counted at its time limit; learned libraries pooled minus the comparator on the same scenarios, with the crossed bootstrap 95% interval (libraries and one common draw of scenarios).

| Task | Learned - reference | Learned - modes |
|---|---|---|
| reach | -1.90 s (-3.05 to -0.87) | +2.03 s (+0.88 to +3.08) |
| reach3d | -3.04 s (-3.52 to -2.42) | +0.49 s (+0.11 to +1.07) |
| avoid | -7.79 s (-8.85 to -6.79) |  |
| orbit | +0.41 s (-4.86 to +6.97) | +11.11 s (+5.81 to +17.74) |
| land | -4.02 s (-6.43 to -1.72) | -9.72 s (-12.09 to -7.44) |

Table 3b. Decision steps to finish a course (secondary), learned minus reference, on the courses both completed; the last column gives how many pairs that is out of those scheduled, since the subset selects on success.

| Courses | Learned - reference | Pairs used |
|---|---|---|
| Flat courses | -0.49 (-1.01 to +0.02) | 240 of 240 |
| Building courses | -0.85 (-1.74 to -0.01) | 160 of 160 |

Table 4. Disturbances, descriptive. Goal met, summed over the task's learned libraries (counts only). Jamming and radio loss test ArduPilot's configured failsafes (landing and return-to-launch), not the learned procedure; Table 4a gives each flight's actual ending. In the other four the procedure stays in control.

| Task | Jamming | Spoofing | Radio loss | Gust | Weak motor | Threat zone |
|---|---|---|---|---|---|---|
| reach | 0/40 | 40/40 | 0/40 | 40/40 | 40/40 | 4/40 |
| reach3d | 1/40 | 40/40 | 0/40 | 40/40 | 40/40 | 23/40 |
| avoid | 0/25 | 17/25 | 0/25 | 25/25 | 23/25 | 12/25 |
| orbit | 0/25 | 0/25 | 0/25 | 25/25 | 25/25 | - |
| land | 0/40 | 17/40 | 0/40 | 40/40 | 37/40 | 16/40 |

Table 4a. How the disturbance flights ended.

| Task | Family | Endings |
|---|---|---|
| reach | Jamming | autopilot_land 40 |
| reach | Spoofing | held 40 |
| reach | Radio loss | autopilot_rtl 40 |
| reach | Gust | held 40 |
| reach | Weak motor | held 40 |
| reach | Threat zone | entered_threat 1, held 4, timed_out 35 |
| reach3d | Jamming | autopilot_land 39, held 1 |
| reach3d | Spoofing | held 40 |
| reach3d | Radio loss | autopilot_rtl 40 |
| reach3d | Gust | held 40 |
| reach3d | Weak motor | held 40 |
| reach3d | Threat zone | entered_threat 6, held 23, timed_out 11 |
| avoid | Jamming | autopilot_land 25 |
| avoid | Spoofing | entered_zone 8, held 17 |
| avoid | Radio loss | autopilot_rtl 25 |
| avoid | Gust | held 25 |
| avoid | Weak motor | ground_contact 2, held 23 |
| avoid | Threat zone | entered_threat 13, held 12 |
| orbit | Jamming | autopilot_land 25 |
| orbit | Spoofing | left_orbit 25 |
| orbit | Radio loss | autopilot_rtl 24, left_orbit 1 |
| orbit | Gust | orbited 25 |
| orbit | Weak motor | orbited 25 |
| land | Jamming | autopilot_land 40 |
| land | Spoofing | landed 17, landed_off_point 23 |
| land | Radio loss | autopilot_rtl 40 |
| land | Gust | landed 40 |
| land | Weak motor | hard_landing 1, landed 37, landed_off_point 2 |
| land | Threat zone | entered_threat 4, landed 16, timed_out 20 |

Table 5. Repeatability. Scenarios whose three repeat endings agree.

| Task | Controller | Endings agree |
|---|---|---|
| avoid | learn-avoid-0 | 5/5 (1.00; 0.57 to 1.00) |
| avoid | Reference controller | 5/5 (1.00; 0.57 to 1.00) |
| land | learn-land-b0-matched | 5/5 (1.00; 0.57 to 1.00) |
| land | Reference controller | 5/5 (1.00; 0.57 to 1.00) |
| orbit | learn-orbit-0 | 5/5 (1.00; 0.57 to 1.00) |
| orbit | Reference controller | 5/5 (1.00; 0.57 to 1.00) |
| reach3d | learn-reach3d-b0-matched | 5/5 (1.00; 0.57 to 1.00) |
| reach3d | Reference controller | 5/5 (1.00; 0.57 to 1.00) |
| reach | learn-reach-b0-matched | 5/5 (1.00; 0.57 to 1.00) |
| reach | Reference controller | 5/5 (1.00; 0.57 to 1.00) |

Table 6. Decision timing, descriptive: decision lag in seconds of simulated time, and the procedure's and guard's wall-clock seconds per decision, median / 95th percentile / maximum.

| Phase | Lag | Share of decisions at least 0.1 s late | Procedure | Guard | Decisions without a procedure |
|---|---|---|---|---|---|
| learn | 0.000 / 0.100 / 0.201 | 0.174 | 0.043 / 0.054 / 0.156 | 0.030 / 0.040 / 0.070 | 24300/30780 |
| heldout | 0.000 / 0.100 / 0.401 | 0.100 | 0.042 / 0.050 / 0.427 | 0.030 / 0.036 / 0.226 | 0/54641 |
| repeat | 0.000 / 0.098 / 0.198 | 0.054 | 0.043 / 0.053 / 0.113 | 0.030 / 0.036 / 0.086 | 0/3647 |
| autopilot | 0.000 / 0.001 / 0.100 | 0.007 | - | - | - |
| disturb | 0.000 / 0.100 / 0.301 | 0.107 | 0.042 / 0.054 / 0.192 | 0.030 / 0.037 / 0.116 | 0/23894 |
| threat | 0.001 / 0.100 / 0.201 | 0.120 | 0.042 / 0.048 / 0.171 | 0.030 / 0.036 / 0.126 | 0/43897 |
| courses | 0.100 / 0.200 / 0.899 | 1.000 | 0.039 / 0.057 / 0.623 | 0.030 / 0.037 / 0.312 | 0/18026 |
| splits | 0.100 / 0.102 / 0.201 | 1.000 | 0.036 / 0.053 / 0.103 | 0.029 / 0.035 / 0.068 | 0/3972 |
| gazebo | 0.100 / 0.100 / 0.200 | 1.000 | 0.043 / 0.046 / 0.132 | 0.030 / 0.032 / 0.042 | 0/2393 |

Table 6a. Threat zones: least realised first-sight distance (m).

| Library | Least distance | Flights | Under 9 m |
|---|---|---|---|
| learn-land-b0-matched (land) | 9.47 | 5 | 0 |
| learn-land-b1-matched (land) | 10.14 | 5 | 0 |
| learn-land-b2-matched (land) | 10.23 | 5 | 0 |
| learn-land-b3-matched (land) | 9.6 | 5 | 0 |
| learn-land-b4-matched (land) | 10.14 | 5 | 0 |
| learn-land-b5-matched (land) | 10.1 | 5 | 0 |
| learn-land-b6-matched (land) | 10.86 | 5 | 0 |
| learn-land-b7-matched (land) | 10.19 | 5 | 0 |
| learn-reach-b0-matched (reach) | 10.76 | 5 | 0 |
| learn-reach-b1-matched (reach) | 9.34 | 5 | 0 |
| learn-reach-b2-matched (reach) | 10.26 | 5 | 0 |
| learn-reach-b3-matched (reach) | 9.62 | 5 | 0 |
| learn-reach-b4-matched (reach) | 9.43 | 5 | 0 |
| learn-reach-b5-matched (reach) | 10.22 | 5 | 0 |
| learn-reach-b6-matched (reach) | 9.9 | 5 | 0 |
| learn-reach-b7-matched (reach) | 9.53 | 5 | 0 |
| learn-reach3d-b0-matched (reach3d) | 12.3 | 5 | 0 |
| learn-reach3d-b1-matched (reach3d) | 12.3 | 5 | 0 |
| learn-reach3d-b2-matched (reach3d) | 11.89 | 5 | 0 |
| learn-reach3d-b3-matched (reach3d) | 12.18 | 5 | 0 |
| learn-reach3d-b4-matched (reach3d) | 12.34 | 5 | 0 |
| learn-reach3d-b5-matched (reach3d) | 12.32 | 5 | 0 |
| learn-reach3d-b6-matched (reach3d) | 12.31 | 5 | 0 |
| learn-reach3d-b7-matched (reach3d) | 12.04 | 5 | 0 |
| learn-land-b0-matched (threat evaluation) | 9.31 | 20 | 0 |
| learn-land-b0-threat (threat evaluation) | 9.26 | 20 | 0 |
| learn-land-b1-matched (threat evaluation) | 9.95 | 20 | 0 |
| learn-land-b1-threat (threat evaluation) | 10.66 | 20 | 0 |
| learn-land-b2-matched (threat evaluation) | 9.83 | 20 | 0 |
| learn-land-b2-threat (threat evaluation) | 9.58 | 20 | 0 |
| learn-land-b3-matched (threat evaluation) | 9.28 | 20 | 0 |
| learn-land-b3-threat (threat evaluation) | 9.29 | 20 | 0 |
| learn-land-b4-matched (threat evaluation) | 9.41 | 20 | 0 |
| learn-land-b4-threat (threat evaluation) | 11.05 | 20 | 0 |
| learn-land-b5-matched (threat evaluation) | 9.97 | 20 | 0 |
| learn-land-b5-threat (threat evaluation) | 9.31 | 20 | 0 |
| learn-land-b6-matched (threat evaluation) | 9.99 | 20 | 0 |
| learn-land-b6-threat (threat evaluation) | 9.35 | 20 | 0 |
| learn-land-b7-matched (threat evaluation) | 9.89 | 20 | 0 |
| learn-land-b7-threat (threat evaluation) | 10.05 | 20 | 0 |
| learn-reach-b0-matched (threat evaluation) | 10.0 | 20 | 0 |
| learn-reach-b0-threat (threat evaluation) | 9.47 | 20 | 0 |
| learn-reach-b1-matched (threat evaluation) | 9.09 | 20 | 0 |
| learn-reach-b1-threat (threat evaluation) | 9.07 | 20 | 0 |
| learn-reach-b2-matched (threat evaluation) | 9.5 | 20 | 0 |
| learn-reach-b2-threat (threat evaluation) | 9.31 | 20 | 0 |
| learn-reach-b3-matched (threat evaluation) | 9.07 | 20 | 0 |
| learn-reach-b3-threat (threat evaluation) | 9.09 | 20 | 0 |
| learn-reach-b4-matched (threat evaluation) | 9.31 | 20 | 0 |
| learn-reach-b5-matched (threat evaluation) | 9.6 | 20 | 0 |
| learn-reach-b5-threat (threat evaluation) | 9.12 | 20 | 0 |
| learn-reach-b6-matched (threat evaluation) | 9.25 | 20 | 0 |
| learn-reach-b6-threat (threat evaluation) | 9.22 | 20 | 0 |
| learn-reach-b7-matched (threat evaluation) | 9.09 | 20 | 0 |
| learn-reach-b7-threat (threat evaluation) | 9.38 | 20 | 0 |
| learn-reach3d-b0-matched (threat evaluation) | 9.59 | 20 | 0 |
| learn-reach3d-b0-threat (threat evaluation) | 9.44 | 20 | 0 |
| learn-reach3d-b1-matched (threat evaluation) | 10.07 | 20 | 0 |
| learn-reach3d-b1-threat (threat evaluation) | 9.39 | 20 | 0 |
| learn-reach3d-b2-matched (threat evaluation) | 9.43 | 20 | 0 |
| learn-reach3d-b2-threat (threat evaluation) | 10.28 | 20 | 0 |
| learn-reach3d-b3-matched (threat evaluation) | 10.1 | 20 | 0 |
| learn-reach3d-b3-threat (threat evaluation) | 9.62 | 20 | 0 |
| learn-reach3d-b4-matched (threat evaluation) | 10.06 | 20 | 0 |
| learn-reach3d-b4-threat (threat evaluation) | 9.96 | 20 | 0 |
| learn-reach3d-b5-matched (threat evaluation) | 10.1 | 20 | 0 |
| learn-reach3d-b5-threat (threat evaluation) | 9.33 | 20 | 0 |
| learn-reach3d-b6-matched (threat evaluation) | 9.95 | 20 | 0 |
| learn-reach3d-b6-threat (threat evaluation) | 10.71 | 20 | 0 |
| learn-reach3d-b7-matched (threat evaluation) | 9.65 | 20 | 0 |

Table 7. Attribution checks per adopted procedure: code lines; matches in its code of numbers from its own learning scenarios (each occurrence counted); model requests containing a reference-controller line longer than 25 characters, after removing text the model wrote earlier; held-out scenario numbers found in the requests, against the same search for never-flown control scenarios.

| Library | Lines | Learning-number matches in code | Requests with reference-line hits | Held-out numbers found | Control numbers found |
|---|---|---|---|---|---|
| avoid-0 | 49 | 0 | 0 | 2/124 | 1/121 |
| avoid-1 | 63 | 0 | 0 | 3/128 | 2/117 |
| avoid-2 | 57 | 0 | 0 | 2/129 | 1/121 |
| avoid-3 | 53 | 0 | 0 | 1/127 | 2/121 |
| avoid-4 | 52 | 0 | 0 | 4/127 | 1/123 |
| land-b0-matched | 52 | 0 | 0 | 1/129 | 2/127 |
| land-b0-threat | 83 | 0 | 0 | 2/124 | 1/125 |
| land-b1-matched | 55 | 0 | 0 | 1/130 | 0/127 |
| land-b1-threat | 69 | 0 | 0 | 1/128 | 1/126 |
| land-b2-matched | 59 | 0 | 0 | 1/129 | 1/127 |
| land-b2-threat | 59 | 0 | 0 | 1/129 | 1/122 |
| land-b3-matched | 54 | 0 | 0 | 1/129 | 1/126 |
| land-b3-threat | 88 | 0 | 0 | 2/125 | 1/121 |
| land-b4-matched | 59 | 0 | 0 | 2/130 | 2/128 |
| land-b4-threat | 60 | 0 | 0 | 1/129 | 2/125 |
| land-b5-matched | 39 | 0 | 0 | 1/130 | 2/128 |
| land-b5-threat | 103 | 0 | 0 | 4/129 | 4/125 |
| land-b6-matched | 53 | 0 | 0 | 2/130 | 2/127 |
| land-b6-threat | 52 | 0 | 0 | 2/128 | 2/126 |
| land-b7-matched | 57 | 0 | 0 | 1/130 | 0/126 |
| land-b7-threat | 72 | 0 | 0 | 1/127 | 1/122 |
| orbit-0 | 33 | 0 | 0 | 3/69 | 2/75 |
| orbit-1 | 31 | 0 | 0 | 2/70 | 4/79 |
| orbit-2 | 29 | 0 | 0 | 1/70 | 2/77 |
| orbit-3 | 23 | 0 | 0 | 2/70 | 3/76 |
| orbit-4 | 61 | 0 | 0 | 1/71 | 3/78 |
| reach-b0-matched | 46 | 0 | 0 | 2/130 | 2/127 |
| reach-b0-threat | 67 | 0 | 0 | 2/128 | 1/125 |
| reach-b1-matched | 39 | 0 | 0 | 0/131 | 0/127 |
| reach-b1-threat | 65 | 0 | 0 | 1/130 | 1/124 |
| reach-b2-matched | 48 | 0 | 0 | 1/131 | 1/126 |
| reach-b2-threat | 53 | 0 | 0 | 2/130 | 3/123 |
| reach-b3-matched | 56 | 0 | 0 | 1/130 | 3/126 |
| reach-b3-threat | 50 | 0 | 1 | 1/127 | 2/124 |
| reach-b4-matched | 37 | 0 | 0 | 3/130 | 1/127 |
| reach-b5-matched | 41 | 0 | 0 | 0/129 | 1/127 |
| reach-b5-threat | 91 | 0 | 0 | 1/127 | 3/124 |
| reach-b6-matched | 51 | 0 | 0 | 2/129 | 1/127 |
| reach-b6-threat | 71 | 0 | 0 | 2/127 | 3/124 |
| reach-b7-matched | 44 | 0 | 0 | 1/131 | 1/127 |
| reach-b7-threat | 69 | 1 | 0 | 2/129 | 2/125 |
| reach3d-b0-matched | 40 | 0 | 0 | 2/154 | 2/173 |
| reach3d-b0-threat | 79 | 0 | 0 | 2/152 | 3/170 |
| reach3d-b1-matched | 57 | 0 | 0 | 2/152 | 3/175 |
| reach3d-b1-threat | 79 | 0 | 0 | 3/149 | 5/171 |
| reach3d-b2-matched | 49 | 0 | 0 | 1/151 | 1/171 |
| reach3d-b2-threat | 65 | 0 | 0 | 1/149 | 5/169 |
| reach3d-b3-matched | 60 | 0 | 0 | 1/152 | 3/174 |
| reach3d-b3-threat | 75 | 0 | 0 | 1/148 | 3/170 |
| reach3d-b4-matched | 53 | 0 | 0 | 1/150 | 2/175 |
| reach3d-b4-threat | 46 | 0 | 0 | 1/147 | 2/173 |
| reach3d-b5-matched | 58 | 0 | 0 | 1/153 | 2/174 |
| reach3d-b5-threat | 62 | 0 | 0 | 1/150 | 2/169 |
| reach3d-b6-matched | 62 | 0 | 0 | 2/154 | 4/173 |
| reach3d-b6-threat | 53 | 0 | 0 | 2/153 | 4/168 |
| reach3d-b7-matched | 54 | 0 | 0 | 3/154 | 3/172 |

Table 8. Study 2, learning under threat. Per task, blocks x fresh threat scenarios; the share of block-scenario pairs whose learning run adopted and whose procedure then met the goal, for each arm (a non-adopted run counts 0 on every scenario); threat arm minus calm arm with the matched-block bootstrap 95% interval (blocks and scenarios resampled, arms kept paired). Capped seconds count a failed flight at its time limit. The held-out column compares the arms on the whole held-out set, 20 calm and 10 wind scenarios.

| Task | Pairs | Threat arm | Calm arm | Threat - calm | Capped seconds, threat - calm | Held-out, threat - calm |
|---|---|---|---|---|---|---|
| reach | 8 x 20 | 0.81 | 0.12 | +0.68 (+0.38 to +0.91) | -44.94 s (-59.73 to -24.86) | -0.12 (-0.38 to +0.00) |
| reach3d | 8 x 20 | 0.88 | 0.56 | +0.31 (+0.06 to +0.59) | -35.23 s (-61.68 to -10.69) | -0.12 (-0.38 to +0.00) |
| land | 8 x 20 | 0.90 | 0.39 | +0.51 (+0.16 to +0.81) | -43.04 s (-67.04 to -15.76) | +0.00 (+0.00 to +0.00) |

Table 8a. Study 2 by arm: adoption over scheduled learning runs; goals met on the threat scenarios by adopted libraries only (secondary, conditional on adoption); flights that entered a zone; median model calls and attempts per run; list-price cost of the arm's learning runs, US$.

| Task | Arm | Adopted | Goal met given adoption | Entered a zone | Calls | Attempts | Cost |
|---|---|---|---|---|---|---|---|
| reach | Threat arm | 7/8 (0.88; 0.53 to 0.98) | 129/140 (0.92; 0.86 to 0.96) | 11 | 2.5 | 1.5 | 1.071 |
| reach | Calm arm | 8/8 (1.00; 0.68 to 1.00) | 20/160 (0.12; 0.08 to 0.19) | 13 | 2.0 | 1.0 | 0.521 |
| reach3d | Threat arm | 7/8 (0.88; 0.53 to 0.98) | 140/140 (1.00; 0.97 to 1.00) | 0 | 2.0 | 1.0 | 0.902 |
| reach3d | Calm arm | 8/8 (1.00; 0.68 to 1.00) | 90/160 (0.56; 0.49 to 0.64) | 22 | 2.0 | 1.0 | 0.551 |
| land | Threat arm | 8/8 (1.00; 0.68 to 1.00) | 144/160 (0.90; 0.84 to 0.94) | 9 | 2.5 | 1.0 | 1.061 |
| land | Calm arm | 8/8 (1.00; 0.68 to 1.00) | 63/160 (0.39; 0.32 to 0.47) | 19 | 2.0 | 1.0 | 0.687 |


#!/bin/bash
# Ruling 85 point 5: the corrected simulation, run again from a clean head, in order.
#   1. the development table (5,000 samples, seed 20261120), into a new parts folder and a new output
#   2. the acceptance check against the 30 rows of the sample's development check; stops here if any row
#      is outside its full range
#   3. the N = 32, 40, 48 grid (2,000 runs, 2,000 resamples, seed 20261119), a new parts folder, one output
#   4. the N = 64, 96 grid, the same otherwise, its own new parts folder and output
# Start from paper3/ of the worktree, as a detached process:
#   PARTS_ROOT=/some/new/folder nohup bash protocol/run_sim6_rerun.sh > run_sim6_rerun.out 2>&1 &
# Nothing from 4133ba4a is overwritten: the outputs have the suffixes b and c.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-/Users/s.vajda/Development/telohelm-worktrees/p3-fix3/paper3/.venv/bin/python}
WORKERS=${WORKERS:-12}
PARTS_ROOT=${PARTS_ROOT:?set PARTS_ROOT to a folder that does not exist yet}
CHK=${CHK:-/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/cluster-20261119/chain-4802829/runs/dev3-sample-20261118-R2-devcheck.json}
POOLS=reproduction/ladder-pooled3-20261111.json
DEV=reproduction/ladder-devgrid-20261119b.json
G1=reproduction/ladder-pooled3-20261119b.json
G2=reproduction/ladder-pooled3-20261119c.json
LOG=$PARTS_ROOT/run.log
for f in "$DEV" "$G1" "$G2"; do
  if [ -e "$f" ]; then echo "refusing: $f exists" >&2; exit 2; fi
done
if [ -e "$PARTS_ROOT" ]; then echo "refusing: $PARTS_ROOT exists" >&2; exit 2; fi
mkdir -p "$PARTS_ROOT" || exit 2
stamp() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
run() { "$PY" -B -W ignore protocol/ladder_pooled3.py "$@"; }

stamp "git head $(git rev-parse HEAD)"
stamp "development table start"
run --dev --kinds --pools $POOLS --parts "$PARTS_ROOT/dev" --sims 5000 --workers "$WORKERS" --seed 20261120 --out $DEV || { stamp "development table FAILED"; exit 3; }
stamp "development table end"
run --acceptance $DEV "$CHK" | tee -a "$LOG"
if [ "${PIPESTATUS[0]}" -ne 0 ]; then stamp "acceptance FAILED: stopping before the grid"; exit 4; fi
stamp "acceptance passed"

stamp "grid N = 32 40 48 start"
run --kinds --ns 32 40 48 --pools $POOLS --parts "$PARTS_ROOT/grid-b" --sims 2000 --boot 2000 --workers "$WORKERS" --seed 20261119 --out $G1 || { stamp "grid b FAILED"; exit 5; }
stamp "grid N = 32 40 48 end"

stamp "grid N = 64 96 start"
run --kinds --ns 64 96 --pools $POOLS --parts "$PARTS_ROOT/grid-c" --sims 2000 --boot 2000 --workers "$WORKERS" --seed 20261119 --out $G2 || { stamp "grid c FAILED"; exit 6; }
stamp "grid N = 64 96 end"
stamp "done"

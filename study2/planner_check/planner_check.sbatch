#!/bin/bash -l
#SBATCH --job-name=p3-planner
#SBATCH --partition=gpu
#SBATCH --constraint=gpu-l40s
#SBATCH --qos=batch-short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=10:00:00
#SBATCH --no-requeue
#SBATCH --output=/scratch/%u/planner-check/logs/%x-%j.out
#SBATCH --error=/scratch/%u/planner-check/logs/%x-%j.err
# Paper 3, the planner check: one pass of ArduPilot's own path planner on Study 2's zone flights, as one batch job
# (notes/PLANNER-CHECK-DESIGN-20261120.md, sections 5 and 9; ruling 98 of notes/TAKEOVER-20261111.md). It makes no model
# call and needs no key. It follows cluster/scored.sbatch and cluster/nor_chain.sbatch.
#
#   mkdir -p /scratch/$USER/planner-check/logs        (once, before the first sbatch: the log folder must exist)
#   sbatch -w NODE planner_check.sbatch ARCHIVE.tgz ARCHIVE_SHA256 TAG PASS [shakedown [preloaded]]
#
# ARCHIVE.tgz     an archive made on the Mac by protocol/package_for_cluster.py from the planner branch's commit. This job
#                 unpacks it itself; it uses no other copy of the code.
# ARCHIVE_SHA256  the SHA-256 that tool printed on the Mac. It comes from outside the archive, and the job stops (20) if the
#                 archive's own SHA-256 differs.
# TAG             names the run. The run folder is runs/planner-check-TAG and the saved copy is
#                 /scratch/$USER/planner-check/TAG-passPASS/ (with -shakedown added for a shake-down).
# PASS            1 or 2. The second pass flies the same list in reverse order (design section 5). A shake-down flies pass 1.
# preloaded       (sixth argument, after shakedown or flight) the fallback of design section 4: the zone is loaded before
#                 take-off with the fence off and switched on at the moment. Only if the shake-down shows a fence cannot be loaded in flight.
# shakedown       fly the 18 development evaluation cases with all seven settings (126 flights) and not the 72 evaluation cases.
#
# What it does, on one node with four simulators at once (instances 10 to 13, one worker each):
#   0  checks its arguments and that the node is free of this user's other jobs and of the simulators' ports
#   1  unpacks the archive into /dev/shm, checks its SHA-256, builds the Python environment (as chain.sbatch does)
#   2  starts four workers, planner_check.fly --worker 0 to 3, and waits for all four
#   3  makes the summary of the pass (planner_check.summarise) from the run files
#   4  copies the run files to the saved folder, with a hash list, every two minutes and when the job ends
# The job writes only inside /dev/shm/$USER-planner-TAG-passPASS (its working folder, removed when it ends) and
# /scratch/$USER/planner-check/ (its logs and its saved folder). It writes nothing into a scored run's folders, and it
# reads no scored run's files. It never sets TELOHELM_ALLOW_SCORING_SEEDS.
#
# Statuses: 20 the archive's SHA-256 differs   21 unpacking   22 the interpreter or packages   25 the batch system started
# the job again (never flown twice under one job id)   26 bad arguments   29 the saved folder exists   59 another job of
# $USER is on this node or a simulator port of instances 10 to 13 is listening   60 the working folder exists
# 50 a worker or the summary exited non-zero   47 the last copy did not verify   99 a TERM or INT signal.
# bash, not zsh, so nothing is niced.
set -uo pipefail
ARCHIVE=${1:-}; WANT=${2:-}; TAG=${3:-}; PASS=${4:-}; MODE=${5:-flight}; ROUTE=${6:-midflight}
SUFFIX=""; [ "$MODE" = shakedown ] && SUFFIX="-shakedown"; [ "$ROUTE" = preloaded ] && SUFFIX="$SUFFIX-preloaded"
W=/dev/shm/$USER-planner-$TAG-pass$PASS$SUFFIX
SAVE=/scratch/$USER/planner-check/$TAG-pass$PASS$SUFFIX
RUN=runs/planner-check-$TAG$SUFFIX
W_OWNED=no; SAVING=no; P3=""
say() { echo "=== $(date '+%F %T') $*"; }
filelist() { ( cd "$1" && find runs -type f -print0 | sort -z | xargs -0 sha256sum ); }
copy_verified() {   # copy the run files to $SAVE/runs and check them against a hash list made from the working copy
  mkdir -p "$SAVE/runs" || return 1
  rsync -a --delete "$P3/runs/" "$SAVE/runs/" || return 1
  filelist "$P3" > "$W/saved-from.sha256" || return 1
  filelist "$SAVE" > "$W/saved-to.sha256" || return 1
  cmp -s "$W/saved-from.sha256" "$W/saved-to.sha256" || return 1
  cp "$W/saved-to.sha256" "$SAVE/SHA256SUMS"
}
save() {   # the periodic copy; a failure is printed and the job goes on
  if [ "$SAVING" = yes ] && [ -d "$P3/runs" ]; then
    rsync -a --delete "$P3/runs/" "$SAVE/runs/" || say "the periodic copy to $SAVE failed"
  fi
  return 0
}
finish() {
  local rc=$?
  if [ -n "${SAVER:-}" ]; then pkill -P "$SAVER" 2>/dev/null; kill "$SAVER" 2>/dev/null; wait "$SAVER" 2>/dev/null; fi
  if [ "$SAVING" = yes ] && [ -d "$P3/runs" ]; then
    if copy_verified; then say "run files copied to $SAVE, verified; $(du -sh "$SAVE" 2>/dev/null | cut -f1)"
    else say "THE LAST COPY DID NOT VERIFY: the working copy is left at $W on node $(hostname)"; exit 47; fi
  fi
  [ "$W_OWNED" = yes ] && rm -rf "$W"
  exit $rc
}
trap finish EXIT
trap 'say "signal received, stopping"; exit 99' TERM INT
stop() { say "JOB STOPPED at: $2 (status $1)"; exit "$1"; }
say "node $(hostname); cores $(nproc); load $(cut -d' ' -f1-3 /proc/loadavg); job ${SLURM_JOB_ID:-none}; tag $TAG; pass $PASS; mode $MODE"
if [ "${SLURM_RESTART_COUNT:-0}" != 0 ]; then
  trap - EXIT
  stop 25 "the batch system started this job again (restart count $SLURM_RESTART_COUNT)"
fi
case "$PASS" in 1|2) ;; *) stop 26 "PASS is '$PASS'; it must be 1 or 2" ;; esac
case "$MODE" in flight|shakedown) ;; *) stop 26 "the fifth argument is '$MODE'; it must be absent or shakedown" ;; esac
case "$ROUTE" in midflight|preloaded) ;; *) stop 26 "the sixth argument is '$ROUTE'; it must be absent or preloaded" ;; esac
[ "$MODE" = shakedown ] && [ "$PASS" != 1 ] && stop 26 "a shake-down flies pass 1"
case "$TAG" in ''|*[!A-Za-z0-9._-]*) stop 26 "TAG is '$TAG'; use letters, digits, dots, dashes and underscores" ;; esac
[ -n "$ARCHIVE" ] && [ -n "$WANT" ] || stop 26 "usage: planner_check.sbatch ARCHIVE.tgz ARCHIVE_SHA256 TAG PASS [shakedown]"

# The node must be free of this user's other jobs and of the simulator ports of instances 10 to 13 (the scored run's
# check, K1 of cluster/scored.sbatch), so that this job cannot meet a scored job's simulators.
SIM_INSTANCES="10 11 12 13"
node=$(hostname -s)
others=$(squeue -u "$USER" -t R,CG -w "$node" -h -o %i) || stop 59 "squeue failed, so it cannot be told whether the node is free"
others=$(printf '%s\n' "$others" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -vx "$SLURM_JOB_ID" | grep . | tr '\n' ' ')
[ -z "$others" ] || stop 59 "job(s) ${others% } of $USER are running on node $node; nothing is written"
command -v ss >/dev/null 2>&1 || stop 59 "ss is not installed, so the listening ports cannot be read"
listen=$(ss -ltn | awk '$1 == "LISTEN" { print $4 }') || stop 59 "the listening ports could not be read"
for i in $SIM_INSTANCES; do
  for off in 0 2 3; do
    port=$((5760 + 10 * i + off))
    printf '%s\n' "$listen" | grep -Eq "[.:]$port\$" && stop 59 "TCP port $port (instance $i) is already listening; nothing is written"
  done
done
[ ! -e "$SAVE" ] || stop 29 "the saved folder $SAVE exists; a run is never written over"
[ ! -e "$W" ] || stop 60 "the working folder $W exists; nothing is touched"
mkdir -p "$W" || stop 21 "making the working folder"
W_OWNED=yes

GOT=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
say "archive $ARCHIVE sha256 $GOT"
[ "$GOT" = "$WANT" ] || stop 20 "the archive's SHA-256 is not the one given on the command line ($WANT)"
mkdir -p "$SAVE" || stop 21 "making the saved folder"      # made only after the archive has been checked
tar -xzf "$ARCHIVE" -C "$W" || stop 21 "unpacking"
P3=$(echo "$W"/dcarr-runtime-*/paper3)
cd "$P3" || stop 21 "no paper3 folder in the archive"
[ -f planner_check/fly.py ] || stop 21 "the archive has no planner_check folder"
say "code: $(head -c 60 SOURCE.json | tr -d '\n ')"
cp -a ~/.local/share/uv/python/cpython-3.12.15-linux-x86_64-gnu "$W/py" || stop 22 "copying the interpreter into memory"
~/.local/bin/uv venv -q --python "$W/py/bin/python3.12" .venv && ~/.local/bin/uv pip install -q --no-deps --python .venv/bin/python \
  -r ~/paper3-run/requirements-mac.txt protocol/telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl || stop 22 "building the Python environment"
mkdir -p runs
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP COLUMNS
unset TELOHELM_ALLOW_SCORING_SEEDS
export PAPER3_PLATFORM=cluster ARDUPILOT_HOME=/scratch/$USER/paper3-probe/ardupilot PYTHONDONTWRITEBYTECODE=1
PY=.venv/bin/python
say "$($PY --version); simulator binary sha256 $(sha256sum "$ARDUPILOT_HOME/build/sitl/bin/arducopter" | cut -c1-16); ArduPilot commit $(git -C "$ARDUPILOT_HOME" rev-parse --short HEAD 2>/dev/null)"
say "source fingerprint of the scored build, for reference: $($PY -W ignore -B -c 'from ardupilot import scored; scored.use_protocol(3); f = scored.source_fingerprint(); print(f["sha256"], f["files"])')"

SAVING=yes
( while sleep 120; do save; done ) &
SAVER=$!

FLAGS=""; [ "$MODE" = shakedown ] && FLAGS="--shakedown"; [ "$ROUTE" = preloaded ] && FLAGS="$FLAGS --preloaded-fence"
mkdir -p "$RUN/logs"
say "starting four workers: pass $PASS, instances 10 to 13, $MODE"
PIDS=()
for k in 0 1 2 3; do
  timeout --signal=TERM --kill-after=120 32400 $PY -B -m planner_check.fly --pass "$PASS" --worker "$k" \
    --out "$RUN/pass$PASS/worker$k" $FLAGS > "$RUN/logs/worker$k.log" 2>&1 &
  PIDS+=($!)
done
STATUS=0
for k in 0 1 2 3; do
  wait "${PIDS[$k]}"; rc=$?
  say "worker $k exited $rc"
  [ $rc -eq 0 ] || STATUS=50
done
save
$PY -B -m planner_check.summarise "$RUN" --out "$RUN/summary-pass$PASS.json" > "$RUN/summary-pass$PASS.txt" 2>&1
rc=$?; say "summary exited $rc"
[ $rc -eq 0 ] || STATUS=50
say "PLANNER CHECK PASS $PASS FINISHED (status $STATUS)"
exit $STATUS

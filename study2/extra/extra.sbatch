#!/bin/bash -l
#SBATCH --job-name=p3-extra
#SBATCH --partition=gpu
#SBATCH --constraint=gpu-l40s
#SBATCH --qos=batch-short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=2-00:00:00
#SBATCH --no-requeue
#SBATCH --output=/scratch/%u/paper3-probe/logs/%x-%j.out
#SBATCH --error=/scratch/%u/paper3-probe/logs/%x-%j.err
# Paper 3's extra experiment (paper3/PROTOCOL-EXTRA.md) as one batch job, on the node type Study 2 flew on (an L40S node,
# CPU only, 16 cores, 32 GB), built the way cluster/scored.sbatch builds Study 2's jobs:
#
#   sbatch extra.sbatch ARCHIVE.tgz ARCHIVE_SHA256 TAG arm-e reach 4.33          # arm E for one task, with its control
#   sbatch extra.sbatch ARCHIVE.tgz ARCHIVE_SHA256 TAG arm-e-rehearsal reach 0 B  # block B, scripted replies, no paid call
#   sbatch extra.sbatch ARCHIVE.tgz ARCHIVE_SHA256 TAG yard all                   # the yardstick, all three tasks
#   sbatch extra.sbatch ARCHIVE.tgz ARCHIVE_SHA256 TAG arm-e-resume reach 2.10 "why" # a later job on the same saved run
#
# ARCHIVE.tgz is made on the Mac by protocol/package_for_cluster.py from a named commit of claude/paper3-extra-arm; its
# SHA-256 comes from outside the archive. The job unpacks it into its own folder in /dev/shm, checks the SHA-256, builds
# the Python environment from the wheel Study 2 flew, checks the gateway key with one free request (cluster/key_check.py)
# when the mode builds requests, and runs extra/run_extra.py. The run files are copied to the saved folder
# /scratch/$USER/paper3-runs/extra-TAG-TASK/ every two minutes and when the job ends; that last copy counts only when the
# files at the destination, hashed, match the working copy. The job removes its own /dev/shm folder only after a copy has
# verified, and never another job's. A resume (MODE ending in -resume, same TAG and TASK) copies the saved run back into a
# new /dev/shm folder, retires the dead job's RUNNING marker, and runs the driver with --resume, which sets aside each
# phase left without a done mark (at most twice for each) before it goes on from the done marks. Its last argument is
# the reason, written to the run's log.
#
# Study 2's saved runs are read in place and never written: /scratch/$USER/paper3-runs/scored-20261120-S-TASK/runs/...
#
# Status: 0 the driver finished with every phase done and the copy verified; the driver's own 1 (phases held for a decision)
# and 3 (refused to start) are passed on; 20 archive SHA-256; 21 unpacking; 22 environment; 23 key refused; 24 key check got
# no answer; 26 bad arguments; 27 the working or saved folder exists already (or, for a resume, the saved run is missing);
# 28 a resume could not restore the saved run; 29 another of this user's jobs is running on the node; 47 no copy verified
# (the working copy is left in /dev/shm, named in the log).
#
# Study 2's machine check (scored.machine_check) counts every simulator this user runs on the node, so two of these jobs on
# one node refuse each other's flights. Each job is pinned to its own L40S node with sbatch --nodelist=l40s-f-0N, as
# Study 2's three jobs each had a node of their own; the job stops with status 29 if it finds another of this user's jobs
# running on its node.
set -uo pipefail
ARCHIVE=$1; WANT=$2; TAG=$3; MODE=${4:-}; TASK=${5:-}; STOP=${6:-0}; BLOCKS=${7:-}
REASON=$BLOCKS
W=/dev/shm/$USER-p3extra-$TAG-$TASK
SAVE=/scratch/$USER/paper3-runs/extra-$TAG-$TASK
S2BASE=/scratch/$USER/paper3-runs
W_OWNED=no
SAVING=no
P3=""
say() { echo "=== $(date '+%F %T') $*"; }
stop() { say "JOB STOPPED at: $2 (status $1)"; exit "$1"; }
filelist() { ( cd "$1/runs" && find . -type f -print0 | sort -z | xargs -0 sha256sum ); }
save() { [ "$SAVING" = yes ] && { rsync -a "$P3/runs/" "$SAVE/runs/" || say "the periodic copy to $SAVE failed: rsync exited $?"; }; }
copy_verified() {
  rsync -a --delete "$P3/runs/" "$SAVE/runs/" || { say "the copy to $SAVE failed"; return 1; }
  filelist "$P3" > "$W/saved-from.sha256" && filelist "$SAVE" > "$W/saved-to.sha256" || { say "hashing failed"; return 1; }
  cmp -s "$W/saved-from.sha256" "$W/saved-to.sha256" || { say "the copy to $SAVE did not verify"; return 1; }
  cp "$W/saved-to.sha256" "$SAVE/SHA256SUMS"
}
finish() {
  local rc=$?
  if [ -n "${SAVER:-}" ]; then kill "$SAVER" 2>/dev/null; wait "$SAVER" 2>/dev/null; fi
  if [ "$SAVING" = yes ] && [ -d "$P3/runs" ]; then
    local n=1 ok=no
    while [ $n -le 3 ]; do if copy_verified; then ok=yes; break; fi; sleep 30; n=$((n+1)); done
    if [ $ok = yes ]; then say "run files copied to $SAVE, verified; $(du -sh "$SAVE" | cut -f1)"; [ "$W_OWNED" = yes ] && rm -rf "$W"
    else say "RUN FILES NOT SAVED: the working copy is left at $W on node $(hostname)"; exit 47; fi
  elif [ "$W_OWNED" = yes ]; then rm -rf "$W"; fi
  say "job ends with status $rc"
}
trap finish EXIT
trap 'say "signal received, stopping"; exit 99' TERM INT

say "node $(hostname); cores $(nproc); nice $(nice); load $(cut -d' ' -f1-3 /proc/loadavg); job $SLURM_JOB_ID; tag $TAG; mode $MODE; task $TASK"
[ "${SLURM_RESTART_COUNT:-0}" = 0 ] || { trap - EXIT; stop 25 "the batch system started this job again; a job is never flown twice"; }
case "$MODE" in
  arm-e|arm-e-rehearsal|arm-e-resume) case "$TASK" in reach|reach3d|land) ;; *) stop 26 "TASK must be reach, reach3d or land" ;; esac ;;
  yard|yard-rehearsal|yard-resume) [ "$TASK" = all ] || stop 26 "the yardstick job flies all three tasks: TASK must be all" ;;
  *) stop 26 "MODE is '$MODE'" ;;
esac
OTHERS=$(squeue -h -u "$USER" -w "${SLURMD_NODENAME:-$(hostname -s)}" -t RUNNING -o %A | grep -vx "$SLURM_JOB_ID" | tr '\n' ' ')
[ -z "$OTHERS" ] || stop 29 "another job of $USER is running on this node ($OTHERS); the machine check counts all of this user's simulators on the node, so each job needs a node of its own (submit with --nodelist)"
[ "$MODE" = arm-e-rehearsal ] && { [ -n "$BLOCKS" ] || stop 26 "a rehearsal names its blocks"; }
case "$MODE" in *-resume) [ -n "$REASON" ] || stop 26 "a resume gives its reason" ;; esac
mkdir "$W" 2>/dev/null || stop 27 "the working folder $W exists already or cannot be made; nothing is removed"
W_OWNED=yes
case "$MODE" in
  *-resume) [ -d "$SAVE/runs" ] || stop 27 "a resume needs the saved run $SAVE/runs" ;;
  *) mkdir "$SAVE" 2>/dev/null || stop 27 "the saved folder $SAVE exists already; give another TAG" ;;
esac

GOT=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
say "archive $ARCHIVE sha256 $GOT"
[ "$GOT" = "$WANT" ] || stop 20 "the archive's SHA-256 is not the one given ($WANT)"
tar -xzf "$ARCHIVE" -C "$W" || stop 21 "unpacking"
P3=$(echo "$W"/dcarr-runtime-*/paper3)
cd "$P3" || stop 21 "no paper3 folder in the archive"
say "code: $(head -c 60 SOURCE.json | tr -d '\n ')"
cp -a ~/.local/share/uv/python/cpython-3.12.15-linux-x86_64-gnu "$W/py" || stop 22 "copying the interpreter into memory"
~/.local/bin/uv venv -q --python "$W/py/bin/python3.12" .venv && ~/.local/bin/uv pip install -q --no-deps --python .venv/bin/python \
  -r ~/paper3-run/requirements-mac.txt protocol/telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl || stop 22 "building the Python environment"
say "packages list sha256 $(sha256sum ~/paper3-run/requirements-mac.txt | cut -d' ' -f1); $(.venv/bin/python --version)"
mkdir -p runs
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP COLUMNS
export PAPER3_PLATFORM=cluster ARDUPILOT_HOME=/scratch/$USER/paper3-probe/ardupilot PYTHONDONTWRITEBYTECODE=1
say "simulator binary sha256 $(sha256sum "$ARDUPILOT_HOME/build/sitl/bin/arducopter" | cut -c1-16)"
PY=.venv/bin/python

case "$MODE" in
  *-resume)
    rsync -a "$SAVE/runs/" "$P3/runs/" || stop 28 "copying the saved run back from $SAVE"
    for m in "$P3"/runs/*/logs/RUNNING; do
      [ -e "$m" ] || continue
      mv "$m" "$m.dead-$(date +%Y%m%d%H%M%S)" || stop 28 "retiring $m"
      say "retired the dead job's marker $m"
    done
    say "restored $(find "$P3/runs" -type f | wc -l | tr -d ' ') files from $SAVE" ;;
esac

if [ "${MODE#yard}" = "$MODE" ]; then
  out=$(env -u ANTHROPIC_LOG timeout 300 $PY -B cluster/key_check.py 2>&1); krc=$?
  say "key check: $out"
  case $krc in 0) ;; 3) stop 23 "the key was refused" ;; *) stop 24 "the key check got no answer it could use (status $krc)" ;; esac
fi

SAVING=yes
( while sleep 120; do save; done ) &
SAVER=$!

S2=$S2BASE/scored-20261120-S-$TASK/runs/scored-20261120-S-$TASK
IDS="$S2BASE/scored-20261120-S-reach/runs/scored-20261120-S-reach/message-ids.jsonl $S2BASE/scored-20261120-S-reach3d/runs/scored-20261120-S-reach3d/message-ids.jsonl $S2BASE/scored-20261120-S-land/runs/scored-20261120-S-land/message-ids.jsonl"
case "$MODE" in
  arm-e)           timeout --signal=TERM --kill-after=120 158400 $PY -B extra/run_extra.py arm-e "runs/extra-$TAG-$TASK" --task "$TASK" --study2 "$S2" --seen-ids $IDS --spend-limit "$STOP" --control; rc=$? ;;
  arm-e-rehearsal) timeout --signal=TERM --kill-after=120 158400 $PY -B extra/run_extra.py arm-e "runs/extra-$TAG-$TASK" --task "$TASK" --study2 "$S2" --spend-limit 0.01 --pilot --blocks "$BLOCKS" --control; rc=$? ;;
  yard)            timeout --signal=TERM --kill-after=120 158400 $PY -B extra/run_extra.py yard "runs/yard-$TAG" "runs/yard-dev-$TAG"; rc=$? ;;
  yard-rehearsal)  timeout --signal=TERM --kill-after=120 158400 $PY -B extra/run_extra.py yard "runs/yard-$TAG" "runs/yard-dev-$TAG" --pilot; rc=$? ;;
  arm-e-resume)    timeout --signal=TERM --kill-after=120 158400 $PY -B extra/run_extra.py arm-e "runs/extra-$TAG-$TASK" --task "$TASK" --study2 "$S2" --seen-ids $IDS --spend-limit "$STOP" --control --resume "$REASON (job $SLURM_JOB_ID)"; rc=$? ;;
  yard-resume)     timeout --signal=TERM --kill-after=120 158400 $PY -B extra/run_extra.py yard "runs/yard-$TAG" "runs/yard-dev-$TAG" --resume "$REASON (job $SLURM_JOB_ID)"; rc=$? ;;
esac
say "driver exit $rc; load $(cut -d' ' -f1-3 /proc/loadavg)"
exit $rc

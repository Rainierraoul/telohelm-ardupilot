"""Which layouts the first candidate failed in its zone test, over every block of Study 2.

    python3 -I first_candidate_zone_test.py <records folder>

<records folder> is where study2-records.zip was unzipped; it holds runs/. For each learning block
(runs/scored-20261120-S-<task>/learn3-<task>-b<N>/arms.json) the script takes arm B's first trial,
which is the first candidate's zone test that arms B and C share, and counts by task: blocks whose
first candidate flew the zone test (one refused at the format check has a trial with no flights), blocks where it failed, blocks where it failed the close layout,
and blocks where the close layout was the only one it failed. A layout counts as failed when its
flight's trial_passed is false. Reads the records and writes nothing."""
import json, sys
from collections import Counter
from pathlib import Path

runs = Path(sys.argv[1]) / "runs"
count = Counter()
for task in ("reach", "reach3d", "land"):
    blocks = sorted((runs / f"scored-20261120-S-{task}").glob(f"learn3-{task}-b*/arms.json"))
    assert len(blocks) == 40, (task, len(blocks))
    for path in blocks:
        trials = json.loads(path.read_text())["arms"]["B"]["trials"]
        first = [t for t in trials if t["candidate_id"] == "c0"]
        if not first or not first[0]["outcomes"]:
            # a first candidate refused at the format check has a trial with no flights
            count[task, "first candidate not flown"] += 1
            continue
        failed = {o["episode_id"].split("-")[1] for o in first[0]["outcomes"] if not o["trial_passed"]}
        count[task, "flew"] += 1
        if failed:
            count[task, "failed"] += 1
        if "close" in failed:
            count[task, "failed close"] += 1
        if failed == {"close"}:
            count[task, "failed close only"] += 1
keys = ("flew", "failed", "failed close", "failed close only", "first candidate not flown")
for task in ("reach", "reach3d", "land", "all"):
    row = {k: (sum(count[t, k] for t in ("reach", "reach3d", "land")) if task == "all" else count[task, k]) for k in keys}
    print(task, row)

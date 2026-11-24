"""Check the paper's results from the study records. Python only: no simulator and no model.

    python reproduce.py study2 --records <folder> [--sums <CONTENTS-SHA256SUMS file>] [--work <new folder>]
    python reproduce.py study1 --records <folder> [--sums <CONTENTS-SHA256SUMS.txt>] [--work <new folder>]

<folder> is where the ZIPs of the data record were unzipped. It then holds runs/.

Study 2 (the main experiment). Four checks, each printed as PASS, FAIL or NOT RUN:

1. With --sums, every file a list of SHA-256 sums names is compared with it. Give the list of each ZIP you unzipped,
   one --sums for each. A named file that is not in <folder> fails the check, unless it is a simulator-log file,
   which is counted and reported, because the simulator logs are separate ZIPs that no check here needs.
2. The deposited analysis.json, report.md and validation report have the SHA-256 sums this repository records in
   study2/results/scored-20261120-S/SHA256SUMS, so the output being checked is the output the paper was written from.
3. The independent recomputation runs again. The four programs in study2/reproduction/independent-check-20261122/
   read the outcome records and recompute the three primary intervals and the six secondary ones with their own code.
   The two tables they build from the records are compared byte for byte with the files deposited beside them (one
   names the folder the records were read from, which is written as the original first). The check was first run on
   a copy of the records that held only what it reads, and the full records also hold, in each procedure's flights
   folder, the run's own library folder and run-config.json. The integrity table reports these as unexpected entries;
   those reports, and only those, are set aside before the comparison, and the number set aside is printed. Their two result files are
   compared value by value: every count, name and label equal and every number within 0.000000001, leaving out the
   entry that records the computer and the versions of Python and numpy. The result is also compared with
   analysis.json by the rule
   fixed before the check was made (estimates equal, names the same, interval ends within 0.01). The programs name
   the folder on the author's computer where the records lay; a working copy is made with that one line changed to
   <folder>/runs, and the deposited programs are not altered. This check needs study2-interval-records.zip only
   (33 MB), and numpy.
4. The frozen analysis runs again on the full records. Its report.md is compared byte for byte with the deposited
   one, and its analysis.json key by key and value by value, after the run folders' path and the code folder's path
   are written as the original ones (the analysis ran from a temporary folder on the cluster). The bytes of analysis.json can differ in one way: it lists its input files in the order the file system gives
   them, and that order is not the same on every computer. This needs the full records
   ZIP, the packages in study2/cluster/requirements-mac.txt and the study's wheel. Without the full records it is
   reported as NOT RUN. The analysis program itself refuses to analyse a run twice: it writes analysis-run.json into
   each run folder and stops if it finds one, and the deposited folders hold that file. This script therefore calls
   the same two frozen functions the program calls, the validation check (validate3.load_runs) and the analysis of
   what it loaded (analysis3.analyse_snapshot), and writes no run record. Nothing else differs.

Study 1 and the earlier comparison: study1/reproduce.py runs unchanged, as it was reviewed in November 2026. Its own
docstring lists its checks. In files under study1/, written before the main experiment existed, 'Study 2' means the
earlier comparison of Supplement S13.

Exit status 0 means every check that ran passed. A check that did not run is named, and is not a pass.
The records are read and never written. Everything this script writes goes into the work folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
S2 = HERE / "study2"
CHECK = S2 / "reproduction" / "independent-check-20261122"
RESULTS = S2 / "results" / "scored-20261120-S"
TAG = "scored-20261120-S"
TASKS = ("reach", "reach3d", "land")
ORIGINAL_RUNS = "/dev/shm/svajda-p3combine-4875747/dcarr-runtime-a970d1a413c5/paper3/runs"
ORIGINAL_TREE = "/dev/shm/svajda-p3combine-4875747/dcarr-runtime-a970d1a413c5/paper3"
FULL_RECORD_ONLY = ": unexpected entries in flights/: ['library', 'run-config.json']"
CHECK_DATA_LINES = ('DATA = ("/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/"\n'
                    '        "scored-20261120-S-extract/data/runs")\n')
CHECK_DATA_FOLDER = "/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-20261120-S-extract/data/runs"
OPTIONAL_PARTS = ("/simulators/", "/simulator/")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_sums(records: Path, sums: Path):
    """Every file a list names must be there with its sum. Only simulator-log files may be absent, and they are counted."""
    checked, absent_ok, missing, wrong = 0, 0, [], []
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        path = records / rel
        if not path.exists():
            if any(part in rel for part in OPTIONAL_PARTS):
                absent_ok += 1
            else:
                missing.append(rel)
            continue
        checked += 1
        if sha256(path) != digest:
            wrong.append(rel)
    ok = checked > 0 and not missing and not wrong
    detail = (f"{checked} files match; {absent_ok} simulator-log files not unzipped; "
              f"{len(missing)} missing; {len(wrong)} differ")
    return ok, detail + (f" (first: {(missing + wrong)[0]})" if missing or wrong else "")


def deposited_output(records: Path):
    """Where the deposited analysis output lies under <folder>, and whether it has the recorded SHA-256 sums."""
    want = dict(reversed(line.split("  ", 1)) for line in (RESULTS / "SHA256SUMS").read_text().splitlines() if line.strip())
    places = {"analysis.json": records / "runs" / f"{TAG}-analysis" / "analysis.json",
              "report.md": records / "runs" / f"{TAG}-analysis" / "report.md",
              f"{TAG}-gate.json": records / "runs" / f"{TAG}-gate.json"}
    bad = [name for name, path in places.items() if not path.is_file() or sha256(path) != want[name]]
    if sha256(RESULTS / "report.md") != want["report.md"]:
        bad.append("report.md in this repository")
    return places, (not bad, "analysis.json, report.md and the validation report have the recorded SHA-256"
                    if not bad else "missing or different: " + ", ".join(bad))


def first_difference(new, old, path="", tolerance=1e-9):
    """Where two JSON values first differ, or None. Numbers that are not whole may differ by the tolerance."""
    if isinstance(new, dict) and isinstance(old, dict):
        if set(new) != set(old):
            return f"{path}: different keys"
        return next((d for k in sorted(new) if (d := first_difference(new[k], old[k], f"{path}/{k}", tolerance))), None)
    if isinstance(new, list) and isinstance(old, list):
        if len(new) != len(old):
            return f"{path}: different lengths"
        return next((d for i, (x, y) in enumerate(zip(new, old))
                     if (d := first_difference(x, y, f"{path}[{i}]", tolerance))), None)
    if isinstance(new, float) or isinstance(old, float):
        both = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (new, old))
        return None if both and abs(new - old) <= tolerance else path
    return None if new == old and type(new) is type(old) else path


def independent_check(records: Path, work: Path, analysis_json: Path):
    out = work / "independent-check"
    out.mkdir()
    for name in ("build_table.py", "bootstrap.py", "selfcheck.py", "compare_with_analysis.py"):
        text = (CHECK / name).read_text()
        if name in ("build_table.py", "selfcheck.py"):
            if text.count(CHECK_DATA_LINES) != 1:
                return [("independent recomputation", False, f"{name} does not hold the expected line naming the records folder")]
            text = text.replace(CHECK_DATA_LINES, f"DATA = {str(records / 'runs')!r}\n")
        (out / name).write_text(text)
    results = []
    for name in ("build_table.py", "bootstrap.py", "selfcheck.py"):
        with open(out / (name + ".log"), "w") as log:
            code = subprocess.run([sys.executable, "-I", "-B", name], cwd=out, stdout=log, stderr=subprocess.STDOUT).returncode
        if code != 0:
            return results + [(f"independent recomputation, {name}", False, f"exit {code}; see {out / (name + '.log')}")]
    same = (out / "outcomes.json").read_text() == (CHECK / "outcomes.json").read_text()
    results.append(("independent recomputation, outcomes.json matches the deposited file", same,
                    "identical" if same else f"differs; see {out / 'outcomes.json'}"))
    # integrity.json names the folder the records were read from; it is written as the original before comparing.
    new = json.loads((out / "integrity.json").read_text().replace(str(records / "runs"), CHECK_DATA_FOLDER))
    problems = new.get("problems", [])
    kept = [x for x in problems if not (isinstance(x, str) and x.endswith(FULL_RECORD_ONLY))]
    new["problems"] = kept
    same = new == json.loads((CHECK / "integrity.json").read_text())
    note = (f"; {len(problems) - len(kept)} reports of the run's library folder and run-config.json in a flights "
            "folder set aside" if len(kept) < len(problems) else "")
    results.append(("independent recomputation, integrity.json matches the deposited file", same,
                    ("every key and value equal" + note) if same else f"differs; see {out / 'integrity.json'}"))
    for name in ("RESULT.json", "SELFCHECK.json"):
        new, old = json.loads((out / name).read_text()), json.loads((CHECK / name).read_text())
        new.pop("environment", None), old.pop("environment", None)
        where = first_difference(new, old)
        bytes_same = (out / name).read_bytes() == (CHECK / name).read_bytes()
        results.append((f"independent recomputation, {name} matches the deposited file", where is None,
                        ("every value equal" + ("; identical bytes" if bytes_same else "; the bytes differ, as they do "
                         "on another computer or version")) if where is None else f"differs at {where}"))
    with open(out / "COMPARISON.md", "w") as f:
        code = subprocess.run([sys.executable, "-I", "-B", "compare_with_analysis.py", "RESULT.json", str(analysis_json)],
                              cwd=out, stdout=f, stderr=subprocess.DEVNULL).returncode
    text = (out / "COMPARISON.md").read_text() if code == 0 else ""
    rows = [line for line in text.splitlines() if line.startswith("| ") and line.rstrip().endswith("|")
            and line.rstrip().rstrip("|").rstrip().endswith(("yes", "NO"))]
    agree = [line for line in rows if line.rstrip().rstrip("|").rstrip().endswith("yes")]
    results.append(("the independent recomputation agrees with analysis.json", code == 0 and len(rows) == 18 and len(agree) == 18,
                    f"{len(agree)} of {len(rows)} rows agree (9 intervals and the 9 per-task steps beside them)"))
    # The comparison's third line gives the SHA-256 of RESULT.json, whose bytes depend on the computer; it is left out.
    lines = lambda t: [line for line in t.splitlines() if not line.startswith("Independent result:")]
    same = code == 0 and lines(text) == lines((CHECK / "COMPARISON.md").read_text())
    results.append(("COMPARISON.md matches the deposited file", same,
                    "identical apart from the line that gives RESULT.json's own SHA-256" if same else f"differs; see {out}"))
    return results


def full_records_present(records: Path) -> bool:
    root = records / "runs" / f"{TAG}-reach"
    return (root / "logs" / "learn3-reach-b0.done").is_file() and (root / "learn3-reach-b0" / "sandbox-end.json").is_file()


RERUN = r"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from protocol import analysis3 as A, contract3 as C
from protocol.validate3 import load_runs
out, pilot, roots = Path(sys.argv[2]), sys.argv[3] == "pilot", [Path(r) for r in sys.argv[4:]]
one = roots if len(roots) > 1 else roots[0]
# The body of analysis3.analyse(), without the check that the run was not analysed before and without the run record.
gate, snapshot = load_runs(one, pilot=pilot, seed_path=Path(C.SEED_PATH), protocol_path=None)
if not gate["ok"]:
    sys.exit("the validation check failed: " + "; ".join(gate["errors"][:10]))
result = A.analyse_snapshot(snapshot, n_boot=C.BOOT_N, boot_seed=C.BOOT_SEED)
result["validation"] = gate
result["input_sha256"] = snapshot["input_sha256"]
result["inputs_aggregate_sha256"] = hashlib.sha256(C.canonical(snapshot["input_sha256"])).hexdigest()
if len(roots) > 1:
    result["roots"] = snapshot["roots"]
result["analysis_sources_sha256"] = A.analysis_sources_sha256()
out.mkdir(parents=True)
(out / "analysis.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
(out / "report.md").write_text("\n".join(A.report_lines(result)) + "\n")
"""


def frozen_analysis(tree: Path, roots: list, work: Path, deposited: dict, original_runs: str, pilot: bool = False):
    out, log = work / "analysis", work / "analysis.log"
    with open(log, "w") as f:
        code = subprocess.run([sys.executable, "-B", "-c", RERUN, str(tree), str(out), "pilot" if pilot else "scored",
                               *[str(r) for r in roots]], cwd=tree, stdout=f, stderr=subprocess.STDOUT).returncode
    results = [("the frozen analysis ran and its validation check passed", code == 0, f"exit {code}; log {log}")]
    if code == 0:
        here = str(roots[0].parent)
        new = (out / "report.md").read_text().replace(here, original_runs)
        old = deposited["report.md"].read_text()
        at = next((n for n, (x, y) in enumerate(zip(new.splitlines(), old.splitlines()), 1) if x != y), None)
        results.append(("report.md from the rerun matches the deposited file", new == old, "identical" if new == old else
                        (f"first difference at line {at}" if at else "one is longer than the other")))
        new = (out / "analysis.json").read_text().replace(here, original_runs).replace(str(tree), ORIGINAL_TREE)
        old = deposited["analysis.json"].read_text()
        same = json.loads(new) == json.loads(old)
        results.append(("analysis.json from the rerun matches the deposited file", same,
                        ("every key and value equal" + ("; identical bytes" if new == old else
                         "; the list of input files is in this file system's order, so the bytes differ")) if same
                        else "a key or a value differs"))
    return results


def study2(a):
    records = a.records.resolve()
    roots = [records / "runs" / f"{TAG}-{task}" for task in TASKS]
    for root in roots:
        if not root.is_dir():
            raise SystemExit(f"{root} is not a folder; unzip the Study 2 records into {records} first")
    work = (a.work or Path(tempfile.mkdtemp(prefix="reproduce-paper3-")) / "work").resolve()
    if work.exists():
        raise SystemExit(f"{work} exists; give a new folder")
    work.mkdir(parents=True)
    full = full_records_present(records)
    results, not_run = [], []
    if a.sums:
        for sums in a.sums:
            results.append((f"record files match {sums.name}", *check_sums(records, sums)))
    else:
        not_run.append("the comparison of the record files with the data record's sums (give --sums)")
    places, verdict = deposited_output(records)
    results.append(("the deposited analysis output is the recorded one", *verdict))
    if verdict[0]:
        results += independent_check(records, work, places["analysis.json"])
        if full:
            results += frozen_analysis(S2, roots, work, places, ORIGINAL_RUNS)
        else:
            not_run.append("the rerun of the frozen analysis (it needs the full records, study2-records.zip)")
    else:
        not_run += ["the independent recomputation's comparison and the rerun of the frozen analysis "
                    "(unzip study2-analysis-output.zip into the same folder)"]
    return finish(results, not_run, work)


def study1(a):
    command = [sys.executable, str(HERE / "study1" / "reproduce.py"), "--records", str(a.records.resolve())]
    if a.sums:
        command += ["--sums", str(a.sums[0].resolve())]
    if a.work:
        command += ["--work", str(a.work.resolve())]
    return subprocess.run(command, cwd=HERE / "study1").returncode


def finish(results, not_run, work):
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    for name in not_run:
        print(f"NOT RUN  {name}")
    print(f"work folder: {work}")
    return 0 if results and all(ok for _, ok, _ in results) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("study", choices=("study1", "study2"))
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--sums", type=Path, action="append")
    p.add_argument("--work", type=Path)
    a = p.parse_args(argv)
    return study2(a) if a.study == "study2" else study1(a)


if __name__ == "__main__":
    sys.exit(main())

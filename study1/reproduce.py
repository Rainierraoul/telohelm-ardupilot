"""Rebuild paper 3's results from the study records in its Zenodo data record, and compare them with the archive.

    python reproduce.py --records <folder> [--sums CONTENTS-SHA256SUMS.txt] [--work <new folder>]

<folder> is where scored-2-records.zip was unzipped: it holds runs/scored-2. The simulator-log ZIP is not needed.

1. With --sums, every file in the records is checked against the data record's CONTENTS-SHA256SUMS.txt (files of the
   simulator-log ZIP are skipped when that ZIP was not unzipped).
2. The frozen analysis runs as the scheduler ran it on 6 November 2026: protocol/analysis.py on the run root, second
   protocol, five tasks, eight blocks. It verifies every hash-chained log and runs the validation gate first, and
   computes no outcome if the gate fails.
3. Its analysis.json and report.md are compared byte for byte with results/scored-2-20261106/, after the run root's
   path is written as the original one (the records name the folder they were written in).
4. The result tables are rebuilt with manuscript/results_tables.py and compared with
   manuscript/drafts/RESULTS-TABLES-scored-2.md, apart from the line that names the input file.

It prints one line per check and exits 0 only if every check passes. It reads the records and writes only into the
work folder, which must not exist.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "results" / "scored-2-20261106"
TABLES = HERE / "manuscript" / "drafts" / "RESULTS-TABLES-scored-2.md"
ORIGINAL_ROOT = "/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/scored-2"
TASKS = "reach,reach3d,avoid,orbit,land"
BLOCKS = "8"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_sums(records: Path, sums: Path) -> tuple[bool, str]:
    checked, missing, wrong, skipped = 0, [], [], 0
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        path = records / rel
        if not path.exists():
            if "/simulator/" in rel or "/simulators/" in rel:
                skipped += 1
            else:
                missing.append(rel)
            continue
        checked += 1
        if sha256(path) != digest:
            wrong.append(rel)
    ok = not missing and not wrong
    return ok, (f"{checked} files match; {skipped} simulator-log files not unzipped; "
                f"{len(missing)} missing; {len(wrong)} differ" + (f" (first: {(missing + wrong)[0]})" if not ok else ""))


def same_text(new: Path, old: Path, root: Path, skip_prefix: str | None = None) -> tuple[bool, str]:
    a = new.read_text().replace(str(root), ORIGINAL_ROOT)
    b = old.read_text()
    if skip_prefix:
        a = "\n".join(l for l in a.splitlines() if not l.startswith(skip_prefix))
        b = "\n".join(l for l in b.splitlines() if not l.startswith(skip_prefix))
    if a == b:
        return True, "identical"
    for n, (x, y) in enumerate(zip(a.splitlines(), b.splitlines()), 1):
        if x != y:
            return False, f"first difference at line {n}"
    return False, "one is longer than the other"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--records", type=Path, required=True)
    p.add_argument("--sums", type=Path)
    p.add_argument("--work", type=Path)
    a = p.parse_args(argv)
    root = (a.records / "runs" / "scored-2").resolve()
    if not root.is_dir():
        raise SystemExit(f"{root} is not a folder; unzip scored-2-records.zip into {a.records} first")
    work = (a.work or Path(tempfile.mkdtemp(prefix="reproduce-paper3-")) / "work").resolve()
    if work.exists():
        raise SystemExit(f"{work} exists; give a new folder")
    work.mkdir(parents=True)
    results = []

    if a.sums:
        results.append(("records match the data record's checksums", *check_sums(a.records.resolve(), a.sums)))

    out = work / "analysis"
    log = work / "analysis.log"
    with open(log, "w") as f:
        code = subprocess.run([sys.executable, str(HERE / "protocol" / "analysis.py"), str(root), "--out", str(out),
                               "--tasks", TASKS, "--protocol", "2", "--blocks", BLOCKS],
                              cwd=HERE, stdout=f, stderr=subprocess.STDOUT).returncode
    results.append(("analysis ran and the validation gate passed", code == 0, f"exit {code}; log {log}"))
    if code == 0:
        for name in ("analysis.json", "report.md"):
            results.append((f"{name} matches the archive", *same_text(out / name, ARCHIVE / name, root)))
        tables = work / "RESULTS-TABLES.md"
        with open(tables, "w") as f:
            t = subprocess.run([sys.executable, str(HERE / "manuscript" / "results_tables.py"), str(out / "analysis.json")],
                               cwd=HERE, stdout=f, stderr=subprocess.STDOUT).returncode
        if t == 0:
            results.append(("result tables match the paper's", *same_text(tables, TABLES, root, skip_prefix="From `")))
        else:
            results.append(("result tables rebuilt", False, f"exit {t}; see {tables}"))

    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    print(f"work folder: {work}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())

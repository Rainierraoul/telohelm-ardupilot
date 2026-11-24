"""Independent check, step 1: build the outcome tables from the raw records.

Reads, as data only:
  <root>/learn3-<task>-b<N>/arms.json
  <root>/threat3-<task>-b<N>-<sha>/manifest.json
  <root>/threat3-<task>-b<N>-<sha>/flights/<case>/outcome.json
  <root>/threat3-<task>-b<N>-<sha>/flights/results.jsonl
  <root>/threat3-<task>-b<N>-<sha>/flights/summary.json
  <root>/threat3-<task>-b<N>-<sha>/kept-late.json   (presence and flight names only)

Never opens: the .set-aside folders, analysis-run.json, logs/, retain3 folders.

Writes outcomes.json and integrity.json beside this script.
Any missing folder or missing outcome stops the program; nothing is filled with 0
except the arms that adopted nothing (protocol section 6.1).
"""
import json
import os
import re
import sys

DATA = ("/Users/s.vajda/Development/DCARR-RUNTIME/paper3/runs/"
        "scored-20261120-S-extract/data/runs")
HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = ["reach", "reach3d", "land"]          # protocol 6.2: index 0, 1, 2
ARMS = ["A", "B", "C", "D"]
BANDS = ["close", "middle", "wide"]
N_BLOCKS = 40
PER_BAND = 8
CASE_RE = re.compile(r"^threat-(close|middle|wide)-(\d+)$")


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def case_key(name):
    m = CASE_RE.match(name)
    if not m:
        raise SystemExit(f"unexpected case name {name!r}")
    return (BANDS.index(m.group(1)), int(m.group(2)))


def main():
    outcomes = {}
    integrity = {"tasks": {}, "problems": []}
    problems = integrity["problems"]

    for task in TASKS:
        root = os.path.join(DATA, f"scored-20261120-S-{task}")
        top = sorted(os.listdir(root))
        threat_re = re.compile(rf"^threat3-{re.escape(task)}-b(\d+)-([0-9a-f]{{64}})$")
        threat_folders = {}
        for name in top:
            m = threat_re.match(name)
            if m:
                threat_folders[(int(m.group(1)), m.group(2))] = name
        learn_re = re.compile(rf"^learn3-{re.escape(task)}-b(\d+)$")
        learn_blocks = sorted(int(learn_re.match(n).group(1)) for n in top if learn_re.match(n))
        if learn_blocks != list(range(N_BLOCKS)):
            raise SystemExit(f"{task}: learning blocks are {learn_blocks}, expected 0..39")

        scen_ref = None                       # the 24 planned cases, from the manifests
        cells = {a: [] for a in ARMS}         # arm -> 40 lists of 24 ints
        adopted = {a: [] for a in ARMS}
        sources = {a: [] for a in ARMS}
        candidates = {a: [] for a in ARMS}
        used = set()
        end_reason_table = {}
        kept_late = []
        n_outcomes = 0
        disagree_results = 0
        disagree_summary = 0
        shared = {}                           # how many blocks have arms sharing a source

        for b in range(N_BLOCKS):
            arms = load(os.path.join(root, f"learn3-{task}-b{b}", "arms.json"))["arms"]
            if sorted(arms) != ARMS:
                raise SystemExit(f"{task} b{b}: arms are {sorted(arms)}")
            by_source = {}
            for a in ARMS:
                rec = arms[a]
                ad = rec["adopted"]
                sha = rec.get("source_sha256")
                if not isinstance(ad, bool):
                    raise SystemExit(f"{task} b{b} {a}: adopted is {ad!r}")
                if ad != (sha is not None):
                    raise SystemExit(f"{task} b{b} {a}: adopted={ad} but source_sha256={sha!r}")
                adopted[a].append(ad)
                sources[a].append(sha)
                candidates[a].append(rec.get("candidate_id"))
                if ad:
                    by_source.setdefault(sha, []).append(a)
            pattern = "|".join("".join(v) for v in sorted(by_source.values()))
            shared[pattern] = shared.get(pattern, 0) + 1

            flown = {}                        # sha -> list of 24 ints in scenario order
            for sha, arms_of in by_source.items():
                key = (b, sha)
                if key not in threat_folders:
                    raise SystemExit(f"{task} b{b}: adopted source {sha} has no threat3 folder")
                used.add(key)
                folder = os.path.join(root, threat_folders[key])
                man = load(os.path.join(folder, "manifest.json"))
                args = man["args"]
                if man.get("phase") != "threat3" or args["task"] != task or args["block"] != b \
                        or args["source_sha256"] != sha:
                    problems.append(f"{task} b{b} {sha[:12]}: manifest does not match its folder")
                if sorted(args["arms"]) != sorted(arms_of):
                    problems.append(f"{task} b{b} {sha[:12]}: manifest arms {args['arms']} "
                                    f"but arms.json gives {arms_of}")
                cases = sorted(args["cases"], key=case_key)
                if len(cases) != 24 or len(set(cases)) != 24:
                    raise SystemExit(f"{task} b{b} {sha[:12]}: manifest lists {len(cases)} cases")
                if scen_ref is None:
                    scen_ref = cases
                    per_band = [sum(1 for c in cases if case_key(c)[0] == i) for i in range(3)]
                    if per_band != [PER_BAND] * 3:
                        raise SystemExit(f"{task}: cases per band are {per_band}")
                elif cases != scen_ref:
                    raise SystemExit(f"{task} b{b} {sha[:12]}: its 24 cases differ from the task's")
                fdir = os.path.join(folder, "flights")
                listing = sorted(os.listdir(fdir))
                extra = sorted(set(listing) - set(cases) - {"results.jsonl", "summary.json"})
                missing = sorted(set(cases) - set(listing))
                if missing:
                    raise SystemExit(f"{task} b{b} {sha[:12]}: flights missing {missing}")
                if extra:
                    problems.append(f"{task} b{b} {sha[:12]}: unexpected entries in flights/: {extra}")

                row = []
                per_band_met = [0, 0, 0]
                from_outcome = {}
                for c in cases:
                    o = load(os.path.join(fdir, c, "outcome.json"))
                    g = o["goal_met"]
                    if not isinstance(g, bool):
                        raise SystemExit(f"{task} b{b} {sha[:12]} {c}: goal_met is {g!r}")
                    if o.get("task") != task:
                        problems.append(f"{task} b{b} {sha[:12]} {c}: outcome task is {o.get('task')!r}")
                    er = str(o.get("end_reason"))
                    k = f"{er}|goal_met={g}"
                    end_reason_table[k] = end_reason_table.get(k, 0) + 1
                    from_outcome[c] = (g, er)
                    row.append(1 if g else 0)
                    per_band_met[case_key(c)[0]] += 1 if g else 0
                    n_outcomes += 1
                flown[sha] = row

                # second source: results.jsonl
                with open(os.path.join(fdir, "results.jsonl"), "r", encoding="utf-8") as fh:
                    rows = [json.loads(line) for line in fh if line.strip()]
                seen = {}
                for r in rows:
                    name = f"{r['family']}-{r['seed']}"
                    if name in seen:
                        problems.append(f"{task} b{b} {sha[:12]}: results.jsonl repeats {name}")
                    seen[name] = (r["goal_met"], str(r.get("end_reason")))
                if sorted(seen, key=case_key) != cases or len(rows) != 24:
                    problems.append(f"{task} b{b} {sha[:12]}: results.jsonl has {len(rows)} rows, "
                                    f"{len(seen)} distinct, not the 24 cases")
                for c in cases:
                    if c in seen and seen[c] != from_outcome[c]:
                        disagree_results += 1
                        problems.append(f"{task} b{b} {sha[:12]} {c}: results.jsonl {seen[c]} "
                                        f"against outcome.json {from_outcome[c]}")

                # third source: summary.json
                fam = load(os.path.join(fdir, "summary.json"))["families"]
                for i, band in enumerate(BANDS):
                    rec = fam.get(f"threat-{band}")
                    if rec is None or rec["of"] != PER_BAND or rec["met"] != per_band_met[i]:
                        disagree_summary += 1
                        problems.append(f"{task} b{b} {sha[:12]} {band}: summary.json {rec} "
                                        f"against {per_band_met[i]} of 8 from outcome.json")
                if sorted(fam) != [f"threat-{x}" for x in BANDS]:
                    problems.append(f"{task} b{b} {sha[:12]}: summary families {sorted(fam)}")

                kl = os.path.join(folder, "kept-late.json")
                if os.path.exists(kl):
                    rec = load(kl)
                    kept_late.append({"block": b, "source_sha256": sha, "arms": arms_of,
                                      "record": rec,
                                      "recorded_goal_met": {c: from_outcome[c][0]
                                                            for c in rec.get("kept_late_flights", [])},
                                      "recorded_end_reason": {c: from_outcome[c][1]
                                                              for c in rec.get("kept_late_flights", [])}})

            for a in ARMS:
                sha = sources[a][b]
                cells[a].append(list(flown[sha]) if sha is not None else [0] * 24)

        # threat3 folders no arm adopted: must be the block's c0 folder; never used
        unused = sorted(set(threat_folders) - used)
        unused_not_c0 = []
        for (b, sha) in unused:
            man = load(os.path.join(root, threat_folders[(b, sha)], "manifest.json"))
            if not man["args"].get("includes_c0"):
                unused_not_c0.append(threat_folders[(b, sha)])
        if unused_not_c0:
            problems.append(f"{task}: threat3 folders neither adopted nor c0: {unused_not_c0}")

        outcomes[task] = {
            "scenarios": scen_ref,
            "bands": [BANDS[case_key(c)[0]] for c in scen_ref],
            "cells": cells,
            "adopted": adopted,
            "source_sha256": sources,
            "candidate_id": candidates,
        }
        integrity["tasks"][task] = {
            "root": root,
            "threat3_folders_in_root": len(threat_folders),
            "threat3_folders_used": len(used),
            "threat3_folders_unused_c0_only": len(unused),
            "outcome_files_read": n_outcomes,
            "end_reason_by_goal_met": dict(sorted(end_reason_table.items())),
            "cells_disagreeing_with_results_jsonl": disagree_results,
            "bands_disagreeing_with_summary_json": disagree_summary,
            "kept_late_folders": kept_late,
            "blocks_by_which_arms_share_a_source": dict(sorted(shared.items())),
            "adopted_blocks": {a: sum(adopted[a]) for a in ARMS},
        }

    with open(os.path.join(HERE, "outcomes.json"), "w", encoding="utf-8") as fh:
        json.dump(outcomes, fh, indent=1)
    with open(os.path.join(HERE, "integrity.json"), "w", encoding="utf-8") as fh:
        json.dump(integrity, fh, indent=1)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "kept_late_folders"}
                      for k, v in integrity["tasks"].items()}, indent=1))
    print("kept-late folders:", {t: len(v["kept_late_folders"]) for t, v in integrity["tasks"].items()})
    print("problems:", len(problems))
    for p in problems[:40]:
        print("  ", p)


if __name__ == "__main__":
    sys.exit(main())

#!/bin/bash
#SBATCH --job-name=p3-oadj
#SBATCH --partition=gpu
#SBATCH --nodelist=l40s-f-01
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=/scratch/svajda/planner-check/logs/p3-oadj-%j.out
set -euo pipefail
out=/scratch/svajda/planner-check/oadj-20261121
mkdir -p $out
for p in 1 2; do
  ~/paper3-probe/venv/bin/python -I -B ~/planner-oadj/read_oadj.py /scratch/svajda/planner-check/20261120-P-pass$p/runs/planner-check-20261120-P > $out/oadj-pass$p.jsonl
  echo "pass $p: $(wc -l < $out/oadj-pass$p.jsonl) flights"
done

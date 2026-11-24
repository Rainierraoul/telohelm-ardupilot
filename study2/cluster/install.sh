#!/bin/bash
# Unpack a Paper 3 archive made by protocol/package_for_cluster.py and give it a Python 3.12 environment with the
# Mac's exact package versions (no dependency resolution, as on the Mac). Usage: ~/paper3-run/install.sh ARCHIVE.tgz
# Prints the path of the unpacked paper3 folder on its last line.
set -euo pipefail
cd ~/paper3-run
top=$(tar -tzf "$1" | sed -n 1p | cut -d/ -f1)   # sed reads to the end, so tar is not cut off under pipefail
rm -rf "$top"
tar -xzf "$1"
cd "$top/paper3"
~/.local/bin/uv venv -q --clear --python 3.12 .venv
~/.local/bin/uv pip install -q --no-deps --python .venv/bin/python -r ~/paper3-run/requirements-mac.txt protocol/telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl
.venv/bin/python -c "import pymavlink, numpy, scipy.optimize, anthropic, telohelm, tokenizers, jinja2"
# Run folders are large (a pilot is about 1 GB) and /home is nearly full, so runs/ lives on /scratch.
mkdir -p "/scratch/$USER/paper3-runs/$top"
[ -e runs ] || ln -s "/scratch/$USER/paper3-runs/$top" runs
echo "$PWD"

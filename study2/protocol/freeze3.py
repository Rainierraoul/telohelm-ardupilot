"""Write the frozen values of the third protocol's scored run, once.

  .venv/bin/python protocol/freeze3.py --platform-from PATH/TO/manifest.json

The file protocol/FROZEN-3.json holds what the scored run must match (notes/TAKEOVER-20261111.md, ruling 39, point 5):
  source_fingerprint          sha256 and file count, from scored.source_fingerprint() under scored.use_protocol(3)
  wheel_sha256                the wheel the gate and the manifests name (scored.WHEEL)
  seeds_sha256                protocol/seeds-3.json
  protocol_sha256             PROTOCOL-3.md, the frozen protocol; the tool refuses if that file is absent
  delay_check_expected_sha256 protocol/delay-check3-expected-3p.json
  pilot_adoption_sha256       protocol/pilot3-adoption-3p.json
  platform                    the platform of record: partition, node type and processor model
The platform comes from the platform record that every cluster manifest carries (scored.platform_record), in a manifest the
caller names, usually the rehearsal's. The partition is its slurm_job_partition and the processor model is its cpu_model.
The record has no field for a node type, so the node type is its node name with the trailing node number cut off
(l40s-f-02 gives l40s-f), because the L40S nodes are one speed group and a run may land on any of them.

The file is written once. The tool refuses to overwrite it, so a change after the freeze cannot be made by running the
tool again. The gate (validate3.check_frozen) reads the file and refuses a scored run whose records differ from it, or
that has no such file. This tool changes no other file.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FROZEN_PATH = ROOT / 'protocol' / 'FROZEN-3.json'
SEEDS = ROOT / 'protocol' / 'seeds-3.json'
PROTOCOL = ROOT / 'PROTOCOL-3.md'
DELAY_EXPECTED = ROOT / 'protocol' / 'delay-check3-expected-3p.json'
PILOT_ADOPTION = ROOT / 'protocol' / 'pilot3-adoption-3p.json'
KEYS = ('source_fingerprint', 'wheel_sha256', 'seeds_sha256', 'protocol_sha256', 'delay_check_expected_sha256',
        'pilot_adoption_sha256', 'platform')
PLATFORM_FIELDS = {'partition': 'platform.slurm_job_partition', 'cpu_model': 'platform.cpu_model',
                   'node_type': 'platform.node, with the trailing -NN removed'}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def node_type(node: str) -> str:
    """The node's name without its number: l40s-f-02 gives l40s-f."""
    return re.sub(r'-\d+$', '', node)


def platform_of(manifest: Path) -> dict:
    """The platform of record from one cluster manifest's platform record."""
    manifest = Path(manifest)
    try:
        record = json.loads(manifest.read_text()).get('platform')
    except (OSError, ValueError, AttributeError) as error:
        raise SystemExit(f'{manifest} cannot be read as a manifest ({error})')
    if not isinstance(record, dict) or record.get('platform') != 'cluster':
        raise SystemExit(f'{manifest} has no cluster platform record; the platform of record is a cluster node')
    for field in ('slurm_job_partition', 'cpu_model', 'node'):
        if not isinstance(record.get(field), str) or not record[field]:
            raise SystemExit(f'{manifest}: the platform record has no {field}')
    return {'partition': record['slurm_job_partition'], 'node_type': node_type(record['node']),
            'cpu_model': record['cpu_model'], 'taken_from': {'manifest': str(manifest), 'fields': dict(PLATFORM_FIELDS)}}


def frozen_values(*, manifest: Path, fingerprint: dict | None = None, wheel: Path | None = None, seeds: Path = SEEDS,
                  protocol: Path = PROTOCOL, delay_expected: Path = DELAY_EXPECTED,
                  pilot_adoption: Path = PILOT_ADOPTION) -> dict:
    """The values to freeze. Every path is a parameter so that a test can use temporary files."""
    if not Path(protocol).is_file():
        raise SystemExit(f'{protocol} is absent; the frozen protocol must exist before the freeze')
    for path in (seeds, delay_expected, pilot_adoption):
        if not Path(path).is_file():
            raise SystemExit(f'{path} is absent; nothing is frozen')
    if fingerprint is None or wheel is None:
        from ardupilot import scored as S
        S.use_protocol(3)
        fingerprint = fingerprint or S.source_fingerprint()
        wheel = wheel or S.WHEEL
    return {'schema_version': 1, 'written': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
            'source_fingerprint': {'sha256': fingerprint['sha256'], 'files': fingerprint['files']},
            'wheel_sha256': sha256(wheel), 'seeds_sha256': sha256(seeds), 'protocol_sha256': sha256(protocol),
            'delay_check_expected_sha256': sha256(delay_expected), 'pilot_adoption_sha256': sha256(pilot_adoption),
            'platform': platform_of(manifest)}


def freeze(*, manifest: Path, out: Path = FROZEN_PATH, **paths) -> Path:
    out = Path(out)
    if out.exists():
        raise SystemExit(f'{out} exists; the frozen values are written once and never overwritten')
    values = frozen_values(manifest=manifest, **paths)
    try:
        with open(out, 'x') as f:           # 'x' fails if the file appeared since the check above
            f.write(json.dumps(values, indent=1) + '\n')
    except FileExistsError:
        raise SystemExit(f'{out} exists; the frozen values are written once and never overwritten')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--platform-from', type=Path, required=True, help='a cluster manifest.json, usually the rehearsal\'s')
    a = p.parse_args(argv)
    print(freeze(manifest=a.platform_from))
    return 0


if __name__ == '__main__':
    sys.exit(main())

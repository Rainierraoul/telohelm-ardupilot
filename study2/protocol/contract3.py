"""Shared, model-free protocol-3 identities and paths.

Read a reserved seed book -> select the declared cohort -> construct exact
scenario lists -> derive phase paths. No inferred schedule from completed files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

TASKS = ('reach', 'reach3d', 'land')
ARMS = ('A', 'B', 'C', 'D')
BANDS = ('close', 'middle', 'wide')
STEPS = {'C-B': ('C', 'B'), 'B-A': ('B', 'A'), 'D-C': ('D', 'C'), 'D-A': ('D', 'A')}
SEED_PATH = Path(__file__).with_name('seeds-3.json')
# The key under which the driver records the settings it requested, in each call receipt and in request.json.
# Provisional: the driver (ardupilot/ladder.py, job 2 of notes/TAKEOVER-20261111.md) has to write it under this name.
SETTINGS_FIELD = 'requested_settings'
BOOT_SEED = 20261112
BOOT_N = 10000


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def book(seeds: dict, pilot: bool) -> dict:
    return seeds['pilot'] if pilot else seeds


def learning_cases(seeds: dict, task: str, block: int, pilot: bool = False, *, threat: bool = True):
    from ardupilot.battle import generate
    row = book(seeds, pilot)['blocks'][task][block]
    return [generate(task, 'threat' if threat else 'matched', row[b], gap_stratum=b) for b in BANDS]


# The four simulators of a scored run (scored.SCORED_INSTANCES, timing_preflight3.INSTANCES).
FLIGHT_INSTANCES = (10, 11, 12, 13)


def flight_order(n: int, instance: int) -> list:
    """The order in which the simulator on instance flies a phase's n scheduled cases: simulator k of the four starts k
    quarters of the way down the list and wraps round, so that phases flying the same list together do not fly the
    same case at the same moment. It is the timing preflight's four-at-once order (timing_preflight3.case_order), and
    the scored run's evaluation phases fly in it (notes/TAKEOVER-20261111.md, round two, ruling 2). An instance outside
    the four, which only a development run may use, flies the listed order. Order cannot change a flight's inputs."""
    k = FLIGHT_INSTANCES.index(instance) if instance in FLIGHT_INSTANCES else 0
    start = k * n // len(FLIGHT_INSTANCES)
    return [(start + i) % n for i in range(n)]


def evaluation_cases(seeds: dict, task: str, pilot: bool = False):
    from ardupilot.battle import generate
    rows = book(seeds, pilot)['threat_evaluation'][task]
    return [generate(task, 'threat', seed, gap_stratum=b) for b in BANDS for seed in rows[b]]


def retention_cases(seeds: dict, task: str, pilot: bool = False):
    from ardupilot.battle import generate
    rows = book(seeds, pilot)['heldout'][task]
    return [generate(task, family, seed) for family in ('calm', 'wind') for seed in rows[family]]


def phase_name(phase: str, task: str, block: int, source: str | None = None) -> str:
    if phase not in ('learn3', 'threat3', 'retain3') or task not in TASKS or block < 0:
        raise ValueError('Unknown protocol-3 phase/task/block')
    if (phase == 'learn3') != (source is None):
        raise ValueError('Only evaluation phases require a source hash')
    if source is not None and (len(source) != 64 or any(c not in '0123456789abcdef' for c in source)):
        raise ValueError('Expected a SHA-256 source identity')
    return f'{phase}-{task}-b{block}' + (f'-{source}' if source else '')


def source_roles(arms: dict, candidates: dict, *, include_c0: bool) -> dict:
    """A source is evaluated once within a block; independent blocks stay separate."""
    out = {}
    for arm in ARMS:
        row = arms[arm]
        if row['adopted']:
            out.setdefault(row['source_sha256'], {'arms': [], 'includes_c0': False})['arms'].append(arm)
    if include_c0 and candidates['c0']['format_valid']:
        h = candidates['c0']['source_sha256']
        out.setdefault(h, {'arms': [], 'includes_c0': False})['includes_c0'] = True
    return out

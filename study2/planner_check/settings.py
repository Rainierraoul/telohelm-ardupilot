"""The seven planner settings of the check and the parameters that are the same in all of them.

A setting is one complete set of planner parameters, flown on every scenario. The values and where each comes from are
in sections 2 and 3 of notes/PLANNER-CHECK-DESIGN-20261120.md. Every value is either ArduPilot Copter 4.7.2's own default
or a value the ArduPilot wiki calls typical; none was chosen to suit the results.

The planner reads OA_TYPE only when the autopilot starts, so a setting goes into a defaults file that the simulator is
given at start-up (design fact 4). Setting it over the link afterwards would leave the planner off.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ardupilot.autopilot_modes import LIMITS

# The headline setting, named in advance (design section 3): Dijkstra with every parameter at ArduPilot's default.
HEADLINE = 1

# Where the two values that a setting does not use take ArduPilot's own default. They are written into the file
# anyway, so that every setting writes the same parameter names and the read-back has the same list to check.
MARGIN_DEFAULT_M = 5.0      # OA_MARGIN_MAX_DEFAULT, libraries/AC_Avoidance/AP_OAPathPlanner.cpp, line 31
LOOKAHEAD_DEFAULT_M = 15.0  # OA_BENDYRULER_LOOKAHEAD_DEFAULT, libraries/AC_Avoidance/AP_OABendyRuler.cpp, line 28

OA_OFF, OA_BENDYRULER, OA_DIJKSTRA = 0, 1, 2   # the documented values of OA_TYPE (AP_OAPathPlanner.cpp, line 42)


@dataclass(frozen=True)
class Setting:
    number: int
    oa_type: int          # OA_TYPE
    margin_m: float       # OA_MARGIN_MAX: how far from a fence the planner tries to stay
    lookahead_m: float    # OA_BR_LOOKAHEAD: how far ahead BendyRuler looks
    label: str


# Setting 0 is the planner switched off. Type 3 (both planners) is left out: with no proximity sensor it flies as type 2
# (design fact 10).
SETTINGS = (
    Setting(0, OA_OFF, MARGIN_DEFAULT_M, LOOKAHEAD_DEFAULT_M, 'planner off'),
    Setting(1, OA_DIJKSTRA, 5.0, LOOKAHEAD_DEFAULT_M, 'Dijkstra, margin 5 m'),
    Setting(2, OA_DIJKSTRA, 2.0, LOOKAHEAD_DEFAULT_M, 'Dijkstra, margin 2 m'),
    Setting(3, OA_BENDYRULER, 5.0, 15.0, 'BendyRuler, margin 5 m, look-ahead 15 m'),
    Setting(4, OA_BENDYRULER, 5.0, 5.0, 'BendyRuler, margin 5 m, look-ahead 5 m'),
    Setting(5, OA_BENDYRULER, 2.0, 15.0, 'BendyRuler, margin 2 m, look-ahead 15 m'),
    Setting(6, OA_BENDYRULER, 2.0, 5.0, 'BendyRuler, margin 2 m, look-ahead 5 m'),
)

# Parameters that are the same in every setting, each with where its value comes from (design section 3, second table).
FIXED = {
    'FENCE_ENABLE': (1, 'needed for either planner to read a fence (AP_OADijkstra.cpp, some_fences_enabled; AP_OABendyRuler.cpp, line 609)'),
    'FENCE_TYPE': (7, 'Copter default: altitude, circle round home, polygons and circles (AC_Fence.cpp, line 26)'),
    'FENCE_RADIUS': (150, "the simulator's own Copter defaults file, Tools/autotest/default_params/copter.parm"),
    'FENCE_ALT_MAX': (100, 'default (AC_Fence.cpp, line 30)'),
    'FENCE_MARGIN': (2, 'default (AC_Fence.cpp, line 35)'),
    'FENCE_ACTION': (1, 'default: return to launch or land on a breach (AC_Fence.cpp, line 75)'),
    'GUID_OPTIONS': (64, 'bit 6 lets the planner see a Guided position target (design fact 1)'),
    'OA_OPTIONS': (1, 'default (AP_OAPathPlanner.cpp, line 32)'),
    'OA_BR_CONT_RATIO': (1.5, 'default (AP_OABendyRuler.cpp, line 29)'),
    'OA_BR_CONT_ANGLE': (75, 'default (AP_OABendyRuler.cpp, line 30)'),
    'OA_BR_TYPE': (1, 'default (AP_OABendyRuler.cpp, line 31)'),
    'AVOID_ENABLE': (3, 'default (AC_Avoid.h, line 19); it does not act in the waypoint controller (design fact 3)'),
}

# LIMITS, imported above, is the speed limits the study's own comparator sets over the link (ardupilot/autopilot_modes.py), the
# procedures' own limits. They are not in the defaults file because the study's code sends them after start-up.


def setting(number: int) -> Setting:
    for s in SETTINGS:
        if s.number == number:
            return s
    raise ValueError(f'there is no setting {number}; the settings are 0 to {len(SETTINGS) - 1}')


# The BendyRuler parameters exist in ArduPilot 4.7.2 only when BendyRuler has been created, which happens only when
# OA_TYPE is 1 (or 3). With OA_TYPE 0 or 2 a request for one of them is answered "does not exist". The check therefore asks
# for them only in the BendyRuler settings, and in the others records that the autopilot reports them absent.
BENDYRULER_ONLY = ('OA_BR_LOOKAHEAD', 'OA_BR_CONT_RATIO', 'OA_BR_CONT_ANGLE', 'OA_BR_TYPE')


def defaults(s: Setting, preloaded: bool = False) -> dict:
    """Every parameter the defaults file of setting s holds: the setting's own and the fixed ones. The BendyRuler ones
    are written only for a BendyRuler setting. With preloaded (the fallback of design section 4) FENCE_ENABLE is 0."""
    out = {'OA_TYPE': s.oa_type, 'OA_MARGIN_MAX': s.margin_m, 'OA_BR_LOOKAHEAD': s.lookahead_m,
           **{name: value for name, (value, _) in FIXED.items()}}
    if preloaded:
        out['FENCE_ENABLE'] = 0
    if s.oa_type != OA_BENDYRULER:
        out = {k: v for k, v in out.items() if k not in BENDYRULER_ONLY}
    return out


def expected(s: Setting, preloaded: bool = False) -> dict:
    """Every parameter a flight reads back from the autopilot before take-off and compares with the setting's value:
    the defaults file's parameters and the speed limits the study's code sets."""
    return {**defaults(s, preloaded), **LIMITS}


def expected_absent(s: Setting) -> tuple:
    """The parameters the autopilot should report as not existing in this setting."""
    return BENDYRULER_ONLY if s.oa_type != OA_BENDYRULER else ()


def defaults_text(s: Setting, preloaded: bool = False) -> str:
    """The defaults file's text: one 'NAME VALUE' line a parameter, in alphabetical order."""
    return ''.join(f'{name} {value:g}\n' for name, value in sorted(defaults(s, preloaded).items()))


def write_defaults(s: Setting, path: Path, preloaded: bool = False) -> str:
    """Write setting s's defaults file to path, which must not exist, and return the file's SHA-256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'x') as f:
        f.write(defaults_text(s, preloaded))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_defaults(path: Path) -> dict:
    """The parameters a defaults file holds, as numbers."""
    out = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            name, value = line.split()
            out[name] = float(value)
    return out

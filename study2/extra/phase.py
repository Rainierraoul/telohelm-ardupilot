"""One phase of the extra experiment, as the scheduler (extra/run_extra.py) starts it:

  python -m extra.phase learnE ...     a block of arm E (extra/arm_e.py)
  python -m extra.phase yard3 ...      the hand-written yardstick on one task's zone flights (extra/yardstick.py)
  python -m extra.phase threat3 ...    Study 2's own evaluation phase, run by ardupilot/scored.py unchanged

The scheduler is Study 2's (protocol/run_scored.py), which starts every phase with one module; this one passes each
phase to the code that runs it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['learnE']:
        from extra.arm_e import phase_learn
        return phase_learn(argv[1:])
    if argv[:1] == ['yard3']:
        from extra.yardstick import phase_yard
        return phase_yard(argv[1:])
    if argv[:1] in (['threat3'], ['retain3']):
        from ardupilot import scored
        return scored.main(argv)
    raise SystemExit(f'not a phase of the extra experiment: {argv[:1]}')


if __name__ == '__main__':
    raise SystemExit(main())

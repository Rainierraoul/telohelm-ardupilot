# Protocol 3 timing counts and sensitivity analyses

protocol3 scored sensitivity analyses

## Off-stamp commands in flights kept late

Commands sent at other than the third telemetry stamp, summed over the flights kept late, by arm. A flight that is not kept late has none by construction (ardupilot/ladder.py, timing()).

| Arm | learning trials: flights kept late, commands | zone evaluation: flights kept late, commands | retention: flights kept late, commands |
|---|---:|---:|---:|
| A | 0, 0 | 3, 0 | 0, 0 |
| B | 0, 0 | 1, 0 | 0, 0 |
| C | 0, 0 | 1, 0 | 0, 0 |
| D | 0, 0 | 0, 0 | 0, 0 |

First-round flights, which the analysis does not group by arm: 0 kept late, 0 off-stamp commands.
Flights checked for the zero-by-construction rule: 14216. The rule held in all of them.

## Learning calls kept late (ruling 78)

No learning call was kept late on its third attempt. The list is empty and nothing is computed.

## Learning blocks set aside and flown again (ruling 81, ruling 87)

Set-aside learning attempts (each counts one attempt): 0. By reason on the receipt: none. By cause: none.
Distinct blocks with any set-aside attempt (each block once, whatever the reason): 0.
Distinct listed blocks (each block once, all four arms filled): 0. Listed attempts by status: 0 sent, 0 sending not established, 0 not determinable.

No set-aside attempt has a recorded fresh or repair request, a request file with no row, or missing candidate folders. The list is empty and nothing is computed.

The two analyses are separate and are never combined. Neither changes the primary estimate.

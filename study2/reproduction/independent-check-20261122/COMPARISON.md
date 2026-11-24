# The independent check compared with the scored analysis

Independent result: `RESULT.json`, SHA-256 027619a00ec284e1f851ad09bb869f4a0663468d028dad44d2c71276a1bc22ee.
Scored analysis: `analysis.json`, SHA-256 6304fbf652d96e3584e4042bb4a16232d8bdf602d3566849f8e083522ae0555b.

The rule for a match, fixed before any outcome was read: point estimates equal (to 1e-9), the section 6.4 key and the
larger-than-the-margin label the same, and each end of the 95% and 90% intervals within 0.01.

| Contrast | Kind | Estimate, independent | Estimate, analysis | 95% interval, independent | 95% interval, analysis | 90% interval, independent | 90% interval, analysis | Key, both | Largest difference of an interval end | Match |
|---|---|---:|---:|---|---|---|---|---|---:|---|
| pooled C-B | primary | +0.494444 | +0.494444 | +0.398264, +0.586111 | +0.397908, +0.586814 | +0.413524, +0.571875 | +0.413194, +0.572222 | different_not_equivalent | 0.000703 | yes |
| pooled B-A | primary | -0.211458 | -0.211458 | -0.286806, -0.131597 | -0.286806, -0.132986 | -0.274653, -0.145486 | -0.274670, -0.145833 | different_not_equivalent | 0.001389 | yes |
| pooled D-C | primary | -0.045139 | -0.045139 | -0.135764, +0.047222 | -0.136458, +0.045833 | -0.120833, +0.031597 | -0.122222, +0.031250 | equivalent_not_different | 0.001389 | yes |
| reach D-A close | secondary (RQ4) | +0.575000 | +0.575000 | +0.415625, +0.728125 | +0.418750, +0.728125 | +0.440625, +0.703125 | +0.443750, +0.703125 | different_not_equivalent | 0.003125 | yes |
| reach D-A distant | secondary (RQ4) | +0.071875 | +0.071875 | -0.068750, +0.214062 | -0.068750, +0.212500 | -0.045312, +0.190625 | -0.046875, +0.190625 | equivalent_not_different | 0.001563 | yes |
| reach3d D-A close | secondary (RQ4) | +0.571875 | +0.571875 | +0.393750, +0.731250 | +0.400000, +0.734375 | +0.425000, +0.706250 | +0.425000, +0.709375 | different_not_equivalent | 0.006250 | yes |
| reach3d D-A distant | secondary (RQ4) | +0.053125 | +0.053125 | -0.100000, +0.198437 | -0.101562, +0.201563 | -0.076563, +0.176563 | -0.075000, +0.178125 | equivalent_not_different | 0.003125 | yes |
| land D-A close | secondary (RQ4) | +0.493750 | +0.493750 | +0.321875, +0.659375 | +0.318750, +0.659375 | +0.350000, +0.631250 | +0.350000, +0.634375 | different_not_equivalent | 0.003125 | yes |
| land D-A distant | secondary (RQ4) | +0.125000 | +0.125000 | -0.078125, +0.318750 | -0.078125, +0.320312 | -0.043750, +0.290625 | -0.045312, +0.290625 | unresolved | 0.001563 | yes |
| reach C-B | per-task step | +0.412500 | +0.412500 | +0.252083, +0.562500 | +0.252083, +0.565625 | +0.278125, +0.539583 | +0.277083, +0.540625 | different_not_equivalent | 0.003125 | yes |
| reach3d C-B | per-task step | +0.546875 | +0.546875 | +0.361458, +0.712500 | +0.363542, +0.713542 | +0.392708, +0.687500 | +0.397917, +0.688542 | different_not_equivalent | 0.005208 | yes |
| land C-B | per-task step | +0.523958 | +0.523958 | +0.363542, +0.677083 | +0.363516, +0.678125 | +0.390625, +0.656250 | +0.391667, +0.655208 | different_not_equivalent | 0.001042 | yes |
| reach B-A | per-task step | -0.182292 | -0.182292 | -0.325026, -0.029167 | -0.323958, -0.030208 | -0.303125, -0.053125 | -0.301042, -0.055208 | different_not_equivalent | 0.002083 | yes |
| reach3d B-A | per-task step | -0.202083 | -0.202083 | -0.341667, -0.047917 | -0.345833, -0.053099 | -0.319792, -0.075000 | -0.322917, -0.076042 | different_not_equivalent | 0.005182 | yes |
| land B-A | per-task step | -0.250000 | -0.250000 | -0.351042, -0.151042 | -0.351042, -0.148958 | -0.335417, -0.166667 | -0.335417, -0.164583 | different_not_equivalent | 0.002083 | yes |
| reach D-C | per-task step | +0.009375 | +0.009375 | -0.137500, +0.161458 | -0.141667, +0.160417 | -0.115625, +0.137500 | -0.117708, +0.136458 | equivalent_not_different | 0.004167 | yes |
| reach3d D-C | per-task step | -0.118750 | -0.118750 | -0.256276, +0.021875 | -0.257292, +0.016667 | -0.234427, -0.004167 | -0.235417, -0.006250 | unresolved | 0.005208 | yes |
| land D-C | per-task step | -0.026042 | -0.026042 | -0.207292, +0.157292 | -0.205208, +0.159375 | -0.176042, +0.125000 | -0.176094, +0.124010 | equivalent_not_different | 0.002083 | yes |

The nine intervals of the protocol (three primary, six for RQ4): 9 of 9 match.
The nine per-task steps beside them: 9 of 9 match.
Largest difference of any point estimate: 4.44e-13. Largest difference of any interval end: 0.006250.
Pooled C-B: analysis task_dependent=False, answer status: answered.
Pooled B-A: analysis task_dependent=False, answer status: answered.
Pooled D-C: analysis task_dependent=False, answer status: not_settled.
Arm means and blocks adopted, 12 task-arm pairs: 12 of 12 equal.

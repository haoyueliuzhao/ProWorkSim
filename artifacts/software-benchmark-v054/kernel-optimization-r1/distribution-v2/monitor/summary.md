# Kernel rollout observation

Status: completed

This is an observation of different task cohorts, not a causal kernel speedup estimate.
GPU utilization and memory include all processes on each sampled device.

## baseline

| GPU | Arm | Revision | Closed | Closed/h | Median episode seconds | Complete-ledger tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 6 | MATCH | 43fb7dde14a7 | 7 | 9.33 | 555.95 | 3150223 |
| 6 | PROJECT | 43fb7dde14a7 | 2 | 2.67 | 1054.29 | 330341 |

## observed

| GPU | Arm | Revision | Closed | Closed/h | Median episode seconds | Complete-ledger tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 3 | MATCH | 43fb7dde14a7 | 1 | 2.00 | 552.63 | 361715 |
| 3 | PROJECT | 43fb7dde14a7 | 5 | 10.00 | 580.32 | 444947 |
| 6 | MATCH | 9664f6d348f3 | 4 | 8.00 | 672.34 | 1954719 |
| 7 | REF | 43fb7dde14a7 | 7 | 14.00 | 122.66 | 3182491 |

Pending/running episodes are right-censored; their final token costs are not imputed.
Token/window-second counts tokens of episodes closed within the window, including work started earlier; it is not model decode tokens/second.

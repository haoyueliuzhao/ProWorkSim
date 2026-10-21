# GPU6 native request timing supplement

- Different tasks, outputs, prompt lengths and shared-device conditions; no causal kernel speedup or accuracy-equivalence estimate.
- Cohorts contain episodes closed in monitor windows. All settled requests from those episodes are included, including work started before a window. Requests in still-running episodes are excluded, not zeroed.
- Native seconds includes prefill, decode, input tensor/start-record setup and output/logprob transfer. It excludes outer FIFO wait and earlier prompt preparation. Output tokens/native second is not isolated decode throughput.
- Queue wait includes FIFO and grant/commit delay. Executed and cancelled receipts are separate. Overlapping session waits cannot be read as GPU idle time.
- Queue receipts lack a direct native-attempt/prompt-length key. No ordinal-based join is assumed; queue summaries are by cohort/arm/operation, not prompt bucket.
- Actual tool CPU time is absent. MATCH native tool transcript has no tool wall timer. PROJECT interaction wall exists only in full world state; this metadata-only supplement does not read those task states. Tool wall/CPU remain null; configured limits and episode residuals are not substituted.
- Completion facts are reused from monitor artifacts without rereading each completion. Controller/native refs are checked once; native result files are read only to project usage, identity and timing fields.
- Missing timings are reported as errors and excluded from timed denominators. Counts and incomplete ledgers remain visible. No model requests, new GPU samples or service actions are performed.

Selected episodes: 13; timed requests: 518; extraction errors: 0.

| Cohort | Arm | Revision | Prompt tokens | Requests | Native seconds total | Output tokens | Output/native second | Median native seconds |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| baseline | MATCH | 43fb7dde14a7 | 0-2047 | 9 | 106.165 | 3077 | 28.983 | 11.248 |
| baseline | MATCH | 43fb7dde14a7 | 12288-16384 | 110 | 875.588 | 17334 | 19.797 | 5.492 |
| baseline | MATCH | 43fb7dde14a7 | 2048-4095 | 12 | 191.870 | 5625 | 29.317 | 16.609 |
| baseline | MATCH | 43fb7dde14a7 | 4096-8191 | 19 | 89.898 | 1925 | 21.413 | 3.614 |
| baseline | MATCH | 43fb7dde14a7 | 8192-12287 | 129 | 725.700 | 15311 | 21.098 | 4.244 |
| baseline | PROJECT | 43fb7dde14a7 | 12288-16384 | 53 | 397.989 | 7301 | 18.345 | 7.322 |
| baseline | PROJECT | 43fb7dde14a7 | 8192-12287 | 2 | 4.887 | 71 | 14.529 | 2.443 |
| observed | MATCH | 9664f6d348f3 | 0-2047 | 12 | 148.664 | 4818 | 32.409 | 12.471 |
| observed | MATCH | 9664f6d348f3 | 12288-16384 | 69 | 482.036 | 9495 | 19.698 | 4.759 |
| observed | MATCH | 9664f6d348f3 | 2048-4095 | 7 | 114.806 | 3725 | 32.446 | 16.637 |
| observed | MATCH | 9664f6d348f3 | 4096-8191 | 14 | 70.126 | 1700 | 24.242 | 3.644 |
| observed | MATCH | 9664f6d348f3 | 8192-12287 | 82 | 391.200 | 8460 | 21.626 | 3.749 |

| Cohort | Arm | Revision | State | Operation | Receipts | Queue seconds total | Median queue seconds |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| baseline | MATCH | 43fb7dde14a7 | executed | begin | 7 | 3.012 | 0.056 |
| baseline | MATCH | 43fb7dde14a7 | executed | finish | 7 | 26.008 | 2.458 |
| baseline | MATCH | 43fb7dde14a7 | executed | match_complete | 285 | 308.636 | 0.059 |
| baseline | MATCH | 43fb7dde14a7 | executed | match_count | 424 | 694.600 | 0.061 |
| baseline | PROJECT | 43fb7dde14a7 | executed | begin | 2 | 2.422 | 1.211 |
| baseline | PROJECT | 43fb7dde14a7 | executed | finish | 2 | 5.266 | 2.633 |
| baseline | PROJECT | 43fb7dde14a7 | executed | project_complete | 55 | 323.698 | 3.867 |
| observed | MATCH | 9664f6d348f3 | executed | begin | 4 | 12.591 | 1.289 |
| observed | MATCH | 9664f6d348f3 | executed | finish | 4 | 5.323 | 1.086 |
| observed | MATCH | 9664f6d348f3 | executed | match_complete | 188 | 390.886 | 0.121 |
| observed | MATCH | 9664f6d348f3 | executed | match_count | 312 | 749.733 | 0.122 |

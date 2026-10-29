# v085 startup throughput observation

Read-only snapshot at Unix 1793259752 (2026-10-29, Asia/Shanghai). The queue remains running with no coordinator failure. It reached 43 API actor claims and was at 41 at the final snapshot; eight of those were still in environment startup, so actor claims must not be described as simultaneous HTTP requests.

The eight-startup limit is a binding refill constraint in this observed interval, rather than merely an initially empty queue. In the preceding ten minutes, 17 of 20 existing monitor samples had at least seven pending API starts, and 14 had eight. Thirteen tasks were newly scheduled and eight completed in the same approximate window. Concurrency can still increase; this short interval does not establish a final steady-state ceiling.

For the latest 24 scheduled tasks, 16 had a ready marker. Their schedule-to-controller-ready time was 175–402 seconds, median 239 seconds. The latest six completed starts took 351–402 seconds, median 371 seconds. In those six, schedule-to-actor-ready median was 170 seconds and actor-ready-to-controller-ready median was 201 seconds. These are filesystem milestone times; they do not isolate Docker creation, bundle upload, snapshot preparation or SDK import cost.

At the final snapshot, **all eight pending tasks lacked `controller-ready.json`**. Three already had an actor-ready marker and five did not. The oldest two pending starts were approximately 511 and 472 seconds old. All 16 existing ready markers passed the frozen version / trusted-import / zero-model-call checks; their ready-to-model-dispatch delay was only 3.6–13.5 seconds. There is no evidence that the safe reader's stricter fields are holding a fully initialized task pending.

The supported conclusion is that environment startup and controller initialization currently limit replenishment. It is not evidence for loosening integrity checks or immediately increasing the startup batch; additional parallel startup could increase the same contention. No model answers, source edits, tests, container operations or service changes were involved. Exact metadata and the existing monitor window are retained in `observation.json`.

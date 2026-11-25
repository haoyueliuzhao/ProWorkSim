"""Verify the ordinary settled-action entry and evidence-dependent route catalog without API calls."""

from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_osa_checkpoint_v226 as control
import run_event_pairs_v243 as batch
from proworksim.organization_harness import run_worker_fragment
from proworksim.software_sdk_resume_v203_3_4 import read
from proworksim.software_event_harness_v243 import artifact_state, work_budget
from proworksim.software_event_orders_v243 import orders
from proworksim.storage import read_json
from proworksim.software_event_intake_v243 import NaturalCapture


def main():
    root = batch.RUN / "sdk-control"

    def observe(prep, rt, *, on_opportunity):
        return run_worker_fragment(
            prep,
            rt,
            folder=root / "capture",
            on_opportunity=on_opportunity,
            native_run=control.runtime.run_fragment,
        )

    module = SimpleNamespace(**{**vars(control.runtime), "run_fragment": observe})
    control.clone_function(control.main, {**control.main.__globals__, "runtime": module})(root)
    index = read_json(root / "capture/capture-index.json")
    assert not index["errors"]
    (event,) = index["events"]
    assert event["kind"] == "A2"
    p = root / "capture" / event["site"]
    a, _ = read(p / "checkpoint")
    b, _ = read(root / "checkpoint")
    for k in (
        "workers",
        "runtime",
        "schedule",
        "team_state",
        "world_state_sha256",
        "prefix_ledger",
    ):
        assert a[k] == b[k], k
    facts = read_json(p / "capture.json")
    assert facts["artifact_states"][0]["state"] == "unknown"
    masks = [
        ({}, "unknown"),
        ({"exists": False}, "absent"),
        ({"patch_id": "P", "published": False}, "unpublished"),
        ({"patch_id": "P", "kind": "upstream_patch_not_adopted"}, "published_not_adopted"),
        ({"patch_id": "P", "current": False}, "stale"),
        ({"patch_id": "P", "verified": False}, "unverified"),
    ]
    for v, s in masks:
        assert artifact_state(v) == s
    r = work_budget("A2", 1048576, 8, 8)
    assert (
        not r["enough"]
        and work_budget("A2", r["required"], 8, 8)["enough"]
        and not work_budget("A2", r["required"], 7, 8)["enough"]
    )
    cases = []
    for row in batch.previous.prior.sources():
        ops = orders(row)
        if ops:
            cases.append(dict(id=row["id"], types=sorted({o["dimension"] for o in ops.values()})))
    assert {"D4", "D5", "D6"} <= {d for c in cases for d in c["types"]}
    # A5 has no work package; repeated readiness before submission stays observational.
    mon = NaturalCapture(root / "unused", kinds=("A5",))

    def act(i, tool, value):
        return mon.observe(
            i,
            dict(
                worker_id="member_001",
                decision=dict(action=tool, arguments={}),
                response=dict(ok=True, command_id=f"cmd-{i}", result=value),
            ),
        )

    ready = dict(
        ready_to_submit=True,
        final_identity=dict(source_reference=dict(object_id="obj", version_id="v1")),
    )
    act(1, "delivery_readiness", ready)
    act(2, "read_file", {})
    act(3, "read_file", {})
    assert any(n["anomaly_type"] == "A5" for n in act(4, "delivery_readiness", ready))
    batch.save(
        batch.PLAN / "cpu-controls.json",
        dict(
            sdk_event=event,
            dependency_state=facts["artifact_states"],
            zero_call_capture=True,
            equal_checkpoint_fields=[
                "workers",
                "runtime",
                "schedule",
                "team_state",
                "world_state_sha256",
                "prefix_ledger",
            ],
            artifact_states=[s for _, s in masks],
            budget_boundaries=True,
            observational_A5=True,
            archived_available_orders=cases,
        ),
    )


if __name__ == "__main__":
    main()
